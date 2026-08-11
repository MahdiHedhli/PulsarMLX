use backend::{CancellationToken, TensorCatalog};
use f017_runner::checkpoint::{
    catalog_sha256, CheckpointKind, CheckpointManifest, CheckpointShard, VerifiedCheckpoint,
};
use f017_runner::evidence::Evidence;
use f017_runner::json::{parse_json_no_duplicates, sha256_bytes};
use f017_runner::store::RunnerTensorStore;
use gguf::{Gguf, GGUF_MAGIC};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT_FIXTURE_ID: AtomicU64 = AtomicU64::new(0);

struct Fixture {
    root: PathBuf,
    manifest: PathBuf,
    environment: PathBuf,
    first_shard: PathBuf,
    first_payload: Vec<u8>,
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}

#[test]
fn fake_multi_shard_catalog_and_exact_read_pass() {
    let fixture = fixture(false);
    let manifest = CheckpointManifest::load(&fixture.manifest).unwrap();
    let verified = VerifiedCheckpoint::verify(&fixture.manifest, manifest).unwrap();
    assert_eq!(verified.catalog.tensors.len(), 2);
    let store = RunnerTensorStore::open(verified).unwrap();
    let tensor = store.tensor("token_embd.weight").unwrap().unwrap();
    assert_eq!(tensor.shard, "fixture-00001-of-00002.gguf");
    assert_eq!(
        store
            .read_tensor_exact("token_embd.weight", &CancellationToken::new())
            .unwrap(),
        fixture.first_payload
    );
}

#[test]
fn duplicate_tensor_names_fail_closed() {
    let fixture = fixture(true);
    let manifest = CheckpointManifest::load(&fixture.manifest).unwrap();
    let error = VerifiedCheckpoint::verify(&fixture.manifest, manifest)
        .err()
        .unwrap();
    assert_eq!(error.code, "checkpoint_duplicate_tensor");
}

#[test]
fn post_identity_truncation_is_a_hard_short_read() {
    let fixture = fixture(false);
    let manifest = CheckpointManifest::load(&fixture.manifest).unwrap();
    let verified = VerifiedCheckpoint::verify(&fixture.manifest, manifest).unwrap();
    let store = RunnerTensorStore::open(verified).unwrap();
    let length = fs::metadata(&fixture.first_shard).unwrap().len();
    fs::OpenOptions::new()
        .write(true)
        .open(&fixture.first_shard)
        .unwrap()
        .set_len(length - 1)
        .unwrap();
    let error = store
        .read_tensor_exact("token_embd.weight", &CancellationToken::new())
        .unwrap_err();
    assert_eq!(error.code(), "tensor_read");
}

#[test]
fn actual_binary_runs_dry_and_identity_modes() {
    let fixture = fixture(false);
    let dry_out = fixture.root.join("dry.json");
    let status = Command::new(env!("CARGO_BIN_EXE_f017-glm52-runner"))
        .args(common_args(&fixture.environment, &dry_out))
        .arg("--dry-run")
        .status()
        .unwrap();
    assert!(status.success());
    let dry: Evidence = parse_json_no_duplicates(&fs::read(&dry_out).unwrap()).unwrap();
    assert_eq!(dry.input.mode, "dry_run");
    assert!(!dry.identity.checkpoint.accessed);

    let identity_out = fixture.root.join("identity.json");
    let status = Command::new(env!("CARGO_BIN_EXE_f017-glm52-runner"))
        .args(common_args(&fixture.environment, &identity_out))
        .args([
            "--fixture-checkpoint-identity-only",
            "--checkpoint-manifest",
        ])
        .arg(&fixture.manifest)
        .status()
        .unwrap();
    assert!(status.success());
    let identity: Evidence = parse_json_no_duplicates(&fs::read(&identity_out).unwrap()).unwrap();
    assert_eq!(identity.input.mode, "fixture_checkpoint_identity");
    assert!(identity.identity.checkpoint.accessed);
    assert_eq!(identity.identity.checkpoint.shards.len(), 2);
    assert_eq!(identity.execution.storage.read_count, 4);
    assert_eq!(
        identity.execution.storage.read_bytes,
        identity
            .identity
            .checkpoint
            .shards
            .iter()
            .map(|shard| shard.size_bytes * 2)
            .sum::<u64>()
    );
    assert_eq!(identity.execution.dispatch.native, 0);
    assert_eq!(
        identity.identity.checkpoint.tensor_map.status,
        f017_runner::evidence::TensorMapStatus::NotApplicable
    );
    let public_json = fs::read_to_string(&identity_out).unwrap();
    assert!(!public_json.contains(fixture.root.to_str().unwrap()));
}

