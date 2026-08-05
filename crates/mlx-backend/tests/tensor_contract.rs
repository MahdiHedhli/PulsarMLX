use mlx_backend::{
    CleanupOutcome, TensorFixtureRequest, WorkerClient, WorkerConfig, WorkerError, WorkerErrorKind,
    WorkerTimeouts,
};
use serde_json::{json, Value};
use std::ffi::OsString;
use std::fs;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

const FIXTURE_SET_ID: &str = "mlx-tensor-fixtures-v1";
const CASE_ID: &str = "matmul-nonsymmetric-f32-v1";
const OPERATION: &str = "matmul";
const DEVICE: &str = "gpu";
const WORKER_VERSION: &str = "fake-worker-v1";
const MLX_VERSION: &str = "0.32.0";
const MAX_FIXTURE_ELEMENTS: usize = 4096;
const HELLO: &str = r#"{"protocol":1,"op":"hello","worker_version":"fake-worker-v1","python_version":"3.12.0","python_arch":"arm64","mlx_version":"0.32.0","macos_version":"15.0","metal_available":true,"gpu_count":1,"devices":[{"id":"gpu","kind":"gpu"}],"capabilities":{"operations":["health","run_fixture","shutdown"],"dtypes":["float32","q8_0"]},"limits":{"max_request_bytes":65536,"max_response_bytes":1048576,"max_fixture_elements":4096}}"#;

static NEXT_TEMP_ID: AtomicU64 = AtomicU64::new(0);

struct FakeWorker {
    directory: PathBuf,
    script: PathBuf,
}

impl FakeWorker {
    fn returning(result_json: impl AsRef<str>) -> Self {
        let sequence = NEXT_TEMP_ID.fetch_add(1, Ordering::Relaxed);
        let directory = std::env::temp_dir().join(format!(
            "pulsarmlx-tensor-contract-{}-{sequence}",
            std::process::id()
        ));
        fs::create_dir(&directory).expect("create isolated fake-worker directory");
        let script = directory.join("worker.py");
        let source = worker_script(result_json.as_ref());
        assert!(
            source.len() <= 256 * 1024,
            "fake worker must remain bounded"
        );
        fs::write(&script, source).expect("write bounded fake-worker script");
        Self { directory, script }
    }

    fn config(&self) -> WorkerConfig {
        WorkerConfig::new(
            PathBuf::from("python3"),
            vec![OsString::from("-u"), self.script.as_os_str().to_owned()],
        )
        .with_expected_protocol(1)
        .with_expected_worker_version(WORKER_VERSION)
        .with_expected_mlx_version(MLX_VERSION)
        .with_timeouts(WorkerTimeouts::new(
            Duration::from_secs(2),
            Duration::from_millis(500),
            Duration::from_millis(250),
        ))
    }
}

impl Drop for FakeWorker {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.script);
        let _ = fs::remove_dir(&self.directory);
    }
}

fn worker_script(result_json: &str) -> String {
    format!(
        r#"import json
import sys

HELLO = {hello:?}
RESULT = json.loads({result_json:?})
print(HELLO, flush=True)

def success(request_id, result):
    print(json.dumps({{"protocol": 1, "request_id": request_id, "ok": True, "result": result}}, separators=(",", ":")), flush=True)

def failure(request_id, code, message):
    print(json.dumps({{"protocol": 1, "request_id": request_id, "ok": False, "error": {{"code": code, "message": message, "retryable": False, "details": {{}}}}}}, separators=(",", ":")), flush=True)

for line in sys.stdin:
    request = json.loads(line)
    request_id = request["request_id"]
    if request["op"] == "run_fixture":
        expected_params = {{
            "fixture_set_id": {fixture_set_id:?},
            "case_id": {case_id:?},
            "device": {device:?},
            "allow_fallback": False,
        }}
        if request["params"] != expected_params:
            failure(request_id, "malformed_request", "run_fixture parameters violated the bounded schema")
        else:
            success(request_id, RESULT)
    elif request["op"] == "shutdown":
        success(request_id, {{"cleanup": "graceful"}})
        sys.exit(0)
    else:
        failure(request_id, "unsupported_operation", "operation is not supported by the fake worker")
"#,
        hello = HELLO,
        result_json = result_json,
        fixture_set_id = FIXTURE_SET_ID,
        case_id = CASE_ID,
        device = DEVICE,
    )
}

