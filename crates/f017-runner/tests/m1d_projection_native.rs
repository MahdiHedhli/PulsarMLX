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
    assert_eq!(
        evidence
            .execution
            .numerical
            .repeat_integrity
            .repeat_count_observed,
        10
    );
    assert_eq!(
        evidence.execution.numerical.repeat_integrity.outputs.len(),
        10
    );
    assert!(
        evidence
            .execution
            .numerical
            .repeat_integrity
            .all_repeat_hashes_equal
    );
    assert!(
        evidence
            .execution
            .numerical
            .oracle_ordering
            .structural_order_valid
    );
    assert_eq!(evidence.execution.dispatch.qualification_scaffold, 0);
    assert_eq!(evidence.execution.dispatch.explicit_reference, 0);
    assert_eq!(evidence.execution.dispatch.fallback, 0);
    assert_eq!(evidence.execution.expert_execution_count, 0);
    assert_eq!(evidence.execution.layer_execution_count, 0);
    assert_eq!(evidence.execution.logits_count, 0);
    assert!(!evidence.execution.p1);
    assert!(evidence.lifecycle.reconciled);

    let mut invalid = evidence.clone();
    invalid.execution.dispatch.fallback = 1;
    assert!(invalid.validate_success_ready().is_err());
    let mut invalid = evidence.clone();
    invalid.execution.dispatch.qualification_scaffold = 1;
    assert!(invalid.validate_success_ready().is_err());
    let mut invalid = evidence.clone();
    invalid.lifecycle.reconciled = false;
    assert!(invalid.validate_success_ready().is_err());
    let mut invalid = evidence.clone();
    invalid.execution.projection_count = 2;
    assert!(invalid.validate_success_ready().is_err());
    let mut invalid = evidence;
    invalid.execution.numerical_classification = Some(
        f017_runner::numerical_classification::NumericalClassification::NumericallyQualifiedGreedyIdentical,
    );
    assert!(invalid.validate_success_ready().is_err());
}

#[test]
fn one_bit_repeat_divergence_fails_even_when_selected_repeat_is_clean() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../specs/017-rust-native-inference-runtime/fixtures");
    let temp = std::env::temp_dir().join(format!(
        "f017-m1d-divergence-{}-{}",
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
        .env("PULSAR_F017_TEST_DIVERGE_REPEAT", "5")
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
    assert!(!status.success());
    let evidence: Evidence = parse_json_no_duplicates(&fs::read(&out).unwrap()).unwrap();
    assert_eq!(
        evidence.result.first_failure.as_ref().unwrap().code,
        "m1d_repeat_divergence"
    );
    assert_ne!(
        evidence.result.classification,
        f017_runner::evidence::ResultClassification::Pass
    );
    fs::remove_dir_all(temp).unwrap();
}
