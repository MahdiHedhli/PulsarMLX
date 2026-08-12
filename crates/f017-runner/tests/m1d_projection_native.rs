#![cfg(all(target_os = "macos", pulsar_native_mlx))]

use f017_runner::evidence::Evidence;
use f017_runner::json::{parse_json_no_duplicates, sha256_bytes};
use serde_json::{json, Value};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);

fn artifact(repository: &Path, role: &str, path: &str) -> Value {
    json!({
        "path_kind": "repository_relative",
        "symbolic_path": path,
        "content_sha256": sha256_bytes(&fs::read(repository.join(path)).unwrap()),
        "logical_role": role,
    })
}

fn make_execution_config(temp: &Path) -> (PathBuf, String, PathBuf) {
    let repository = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap();
    let fixtures = repository.join("specs/017-rust-native-inference-runtime/fixtures");
    let environment = temp.join("environment.json");
    fs::write(
        &environment,
        format!(
            "{{\"schema\":\"pulsarmlx.f017.fixture-environment\",\"schema_version\":1,\"architecture\":\"{}\",\"purpose\":\"checkpoint_free_ci\"}}\n",
            std::env::consts::ARCH
        ),
    )
    .unwrap();
    let package = temp.join("relocated-package.json");
    let oracle = temp.join("f017-m1d-projection-oracle-v1.json");
    fs::copy(
        fixtures.join("f017-m1d-projection-package-v1.json"),
        &package,
    )
    .unwrap();
    fs::copy(fixtures.join("f017-m1d-projection-oracle-v1.json"), &oracle).unwrap();
    let checkpoint = fixtures.join("f017-m1d-projection-checkpoint-v1.json");
    let target = fixtures.join("f017-m1d-projection-q8-0-v1.bin");
    let output = temp.join("evidence.json");
    let preparer_path = "scripts/research/prepare_f017_m1d_real_reference.py";
    let preparer_sha = sha256_bytes(&fs::read(repository.join(preparer_path)).unwrap());
    let repository_artifacts = json!({
        "fixture_finalization_source": artifact(&repository, "fixture_finalization_source", "scripts/research/generate_f017_m1d_projection_oracle.py"),
        "real_reference_preparer": artifact(&repository, "real_reference_preparer", preparer_path),
        "boundary_contract": artifact(&repository, "boundary_contract", "specs/017-rust-native-inference-runtime/contracts/m1d-projection-boundary-v1.json"),
        "decoder_contract": artifact(&repository, "decoder_contract", "specs/017-rust-native-inference-runtime/contracts/m1d-q8-0-decoder-v1.json"),
        "scaffold_contract": artifact(&repository, "scaffold_contract", "specs/017-rust-native-inference-runtime/contracts/m1d-exact-scaffold-v1.json"),
        "tier_b_contract": artifact(&repository, "tier_b_contract", "specs/017-rust-native-inference-runtime/contracts/production-m1d-projection-tier-b-v1.json"),
        "repeat_integrity_contract": artifact(&repository, "repeat_integrity_contract", "specs/017-rust-native-inference-runtime/contracts/m1d-repeat-integrity-v1.json"),
        "oracle_ordering_contract": artifact(&repository, "oracle_ordering_contract", "specs/017-rust-native-inference-runtime/contracts/m1d-oracle-ordering-v1.json"),
        "path_resolution_contract": artifact(&repository, "path_resolution_contract", "specs/017-rust-native-inference-runtime/contracts/m1d-artifact-path-resolution-v1.json"),
        "package_schema": artifact(&repository, "package_schema", "specs/017-rust-native-inference-runtime/contracts/m1d-projection-package-v2.schema.json"),
        "command_assembly_contract": artifact(&repository, "command_assembly_contract", "specs/017-rust-native-inference-runtime/contracts/m1d-command-assembly-v1.json"),
        "execution_config_schema": artifact(&repository, "execution_config_schema", "specs/017-rust-native-inference-runtime/contracts/m1d-execution-config-v1.schema.json"),
    });
    let document = json!({
        "schema": "pulsarmlx.f017.m1d-execution-config",
        "schema_version": "1.0.0",
        "status": "READY_TO_EXECUTE_ATTEMPT_3",
        "attempt": 3,
        "attempt_consumed": false,
        "runtime_sha": env!("PULSARMLX_SOURCE_SHA"),
        "tooling_sha": env!("PULSARMLX_SOURCE_SHA"),
        "repository_root": {"path_kind":"absolute_private_local", "path":repository, "identity":env!("PULSARMLX_SOURCE_SHA")},
        "package_root": {"path_kind":"absolute_private_local", "path":temp, "identity":"m1d_attempt_3_private_package_root"},
        "activation_fixture": artifact(&repository, "activation_fixture", "specs/017-rust-native-inference-runtime/fixtures/f017-m1d-projection-oracle-v1.json"),
        "activation_payload_sha256": "dfc1df6cc6efa38c5c0f5bf086757ed78baf4cfc6f721da1e0ae7f73560193c2",
        "provenance": {
            "activation_generation_source_sha256":"29c5c51a8f440e06d6584a71e0b79283d2bd6f806a2435c15ff93f3a0cae7984",
            "fixture_finalization_source_sha256":"0299066d46211d1921ded772ab907fcd9e9f1c8e3d2c497d979914a30c3dbd92",
            "real_reference_preparer_sha256":preparer_sha,
        },
        "repository_artifacts": repository_artifacts,
        "local_artifacts": {
            "environment_manifest":{"path_kind":"absolute_private_local", "path":environment, "content_sha256":sha256_bytes(&fs::read(&environment).unwrap())},
            "checkpoint_manifest":{"path_kind":"absolute_private_local", "path":checkpoint, "content_sha256":sha256_bytes(&fs::read(&checkpoint).unwrap())},
            "target_shard":{"path_kind":"absolute_private_local", "path":target, "basename":"f017-m1d-projection-q8-0-v1.bin", "ordinal":2, "byte_size":fs::metadata(&target).unwrap().len(), "sha256":sha256_bytes(&fs::read(&target).unwrap())},
            "oracle_output":oracle,
            "package_output":package,
            "evidence_output":output,
        },
        "prior_evidence": {
            "attempt_1":"a5aefaaf59583dad87765303e159986c895017c20ea80eb874cd447ad80f9a62",
            "attempt_2":"6a87c36c380fb43393bc79cdc4e22e59bb81c0425ad0285017d6a1bc00dd79f6",
            "m1_a":"aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805",
            "m1_b":"9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770",
            "m1_c":"343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e"
        },
        "checkpoint_bindings": {
            "checkpoint_set_sha256":"d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee",
            "catalog_sha256":"0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0",
            "tensor_map_sha256":"ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223"
        },
        "runner":{"mode":"fixture_projection", "validation_mode":"golden_strict", "stream_mode":"owned_device", "numerical_mode":"production_mlx_tier_b", "memory_floor_bytes":1},
        "execution":{"conceptual_projection_count":1, "repeat_count":10, "native_dispatch_count":10, "auto_retry":false, "stop_before_m1_e":true}
    });
    let bytes = (serde_json::to_string_pretty(&document).unwrap() + "\n").into_bytes();
    let digest = sha256_bytes(&bytes);
    let config = temp.join("immutable-execution-config.json");
    fs::write(&config, bytes).unwrap();
    (config, digest, output)
}