#[test]
fn adapter_preflight_mode_rejects_every_checkpoint_argument() {
    let fixture = fixture(false);
    let out = fixture.root.join("adapter-mixed.json");
    let status = Command::new(env!("CARGO_BIN_EXE_f017-glm52-runner"))
        .args(common_args(&fixture.environment, &out))
        .arg("--adapter-preflight-only")
        .args(["--checkpoint-manifest"])
        .arg(&fixture.manifest)
        .status()
        .unwrap();
    assert_eq!(status.code(), Some(14));
    assert!(!out.exists());
}

#[test]
fn fixture_identity_mode_never_constructs_execution_or_dispatch_state() {
    let fixture = fixture(false);
    let out = fixture.root.join("identity-isolation.json");
    let status = Command::new(env!("CARGO_BIN_EXE_f017-glm52-runner"))
        .args(common_args(&fixture.environment, &out))
        .args([
            "--fixture-checkpoint-identity-only",
            "--checkpoint-manifest",
        ])
        .arg(&fixture.manifest)
        .status()
        .unwrap();
    assert!(status.success());
    let evidence: Evidence = parse_json_no_duplicates(&fs::read(out).unwrap()).unwrap();
    assert!(evidence.execution.layers.is_empty());
    assert_eq!(evidence.execution.generated_token, None);
    assert_eq!(evidence.execution.dispatch, Default::default());
    assert_eq!(evidence.residency, Default::default());
}

#[test]
fn production_stage_modes_reject_fixture_environment_before_stage_work() {
    let fixture = fixture(false);

    let adapter_out = fixture.root.join("adapter-fixture-environment.json");
    let adapter = Command::new(env!("CARGO_BIN_EXE_f017-glm52-runner"))
        .args(common_args(&fixture.environment, &adapter_out))
        .arg("--adapter-preflight-only")
        .status()
        .unwrap();
    assert_eq!(adapter.code(), Some(10));
    assert!(!adapter_out.exists());

    let identity_out = fixture.root.join("identity-fixture-environment.json");
    let missing_checkpoint = fixture.root.join("must-not-open-checkpoint.json");
    assert!(!missing_checkpoint.exists());
    let identity = Command::new(env!("CARGO_BIN_EXE_f017-glm52-runner"))
        .args(common_args(&fixture.environment, &identity_out))
        .args(["--checkpoint-identity-only", "--checkpoint-manifest"])
        .arg(&missing_checkpoint)
        .status()
        .unwrap();
    assert_eq!(identity.code(), Some(10));
    assert!(!identity_out.exists());
    assert!(!missing_checkpoint.exists());
}

