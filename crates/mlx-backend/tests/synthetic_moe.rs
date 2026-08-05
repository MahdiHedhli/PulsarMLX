use mlx_backend::{
    CleanupOutcome, SyntheticMoeRequest, WorkerClient, WorkerConfig, WorkerErrorKind,
    WorkerTimeouts,
};
use serde_json::{json, Value};
use std::ffi::OsString;
use std::fs;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

const FIXTURE_ID: &str = "synthetic-routed-moe-v1";
const WORKER_VERSION: &str = "fake-worker-v1";
const HELLO: &str = r#"{"protocol":1,"op":"hello","worker_version":"fake-worker-v1","python_version":"3.12.0","python_arch":"arm64","mlx_version":"0.32.0","macos_version":"15.0","metal_available":true,"gpu_count":1,"devices":[{"id":"gpu","kind":"gpu"}],"capabilities":{"operations":["health","run_synthetic_moe","shutdown"],"dtypes":["float32"]},"limits":{"max_request_bytes":65536,"max_response_bytes":1048576,"max_fixture_elements":4096}}"#;

static NEXT_ID: AtomicU64 = AtomicU64::new(0);

struct FakeWorker {
    directory: PathBuf,
    script: PathBuf,
}

impl FakeWorker {
    fn returning(result: &Value) -> Self {
        let sequence = NEXT_ID.fetch_add(1, Ordering::Relaxed);
        let directory = std::env::temp_dir().join(format!(
            "pulsarmlx-synthetic-moe-{}-{sequence}",
            std::process::id()
        ));
        fs::create_dir(&directory).expect("create fake-worker directory");
        let script = directory.join("worker.py");
        let encoded = serde_json::to_string(result).expect("result is JSON");
        let source = format!(
            r#"import json
import sys
print({hello:?}, flush=True)
RESULT = json.loads({encoded:?})
for line in sys.stdin:
    request = json.loads(line)
    request_id = request["request_id"]
    if request["op"] == "run_synthetic_moe":
        expected = {{"fixture_id": {fixture_id:?}, "device": "gpu", "allow_fallback": False}}
        assert request["params"] == expected
        response = {{"protocol": 1, "request_id": request_id, "ok": True, "result": RESULT}}
        print(json.dumps(response, separators=(",", ":")), flush=True)
    elif request["op"] == "shutdown":
        response = {{"protocol": 1, "request_id": request_id, "ok": True, "result": {{"cleanup": "graceful"}}}}
        print(json.dumps(response, separators=(",", ":")), flush=True)
        sys.exit(0)
"#,
            hello = HELLO,
            encoded = encoded,
            fixture_id = FIXTURE_ID,
        );
        fs::write(&script, source).expect("write fake worker");
        Self { directory, script }
    }

    fn config(&self) -> WorkerConfig {
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
    }
}

impl Drop for FakeWorker {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.script);
        let _ = fs::remove_dir(&self.directory);
    }
}

fn valid_result() -> Value {
    json!({
        "fixture_id": FIXTURE_ID,
        "fixture_kind": "synthetic",
        "backend_id": "apple-mlx",
        "requested_device": "gpu",
        "selected_device": "gpu",
        "fallback_used": false,
        "evaluated": true,
        "synchronized": true,
        "token_count": 2,
        "hidden_size": 2,
        "expert_count": 4,
        "top_k": 2,
        "selected_expert_ids": [[1, 2], [3, 1]],
        "normalized_weights": [[0.5, 0.5], [0.7310586, 0.26894143]],
        "fetched_experts": [
            {"expert_id": 1, "offset": 16, "length": 16, "shard_id": "experts-00001-of-00002", "payload_sha256": "59f6b8505959d216462694b9e7b20728e6ce4199aa6fcf652386b0774e22f1c7"},
            {"expert_id": 2, "offset": 32, "length": 16, "shard_id": "experts-00002-of-00002", "payload_sha256": "a527f6c2fbde17555714773e4d5ce06608d7f336389de936d73f09383fd17960"},
            {"expert_id": 3, "offset": 48, "length": 16, "shard_id": "experts-00002-of-00002", "payload_sha256": "7cc507b4e456b5c69819f532111018c3d428adc29485bf9ec6b38112d66acbba"}
        ],
        "actual": [2.0, 2.0, 4.069116, 4.037883],
        "comparison": {
            "oracle_id": "committed-scalar-routed-moe-v1",
            "absolute_tolerance": 0.00001,
            "relative_tolerance": 0.00001,
            "compared_count": 4,
            "max_absolute_error": 0.0000002,
            "max_relative_error": 0.00000005,
            "first_mismatch_index": null,
            "passed": true
        },
        "memory_gauges": {
            "mlx_active_bytes": 64,
            "mlx_cache_bytes": 128,
            "mlx_peak_bytes": 256,
            "process_footprint_bytes": 16777216,
            "process_footprint_source": "ps-rss",
            "system_pressure": "normal",
            "reported_summed_total_bytes": null
        },
        "passed": true
    })
}

