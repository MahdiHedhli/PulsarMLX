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
pub const EXPECTED_GRANT_SHA256: &str = "15b2fbb2504546147fe7747f46004d1661c88d9eb9966fb04e218185f5f57776";
pub const EXPECTED_PACKAGE_SHA256: &str = "a2fc41cda5f2dbf9f2ea2f9f930569cf24fd6b51766260766ed63ce45cc03e7f";
pub const EXPECTED_D0_SHA256: &str = "cc62cdc7550e3a25f55de783e9eb7c68f6cf03d0eafb944a86dc8a2a60007fb9";
pub const EXPECTED_LEDGER_SHA256: &str = "aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e";
pub const HISTORICAL_PACKAGE_ROOT_SHA256: &str = "564a33aee801b4a44e23f3a9b370e1a2ce040dda521dadc4ac54dbfd29045be6";
pub const EXPECTED_PACKAGE_ROOT_SHA256: &str = "03ccbb1be96073bfe051ba8950ec4e16a3824b998c041dfcac7e209ede66151c";

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AllowedRead {
    pub ordinal: usize,
    pub role: String,
    pub canonical_tensor_id: String,
    pub destination_relative_path: String,
    pub path: PathBuf,
    pub byte_count: u64,
    pub sha256: String,
    pub encoding: String,
    pub quantization: String,
    pub decoder_binding: String,
    pub shape: Vec<usize>,
    pub source_branch: String,
    pub source_commit: String,
    pub source_authority_path: String,
    pub source_authority_sha256: String,
    pub source_result_event: String,
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
    pub historical_package_root_sha256: String,
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
    let bytes = fs::read(path).map_err(|e| format!("GRANT_READ:{e}"))?;
    if sha256_bytes(&bytes) != EXPECTED_GRANT_SHA256 {
        return Err("GRANT_EXACT_SHA".into());
    }
    parse_json_no_duplicates(&bytes)
}

pub fn load_package(path: &Path) -> Result<RetainedPackage, String> {
    let bytes = fs::read(path).map_err(|e| format!("PACKAGE_READ:{e}"))?;
    if sha256_bytes(&bytes) != EXPECTED_PACKAGE_SHA256 {
        return Err("PACKAGE_EXACT_SHA".into());
    }
    parse_json_no_duplicates(&bytes)
}

fn package_root(grant: &RetainedReuseGrant) -> Result<String, String> {
    let descriptors = grant.allowed_reads.iter().map(|row| serde_json::json!({
        "ordinal": row.ordinal,
        "canonical_tensor_id": row.canonical_tensor_id,
        "role": row.role,
        "destination_relative_path": row.destination_relative_path,
        "sha256": row.sha256,
        "byte_count": row.byte_count,
        "encoding": row.encoding,
        "shape": row.shape,
        "quantization": row.quantization,
        "decoder_binding": row.decoder_binding,
        "source_authority_path": row.source_authority_path,
        "source_authority_sha256": row.source_authority_sha256,
        "source_result_event": row.source_result_event,
    })).collect::<Vec<_>>();
    let value = serde_json::json!({
        "schema":"pulsarmlx.f017.apple-production-serial-f32-retained-package-root",
        "schema_version":"1.0.0",
        "package_version":"F017-APPLE-SERIAL-F32-RETAINED-40-V1",
        "tensor_count":40,
        "ordered_tensor_descriptors":descriptors,
    });
    let mut bytes = serde_json::to_vec(&value).map_err(|e| format!("ROOT_JSON:{e}"))?;
    bytes.push(b'\n');
    Ok(sha256_bytes(&bytes))
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
            || grant.d0_sha256 != EXPECTED_D0_SHA256
            || grant.historical_master_ledger_sha256 != EXPECTED_LEDGER_SHA256
            || grant.historical_package_root_sha256 != HISTORICAL_PACKAGE_ROOT_SHA256
            || grant.package_root_sha256 != EXPECTED_PACKAGE_ROOT_SHA256
            || package_root(&grant)? != EXPECTED_PACKAGE_ROOT_SHA256
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
            historical_package_root_sha256: "3".repeat(64),
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
