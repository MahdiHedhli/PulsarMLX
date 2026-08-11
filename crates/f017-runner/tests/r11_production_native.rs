#![cfg(all(target_os = "macos", pulsar_native_mlx))]

use f017_runner::final_output_qualification::{
    decode_q4_k_matrix, run_r11_exact, run_r11_with_decoded_matvec, R11Error, R11Inputs, R11Output,
    R11_SCAFFOLD_VERSION,
};
use f017_runner::json::{parse_json_no_duplicates, sha256_bytes, sha256_file};
use f017_runner::numerical_classification::{GreedyApplicability, NumericalClassification};
use f017_runner::qualification::{qualify_tier_b_down, TierBQualification};
use serde::Serialize;
use serde_json::Value;
use std::fs;
use std::path::Path;
use std::process::Command;
use std::time::Instant;
use stream::{MlxContext, MlxDevice, MlxStreamMode};

const REPEATS: usize = 10;

#[derive(Default, Serialize)]
struct Timings {
    exact_scaffold_seconds: f64,
    q4_k_decode_seconds: f64,
    production_total_seconds: f64,
    backend_import_seconds: f64,
    output_head_compute_sync_seconds: f64,
    readback_seconds: f64,
    rms_norm_topk_orchestration_seconds: f64,
    per_repeat_total_seconds: Vec<f64>,
    first_use_seconds: f64,
    warm_median_seconds: f64,
    warm_min_seconds: f64,
    warm_max_seconds: f64,
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

#[derive(Serialize)]
struct Report {
    schema: &'static str,
    schema_version: &'static str,
    source_commit: String,
    fixture_version: String,
    fixture_sha256: String,
    oracle_generator_sha: String,
    exact_scaffold_version: &'static str,
    frozen_contract_versions: Vec<String>,
    production_backend_version: &'static str,
    numerical_mode: &'static str,
    deterministic_repeat_count: usize,
    logit_qualification: TierBQualification,
    top_k_ids: Vec<usize>,
    top_k_score_deltas: Vec<f64>,
    argmax: usize,
    top1_top2_margin: f64,
    classification: NumericalClassification,
    greedy_applicability: GreedyApplicability,
    top_k_ids_exact: bool,
    argmax_exact: bool,
    direct_native_dispatch_count: u64,
    qualification_scaffold_dispatch_count: u64,
    explicit_reference_dispatch_count: u64,
    unexpected_fallback_count: u64,
    backend_error_count: u64,
    materialized_f32_elements: usize,
    packed_q4_k_bytes: usize,
    timings: Timings,
    lifecycle: Lifecycle,
    review_status: &'static str,
    checkpoint_accessed: bool,
}

#[test]
fn checkpoint_free_r11_final_output_qualifies_with_exact_greedy_identity() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let fixture_path = root.join(
        "specs/017-rust-native-inference-runtime/fixtures/f017-r11-final-output-oracle-v1.json",
    );
    let contract_path = root
        .join("specs/017-rust-native-inference-runtime/contracts/production-r11-tier-b-v1.json");
    let fixture_bytes = fs::read(&fixture_path).unwrap();
    let contract_bytes = fs::read(&contract_path).unwrap();
    let oracle: Value = parse_json_no_duplicates(&fixture_bytes).unwrap();
    let contract: Value = parse_json_no_duplicates(&contract_bytes).unwrap();
    assert_eq!(
        contract["status"],
        "frozen_before_production_candidate_execution"
    );
    assert_eq!(contract["required_repeats"], REPEATS);
    assert_eq!(contract["greedy_applicability"], "applicable");
    assert_eq!(oracle["checkpoint_accessed"], false);
    assert_eq!(
        sha256_file(&root.join(oracle["generator_path"].as_str().unwrap())).unwrap(),
        oracle["generator_sha256"]
    );

    let inputs = load_inputs(&oracle);
    let exact_started = Instant::now();
    let exact = run_r11_exact(&inputs).unwrap();
    let exact_seconds = exact_started.elapsed().as_secs_f64();
    assert_expected(&oracle, &exact);

