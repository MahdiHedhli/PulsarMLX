#![cfg(all(target_os = "macos", pulsar_native_mlx))]

use f017_runner::json::{parse_json_no_duplicates, sha256_bytes, sha256_file};
use f017_runner::layer_qualification::{
    run_r10_exact, run_r10_with_matvec, run_r9_exact, run_r9_with_matvec, ExpertMatrices,
    R10Inputs, R10Matrices, R10Output, R9Error, R9Inputs, R9Matrices, R9Output,
    R10_SCAFFOLD_VERSION, R9_SCAFFOLD_VERSION,
};
use f017_runner::numerical_classification::{GreedyApplicability, NumericalClassification};
use f017_runner::qualification::{
    exact_matvec_f32, measure_f32, qualify_tier_b_down, NumericalMetrics, TierBQualification,
};
use serde::Serialize;
use serde_json::Value;
use std::collections::BTreeMap;
use std::fs;
use std::path::Path;
use std::process::Command;
use std::time::Instant;
use stream::{MlxContext, MlxDevice, MlxStreamMode};

const REPEATS: usize = 10;

#[derive(Serialize)]
struct Report {
    schema: &'static str,
    schema_version: &'static str,
    source_commit: String,
    fixture_version: String,
    fixture_sha256: String,
    r9_fixture_sha256: String,
    oracle_generator_sha: String,
    exact_scaffold_versions: [&'static str; 2],
    frozen_contract_versions: [String; 3],
    production_backend_version: &'static str,
    numerical_mode: &'static str,
    deterministic_repeat_count: usize,
    selected_ids: Vec<usize>,
    routing_weights: F64Metrics,
    r9_output: NumericalMetrics,
    r10_f32_boundaries: BTreeMap<String, NumericalMetrics>,
    r10_f64_boundaries: BTreeMap<String, F64Metrics>,
    first_repeat_matvec_qualifications: Vec<MatvecReport>,
    classification: NumericalClassification,
    greedy_applicability: GreedyApplicability,
    direct_native_dispatch_count: u64,
    qualification_scaffold_dispatch_count: u64,
    explicit_reference_dispatch_count: u64,
    unexpected_fallback_count: u64,
    backend_error_count: u64,
    timings: Timings,
    lifecycle: Lifecycle,
    review_status: &'static str,
    checkpoint_accessed: bool,
}

#[derive(Serialize)]
struct MatvecReport {
    role: String,
    qualification: TierBQualification,
}

#[derive(Serialize)]
struct F64Metrics {
    element_count: usize,
    bit_mismatch_count: usize,
    non_finite_count: usize,
    max_abs_error: f64,
    rmse: f64,
    cosine_similarity: Option<f64>,
    first_divergence_index: Option<usize>,
}

#[derive(Default, Serialize)]
struct Timings {
    exact_complete_layer_seconds: f64,
    production_total_seconds: f64,
    attention_mla_seconds: f64,
    moe_branch_seconds: f64,
    import_seconds: f64,
    compute_sync_seconds: f64,
    router_projection_seconds: f64,
    routed_expert_projection_seconds: f64,
    shared_expert_projection_seconds: f64,
    cpu_norm_activation_routing_aggregation_residual_seconds: f64,
    per_role: BTreeMap<String, RoleTiming>,
}

#[derive(Default, Serialize)]
struct RoleTiming {
    dispatch_count: u64,
    import_seconds: f64,
    compute_sync_seconds: f64,
}

#[derive(Serialize)]
struct Lifecycle {
    managed_created: u64,
    managed_destroyed: u64,
    derived_created: u64,
    derived_destroyed: u64,
    callback_count: u64,
    owned_stream_created_delta: u64,
    owned_stream_freed_delta: u64,
    context_active_after: bool,
    in_flight_after_teardown: u64,
    stale_generation_count: u64,
    reconciled: bool,
}

#[test]
fn checkpoint_free_r10_complete_layer_qualifies_without_fallback() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let r9_bytes =
        fs::read(root.join(
            "specs/017-rust-native-inference-runtime/fixtures/f017-r9-mla-dsa-oracle-v1.json",
        ))
        .unwrap();
    let r10_bytes = fs::read(root.join(
        "specs/017-rust-native-inference-runtime/fixtures/f017-r10-complete-layer-oracle-v1.json",
    ))
    .unwrap();
    let r9_contract_bytes = fs::read(
        root.join("specs/017-rust-native-inference-runtime/contracts/production-r9-tier-b-v2.json"),
    )
    .unwrap();
    let r10_contract_bytes =
        fs::read(root.join(
            "specs/017-rust-native-inference-runtime/contracts/production-r10-tier-b-v2.json",
        ))
        .unwrap();
    let r9: Value = parse_json_no_duplicates(&r9_bytes).unwrap();
    let r10: Value = parse_json_no_duplicates(&r10_bytes).unwrap();
    let r9_contract: Value = parse_json_no_duplicates(&r9_contract_bytes).unwrap();
    let r10_contract: Value = parse_json_no_duplicates(&r10_contract_bytes).unwrap();
    assert_eq!(
        r10_contract["status"],
        "reviewed_semantic_tightening_of_frozen_v1"
    );
    assert_eq!(r10_contract["required_repeats"], REPEATS);
    assert_eq!(sha256_bytes(&r9_bytes), r10["r9_fixture_sha256"]);
    assert_eq!(
        sha256_file(&root.join(r10["generator_path"].as_str().unwrap())).unwrap(),
        r10["generator_sha256"]
    );
    assert_eq!(r10["checkpoint_accessed"], false);

