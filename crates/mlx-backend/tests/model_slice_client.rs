use mlx_backend::{
    CleanupOutcome, ModelSliceRequest, WorkerClient, WorkerConfig, WorkerError, WorkerErrorKind,
    WorkerTimeouts, MODEL_FILE_DESCRIPTOR, MODEL_SLICE_ID,
};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::ffi::OsString;
use std::fs::{self, File, OpenOptions};
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

const WORKER_VERSION: &str = "fake-worker-v1";
const EXPECTED_ENCODED_SHA256: &str =
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const INHERITED_BYTES: &[u8] = b"bounded-model-fd";
const HELLO: &str = r#"{"protocol":1,"op":"hello","worker_version":"fake-worker-v1","python_version":"3.12.0","python_arch":"arm64","mlx_version":"0.32.0","macos_version":"15.0","metal_available":true,"gpu_count":1,"devices":[{"id":"gpu","kind":"gpu"}],"capabilities":{"operations":["health","run_model_slice","shutdown"],"dtypes":["float32","q8_0"]},"limits":{"max_request_bytes":65536,"max_response_bytes":1048576,"max_fixture_elements":4096}}"#;

static NEXT_ID: AtomicU64 = AtomicU64::new(0);

struct FakeWorker {
    directory: PathBuf,
    script: PathBuf,
    model: PathBuf,
}

impl FakeWorker {
    fn returning(result: &Value) -> Self {
        let sequence = NEXT_ID.fetch_add(1, Ordering::Relaxed);
        let directory = std::env::temp_dir().join(format!(
            "pulsarmlx-model-slice-client-{}-{sequence}",
            std::process::id()
        ));
        fs::create_dir(&directory).expect("create fake-worker directory");
        let script = directory.join("worker.py");
        let model = directory.join("external-model.bin");
        fs::write(&model, INHERITED_BYTES).expect("write bounded inherited file");
        let encoded = serde_json::to_string(result).expect("result is JSON");
        let source = format!(
            r#"import json
import os
import sys

MODEL_FD = {model_fd}
assert os.pread(MODEL_FD, {model_bytes}, 0) == {inherited:?}.encode("ascii")
print({hello:?}, flush=True)
RESULT = json.loads({encoded:?})
for line in sys.stdin:
    request = json.loads(line)
    request_id = request["request_id"]
    if request["op"] == "run_model_slice":
        expected = {{"slice_id": {slice_id:?}, "device": "gpu", "allow_fallback": False}}
        assert request["params"] == expected
        serialized = json.dumps(request["params"], separators=(",", ":"))
        for forbidden in ("path", "weight", "base64", "token", "prompt", "depth", "sha256"):
            assert forbidden not in serialized.lower()
        response = {{"protocol": 1, "request_id": request_id, "ok": True, "result": RESULT}}
        print(json.dumps(response, separators=(",", ":")), flush=True)
    elif request["op"] == "shutdown":
        response = {{"protocol": 1, "request_id": request_id, "ok": True, "result": {{"cleanup": "graceful"}}}}
        print(json.dumps(response, separators=(",", ":")), flush=True)
        sys.exit(0)
"#,
            model_fd = MODEL_FILE_DESCRIPTOR,
            model_bytes = INHERITED_BYTES.len(),
            inherited = std::str::from_utf8(INHERITED_BYTES).expect("ASCII fixture"),
            hello = HELLO,
            encoded = encoded,
            slice_id = MODEL_SLICE_ID,
        );
        fs::write(&script, source).expect("write fake worker");
        Self {
            directory,
            script,
            model,
        }
    }

    fn config(&self) -> WorkerConfig {
        let model = File::open(&self.model).expect("open inherited model fixture");
        self.config_with_model(model)
    }

    fn config_with_model(&self, model: File) -> WorkerConfig {
        WorkerConfig::new(
            PathBuf::from("python3"),
            vec![OsString::from("-u"), self.script.as_os_str().to_owned()],
        )
        .with_expected_worker_version(WORKER_VERSION)
        .with_timeouts(WorkerTimeouts::new(
            Duration::from_secs(2),
            Duration::from_millis(500),
            Duration::from_millis(250),
        ))
        .with_model_file(model)
    }
}

#[test]
fn inherited_model_descriptor_must_be_regular_and_read_only() {
    let worker = FakeWorker::returning(&valid_result());
    let writable = OpenOptions::new()
        .read(true)
        .write(true)
        .open(&worker.model)
        .expect("open writable model fixture");
    let error = match WorkerClient::spawn(worker.config_with_model(writable)) {
        Ok(_) => panic!("writable model descriptor must be rejected"),
        Err(error) => error,
    };
    assert_eq!(error.kind(), WorkerErrorKind::Spawn);
}

impl Drop for FakeWorker {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.script);
        let _ = fs::remove_file(&self.model);
        let _ = fs::remove_dir(&self.directory);
    }
}

fn output_sha256(values: &[f32]) -> String {
    let mut bytes = Vec::with_capacity(values.len() * 4);
    for value in values {
        bytes.extend_from_slice(&value.to_le_bytes());
    }
    format!("{:x}", Sha256::digest(bytes))
}

