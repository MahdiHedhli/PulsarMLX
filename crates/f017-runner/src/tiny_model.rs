//! Checkpoint-free R12 execution through the canonical runner composition.

use crate::cli::Config;
use crate::evidence::Evidence;
use crate::{FailureClass, RunnerError};
use std::path::Path;

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
use {
    crate::checkpoint::{CheckpointKind, CheckpointManifest, VerifiedCheckpoint},
    crate::contract_bindings::{r12_contract_bindings, R12_CONTRACT_VERSIONS},
    crate::evidence::LayerEvidence,
    crate::final_output_qualification::{
        run_r11_exact, run_r11_with_decoded_matvec, R11Error, R11Inputs, R11Output,
        R11_SCAFFOLD_VERSION,
    },
    crate::glm52_map::{Glm52FixtureTensorContract, Glm52FixtureTensorMap},
    crate::json::{parse_json_no_duplicates, sha256_bytes, sha256_file},
    crate::layer_qualification::{
        run_r10_exact, run_r10_with_matvec, run_r9_exact, run_r9_with_matvec, ExpertMatrices,
        R10Inputs, R10Matrices, R10Output, R9Error, R9Inputs, R9Matrices, R9Output,
        R10_SCAFFOLD_VERSION, R9_SCAFFOLD_VERSION,
    },
    crate::numerical_classification::{
        GreedyApplicability, GreedyIdentityEvidence, NumericalClassification,
    },
    crate::qualification::{measure_f32, qualify_tier_b_down, NumericalMetrics},
    crate::store::RunnerTensorStore,
    backend::CancellationToken,
    gguf::TensorType,
    serde_json::Value,
    std::collections::BTreeMap,
    std::fs,
    std::time::Instant,
    stream::{MlxContext, MlxDebugStreamCounters, MlxDevice, MlxStreamMode},
};

