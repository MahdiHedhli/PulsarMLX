use crate::json::parse_json_no_duplicates;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, OpenOptions};
use std::io::Read;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};

pub const CONSUMER_ID: &str = "F017-NATIVE-REPRESENTATIVE-LAYER3-QUALIFICATION-1";
pub const GRANT_SCHEMA: &str = "pulsarmlx.f017.native-retained-reuse-grant/1.0.0";
pub const PACKAGE_SCHEMA: &str = "pulsarmlx.f017.apple-production-serial-f32-package";

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AllowedRead {
    pub ordinal: usize,
    pub role: String,
    pub path: PathBuf,
    pub byte_count: u64,
    pub sha256: String,
    pub encoding: String,
    pub shape: Vec<usize>,
    pub source_branch: String,
    pub source_commit: String,
    pub source_authority_path: String,
    pub source_authority_sha256: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RetainedReuseGrant {
    pub schema: String,
    pub grant_id: String,
    pub consumer_id: String,
    pub consumer_source_path: String,
    pub consumer_source_sha256: String,
    pub d0_sha256: String,
    pub historical_master_ledger_sha256: String,
    pub package_root_sha256: String,
    pub tensor_count: usize,
    pub total_bytes: u64,
    pub attempts: u32,
    pub checkpoint_fallback: bool,
    pub original_checkpoint_reads: u32,
    pub original_checkpoint_shard_opens: u32,
    pub historical_payload_ledger_delta: u32,
    pub terminal_semantics: String,
    pub allowed_output_root: PathBuf,
    pub allowed_reads: Vec<AllowedRead>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TensorSpec {
    pub path: PathBuf,
    pub sha256: String,
    pub encoding: String,
    pub shape: Vec<usize>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RuntimeSpec {
    pub device: String,
    pub mlx_version: String,
    pub mlx_c_version: String,
    pub libmlx_sha256: String,
    pub libmlxc_sha256: String,
    pub backend: String,
    pub thread_limits: BTreeMap<String, String>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RetainedPackage {
    pub schema: String,
    pub schema_version: String,
    pub graph_version: String,
    pub execution_code_head: String,
    pub fixed_attempt_root: PathBuf,
    pub fixed_capture_root: PathBuf,
    pub tensors: BTreeMap<String, TensorSpec>,
    pub position: usize,
    pub rope_base: f32,
    pub attention_scale: f32,
    pub expert_weight_scale: f32,
    pub heads: usize,
    pub qk_nope: usize,
    pub qk_rope: usize,
    pub kv_lora: usize,
    pub value_dim: usize,
    pub routed_expert_ids: Vec<usize>,
    pub runtime: RuntimeSpec,
    pub checkpoint_paths: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct RetainedReadReceipt {
    pub schema: &'static str,
    pub grant_id: String,
    pub consumer_id: String,
    pub ordinal: usize,
    pub role: String,
    pub path: String,
    pub byte_count: u64,
    pub expected_sha256: String,
    pub before_sha256: String,
    pub consumed_sha256: String,
    pub after_sha256: String,
    pub descriptor_device: u64,
    pub descriptor_inode: u64,
    pub checkpoint_read: bool,
    pub original_checkpoint_shard_open: bool,
}

pub struct GrantedInputs {
    grant: RetainedReuseGrant,
    by_role: BTreeMap<String, AllowedRead>,
    receipts: Vec<RetainedReadReceipt>,
}

pub fn sha256_bytes(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

pub fn load_grant(path: &Path) -> Result<RetainedReuseGrant, String> {
    parse_json_no_duplicates(&fs::read(path).map_err(|e| format!("GRANT_READ:{e}"))?)
}

pub fn load_package(path: &Path) -> Result<RetainedPackage, String> {
    parse_json_no_duplicates(&fs::read(path).map_err(|e| format!("PACKAGE_READ:{e}"))?)
}

impl GrantedInputs {
    pub fn validate(grant: RetainedReuseGrant, package: &RetainedPackage) -> Result<Self, String> {
        if grant.schema != GRANT_SCHEMA
            || grant.consumer_id != CONSUMER_ID
            || grant.attempts != 1
            || grant.checkpoint_fallback
            || grant.original_checkpoint_reads != 0
            || grant.original_checkpoint_shard_opens != 0
            || grant.historical_payload_ledger_delta != 0
            || grant.terminal_semantics != "ONE_ATTEMPT_NO_RETRY_NO_RESUME_COMPLETE_OR_TERMINAL_FAILURE"
            || grant.allowed_reads.len() != 40
            || grant.tensor_count != 40
            || package.tensors.len() != 40
            || package.schema != PACKAGE_SCHEMA
            || package.schema_version != "1.0.0"
            || !package.checkpoint_paths.is_empty()
        {
            return Err("GRANT_OR_PACKAGE_POLICY".into());
        }
        let mut roles = BTreeSet::new();
        let mut total = 0_u64;
        let mut by_role = BTreeMap::new();
        for (ordinal, read) in grant.allowed_reads.iter().enumerate() {
            if read.ordinal != ordinal
                || !roles.insert(read.role.clone())
                || read.sha256.len() != 64
                || read.source_authority_sha256.len() != 64
                || read.source_commit.len() != 40
                || read.source_branch != "feat/017-real-checkpoint-runner"
            {
                return Err("GRANT_READ_CENSUS".into());
            }
            let tensor = package
                .tensors
                .get(&read.role)
                .ok_or_else(|| format!("GRANT_ROLE:{}", read.role))?;
            if tensor.path != read.path
                || tensor.sha256 != read.sha256
                || tensor.encoding != read.encoding
                || tensor.shape != read.shape
            {
                return Err(format!("GRANT_PACKAGE_MISMATCH:{}", read.role));
            }
            total = total.checked_add(read.byte_count).ok_or("GRANT_TOTAL_OVERFLOW")?;
            by_role.insert(read.role.clone(), read.clone());
        }
        if total != grant.total_bytes || roles.len() != package.tensors.len() {
            return Err("GRANT_TOTAL_OR_ROLE_CENSUS".into());
        }
        Ok(Self {
            grant,
            by_role,
            receipts: Vec::new(),
        })
    }

    pub fn read(&mut self, role: &str) -> Result<Vec<u8>, String> {
        let allowed = self
            .by_role
            .get(role)
            .ok_or_else(|| format!("UNAUTHORIZED_RETAINED_READ:{role}"))?
            .clone();
        let before = fs::symlink_metadata(&allowed.path).map_err(|e| format!("READ_STAT:{e}"))?;
        if before.file_type().is_symlink()
            || !before.file_type().is_file()
            || before.nlink() != 1
            || before.mode() & 0o222 != 0
            || before.len() != allowed.byte_count
        {
            return Err(format!("READ_POLICY:{role}"));
        }
        let mut file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW)
            .open(&allowed.path)
            .map_err(|e| format!("READ_OPEN:{e}"))?;
        let opened = file.metadata().map_err(|e| format!("READ_FSTAT:{e}"))?;
        if before.dev() != opened.dev() || before.ino() != opened.ino() {
            return Err(format!("READ_DESCRIPTOR_SUBSTITUTION:{role}"));
        }
        let mut bytes = Vec::with_capacity(allowed.byte_count as usize);
        file.read_to_end(&mut bytes)
            .map_err(|e| format!("READ_BYTES:{e}"))?;
        let before_sha = sha256_bytes(&bytes);
        if before_sha != allowed.sha256 || bytes.len() as u64 != allowed.byte_count {
            return Err(format!("READ_IDENTITY:{role}"));
        }
        let after = file.metadata().map_err(|e| format!("READ_AFTER:{e}"))?;
        if opened.dev() != after.dev()
            || opened.ino() != after.ino()
            || opened.len() != after.len()
        {
            return Err(format!("READ_AFTER_IDENTITY:{role}"));
        }
        let after_sha = sha256_bytes(&bytes);
        self.receipts.push(RetainedReadReceipt {
            schema: "pulsarmlx.f017.native-retained-read-receipt/1.0.0",
            grant_id: self.grant.grant_id.clone(),
            consumer_id: self.grant.consumer_id.clone(),
            ordinal: allowed.ordinal,
            role: role.to_owned(),
            path: allowed.path.display().to_string(),
            byte_count: allowed.byte_count,
            expected_sha256: allowed.sha256,
            before_sha256: before_sha.clone(),
            consumed_sha256: before_sha,
            after_sha256: after_sha,
            descriptor_device: opened.dev(),
            descriptor_inode: opened.ino(),
            checkpoint_read: false,
            original_checkpoint_shard_open: false,
        });
        Ok(bytes)
    }

    pub fn receipts(&self) -> &[RetainedReadReceipt] {
        &self.receipts
    }

    pub fn grant(&self) -> &RetainedReuseGrant {
        &self.grant
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn grant_requires_exact_closed_census() {
        let grant = RetainedReuseGrant {
            schema: GRANT_SCHEMA.into(), grant_id: "g".into(), consumer_id: CONSUMER_ID.into(),
            consumer_source_path: "x".into(), consumer_source_sha256: "0".repeat(64),
            d0_sha256: "1".repeat(64), historical_master_ledger_sha256: "2".repeat(64),
            package_root_sha256: "3".repeat(64), tensor_count: 40, total_bytes: 0,
            attempts: 1, checkpoint_fallback: false, original_checkpoint_reads: 0,
            original_checkpoint_shard_opens: 0, historical_payload_ledger_delta: 0,
            terminal_semantics: "ONE_ATTEMPT_NO_RETRY_NO_RESUME_COMPLETE_OR_TERMINAL_FAILURE".into(),
            allowed_output_root: PathBuf::from("/tmp/out"), allowed_reads: vec![],
        };
        let package = RetainedPackage {
            schema: PACKAGE_SCHEMA.into(), schema_version: "1.0.0".into(), graph_version: "g".into(),
            execution_code_head: "h".into(), fixed_attempt_root: "/tmp/a".into(), fixed_capture_root: "/tmp/c".into(),
            tensors: BTreeMap::new(), position: 0, rope_base: 1.0, attention_scale: 1.0,
            expert_weight_scale: 1.0, heads: 1, qk_nope: 1, qk_rope: 1, kv_lora: 1,
            value_dim: 1, routed_expert_ids: vec![], runtime: RuntimeSpec { device:"d".into(),
            mlx_version:"m".into(), mlx_c_version:"c".into(), libmlx_sha256:"l".into(),
            libmlxc_sha256:"x".into(), backend:"b".into(), thread_limits:BTreeMap::new() }, checkpoint_paths: vec![],
        };
        assert!(GrantedInputs::validate(grant, &package).is_err());
    }
}