fn request() -> TensorFixtureRequest {
    TensorFixtureRequest::new(FIXTURE_SET_ID, CASE_ID, OPERATION, DEVICE)
        .expect("the frozen fixture request is valid")
}

fn valid_result() -> Value {
    json!({
        "fixture_set_id": FIXTURE_SET_ID,
        "case_id": CASE_ID,
        "operation": OPERATION,
        "backend_id": "apple-mlx",
        "requested_device": DEVICE,
        "selected_device": DEVICE,
        "fallback_used": false,
        "output_shape": [2, 2],
        "input_dtype": "float32",
        "accumulation_dtype": "float32",
        "output_dtype": "float32",
        "evaluated": true,
        "synchronized": true,
        "actual": [58.0, 64.0, 139.0, 154.0],
        "comparison": {
            "oracle_id": "committed-independent-scalar-v1",
            "mode": "abs_rel",
            "absolute_tolerance": 0.00001,
            "relative_tolerance": 0.00001,
            "non_finite_policy": "reject",
            "compared_count": 4,
            "max_absolute_error": 0.0,
            "max_relative_error": 0.0,
            "first_mismatch_index": null,
            "passed": true
        },
        "memory_gauges": {
            "mlx_active_bytes": 64,
            "mlx_cache_bytes": 0,
            "mlx_peak_bytes": 128,
            "process_footprint_bytes": 16777216,
            "process_footprint_source": "ps-rss",
            "system_pressure": "normal",
            "reported_summed_total_bytes": null
        },
        "passed": true
    })
}

fn run_result(result: &Value) -> Result<mlx_backend::TensorFixtureResult, WorkerError> {
    let worker = FakeWorker::returning(
        serde_json::to_string(result).expect("test result must be JSON serializable"),
    );
    let mut client = WorkerClient::spawn(worker.config()).expect("valid fake worker starts");
    client.run_fixture(&request())
}

fn assert_protocol_rejection(result: Value, context: &str) {
    let error = run_result(&result).expect_err(context);
    assert_eq!(
        error.kind(),
        WorkerErrorKind::Protocol,
        "{context}: unexpected error: {error}"
    );
}

#[test]
fn fixture_requests_are_bounded_identifiers_without_tensor_payloads() {
    let request = request();
    assert_eq!(request.fixture_set_id(), FIXTURE_SET_ID);
    assert_eq!(request.case_id(), CASE_ID);
    assert_eq!(request.operation(), OPERATION);
    assert_eq!(request.device(), DEVICE);
    assert!(!request.allow_fallback());

    for invalid in ["", " whitespace "] {
        assert!(TensorFixtureRequest::new(invalid, CASE_ID, OPERATION, DEVICE).is_err());
        assert!(TensorFixtureRequest::new(FIXTURE_SET_ID, invalid, OPERATION, DEVICE).is_err());
        assert!(TensorFixtureRequest::new(FIXTURE_SET_ID, CASE_ID, invalid, DEVICE).is_err());
    }

    let oversized = "x".repeat(129);
    assert!(TensorFixtureRequest::new(&oversized, CASE_ID, OPERATION, DEVICE).is_err());
    assert!(TensorFixtureRequest::new(FIXTURE_SET_ID, &oversized, OPERATION, DEVICE).is_err());
    assert!(TensorFixtureRequest::new(FIXTURE_SET_ID, CASE_ID, &oversized, DEVICE).is_err());
    assert!(TensorFixtureRequest::new(FIXTURE_SET_ID, CASE_ID, OPERATION, "cpu").is_err());

    // The fake worker accepts only the four scalar control fields. A passing
    // response therefore proves the Rust request did not transfer numeric
    // tensor/weight lists, encoded bytes, or a base64 payload over NDJSON.
    let worker = FakeWorker::returning(
        serde_json::to_string(&valid_result()).expect("valid result serializes"),
    );
    let mut client = WorkerClient::spawn(worker.config()).expect("valid fake worker starts");
    client
        .run_fixture(&request)
        .expect("bounded control-only request is admitted");
    assert_eq!(client.shutdown().outcome(), CleanupOutcome::Graceful);
}