    let r9_matrices = r9_matrices(&r9);
    let r9_inputs = r9_inputs(&r9);
    let r10_matrices = r10_matrices(&r10);
    let mut r10_inputs = r10_inputs(&r10);
    let exact_started = Instant::now();
    let exact_r9 = run_r9_exact(&r9_matrices, &r9_inputs).unwrap();
    assert_bits(
        &exact_r9.output,
        &r10_inputs.attention_residual,
        "R9/R10 composition",
    );
    r10_inputs.attention_residual = exact_r9.output.clone();
    let exact_r10 = run_r10_exact(&r10_matrices, &r10_inputs).unwrap();
    assert_r10_fixture(&r10, &exact_r10);
    let exact_seconds = exact_started.elapsed().as_secs_f64();

    let streams_before = MlxContext::debug_stream_counters().unwrap();
    assert!(!MlxContext::debug_context_active());
    let context = MlxContext::new(MlxDevice::Gpu, MlxStreamMode::Owned).unwrap();
    let mut timings = Timings {
        exact_complete_layer_seconds: exact_seconds,
        ..Timings::default()
    };
    let mut first: Option<(R9Output, R10Output)> = None;
    let mut first_reports = Vec::new();
    let production_started = Instant::now();
    for repeat in 0..REPEATS {
        let mut reports = Vec::new();
        let attention_started = Instant::now();
        let candidate_r9 = run_r9_with_matvec(
            &r9_matrices,
            &r9_inputs,
            |matrix, rows, columns, vector, role| {
                qualified_production_matvec(
                    &context,
                    matrix,
                    rows,
                    columns,
                    vector,
                    role,
                    &mut timings,
                    &mut reports,
                )
            },
        )
        .unwrap();
        timings.attention_mla_seconds += attention_started.elapsed().as_secs_f64();
        let mut candidate_inputs = r10_inputs.clone();
        candidate_inputs.attention_residual = candidate_r9.output.clone();
        let moe_started = Instant::now();
        let candidate_r10 = run_r10_with_matvec(
            &r10_matrices,
            &candidate_inputs,
            |matrix, rows, columns, vector, role| {
                qualified_production_matvec(
                    &context,
                    matrix,
                    rows,
                    columns,
                    vector,
                    role,
                    &mut timings,
                    &mut reports,
                )
            },
        )
        .unwrap();
        timings.moe_branch_seconds += moe_started.elapsed().as_secs_f64();
        assert_eq!(reports.len(), 34);
        if let Some((first_r9, first_r10)) = &first {
            assert_r9_bits(first_r9, &candidate_r9);
            assert_r10_bits(first_r10, &candidate_r10);
        } else {
            first = Some((candidate_r9, candidate_r10));
            first_reports = reports;
        }
        assert!(repeat < REPEATS);
    }
    timings.production_total_seconds = production_started.elapsed().as_secs_f64();
    timings.import_seconds = timings
        .per_role
        .values()
        .map(|value| value.import_seconds)
        .sum();
    timings.compute_sync_seconds = timings
        .per_role
        .values()
        .map(|value| value.compute_sync_seconds)
        .sum();
    timings.router_projection_seconds = role_total(&timings, "ffn_gate_inp");
    timings.routed_expert_projection_seconds = ["routed_gate", "routed_up", "routed_down"]
        .iter()
        .map(|role| role_total(&timings, role))
        .sum();
    timings.shared_expert_projection_seconds = ["shared_gate", "shared_up", "shared_down"]
        .iter()
        .map(|role| role_total(&timings, role))
        .sum();
    timings.cpu_norm_activation_routing_aggregation_residual_seconds =
        (timings.production_total_seconds - timings.import_seconds - timings.compute_sync_seconds)
            .max(0.0);
    let (candidate_r9, candidate_r10) = first.unwrap();
    let r9_output_metrics = measure_f32(&exact_r9.output, &candidate_r9.output).unwrap();
    assert_f32_contract("R9 output", &r9_output_metrics, &r9_contract["final"]);
    assert_eq!(candidate_r10.selected_ids, exact_r10.selected_ids);
    let routing_weights = measure_f64(&exact_r10.routing_weights, &candidate_r10.routing_weights);
    assert!(
        routing_weights.max_abs_error
            <= r10_contract["router"]["routing_weight_max_absolute_error"]
                .as_f64()
                .unwrap()
    );
    let r10_f32_boundaries = r10_f32_metrics(&exact_r10, &candidate_r10);
    for (name, metrics) in &r10_f32_boundaries {
        let contract = if name == "output" {
            &r10_contract["final"]
        } else {
            &r10_contract["intermediate"]
        };
        assert_f32_contract(name, metrics, contract);
    }
    let r10_f64_boundaries = BTreeMap::from([
        (
            "router_probabilities".to_owned(),
            measure_f64(
                &exact_r10.router_probabilities,
                &candidate_r10.router_probabilities,
            ),
        ),
        (
            "router_scores".to_owned(),
            measure_f64(&exact_r10.router_scores, &candidate_r10.router_scores),
        ),
        (
            "routing_weights".to_owned(),
            measure_f64(&exact_r10.routing_weights, &candidate_r10.routing_weights),
        ),
        (
            "routed_aggregate".to_owned(),
            measure_f64(&exact_r10.routed_aggregate, &candidate_r10.routed_aggregate),
        ),
        (
            "combined_moe".to_owned(),
            measure_f64(&exact_r10.combined_moe, &candidate_r10.combined_moe),
        ),
    ]);
    for (name, metrics) in &r10_f64_boundaries {
        assert_eq!(metrics.non_finite_count, 0, "{name}");
        assert!(
            metrics.max_abs_error
                <= r10_contract["final"]["max_absolute_error"]
                    .as_f64()
                    .unwrap(),
            "{name} max abs"
        );
        assert!(
            metrics.rmse <= r10_contract["final"]["rmse"].as_f64().unwrap(),
            "{name} rmse"
        );
    }