fn run_result(result: &Value) -> Result<mlx_backend::SyntheticMoeResult, mlx_backend::WorkerError> {
    let worker = FakeWorker::returning(result);
    let mut client = WorkerClient::spawn(worker.config()).expect("fake worker starts");
    client.run_synthetic_moe(&SyntheticMoeRequest::new(FIXTURE_ID, "gpu")?)
}

#[test]
fn control_only_request_and_exact_routed_output_are_preserved() {
    let request = SyntheticMoeRequest::new(FIXTURE_ID, "gpu").expect("valid request");
    assert_eq!(request.fixture_id(), FIXTURE_ID);
    assert_eq!(request.device(), "gpu");
    assert!(!request.allow_fallback());
    assert!(SyntheticMoeRequest::new("", "gpu").is_err());
    assert!(SyntheticMoeRequest::new("different-synthetic-fixture", "gpu").is_err());
    assert!(SyntheticMoeRequest::new(FIXTURE_ID, "cpu").is_err());

    let worker = FakeWorker::returning(&valid_result());
    let mut client = WorkerClient::spawn(worker.config()).expect("fake worker starts");
    let result = client
        .run_synthetic_moe(&request)
        .expect("valid synthetic result");
    assert_eq!(result.fixture_id(), FIXTURE_ID);
    assert_eq!(result.selected_expert_ids(), &[vec![1, 2], vec![3, 1]]);
    assert_eq!(result.actual(), &[2.0, 2.0, 4.069116, 4.037883]);
    assert!(result.evaluated() && result.synchronized() && result.passed());
    assert_eq!(client.shutdown().outcome(), CleanupOutcome::Graceful);
}

#[test]
fn repeated_expert_routes_and_normalized_weights_are_bounded() {
    let result = run_result(&valid_result()).expect("valid synthetic result");
    assert_eq!(result.selected_expert_ids()[0], [1, 2]);
    assert_eq!(result.selected_expert_ids()[1], [3, 1]);
    for weights in result.normalized_weights() {
        assert!((weights.iter().sum::<f64>() - 1.0).abs() <= 1.0e-6);
    }
    assert_eq!(result.fetched_experts().len(), 3);
    assert_eq!(result.fetched_experts()[0].offset(), 16);
    assert_eq!(result.fetched_experts()[1].offset(), 32);
    assert_eq!(result.fetched_experts()[2].offset(), 48);
}

#[test]
fn malformed_identity_lifecycle_routes_and_payloads_are_rejected() {
    for (field, value) in [
        ("fixture_id", json!("wrong-fixture")),
        ("backend_id", json!("cuda")),
        ("selected_device", json!("cpu")),
        ("fallback_used", json!(true)),
        ("evaluated", json!(false)),
        ("synchronized", json!(false)),
    ] {
        let mut result = valid_result();
        result[field] = value;
        assert_eq!(
            run_result(&result).expect_err("malformed result").kind(),
            WorkerErrorKind::Protocol
        );
    }

    let mut duplicate_payload = valid_result();
    duplicate_payload["fetched_experts"][1]["expert_id"] = json!(1);
    assert_eq!(
        run_result(&duplicate_payload)
            .expect_err("duplicate payload")
            .kind(),
        WorkerErrorKind::Protocol
    );

    let mut bad_weights = valid_result();
    bad_weights["normalized_weights"][0] = json!([0.4, 0.4]);
    assert_eq!(
        run_result(&bad_weights)
            .expect_err("unnormalized weights")
            .kind(),
        WorkerErrorKind::Protocol
    );
}

#[test]
fn comparison_and_memory_evidence_cannot_contradict_success() {
    let mut failed_comparison = valid_result();
    failed_comparison["comparison"]["passed"] = json!(false);
    assert_eq!(
        run_result(&failed_comparison)
            .expect_err("comparison contradiction")
            .kind(),
        WorkerErrorKind::Protocol
    );

    let mut summed_memory = valid_result();
    summed_memory["memory_gauges"]["reported_summed_total_bytes"] = json!(16_777_408_u64);
    assert_eq!(
        run_result(&summed_memory)
            .expect_err("summed memory")
            .kind(),
        WorkerErrorKind::Protocol
    );

    let mut wrong_output = valid_result();
    wrong_output["actual"][2] = json!(3.0);
    assert_eq!(
        run_result(&wrong_output)
            .expect_err("wrong committed output")
            .kind(),
        WorkerErrorKind::Protocol
    );

    let mut wrong_payload = valid_result();
    wrong_payload["fetched_experts"][0]["payload_sha256"] = json!("0".repeat(64));
    assert_eq!(
        run_result(&wrong_payload)
            .expect_err("wrong committed payload digest")
            .kind(),
        WorkerErrorKind::Protocol
    );

    let mut plausible_wrong_weights = valid_result();
    plausible_wrong_weights["normalized_weights"][0] = json!([0.6, 0.4]);
    assert_eq!(
        run_result(&plausible_wrong_weights)
            .expect_err("wrong normalized routing oracle")
            .kind(),
        WorkerErrorKind::Protocol
    );
}
