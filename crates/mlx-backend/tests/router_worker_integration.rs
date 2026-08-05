#![cfg(all(target_os = "macos", target_arch = "aarch64"))]

use mlx_backend::router::{
    compare_router_outputs, RouterCaseScope, RouterOutput, RouterTolerancePolicy,
};
use mlx_backend::{
    CleanupOutcome, RouterRequest, RouterResult, WorkerClient, WorkerConfig, WorkerTimeouts,
    MODEL_FILE_DESCRIPTOR, ROUTER_TWO_ROW_CASE_ID,
};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::ffi::OsString;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::Duration;

const GOLDEN_RELATIVE_PATH: &str = "fixtures/research/router-v1/golden/expected_results.json";
const EXPECTED_RESULTS_FIXTURE_ID: &str = "generated-qwen3moe-router-expected-results-v1";

fn project_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .expect("workspace root must be an absolute existing directory")
}

fn worker_config(root: &Path) -> WorkerConfig {
    let python = root.join(".venv/bin/python");
    assert!(
        python.is_file(),
        "run `uv sync --frozen` before the ignored integration test"
    );
    let python_path = root
        .join("python")
        .canonicalize()
        .expect("worker source root must exist");

    WorkerConfig::new(
        python,
        vec![
            OsString::from("-u"),
            OsString::from("-m"),
            OsString::from("pulsar_mlx_worker"),
        ],
    )
    .with_current_dir(root)
    .with_env("PYTHONPATH", python_path.into_os_string())
    .with_env("PULSARMLX_MODEL_GGUF", "")
    .with_timeouts(WorkerTimeouts::new(
        Duration::from_secs(20),
        Duration::from_secs(20),
        Duration::from_secs(5),
    ))
}

fn golden_case(root: &Path) -> Value {
    let path = root.join(GOLDEN_RELATIVE_PATH);
    let document: Value = serde_json::from_slice(
        &fs::read(&path).unwrap_or_else(|error| panic!("read {}: {error}", path.display())),
    )
    .unwrap_or_else(|error| panic!("parse {}: {error}", path.display()));
    assert_eq!(
        document.get("schema").and_then(Value::as_str),
        Some("pulsarmlx.fixture.router-expected-results")
    );
    assert_eq!(
        document.get("schema_version").and_then(Value::as_str),
        Some("1.0.0")
    );
    assert_eq!(
        document.get("fixture_id").and_then(Value::as_str),
        Some(EXPECTED_RESULTS_FIXTURE_ID)
    );
    document
        .get("cases")
        .and_then(Value::as_object)
        .and_then(|cases| cases.get(ROUTER_TWO_ROW_CASE_ID))
        .cloned()
        .expect("golden two-row router case must exist")
}

fn f32_matrix(value: &Value, label: &str) -> Vec<Vec<f32>> {
    value
        .as_array()
        .unwrap_or_else(|| panic!("{label} must be a matrix"))
        .iter()
        .enumerate()
        .map(|(row_index, row)| {
            row.as_array()
                .unwrap_or_else(|| panic!("{label}[{row_index}] must be a row"))
                .iter()
                .enumerate()
                .map(|(column_index, value)| {
                    let wire = value.as_f64().unwrap_or_else(|| {
                        panic!("{label}[{row_index}][{column_index}] must be numeric")
                    });
                    let canonical = wire as f32;
                    assert!(
                        wire.is_finite() && canonical.is_finite(),
                        "{label}[{row_index}][{column_index}] must round to finite F32"
                    );
                    canonical
                })
                .collect()
        })
        .collect()
}

fn u64_matrix(value: &Value, label: &str) -> Vec<Vec<u64>> {
    value
        .as_array()
        .unwrap_or_else(|| panic!("{label} must be a matrix"))
        .iter()
        .enumerate()
        .map(|(row_index, row)| {
            row.as_array()
                .unwrap_or_else(|| panic!("{label}[{row_index}] must be a row"))
                .iter()
                .enumerate()
                .map(|(column_index, value)| {
                    value.as_u64().unwrap_or_else(|| {
                        panic!("{label}[{row_index}][{column_index}] must be an unsigned integer")
                    })
                })
                .collect()
        })
        .collect()
}

