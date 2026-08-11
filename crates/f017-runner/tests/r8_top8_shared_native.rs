#![cfg(all(target_os = "macos", pulsar_native_mlx))]

use f017_runner::json::{parse_json_no_duplicates, sha256_bytes, sha256_file};
use f017_runner::numerical_classification::{GreedyApplicability, NumericalClassification};
use f017_runner::qualification::{
    exact_matvec_f32, exact_swiglu_f32, measure_f32, qualify_tier_b_down, NumericalMetrics,
    TierBQualification, EXACT_SCAFFOLD_VERSION, TIER_B_CONTRACT_VERSION,
};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;
use std::process::Command;
use std::time::Instant;
use stream::{MlxContext, MlxDevice, MlxStreamMode};

const WIDTH: usize = 32;
const REPEATS: usize = 10;

#[derive(Deserialize)]
struct R8Oracle {
    schema: String,
    schema_version: String,
    fixture_version: String,
    generator_path: String,
    generator_sha256: String,
    r7_oracle_fixture_sha256: String,
    contract_version: String,
    independence: Independence,
    shape: [usize; 3],
    quantization: String,
    scores_f64_le_hex: String,
    scores_sha256: String,
    selected_ids: Vec<usize>,
    weights_f64_le_hex: String,
    weights_sha256: String,
    activations: Vec<Vec<f32>>,
    activation_sha256: Vec<String>,
    expert_outputs: Vec<Vec<f32>>,
    expert_output_sha256: Vec<String>,
    shared_output: Vec<f32>,
    shared_output_sha256: String,
    per_expert_absolute_bounds: Vec<Vec<f64>>,
    residual_f64_le_hex: String,
    residual_sha256: String,
    aggregate_f64_le_hex: String,
    aggregate_sha256: String,
    aggregate_absolute_bounds_f64_le_hex: String,
    final_output_f64_le_hex: String,
    final_output_sha256: String,
    behavioral_contract: BehavioralContract,
}

#[derive(Deserialize)]
struct Independence {
    classification: String,
    uses_rust_candidate: bool,
    uses_rust_reference_functions: bool,
    uses_mlx: bool,
    uses_checkpoint: bool,
}

#[derive(Deserialize)]
struct BehavioralContract {
    router_ids: String,
    router_weights_atol: f64,
    tie_break: String,
    greedy_applicability: String,
}

#[derive(Deserialize)]
struct R7Oracle {
    schema: String,
    boundaries: R7Boundaries,
}

#[derive(Deserialize)]
struct R7Boundaries {
    complete_expert: R7Expert,
}

#[derive(Deserialize)]
struct R7Expert {
    fixture_version: String,
    inputs: R7Inputs,
}

#[derive(Deserialize)]
struct R7Inputs {
    gate_packed_hex: String,
    up_packed_hex: String,
    down_packed_hex: String,
}

#[derive(Serialize)]
struct R8Report {
    schema: &'static str,
    schema_version: &'static str,
    source_commit: String,
    fixture_version: String,
    fixture_sha256: String,
    oracle_generator_sha: String,
    scaffold_version: &'static str,
    numerical_mode: &'static str,
    production_backend_version: &'static str,
    frozen_contract_version: &'static str,
    deterministic_repeat_count: usize,
    selected_ids: Vec<usize>,
    weights: Vec<f64>,
    routed_experts: Vec<ExpertReport>,
    shared_expert: ExpertReport,
    aggregate: F64Metrics,
    final_output: F64Metrics,
    classification: NumericalClassification,
    greedy_applicability: GreedyApplicability,
    direct_native_dispatch_count: u64,
    qualification_scaffold_dispatch_count: u64,
    explicit_reference_dispatch_count: u64,
    unexpected_fallback_count: u64,
    timings: Timings,
    lifecycle: Lifecycle,
    checkpoint_accessed: bool,
}

#[derive(Serialize)]
struct ExpertReport {
    expert_id: usize,
    shared: bool,
    gate: NumericalMetrics,
    up: NumericalMetrics,
    activated_hidden: NumericalMetrics,
    down: TierBQualification,
    candidate_output_sha256: String,
}