fn valid_result() -> Value {
    let actual = [0.0_f32; 16];
    json!({
        "slice_id": MODEL_SLICE_ID,
        "operation": "q8_0_expert_projection_matvec",
        "tensor_name": "blk.0.ffn_gate_exps.weight",
        "output_name": "blk0_ffn_gate_expert0_rows0_16_matvec",
        "requested_device": "gpu",
        "selected_device": "gpu",
        "fallback_used": false,
        "output_shape": [16],
        "output_dtype": "float32",
        "evaluated": true,
        "synchronized": true,
        "actual": actual,
        "encoded_slice_sha256": EXPECTED_ENCODED_SHA256,
        "decoded_slice_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "activation_sha256": "3821796e8415d1214890e0e2fc97cddbb9ec773f2e941203dac41c1c7b36a92e",
        "output_sha256": output_sha256(&actual),
        "memory_gauges": {
            "model_file_bytes": 32_483_931_648_u64,
            "mapped_virtual_bytes": 0,
            "mapped_resident_bytes": 0,
            "owned_compressed_bytes": 34_816,
            "decoded_array_bytes": 131_072,
            "activation_array_bytes": 8_192,
            "output_bytes": 64,
            "temporary_current_bytes": 135_168,
            "temporary_peak_bytes": 135_168,
            "mlx_active_bytes": 274_496,
            "mlx_cache_bytes": 0,
            "mlx_peak_bytes": 274_496,
            "process_footprint_bytes": 32_000_000,
            "process_footprint_source": "ps-rss",
            "process_physical_footprint_bytes": 31_000_000,
            "process_physical_footprint_peak_bytes": 33_000_000,
            "process_physical_footprint_source": "proc_pid_rusage:RUSAGE_INFO_V4",
            "system_pressure": "normal",
            "reported_summed_total_bytes": null
        }
    })
}

fn request() -> ModelSliceRequest {
    ModelSliceRequest::new(MODEL_SLICE_ID, "gpu").expect("frozen request")
}

fn run_result(result: &Value) -> Result<mlx_backend::ModelSliceResult, WorkerError> {
    let worker = FakeWorker::returning(result);
    let mut client = WorkerClient::spawn(worker.config()).expect("fake worker starts");
    client.run_model_slice(&request(), EXPECTED_ENCODED_SHA256)
}

#[test]
fn inherited_fd_and_control_only_request_produce_a_bounded_result() {
    assert!(ModelSliceRequest::new(MODEL_SLICE_ID, "cpu").is_err());
    assert!(ModelSliceRequest::new("other-slice", "gpu").is_err());

    let worker = FakeWorker::returning(&valid_result());
    let mut client = WorkerClient::spawn(worker.config()).expect("fake worker starts");
    let result = client
        .run_model_slice(&request(), EXPECTED_ENCODED_SHA256)
        .expect("valid model slice result");
    assert_eq!(result.slice_id(), MODEL_SLICE_ID);
    assert_eq!(result.actual(), &[0.0; 16]);
    assert!(result.evaluated() && result.synchronized());
    assert_eq!(
        result.memory_gauges().model_file_bytes(),
        Some(32_483_931_648)
    );
    assert_eq!(client.shutdown().outcome(), CleanupOutcome::Graceful);
}

#[test]
fn identity_completion_hash_and_output_contracts_are_enforced() {
    for (field, value) in [
        ("slice_id", json!("other-slice")),
        ("selected_device", json!("cpu")),
        ("fallback_used", json!(true)),
        ("evaluated", json!(false)),
        ("synchronized", json!(false)),
        ("output_shape", json!([8, 2])),
        ("encoded_slice_sha256", json!("c".repeat(64))),
        ("activation_sha256", json!("d".repeat(64))),
        ("output_sha256", json!("e".repeat(64))),
    ] {
        let mut result = valid_result();
        result[field] = value;
        assert_eq!(
            run_result(&result).expect_err("malformed result").kind(),
            WorkerErrorKind::Protocol
        );
    }
}

#[test]
fn overlapping_missing_or_over_budget_memory_evidence_is_rejected() {
    for (field, value) in [
        ("reported_summed_total_bytes", json!(1)),
        ("model_file_bytes", json!(1)),
        ("temporary_current_bytes", json!(1_073_741_825_u64)),
        ("mlx_active_bytes", Value::Null),
        ("mlx_peak_bytes", json!(5_000_000_000_u64)),
        ("process_physical_footprint_bytes", Value::Null),
        ("process_physical_footprint_bytes", json!(0)),
        (
            "process_physical_footprint_peak_bytes",
            json!(9_000_000_000_u64),
        ),
        ("system_pressure", json!("warning")),
    ] {
        let mut result = valid_result();
        result["memory_gauges"][field] = value;
        assert_eq!(
            run_result(&result)
                .expect_err("malformed memory evidence")
                .kind(),
            WorkerErrorKind::Protocol
        );
    }
}
