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

pub fn validate_static(contract: &RealP1Contract, repo_root: &Path) -> Result<(), String> {
    if contract.schema != CONTRACT_SCHEMA
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
    if one.attempt_id != "F017-NATIVE-BOUNDED-P1-ATTEMPT-1"
        || one.prompt_token != 9703
        || one.expected_token != 21615
        || one.attempts != 1
        || one.retries != 0
        || one.resume
        || !one.mandatory_stop
        || one.generated_token_limit != 1
        || one.sequence_position != 0
        || one.initial_kv_state != "EMPTY_CLEAN_PROCESS"
        || one.receipt_schema != stream::RECEIPT_SCHEMA
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