    context.synchronize().unwrap();
    let ownership = context.ownership_snapshot().unwrap();
    drop(context);
    let streams_after = MlxContext::debug_stream_counters().unwrap();
    let context_active_after = MlxContext::debug_context_active();
    let reconciled = ownership.managed_created == ownership.managed_destroyed
        && ownership.derived_created == ownership.derived_destroyed
        && ownership.derived_live == 0
        && ownership.callback_count == ownership.managed_created
        && streams_after.owned_created - streams_before.owned_created
            == streams_after.owned_freed - streams_before.owned_freed
        && !context_active_after;
    assert!(reconciled);
    let all_exact = r9_output_metrics.bit_mismatch_count == 0
        && r10_f32_boundaries
            .values()
            .all(|metrics| metrics.bit_mismatch_count == 0)
        && r10_f64_boundaries
            .values()
            .all(|metrics| metrics.bit_mismatch_count == 0);
    let report = Report {
        schema: "pulsarmlx.f017.r10-production-result",
        schema_version: "1.0.0",
        source_commit: clean_source_commit(&root),
        fixture_version: r10["fixture_version"].as_str().unwrap().to_owned(),
        fixture_sha256: sha256_bytes(&r10_bytes),
        r9_fixture_sha256: sha256_bytes(&r9_bytes),
        oracle_generator_sha: r10["generator_sha256"].as_str().unwrap().to_owned(),
        exact_scaffold_versions: [R9_SCAFFOLD_VERSION, R10_SCAFFOLD_VERSION],
        frozen_contract_versions: [
            "f017-production-expert-tier-b-v1".to_owned(),
            r9_contract["contract_version"].as_str().unwrap().to_owned(),
            r10_contract["contract_version"]
                .as_str()
                .unwrap()
                .to_owned(),
        ],
        production_backend_version: "mlx-native-0.31.2-mlxc-0.6.0-production-adapter",
        numerical_mode: "production_mlx_tier_b",
        deterministic_repeat_count: REPEATS,
        selected_ids: candidate_r10.selected_ids,
        routing_weights,
        r9_output: r9_output_metrics,
        r10_f32_boundaries,
        r10_f64_boundaries,
        first_repeat_matvec_qualifications: first_reports,
        classification: if all_exact {
            NumericalClassification::GoldenIdentical
        } else {
            NumericalClassification::NumericallyQualifiedGreedyNotApplicable
        },
        greedy_applicability: GreedyApplicability::NotApplicable,
        direct_native_dispatch_count: (REPEATS * 34) as u64,
        qualification_scaffold_dispatch_count: (REPEATS * 34 + 34) as u64,
        explicit_reference_dispatch_count: 0,
        unexpected_fallback_count: 0,
        backend_error_count: 0,
        timings,
        lifecycle: Lifecycle {
            managed_created: ownership.managed_created,
            managed_destroyed: ownership.managed_destroyed,
            derived_created: ownership.derived_created,
            derived_destroyed: ownership.derived_destroyed,
            callback_count: ownership.callback_count,
            owned_stream_created_delta: streams_after.owned_created - streams_before.owned_created,
            owned_stream_freed_delta: streams_after.owned_freed - streams_before.owned_freed,
            context_active_after,
            in_flight_after_teardown: 0,
            stale_generation_count: 0,
            reconciled,
        },
        review_status: "pending_adversarial_numerical_review",
        checkpoint_accessed: false,
    };
    if let Ok(path) = std::env::var("PULSAR_F017_R10_EVIDENCE_OUT") {
        fs::write(path, serde_json::to_string_pretty(&report).unwrap() + "\n").unwrap();
    }
    println!(
        "F017_R10_RESULT_JSON={}",
        serde_json::to_string(&report).unwrap()
    );
}

