#![cfg(all(target_os = "macos", pulsar_native_mlx))]

use f017_runner::json::{parse_json_no_duplicates, sha256_bytes, sha256_file};
use f017_runner::numerical_classification::NumericalClassification;
use f017_runner::qualification::{qualify_tier_b_down, TierBQualification};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;
use std::time::Instant;
use stream::{MlxContext, MlxDevice, MlxStreamMode};

const REPEATS: usize = 10;

#[derive(Deserialize)]
struct Oracle {
    schema: String,
    schema_version: String,
    contract_version: String,
    source_commit: String,
    generator_path: String,
    generator_sha256: String,
    independence: Independence,
    cases: Vec<StressCase>,
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
struct StressCase {
    name: String,
    shape: [usize; 2],
    matrix: Vec<f32>,
    matrix_sha256: String,
    vector: Vec<f32>,
    vector_sha256: String,
    expected: Vec<f32>,
    expected_sha256: String,
    l1_products: Vec<f64>,
    absolute_bounds: Vec<f64>,
    rmse_bound: f64,
    behavioral_selection: bool,
    expected_argmax_lowest_index_tie_break: usize,
}

#[derive(Serialize)]
struct StressReport {
    schema: &'static str,
    schema_version: &'static str,
    contract_version: String,
    oracle_fixture_sha256: String,
    oracle_source_commit: String,
    oracle_generator_sha256: String,
    production_backend: &'static str,
    deterministic_repeat_count: usize,
    cases: Vec<CaseReport>,
    all_numerically_qualified: bool,
    all_applicable_behavior_identical: bool,
    lifecycle: Lifecycle,
    checkpoint_accessed: bool,
}

#[derive(Serialize)]
struct CaseReport {
    name: String,
    shape: [usize; 2],
    candidate_sha256: String,
    deterministic: bool,
    candidate_argmax_lowest_index_tie_break: usize,
    behavioral_selection_matches: Option<bool>,
    classification: NumericalClassification,
    qualification: TierBQualification,
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
    reconciled: bool,
}

#[test]
fn frozen_independent_stresses_qualify_production_mlx_without_contract_tuning() {
    let fixture_path = Path::new(env!("CARGO_MANIFEST_DIR")).join(
        "../../specs/017-rust-native-inference-runtime/fixtures/f017-tier-b-stress-oracle-v1.json",
    );
    let fixture_bytes = fs::read(&fixture_path).unwrap();
    let fixture_sha256 = sha256_bytes(&fixture_bytes);
    let oracle: Oracle = parse_json_no_duplicates(&fixture_bytes).unwrap();
    validate_oracle(&oracle);

    let streams_before = MlxContext::debug_stream_counters().unwrap();
    assert!(!MlxContext::debug_context_active());
    let context = MlxContext::new(MlxDevice::Gpu, MlxStreamMode::Owned).unwrap();
    let mut reports = Vec::new();

    for case in oracle.cases {
        validate_case_hashes(&case);
        let mut first: Option<Vec<f32>> = None;
        let mut import_seconds = 0.0;
        let mut compute_sync_seconds = 0.0;
        for _ in 0..REPEATS {
            let (output, import, compute) = production_matvec(
                &context,
                case.matrix.clone(),
                case.vector.clone(),
                case.shape,
            );
            import_seconds += import;
            compute_sync_seconds += compute;
            if let Some(expected_bits) = &first {
                assert_bits_equal(expected_bits, &output);
            } else {
                first = Some(output);
            }
        }
        let output = first.unwrap();
        let qualification = qualify_tier_b_down(
            &case.matrix,
            case.shape[0],
            case.shape[1],
            &case.vector,
            &case.expected,
            &output,
        )
        .unwrap();
        assert_frozen_bounds_match(&case, &qualification);
        let candidate_argmax = argmax_lowest_index(&output);
        let behavioral_matches = case
            .behavioral_selection
            .then_some(candidate_argmax == case.expected_argmax_lowest_index_tie_break);
        let classification = if !qualification.passes {
            NumericalClassification::NumericallyFailed
        } else if qualification.metrics.bit_mismatch_count == 0 {
            NumericalClassification::GoldenIdentical
        } else if behavioral_matches == Some(false) {
            NumericalClassification::NumericallyQualifiedGreedyDivergent
        } else if behavioral_matches.is_none() {
            NumericalClassification::NumericallyQualifiedGreedyNotApplicable
        } else {
            NumericalClassification::NumericallyQualifiedGreedyIdentical
        };
        reports.push(CaseReport {
            name: case.name,
            shape: case.shape,
            candidate_sha256: sha256_bytes(&f32_bytes(&output)),
            deterministic: true,
            candidate_argmax_lowest_index_tie_break: candidate_argmax,
            behavioral_selection_matches: behavioral_matches,
            classification,
            qualification,
            import_seconds,
            compute_sync_seconds,
        });
    }

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
    let all_numerically_qualified = reports.iter().all(|case| case.qualification.passes);
    let all_applicable_behavior_identical = reports
        .iter()
        .all(|case| case.behavioral_selection_matches != Some(false));
    let report = StressReport {
        schema: "pulsarmlx.f017.tier-b-production-stress-result",
        schema_version: "1.0.0",
        contract_version: oracle.contract_version,
        oracle_fixture_sha256: fixture_sha256,
        oracle_source_commit: oracle.source_commit,
        oracle_generator_sha256: oracle.generator_sha256,
        production_backend: "mlx-c-matmul",
        deterministic_repeat_count: REPEATS,
        cases: reports,
        all_numerically_qualified,
        all_applicable_behavior_identical,
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
    println!(
        "F017_TIER_B_STRESS_JSON={}",
        serde_json::to_string(&report).unwrap()
    );
    assert!(report.all_numerically_qualified);
    assert!(report.all_applicable_behavior_identical);
    assert!(report.lifecycle.reconciled);
}

fn validate_oracle(oracle: &Oracle) {
    assert_eq!(oracle.schema, "pulsarmlx.f017.tier-b-stress-oracle");
    assert_eq!(oracle.schema_version, "1.0.0");
    assert_eq!(oracle.contract_version, "f017-production-expert-tier-b-v1");
    assert_eq!(oracle.independence.classification, "INDEPENDENT");
    assert!(!oracle.independence.uses_rust_candidate);
    assert!(!oracle.independence.uses_rust_reference_functions);
    assert!(!oracle.independence.uses_mlx);
    assert!(!oracle.independence.uses_checkpoint);
    let generator_path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .join(&oracle.generator_path);
    assert_eq!(
        sha256_file(&generator_path).unwrap(),
        oracle.generator_sha256
    );
}

fn validate_case_hashes(case: &StressCase) {
    assert_eq!(sha256_bytes(&f32_bytes(&case.matrix)), case.matrix_sha256);
    assert_eq!(sha256_bytes(&f32_bytes(&case.vector)), case.vector_sha256);
    assert_eq!(
        sha256_bytes(&f32_bytes(&case.expected)),
        case.expected_sha256
    );
}

fn assert_frozen_bounds_match(case: &StressCase, qualification: &TierBQualification) {
    for (index, row) in qualification.rows.iter().enumerate() {
        assert_close(row.l1_products, case.l1_products[index]);
        assert_close(row.absolute_bound, case.absolute_bounds[index]);
    }
    assert_close(qualification.rmse_bound, case.rmse_bound);
}

fn assert_close(actual: f64, expected: f64) {
    let scale = expected.abs().max(f64::MIN_POSITIVE);
    assert!((actual - expected).abs() <= scale * 1.0e-14);
}

fn production_matvec(
    context: &MlxContext,
    mut matrix_owner: Vec<f32>,
    mut vector_owner: Vec<f32>,
    shape: [usize; 2],
) -> (Vec<f32>, f64, f64) {
    let import_started = Instant::now();
    let matrix = context
        .import_f32_shaped(&mut matrix_owner, &shape)
        .unwrap();
    let vector = context
        .import_f32_shaped(&mut vector_owner, &[shape[1]])
        .unwrap();
    let import_seconds = import_started.elapsed().as_secs_f64();
    let compute_started = Instant::now();
    let result = matrix.matvec(&vector).unwrap();
    result.evaluate_sync().unwrap();
    let mut output = vec![0.0_f32; shape[0]];
    result.copy_f32(&mut output).unwrap();
    let compute_sync_seconds = compute_started.elapsed().as_secs_f64();
    result.destroy().unwrap();
    vector.destroy().unwrap();
    matrix.destroy().unwrap();
    (output, import_seconds, compute_sync_seconds)
}

fn argmax_lowest_index(values: &[f32]) -> usize {
    let mut best = 0;
    for index in 1..values.len() {
        if values[index] > values[best] {
            best = index;
        }
    }
    best
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
