use mlx_backend::{
    CleanupOutcome, WorkerClient, WorkerConfig, WorkerError, WorkerErrorKind, WorkerTimeouts,
};
use std::ffi::OsString;
use std::fs;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

const WORKER_VERSION: &str = "fake-worker-v1";
const MLX_VERSION: &str = "0.32.0";
const HELLO: &str = r#"{"protocol":1,"op":"hello","worker_version":"fake-worker-v1","python_version":"3.12.0","python_arch":"arm64","mlx_version":"0.32.0","macos_version":"15.0","metal_available":true,"gpu_count":1,"devices":[{"id":"gpu","kind":"gpu"}],"capabilities":{"operations":["health","shutdown"],"dtypes":["float32"]},"limits":{"max_request_bytes":65536,"max_response_bytes":1048576,"max_fixture_elements":1024}}"#;

static NEXT_TEMP_ID: AtomicU64 = AtomicU64::new(0);

struct FakeWorker {
    directory: PathBuf,
    script: PathBuf,
}

impl FakeWorker {
    fn new(source: impl AsRef<str>) -> Self {
        let sequence = NEXT_TEMP_ID.fetch_add(1, Ordering::Relaxed);
        let directory = std::env::temp_dir().join(format!(
            "pulsarmlx-worker-contract-{}-{sequence}",
            std::process::id()
        ));
        fs::create_dir(&directory).expect("create isolated fake-worker directory");
        let script = directory.join("worker.py");
        let source = source.as_ref();
        assert!(source.len() <= 32 * 1024, "fake worker must remain bounded");
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
            Duration::from_millis(150),
            Duration::from_millis(150),
        ))
    }
}

impl Drop for FakeWorker {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.script);
        let _ = fs::remove_dir(&self.directory);
    }
}

fn worker_script(body: &str) -> String {
    format!(
        r#"import json
import os
import sys
import time

HELLO = {hello:?}
print(HELLO, flush=True)

def success(request_id, result):
    print(json.dumps({{"protocol": 1, "request_id": request_id, "ok": True, "result": result}}, separators=(",", ":")), flush=True)

{body}
"#,
        hello = HELLO,
    )
}

fn hello_only_script(hello: &str) -> String {
    format!("import sys\nprint({hello:?}, flush=True)\nsys.exit(0)\n")
}

fn graceful_loop() -> String {
    worker_script(
        r#"for line in sys.stdin:
    request = json.loads(line)
    if request["op"] == "health":
        success(request["request_id"], {"ready": True})
    elif request["op"] == "shutdown":
        success(request["request_id"], {"cleanup": "graceful"})
        sys.exit(0)
"#,
    )
}

fn spawn_error(config: WorkerConfig, context: &str) -> WorkerError {
    match WorkerClient::spawn(config) {
        Ok(client) => {
            let _ = client.shutdown();
            panic!("{context}");
        }
        Err(error) => error,
    }
}

fn assert_kind(error: &WorkerError, expected: WorkerErrorKind) {
    assert_eq!(error.kind(), expected, "unexpected error: {error}");
}

#[test]
fn valid_hello_is_negotiated_before_requests_are_admitted() {
    let worker = FakeWorker::new(graceful_loop());
    let client = WorkerClient::spawn(worker.config()).expect("valid hello negotiates");

    let hello = client.hello();
    assert_eq!(hello.protocol(), 1);
    assert_eq!(hello.worker_version(), WORKER_VERSION);
    assert_eq!(hello.mlx_version(), MLX_VERSION);
    assert_eq!(hello.python_arch(), "arm64");
    assert_eq!(hello.request_id(), None, "hello is unsolicited");

    let report = client.shutdown();
    assert_eq!(report.outcome(), CleanupOutcome::Graceful);
}

