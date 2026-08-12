#![cfg(all(target_os = "macos", pulsar_native_mlx))]

use f017_runner::evidence::Evidence;
use f017_runner::json::parse_json_no_duplicates;
use std::fs;
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);

#[test]
fn canonical_binary_executes_one_real_shaped_checkpoint_free_projection() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../specs/017-rust-native-inference-runtime/fixtures");
    let temp = std::env::temp_dir().join(format!(
        "f017-m1d-native-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir_all(&temp).unwrap();
    let environment = temp.join("environment.json");
    fs::write(
        &environment,
        format!(
            "{{\"schema\":\"pulsarmlx.f017.fixture-environment\",\"schema_version\":1,\"architecture\":\"{}\",\"purpose\":\"checkpoint_free_ci\"}}\n",
            std::env::consts::ARCH
        ),
    )
    .unwrap();
    let out = temp.join("evidence.json");
    let status = Command::new(env!("CARGO_BIN_EXE_f017-glm52-runner"))
        .args(["--out"])
        .arg(&out)
        .args([
            "--validation-mode",
            "golden-strict",
            "--stream-mode",
            "owned-device",
            "--memory-floor-bytes",
            "17179869184",
            "--environment-manifest",
        ])
        .arg(&environment)
        .args(["--checkpoint-manifest"])
        .arg(root.join("f017-m1d-projection-checkpoint-v1.json"))
        .args(["--fixture-projection-boundary"])
        .arg(root.join("f017-m1d-projection-package-v1.json"))
        .args(["--numerical-mode", "production-mlx-tier-b"])
        .status()
        .unwrap();
    assert!(status.success());
    let evidence: Evidence = parse_json_no_duplicates(&fs::read(out).unwrap()).unwrap();
    evidence.validate_success_ready().unwrap();
    assert_eq!(evidence.execution.projection_count, 1);
    assert_eq!(evidence.execution.quant_decode_count, 1);
    assert_eq!(evidence.execution.dispatch.native, 10);
    assert_eq!(evidence.execution.dispatch.qualification_scaffold, 0);
    assert_eq!(evidence.execution.dispatch.explicit_reference, 0);
    assert_eq!(evidence.execution.dispatch.fallback, 0);
    assert_eq!(evidence.execution.expert_execution_count, 0);
    assert_eq!(evidence.execution.layer_execution_count, 0);
    assert_eq!(evidence.execution.logits_count, 0);
    assert!(!evidence.execution.p1);
    assert!(evidence.lifecycle.reconciled);
}