#[derive(Serialize)]
struct F64Metrics {
    element_count: usize,
    bit_mismatch_count: usize,
    max_abs_error: f64,
    rmse: f64,
    all_within_propagated_bound: bool,
    first_divergence_index: Option<usize>,
}

#[derive(Default, Serialize)]
struct Timings {
    exact_scaffold_seconds: f64,
    production_import_seconds: f64,
    production_compute_sync_seconds: f64,
    activation_seconds: f64,
    router_aggregation_seconds: f64,
    total_seconds: f64,
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
    reconciled: bool,
}

#[test]
fn checkpoint_free_r8_top8_shared_qualifies_without_fallback() {
    let total_started = Instant::now();
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let source_commit = clean_source_commit(&root);
    let r8_path = root.join(
        "specs/017-rust-native-inference-runtime/fixtures/f017-r8-top8-shared-oracle-v2.json",
    );
    let r7_path = root
        .join("specs/017-rust-native-inference-runtime/fixtures/f017-independent-oracle-v1.json");
    let r8_bytes = fs::read(&r8_path).unwrap();
    let r7_bytes = fs::read(&r7_path).unwrap();
    let r8: R8Oracle = parse_json_no_duplicates(&r8_bytes).unwrap();
    let r7: R7Oracle = parse_json_no_duplicates(&r7_bytes).unwrap();
    validate_oracles(&root, &r8, &r7, &r7_bytes);
    let scores = decode_f64_hex(&r8.scores_f64_le_hex);
    let oracle_weights = decode_f64_hex(&r8.weights_f64_le_hex);
    let residual = decode_f64_hex(&r8.residual_f64_le_hex);
    let oracle_aggregate = decode_f64_hex(&r8.aggregate_f64_le_hex);
    let aggregate_bounds = decode_f64_hex(&r8.aggregate_absolute_bounds_f64_le_hex);
    let oracle_final = decode_f64_hex(&r8.final_output_f64_le_hex);
    let matrices = [
        decode_matrix(&r7.boundaries.complete_expert.inputs.gate_packed_hex),
        decode_matrix(&r7.boundaries.complete_expert.inputs.up_packed_hex),
        decode_matrix(&r7.boundaries.complete_expert.inputs.down_packed_hex),
    ];

    let selected_ids = select_top8(&scores);
    assert_eq!(selected_ids, r8.selected_ids);
    let weights = selected_softmax(&scores, &selected_ids);
    for (actual, expected) in weights.iter().zip(&oracle_weights) {
        assert!((actual - expected).abs() <= r8.behavioral_contract.router_weights_atol);
    }

    let mut timings = Timings::default();
    let exact = r8
        .activations
        .iter()
        .map(|activation| exact_expert(&matrices, activation, &mut timings))
        .collect::<Vec<_>>();
    for expert_id in 0..8 {
        assert_bits_equal(&exact[expert_id].3, &r8.expert_outputs[expert_id]);
    }
    assert_bits_equal(&exact[8].3, &r8.shared_output);

    let streams_before = MlxContext::debug_stream_counters().unwrap();
    assert!(!MlxContext::debug_context_active());
    let context = MlxContext::new(MlxDevice::Gpu, MlxStreamMode::Owned).unwrap();
    let mut first_outputs: Option<Vec<Vec<f32>>> = None;
    for _ in 0..REPEATS {
        let outputs = r8
            .activations
            .iter()
            .map(|activation| production_expert(&context, &matrices, activation, &mut timings))
            .collect::<Vec<_>>();
        if let Some(first) = &first_outputs {
            for (expected, actual) in first.iter().zip(&outputs) {
                assert_bits_equal(expected, actual);
            }
        } else {
            first_outputs = Some(outputs);
        }
    }
    let outputs = first_outputs.unwrap();
    let mut expert_reports = Vec::new();
    for expert_id in 0..9 {
        let expected = if expert_id < 8 {
            &r8.expert_outputs[expert_id]
        } else {
            &r8.shared_output
        };
        let candidate_gate = production_gate(
            &context,
            &matrices[0],
            &r8.activations[expert_id],
            &mut timings,
        );
        let candidate_up = production_gate(
            &context,
            &matrices[1],
            &r8.activations[expert_id],
            &mut timings,
        );
        let gate = measure_f32(&exact[expert_id].0, &candidate_gate).unwrap();
        let up = measure_f32(&exact[expert_id].1, &candidate_up).unwrap();
        let mut production_hidden = vec![0.0; WIDTH];
        exact_swiglu_f32(&candidate_gate, &candidate_up, &mut production_hidden).unwrap();
        assert_eq!(gate.bit_mismatch_count, 0);
        assert_eq!(up.bit_mismatch_count, 0);
        let hidden_metrics = measure_f32(&exact[expert_id].2, &production_hidden).unwrap();
        assert_eq!(hidden_metrics.bit_mismatch_count, 0);
        let down = qualify_tier_b_down(
            &matrices[2],
            WIDTH,
            WIDTH,
            &exact[expert_id].2,
            expected,
            &outputs[expert_id],
        )
        .unwrap();
        assert!(down.passes);
        assert_frozen_bounds(&down, &r8.per_expert_absolute_bounds[expert_id]);
        expert_reports.push(ExpertReport {
            expert_id,
            shared: expert_id == 8,
            gate,
            up,
            activated_hidden: hidden_metrics,
            down,
            candidate_output_sha256: sha256_bytes(&f32_bytes(&outputs[expert_id])),
        });
    }

    let aggregation_started = Instant::now();
    let aggregate = aggregate_outputs(&outputs, &selected_ids, &weights);
    let final_output = aggregate
        .iter()
        .zip(&outputs[8])
        .zip(&residual)
        .map(|((routed, shared), residual)| routed + f64::from(*shared) + residual)
        .collect::<Vec<_>>();
    timings.router_aggregation_seconds += aggregation_started.elapsed().as_secs_f64();
    let mut routed_bounds =
        routed_aggregate_bounds(&r8.per_expert_absolute_bounds, &selected_ids, &weights);
    include_router_weight_error(
        &mut routed_bounds,
        &r8.expert_outputs,
        &selected_ids,
        &weights,
        &oracle_weights,
    );
    let aggregate_metrics = measure_f64(&oracle_aggregate, &aggregate, &routed_bounds);
    let mut final_bounds = aggregate_bounds;
    include_router_weight_error(
        &mut final_bounds,
        &r8.expert_outputs,
        &selected_ids,
        &weights,
        &oracle_weights,
    );
    let final_metrics = measure_f64(&oracle_final, &final_output, &final_bounds);
    assert!(aggregate_metrics.all_within_propagated_bound);
    assert!(final_metrics.all_within_propagated_bound);

    context.synchronize().unwrap();
    let ownership = context.ownership_snapshot().unwrap();
    drop(context);
    let streams_after = MlxContext::debug_stream_counters().unwrap();
    let context_active_after = MlxContext::debug_context_active();
    let lifecycle_reconciled = ownership.managed_created == ownership.managed_destroyed
        && ownership.derived_created == ownership.derived_destroyed
        && ownership.derived_live == 0
        && ownership.callback_count == ownership.managed_created
        && streams_after.owned_created - streams_before.owned_created
            == streams_after.owned_freed - streams_before.owned_freed
        && !context_active_after;
    assert!(lifecycle_reconciled);
    timings.total_seconds = total_started.elapsed().as_secs_f64();
    let shared_report = expert_reports.pop().unwrap();
    let report = R8Report {
        schema: "pulsarmlx.f017.r8-top8-shared-production-result",
        schema_version: "1.0.0",
        source_commit,
        fixture_version: r8.fixture_version,
        fixture_sha256: sha256_bytes(&r8_bytes),
        oracle_generator_sha: r8.generator_sha256,
        scaffold_version: EXACT_SCAFFOLD_VERSION,
        numerical_mode: "production_mlx_tier_b",
        production_backend_version: "mlx-c-matmul; mlx-native-0.31.2; mlx-c-0.6.0",
        frozen_contract_version: TIER_B_CONTRACT_VERSION,
        deterministic_repeat_count: REPEATS,
        selected_ids,
        weights,
        routed_experts: expert_reports,
        shared_expert: shared_report,
        aggregate: aggregate_metrics,
        final_output: final_metrics,
        classification: NumericalClassification::NumericallyQualifiedGreedyNotApplicable,
        greedy_applicability: GreedyApplicability::NotApplicable,
        direct_native_dispatch_count: (REPEATS * 9 * 3 + 9 * 2) as u64,
        qualification_scaffold_dispatch_count: (9 * 3) as u64,
        explicit_reference_dispatch_count: 0,
        unexpected_fallback_count: 0,
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
            reconciled: lifecycle_reconciled,
        },
        checkpoint_accessed: false,
    };
    let report_json = serde_json::to_string(&report).unwrap();
    if let Ok(path) = std::env::var("PULSAR_F017_R8_RESULT_OUT") {
        let path = Path::new(&path);
        let temporary = path.with_extension("json.tmp");
        fs::write(
            &temporary,
            format!("{}\n", serde_json::to_string_pretty(&report).unwrap()),
        )
        .unwrap();
        fs::rename(temporary, path).unwrap();
    }
    println!("F017_R8_JSON={report_json}");
}

