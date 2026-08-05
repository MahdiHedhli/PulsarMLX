use mlx_backend::{
    validate_device_smoke, DeviceHello, DeviceProbe, DeviceSmokeErrorCode, DeviceState,
    PINNED_MLX_VERSION,
};

const BACKEND_ID: &str = "apple-mlx";
const GPU_DEVICE: &str = "gpu";

fn supported_hello() -> DeviceHello {
    DeviceHello {
        python_arch: "arm64".to_owned(),
        mlx_version: "0.32.0".to_owned(),
        metal_available: true,
        gpu_count: 1,
    }
}

fn passing_probe() -> DeviceProbe {
    DeviceProbe {
        backend_id: BACKEND_ID.to_owned(),
        requested_device: GPU_DEVICE.to_owned(),
        selected_device: GPU_DEVICE.to_owned(),
        fallback_used: false,
        operation_id: "nonsymmetric-f32-matmul".to_owned(),
        evaluated: true,
        synchronized: true,
        expected: vec![58.0, 64.0, 139.0, 154.0],
        actual: vec![58.0, 64.0, 139.0, 154.0],
        absolute_tolerance: 1.0e-5,
        relative_tolerance: 1.0e-5,
    }
}

fn assert_rejected(hello: &DeviceHello, probe: &DeviceProbe, expected_code: DeviceSmokeErrorCode) {
    let error = validate_device_smoke(hello, probe)
        .expect_err("an invalid Apple accelerator proof must not become evaluated evidence");
    assert_eq!(error.code(), expected_code);
}

#[test]
fn pinned_mlx_version_is_exact() {
    assert_eq!(PINNED_MLX_VERSION, "0.32.0");
}

#[test]
fn rejects_a_non_arm64_worker_identity() {
    let mut hello = supported_hello();
    hello.python_arch = "x86_64".to_owned();

    assert_rejected(
        &hello,
        &passing_probe(),
        DeviceSmokeErrorCode::UnsupportedHost,
    );
}

#[test]
fn rejects_a_worker_with_the_wrong_mlx_version() {
    let mut hello = supported_hello();
    hello.mlx_version = "0.31.0".to_owned();

    assert_rejected(
        &hello,
        &passing_probe(),
        DeviceSmokeErrorCode::RuntimeVersionMismatch,
    );
}

#[test]
fn rejects_unavailable_metal() {
    let mut hello = supported_hello();
    hello.metal_available = false;

    assert_rejected(
        &hello,
        &passing_probe(),
        DeviceSmokeErrorCode::MetalUnavailable,
    );
}

#[test]
fn rejects_a_worker_with_no_gpu() {
    let mut hello = supported_hello();
    hello.gpu_count = 0;

    assert_rejected(
        &hello,
        &passing_probe(),
        DeviceSmokeErrorCode::DeviceUnavailable,
    );
}

#[test]
fn rejects_cpu_selection_even_when_the_probe_otherwise_passes() {
    let mut probe = passing_probe();
    probe.selected_device = "cpu".to_owned();

    assert_rejected(
        &supported_hello(),
        &probe,
        DeviceSmokeErrorCode::DeviceSelectionMismatch,
    );
}

#[test]
fn rejects_cpu_fallback_instead_of_silently_accepting_it() {
    let mut probe = passing_probe();
    probe.selected_device = "cpu".to_owned();
    probe.fallback_used = true;

    assert_rejected(
        &supported_hello(),
        &probe,
        DeviceSmokeErrorCode::FallbackForbidden,
    );
}

#[test]
fn rejects_unevaluated_work() {
    let mut probe = passing_probe();
    probe.evaluated = false;

    assert_rejected(
        &supported_hello(),
        &probe,
        DeviceSmokeErrorCode::EvaluationIncomplete,
    );
}

#[test]
fn rejects_unsynchronized_work() {
    let mut probe = passing_probe();
    probe.synchronized = false;

    assert_rejected(
        &supported_hello(),
        &probe,
        DeviceSmokeErrorCode::SynchronizationIncomplete,
    );
}

#[test]
fn rejects_a_numeric_mismatch() {
    let mut probe = passing_probe();
    probe.actual[2] = 138.0;

    assert_rejected(
        &supported_hello(),
        &probe,
        DeviceSmokeErrorCode::ComparisonFailed,
    );
}

#[test]
fn admits_only_a_matching_evaluated_synchronized_gpu_probe() {
    let report = validate_device_smoke(&supported_hello(), &passing_probe())
        .expect("the exact bounded GPU proof is admissible");

    assert_eq!(report.backend_id(), BACKEND_ID);
    assert_eq!(report.selected_device(), GPU_DEVICE);
    assert_eq!(report.device_state(), DeviceState::Evaluated);
    assert_eq!(report.compared_count(), 4);
    assert!(report.comparison_passed());
    assert!(!report.fallback_used());
}

#[cfg(all(target_os = "macos", target_arch = "aarch64"))]
#[test]
#[ignore = "requires `uv sync --frozen` and the pinned native MLX runtime"]
fn native_device_smoke_command_emits_evaluated_evidence() {
    use std::fs;
    use std::process::Command;
    use std::time::{SystemTime, UNIX_EPOCH};

    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("the system clock must be after the Unix epoch")
        .as_nanos();
    let evidence_path = std::env::temp_dir().join(format!(
        "pulsarmlx-device-smoke-{}-{nonce}.json",
        std::process::id()
    ));

    let output = Command::new(env!("CARGO_BIN_EXE_pulsar-mlx"))
        .args([
            "device-smoke",
            "--backend",
            BACKEND_ID,
            "--device",
            GPU_DEVICE,
            "--evidence",
        ])
        .arg(&evidence_path)
        .output()
        .expect("the device-smoke executable must start");

    assert!(
        output.status.success(),
        "device-smoke failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );

    let evidence = fs::read_to_string(&evidence_path)
        .expect("T023 must make device-smoke write the requested evidence record");
    fs::remove_file(&evidence_path).expect("the test must remove its temporary evidence file");

    assert!(evidence.contains("\"backend_id\":\"apple-mlx\""));
    assert!(evidence.contains("\"selected_device\":\"gpu\""));
    assert!(evidence.contains("\"device_state\":\"evaluated\""));
    assert!(evidence.contains("\"evaluated\":true"));
    assert!(evidence.contains("\"synchronized\":true"));
    assert!(evidence.contains("\"comparison_passed\":true"));
    assert!(evidence.contains("\"fallback_used\":false"));
}