fn flatten(rows: &[Vec<f32>]) -> Vec<f32> {
    rows.iter().flatten().copied().collect()
}

fn output_from_golden(case: &Value) -> RouterOutput {
    let case_id = case
        .get("case_id")
        .and_then(Value::as_str)
        .expect("golden case ID")
        .to_owned();
    let logits = f32_matrix(&case["logits"], "golden logits");
    let probabilities = f32_matrix(
        &case["full_softmax_probabilities"],
        "golden full-softmax probabilities",
    );
    let selected_ids = u64_matrix(&case["selected_expert_ids"], "golden selected IDs");
    let selected = f32_matrix(
        &case["selected_probabilities"],
        "golden selected probabilities",
    );
    let normalized = f32_matrix(&case["normalized_weights"], "golden normalized weights");

    RouterOutput::try_new(
        case_id,
        RouterCaseScope::SyntheticFixture,
        logits.len(),
        flatten(&logits),
        flatten(&probabilities),
        selected_ids,
        selected,
        normalized,
    )
    .expect("committed golden router output must satisfy the Rust contract")
}

fn output_from_worker(result: &RouterResult) -> RouterOutput {
    let logits = result
        .logits()
        .iter()
        .flatten()
        .map(|value| *value as f32)
        .collect();
    let probabilities = result
        .full_probabilities()
        .iter()
        .flatten()
        .map(|value| *value as f32)
        .collect();
    let selected = result
        .selected_probabilities()
        .iter()
        .map(|row| row.iter().map(|value| *value as f32).collect())
        .collect();
    let normalized = result
        .normalized_weights()
        .iter()
        .map(|row| row.iter().map(|value| *value as f32).collect())
        .collect();

    RouterOutput::try_new(
        result.router_case_id(),
        RouterCaseScope::SyntheticFixture,
        usize::try_from(result.batch_size()).expect("bounded batch size fits usize"),
        logits,
        probabilities,
        result.selected_expert_ids().to_vec(),
        selected,
        normalized,
    )
    .expect("Rust-parsed worker output must satisfy the complete router contract")
}

fn sha256_f32_and_ids(output: &RouterOutput) -> (String, String) {
    let mut ids = Sha256::new();
    for expert_id in output.selected_expert_ids().iter().flatten() {
        let expert_id = u32::try_from(*expert_id).expect("bounded expert ID fits u32");
        ids.update(expert_id.to_le_bytes());
    }

    let mut bundle = Sha256::new();
    for value in output.logits() {
        bundle.update(value.to_le_bytes());
    }
    for value in output.full_probabilities() {
        bundle.update(value.to_le_bytes());
    }
    for value in output.selected_probabilities().iter().flatten() {
        bundle.update(value.to_le_bytes());
    }
    for value in output.normalized_weights().iter().flatten() {
        bundle.update(value.to_le_bytes());
    }

    (
        format!("{:x}", ids.finalize()),
        format!("{:x}", bundle.finalize()),
    )
}

fn golden_hash<'a>(case: &'a Value, name: &str) -> &'a str {
    case.get("hashes")
        .and_then(Value::as_object)
        .and_then(|hashes| hashes.get(name))
        .and_then(Value::as_str)
        .unwrap_or_else(|| panic!("golden hash {name} must exist"))
}