    let streams_before = MlxContext::debug_stream_counters().unwrap();
    assert!(!MlxContext::debug_context_active());
    let context = MlxContext::new(MlxDevice::Gpu, MlxStreamMode::Owned).unwrap();
    let mut timings = Timings {
        exact_scaffold_seconds: exact_seconds,
        ..Timings::default()
    };
    let mut first: Option<R11Output> = None;
    for _ in 0..REPEATS {
        let repeat_started = Instant::now();
        let decode_started = Instant::now();
        let decoded = decode_q4_k_matrix(
            &inputs.output_head_packed,
            inputs.output_rows,
            inputs.output_columns,
        )
        .unwrap();
        timings.q4_k_decode_seconds += decode_started.elapsed().as_secs_f64();
        let candidate = run_r11_with_decoded_matvec(
            &inputs,
            decoded,
            |matrix, rows, columns, vector, _role| {
                production_matvec(&context, matrix, rows, columns, vector, &mut timings)
            },
        )
        .unwrap();
        timings
            .per_repeat_total_seconds
            .push(repeat_started.elapsed().as_secs_f64());
        if let Some(first) = &first {
            assert_output_bits(first, &candidate);
        } else {
            first = Some(candidate);
        }
    }
    timings.production_total_seconds = timings.per_repeat_total_seconds.iter().sum();
    timings.rms_norm_topk_orchestration_seconds = (timings.production_total_seconds
        - timings.q4_k_decode_seconds
        - timings.backend_import_seconds
        - timings.output_head_compute_sync_seconds
        - timings.readback_seconds)
        .max(0.0);
    timings.first_use_seconds = timings.per_repeat_total_seconds[0];
    let mut warm = timings.per_repeat_total_seconds[1..].to_vec();
    warm.sort_by(f64::total_cmp);
    timings.warm_median_seconds = warm[warm.len() / 2];
    timings.warm_min_seconds = warm[0];
    timings.warm_max_seconds = warm[warm.len() - 1];

    let candidate = first.unwrap();
    let logit_qualification = qualify_tier_b_down(
        &exact.decoded_output_head,
        inputs.output_rows,
        inputs.output_columns,
        &exact.normalized,
        &exact.logits,
        &candidate.logits,
    )
    .unwrap();
    assert!(logit_qualification.passes);
    let top_k_ids_exact = candidate.top_k_ids == exact.top_k_ids;
    let argmax_exact = candidate.argmax == exact.argmax;
    assert!(top_k_ids_exact);
    assert!(argmax_exact);
    let top_k_score_deltas = candidate
        .top_k_scores
        .iter()
        .zip(exact.top_k_scores.iter())
        .map(|(actual, expected)| f64::from(*actual) - f64::from(*expected))
        .collect::<Vec<_>>();

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

    let all_exact = logit_qualification.metrics.bit_mismatch_count == 0;
    let report = Report {
        schema: "pulsarmlx.f017.r11-production-result",
        schema_version: "1.0.0",
        source_commit: clean_source_commit(&root),
        fixture_version: oracle["fixture_version"].as_str().unwrap().to_owned(),
        fixture_sha256: sha256_bytes(&fixture_bytes),
        oracle_generator_sha: oracle["generator_sha256"].as_str().unwrap().to_owned(),
        exact_scaffold_version: R11_SCAFFOLD_VERSION,
        frozen_contract_versions: vec![
            "f017-production-expert-tier-b-v1".to_owned(),
            "f017-production-r9-tier-b-v2".to_owned(),
            "f017-production-r10-tier-b-v2".to_owned(),
            contract["contract_version"].as_str().unwrap().to_owned(),
        ],
        production_backend_version: "mlx-native-0.31.2-mlxc-0.6.0-production-adapter",
        numerical_mode: "production_mlx_tier_b",
        deterministic_repeat_count: REPEATS,
        logit_qualification,
        top_k_ids: candidate.top_k_ids,
        top_k_score_deltas,
        argmax: candidate.argmax,
        top1_top2_margin: f64::from(candidate.top_k_scores[0] - candidate.top_k_scores[1]),
        classification: if all_exact {
            NumericalClassification::GoldenIdentical
        } else {
            NumericalClassification::NumericallyQualifiedGreedyIdentical
        },
        greedy_applicability: GreedyApplicability::Applicable,
        top_k_ids_exact,
        argmax_exact,
        direct_native_dispatch_count: REPEATS as u64,
        qualification_scaffold_dispatch_count: 1,
        explicit_reference_dispatch_count: 0,
        unexpected_fallback_count: 0,
        backend_error_count: 0,
        materialized_f32_elements: exact.decoded_output_head.len(),
        packed_q4_k_bytes: inputs.output_head_packed.len(),
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
        review_status: "pending_adversarial_canonical_runner_review",
        checkpoint_accessed: false,
    };
    if let Ok(path) = std::env::var("PULSAR_F017_R11_EVIDENCE_OUT") {
        fs::write(path, serde_json::to_string_pretty(&report).unwrap() + "\n").unwrap();
    }
    println!(
        "F017_R11_RESULT_JSON={}",
        serde_json::to_string(&report).unwrap()
    );
}