fn run_native(diverge: bool) -> (std::process::ExitStatus, Evidence, PathBuf) {
    let temp = std::env::temp_dir().join(format!(
        "f017-m1d-command-config-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir_all(&temp).unwrap();
    let (config, digest, output) = make_execution_config(&temp);
    let mut command = Command::new(env!("CARGO_BIN_EXE_f017-glm52-runner"));
    command
        .current_dir(std::env::temp_dir())
        .args(["--m1d-execution-config"])
        .arg(&config)
        .args(["--execution-config-sha256", &digest]);
    if diverge {
        command.env("PULSAR_F017_TEST_DIVERGE_REPEAT", "5");
    }
    let status = command.status().unwrap();
    let evidence = parse_json_no_duplicates(&fs::read(output).unwrap()).unwrap();
    (status, evidence, temp)
}

#[test]
fn canonical_binary_executes_one_real_shaped_checkpoint_free_projection_from_immutable_config() {
    let (status, evidence, temp) = run_native(false);
    assert!(status.success());
    evidence.validate_success_ready().unwrap();
    assert!(evidence.identity.execution_config_sha256.is_some());
    assert_eq!(evidence.execution.projection_count, 1);
    assert_eq!(evidence.execution.dispatch.native, 10);
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
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn one_bit_repeat_divergence_fails_even_when_selected_repeat_is_clean() {
    let (status, evidence, temp) = run_native(true);
    assert!(!status.success());
    assert_eq!(
        evidence.result.first_failure.as_ref().unwrap().code,
        "m1d_repeat_divergence"
    );
    fs::remove_dir_all(temp).unwrap();
}

#[test]
fn config_only_cli_rejects_duplicate_or_manual_override() {
    let temp = std::env::temp_dir().join(format!(
        "f017-m1d-command-negative-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir_all(&temp).unwrap();
    let (config, digest, _) = make_execution_config(&temp);
    let status = Command::new(env!("CARGO_BIN_EXE_f017-glm52-runner"))
        .args(["--m1d-execution-config"])
        .arg(&config)
        .args([
            "--execution-config-sha256",
            &digest,
            "--activation-fixture",
            "wrong",
        ])
        .status()
        .unwrap();
    assert!(!status.success());
    fs::remove_dir_all(temp).unwrap();
}