#[test]
fn orientation_visible_output_is_preserved_after_evaluated_readback() {
    let worker = FakeWorker::returning(
        serde_json::to_string(&valid_result()).expect("valid result serializes"),
    );
    let mut client = WorkerClient::spawn(worker.config()).expect("valid fake worker starts");
    let result = client
        .run_fixture(&request())
        .expect("valid evaluated fixture result");

    assert_eq!(result.fixture_set_id(), FIXTURE_SET_ID);
    assert_eq!(result.case_id(), CASE_ID);
    assert_eq!(result.operation(), OPERATION);
    assert_eq!(result.backend_id(), "apple-mlx");
    assert_eq!(result.requested_device(), DEVICE);
    assert_eq!(result.selected_device(), DEVICE);
    assert!(!result.fallback_used());
    assert_eq!(result.output_shape(), &[2, 2]);
    assert_eq!(result.input_dtype(), "float32");
    assert_eq!(result.accumulation_dtype(), "float32");
    assert_eq!(result.output_dtype(), "float32");
    assert!(result.evaluated());
    assert!(result.synchronized());
    assert!(result.passed());

    let actual = result.actual();
    assert_eq!(actual, &[58.0, 64.0, 139.0, 154.0]);
    assert_ne!(
        actual,
        &[58.0, 139.0, 64.0, 154.0],
        "the nonsymmetric fixture must expose a transposed readback"
    );

    assert_eq!(client.shutdown().outcome(), CleanupOutcome::Graceful);
}

#[test]
fn comparison_error_metrics_and_memory_gauges_are_preserved_exactly() {
    let result = run_result(&valid_result()).expect("valid fixture result");
    let comparison = result.comparison();

    assert_eq!(comparison.oracle_id(), "committed-independent-scalar-v1");
    assert_eq!(comparison.mode(), "abs_rel");
    assert_eq!(comparison.absolute_tolerance(), 0.00001);
    assert_eq!(comparison.relative_tolerance(), 0.00001);
    assert_eq!(comparison.non_finite_policy(), "reject");
    assert_eq!(comparison.compared_count(), 4);
    assert_eq!(comparison.max_absolute_error(), 0.0);
    assert_eq!(comparison.max_relative_error(), 0.0);
    assert_eq!(comparison.first_mismatch_index(), None);
    assert!(comparison.passed());

    let memory = result.memory_gauges();
    assert_eq!(memory.mlx_active_bytes(), Some(64));
    assert_eq!(memory.mlx_cache_bytes(), Some(0));
    assert_eq!(memory.mlx_peak_bytes(), Some(128));
    assert_eq!(memory.process_footprint_bytes(), Some(16_777_216));
    assert_eq!(memory.process_footprint_source(), Some("ps-rss"));
    assert_eq!(memory.system_pressure(), Some("normal"));
    assert_eq!(memory.reported_summed_total_bytes(), None);
}

#[test]
fn result_identity_operation_and_device_must_match_the_request() {
    for (field, wrong) in [
        ("fixture_set_id", json!("different-fixture-set")),
        ("case_id", json!("different-case")),
        ("operation", json!("embedding_gather")),
        ("backend_id", json!("cuda")),
        ("requested_device", json!("cpu")),
        ("selected_device", json!("cpu")),
    ] {
        let mut result = valid_result();
        result[field] = wrong;
        assert_protocol_rejection(result, &format!("wrong {field} must be rejected"));
    }

    let mut fallback = valid_result();
    fallback["fallback_used"] = json!(true);
    assert_protocol_rejection(fallback, "fallback cannot become fixture evidence");
}

