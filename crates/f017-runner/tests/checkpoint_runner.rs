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
use std::time::{SystemTime, UNIX_EPOCH};

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
        .args(["--checkpoint-identity-only", "--checkpoint-manifest"])
        .arg(&fixture.manifest)
        .status()
        .unwrap();
    assert!(status.success());
    let identity: Evidence = parse_json_no_duplicates(&fs::read(&identity_out).unwrap()).unwrap();
    assert_eq!(identity.input.mode, "checkpoint_identity");
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
    let public_json = fs::read_to_string(&identity_out).unwrap();
    assert!(!public_json.contains(fixture.root.to_str().unwrap()));
}

#[test]
fn unsupported_p1_fails_before_checkpoint_access_and_banks_failure() {
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
        ])
        .status()
        .unwrap();
    assert_eq!(status.code(), Some(14));
    let evidence: Evidence = parse_json_no_duplicates(&fs::read(&out).unwrap()).unwrap();
    assert!(!evidence.identity.checkpoint.accessed);
    assert_eq!(
        evidence.result.first_failure.unwrap().code,
        "p1_not_admitted"
    );
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
        .status()
        .unwrap();
    assert!(status.success());
    let evidence: Evidence = parse_json_no_duplicates(&fs::read(&out).unwrap()).unwrap();
    assert_eq!(
        evidence.execution.numerical_classification.as_deref(),
        Some("golden_identical")
    );
    assert_eq!(evidence.execution.dispatch.native, 1);
    assert_eq!(evidence.execution.dispatch.fallback, 0);
    assert!(evidence.lifecycle.reconciled);
    assert!(!evidence.identity.checkpoint.accessed);
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
    let suffix = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
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
    fs::write(&environment, b"{\"schema\":\"fixture-environment-v1\"}\n").unwrap();
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