fn clean_source_commit(root: &Path) -> String {
    let head = Command::new("git")
        .args(["rev-parse", "HEAD"])
        .current_dir(root)
        .output()
        .unwrap();
    assert!(head.status.success());
    let status = Command::new("git")
        .args(["status", "--porcelain", "--untracked-files=no"])
        .current_dir(root)
        .output()
        .unwrap();
    assert!(status.status.success());
    assert!(
        status.stdout.is_empty(),
        "R8 result requires a clean tracked source tree"
    );
    String::from_utf8(head.stdout).unwrap().trim().to_owned()
}

fn validate_oracles(root: &Path, r8: &R8Oracle, r7: &R7Oracle, r7_bytes: &[u8]) {
    assert_eq!(r8.schema, "pulsarmlx.f017.r8-top8-shared-oracle");
    assert_eq!(r8.schema_version, "2.0.0");
    assert_eq!(r8.contract_version, TIER_B_CONTRACT_VERSION);
    assert_eq!(r8.shape, [1, 8, WIDTH]);
    assert_eq!(r8.quantization, "Q8_0");
    assert_eq!(r8.independence.classification, "INDEPENDENT");
    assert!(!r8.independence.uses_rust_candidate);
    assert!(!r8.independence.uses_rust_reference_functions);
    assert!(!r8.independence.uses_mlx);
    assert!(!r8.independence.uses_checkpoint);
    assert_eq!(r7.schema, "glm52-f017-independent-oracle-v1");
    assert_eq!(
        r7.boundaries.complete_expert.fixture_version,
        "glm52-runtime-expert-q8-0-v2"
    );
    assert_eq!(sha256_bytes(r7_bytes), r8.r7_oracle_fixture_sha256);
    assert_eq!(
        sha256_file(&root.join(&r8.generator_path)).unwrap(),
        r8.generator_sha256
    );
    assert_eq!(
        sha256_bytes(&decode_hex(&r8.scores_f64_le_hex)),
        r8.scores_sha256
    );
    assert_eq!(
        sha256_bytes(&decode_hex(&r8.weights_f64_le_hex)),
        r8.weights_sha256
    );
    assert_eq!(
        sha256_bytes(&decode_hex(&r8.residual_f64_le_hex)),
        r8.residual_sha256
    );
    assert_eq!(
        sha256_bytes(&decode_hex(&r8.aggregate_f64_le_hex)),
        r8.aggregate_sha256
    );
    assert_eq!(
        sha256_bytes(&decode_hex(&r8.final_output_f64_le_hex)),
        r8.final_output_sha256
    );
    assert_eq!(decode_f64_hex(&r8.scores_f64_le_hex).len(), 8);
    assert_eq!(decode_f64_hex(&r8.weights_f64_le_hex).len(), 8);
    assert_eq!(
        decode_f64_hex(&r8.aggregate_absolute_bounds_f64_le_hex).len(),
        WIDTH
    );
    assert_eq!(r8.behavioral_contract.router_ids, "exact");
    assert_eq!(r8.behavioral_contract.tie_break, "lowest_expert_id");
    assert_eq!(r8.behavioral_contract.greedy_applicability, "router_top8");
    for index in 0..9 {
        assert_eq!(
            sha256_bytes(&f32_bytes(&r8.activations[index])),
            r8.activation_sha256[index]
        );
    }
    for index in 0..8 {
        assert_eq!(
            sha256_bytes(&f32_bytes(&r8.expert_outputs[index])),
            r8.expert_output_sha256[index]
        );
    }
    assert_eq!(
        sha256_bytes(&f32_bytes(&r8.shared_output)),
        r8.shared_output_sha256
    );
}

