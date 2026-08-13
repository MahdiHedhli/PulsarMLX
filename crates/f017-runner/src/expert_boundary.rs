//! Canonical one-complete-expert M1-E boundary.

use crate::artifact_paths::{ArtifactReference, PrivatePackageRoot};
use crate::checkpoint::{CheckpointKind, CheckpointManifest};
use crate::cli::{Config, RunnerMode};
use crate::evidence::{
    ArtifactPathEvidence, Evidence, ExpertRepeatIntegrityEvidence, ExpertRepeatOutputEvidence,
    ExpertStageMetricsEvidence, OracleOrderingEvidence,
};
use crate::json::{parse_json_no_duplicates, sha256_bytes};
use crate::numerical_classification::{GreedyApplicability, NumericalClassification};
use crate::qualification::{
    exact_matvec_f32, exact_swiglu_f32, qualify_m1e_expert_tier_b, M1E_EXACT_SCAFFOLD_VERSION,
    M1E_TIER_B_CONTRACT_VERSION,
};
use crate::{FailureClass, RunnerError};
use serde::Deserialize;
use std::fs::{self, File};
use std::path::Path;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

const INPUT: usize = 6144;
const HIDDEN: usize = 2048;
const OUTPUT: usize = 6144;
const REPEATS: usize = 10;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Package {
    schema: String,
    schema_version: String,
    package_kind: String,
    checkpoint_set_sha256: String,
    catalog_sha256: String,
    tensor_map_sha256: String,
    #[serde(default)]
    source_checkpoint_read_count: u64,
    tensors: Vec<Tensor>,
    oracle: ArtifactReference,
    one_attempt: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Tensor {
    role: String,
    name: String,
    shard_ordinal: usize,
    offset: u64,
    packed_length: usize,
    quantization: String,
    matrix_shape: [usize; 2],
    packed_sha256: String,
    #[serde(default)]
    payload: Option<ArtifactReference>,
}

#[derive(Deserialize)]
struct Oracle {
    schema: String,
    schema_version: String,
    generator: OracleGenerator,
    matrices: OracleMatrices,
    activation: BytesArtifact,
    stages: OracleStages,
    bounds: OracleBounds,
    derived_global: DerivedGlobal,
    timings: OracleTimings,
    finalization: Finalization,
}
#[derive(Deserialize)]
struct OracleGenerator {
    source_sha256: String,
}
#[derive(Deserialize)]
struct OracleMatrices {
    gate: MatrixHash,
    up: MatrixHash,
    down: MatrixHash,
}
#[derive(Deserialize)]
struct MatrixHash {
    packed_sha256: String,
    decoded_sha256: String,
}
#[derive(Deserialize)]
struct BytesArtifact {
    sha256: String,
    bytes_hex: String,
    element_count: usize,
}
#[derive(Deserialize)]
struct OracleStages {
    gate: Stage,
    up: Stage,
    activated_hidden: Stage,
    final_output: Stage,
}
#[derive(Deserialize)]
struct Stage {
    sha256: String,
    bytes_hex: String,
}
#[derive(Deserialize)]
struct OracleBounds {
    gate: BoundStage,
    up: BoundStage,
    activated_hidden: BoundStage,
    final_output: BoundStage,
}
#[derive(Deserialize)]
struct BoundStage {
    sha256: String,
    f64_hex: String,
}
#[derive(Deserialize)]
struct DerivedGlobal {
    max_absolute_bound: f64,
    rmse_bound: f64,
    cosine_minimum: Option<f64>,
}
#[derive(Deserialize)]
struct OracleTimings {
    oracle_gate_seconds: f64,
    oracle_up_seconds: f64,
    oracle_activation_seconds: f64,
    oracle_down_seconds: f64,
}
#[derive(Deserialize)]
struct Finalization {
    preparation_started_at: String,
    oracle_completed_at: String,
    completion_marker: String,
    immutable_after_finalization: bool,
}

pub fn run(
    package_path: &Path,
    config: &Config,
    evidence: &mut Evidence,
) -> Result<(), RunnerError> {
    run_impl(package_path, config, evidence)
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn run_impl(
    package_path: &Path,
    config: &Config,
    evidence: &mut Evidence,
) -> Result<(), RunnerError> {
    use stream::{MlxContext, MlxDevice, MlxStreamMode};
    let binding = config
        .execution_config
        .as_ref()
        .ok_or_else(|| infra("m1e_execution_config", "missing immutable execution config"))?;
    let loaded = crate::m1e_execution_config::load(&binding.path, &binding.sha256, false)?;
    evidence.identity.prior_evidence = loaded.document.prior_evidence.clone();
    let mut artifacts = loaded
        .document
        .repository_artifacts
        .values()
        .chain(std::iter::once(&loaded.document.activation_fixture))
        .map(|artifact| ArtifactPathEvidence {
            path_kind: "repository_relative".into(),
            symbolic_path: artifact.symbolic_path.display().to_string(),
            content_sha256: artifact.content_sha256.clone(),
            logical_role: artifact.logical_role.clone(),
            repository_identity: Some(loaded.document.runtime_sha.clone()),
            package_artifact_id: None,
        })
        .collect::<Vec<_>>();
    artifacts.sort_by(|left, right| left.logical_role.cmp(&right.logical_role));
    evidence.identity.artifact_paths = artifacts;
    let package_bytes = fs::read(package_path).map_err(|e| infra("m1e_package_read", e))?;
    let package_hash = sha256_bytes(&package_bytes);
    let package: Package =
        parse_json_no_duplicates(&package_bytes).map_err(|e| infra("m1e_package_json", e))?;
    validate_package(&package, &config.mode)?;
    let package_root = PrivatePackageRoot::from_package(package_path)?;
    let oracle_resolved = package_root.resolve(&package.oracle)?;
    let oracle_path = oracle_resolved.canonical_path;
    let oracle: Oracle = parse_json_no_duplicates(&oracle_resolved.bytes)
        .map_err(|e| infra("m1e_oracle_json", e))?;
    let preparer_sha = &loaded
        .document
        .repository_artifacts
        .get("real_reference_preparer")
        .ok_or_else(|| infra("m1e_preparer_binding", "preparer binding missing"))?
        .content_sha256;
    validate_oracle(&oracle, &package, preparer_sha)?;
    for (role, bound, count) in [
        ("gate", &oracle.bounds.gate, HIDDEN),
        ("up", &oracle.bounds.up, HIDDEN),
        ("activated_hidden", &oracle.bounds.activated_hidden, HIDDEN),
        ("final_output", &oracle.bounds.final_output, OUTPUT),
    ] {
        validate_bound_stage(bound, count, role)?;
        evidence
            .execution
            .numerical
            .expert_bound_sha256
            .insert(role.into(), bound.sha256.clone());
    }

    let manifest_path = config
        .checkpoint_manifest
        .as_ref()
        .ok_or_else(|| infra("m1e_manifest", "missing checkpoint manifest"))?;
    let manifest = CheckpointManifest::load(manifest_path)?;
    let expected_kind = if matches!(config.mode, RunnerMode::RealExpert { .. }) {
        CheckpointKind::Production
    } else {
        CheckpointKind::Fixture
    };
    if manifest.kind != expected_kind
        || manifest.checkpoint_set_sha256 != package.checkpoint_set_sha256
        || manifest.catalog_sha256 != package.catalog_sha256
    {
        return Err(infra(
            "m1e_checkpoint_binding",
            "checkpoint identity mismatch",
        ));
    }
    let shard = manifest
        .shards
        .get(1)
        .ok_or_else(|| infra("m1e_shard", "shard 2 missing"))?;
    let shard_path = manifest_path
        .parent()
        .unwrap_or(Path::new("."))
        .join(&shard.filename);
    // This is the one-way attempt-consumption boundary. All immutable-config,
    // admission, package, oracle, and checkpoint metadata checks have passed;
    // no tensor payload has been read yet.
    evidence.execution.attempt_state = "execution_started".into();
    evidence.execution.attempt_consumed = true;
    evidence.identity.checkpoint.accessed = true;
    evidence.identity.checkpoint.checkpoint_set_sha256 =
        Some(manifest.checkpoint_set_sha256.clone());
    evidence.identity.checkpoint.catalog_sha256 = Some(manifest.catalog_sha256.clone());

    let storage_started = Instant::now();
    let gate_packed = read_tensor(&package_root, &shard_path, tensor(&package, "gate")?)?;
    let up_packed = read_tensor(&package_root, &shard_path, tensor(&package, "up")?)?;
    let down_packed = read_tensor(&package_root, &shard_path, tensor(&package, "down")?)?;
    evidence.execution.storage.read_count = if matches!(config.mode, RunnerMode::RealExpert { .. })
    {
        package.source_checkpoint_read_count
    } else {
        3
    };
    evidence.execution.storage.read_bytes =
        (gate_packed.len() + up_packed.len() + down_packed.len()) as u64;
    evidence.execution.timings.insert(
        "storage_seconds".into(),
        storage_started.elapsed().as_secs_f64(),
    );

    require_hash(
        &gate_packed,
        &oracle.matrices.gate.packed_sha256,
        "m1e_gate_packed",
    )?;
    require_hash(
        &up_packed,
        &oracle.matrices.up.packed_sha256,
        "m1e_up_packed",
    )?;
    require_hash(
        &down_packed,
        &oracle.matrices.down.packed_sha256,
        "m1e_down_packed",
    )?;
    for (role, value) in [
        ("gate", &oracle.matrices.gate.packed_sha256),
        ("up", &oracle.matrices.up.packed_sha256),
        ("down", &oracle.matrices.down.packed_sha256),
    ] {
        evidence
            .execution
            .numerical
            .expert_payload_sha256
            .insert(role.into(), value.clone());
    }
    let mut gate_matrix = vec![0.0_f32; HIDDEN * INPUT];
    let mut up_matrix = vec![0.0_f32; HIDDEN * INPUT];
    let mut down_matrix = vec![0.0_f32; OUTPUT * HIDDEN];
    let decode_gate_started = Instant::now();
    quant::decode_iq2_xxs_matrix(&gate_packed, HIDDEN, INPUT, &mut gate_matrix)
        .map_err(|e| numerical("m1e_gate_decode", format!("{e:?}")))?;
    evidence.execution.timings.insert(
        "decoder_gate_seconds".into(),
        decode_gate_started.elapsed().as_secs_f64(),
    );
    let decode_up_started = Instant::now();
    quant::decode_iq2_xxs_matrix(&up_packed, HIDDEN, INPUT, &mut up_matrix)
        .map_err(|e| numerical("m1e_up_decode", format!("{e:?}")))?;
    evidence.execution.timings.insert(
        "decoder_up_seconds".into(),
        decode_up_started.elapsed().as_secs_f64(),
    );
    let decode_down_started = Instant::now();
    quant::decode_iq3_xxs_matrix(&down_packed, OUTPUT, HIDDEN, &mut down_matrix)
        .map_err(|e| numerical("m1e_down_decode", format!("{e:?}")))?;
    evidence.execution.timings.insert(
        "decoder_down_seconds".into(),
        decode_down_started.elapsed().as_secs_f64(),
    );
    require_hash(
        &f32_bytes(&gate_matrix),
        &oracle.matrices.gate.decoded_sha256,
        "m1e_gate_decoded",
    )?;
    require_hash(
        &f32_bytes(&up_matrix),
        &oracle.matrices.up.decoded_sha256,
        "m1e_up_decoded",
    )?;
    require_hash(
        &f32_bytes(&down_matrix),
        &oracle.matrices.down.decoded_sha256,
        "m1e_down_decoded",
    )?;
    for (role, value) in [
        ("gate", &oracle.matrices.gate.decoded_sha256),
        ("up", &oracle.matrices.up.decoded_sha256),
        ("down", &oracle.matrices.down.decoded_sha256),
    ] {
        evidence
            .execution
            .numerical
            .expert_decoded_sha256
            .insert(role.into(), value.clone());
    }
    for (name, value) in [
        ("oracle_gate_seconds", oracle.timings.oracle_gate_seconds),
        ("oracle_up_seconds", oracle.timings.oracle_up_seconds),
        (
            "oracle_activation_seconds",
            oracle.timings.oracle_activation_seconds,
        ),
        ("oracle_down_seconds", oracle.timings.oracle_down_seconds),
    ] {
        evidence.execution.timings.insert(name.into(), value);
    }

    let activation = stage_values(
        &oracle.activation.bytes_hex,
        oracle.activation.element_count,
        &oracle.activation.sha256,
        "m1e_activation",
    )?;
    let reference_gate = stage_values(
        &oracle.stages.gate.bytes_hex,
        HIDDEN,
        &oracle.stages.gate.sha256,
        "m1e_reference_gate",
    )?;
    let reference_up = stage_values(
        &oracle.stages.up.bytes_hex,
        HIDDEN,
        &oracle.stages.up.sha256,
        "m1e_reference_up",
    )?;
    let reference_hidden = stage_values(
        &oracle.stages.activated_hidden.bytes_hex,
        HIDDEN,
        &oracle.stages.activated_hidden.sha256,
        "m1e_reference_hidden",
    )?;
    let reference_output = stage_values(
        &oracle.stages.final_output.bytes_hex,
        OUTPUT,
        &oracle.stages.final_output.sha256,
        "m1e_reference_output",
    )?;
    for (role, value) in [
        ("gate", &oracle.stages.gate.sha256),
        ("up", &oracle.stages.up.sha256),
        ("activated_hidden", &oracle.stages.activated_hidden.sha256),
        ("final_output", &oracle.stages.final_output.sha256),
    ] {
        evidence
            .execution
            .numerical
            .expert_reference_sha256
            .insert(role.into(), value.clone());
    }

    // Qualification scaffold is completed before candidate start and is never
    // callable as a production fallback.
    let mut scaffold_gate = vec![0.0; HIDDEN];
    let mut scaffold_up = vec![0.0; HIDDEN];
    let mut scaffold_hidden = vec![0.0; HIDDEN];
    let mut scaffold_output = vec![0.0; OUTPUT];
    exact_matvec_f32(&gate_matrix, HIDDEN, INPUT, &activation, &mut scaffold_gate)
        .map_err(|e| numerical("m1e_scaffold_gate", e))?;
    exact_matvec_f32(&up_matrix, HIDDEN, INPUT, &activation, &mut scaffold_up)
        .map_err(|e| numerical("m1e_scaffold_up", e))?;
    exact_swiglu_f32(&scaffold_gate, &scaffold_up, &mut scaffold_hidden)
        .map_err(|e| numerical("m1e_scaffold_activation", e))?;
    exact_matvec_f32(
        &down_matrix,
        OUTPUT,
        HIDDEN,
        &scaffold_hidden,
        &mut scaffold_output,
    )
    .map_err(|e| numerical("m1e_scaffold_down", e))?;
    for (actual, expected, code) in [
        (&scaffold_gate, &reference_gate, "m1e_scaffold_gate_parity"),
        (&scaffold_up, &reference_up, "m1e_scaffold_up_parity"),
        (
            &scaffold_hidden,
            &reference_hidden,
            "m1e_scaffold_hidden_parity",
        ),
        (
            &scaffold_output,
            &reference_output,
            "m1e_scaffold_output_parity",
        ),
    ] {
        if f32_bytes(actual) != f32_bytes(expected) {
            return Err(numerical(code, "independent oracle/scaffold mismatch"));
        }
    }

    require_unchanged(package_path, &package_hash, "m1e_package_mutated")?;
    require_unchanged(
        &oracle_path,
        &package.oracle.content_sha256,
        "m1e_oracle_mutated",
    )?;
    let completed = oracle
        .finalization
        .oracle_completed_at
        .parse::<u128>()
        .map_err(|_| infra("m1e_oracle_time", "invalid oracle completion marker"))?;
    let candidate_started = now_ns()?;
    if completed >= candidate_started {
        return Err(infra(
            "m1e_oracle_order",
            "oracle did not complete before candidate",
        ));
    }
    evidence.execution.numerical.oracle_ordering = OracleOrderingEvidence {
        oracle_package_sha256: Some(package.oracle.content_sha256.clone()),
        oracle_completed_at: Some(oracle.finalization.oracle_completed_at.clone()),
        oracle_completion_marker: Some("oracle_finalized_sequence_0".into()),
        oracle_validated_before_candidate: true,
        candidate_started_at: Some(candidate_started.to_string()),
        candidate_start_marker: Some("candidate_started_sequence_1".into()),
        structural_order_valid: true,
    };

    let streams_before = MlxContext::debug_stream_counters().map_err(backend)?;
    if MlxContext::debug_context_active() {
        return Err(lifecycle("m1e_singleton", "singleton already active"));
    }
    evidence.admission.singleton_initially_unclaimed = true;
    let context = MlxContext::new(
        MlxDevice::Gpu,
        match config.stream_mode {
            crate::cli::StreamMode::DefaultGpu => MlxStreamMode::BorrowedDefault,
            crate::cli::StreamMode::OwnedDevice => MlxStreamMode::Owned,
        },
    )
    .map_err(backend)?;
    let gate_qualification = gate_matrix.clone();
    let up_qualification = up_matrix.clone();
    let down_qualification = down_matrix.clone();
    let mut activation_owned = activation.clone();
    let import_started = Instant::now();
    let gate_array = context
        .import_f32_shaped(&mut gate_matrix, &[HIDDEN, INPUT])
        .map_err(backend)?;
    let up_array = context
        .import_f32_shaped(&mut up_matrix, &[HIDDEN, INPUT])
        .map_err(backend)?;
    let down_array = context
        .import_f32_shaped(&mut down_matrix, &[OUTPUT, HIDDEN])
        .map_err(backend)?;
    let activation_array = context
        .import_f32_shaped(&mut activation_owned, &[INPUT])
        .map_err(backend)?;
    evidence.execution.timings.insert(
        "production_import_seconds".into(),
        import_started.elapsed().as_secs_f64(),
    );
    let production_started = Instant::now();
    let mut gate_seconds = 0.0;
    let mut up_seconds = 0.0;
    let mut activation_seconds = 0.0;
    let mut down_seconds = 0.0;
    let mut repeats = Vec::with_capacity(REPEATS);
    let mut last = (Vec::new(), Vec::new(), Vec::new(), Vec::new());
    for ordinal in 0..REPEATS {
        let gate_started = Instant::now();
        let gate_result = gate_array.matvec(&activation_array).map_err(backend)?;
        gate_result.evaluate_sync().map_err(backend)?;
        let mut gate = vec![0.0; HIDDEN];
        gate_result.copy_f32(&mut gate).map_err(backend)?;
        gate_result.destroy().map_err(backend)?;
        gate_seconds += gate_started.elapsed().as_secs_f64();
        let up_started = Instant::now();
        let up_result = up_array.matvec(&activation_array).map_err(backend)?;
        up_result.evaluate_sync().map_err(backend)?;
        let mut up = vec![0.0; HIDDEN];
        up_result.copy_f32(&mut up).map_err(backend)?;
        up_result.destroy().map_err(backend)?;
        up_seconds += up_started.elapsed().as_secs_f64();
        let activation_started = Instant::now();
        let mut hidden = vec![0.0; HIDDEN];
        exact_swiglu_f32(&gate, &up, &mut hidden).map_err(|e| numerical("m1e_activation", e))?;
        activation_seconds += activation_started.elapsed().as_secs_f64();
        let mut hidden_owned = hidden.clone();
        let hidden_array = context
            .import_f32_shaped(&mut hidden_owned, &[HIDDEN])
            .map_err(backend)?;
        let down_started = Instant::now();
        let output_result = down_array.matvec(&hidden_array).map_err(backend)?;
        output_result.evaluate_sync().map_err(backend)?;
        let mut output = vec![0.0; OUTPUT];
        output_result.copy_f32(&mut output).map_err(backend)?;
        output_result.destroy().map_err(backend)?;
        hidden_array.destroy().map_err(backend)?;
        down_seconds += down_started.elapsed().as_secs_f64();
        if fixture_divergence_repeat(&package)? == Some(ordinal) {
            gate[0] = f32::from_bits(gate[0].to_bits() ^ 1);
        }
        repeats.push(ExpertRepeatOutputEvidence {
            ordinal: ordinal as u64,
            gate_sha256: sha256_bytes(&f32_bytes(&gate)),
            up_sha256: sha256_bytes(&f32_bytes(&up)),
            activated_hidden_sha256: sha256_bytes(&f32_bytes(&hidden)),
            final_output_sha256: sha256_bytes(&f32_bytes(&output)),
        });
        last = (gate, up, hidden, output);
    }
    evidence.execution.timings.insert(
        "production_gate_compute_sync_readback_seconds".into(),
        gate_seconds,
    );
    evidence.execution.timings.insert(
        "production_up_compute_sync_readback_seconds".into(),
        up_seconds,
    );
    evidence.execution.timings.insert(
        "production_activation_orchestration_seconds".into(),
        activation_seconds,
    );
    evidence.execution.timings.insert(
        "production_down_compute_sync_readback_seconds".into(),
        down_seconds,
    );
    evidence.execution.timings.insert(
        "total_wall_seconds".into(),
        production_started.elapsed().as_secs_f64(),
    );
    let teardown_started = Instant::now();
    activation_array.destroy().map_err(backend)?;
    gate_array.destroy().map_err(backend)?;
    up_array.destroy().map_err(backend)?;
    down_array.destroy().map_err(backend)?;
    let ownership = context.ownership_snapshot().map_err(backend)?;
    context.synchronize().map_err(backend)?;
    drop(context);
    evidence.execution.timings.insert(
        "teardown_seconds".into(),
        teardown_started.elapsed().as_secs_f64(),
    );
    let streams_after = MlxContext::debug_stream_counters().map_err(backend)?;
    evidence.lifecycle.post.managed_created = ownership.managed_created;
    evidence.lifecycle.post.managed_destroyed = ownership.managed_destroyed;
    evidence.lifecycle.post.derived_created = ownership.derived_created;
    evidence.lifecycle.post.derived_destroyed = ownership.derived_destroyed;
    evidence.lifecycle.post.callback_count = ownership.callback_count;
    evidence.lifecycle.post.owned_stream_created = streams_after.owned_created;
    evidence.lifecycle.post.owned_stream_freed = streams_after.owned_freed;
    evidence.lifecycle.post.default_cpu_stream_created = streams_after.default_cpu_created;
    evidence.lifecycle.post.default_cpu_stream_freed = streams_after.default_cpu_freed;
    evidence.lifecycle.post.default_gpu_stream_created = streams_after.default_gpu_created;
    evidence.lifecycle.post.default_gpu_stream_freed = streams_after.default_gpu_freed;
    evidence.lifecycle.post.singleton_claimed = MlxContext::debug_context_active();
    evidence.lifecycle.reconciled = ownership.managed_created == ownership.managed_destroyed
        && ownership.derived_created == ownership.derived_destroyed
        && ownership.callback_count == ownership.managed_created
        && streams_after.owned_created - streams_before.owned_created
            == streams_after.owned_freed - streams_before.owned_freed
        && !evidence.lifecycle.post.singleton_claimed;
    if !evidence.lifecycle.reconciled {
        return Err(lifecycle(
            "m1e_lifecycle",
            "expert lifecycle did not reconcile",
        ));
    }

    let equal = |select: fn(&ExpertRepeatOutputEvidence) -> &str| {
        repeats
            .iter()
            .all(|entry| select(entry) == select(&repeats[0]))
    };
    evidence.execution.numerical.expert_repeat_integrity = ExpertRepeatIntegrityEvidence {
        repeat_count_required: 10,
        repeat_count_observed: 10,
        native_dispatch_count_expected: 30,
        conceptual_expert_count: 1,
        gate_all_equal: equal(|v| &v.gate_sha256),
        up_all_equal: equal(|v| &v.up_sha256),
        activated_hidden_all_equal: equal(|v| &v.activated_hidden_sha256),
        final_output_all_equal: equal(|v| &v.final_output_sha256),
        outputs: repeats,
    };
    if !evidence
        .execution
        .numerical
        .expert_repeat_integrity
        .gate_all_equal
        || !evidence
            .execution
            .numerical
            .expert_repeat_integrity
            .up_all_equal
        || !evidence
            .execution
            .numerical
            .expert_repeat_integrity
            .activated_hidden_all_equal
        || !evidence
            .execution
            .numerical
            .expert_repeat_integrity
            .final_output_all_equal
    {
        return Err(numerical(
            "m1e_repeat_divergence",
            "expert repeat stage hashes diverged",
        ));
    }
    let qualification = qualify_m1e_expert_tier_b(
        &gate_qualification,
        &up_qualification,
        &down_qualification,
        &activation,
        &reference_gate,
        &last.0,
        &reference_up,
        &last.1,
        &reference_hidden,
        &last.2,
        &reference_output,
        &last.3,
    )
    .map_err(|e| numerical("m1e_tier_b", e))?;
    if !qualification.passes {
        return Err(numerical(
            "m1e_tier_b_failed",
            "complete expert violates frozen Tier-B composition",
        ));
    }
    let stage = |metrics: &crate::qualification::NumericalMetrics, passed: bool| {
        ExpertStageMetricsEvidence {
            bit_mismatch_count: metrics.bit_mismatch_count as u64,
            signed_zero_mismatch_count: metrics.signed_zero_mismatch_count as u64,
            max_abs_error: metrics.max_abs_error,
            rmse: metrics.rmse,
            cosine_similarity: metrics.cosine_similarity,
            passed,
        }
    };
    for (role, metrics) in [
        (
            "gate",
            stage(&qualification.gate.metrics, qualification.gate.passes),
        ),
        (
            "up",
            stage(&qualification.up.metrics, qualification.up.passes),
        ),
        (
            "activated_hidden",
            stage(&qualification.activated_hidden, qualification.passes),
        ),
        (
            "final_output",
            stage(&qualification.final_output, qualification.passes),
        ),
    ] {
        evidence
            .execution
            .numerical
            .expert_stage_metrics
            .insert(role.into(), metrics);
    }
    require_unchanged(package_path, &package_hash, "m1e_package_mutated")?;
    require_unchanged(
        &oracle_path,
        &package.oracle.content_sha256,
        "m1e_oracle_mutated",
    )?;
    evidence.execution.dispatch.native = 30;
    evidence.execution.projection_count = 3;
    evidence.execution.quant_decode_count = 3;
    evidence.execution.expert_execution_count = 1;
    evidence.execution.numerical_classification =
        Some(NumericalClassification::NumericallyQualifiedGreedyNotApplicable);
    evidence.execution.numerical.greedy_applicability = Some(GreedyApplicability::NotApplicable);
    evidence.execution.numerical.scaffold_version = Some(M1E_EXACT_SCAFFOLD_VERSION.into());
    evidence.execution.numerical.frozen_contract_version = Some(M1E_TIER_B_CONTRACT_VERSION.into());
    evidence.execution.numerical.max_abs_error = Some(qualification.final_output.max_abs_error);
    evidence.execution.numerical.rmse = Some(qualification.final_output.rmse);
    evidence.execution.numerical.cosine_similarity = qualification.final_output.cosine_similarity;
    evidence.execution.numerical.deterministic_repeat_count = Some(10);
    evidence.execution.progress_state = "m1e_one_expert_complete".into();
    Ok(())
}

#[cfg(not(all(target_os = "macos", pulsar_native_mlx)))]
fn run_impl(
    _package_path: &Path,
    _config: &Config,
    _evidence: &mut Evidence,
) -> Result<(), RunnerError> {
    Err(infra("native_mlx_unavailable", "M1-E requires native MLX"))
}

fn validate_package(package: &Package, mode: &RunnerMode) -> Result<(), RunnerError> {
    let kind = if matches!(mode, RunnerMode::RealExpert { .. }) {
        "production_reviewed"
    } else {
        "checkpoint_free_fixture"
    };
    if package.schema != "pulsarmlx.f017.m1e-package"
        || package.schema_version != "1.0.0"
        || package.package_kind != kind
        || !package.one_attempt
        || matches!(mode, RunnerMode::RealExpert { .. })
            && package.source_checkpoint_read_count != 3
        || package.tensor_map_sha256
            != "ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223"
        || package.tensors.len() != 3
    {
        return Err(infra(
            "m1e_package_contract",
            "M1-E package contract mismatch",
        ));
    }
    for (role, name, quant, offset, length, shape) in [
        (
            "gate",
            "blk.3.ffn_gate_exps.weight",
            "IQ2_XXS",
            3_423_197_024,
            3_244_032,
            [HIDDEN, INPUT],
        ),
        (
            "up",
            "blk.3.ffn_up_exps.weight",
            "IQ2_XXS",
            4_268_636_000,
            3_244_032,
            [HIDDEN, INPUT],
        ),
        (
            "down",
            "blk.3.ffn_down_exps.weight",
            "IQ3_XXS",
            2_203_342_688,
            4_816_896,
            [OUTPUT, HIDDEN],
        ),
    ] {
        let t = tensor(package, role)?;
        if t.name != name
            || t.quantization != quant
            || t.shard_ordinal != 2
            || t.offset != offset
            || t.packed_length != length
            || t.matrix_shape != shape
            || matches!(mode, RunnerMode::RealExpert { .. }) && t.payload.is_none()
        {
            return Err(infra(
                "m1e_tensor_contract",
                format!("{role} tensor mismatch"),
            ));
        }
    }
    Ok(())
}
fn validate_oracle(
    oracle: &Oracle,
    package: &Package,
    expected_preparer_sha: &str,
) -> Result<(), RunnerError> {
    let started = oracle
        .finalization
        .preparation_started_at
        .parse::<u128>()
        .ok();
    let completed = oracle.finalization.oracle_completed_at.parse::<u128>().ok();
    if oracle.schema != "pulsarmlx.f017.m1e-oracle-package"
        || oracle.schema_version != "1.0.0"
        || oracle.generator.source_sha256 != expected_preparer_sha
        || oracle.activation.element_count != INPUT
        || oracle.stages.gate.bytes_hex.len() != HIDDEN * 8
        || oracle.stages.up.bytes_hex.len() != HIDDEN * 8
        || oracle.stages.activated_hidden.bytes_hex.len() != HIDDEN * 8
        || oracle.stages.final_output.bytes_hex.len() != OUTPUT * 8
        || !oracle.derived_global.max_absolute_bound.is_finite()
        || oracle.derived_global.max_absolute_bound < 0.0
        || !oracle.derived_global.rmse_bound.is_finite()
        || oracle.derived_global.rmse_bound < 0.0
        || oracle
            .derived_global
            .cosine_minimum
            .is_some_and(|value| !value.is_finite() || !(0.0..=1.0).contains(&value))
        || oracle.finalization.completion_marker != "m1e_oracle_finalized_sequence_0"
        || !oracle.finalization.immutable_after_finalization
        || !matches!((started,completed),(Some(a),Some(b)) if a < b)
        || oracle.matrices.gate.packed_sha256 != tensor(package, "gate")?.packed_sha256
        || oracle.matrices.up.packed_sha256 != tensor(package, "up")?.packed_sha256
        || oracle.matrices.down.packed_sha256 != tensor(package, "down")?.packed_sha256
        || [
            oracle.timings.oracle_gate_seconds,
            oracle.timings.oracle_up_seconds,
            oracle.timings.oracle_activation_seconds,
            oracle.timings.oracle_down_seconds,
        ]
        .iter()
        .any(|value| !value.is_finite() || *value < 0.0)
    {
        return Err(infra(
            "m1e_oracle_contract",
            "M1-E oracle contract mismatch",
        ));
    }
    Ok(())
}
fn validate_bound_stage(
    stage: &BoundStage,
    expected_count: usize,
    role: &str,
) -> Result<(), RunnerError> {
    let bytes = decode_hex(&stage.f64_hex)?;
    if bytes.len() != expected_count * 8 || sha256_bytes(&bytes) != stage.sha256 {
        return Err(infra(
            "m1e_oracle_bound_hash",
            format!("{role} oracle bound vector identity mismatch"),
        ));
    }
    if bytes.chunks_exact(8).any(|chunk| {
        let value = f64::from_le_bytes(chunk.try_into().unwrap());
        !value.is_finite() || value < 0.0
    }) {
        return Err(infra(
            "m1e_oracle_bound_value",
            format!("{role} oracle bound vector contains an invalid value"),
        ));
    }
    Ok(())
}
fn fixture_divergence_repeat(package: &Package) -> Result<Option<usize>, RunnerError> {
    let value = std::env::var("PULSAR_F017_TEST_DIVERGE_M1E_REPEAT").ok();
    if value.is_some() && package.package_kind != "checkpoint_free_fixture" {
        return Err(infra(
            "m1e_test_injection",
            "fixture injection is forbidden in production",
        ));
    }
    value
        .map(|v| {
            v.parse::<usize>()
                .ok()
                .filter(|v| *v < REPEATS)
                .ok_or_else(|| infra("m1e_test_injection", "invalid repeat ordinal"))
        })
        .transpose()
}
fn tensor<'a>(package: &'a Package, role: &str) -> Result<&'a Tensor, RunnerError> {
    package
        .tensors
        .iter()
        .find(|t| t.role == role)
        .ok_or_else(|| infra("m1e_tensor", format!("missing {role}")))
}
fn read_tensor(
    package_root: &PrivatePackageRoot,
    path: &Path,
    tensor: &Tensor,
) -> Result<Vec<u8>, RunnerError> {
    if let Some(payload) = &tensor.payload {
        let resolved = package_root.resolve(payload)?;
        if resolved.bytes.len() != tensor.packed_length {
            return Err(infra(
                "m1e_short_read",
                "private bounded payload length mismatch",
            ));
        }
        require_hash(&resolved.bytes, &tensor.packed_sha256, "m1e_packed_hash")?;
        return Ok(resolved.bytes);
    }
    use std::os::unix::fs::FileExt;
    let file = File::open(path).map_err(|e| infra("m1e_shard_open", e))?;
    let mut b = vec![0; tensor.packed_length];
    file.read_exact_at(&mut b, tensor.offset)
        .map_err(|e| infra("m1e_short_read", e))?;
    require_hash(&b, &tensor.packed_sha256, "m1e_packed_hash")?;
    Ok(b)
}
fn stage_values(
    hex: &str,
    count: usize,
    hash: &str,
    code: &'static str,
) -> Result<Vec<f32>, RunnerError> {
    let b = decode_hex(hex)?;
    if b.len() != count * 4 {
        return Err(infra(code, "stage shape mismatch"));
    }
    require_hash(&b, hash, code)?;
    Ok(b.chunks_exact(4)
        .map(|v| f32::from_le_bytes(v.try_into().unwrap()))
        .collect())
}
fn decode_hex(value: &str) -> Result<Vec<u8>, RunnerError> {
    if !value.len().is_multiple_of(2) {
        return Err(infra("m1e_hex", "odd hex"));
    }
    (0..value.len())
        .step_by(2)
        .map(|i| {
            u8::from_str_radix(&value[i..i + 2], 16).map_err(|_| infra("m1e_hex", "invalid hex"))
        })
        .collect()
}
fn f32_bytes(v: &[f32]) -> Vec<u8> {
    v.iter().flat_map(|v| v.to_le_bytes()).collect()
}
fn require_hash(bytes: &[u8], expected: &str, code: &'static str) -> Result<(), RunnerError> {
    if expected.len() != 64 || sha256_bytes(bytes) != expected {
        Err(infra(code, "SHA-256 mismatch"))
    } else {
        Ok(())
    }
}
fn require_unchanged(path: &Path, hash: &str, code: &'static str) -> Result<(), RunnerError> {
    require_hash(&fs::read(path).map_err(|e| infra(code, e))?, hash, code)
}
fn now_ns() -> Result<u128, RunnerError> {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|v| v.as_nanos())
        .map_err(|e| infra("m1e_clock", e))
}
fn infra(code: &'static str, e: impl std::fmt::Display) -> RunnerError {
    RunnerError::new(FailureClass::InfrastructureEvidence, code, e.to_string())
}
fn numerical(code: &'static str, e: impl std::fmt::Display) -> RunnerError {
    RunnerError::new(FailureClass::NumericalBehavioral, code, e.to_string())
}
fn lifecycle(code: &'static str, e: impl std::fmt::Display) -> RunnerError {
    RunnerError::new(FailureClass::LifecycleOwnership, code, e.to_string())
}
fn backend(e: String) -> RunnerError {
    infra("m1e_backend", e)
}