fn qualified_production_matvec(
    context: &MlxContext,
    matrix: &[f32],
    rows: usize,
    columns: usize,
    vector: &[f32],
    role: &'static str,
    timings: &mut Timings,
    reports: &mut Vec<MatvecReport>,
) -> Result<Vec<f32>, R9Error> {
    let mut expected = vec![0.0; rows];
    exact_matvec_f32(matrix, rows, columns, vector, &mut expected).map_err(R9Error::Matvec)?;
    let role_timing = timings.per_role.entry(role.to_owned()).or_default();
    let import_started = Instant::now();
    let mut matrix_owner = matrix.to_vec();
    let mut vector_owner = vector.to_vec();
    let matrix_array = context
        .import_f32_shaped(&mut matrix_owner, &[rows, columns])
        .map_err(|_| R9Error::CandidateMatvec("import matrix"))?;
    let vector_array = context
        .import_f32_shaped(&mut vector_owner, &[columns])
        .map_err(|_| R9Error::CandidateMatvec("import vector"))?;
    role_timing.import_seconds += import_started.elapsed().as_secs_f64();
    let compute_started = Instant::now();
    let result = matrix_array
        .matvec(&vector_array)
        .map_err(|_| R9Error::CandidateMatvec("dispatch"))?;
    result
        .evaluate_sync()
        .map_err(|_| R9Error::CandidateMatvec("evaluate/sync"))?;
    let mut actual = vec![0.0; rows];
    result
        .copy_f32(&mut actual)
        .map_err(|_| R9Error::CandidateMatvec("copy"))?;
    role_timing.compute_sync_seconds += compute_started.elapsed().as_secs_f64();
    role_timing.dispatch_count += 1;
    result
        .destroy()
        .map_err(|_| R9Error::CandidateMatvec("destroy result"))?;
    vector_array
        .destroy()
        .map_err(|_| R9Error::CandidateMatvec("destroy vector"))?;
    matrix_array
        .destroy()
        .map_err(|_| R9Error::CandidateMatvec("destroy matrix"))?;
    let qualification = qualify_tier_b_down(matrix, rows, columns, vector, &expected, &actual)
        .map_err(R9Error::Matvec)?;
    assert!(qualification.passes, "{role}");
    reports.push(MatvecReport {
        role: role.to_owned(),
        qualification,
    });
    Ok(actual)
}