fn exact_expert(
    matrices: &[Vec<f32>; 3],
    activation: &[f32],
    timings: &mut Timings,
) -> (Vec<f32>, Vec<f32>, Vec<f32>, Vec<f32>) {
    let started = Instant::now();
    let mut gate = vec![0.0; WIDTH];
    let mut up = vec![0.0; WIDTH];
    let mut hidden = vec![0.0; WIDTH];
    let mut output = vec![0.0; WIDTH];
    exact_matvec_f32(&matrices[0], WIDTH, WIDTH, activation, &mut gate).unwrap();
    exact_matvec_f32(&matrices[1], WIDTH, WIDTH, activation, &mut up).unwrap();
    exact_swiglu_f32(&gate, &up, &mut hidden).unwrap();
    exact_matvec_f32(&matrices[2], WIDTH, WIDTH, &hidden, &mut output).unwrap();
    timings.exact_scaffold_seconds += started.elapsed().as_secs_f64();
    (gate, up, hidden, output)
}

fn production_expert(
    context: &MlxContext,
    matrices: &[Vec<f32>; 3],
    activation: &[f32],
    timings: &mut Timings,
) -> Vec<f32> {
    let gate = production_gate(context, &matrices[0], activation, timings);
    let up = production_gate(context, &matrices[1], activation, timings);
    let activation_started = Instant::now();
    let mut hidden = vec![0.0; WIDTH];
    exact_swiglu_f32(&gate, &up, &mut hidden).unwrap();
    timings.activation_seconds += activation_started.elapsed().as_secs_f64();
    production_gate(context, &matrices[2], &hidden, timings)
}