fn production_matvec(
    context: &MlxContext,
    matrix: &[f32],
    rows: usize,
    columns: usize,
    vector: &[f32],
    timings: &mut Timings,
) -> Result<Vec<f32>, R11Error> {
    let import_started = Instant::now();
    let mut matrix_owner = matrix.to_vec();
    let mut vector_owner = vector.to_vec();
    let matrix_array = context
        .import_f32_shaped(&mut matrix_owner, &[rows, columns])
        .map_err(|_| R11Error::CandidateMatvec("output_head_import"))?;
    let vector_array = context
        .import_f32_shaped(&mut vector_owner, &[columns])
        .map_err(|_| R11Error::CandidateMatvec("final_hidden_import"))?;
    timings.backend_import_seconds += import_started.elapsed().as_secs_f64();
    let compute_started = Instant::now();
    let result = matrix_array
        .matvec(&vector_array)
        .map_err(|_| R11Error::CandidateMatvec("output_head_dispatch"))?;
    result
        .evaluate_sync()
        .map_err(|_| R11Error::CandidateMatvec("output_head_sync"))?;
    timings.output_head_compute_sync_seconds += compute_started.elapsed().as_secs_f64();
    let readback_started = Instant::now();
    let mut output = vec![0.0_f32; rows];
    result
        .copy_f32(&mut output)
        .map_err(|_| R11Error::CandidateMatvec("output_head_readback"))?;
    timings.readback_seconds += readback_started.elapsed().as_secs_f64();
    result
        .destroy()
        .map_err(|_| R11Error::CandidateMatvec("output_head_destroy"))?;
    vector_array
        .destroy()
        .map_err(|_| R11Error::CandidateMatvec("vector_destroy"))?;
    matrix_array
        .destroy()
        .map_err(|_| R11Error::CandidateMatvec("matrix_destroy"))?;
    Ok(output)
}

fn load_inputs(oracle: &Value) -> R11Inputs {
    let head = &oracle["inputs"]["output_head"];
    let shape = usize_values(&head["shape"]);
    R11Inputs {
        final_hidden: f32_record(&oracle["inputs"]["final_hidden"]),
        output_norm_scale: f32_record(&oracle["inputs"]["output_norm_scale"]),
        rms_epsilon: oracle["inputs"]["rms_epsilon"].as_f64().unwrap() as f32,
        output_head_packed: decode_hex(head["packed_hex"].as_str().unwrap()),
        output_rows: shape[0],
        output_columns: shape[1],
        top_k: oracle["architecture"]["top_k"].as_u64().unwrap() as usize,
    }
}

fn assert_expected(oracle: &Value, output: &R11Output) {
    assert_bits(
        &output.normalized,
        &f32_record(&oracle["expected"]["final_normalized"]),
    );
    assert_bits(&output.logits, &f32_record(&oracle["expected"]["logits"]));
    assert_eq!(
        output.top_k_ids,
        usize_values(&oracle["expected"]["top_k_ids"])
    );
    assert_eq!(
        output.argmax,
        oracle["expected"]["argmax"].as_u64().unwrap() as usize
    );
}

fn assert_output_bits(left: &R11Output, right: &R11Output) {
    assert_bits(&left.normalized, &right.normalized);
    assert_bits(&left.logits, &right.logits);
    assert_eq!(left.top_k_ids, right.top_k_ids);
    assert_eq!(left.argmax, right.argmax);
}

fn f32_record(value: &Value) -> Vec<f32> {
    decode_hex(value["f32_le_hex"].as_str().unwrap())
        .chunks_exact(4)
        .map(|bytes| f32::from_le_bytes(bytes.try_into().unwrap()))
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

fn decode_hex(encoded: &str) -> Vec<u8> {
    encoded
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
        .collect()
}

fn assert_bits(left: &[f32], right: &[f32]) {
    assert_eq!(
        left.iter().map(|value| value.to_bits()).collect::<Vec<_>>(),
        right
            .iter()
            .map(|value| value.to_bits())
            .collect::<Vec<_>>()
    );
}

fn clean_source_commit(root: &Path) -> String {
    let output = Command::new("git")
        .args(["-C", root.to_str().unwrap(), "rev-parse", "HEAD"])
        .output()
        .unwrap();
    assert!(output.status.success());
    String::from_utf8(output.stdout).unwrap().trim().to_owned()
}
