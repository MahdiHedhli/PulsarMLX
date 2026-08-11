#![cfg(all(target_os = "macos", pulsar_native_mlx))]

use f017_runner::json::{parse_json_no_duplicates, sha256_bytes, sha256_file};
use f017_runner::layer_qualification::{
    dsa_select_stable, run_r9_exact, run_r9_with_matvec, R9Error, R9Inputs, R9Matrices, R9Output,
    R9_SCAFFOLD_VERSION,
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
    oracle_generator_sha: String,
    exact_scaffold_version: &'static str,
    production_backend_version: &'static str,
    frozen_contract_version: String,
    numerical_mode: &'static str,
    deterministic_repeat_count: usize,
    boundaries: BTreeMap<String, NumericalMetrics>,
    per_matvec: Vec<MatvecReport>,
    dsa: DsaReport,
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
struct DsaReport {
    mode: &'static str,
    selected_positions: Vec<usize>,
    synthetic_indexer_selected_positions: Vec<usize>,
    exact: bool,
}

#[derive(Default, Serialize)]
struct Timings {
    exact_scaffold_seconds: f64,
    production_import_seconds: f64,
    production_compute_sync_seconds: f64,
    production_total_seconds: f64,
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
    reconciled: bool,
}

#[test]
fn checkpoint_free_r9_production_mlx_qualifies_fail_closed() {
    let total_started = Instant::now();
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let fixture_path = root
        .join("specs/017-rust-native-inference-runtime/fixtures/f017-r9-mla-dsa-oracle-v1.json");
    let contract_path =
        root.join("specs/017-rust-native-inference-runtime/contracts/production-r9-tier-b-v2.json");
    let fixture_bytes = fs::read(&fixture_path).unwrap();
    let contract_bytes = fs::read(&contract_path).unwrap();
    let oracle: Value = parse_json_no_duplicates(&fixture_bytes).unwrap();
    let contract: Value = parse_json_no_duplicates(&contract_bytes).unwrap();
    assert_eq!(
        contract["status"],
        "reviewed_semantic_tightening_of_frozen_v1"
    );
    assert_eq!(contract["required_repeats"], REPEATS);
    assert_eq!(
        oracle["numerical_contract"]["deterministic_repeats"],
        REPEATS
    );
    assert_eq!(oracle["checkpoint_accessed"], false);
    assert_eq!(
        sha256_file(&root.join(oracle["generator_path"].as_str().unwrap())).unwrap(),
        oracle["generator_sha256"]
    );

    let matrices = matrices(&oracle);
    let inputs = inputs(&oracle);
    let mut timings = Timings::default();
    let exact_started = Instant::now();
    let exact = run_r9_exact(&matrices, &inputs).unwrap();
    timings.exact_scaffold_seconds = exact_started.elapsed().as_secs_f64();
    assert_fixture_boundaries(&oracle, &exact);

    let streams_before = MlxContext::debug_stream_counters().unwrap();
    assert!(!MlxContext::debug_context_active());
    let context = MlxContext::new(MlxDevice::Gpu, MlxStreamMode::Owned).unwrap();
    let mut first: Option<R9Output> = None;
    let mut first_matvec_reports = Vec::new();
    let production_started = Instant::now();
    for repeat in 0..REPEATS {
        let mut reports = Vec::new();
        let candidate =
            run_r9_with_matvec(&matrices, &inputs, |matrix, rows, columns, vector, role| {
                let mut expected = vec![0.0_f32; rows];
                exact_matvec_f32(matrix, rows, columns, vector, &mut expected)
                    .map_err(R9Error::Matvec)?;
                let actual =
                    production_matvec(&context, matrix, rows, columns, vector, &mut timings)?;
                let qualification =
                    qualify_tier_b_down(matrix, rows, columns, vector, &expected, &actual)
                        .map_err(R9Error::Matvec)?;
                assert!(qualification.passes, "native matvec failed Tier-B: {role}");
                reports.push(MatvecReport {
                    role: role.to_owned(),
                    qualification,
                });
                Ok(actual)
            })
            .unwrap();
        assert_eq!(reports.len(), 6);
        if let Some(first) = &first {
            assert_r9_bits(first, &candidate);
        } else {
            first = Some(candidate);
            first_matvec_reports = reports;
        }
        assert!(repeat < REPEATS);
    }
    timings.production_total_seconds = production_started.elapsed().as_secs_f64();
    let candidate = first.unwrap();
    assert_eq!(candidate.selected_positions, exact.selected_positions);

    let boundaries = measure_boundaries(&exact, &candidate);
    for (name, metrics) in &boundaries {
        let limit = if name == "output" {
            &contract["final"]
        } else {
            &contract["intermediate"]
        };
        assert_eq!(metrics.non_finite_count, 0, "{name} non-finite");
        assert_eq!(metrics.signed_zero_mismatch_count, 0, "{name} signed-zero");
        assert!(
            metrics.max_abs_error <= limit["max_absolute_error"].as_f64().unwrap(),
            "{name} max abs"
        );
        assert!(
            metrics.rmse <= limit["rmse"].as_f64().unwrap(),
            "{name} rmse"
        );
        if let Some(cosine) = metrics.cosine_similarity {
            assert!(
                cosine >= limit["cosine_similarity_minimum"].as_f64().unwrap(),
                "{name} cosine"
            );
        }
    }
    let dsa_scores = record(&oracle["dsa_indexer_fixture"]["scores"]);
    let dsa_mask = oracle["dsa_indexer_fixture"]["visible_mask"]
        .as_array()
        .unwrap()
        .iter()
        .map(|value| value.as_bool().unwrap())
        .collect::<Vec<_>>();
    let synthetic_dsa = dsa_select_stable(
        &dsa_scores,
        &dsa_mask,
        oracle["dsa_indexer_fixture"]["top_k"].as_u64().unwrap() as usize,
    )
    .unwrap();
    let expected_dsa = usize_values(&oracle["dsa_indexer_fixture"]["selected_positions"]);
    assert_eq!(synthetic_dsa, expected_dsa);

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
    let all_exact = boundaries
        .values()
        .all(|metrics| metrics.bit_mismatch_count == 0);
    let report = Report {
        schema: "pulsarmlx.f017.r9-production-result",
        schema_version: "1.0.0",
        source_commit: clean_source_commit(&root),
        fixture_version: oracle["fixture_version"].as_str().unwrap().to_owned(),
        fixture_sha256: sha256_bytes(&fixture_bytes),
        oracle_generator_sha: oracle["generator_sha256"].as_str().unwrap().to_owned(),
        exact_scaffold_version: R9_SCAFFOLD_VERSION,
        production_backend_version: "mlx-native-0.31.2-mlxc-0.6.0-production-adapter",
        frozen_contract_version: contract["contract_version"].as_str().unwrap().to_owned(),
        numerical_mode: "production_mlx_tier_b",
        deterministic_repeat_count: REPEATS,
        boundaries,
        per_matvec: first_matvec_reports,
        dsa: DsaReport {
            mode: "range_fill",
            selected_positions: candidate.selected_positions,
            synthetic_indexer_selected_positions: synthetic_dsa,
            exact: true,
        },
        classification: if all_exact {
            NumericalClassification::GoldenIdentical
        } else {
            NumericalClassification::NumericallyQualifiedGreedyNotApplicable
        },
        greedy_applicability: GreedyApplicability::NotApplicable,
        direct_native_dispatch_count: (REPEATS * 6) as u64,
        qualification_scaffold_dispatch_count: (REPEATS * 6 + 6) as u64,
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
            reconciled: lifecycle_reconciled,
        },
        review_status: "pending_adversarial_numerical_review",
        checkpoint_accessed: false,
    };
    assert!(total_started.elapsed().as_secs_f64() >= report.timings.production_total_seconds);
    if let Ok(path) = std::env::var("PULSAR_F017_R9_EVIDENCE_OUT") {
        fs::write(path, serde_json::to_string_pretty(&report).unwrap() + "\n").unwrap();
    }
    println!(
        "F017_R9_RESULT_JSON={}",
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
) -> Result<Vec<f32>, R9Error> {
    let import_started = Instant::now();
    let mut matrix_owner = matrix.to_vec();
    let mut vector_owner = vector.to_vec();
    let matrix_array = context
        .import_f32_shaped(&mut matrix_owner, &[rows, columns])
        .map_err(|_| R9Error::CandidateMatvec("import matrix"))?;
    let vector_array = context
        .import_f32_shaped(&mut vector_owner, &[columns])
        .map_err(|_| R9Error::CandidateMatvec("import vector"))?;
    timings.production_import_seconds += import_started.elapsed().as_secs_f64();
    let compute_started = Instant::now();
    let result = matrix_array
        .matvec(&vector_array)
        .map_err(|_| R9Error::CandidateMatvec("dispatch"))?;
    result
        .evaluate_sync()
        .map_err(|_| R9Error::CandidateMatvec("evaluate/sync"))?;
    let mut output = vec![0.0_f32; rows];
    result
        .copy_f32(&mut output)
        .map_err(|_| R9Error::CandidateMatvec("copy"))?;
    timings.production_compute_sync_seconds += compute_started.elapsed().as_secs_f64();
    result
        .destroy()
        .map_err(|_| R9Error::CandidateMatvec("destroy result"))?;
    vector_array
        .destroy()
        .map_err(|_| R9Error::CandidateMatvec("destroy vector"))?;
    matrix_array
        .destroy()
        .map_err(|_| R9Error::CandidateMatvec("destroy matrix"))?;
    Ok(output)
}

fn matrices(value: &Value) -> R9Matrices {
    R9Matrices {
        q_a: matrix(&value["matrices"]["attn_q_a"]),
        q_b: matrix(&value["matrices"]["attn_q_b"]),
        kv_a: matrix(&value["matrices"]["attn_kv_a_mqa"]),
        k_b: matrix(&value["matrices"]["attn_k_b"]),
        v_b: matrix(&value["matrices"]["attn_v_b"]),
        output: matrix(&value["matrices"]["attn_output"]),
    }
}

fn inputs(value: &Value) -> R9Inputs {
    R9Inputs {
        residual: record(&value["inputs"]["residual"]),
        attn_norm_scale: record(&value["inputs"]["attn_norm_scale"]),
        q_norm_scale: record(&value["inputs"]["q_norm_scale"]),
        kv_norm_scale: record(&value["inputs"]["kv_norm_scale"]),
        prior_cache_latents: record(&value["inputs"]["prior_cache_latents"]),
        prior_cache_ropes: record(&value["inputs"]["prior_cache_ropes"]),
        q_rope_cosine: record(&value["inputs"]["q_rope_cosine"]),
        q_rope_sine: record(&value["inputs"]["q_rope_sine"]),
        rms_epsilon: value["inputs"]["rms_epsilon"].as_f64().unwrap() as f32,
        attention_scale: value["inputs"]["attention_scale"].as_f64().unwrap() as f32,
        query_position: value["architecture"]["query_position"].as_u64().unwrap() as usize,
        visible_positions: value["architecture"]["visible_positions"].as_u64().unwrap() as usize,
    }
}

fn assert_fixture_boundaries(value: &Value, output: &R9Output) {
    for (name, actual) in output_boundaries(output) {
        assert_bits(name, actual, &record(&value["expected"][name]));
    }
}

fn measure_boundaries(
    expected: &R9Output,
    actual: &R9Output,
) -> BTreeMap<String, NumericalMetrics> {
    let actual = output_boundaries(actual)
        .into_iter()
        .collect::<BTreeMap<_, _>>();
    output_boundaries(expected)
        .into_iter()
        .map(|(name, expected)| {
            (
                name.to_owned(),
                measure_f32(expected, actual[name]).unwrap(),
            )
        })
        .collect()
}

fn output_boundaries(output: &R9Output) -> Vec<(&'static str, &[f32])> {
    vec![
        ("x_norm", &output.x_norm),
        ("q_rank", &output.q_rank),
        ("q_rank_norm", &output.q_rank_norm),
        ("q_flat", &output.q_flat),
        ("q_nope", &output.q_nope),
        ("q_rope", &output.q_rope),
        ("kv_raw", &output.kv_raw),
        ("kv_norm", &output.kv_norm),
        ("current_k_rope", &output.current_k_rope),
        ("qk_low", &output.qk_low),
        ("rotated_keys", &output.rotated_keys),
        ("attention_scores", &output.attention_scores),
        ("attention_probabilities", &output.attention_probabilities),
        ("latent_sum", &output.latent_sum),
        ("value", &output.value),
        ("projected", &output.projected),
        ("output", &output.output),
    ]
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

fn record(value: &Value) -> Vec<f32> {
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

fn assert_r9_bits(expected: &R9Output, actual: &R9Output) {
    for ((name, expected), (_, actual)) in output_boundaries(expected)
        .into_iter()
        .zip(output_boundaries(actual))
    {
        assert_bits(name, expected, actual);
    }
    assert_eq!(expected.selected_positions, actual.selected_positions);
}

fn assert_bits(name: &str, expected: &[f32], actual: &[f32]) {
    assert_eq!(expected.len(), actual.len(), "{name} length");
    for (index, (&expected, &actual)) in expected.iter().zip(actual).enumerate() {
        assert_eq!(expected.to_bits(), actual.to_bits(), "{name}[{index}]");
    }
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
            "R9 evidence requires a clean source tree"
        );
        assert!(std::env::var_os("PULSAR_F017_R9_EVIDENCE_OUT").is_none());
    }
    let output = Command::new("git")
        .args(["rev-parse", "HEAD"])
        .current_dir(root)
        .output()
        .unwrap();
    assert!(output.status.success());
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