fn production_gate(
    context: &MlxContext,
    matrix: &[f32],
    vector: &[f32],
    timings: &mut Timings,
) -> Vec<f32> {
    let import_started = Instant::now();
    let mut matrix_owner = matrix.to_vec();
    let mut vector_owner = vector.to_vec();
    let matrix = context
        .import_f32_shaped(&mut matrix_owner, &[WIDTH, WIDTH])
        .unwrap();
    let vector = context
        .import_f32_shaped(&mut vector_owner, &[WIDTH])
        .unwrap();
    timings.production_import_seconds += import_started.elapsed().as_secs_f64();
    let compute_started = Instant::now();
    let result = matrix.matvec(&vector).unwrap();
    result.evaluate_sync().unwrap();
    let mut output = vec![0.0; WIDTH];
    result.copy_f32(&mut output).unwrap();
    timings.production_compute_sync_seconds += compute_started.elapsed().as_secs_f64();
    result.destroy().unwrap();
    vector.destroy().unwrap();
    matrix.destroy().unwrap();
    output
}

fn select_top8(scores: &[f64]) -> Vec<usize> {
    let mut ids = (0..scores.len()).collect::<Vec<_>>();
    ids.sort_by(|left, right| {
        scores[*right]
            .total_cmp(&scores[*left])
            .then_with(|| left.cmp(right))
    });
    ids.truncate(8);
    ids
}

