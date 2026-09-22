//! Exact static and machine-local admission contract for one future P1.
//! Static validation never opens checkpoint shards and cannot mint authority.

use crate::loader::{load_plan_only, ShardIdentity};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File};
use std::io::Read;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::Command;

pub const CONTRACT_SCHEMA: &str = "pulsarmlx.f017.native-bounded-p1-admission-contract/2.0.0";
/// Generation 3 (attempt 2): identical census, machine, checkpoint and
/// authority rules as generation 2, with the one-shot bound to the corrected
/// oracle's expected token and the evidenced v4 receipt. Generation 2 stays
/// exactly as frozen for attempt 1; a generation-3 contract must additionally
/// bind the corrected-oracle binding document.
pub const CONTRACT_SCHEMA_V3: &str = "pulsarmlx.f017.native-bounded-p1-admission-contract/3.0.0";
pub const ATTEMPT_2_ID: &str = "F017-NATIVE-BOUNDED-P1-ATTEMPT-2";
/// Event 06 (sequence 43) corrected full-checkpoint oracle result for prompt
/// 9703 at position 0: primary and secondary both select 154820.
pub const CORRECTED_EXPECTED_TOKEN: u32 = 154_820;
pub const MINIMUM_AVAILABLE_MEMORY_BYTES: u64 = 17_179_869_184;

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FileBinding {
    pub path: String,
    pub sha256: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AuthorityBindings {
    pub cross_branch_authority: FileBinding,
    pub execution_architecture: FileBinding,
    pub runtime_provenance: FileBinding,
    pub d0: FileBinding,
    pub d1: FileBinding,
    pub d2: FileBinding,
    pub retention_reuse_grant: FileBinding,
    pub comparison_read_grant: FileBinding,
    pub d3_5_result: FileBinding,
    pub d3_5_acceptance: FileBinding,
    pub synthetic_full_graph_result: FileBinding,
    pub historical_master_ledger_sha256: String,
    pub historical_master_terminal_value: u64,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CheckpointBinding {
    pub root_environment: String,
    pub manifest: FileBinding,
    pub catalog: FileBinding,
    pub checkpoint_set_sha256: String,
    pub fallback: String,
    pub shards: Vec<ShardIdentity>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RuntimeBinding {
    pub machine_brand: String,
    pub architecture: String,
    pub macos_build: String,
    pub mlx_version: String,
    pub mlx_c_version: String,
    pub rustc_version: String,
    pub build_profile: String,
    pub minimum_available_memory_bytes: u64,
    pub memory_sample_max_age_seconds: u64,
    pub dylibs: Vec<FileBinding>,
    pub environment: BTreeMap<String, String>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OneShotBinding {
    pub attempt_id: String,
    pub prompt_token: u32,
    pub expected_token: u32,
    pub attempts: u32,
    pub retries: u32,
    pub resume: bool,
    pub mandatory_stop: bool,
    pub generated_token_limit: u32,
    pub sequence_position: u32,
    pub initial_kv_state: String,
    pub receipt_schema: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RealP1Contract {
    pub schema: String,
    /// Generation 3 only: the corrected-oracle binding document (attempt 2).
    #[serde(default)]
    pub corrected_oracle_binding: Option<FileBinding>,
    pub status: String,
    pub branch: String,
    pub execution_code_head: String,
    pub executor: FileBinding,
    pub code_manifest: Vec<FileBinding>,
    pub authorities: AuthorityBindings,
    pub checkpoint: CheckpointBinding,
    pub runtime: RuntimeBinding,
    pub one_shot: OneShotBinding,
    pub state_root: String,
    pub live_authorization_present: bool,
    pub normal_validation_can_authorize: bool,
}

pub fn sha256(path: &Path) -> Result<String, String> {
    let mut file = File::open(path).map_err(|e| e.to_string())?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let count = file.read(&mut buffer).map_err(|e| e.to_string())?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    Ok(format!("{:x}", digest.finalize()))
}

pub fn load(path: &Path) -> Result<(RealP1Contract, String), String> {
    let raw = fs::read(path).map_err(|e| e.to_string())?;
    let contract = crate::json::parse_json_no_duplicates(&raw)?;
    Ok((contract, format!("{:x}", Sha256::digest(raw))))
}

fn repo_path(root: &Path, binding: &FileBinding) -> Result<PathBuf, String> {
    let relative = Path::new(&binding.path);
    if relative.is_absolute()
        || relative
            .components()
            .any(|part| matches!(part, std::path::Component::ParentDir))
    {
        return Err("unsafe repository binding path".into());
    }
    let path = root.join(relative);
    let canonical_root = root.canonicalize().map_err(|e| e.to_string())?;
    let canonical = path.canonicalize().map_err(|e| e.to_string())?;
    if !canonical.starts_with(&canonical_root)
        || fs::symlink_metadata(&path)
            .map_err(|e| e.to_string())?
            .file_type()
            .is_symlink()
        || sha256(&path)? != binding.sha256
    {
        return Err(format!("repository binding mismatch {}", binding.path));
    }
    Ok(path)
}

/// Contract generation by schema: 2 = attempt 1 (frozen), 3 = attempt 2.
pub fn contract_generation(schema: &str) -> Option<u8> {
    match schema {
        CONTRACT_SCHEMA => Some(2),
        CONTRACT_SCHEMA_V3 => Some(3),
        _ => None,
    }
}

pub fn validate_static(contract: &RealP1Contract, repo_root: &Path) -> Result<(), String> {
    let generation =
        contract_generation(&contract.schema).ok_or("contract root authority mismatch")?;
    if (generation == 2) != contract.corrected_oracle_binding.is_none()
        || contract.status != "PREPARED_HUMAN_GATE_REQUIRED"
        || contract.branch != "feat/017-rust-native-inference-runtime"
        || contract.execution_code_head.len() != 40
        || contract.live_authorization_present
        || contract.normal_validation_can_authorize
        || contract.authorities.historical_master_ledger_sha256
            != "aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e"
        || contract.authorities.historical_master_terminal_value != 175
    {
        return Err("contract root authority mismatch".into());
    }
    for binding in contract.code_manifest.iter().chain([
        &contract.executor,
        &contract.authorities.cross_branch_authority,
        &contract.authorities.execution_architecture,
        &contract.authorities.runtime_provenance,
        &contract.authorities.d0,
        &contract.authorities.d1,
        &contract.authorities.d2,
        &contract.authorities.retention_reuse_grant,
        &contract.authorities.comparison_read_grant,
        &contract.authorities.d3_5_result,
        &contract.authorities.d3_5_acceptance,
        &contract.authorities.synthetic_full_graph_result,
        &contract.checkpoint.manifest,
        &contract.checkpoint.catalog,
    ]) {
        repo_path(repo_root, binding)?;
    }
    let expected_code_manifest = [
        "Cargo.lock",
        "crates/f017-native/Cargo.toml",
        "crates/f017-native/build.rs",
        "crates/f017-native/src/lib.rs",
        "crates/f017-native/src/json.rs",
        "crates/f017-native/src/contract.rs",
        "crates/f017-native/src/executor.rs",
        "crates/f017-native/src/loader.rs",
        "crates/f017-native/src/model.rs",
        "crates/f017-native/src/bin/bounded_p1.rs",
        "crates/gguf/src/lib.rs",
        "crates/quant/build.rs",
        "crates/quant/src/lib.rs",
        "crates/quant/src/cpu_dot.rs",
        "crates/quant/src/cpu_dot_tables.rs",
        "crates/quant/src/extra_ref.rs",
        "crates/quant/src/iq.rs",
        "crates/quant/src/iq_ref.rs",
        "crates/quant/src/q6_k_ref.rs",
        "crates/stream/build.rs",
        "crates/stream/src/lib.rs",
        "crates/stream/src/p1_domain.rs",
        "crates/stream/src/apple_mlx_bridge.rs",
        "crates/stream/src/apple_mlx_bridge.mm",
        "crates/stream/src/apple_mlx_deallocation_observer.mm",
        "scripts/research/f017_native_p1_authorization.py",
    ]
    .into_iter()
    .map(str::to_owned)
    .collect::<BTreeSet<_>>();
    let actual_code_manifest = contract
        .code_manifest
        .iter()
        .map(|binding| binding.path.clone())
        .collect::<BTreeSet<_>>();
    if actual_code_manifest.len() != contract.code_manifest.len()
        || actual_code_manifest != expected_code_manifest
    {
        return Err("execution code manifest census mismatch".into());
    }
    let executor = repo_path(repo_root, &contract.executor)?;
    let executor_metadata = fs::metadata(&executor).map_err(|e| e.to_string())?;
    if !executor_metadata.is_file() || executor_metadata.permissions().mode() & 0o111 == 0 {
        return Err("bound executor is not a regular executable".into());
    }
    let (manifest, _catalog) = load_plan_only(
        &repo_root.join(&contract.checkpoint.manifest.path),
        &repo_root.join(&contract.checkpoint.catalog.path),
    )?;
    if contract.checkpoint.root_environment != "PULSARMLX_GLM_GGUF"
        || contract.checkpoint.fallback != "PROHIBITED"
        || contract.checkpoint.checkpoint_set_sha256 != manifest.checkpoint_set_sha256
        || contract.checkpoint.shards.len() != 6
        || contract
            .checkpoint
            .shards
            .iter()
            .zip(&manifest.files)
            .any(|(a, b)| {
                a.filename != b.filename || a.sha256 != b.sha256 || a.size_bytes != b.size_bytes
            })
    {
        return Err("checkpoint authority mismatch".into());
    }
    let one = &contract.one_shot;
    let (attempt_id, expected_token, receipt_schema) = if generation == 2 {
        (
            "F017-NATIVE-BOUNDED-P1-ATTEMPT-1",
            21615_u32,
            stream::RECEIPT_SCHEMA,
        )
    } else {
        (
            ATTEMPT_2_ID,
            CORRECTED_EXPECTED_TOKEN,
            stream::EVIDENCED_RECEIPT_SCHEMA,
        )
    };
    if generation == 3 {
        let binding = contract
            .corrected_oracle_binding
            .as_ref()
            .ok_or("corrected oracle binding missing")?;
        let path = repo_path(repo_root, binding)?;
        let document: serde_json::Value =
            crate::json::parse_json_no_duplicates(&fs::read(&path).map_err(|e| e.to_string())?)?;
        if document.get("attempt_id").and_then(|v| v.as_str()) != Some(ATTEMPT_2_ID)
            || document.get("expected_token").and_then(|v| v.as_u64())
                != Some(u64::from(CORRECTED_EXPECTED_TOKEN))
            || document.get("acceptance_mode").and_then(|v| v.as_str())
                != Some("EXACT_EXPECTED_TOKEN_STABLE")
            || document
                .get("live_authorization_created")
                .and_then(|v| v.as_bool())
                != Some(false)
            || document
                .pointer("/corrected_oracle_event/primary_selected_token")
                .and_then(|v| v.as_u64())
                != Some(u64::from(CORRECTED_EXPECTED_TOKEN))
            || document
                .pointer("/corrected_oracle_event/secondary_selected_token")
                .and_then(|v| v.as_u64())
                != Some(u64::from(CORRECTED_EXPECTED_TOKEN))
        {
            return Err("corrected oracle binding mismatch".into());
        }
    }
    if one.attempt_id != attempt_id
        || one.prompt_token != 9703
        || one.expected_token != expected_token
        || one.attempts != 1
        || one.retries != 0
        || one.resume
        || !one.mandatory_stop
        || one.generated_token_limit != 1
        || one.sequence_position != 0
        || one.initial_kv_state != "EMPTY_CLEAN_PROCESS"
        || one.receipt_schema != receipt_schema
    {
        return Err("one-shot authority mismatch".into());
    }
    let runtime = &contract.runtime;
    if runtime.machine_brand != "Apple M1 Ultra"
        || runtime.architecture != "arm64"
        || runtime.mlx_version != "0.31.2"
        || runtime.mlx_c_version != "0.6.0"
        || runtime.build_profile != "release"
        || runtime.minimum_available_memory_bytes != MINIMUM_AVAILABLE_MEMORY_BYTES
        || runtime.memory_sample_max_age_seconds != 5
        || runtime
            .environment
            .get("PULSAR_REQUIRE_NATIVE_MLX")
            .map(String::as_str)
            != Some("1")
    {
        return Err("runtime authority mismatch".into());
    }
    if !Path::new(&contract.state_root).is_absolute() {
        return Err("state root is not absolute".into());
    }
    validate_state_root(Path::new(&contract.state_root))?;
    Ok(())
}

fn validate_state_root(path: &Path) -> Result<(), String> {
    let parent = path.parent().ok_or("state root has no parent")?;
    let resolved_parent = parent.canonicalize().map_err(|e| e.to_string())?;
    if resolved_parent.join(path.file_name().ok_or("state root leaf")?) != path {
        return Err("state root contains an alternate or symlinked ancestor".into());
    }
    if path.exists() {
        let metadata = fs::symlink_metadata(path).map_err(|e| e.to_string())?;
        if metadata.file_type().is_symlink() || !metadata.is_dir() {
            return Err("state root is not a real directory".into());
        }
        if metadata.permissions().mode() & 0o077 != 0 {
            return Err("state root permissions are not private".into());
        }
    }
    Ok(())
}

fn command_stdout(program: &str, args: &[&str]) -> Result<String, String> {
    let output = Command::new(program)
        .args(args)
        .output()
        .map_err(|e| e.to_string())?;
    if !output.status.success() {
        return Err(format!("{program} failed"));
    }
    String::from_utf8(output.stdout)
        .map(|s| s.trim_end_matches(['\r', '\n']).to_owned())
        .map_err(|e| e.to_string())
}

pub fn available_memory_bytes_from_vm_stat(text: &str) -> Result<u64, String> {
    let page_size = text
        .lines()
        .next()
        .and_then(|line| line.split("page size of ").nth(1))
        .and_then(|tail| tail.split_whitespace().next())
        .and_then(|v| v.parse::<u64>().ok())
        .ok_or("vm_stat page size")?;
    let mut pages = BTreeMap::<&str, u64>::new();
    for line in text.lines().skip(1) {
        if let Some((name, value)) = line.split_once(':') {
            if let Ok(count) = value.trim().trim_end_matches('.').parse::<u64>() {
                pages.insert(name, count);
            }
        }
    }
    let count = ["Pages free", "Pages inactive", "Pages speculative"]
        .iter()
        .try_fold(0_u64, |sum, key| {
            pages
                .get(key)
                .and_then(|v| sum.checked_add(*v))
                .ok_or("vm_stat census")
        })?;
    count
        .checked_mul(page_size)
        .ok_or("vm_stat overflow".into())
}

pub fn validate_machine(contract: &RealP1Contract) -> Result<u64, String> {
    if command_stdout("/usr/sbin/sysctl", &["-n", "machdep.cpu.brand_string"])?
        != contract.runtime.machine_brand
        || std::env::consts::ARCH != "aarch64"
    {
        return Err("machine identity mismatch".into());
    }
    if command_stdout("/usr/bin/sw_vers", &["-buildVersion"])? != contract.runtime.macos_build {
        return Err("macOS build mismatch".into());
    }
    if command_stdout("/opt/homebrew/bin/rustc", &["--version"])? != contract.runtime.rustc_version
    {
        return Err("rustc identity mismatch".into());
    }
    for binding in &contract.runtime.dylibs {
        let path = Path::new(&binding.path);
        if !path.is_absolute()
            || fs::symlink_metadata(path)
                .map_err(|e| e.to_string())?
                .file_type()
                .is_symlink()
            || sha256(path)? != binding.sha256
        {
            return Err(format!("runtime dylib mismatch {}", binding.path));
        }
    }
    for (key, value) in &contract.runtime.environment {
        if std::env::var(key).ok().as_deref() != Some(value) {
            return Err(format!("runtime environment mismatch {key}"));
        }
    }
    let available = available_memory_bytes_from_vm_stat(&command_stdout("/usr/bin/vm_stat", &[])?)?;
    if available < contract.runtime.minimum_available_memory_bytes {
        return Err("available memory below 16 GiB".into());
    }
    Ok(available)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn contract_generations_are_closed_and_attempt_2_binds_the_corrected_token() {
        assert_eq!(contract_generation(CONTRACT_SCHEMA), Some(2));
        assert_eq!(contract_generation(CONTRACT_SCHEMA_V3), Some(3));
        assert_eq!(
            contract_generation("pulsarmlx.f017.native-bounded-p1-admission-contract/4.0.0"),
            None
        );
        assert_eq!(contract_generation(""), None);
        assert_eq!(CORRECTED_EXPECTED_TOKEN, 154_820);
        assert_ne!(
            CORRECTED_EXPECTED_TOKEN,
            stream::EXPECTED_TOKEN,
            "attempt 2 must not reuse the defective attempt-1 expected token"
        );
        assert_eq!(ATTEMPT_2_ID, "F017-NATIVE-BOUNDED-P1-ATTEMPT-2");
    }
    #[test]
    fn generation_2_contract_without_binding_and_generation_3_with_binding_parse() {
        let base = serde_json::json!({"schema": CONTRACT_SCHEMA, "status": "x", "branch": "b", "execution_code_head": "h", "executor": {"path": "p", "sha256": "s"}, "code_manifest": [],
            "authorities": {"cross_branch_authority": {"path": "p", "sha256": "s"}, "execution_architecture": {"path": "p", "sha256": "s"}, "runtime_provenance": {"path": "p", "sha256": "s"}, "d0": {"path": "p", "sha256": "s"}, "d1": {"path": "p", "sha256": "s"}, "d2": {"path": "p", "sha256": "s"}, "retention_reuse_grant": {"path": "p", "sha256": "s"}, "comparison_read_grant": {"path": "p", "sha256": "s"}, "d3_5_result": {"path": "p", "sha256": "s"}, "d3_5_acceptance": {"path": "p", "sha256": "s"}, "synthetic_full_graph_result": {"path": "p", "sha256": "s"}, "historical_master_ledger_sha256": "s", "historical_master_terminal_value": 175},
            "checkpoint": {"root_environment": "E", "manifest": {"path": "p", "sha256": "s"}, "catalog": {"path": "p", "sha256": "s"}, "checkpoint_set_sha256": "s", "fallback": "PROHIBITED", "shards": []},
            "runtime": {"machine_brand": "m", "architecture": "arm64", "macos_build": "b", "mlx_version": "v", "mlx_c_version": "v", "rustc_version": "r", "build_profile": "release", "minimum_available_memory_bytes": 1, "memory_sample_max_age_seconds": 5, "dylibs": [], "environment": {}},
            "one_shot": {"attempt_id": "a", "prompt_token": 9703, "expected_token": 1, "attempts": 1, "retries": 0, "resume": false, "mandatory_stop": true, "generated_token_limit": 1, "sequence_position": 0, "initial_kv_state": "k", "receipt_schema": "r"},
            "state_root": "/x", "live_authorization_present": false, "normal_validation_can_authorize": false});
        let v2: RealP1Contract = serde_json::from_value(base.clone()).unwrap();
        assert!(v2.corrected_oracle_binding.is_none());
        let mut v3 = base;
        v3["schema"] = serde_json::Value::String(CONTRACT_SCHEMA_V3.into());
        v3["corrected_oracle_binding"] = serde_json::json!({"path": "p", "sha256": "s"});
        let v3: RealP1Contract = serde_json::from_value(v3).unwrap();
        assert_eq!(v3.corrected_oracle_binding.unwrap().path, "p");
    }
    #[test]
    fn vm_stat_parser_is_strict_and_includes_no_caller_claim() {
        let text="Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free: 500000.\nPages inactive: 500000.\nPages speculative: 100000.\n";
        assert_eq!(
            available_memory_bytes_from_vm_stat(text).unwrap(),
            18_022_400_000
        );
        assert!(available_memory_bytes_from_vm_stat("caller says 999999999999").is_err());
        assert!(available_memory_bytes_from_vm_stat(
            "Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free: 1.\n"
        )
        .is_err());
    }
}