#[test]
fn result_schema_requires_known_fields_shapes_and_dtypes() {
    let mut missing = valid_result();
    missing.as_object_mut().expect("object").remove("actual");
    assert_protocol_rejection(missing, "missing actual readback must be rejected");

    let mut unknown = valid_result();
    unknown["unbounded_debug_dump"] = json!("not part of protocol v1");
    assert_protocol_rejection(unknown, "unknown result fields must be rejected");

    for shape in [json!([]), json!([0, 2]), json!([2, "2"])] {
        let mut result = valid_result();
        result["output_shape"] = shape;
        assert_protocol_rejection(result, "malformed output shape must be rejected");
    }

    for field in ["input_dtype", "accumulation_dtype", "output_dtype"] {
        let mut result = valid_result();
        result[field] = json!("float128");
        assert_protocol_rejection(result, &format!("unsupported {field} must be rejected"));
    }

    let mut wrong_cardinality = valid_result();
    wrong_cardinality["actual"] = json!([58.0, 64.0, 139.0]);
    assert_protocol_rejection(
        wrong_cardinality,
        "readback cardinality must equal the checked shape product",
    );
}

#[test]
fn successful_result_requires_evaluation_synchronization_and_consistent_metrics() {
    for field in ["evaluated", "synchronized"] {
        let mut result = valid_result();
        result[field] = json!(false);
        assert_protocol_rejection(
            result,
            &format!("passed result with {field}=false must be rejected"),
        );
    }

    let mut wrong_count = valid_result();
    wrong_count["comparison"]["compared_count"] = json!(3);
    assert_protocol_rejection(
        wrong_count,
        "comparison cardinality must equal bounded readback cardinality",
    );

    for field in ["max_absolute_error", "max_relative_error"] {
        let mut result = valid_result();
        result["comparison"][field] = json!(-1.0);
        assert_protocol_rejection(
            result,
            &format!("negative comparison metric {field} must be rejected"),
        );
    }

    let mut mismatch_on_pass = valid_result();
    mismatch_on_pass["comparison"]["first_mismatch_index"] = json!(0);
    assert_protocol_rejection(
        mismatch_on_pass,
        "a passing comparison cannot report a first mismatch",
    );

    let mut comparison_failed = valid_result();
    comparison_failed["comparison"]["passed"] = json!(false);
    assert_protocol_rejection(
        comparison_failed,
        "overall pass cannot contradict comparison failure",
    );

    let mut summed_memory = valid_result();
    summed_memory["memory_gauges"]["reported_summed_total_bytes"] = json!(16_777_344_u64);
    assert_protocol_rejection(
        summed_memory,
        "overlapping memory gauges must not be published as a summed total",
    );
}

#[test]
fn non_finite_metrics_and_oversized_readbacks_are_rejected() {
    let encoded = serde_json::to_string(&valid_result()).expect("valid result serializes");
    let non_finite = encoded.replacen(
        "\"max_absolute_error\":0.0",
        "\"max_absolute_error\":NaN",
        1,
    );
    assert_ne!(encoded, non_finite, "test must inject a non-finite metric");
    let worker = FakeWorker::returning(non_finite);
    let mut client = WorkerClient::spawn(worker.config()).expect("valid fake worker starts");
    let error = client
        .run_fixture(&request())
        .expect_err("non-finite JSON metric must fail");
    assert_eq!(error.kind(), WorkerErrorKind::StdoutContamination);

    let mut oversized = valid_result();
    oversized["output_shape"] = json!([1, MAX_FIXTURE_ELEMENTS + 1]);
    oversized["actual"] = Value::Array(vec![json!(0.0); MAX_FIXTURE_ELEMENTS + 1]);
    oversized["comparison"]["compared_count"] = json!(MAX_FIXTURE_ELEMENTS + 1);
    let error = run_result(&oversized).expect_err("oversized readback must fail before allocation");
    assert_eq!(error.kind(), WorkerErrorKind::MessageTooLarge);
}