fn r9_matrices(value: &Value) -> R9Matrices {
    R9Matrices {
        q_a: matrix(&value["matrices"]["attn_q_a"]),
        q_b: matrix(&value["matrices"]["attn_q_b"]),
        kv_a: matrix(&value["matrices"]["attn_kv_a_mqa"]),
        k_b: matrix(&value["matrices"]["attn_k_b"]),
        v_b: matrix(&value["matrices"]["attn_v_b"]),
        output: matrix(&value["matrices"]["attn_output"]),
    }
}
fn r9_inputs(value: &Value) -> R9Inputs {
    R9Inputs {
        residual: f32_record(&value["inputs"]["residual"]),
        attn_norm_scale: f32_record(&value["inputs"]["attn_norm_scale"]),
        q_norm_scale: f32_record(&value["inputs"]["q_norm_scale"]),
        kv_norm_scale: f32_record(&value["inputs"]["kv_norm_scale"]),
        prior_cache_latents: f32_record(&value["inputs"]["prior_cache_latents"]),
        prior_cache_ropes: f32_record(&value["inputs"]["prior_cache_ropes"]),
        q_rope_cosine: f32_record(&value["inputs"]["q_rope_cosine"]),
        q_rope_sine: f32_record(&value["inputs"]["q_rope_sine"]),
        rms_epsilon: value["inputs"]["rms_epsilon"].as_f64().unwrap() as f32,
        attention_scale: value["inputs"]["attention_scale"].as_f64().unwrap() as f32,
        query_position: value["architecture"]["query_position"].as_u64().unwrap() as usize,
        visible_positions: value["architecture"]["visible_positions"].as_u64().unwrap() as usize,
    }
}

fn r10_matrices(value: &Value) -> R10Matrices {
    let routed = value["inputs"]["routed_experts"]
        .as_array()
        .unwrap()
        .iter()
        .map(|expert| {
            let matrices = expert["matrices"].as_array().unwrap();
            ExpertMatrices {
                expert_id: expert["expert_id"].as_u64().unwrap() as usize,
                gate: matrix(&matrices[0]),
                up: matrix(&matrices[1]),
                down: matrix(&matrices[2]),
            }
        })
        .collect();
    let shared = value["inputs"]["shared_expert"]["matrices"]
        .as_array()
        .unwrap();
    R10Matrices {
        router: matrix(&value["inputs"]["router"]),
        routed,
        shared: ExpertMatrices {
            expert_id: usize::MAX,
            gate: matrix(&shared[0]),
            up: matrix(&shared[1]),
            down: matrix(&shared[2]),
        },
    }
}
fn r10_inputs(value: &Value) -> R10Inputs {
    R10Inputs {
        attention_residual: f32_record(&value["inputs"]["attention_residual"]),
        post_attention_norm_scale: f32_record(&value["inputs"]["post_attention_norm_scale"]),
        router_bias: f64_record(&value["inputs"]["router_bias"]),
        rms_epsilon: value["inputs"]["rms_epsilon"].as_f64().unwrap() as f32,
        top_k: value["architecture"]["selected_expert_count"]
            .as_u64()
            .unwrap() as usize,
        expert_weight_scale: value["architecture"]["expert_weight_scale"]
            .as_f64()
            .unwrap(),
    }
}