fn selected_softmax(scores: &[f64], selected: &[usize]) -> Vec<f64> {
    let maximum = selected
        .iter()
        .map(|index| scores[*index])
        .fold(f64::NEG_INFINITY, f64::max);
    let exponentials = selected
        .iter()
        .map(|index| (scores[*index] - maximum).exp())
        .collect::<Vec<_>>();
    let denominator = exponentials.iter().sum::<f64>();
    exponentials
        .iter()
        .map(|value| value / denominator)
        .collect()
}

fn aggregate_outputs(outputs: &[Vec<f32>], selected: &[usize], weights: &[f64]) -> Vec<f64> {
    (0..WIDTH)
        .map(|column| {
            selected
                .iter()
                .enumerate()
                .map(|(route, expert_id)| weights[route] * f64::from(outputs[*expert_id][column]))
                .sum()
        })
        .collect()
}

fn routed_aggregate_bounds(bounds: &[Vec<f64>], selected: &[usize], weights: &[f64]) -> Vec<f64> {
    (0..WIDTH)
        .map(|column| {
            selected
                .iter()
                .enumerate()
                .map(|(route, expert_id)| weights[route] * bounds[*expert_id][column])
                .sum()
        })
        .collect()
}

fn include_router_weight_error(
    bounds: &mut [f64],
    oracle_outputs: &[Vec<f32>],
    selected: &[usize],
    actual_weights: &[f64],
    oracle_weights: &[f64],
) {
    for column in 0..bounds.len() {
        bounds[column] += selected
            .iter()
            .enumerate()
            .map(|(route, expert_id)| {
                (actual_weights[route] - oracle_weights[route]).abs()
                    * f64::from(oracle_outputs[*expert_id][column]).abs()
            })
            .sum::<f64>();
    }
}

fn measure_f64(expected: &[f64], actual: &[f64], bounds: &[f64]) -> F64Metrics {
    let errors = expected
        .iter()
        .zip(actual)
        .map(|(expected, actual)| (actual - expected).abs())
        .collect::<Vec<_>>();
    F64Metrics {
        element_count: expected.len(),
        bit_mismatch_count: expected
            .iter()
            .zip(actual)
            .filter(|(expected, actual)| expected.to_bits() != actual.to_bits())
            .count(),
        max_abs_error: errors.iter().copied().fold(0.0, f64::max),
        rmse: (errors.iter().map(|error| error * error).sum::<f64>() / expected.len() as f64)
            .sqrt(),
        all_within_propagated_bound: errors
            .iter()
            .zip(bounds)
            .all(|(error, bound)| error <= bound),
        first_divergence_index: expected
            .iter()
            .zip(actual)
            .position(|(expected, actual)| expected.to_bits() != actual.to_bits()),
    }
}

fn assert_frozen_bounds(qualification: &TierBQualification, expected: &[f64]) {
    for (row, expected) in qualification.rows.iter().zip(expected) {
        let scale = expected.abs().max(f64::MIN_POSITIVE);
        assert!((row.absolute_bound - expected).abs() <= scale * 1.0e-14);
    }
}

fn decode_matrix(encoded: &str) -> Vec<f32> {
    let packed = decode_hex(encoded);
    let mut output = vec![0.0; WIDTH * WIDTH];
    quant::decode_q8_0_matrix(&packed, WIDTH, WIDTH, &mut output).unwrap();
    output
}

fn decode_hex(encoded: &str) -> Vec<u8> {
    assert_eq!(encoded.len() % 2, 0);
    encoded
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
        .collect()
}

fn decode_f64_hex(encoded: &str) -> Vec<f64> {
    let bytes = decode_hex(encoded);
    assert_eq!(bytes.len() % 8, 0);
    bytes
        .chunks_exact(8)
        .map(|value| f64::from_le_bytes(value.try_into().unwrap()))
        .collect()
}

fn assert_bits_equal(expected: &[f32], actual: &[f32]) {
    assert_eq!(
        expected
            .iter()
            .map(|value| value.to_bits())
            .collect::<Vec<_>>(),
        actual
            .iter()
            .map(|value| value.to_bits())
            .collect::<Vec<_>>()
    );
}

fn f32_bytes(values: &[f32]) -> Vec<u8> {
    values
        .iter()
        .flat_map(|value| value.to_le_bytes())
        .collect()
}