#[test]
fn p1_rejects_fixture_environment_before_checkpoint_access() {
    let fixture = fixture(false);
    let out = fixture.root.join("p1-failure.json");
    let status = Command::new(env!("CARGO_BIN_EXE_f017-glm52-runner"))
        .args(common_args(&fixture.environment, &out))
        .args(["--checkpoint-manifest"])
        .arg(&fixture.manifest)
        .args([
            "--tokens",
            "9703",
            "--n-new",
            "1",
            "--expected-token",
            "21615",
            "--numerical-mode",
            "production-mlx-tier-b",
        ])
        .status()
        .unwrap();
    assert_eq!(status.code(), Some(10));
    assert!(!out.exists());
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
#[test]
fn actual_binary_passes_independent_projection_through_production_adapter() {
    let fixture = fixture(false);
    let out = fixture.root.join("projection.json");
    let oracle = Path::new(env!("CARGO_MANIFEST_DIR")).join(
        "../../specs/017-rust-native-inference-runtime/fixtures/f017-independent-oracle-v1.json",
    );
    let status = Command::new(env!("CARGO_BIN_EXE_f017-glm52-runner"))
        .args(common_args(&fixture.environment, &out))
        .arg("--fixture-mode")
        .arg(oracle)
        .args(["--numerical-mode", "production-mlx-tier-b"])
        .status()
        .unwrap();
    assert!(status.success());
    let evidence: Evidence = parse_json_no_duplicates(&fs::read(&out).unwrap()).unwrap();
    assert_eq!(
        evidence.execution.numerical_classification,
        Some(f017_runner::numerical_classification::NumericalClassification::GoldenIdentical)
    );
    assert_eq!(evidence.execution.dispatch.native, 1);
    assert_eq!(evidence.execution.dispatch.qualification_scaffold, 0);
    assert_eq!(evidence.execution.dispatch.fallback, 0);
    assert!(evidence.lifecycle.reconciled);
    assert!(!evidence.identity.checkpoint.accessed);
    assert_eq!(
        evidence.input.numerical_mode.as_deref(),
        Some("production_mlx_tier_b")
    );
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
#[test]
fn actual_binary_keeps_exact_scaffold_explicit_and_separate() {
    let fixture = fixture(false);
    let out = fixture.root.join("projection-exact.json");
    let oracle = Path::new(env!("CARGO_MANIFEST_DIR")).join(
        "../../specs/017-rust-native-inference-runtime/fixtures/f017-independent-oracle-v1.json",
    );
    let status = Command::new(env!("CARGO_BIN_EXE_f017-glm52-runner"))
        .args(common_args(&fixture.environment, &out))
        .arg("--fixture-mode")
        .arg(oracle)
        .args(["--numerical-mode", "exact-qualification-scaffold"])
        .status()
        .unwrap();
    assert!(status.success());
    let evidence: Evidence = parse_json_no_duplicates(&fs::read(&out).unwrap()).unwrap();
    assert_eq!(
        evidence.input.numerical_mode.as_deref(),
        Some("exact_qualification_scaffold")
    );
    assert_eq!(evidence.execution.dispatch.qualification_scaffold, 1);
    assert_eq!(evidence.execution.dispatch.native, 0);
    assert_eq!(evidence.execution.dispatch.fallback, 0);
    assert_eq!(
        evidence.execution.numerical_classification,
        Some(f017_runner::numerical_classification::NumericalClassification::GoldenIdentical)
    );
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
#[test]
fn actual_binary_runs_r12_tiny_model_in_exact_and_production_modes() {
    let fixture = fixture(false);
    let model = Path::new(env!("CARGO_MANIFEST_DIR")).join(
        "../../specs/017-rust-native-inference-runtime/fixtures/f017-r12-tiny-model/model.json",
    );

    let exact_out = fixture.root.join("r12-exact.json");
    let exact_status = Command::new(env!("CARGO_BIN_EXE_f017-glm52-runner"))
        .args(common_args(&fixture.environment, &exact_out))
        .arg("--fixture-mode")
        .arg(&model)
        .args(["--numerical-mode", "exact-qualification-scaffold"])
        .status()
        .unwrap();
    assert!(exact_status.success());
    let exact: Evidence = parse_json_no_duplicates(&fs::read(&exact_out).unwrap()).unwrap();
    exact.validate().unwrap();
    assert_eq!(exact.execution.generated_token, Some(10));
    assert_eq!(exact.input.tokens, vec![3]);
    assert_eq!(exact.input.n_new, 1);
    assert_eq!(exact.input.expected_token, Some(10));
    assert_eq!(exact.execution.layers.len(), 2);
    assert!(exact
        .execution
        .layers
        .iter()
        .all(|layer| layer.total_seconds > 0.0));
    assert_eq!(exact.execution.dispatch.qualification_scaffold, 690);
    assert_eq!(exact.execution.dispatch.fallback, 0);
    assert!(exact.lifecycle.reconciled);

    let production_out = fixture.root.join("r12-production.json");
    let production_status = Command::new(env!("CARGO_BIN_EXE_f017-glm52-runner"))
        .args(common_args(&fixture.environment, &production_out))
        .arg("--fixture-mode")
        .arg(&model)
        .args(["--numerical-mode", "production-mlx-tier-b"])
        .status()
        .unwrap();
    assert!(production_status.success());
    let production: Evidence =
        parse_json_no_duplicates(&fs::read(&production_out).unwrap()).unwrap();
    production.validate().unwrap();
    assert_eq!(production.execution.generated_token, Some(10));
    assert_eq!(
        production.execution.numerical_classification,
        Some(
            f017_runner::numerical_classification::NumericalClassification::NumericallyQualifiedGreedyIdentical
        )
    );
    assert_eq!(production.execution.dispatch.native, 690);
    assert_eq!(production.execution.dispatch.qualification_scaffold, 0);
    assert_eq!(production.execution.dispatch.explicit_reference, 0);
    assert_eq!(production.execution.dispatch.fallback, 0);
    assert_eq!(production.execution.dispatch.errors, 0);
    assert_eq!(production.residency.decoded_hot, 81);
    assert_eq!(production.residency.misses, 81);
    assert!(production
        .execution
        .layers
        .iter()
        .all(|layer| layer.total_seconds > 0.0));
    assert!(production.lifecycle.reconciled);
    assert!(production.identity.checkpoint.accessed);
    assert_eq!(
        production
            .execution
            .numerical
            .frozen_contract_versions
            .keys()
            .map(String::as_str)
            .collect::<std::collections::BTreeSet<_>>(),
        std::collections::BTreeSet::from([
            "f017-production-expert-tier-b-v1",
            "f017-production-r9-tier-b-v2",
            "f017-production-r10-tier-b-v2",
            "f017-production-r11-tier-b-v1",
        ])
    );
    let mut missing = production.clone();
    missing
        .execution
        .numerical
        .frozen_contract_versions
        .remove("f017-production-r9-tier-b-v2");
    assert!(missing.validate().is_err());
    let mut stale = production;
    stale
        .execution
        .numerical
        .frozen_contract_versions
        .insert("f017-production-r10-tier-b-v2".to_owned(), "0".repeat(64));
    assert!(stale.validate().is_err());
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
#[test]
fn actual_binary_banks_malformed_r12_manifest_without_false_pass() {
    let fixture = fixture(false);
    let malformed = fixture.root.join("malformed-r12.json");
    fs::write(
        &malformed,
        b"{\"schema\":\"pulsarmlx.f017.r12-tiny-model-oracle\",\"schema\":\"duplicate\"}\n",
    )
    .unwrap();
    let out = fixture.root.join("malformed-r12-evidence.json");
    let status = Command::new(env!("CARGO_BIN_EXE_f017-glm52-runner"))
        .args(common_args(&fixture.environment, &out))
        .arg("--fixture-mode")
        .arg(&malformed)
        .args(["--numerical-mode", "exact-qualification-scaffold"])
        .status()
        .unwrap();
    assert_eq!(status.code(), Some(14));
    let evidence: Evidence = parse_json_no_duplicates(&fs::read(&out).unwrap()).unwrap();
    assert_eq!(
        evidence.result.classification,
        f017_runner::evidence::ResultClassification::FailInfrastructureEvidence
    );
    assert!(!evidence.identity.checkpoint.accessed);
    assert!(!evidence.result.completed || evidence.result.first_failure.is_some());
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
#[test]
fn actual_binary_cancels_r12_before_and_between_layers_without_false_pass() {
    let fixture = fixture(false);
    let model = Path::new(env!("CARGO_MANIFEST_DIR")).join(
        "../../specs/017-rust-native-inference-runtime/fixtures/f017-r12-tiny-model/model.json",
    );
    for (case, point) in [
        ("before-first-layer", "before_first_layer"),
        ("after-layer-0", "after_layer_0"),
    ] {
        let out = fixture.root.join(format!("r12-cancel-{case}.json"));
        let status = Command::new(env!("CARGO_BIN_EXE_f017-glm52-runner"))
            .args(common_args(&fixture.environment, &out))
            .arg("--fixture-mode")
            .arg(&model)
            .args(["--numerical-mode", "exact-qualification-scaffold"])
            .env("PULSAR_F017_FIXTURE_CANCEL_AT", point)
            .status()
            .unwrap();
        assert_eq!(status.code(), Some(15));
        let evidence: Evidence = parse_json_no_duplicates(&fs::read(&out).unwrap()).unwrap();
        assert_eq!(
            evidence.result.classification,
            f017_runner::evidence::ResultClassification::Cancelled
        );
        assert_eq!(
            evidence.result.first_failure.as_ref().unwrap().code,
            "r12_cancelled"
        );
        assert_ne!(
            evidence.result.classification,
            f017_runner::evidence::ResultClassification::Pass
        );
        assert!(evidence.lifecycle.reconciled);
        assert_eq!(evidence.execution.dispatch.fallback, 0);
    }
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
#[test]
fn actual_binary_banks_backend_failure_after_reconciling_adapter_lifecycle() {
    let fixture = fixture(false);
    let model = Path::new(env!("CARGO_MANIFEST_DIR")).join(
        "../../specs/017-rust-native-inference-runtime/fixtures/f017-r12-tiny-model/model.json",
    );
    let out = fixture.root.join("r12-backend-error.json");
    let status = Command::new(env!("CARGO_BIN_EXE_f017-glm52-runner"))
        .args(common_args(&fixture.environment, &out))
        .arg("--fixture-mode")
        .arg(&model)
        .args(["--numerical-mode", "production-mlx-tier-b"])
        .env("PULSAR_F017_FIXTURE_BACKEND_ERROR", "1")
        .status()
        .unwrap();
    assert_eq!(status.code(), Some(14));
    let evidence: Evidence = parse_json_no_duplicates(&fs::read(&out).unwrap()).unwrap();
    assert_eq!(
        evidence.result.classification,
        f017_runner::evidence::ResultClassification::FailInfrastructureEvidence
    );
    assert_eq!(
        evidence.result.first_failure.as_ref().unwrap().code,
        "r12_backend_error"
    );
    assert!(evidence.lifecycle.reconciled);
    assert_eq!(evidence.lifecycle.post.owned_stream_created, 1);
    assert_eq!(evidence.lifecycle.post.owned_stream_freed, 1);
    assert!(!evidence.lifecycle.post.singleton_claimed);
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
#[test]
fn actual_binary_fails_closed_on_r12_tensor_contract_corruption() {
    for mutation in ["missing_tensor", "wrong_shape", "unsupported_quantization"] {
        let fixture = fixture(false);
        let model = copy_r12_model(&fixture.root);
        let mut document: serde_json::Value =
            parse_json_no_duplicates(&fs::read(&model).unwrap()).unwrap();
        let contracts = document["tensor_contracts"].as_array_mut().unwrap();
        match mutation {
            "missing_tensor" => {
                contracts.remove(0);
            }
            "wrong_shape" => {
                contracts[0]["dims"] = serde_json::json!([255, 16]);
            }
            "unsupported_quantization" => {
                contracts[0]["type_id"] = serde_json::json!(999);
            }
            _ => unreachable!(),
        }
        fs::write(&model, serde_json::to_vec_pretty(&document).unwrap()).unwrap();
        let out = fixture.root.join(format!("r12-{mutation}.json"));
        let status = Command::new(env!("CARGO_BIN_EXE_f017-glm52-runner"))
            .args(common_args(&fixture.environment, &out))
            .arg("--fixture-mode")
            .arg(&model)
            .args(["--numerical-mode", "exact-qualification-scaffold"])
            .status()
            .unwrap();
        assert!(!status.success());
        let evidence: Evidence = parse_json_no_duplicates(&fs::read(&out).unwrap()).unwrap();
        assert_ne!(
            evidence.result.classification,
            f017_runner::evidence::ResultClassification::Pass
        );
        assert!(evidence.result.first_failure.is_some());
    }
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
#[test]
fn actual_binary_rejects_truncated_r12_shard_before_execution() {
    let fixture = fixture(false);
    let model = copy_r12_model(&fixture.root);
    let shard = model
        .parent()
        .unwrap()
        .join("f017-r12-00001-of-00002.fixture");
    let length = fs::metadata(&shard).unwrap().len();
    fs::OpenOptions::new()
        .write(true)
        .open(&shard)
        .unwrap()
        .set_len(length - 1)
        .unwrap();
    let out = fixture.root.join("r12-truncated-shard.json");
    let status = Command::new(env!("CARGO_BIN_EXE_f017-glm52-runner"))
        .args(common_args(&fixture.environment, &out))
        .arg("--fixture-mode")
        .arg(&model)
        .args(["--numerical-mode", "exact-qualification-scaffold"])
        .status()
        .unwrap();
    assert_eq!(status.code(), Some(11));
    let evidence: Evidence = parse_json_no_duplicates(&fs::read(&out).unwrap()).unwrap();
    assert_eq!(
        evidence.result.classification,
        f017_runner::evidence::ResultClassification::FailCheckpointIdentity
    );
    assert_eq!(evidence.execution.dispatch.native, 0);
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn copy_r12_model(root: &Path) -> PathBuf {
    let source = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../specs/017-rust-native-inference-runtime/fixtures/f017-r12-tiny-model");
    let destination = root.join(format!(
        "r12-model-copy-{}",
        NEXT_FIXTURE_ID.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir(&destination).unwrap();
    for name in [
        "model.json",
        "checkpoint.json",
        "f017-r12-00001-of-00002.fixture",
        "f017-r12-00002-of-00002.fixture",
    ] {
        fs::copy(source.join(name), destination.join(name)).unwrap();
    }
    destination.join("model.json")
}

fn common_args(environment: &Path, out: &Path) -> Vec<std::ffi::OsString> {
    [
        "--out".into(),
        out.as_os_str().to_owned(),
        "--validation-mode".into(),
        "golden-strict".into(),
        "--stream-mode".into(),
        "owned-device".into(),
        "--memory-floor-bytes".into(),
        "17179869184".into(),
        "--environment-manifest".into(),
        environment.as_os_str().to_owned(),
    ]
    .into()
}

fn fixture(duplicate_name: bool) -> Fixture {
    let suffix = NEXT_FIXTURE_ID.fetch_add(1, Ordering::Relaxed);
    let root = std::env::temp_dir().join(format!(
        "f017-runner-fixture-{}-{suffix}",
        std::process::id()
    ));
    fs::create_dir(&root).unwrap();
    let first_payload = [1.0_f32, 2.0, 3.0, 4.0]
        .into_iter()
        .flat_map(f32::to_le_bytes)
        .collect::<Vec<_>>();
    let second_payload = [5.0_f32, 6.0, 7.0, 8.0]
        .into_iter()
        .flat_map(f32::to_le_bytes)
        .collect::<Vec<_>>();
    let first = make_gguf("token_embd.weight", &first_payload, true);
    let second_name = if duplicate_name {
        "token_embd.weight"
    } else {
        "output.weight"
    };
    let second = make_gguf(second_name, &second_payload, false);
    let first_name = "fixture-00001-of-00002.gguf";
    let second_name_file = "fixture-00002-of-00002.gguf";
    let first_shard = root.join(first_name);
    fs::write(&first_shard, &first).unwrap();
    fs::write(root.join(second_name_file), &second).unwrap();

    let first_sha = sha256_bytes(&first);
    let second_sha = sha256_bytes(&second);
    let mut set = Sha256::new();
    set.update(first_sha.as_bytes());
    set.update(first.len().to_string().as_bytes());
    set.update(second_sha.as_bytes());
    set.update(second.len().to_string().as_bytes());
    let headers = vec![Gguf::parse(&first).unwrap(), Gguf::parse(&second).unwrap()];
    let merged = Gguf::merge_split(headers, &[0, first.len() as u64]);
    let manifest = CheckpointManifest {
        schema: "pulsarmlx.f017.checkpoint-manifest".to_owned(),
        schema_version: "1.0.0".to_owned(),
        kind: CheckpointKind::Fixture,
        immutable_revision: "fixture-v1".to_owned(),
        architecture: "glm-dsa".to_owned(),
        tokenizer_identity: "exact-token-ids".to_owned(),
        checkpoint_set_sha256: format!("{:x}", set.finalize()),
        catalog_sha256: catalog_sha256(&merged.tensors),
        tensor_count: 2,
        shards: vec![
            CheckpointShard {
                filename: first_name.to_owned(),
                size_bytes: first.len() as u64,
                sha256: first_sha,
            },
            CheckpointShard {
                filename: second_name_file.to_owned(),
                size_bytes: second.len() as u64,
                sha256: second_sha,
            },
        ],
    };
    let manifest_path = root.join("checkpoint.json");
    fs::write(
        &manifest_path,
        serde_json::to_vec_pretty(&manifest).unwrap(),
    )
    .unwrap();
    let environment = root.join("environment.json");
    fs::write(
        &environment,
        format!(
            "{{\"schema\":\"pulsarmlx.f017.fixture-environment\",\"schema_version\":1,\"architecture\":\"{}\",\"purpose\":\"checkpoint_free_ci\"}}\n",
            std::env::consts::ARCH
        ),
    )
    .unwrap();
    Fixture {
        root,
        manifest: manifest_path,
        environment,
        first_shard,
        first_payload,
    }
}

fn make_gguf(name: &str, payload: &[u8], architecture: bool) -> Vec<u8> {
    let mut bytes = Vec::new();
    bytes.extend_from_slice(&GGUF_MAGIC.to_le_bytes());
    bytes.extend_from_slice(&3_u32.to_le_bytes());
    bytes.extend_from_slice(&1_u64.to_le_bytes());
    bytes.extend_from_slice(&(u64::from(architecture)).to_le_bytes());
    if architecture {
        push_string(&mut bytes, "general.architecture");
        bytes.extend_from_slice(&8_u32.to_le_bytes());
        push_string(&mut bytes, "glm-dsa");
    }
    push_string(&mut bytes, name);
    bytes.extend_from_slice(&2_u32.to_le_bytes());
    bytes.extend_from_slice(&2_u64.to_le_bytes());
    bytes.extend_from_slice(&2_u64.to_le_bytes());
    bytes.extend_from_slice(&0_u32.to_le_bytes());
    bytes.extend_from_slice(&0_u64.to_le_bytes());
    while bytes.len() % 32 != 0 {
        bytes.push(0);
    }
    bytes.extend_from_slice(payload);
    bytes
}

fn push_string(bytes: &mut Vec<u8>, value: &str) {
    bytes.extend_from_slice(&(value.len() as u64).to_le_bytes());
    bytes.extend_from_slice(value.as_bytes());
}