fn assert_r10_fixture(value: &Value, output: &R10Output) {
    assert_bits(
        &output.normalized,
        &f32_record(&value["expected"]["normalized"]),
        "normalized",
    );
    assert_bits(
        &output.router_logits,
        &f32_record(&value["expected"]["router_logits"]),
        "router logits",
    );
    assert_eq!(
        output.selected_ids,
        usize_values(&value["expected"]["selected_ids"])
    );
    assert_bits(
        &output.output,
        &f32_record(&value["expected"]["output"]),
        "output",
    );
}

fn r10_f32_metrics(expected: &R10Output, actual: &R10Output) -> BTreeMap<String, NumericalMetrics> {
    let mut metrics = BTreeMap::from([
        (
            "normalized".to_owned(),
            measure_f32(&expected.normalized, &actual.normalized).unwrap(),
        ),
        (
            "router_logits".to_owned(),
            measure_f32(&expected.router_logits, &actual.router_logits).unwrap(),
        ),
        (
            "output".to_owned(),
            measure_f32(&expected.output, &actual.output).unwrap(),
        ),
    ]);
    for (index, (expected, actual)) in expected
        .routed_experts
        .iter()
        .zip(&actual.routed_experts)
        .enumerate()
    {
        for (stage, expected, actual) in [
            ("gate", &expected.gate, &actual.gate),
            ("up", &expected.up, &actual.up),
            ("hidden", &expected.hidden, &actual.hidden),
            ("down", &expected.down, &actual.down),
        ] {
            metrics.insert(
                format!("routed_{index}_{stage}"),
                measure_f32(expected, actual).unwrap(),
            );
        }
    }
    for (stage, expected, actual) in [
        (
            "gate",
            &expected.shared_expert.gate,
            &actual.shared_expert.gate,
        ),
        ("up", &expected.shared_expert.up, &actual.shared_expert.up),
        (
            "hidden",
            &expected.shared_expert.hidden,
            &actual.shared_expert.hidden,
        ),
        (
            "down",
            &expected.shared_expert.down,
            &actual.shared_expert.down,
        ),
    ] {
        metrics.insert(
            format!("shared_{stage}"),
            measure_f32(expected, actual).unwrap(),
        );
    }
    metrics
}

fn assert_f32_contract(name: &str, metrics: &NumericalMetrics, contract: &Value) {
    assert_eq!(metrics.non_finite_count, 0, "{name}");
    assert_eq!(metrics.signed_zero_mismatch_count, 0, "{name}");
    assert!(
        metrics.max_abs_error <= contract["max_absolute_error"].as_f64().unwrap(),
        "{name} max abs"
    );
    assert!(
        metrics.rmse <= contract["rmse"].as_f64().unwrap(),
        "{name} rmse"
    );
    if let Some(cosine) = metrics.cosine_similarity {
        assert!(
            cosine >= contract["cosine_similarity_minimum"].as_f64().unwrap(),
            "{name} cosine"
        );
    }
}

fn measure_f64(expected: &[f64], actual: &[f64]) -> F64Metrics {
    let errors = expected
        .iter()
        .zip(actual)
        .map(|(expected, actual)| (actual - expected).abs())
        .collect::<Vec<_>>();
    let dot = expected
        .iter()
        .zip(actual)
        .map(|(left, right)| left * right)
        .sum::<f64>();
    let expected_norm = expected
        .iter()
        .map(|value| value * value)
        .sum::<f64>()
        .sqrt();
    let actual_norm = actual.iter().map(|value| value * value).sum::<f64>().sqrt();
    F64Metrics {
        element_count: expected.len(),
        bit_mismatch_count: expected
            .iter()
            .zip(actual)
            .filter(|(left, right)| left.to_bits() != right.to_bits())
            .count(),
        non_finite_count: expected
            .iter()
            .chain(actual)
            .filter(|value| !value.is_finite())
            .count(),
        max_abs_error: errors.iter().copied().fold(0.0, f64::max),
        rmse: (errors.iter().map(|value| value * value).sum::<f64>() / expected.len() as f64)
            .sqrt(),
        cosine_similarity: (expected_norm > 0.0 && actual_norm > 0.0)
            .then_some(dot / (expected_norm * actual_norm)),
        first_divergence_index: expected
            .iter()
            .zip(actual)
            .position(|(left, right)| left.to_bits() != right.to_bits()),
    }
}