pub fn run_tiny_model_fixture(
    manifest: &Path,
    config: &Config,
    evidence: &mut Evidence,
) -> Result<(), RunnerError> {
    run_tiny_model_fixture_impl(manifest, config, evidence)
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn run_tiny_model_fixture_impl(
    manifest: &Path,
    config: &Config,
    evidence: &mut Evidence,
) -> Result<(), RunnerError> {
    let fixture_started = Instant::now();
    let bytes = fs::read(manifest).map_err(|error| infrastructure("r12_manifest_read", error))?;
    let model: Value = parse_json_no_duplicates(&bytes)
        .map_err(|error| infrastructure("r12_manifest_json", error))?;
    validate_model_identity(manifest, &model, config)?;
    let checkpoint_name = model["checkpoint_manifest"]
        .as_str()
        .ok_or_else(|| infrastructure("r12_checkpoint_manifest", "missing checkpoint manifest"))?;
    if Path::new(checkpoint_name).components().count() != 1 {
        return Err(infrastructure(
            "r12_checkpoint_manifest",
            "checkpoint manifest must be a repository-relative basename",
        ));
    }
    let checkpoint_path = manifest
        .parent()
        .unwrap_or(Path::new("."))
        .join(checkpoint_name);
    let checkpoint_manifest = CheckpointManifest::load(&checkpoint_path)?;
    if checkpoint_manifest.kind != CheckpointKind::Fixture || checkpoint_manifest.shards.len() != 2
    {
        return Err(infrastructure(
            "r12_checkpoint_kind",
            "R12 requires the frozen two-shard synthetic checkpoint",
        ));
    }
    let verified = VerifiedCheckpoint::verify(&checkpoint_path, checkpoint_manifest)?;
    let contracts = tensor_contracts(&model)?;
    let fixture_map = Glm52FixtureTensorMap::from_parts(
        verified.catalog.architecture(),
        verified.catalog.tensors.iter().cloned(),
        contracts
            .values()
            .map(|contract| Glm52FixtureTensorContract {
                name: contract.name.clone(),
                dims: contract.dims.clone(),
                tensor_type: TensorType::from_id(contract.type_id),
            }),
    )?;
    if fixture_map.len() != contracts.len() || fixture_map.is_empty() {
        return Err(infrastructure(
            "r12_tensor_map",
            "fixture tensor map is incomplete",
        ));
    }
    evidence.identity.checkpoint = verified.evidence_identity();
    evidence.execution.storage.read_bytes = verified.identity_bytes_read;
    evidence.execution.storage.read_count = verified.identity_read_count;
    let store = RunnerTensorStore::open(verified)?;
    let mut cancellation = CancellationToken::new();
    if std::env::var("PULSAR_F017_FIXTURE_CANCEL_AT").as_deref() == Ok("before_tensor_load") {
        cancellation.cancel();
    }
    let identity_read_count = evidence.execution.storage.read_count;
    let load_started = Instant::now();
    let mut runtime = load_runtime(
        &store,
        &fixture_map,
        &contracts,
        &model,
        &cancellation,
        evidence,
    )?;
    runtime.loaded_tensor_count = evidence
        .execution
        .storage
        .read_count
        .saturating_sub(identity_read_count);
    evidence.execution.timings.insert(
        "storage_decode_materialization_seconds".to_owned(),
        load_started.elapsed().as_secs_f64(),
    );
    evidence.execution.progress_state = "r12_tensor_store_complete".to_owned();
    evidence.input.tokens = model["input"]["tokens"]
        .as_array()
        .unwrap()
        .iter()
        .map(|value| value.as_u64().unwrap() as u32)
        .collect();
    evidence.input.n_new = model["input"]["n_new"].as_u64().unwrap() as u32;
    evidence.input.expected_token = Some(model["input"]["expected_token"].as_u64().unwrap() as u32);

    let result = match config.numerical_mode {
        Some(crate::cli::NumericalMode::ExactQualificationScaffold) => {
            evidence.lifecycle.reconciled = true;
            run_exact(&runtime, &model, evidence)
        }
        Some(crate::cli::NumericalMode::ProductionMlxTierB) => {
            run_production(&runtime, &model, config, evidence)
        }
        None => Err(infrastructure(
            "r12_numerical_mode",
            "R12 requires an explicit numerical mode",
        )),
    };
    evidence.execution.timings.insert(
        "complete_run_seconds".to_owned(),
        fixture_started.elapsed().as_secs_f64(),
    );
    result
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
#[derive(Clone)]
struct TensorContract {
    name: String,
    dims: Vec<u64>,
    type_id: u32,
    payload_sha256: String,
    payload_bytes: usize,
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
#[derive(Clone)]
struct LayerRuntime {
    r9: R9Matrices,
    r9_inputs: R9Inputs,
    r10: R10Matrices,
    r10_inputs: R10Inputs,
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
struct TinyRuntime {
    embedding: Vec<f32>,
    layers: Vec<LayerRuntime>,
    r11: R11Inputs,
    loaded_tensor_count: u64,
    cancel_before_layer: Option<usize>,
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn validate_model_identity(
    manifest: &Path,
    model: &Value,
    config: &Config,
) -> Result<(), RunnerError> {
    if model["schema"] != "pulsarmlx.f017.r12-tiny-model-oracle"
        || model["fixture_version"] != "f017-r12-tiny-glm-dsa-v1"
        || model["independence"]["uses_rust_candidate"] != false
        || model["independence"]["uses_mlx"] != false
        || model["checkpoint_accessed"] != false
        || model["architecture"]["layer_count"] != 2
        || model["architecture"]["top_k"] != 8
    {
        return Err(infrastructure(
            "r12_contract",
            "R12 fixture contract differs",
        ));
    }
    let root = Path::new(env!("PULSARMLX_SOURCE_ROOT"));
    let generator = root.join(
        model["generator_path"]
            .as_str()
            .ok_or_else(|| infrastructure("r12_generator", "missing generator path"))?,
    );
    if sha256_file(&generator).map_err(|error| infrastructure("r12_generator", error))?
        != model["generator_sha256"]
    {
        return Err(infrastructure("r12_generator", "generator hash differs"));
    }
    if !config.tokens.is_empty() || config.n_new != 0 || config.expected_token.is_some() {
        return Err(infrastructure(
            "r12_input",
            "fixture execution inputs must come only from the frozen manifest",
        ));
    }
    if !manifest.is_file() {
        return Err(infrastructure(
            "r12_manifest",
            "fixture manifest is not a file",
        ));
    }
    Ok(())
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn tensor_contracts(model: &Value) -> Result<BTreeMap<String, TensorContract>, RunnerError> {
    let mut output = BTreeMap::new();
    for value in model["tensor_contracts"]
        .as_array()
        .ok_or_else(|| infrastructure("r12_tensor_contracts", "missing tensor contracts"))?
    {
        let name = value["name"].as_str().unwrap().to_owned();
        let contract = TensorContract {
            name: name.clone(),
            dims: value["dims"]
                .as_array()
                .unwrap()
                .iter()
                .map(|v| v.as_u64().unwrap())
                .collect(),
            type_id: value["type_id"].as_u64().unwrap() as u32,
            payload_sha256: value["payload_sha256"].as_str().unwrap().to_owned(),
            payload_bytes: value["payload_bytes"].as_u64().unwrap() as usize,
        };
        if output.insert(name, contract).is_some() {
            return Err(infrastructure(
                "r12_tensor_contracts",
                "duplicate tensor contract",
            ));
        }
    }
    Ok(output)
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn load_runtime(
    store: &RunnerTensorStore,
    map: &Glm52FixtureTensorMap,
    contracts: &BTreeMap<String, TensorContract>,
    model: &Value,
    cancellation: &CancellationToken,
    evidence: &mut Evidence,
) -> Result<TinyRuntime, RunnerError> {
    let width = model["architecture"]["hidden_width"].as_u64().unwrap() as usize;
    let vocab = model["architecture"]["vocabulary_size"].as_u64().unwrap() as usize;
    let embedding_matrix = load_f32(
        store,
        map,
        contracts,
        "token_embd.weight",
        cancellation,
        evidence,
    )?;
    let token = model["input"]["tokens"][0].as_u64().unwrap() as usize;
    let embedding = embedding_matrix[token * width..(token + 1) * width].to_vec();
    let mut layers = Vec::new();
    for layer in 0..2 {
        let expected = &model["expected"]["layers"][layer];
        let selected = expected["selected_ids"]
            .as_array()
            .unwrap()
            .iter()
            .map(|value| value.as_u64().unwrap() as usize)
            .collect::<Vec<_>>();
        let r9 = R9Matrices {
            q_a: load_q8(
                store,
                map,
                contracts,
                &format!("blk.{layer}.attn_q_a.weight"),
                cancellation,
                evidence,
            )?,
            q_b: load_q8(
                store,
                map,
                contracts,
                &format!("blk.{layer}.attn_q_b.weight"),
                cancellation,
                evidence,
            )?,
            kv_a: load_q8(
                store,
                map,
                contracts,
                &format!("blk.{layer}.attn_kv_a_mqa.weight"),
                cancellation,
                evidence,
            )?,
            k_b: load_q8(
                store,
                map,
                contracts,
                &format!("blk.{layer}.attn_k_b.weight"),
                cancellation,
                evidence,
            )?,
            v_b: load_q8(
                store,
                map,
                contracts,
                &format!("blk.{layer}.attn_v_b.weight"),
                cancellation,
                evidence,
            )?,
            output: load_q8(
                store,
                map,
                contracts,
                &format!("blk.{layer}.attn_output.weight"),
                cancellation,
                evidence,
            )?,
        };
        let runtime_inputs = &expected["runtime_inputs"];
        let r9_inputs = R9Inputs {
            residual: f32_record(&expected["input"]),
            attn_norm_scale: load_f32(
                store,
                map,
                contracts,
                &format!("blk.{layer}.attn_norm.weight"),
                cancellation,
                evidence,
            )?,
            q_norm_scale: load_f32(
                store,
                map,
                contracts,
                &format!("blk.{layer}.attn_q_a_norm.weight"),
                cancellation,
                evidence,
            )?,
            kv_norm_scale: load_f32(
                store,
                map,
                contracts,
                &format!("blk.{layer}.attn_kv_a_norm.weight"),
                cancellation,
                evidence,
            )?,
            prior_cache_latents: f32_record(&runtime_inputs["prior_cache_latents"]),
            prior_cache_ropes: f32_record(&runtime_inputs["prior_cache_ropes"]),
            q_rope_cosine: f32_record(&runtime_inputs["q_rope_cosine"]),
            q_rope_sine: f32_record(&runtime_inputs["q_rope_sine"]),
            rms_epsilon: runtime_inputs["rms_epsilon"].as_f64().unwrap() as f32,
            attention_scale: runtime_inputs["attention_scale"].as_f64().unwrap() as f32,
            query_position: runtime_inputs["query_position"].as_u64().unwrap() as usize,
            visible_positions: runtime_inputs["visible_positions"].as_u64().unwrap() as usize,
        };
        let routed = selected
            .iter()
            .map(|expert_id| {
                load_expert(
                    store,
                    map,
                    contracts,
                    layer,
                    *expert_id,
                    false,
                    cancellation,
                    evidence,
                )
            })
            .collect::<Result<Vec<_>, _>>()?;
        let shared = load_expert(
            store,
            map,
            contracts,
            layer,
            usize::MAX,
            true,
            cancellation,
            evidence,
        )?;
        let router_bias_f32 = load_f32(
            store,
            map,
            contracts,
            &format!("blk.{layer}.exp_probs_b.bias"),
            cancellation,
            evidence,
        )?;
        let r10 = R10Matrices {
            router: load_q8(
                store,
                map,
                contracts,
                &format!("blk.{layer}.ffn_gate_inp.weight"),
                cancellation,
                evidence,
            )?,
            routed,
            shared,
        };
        let r10_inputs = R10Inputs {
            attention_residual: f32_record(&expected["attention_output"]),
            post_attention_norm_scale: load_f32(
                store,
                map,
                contracts,
                &format!("blk.{layer}.ffn_norm.weight"),
                cancellation,
                evidence,
            )?,
            router_bias: router_bias_f32.into_iter().map(f64::from).collect(),
            rms_epsilon: RMS_EPSILON,
            top_k: 8,
            expert_weight_scale: 2.5,
        };
        layers.push(LayerRuntime {
            r9,
            r9_inputs,
            r10,
            r10_inputs,
        });
    }
    let output_head_packed = read_tensor(
        store,
        map,
        contracts,
        "output.weight",
        cancellation,
        evidence,
    )?;
    let r11 = R11Inputs {
        final_hidden: f32_record(&model["expected"]["final_hidden"]),
        output_norm_scale: load_f32(
            store,
            map,
            contracts,
            "output_norm.weight",
            cancellation,
            evidence,
        )?,
        rms_epsilon: RMS_EPSILON,
        output_head_packed,
        output_rows: vocab,
        output_columns: width,
        top_k: 8,
    };
    Ok(TinyRuntime {
        embedding,
        layers,
        r11,
        loaded_tensor_count: 0,
        cancel_before_layer: match std::env::var("PULSAR_F017_FIXTURE_CANCEL_AT")
            .ok()
            .as_deref()
        {
            Some("before_first_layer") => Some(0),
            Some("after_layer_0") => Some(1),
            _ => None,
        },
    })
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
const RMS_EPSILON: f32 = 1.0e-5;

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn load_expert(
    store: &RunnerTensorStore,
    map: &Glm52FixtureTensorMap,
    contracts: &BTreeMap<String, TensorContract>,
    layer: usize,
    expert_id: usize,
    shared: bool,
    cancellation: &CancellationToken,
    evidence: &mut Evidence,
) -> Result<ExpertMatrices, RunnerError> {
    let prefix = if shared {
        format!("blk.{layer}.shared")
    } else {
        format!("blk.{layer}.routed.{expert_id}")
    };
    Ok(ExpertMatrices {
        expert_id,
        gate: load_q8(
            store,
            map,
            contracts,
            &format!("{prefix}.gate.weight"),
            cancellation,
            evidence,
        )?,
        up: load_q8(
            store,
            map,
            contracts,
            &format!("{prefix}.up.weight"),
            cancellation,
            evidence,
        )?,
        down: load_q8(
            store,
            map,
            contracts,
            &format!("{prefix}.down.weight"),
            cancellation,
            evidence,
        )?,
    })
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn read_tensor(
    store: &RunnerTensorStore,
    map: &Glm52FixtureTensorMap,
    contracts: &BTreeMap<String, TensorContract>,
    name: &str,
    cancellation: &CancellationToken,
    evidence: &mut Evidence,
) -> Result<Vec<u8>, RunnerError> {
    if map.tensor(name).is_none() {
        return Err(infrastructure(
            "r12_tensor_map",
            format!("unmapped tensor {name}"),
        ));
    }
    let contract = contracts
        .get(name)
        .ok_or_else(|| infrastructure("r12_tensor_contract", name))?;
    let bytes = store
        .read_tensor_exact(name, cancellation)
        .map_err(|error| {
            if error.code() == "cancelled" {
                cancelled("r12_cancelled", error.to_string())
            } else {
                infrastructure("r12_tensor_read", error.to_string())
            }
        })?;
    if bytes.len() != contract.payload_bytes || sha256_bytes(&bytes) != contract.payload_sha256 {
        return Err(infrastructure(
            "r12_tensor_hash",
            format!("tensor {name} differs"),
        ));
    }
    evidence.execution.storage.read_bytes += bytes.len() as u64;
    evidence.execution.storage.read_count += 1;
    Ok(bytes)
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn load_f32(
    store: &RunnerTensorStore,
    map: &Glm52FixtureTensorMap,
    contracts: &BTreeMap<String, TensorContract>,
    name: &str,
    cancellation: &CancellationToken,
    evidence: &mut Evidence,
) -> Result<Vec<f32>, RunnerError> {
    let bytes = read_tensor(store, map, contracts, name, cancellation, evidence)?;
    if !bytes.len().is_multiple_of(4) {
        return Err(infrastructure("r12_f32_length", name));
    }
    Ok(bytes
        .chunks_exact(4)
        .map(|chunk| f32::from_le_bytes(chunk.try_into().unwrap()))
        .collect())
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn load_q8(
    store: &RunnerTensorStore,
    map: &Glm52FixtureTensorMap,
    contracts: &BTreeMap<String, TensorContract>,
    name: &str,
    cancellation: &CancellationToken,
    evidence: &mut Evidence,
) -> Result<Vec<f32>, RunnerError> {
    let bytes = read_tensor(store, map, contracts, name, cancellation, evidence)?;
    let contract = &contracts[name];
    if contract.type_id != 8 || contract.dims.len() != 2 {
        return Err(infrastructure("r12_q8_contract", name));
    }
    let columns = contract.dims[0] as usize;
    let rows = contract.dims[1] as usize;
    let mut output = vec![0.0_f32; rows * columns];
    quant::decode_q8_0_matrix(&bytes, rows, columns, &mut output)
        .map_err(|error| infrastructure("r12_q8_decode", error.to_string()))?;
    Ok(output)
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn run_exact(
    runtime: &TinyRuntime,
    model: &Value,
    evidence: &mut Evidence,
) -> Result<(), RunnerError> {
    let repeats = model["deterministic_repeats"].as_u64().unwrap() as usize;
    let mut first = None;
    let mut layer_seconds = vec![0.0; runtime.layers.len()];
    let mut output_head_decode_seconds = 0.0;
    let started = Instant::now();
    for _ in 0..repeats {
        let output = execute_once(runtime, None)?;
        validate_output(model, &output, true)?;
        for (total, observed) in layer_seconds.iter_mut().zip(&output.layer_seconds) {
            *total += observed;
        }
        output_head_decode_seconds += output.output_head_decode_seconds;
        if let Some(first) = &first {
            require_output_bits(first, &output)?;
        } else {
            first = Some(output);
        }
    }
    let mut output = first.unwrap();
    for total in &mut layer_seconds {
        *total /= repeats as f64;
    }
    output.layer_seconds = layer_seconds;
    output.output_head_decode_seconds = output_head_decode_seconds;
    evidence
        .execution
        .timings
        .insert("total_seconds".to_owned(), started.elapsed().as_secs_f64());
    evidence.execution.timings.insert(
        "output_head_decode_seconds".to_owned(),
        output.output_head_decode_seconds,
    );
    evidence.execution.dispatch.qualification_scaffold = (repeats * 69) as u64;
    finalize_evidence(
        evidence,
        model,
        runtime,
        &output,
        NumericalClassification::GoldenIdentical,
        repeats,
        true,
    )?;
    Ok(())
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn run_production(
    runtime: &TinyRuntime,
    model: &Value,
    config: &Config,
    evidence: &mut Evidence,
) -> Result<(), RunnerError> {
    let repeats = model["deterministic_repeats"].as_u64().unwrap() as usize;
    let streams_before = MlxContext::debug_stream_counters().map_err(adapter_error)?;
    if MlxContext::debug_context_active() {
        return Err(lifecycle(
            "r12_context_nonzero",
            "MLX singleton was already claimed",
        ));
    }
    evidence.admission.singleton_initially_unclaimed = true;
    let context = MlxContext::new(
        MlxDevice::Gpu,
        match config.stream_mode {
            crate::cli::StreamMode::DefaultGpu => MlxStreamMode::BorrowedDefault,
            crate::cli::StreamMode::OwnedDevice => MlxStreamMode::Owned,
        },
    )
    .map_err(adapter_error)?;
    if std::env::var("PULSAR_F017_FIXTURE_BACKEND_ERROR").as_deref() == Ok("1") {
        close_production_context(context, streams_before, evidence)?;
        return Err(infrastructure(
            "r12_backend_error",
            "injected fixture backend error",
        ));
    }
    let mut first = None;
    let mut layer_seconds = vec![0.0; runtime.layers.len()];
    let mut output_head_decode_seconds = 0.0;
    let mut import_seconds = 0.0;
    let mut compute_seconds = 0.0;
    let started = Instant::now();
    for _ in 0..repeats {
        let output = match execute_once(
            runtime,
            Some((&context, &mut import_seconds, &mut compute_seconds)),
        ) {
            Ok(output) => output,
            Err(error) => {
                close_production_context(context, streams_before, evidence)?;
                return Err(error);
            }
        };
        if let Err(error) = validate_production(model, runtime, &output) {
            close_production_context(context, streams_before, evidence)?;
            return Err(error);
        }
        for (total, observed) in layer_seconds.iter_mut().zip(&output.layer_seconds) {
            *total += observed;
        }
        output_head_decode_seconds += output.output_head_decode_seconds;
        if let Some(first) = &first {
            require_output_bits(first, &output)?;
        } else {
            first = Some(output);
        }
    }
    let mut output = first.unwrap();
    for total in &mut layer_seconds {
        *total /= repeats as f64;
    }
    output.layer_seconds = layer_seconds;
    output.output_head_decode_seconds = output_head_decode_seconds;
    close_production_context(context, streams_before, evidence)?;
    let total = started.elapsed().as_secs_f64();
    evidence
        .execution
        .timings
        .insert("total_seconds".to_owned(), total);
    evidence
        .execution
        .timings
        .insert("backend_import_seconds".to_owned(), import_seconds);
    evidence
        .execution
        .timings
        .insert("compute_sync_readback_seconds".to_owned(), compute_seconds);
    evidence.execution.timings.insert(
        "output_head_decode_seconds".to_owned(),
        output.output_head_decode_seconds,
    );
    evidence.execution.timings.insert(
        "orchestration_seconds".to_owned(),
        (total - import_seconds - compute_seconds - output.output_head_decode_seconds).max(0.0),
    );
    evidence.execution.dispatch.native = (repeats * 69) as u64;
    let expected_logits = record_f32(&model["expected"]["logits"])?;
    let logit_metrics = measure_f32(&expected_logits, &output.r11.logits)
        .map_err(|error| numerical("r12_logits", error.to_string()))?;
    let classification = if logit_metrics.bit_mismatch_count == 0 {
        NumericalClassification::GoldenIdentical
    } else {
        NumericalClassification::NumericallyQualifiedGreedyIdentical
    };
    finalize_evidence(
        evidence,
        model,
        runtime,
        &output,
        classification,
        repeats,
        false,
    )?;
    evidence.execution.numerical.bit_mismatch_count = Some(logit_metrics.bit_mismatch_count as u64);
    evidence.execution.numerical.max_abs_error = Some(logit_metrics.max_abs_error);
    evidence.execution.numerical.relative_error = logit_metrics.max_relative_error;
    evidence.execution.numerical.rmse = Some(logit_metrics.rmse);
    evidence.execution.numerical.cosine_similarity = logit_metrics.cosine_similarity;
    evidence.execution.numerical.first_divergence = logit_metrics
        .first_divergence
        .map(|value| serde_json::to_value(value).unwrap());
    Ok(())
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
#[derive(Clone)]
struct RunOutput {
    layers: Vec<(R9Output, R10Output)>,
    layer_seconds: Vec<f64>,
    output_head_decode_seconds: f64,
    r11: R11Output,
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn execute_once(
    runtime: &TinyRuntime,
    mut production: Option<(&MlxContext, &mut f64, &mut f64)>,
) -> Result<RunOutput, RunnerError> {
    let mut residual = runtime.embedding.clone();
    let mut outputs = Vec::new();
    let mut layer_seconds = Vec::new();
    for (layer_index, layer) in runtime.layers.iter().enumerate() {
        if runtime.cancel_before_layer == Some(layer_index) {
            return Err(cancelled(
                "r12_cancelled",
                format!("fixture cancellation requested before layer {layer_index}"),
            ));
        }
        let layer_started = Instant::now();
        let mut r9_inputs = layer.r9_inputs.clone();
        r9_inputs.residual = residual;
        let r9 = if let Some((context, import, compute)) = production.as_mut() {
            run_r9_with_matvec(&layer.r9, &r9_inputs, |m, r, c, v, _| {
                production_matvec(context, m, r, c, v, import, compute)
                    .map_err(R9Error::CandidateMatvec)
            })
        } else {
            run_r9_exact(&layer.r9, &r9_inputs)
        }
        .map_err(|error| numerical("r12_r9", error.to_string()))?;
        let mut r10_inputs = layer.r10_inputs.clone();
        r10_inputs.attention_residual = r9.output.clone();
        let r10 = if let Some((context, import, compute)) = production.as_mut() {
            run_r10_with_matvec(&layer.r10, &r10_inputs, |m, r, c, v, _| {
                production_matvec(context, m, r, c, v, import, compute)
                    .map_err(R9Error::CandidateMatvec)
            })
        } else {
            run_r10_exact(&layer.r10, &r10_inputs)
        }
        .map_err(|error| numerical("r12_r10", error.to_string()))?;
        residual = r10.output.clone();
        outputs.push((r9, r10));
        layer_seconds.push(layer_started.elapsed().as_secs_f64());
    }
    let mut r11_inputs = runtime.r11.clone();
    r11_inputs.final_hidden = residual;
    let decode_started = Instant::now();
    let decoded = crate::final_output_qualification::decode_q4_k_matrix(
        &r11_inputs.output_head_packed,
        r11_inputs.output_rows,
        r11_inputs.output_columns,
    )
    .map_err(|error| numerical("r12_q4", error.to_string()))?;
    let output_head_decode_seconds = decode_started.elapsed().as_secs_f64();
    let r11 = if let Some((context, import, compute)) = production.as_mut() {
        run_r11_with_decoded_matvec(&r11_inputs, decoded, |m, r, c, v, _| {
            production_matvec(context, m, r, c, v, import, compute)
                .map_err(|_| R11Error::CandidateMatvec("output_head"))
        })
    } else {
        run_r11_exact(&r11_inputs)
    }
    .map_err(|error| numerical("r12_r11", error.to_string()))?;
    Ok(RunOutput {
        layers: outputs,
        layer_seconds,
        output_head_decode_seconds,
        r11,
    })
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn production_matvec(
    context: &MlxContext,
    matrix: &[f32],
    rows: usize,
    columns: usize,
    vector: &[f32],
    import_seconds: &mut f64,
    compute_seconds: &mut f64,
) -> Result<Vec<f32>, &'static str> {
    let started = Instant::now();
    let mut matrix_owner = matrix.to_vec();
    let mut vector_owner = vector.to_vec();
    let matrix_array = context
        .import_f32_shaped(&mut matrix_owner, &[rows, columns])
        .map_err(|_| "matrix import")?;
    let vector_array = context
        .import_f32_shaped(&mut vector_owner, &[columns])
        .map_err(|_| "vector import")?;
    *import_seconds += started.elapsed().as_secs_f64();
    let started = Instant::now();
    let result = matrix_array.matvec(&vector_array).map_err(|_| "dispatch")?;
    result.evaluate_sync().map_err(|_| "sync")?;
    let mut output = vec![0.0_f32; rows];
    result.copy_f32(&mut output).map_err(|_| "readback")?;
    result.destroy().map_err(|_| "result destroy")?;
    vector_array.destroy().map_err(|_| "vector destroy")?;
    matrix_array.destroy().map_err(|_| "matrix destroy")?;
    *compute_seconds += started.elapsed().as_secs_f64();
    Ok(output)
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn close_production_context(
    context: MlxContext,
    streams_before: MlxDebugStreamCounters,
    evidence: &mut Evidence,
) -> Result<(), RunnerError> {
    context.synchronize().map_err(adapter_error)?;
    let ownership = context.ownership_snapshot().map_err(adapter_error)?;
    drop(context);
    let streams_after = MlxContext::debug_stream_counters().map_err(adapter_error)?;
    let active = MlxContext::debug_context_active();
    let reconciled = ownership.managed_created == ownership.managed_destroyed
        && ownership.derived_created == ownership.derived_destroyed
        && ownership.derived_live == 0
        && ownership.callback_count == ownership.managed_created
        && streams_after.owned_created - streams_before.owned_created
            == streams_after.owned_freed - streams_before.owned_freed
        && !active;
    evidence.lifecycle.post.managed_created = ownership.managed_created;
    evidence.lifecycle.post.managed_destroyed = ownership.managed_destroyed;
    evidence.lifecycle.post.derived_created = ownership.derived_created;
    evidence.lifecycle.post.derived_destroyed = ownership.derived_destroyed;
    evidence.lifecycle.post.callback_count = ownership.callback_count;
    evidence.lifecycle.post.owned_stream_created = streams_after.owned_created;
    evidence.lifecycle.post.owned_stream_freed = streams_after.owned_freed;
    evidence.lifecycle.post.active_contexts = u64::from(active);
    evidence.lifecycle.post.singleton_claimed = active;
    evidence.lifecycle.reconciled = reconciled;
    if !reconciled {
        return Err(lifecycle(
            "r12_lifecycle",
            "production R12 lifecycle did not reconcile",
        ));
    }
    Ok(())
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn validate_output(model: &Value, output: &RunOutput, exact: bool) -> Result<(), RunnerError> {
    for (index, (_, r10)) in output.layers.iter().enumerate() {
        if r10.selected_ids != usize_values(&model["expected"]["layers"][index]["selected_ids"])
            || (exact
                && f32_bytes(&r10.output)
                    != record_bytes(&model["expected"]["layers"][index]["output"]))
        {
            return Err(numerical("r12_layer", format!("layer {index} differs")));
        }
    }
    if output.r11.top_k_ids != usize_values(&model["expected"]["top_k_ids"])
        || output.r11.argmax != model["expected"]["argmax"].as_u64().unwrap() as usize
        || (exact && f32_bytes(&output.r11.logits) != record_bytes(&model["expected"]["logits"]))
    {
        return Err(numerical("r12_final_output", "R12 final output differs"));
    }
    Ok(())
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn validate_production(
    model: &Value,
    runtime: &TinyRuntime,
    candidate: &RunOutput,
) -> Result<(), RunnerError> {
    validate_output(model, candidate, false)?;
    for (index, (candidate_r9, candidate_r10)) in candidate.layers.iter().enumerate() {
        let expected_r9 = record_f32(&model["expected"]["layers"][index]["attention_output"])?;
        let expected_r10 = record_f32(&model["expected"]["layers"][index]["output"])?;
        require_metrics(
            "r9",
            &measure_f32(&expected_r9, &candidate_r9.output).unwrap(),
            0.0078125,
            0.00390625,
            0.99999,
        )?;
        require_metrics(
            "r10",
            &measure_f32(&expected_r10, &candidate_r10.output).unwrap(),
            0.0625,
            0.03125,
            0.999,
        )?;
        if usize_values(&model["expected"]["layers"][index]["selected_ids"])
            != candidate_r10.selected_ids
        {
            return Err(numerical(
                "r12_routing",
                format!("layer {index} routing diverged"),
            ));
        }
    }
    let expected_normalized = record_f32(&model["expected"]["final_normalized"])?;
    let expected_logits = record_f32(&model["expected"]["logits"])?;
    let qualification = qualify_tier_b_down(
        &candidate.r11.decoded_output_head,
        runtime.r11.output_rows,
        runtime.r11.output_columns,
        &expected_normalized,
        &expected_logits,
        &candidate.r11.logits,
    )
    .map_err(|error| numerical("r12_logits", error.to_string()))?;
    if !qualification.passes
        || usize_values(&model["expected"]["top_k_ids"]) != candidate.r11.top_k_ids
        || model["expected"]["argmax"].as_u64().unwrap() as usize != candidate.r11.argmax
    {
        return Err(numerical(
            "r12_greedy",
            "R12 production logits or greedy identity failed",
        ));
    }
    Ok(())
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn require_metrics(
    name: &str,
    metrics: &NumericalMetrics,
    max_abs: f64,
    rmse: f64,
    cosine: f64,
) -> Result<(), RunnerError> {
    if metrics.non_finite_count != 0
        || metrics.signed_zero_mismatch_count != 0
        || metrics.max_abs_error > max_abs
        || metrics.rmse > rmse
        || metrics.cosine_similarity.is_none_or(|value| value < cosine)
    {
        return Err(numerical(
            "r12_tier_b",
            format!("{name} violates frozen contract"),
        ));
    }
    Ok(())
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn finalize_evidence(
    evidence: &mut Evidence,
    model: &Value,
    runtime: &TinyRuntime,
    output: &RunOutput,
    classification: NumericalClassification,
    repeats: usize,
    exact: bool,
) -> Result<(), RunnerError> {
    evidence.execution.generated_token = Some(output.r11.argmax as u32);
    evidence.execution.numerical_classification = Some(classification);
    evidence.execution.numerical.greedy_applicability = Some(GreedyApplicability::Applicable);
    evidence.execution.numerical.greedy_identity = Some(GreedyIdentityEvidence {
        top_k_ids_exact: true,
        argmax_exact: true,
    });
    evidence.execution.numerical.oracle_generator_sha =
        Some(model["generator_sha256"].as_str().unwrap().to_owned());
    evidence.execution.numerical.scaffold_version = Some(format!(
        "{R9_SCAFFOLD_VERSION}+{R10_SCAFFOLD_VERSION}+{R11_SCAFFOLD_VERSION}"
    ));
    evidence.execution.numerical.production_backend_version =
        (!exact).then(|| "mlx-native-0.31.2-mlxc-0.6.0-production-adapter".to_owned());
    evidence.execution.numerical.frozen_contract_version =
        Some("f017-production-r11-tier-b-v1".to_owned());
    evidence.execution.numerical.frozen_contract_versions = contract_bindings(model)?;
    evidence.execution.numerical.deterministic_repeat_count = Some(repeats as u64);
    if exact {
        evidence.execution.numerical.bit_mismatch_count = Some(0);
        evidence.execution.numerical.max_abs_error = Some(0.0);
        evidence.execution.numerical.relative_error = Some(0.0);
        evidence.execution.numerical.rmse = Some(0.0);
        evidence.execution.numerical.cosine_similarity = Some(1.0);
        evidence.lifecycle.reconciled = true;
    }
    evidence.execution.layers = output
        .layer_seconds
        .iter()
        .enumerate()
        .map(|(layer, seconds)| LayerEvidence {
            layer: layer as u32,
            total_seconds: *seconds,
        })
        .collect();
    evidence.residency.decoded_hot = runtime.loaded_tensor_count;
    evidence.residency.misses = runtime.loaded_tensor_count;
    evidence.execution.progress_state = "r12_tiny_model_complete".to_owned();
    Ok(())
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn record_f32(record: &Value) -> Result<Vec<f32>, RunnerError> {
    let bytes = record_bytes(record);
    if bytes.len() % 4 != 0 {
        return Err(infrastructure(
            "r12_expected_record",
            "expected f32 record is malformed",
        ));
    }
    Ok(bytes
        .chunks_exact(4)
        .map(|chunk| f32::from_le_bytes(chunk.try_into().unwrap()))
        .collect())
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn contract_bindings(model: &Value) -> Result<BTreeMap<String, String>, RunnerError> {
    let observed = model["contracts"]
        .as_array()
        .ok_or_else(|| infrastructure("r12_contract_bindings", "missing numerical contract set"))?
        .iter()
        .map(|value| value.as_str().unwrap_or_default())
        .collect::<Vec<_>>();
    if observed != R12_CONTRACT_VERSIONS {
        return Err(infrastructure(
            "r12_contract_bindings",
            "R12 inherited contract set differs",
        ));
    }
    Ok(r12_contract_bindings())
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn require_output_bits(left: &RunOutput, right: &RunOutput) -> Result<(), RunnerError> {
    if left.layers.len() != right.layers.len()
        || left
            .layers
            .iter()
            .zip(&right.layers)
            .any(|((_, a), (_, b))| f32_bytes(&a.output) != f32_bytes(&b.output))
        || f32_bytes(&left.r11.logits) != f32_bytes(&right.r11.logits)
        || left.r11.top_k_ids != right.r11.top_k_ids
    {
        return Err(numerical("r12_determinism", "R12 repeat differs"));
    }
    Ok(())
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn f32_record(value: &Value) -> Vec<f32> {
    record_bytes(value)
        .chunks_exact(4)
        .map(|chunk| f32::from_le_bytes(chunk.try_into().unwrap()))
        .collect()
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn record_bytes(value: &Value) -> Vec<u8> {
    decode_hex(value["f32_le_hex"].as_str().unwrap())
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn decode_hex(value: &str) -> Vec<u8> {
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
        .collect()
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn usize_values(value: &Value) -> Vec<usize> {
    value
        .as_array()
        .unwrap()
        .iter()
        .map(|value| value.as_u64().unwrap() as usize)
        .collect()
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn f32_bytes(values: &[f32]) -> Vec<u8> {
    values
        .iter()
        .flat_map(|value| value.to_le_bytes())
        .collect()
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn adapter_error(message: String) -> RunnerError {
    lifecycle("r12_adapter", message)
}

fn infrastructure(code: &'static str, message: impl ToString) -> RunnerError {
    RunnerError::new(
        FailureClass::InfrastructureEvidence,
        code,
        message.to_string(),
    )
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn numerical(code: &'static str, message: impl ToString) -> RunnerError {
    RunnerError::new(FailureClass::NumericalBehavioral, code, message.to_string())
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn lifecycle(code: &'static str, message: impl ToString) -> RunnerError {
    RunnerError::new(FailureClass::LifecycleOwnership, code, message.to_string())
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn cancelled(code: &'static str, message: impl ToString) -> RunnerError {
    RunnerError::new(FailureClass::Cancelled, code, message.to_string())
}

#[cfg(not(all(target_os = "macos", pulsar_native_mlx)))]
fn run_tiny_model_fixture_impl(
    _manifest: &Path,
    _config: &Config,
    _evidence: &mut Evidence,
) -> Result<(), RunnerError> {
    Err(infrastructure(
        "native_mlx_unavailable",
        "R12 production fixture requires the production native MLX adapter",
    ))
}