#[test]
fn hello_negotiation_rejects_protocol_and_pinned_version_mismatches() {
    let wrong_protocol = HELLO.replace("\"protocol\":1", "\"protocol\":2");
    let worker = FakeWorker::new(hello_only_script(&wrong_protocol));
    let error = spawn_error(worker.config(), "protocol 2 must be rejected");
    assert_kind(&error, WorkerErrorKind::HelloNegotiation);

    let wrong_worker = HELLO.replace(WORKER_VERSION, "fake-worker-v2");
    let worker = FakeWorker::new(hello_only_script(&wrong_worker));
    let error = spawn_error(worker.config(), "worker version must match");
    assert_kind(&error, WorkerErrorKind::HelloNegotiation);

    let wrong_mlx = HELLO.replace(MLX_VERSION, "0.31.0");
    let worker = FakeWorker::new(hello_only_script(&wrong_mlx));
    let error = spawn_error(worker.config(), "MLX version must match");
    assert_kind(&error, WorkerErrorKind::HelloNegotiation);
}

#[test]
fn sequential_requests_preserve_order_and_monotonic_ids() {
    let worker = FakeWorker::new(graceful_loop());
    let mut client = WorkerClient::spawn(worker.config()).expect("valid worker starts");

    let first = client.health().expect("first health response");
    let second = client.health().expect("second health response");

    assert_eq!(second.request_id(), first.request_id() + 1);
    assert!(first.ready());
    assert!(second.ready());

    let report = client.shutdown();
    assert_eq!(report.outcome(), CleanupOutcome::Graceful);
}

#[test]
fn external_worker_configuration_can_clear_inherited_private_environment() {
    assert!(std::env::var_os("HOME").is_some());
    let worker = FakeWorker::new(worker_script(
        r#"for line in sys.stdin:
    request = json.loads(line)
    if request["op"] == "health":
        success(request["request_id"], {"ready": os.environ.get("HOME") is None and os.environ.get("PULSARMLX_EXPLICIT_SAFE") == "yes"})
    elif request["op"] == "shutdown":
        success(request["request_id"], {"cleanup": "graceful"})
        sys.exit(0)
"#,
    ));
    let config = worker
        .config()
        .without_inherited_environment()
        .with_env("PATH", std::env::var_os("PATH").expect("test PATH"))
        .with_env("PULSARMLX_EXPLICIT_SAFE", "yes");
    let mut client = WorkerClient::spawn(config).expect("environment-cleared worker starts");
    assert!(client.health().expect("environment probe").ready());
    assert_eq!(client.shutdown().outcome(), CleanupOutcome::Graceful);
}

#[test]
fn mismatched_response_id_invalidates_the_request() {
    let worker = FakeWorker::new(worker_script(
        r#"request = json.loads(sys.stdin.readline())
success(request["request_id"] + 1, {"ready": True})
time.sleep(5)
"#,
    ));
    let mut client = WorkerClient::spawn(worker.config()).expect("valid worker starts");

    let error = client
        .health()
        .expect_err("response ID must match request ID");
    assert_kind(&error, WorkerErrorKind::RequestIdMismatch);
}

#[test]
fn request_timeout_is_bounded_and_does_not_become_success() {
    let worker = FakeWorker::new(worker_script(
        r#"sys.stdin.readline()
time.sleep(5)
"#,
    ));
    let mut client = WorkerClient::spawn(worker.config()).expect("valid worker starts");

    let error = client.health().expect_err("silent worker must time out");
    assert_kind(&error, WorkerErrorKind::Timeout);
}

#[test]
fn clean_eof_before_a_response_is_not_a_successful_request() {
    let worker = FakeWorker::new(worker_script(
        r#"sys.stdin.readline()
sys.exit(0)
"#,
    ));
    let mut client = WorkerClient::spawn(worker.config()).expect("valid worker starts");

    let error = client.health().expect_err("EOF before response must fail");
    assert_kind(&error, WorkerErrorKind::UnexpectedEof);
}