#[test]
#[ignore = "requires the pinned native Apple MLX environment; fixture is model-free"]
fn real_python_worker_two_row_router_matches_committed_golden() {
    assert!(
        std::env::var_os("PULSARMLX_MODEL_GGUF")
            .map(|value| value.is_empty())
            .unwrap_or(true),
        "the model path must be absent or empty for this model-free integration test"
    );
    let descriptor_status = unsafe { libc::fcntl(MODEL_FILE_DESCRIPTOR, libc::F_GETFD) };
    assert_eq!(
        descriptor_status, -1,
        "the model descriptor must be closed for this model-free integration test"
    );
    assert_eq!(
        std::io::Error::last_os_error().raw_os_error(),
        Some(libc::EBADF),
        "the descriptor check must fail because the descriptor is closed"
    );

    let root = project_root();
    let golden_case = golden_case(&root);
    let reference = output_from_golden(&golden_case);
    let request =
        RouterRequest::new(ROUTER_TWO_ROW_CASE_ID, "gpu").expect("committed router request");

    let mut client = WorkerClient::spawn(worker_config(&root)).expect("real MLX worker starts");
    let operations = client.hello().capabilities().operations().to_vec();
    let health = client.health().expect("real worker health succeeds");
    let result = client
        .run_router(&request)
        .expect("real worker completes the generated two-row router fixture");
    let cleanup = client.shutdown();

    assert_eq!(cleanup.outcome(), CleanupOutcome::Graceful);
    assert_eq!(cleanup.exit_code(), Some(0));
    assert!(health.ready());
    assert_eq!(
        operations.iter().map(String::as_str).collect::<Vec<_>>(),
        vec![
            "health",
            "tensor_probe",
            "run_fixture",
            "run_router",
            "run_synthetic_moe",
            "shutdown",
        ]
    );
    assert!(!operations
        .iter()
        .any(|operation| operation == "run_model_slice"));

    let candidate = output_from_worker(&result);
    let comparison = compare_router_outputs(
        &reference,
        &candidate,
        &RouterTolerancePolicy::contract_v1(),
    )
    .expect("golden and worker output identities are compatible");
    assert!(comparison.passed());
    assert_eq!(comparison.id_mismatch_count(), 0);
    assert_eq!(comparison.order_mismatch_count(), 0);
    for numeric in [
        comparison.logits(),
        comparison.full_probabilities(),
        comparison.selected_probabilities(),
        comparison.normalized_weights(),
    ] {
        assert_eq!(numeric.mismatch_count(), 0);
        assert!(numeric.first_mismatch().is_none());
    }

    assert_eq!(
        candidate.selected_expert_ids(),
        reference.selected_expert_ids()
    );
    assert_eq!(
        candidate.logits_f32le_sha256(),
        result.logits_f32le_sha256()
    );
    assert_eq!(
        candidate.full_probabilities_f32le_sha256(),
        result.full_probabilities_f32le_sha256()
    );
    assert_eq!(
        candidate.selected_probabilities_f32le_sha256(),
        result.selected_probabilities_f32le_sha256()
    );
    assert_eq!(
        candidate.normalized_weights_f32le_sha256(),
        result.normalized_weights_f32le_sha256()
    );

    assert_eq!(
        reference.logits_f32le_sha256(),
        golden_hash(&golden_case, "logits_f32le_sha256")
    );
    assert_eq!(
        reference.full_probabilities_f32le_sha256(),
        golden_hash(&golden_case, "full_softmax_probabilities_f32le_sha256")
    );
    assert_eq!(
        reference.selected_probabilities_f32le_sha256(),
        golden_hash(&golden_case, "selected_probabilities_f32le_sha256")
    );
    assert_eq!(
        reference.normalized_weights_f32le_sha256(),
        golden_hash(&golden_case, "normalized_weights_f32le_sha256")
    );

    let (reference_ids_sha256, reference_bundle_sha256) = sha256_f32_and_ids(&reference);
    let (candidate_ids_sha256, _) = sha256_f32_and_ids(&candidate);
    assert_eq!(
        reference_ids_sha256,
        golden_hash(&golden_case, "selected_expert_ids_u32le_sha256")
    );
    assert_eq!(candidate_ids_sha256, reference_ids_sha256);
    assert_eq!(
        reference_bundle_sha256,
        golden_hash(&golden_case, "float_output_bundle_f32le_sha256")
    );
    assert_eq!(
        candidate.logits_f32le_sha256(),
        reference.logits_f32le_sha256(),
        "the generated one-hot projection has an exact committed F32 logit identity"
    );
}