fn role_total(timings: &Timings, role: &str) -> f64 {
    timings
        .per_role
        .get(role)
        .map(|value| value.import_seconds + value.compute_sync_seconds)
        .unwrap_or(0.0)
}
fn matrix(value: &Value) -> Vec<f32> {
    let packed = decode_hex(value["packed_hex"].as_str().unwrap());
    assert_eq!(sha256_bytes(&packed), value["packed_sha256"]);
    let shape = usize_values(&value["shape"]);
    let mut output = vec![0.0; shape[0] * shape[1]];
    quant::decode_q8_0_matrix(&packed, shape[0], shape[1], &mut output).unwrap();
    assert_eq!(
        sha256_bytes(&f32_bytes(&output)),
        value["decoded_f32_sha256"]
    );
    output
}
fn f32_record(value: &Value) -> Vec<f32> {
    decode_hex(value["f32_le_hex"].as_str().unwrap())
        .chunks_exact(4)
        .map(|bytes| f32::from_le_bytes(bytes.try_into().unwrap()))
        .collect()
}
fn f64_record(value: &Value) -> Vec<f64> {
    decode_hex(value["f64_le_hex"].as_str().unwrap())
        .chunks_exact(8)
        .map(|bytes| f64::from_le_bytes(bytes.try_into().unwrap()))
        .collect()
}
fn usize_values(value: &Value) -> Vec<usize> {
    value
        .as_array()
        .unwrap()
        .iter()
        .map(|value| value.as_u64().unwrap() as usize)
        .collect()
}
fn assert_r9_bits(expected: &R9Output, actual: &R9Output) {
    assert_bits(&expected.output, &actual.output, "deterministic R9 output");
    assert_eq!(expected.selected_positions, actual.selected_positions);
}
fn assert_r10_bits(expected: &R10Output, actual: &R10Output) {
    assert_bits(&expected.output, &actual.output, "deterministic R10 output");
    assert_eq!(expected.selected_ids, actual.selected_ids);
    assert_eq!(
        expected
            .routing_weights
            .iter()
            .map(|v| v.to_bits())
            .collect::<Vec<_>>(),
        actual
            .routing_weights
            .iter()
            .map(|v| v.to_bits())
            .collect::<Vec<_>>()
    );
}
fn assert_bits(expected: &[f32], actual: &[f32], name: &str) {
    assert_eq!(
        expected
            .iter()
            .map(|value| value.to_bits())
            .collect::<Vec<_>>(),
        actual
            .iter()
            .map(|value| value.to_bits())
            .collect::<Vec<_>>(),
        "{name}"
    );
}
fn clean_source_commit(root: &Path) -> String {
    let status = Command::new("git")
        .args(["status", "--porcelain"])
        .current_dir(root)
        .output()
        .unwrap();
    assert!(status.status.success());
    if !status.stdout.is_empty() {
        assert_eq!(
            std::env::var("PULSAR_F017_ALLOW_DIRTY_TEST").as_deref(),
            Ok("1"),
            "R10 evidence requires clean source"
        );
        assert!(std::env::var_os("PULSAR_F017_R10_EVIDENCE_OUT").is_none());
    }
    let output = Command::new("git")
        .args(["rev-parse", "HEAD"])
        .current_dir(root)
        .output()
        .unwrap();
    String::from_utf8(output.stdout).unwrap().trim().to_owned()
}
fn decode_hex(encoded: &str) -> Vec<u8> {
    encoded
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
        .collect()
}
fn f32_bytes(values: &[f32]) -> Vec<u8> {
    values
        .iter()
        .flat_map(|value| value.to_le_bytes())
        .collect()
}