#[test]
fn nonzero_exit_and_signal_termination_are_distinguished() {
    let worker = FakeWorker::new(worker_script(
        r#"sys.stdin.readline()
sys.exit(17)
"#,
    ));
    let mut client = WorkerClient::spawn(worker.config()).expect("valid worker starts");
    let error = client.health().expect_err("nonzero worker exit must fail");
    assert_kind(&error, WorkerErrorKind::NonZeroExit);
    assert_eq!(error.exit_code(), Some(17));

    let worker = FakeWorker::new(worker_script(
        r#"import signal
sys.stdin.readline()
# Preserve signal-termination coverage without invoking macOS Crash Reporter.
os.kill(os.getpid(), signal.SIGTERM)
"#,
    ));
    let mut client = WorkerClient::spawn(worker.config()).expect("valid worker starts");
    let error = client
        .health()
        .expect_err("signal-terminated worker must fail");
    assert_kind(&error, WorkerErrorKind::ProcessCrashed);
    assert_eq!(error.exit_code(), None);
}

#[test]
fn non_protocol_stdout_is_detected_as_contamination() {
    let worker = FakeWorker::new(worker_script(
        r#"sys.stdin.readline()
print("diagnostic leaked to stdout", flush=True)
time.sleep(5)
"#,
    ));
    let mut client = WorkerClient::spawn(worker.config()).expect("valid worker starts");

    let error = client
        .health()
        .expect_err("stdout must contain protocol only");
    assert_kind(&error, WorkerErrorKind::StdoutContamination);
}

#[test]
fn structured_worker_errors_preserve_bounded_semantics() {
    let worker = FakeWorker::new(worker_script(
        r#"for line in sys.stdin:
    request = json.loads(line)
    if request["op"] == "health":
        print(json.dumps({"protocol": 1, "request_id": request["request_id"], "ok": False, "error": {"code": "device_unavailable", "message": "requested fake device is unavailable", "retryable": False, "details": {"device": "gpu"}}}, separators=(",", ":")), flush=True)
    elif request["op"] == "shutdown":
        success(request["request_id"], {"cleanup": "graceful"})
        sys.exit(0)
"#,
    ));
    let mut client = WorkerClient::spawn(worker.config()).expect("valid worker starts");

    let error = client
        .health()
        .expect_err("worker error must remain an error");
    assert_kind(&error, WorkerErrorKind::Remote);
    assert_eq!(error.worker_code(), Some("device_unavailable"));
    assert_eq!(error.message(), "requested fake device is unavailable");
    assert_eq!(error.retryable(), Some(false));

    let report = client.shutdown();
    assert_eq!(report.outcome(), CleanupOutcome::Graceful);
}

#[test]
fn graceful_shutdown_reports_response_and_zero_exit() {
    let worker = FakeWorker::new(graceful_loop());
    let client = WorkerClient::spawn(worker.config()).expect("valid worker starts");

    let report = client.shutdown();
    assert_eq!(report.outcome(), CleanupOutcome::Graceful);
    assert_eq!(report.exit_code(), Some(0));
    assert!(report.error().is_none());
}

#[test]
fn shutdown_timeout_forces_cleanup_and_records_an_error() {
    let worker = FakeWorker::new(worker_script(
        r#"request = json.loads(sys.stdin.readline())
assert request["op"] == "shutdown"
time.sleep(5)
"#,
    ));
    let client = WorkerClient::spawn(worker.config()).expect("valid worker starts");

    let report = client.shutdown();
    assert_eq!(report.outcome(), CleanupOutcome::ForcedTermination);
    let error = report
        .error()
        .expect("forced cleanup is recorded as an error");
    assert_kind(error, WorkerErrorKind::Timeout);
}

#[test]
fn eof_before_hello_fails_startup_negotiation() {
    let worker = FakeWorker::new("import sys\nsys.exit(0)\n");

    let error = spawn_error(worker.config(), "hello is mandatory");
    assert_kind(&error, WorkerErrorKind::UnexpectedEof);
}
