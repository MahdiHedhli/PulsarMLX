use crate::evidence::{CheckpointEvidence, ShardEvidence, TensorMapEvidence};
use crate::json::{parse_json_no_duplicates, read_exact_at, sha256_file_with_metrics};
use crate::{FailureClass, RunnerError};
use gguf::{Gguf, TensorInfo};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::fs::{self, File};
use std::path::{Component, Path, PathBuf};

const MANIFEST_SCHEMA: &str = "pulsarmlx.f017.checkpoint-manifest";
const MANIFEST_VERSION: &str = "1.0.0";
const INITIAL_HEADER_BYTES: usize = 64 * 1024;
const MAX_HEADER_BYTES: usize = 64 * 1024 * 1024;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CheckpointKind {
    Production,
    Fixture,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct CheckpointManifest {
    pub schema: String,
    pub schema_version: String,
    pub kind: CheckpointKind,
    pub immutable_revision: String,
    pub architecture: String,
    pub tokenizer_identity: String,
    pub checkpoint_set_sha256: String,
    pub catalog_sha256: String,
    pub tensor_count: u64,
    pub shards: Vec<CheckpointShard>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct CheckpointShard {
    pub filename: String,
    pub size_bytes: u64,
    pub sha256: String,
}

pub struct VerifiedCheckpoint {
    pub manifest: CheckpointManifest,
    pub root: PathBuf,
    pub shards: Vec<VerifiedShard>,
    pub catalog: Gguf,
    pub header_bytes_read: u64,
    pub identity_bytes_read: u64,
    pub identity_read_count: u64,
}

#[derive(Debug, Clone)]
pub struct VerifiedShard {
    pub filename: String,
    pub path: PathBuf,
    pub size_bytes: u64,
    pub sha256: String,
    pub base: u64,
}

impl CheckpointManifest {
    pub fn load(path: &Path) -> Result<Self, RunnerError> {
        let bytes = fs::read(path).map_err(|error| {
            checkpoint_error(
                "checkpoint_manifest_read",
                format!("cannot read checkpoint manifest: {error}"),
            )
        })?;
        let manifest: Self = parse_json_no_duplicates(&bytes)
            .map_err(|error| checkpoint_error("checkpoint_manifest_json", error))?;
        manifest.validate()?;
        Ok(manifest)
    }

    pub fn validate(&self) -> Result<(), RunnerError> {
        if self.schema != MANIFEST_SCHEMA || self.schema_version != MANIFEST_VERSION {
            return Err(checkpoint_error(
                "checkpoint_manifest_schema",
                "checkpoint manifest schema identity differs",
            ));
        }
        if self.immutable_revision.is_empty() || self.tokenizer_identity.is_empty() {
            return Err(checkpoint_error(
                "checkpoint_manifest_identity",
                "revision and tokenizer identity must be nonempty",
            ));
        }
        if self.architecture != "glm-dsa" {
            return Err(checkpoint_error(
                "checkpoint_architecture",
                "Feature 017 canonical runner requires glm-dsa",
            ));
        }
        validate_sha256(&self.checkpoint_set_sha256, "checkpoint_set_sha256")?;
        validate_sha256(&self.catalog_sha256, "catalog_sha256")?;
        if self.tensor_count == 0 || self.shards.is_empty() {
            return Err(checkpoint_error(
                "checkpoint_manifest_empty",
                "checkpoint manifest requires tensors and shards",
            ));
        }
        let mut filenames = HashSet::new();
        for shard in &self.shards {
            if !is_safe_basename(&shard.filename) || !filenames.insert(&shard.filename) {
                return Err(checkpoint_error(
                    "checkpoint_shard_name",
                    format!("unsafe or duplicate shard filename {:?}", shard.filename),
                ));
            }
            if shard.size_bytes == 0 {
                return Err(checkpoint_error(
                    "checkpoint_shard_size",
                    format!("shard {} has zero length", shard.filename),
                ));
            }
            validate_sha256(&shard.sha256, "shard sha256")?;
        }
        Ok(())
    }
}

impl VerifiedCheckpoint {
    pub fn verify(manifest_path: &Path, manifest: CheckpointManifest) -> Result<Self, RunnerError> {
        let root = manifest_path
            .parent()
            .unwrap_or_else(|| Path::new("."))
            .to_path_buf();
        let mut shard_headers = Vec::with_capacity(manifest.shards.len());
        let mut shards = Vec::with_capacity(manifest.shards.len());
        let mut base = 0_u64;
        let mut header_bytes_read = 0_u64;
        let mut identity_bytes_read = 0_u64;
        let mut identity_read_count = 0_u64;
        let mut set_hasher = Sha256::new();
        let mut names = HashSet::new();

        for expected in &manifest.shards {
            let path = root.join(&expected.filename);
            let metadata = fs::metadata(&path).map_err(|error| {
                checkpoint_error(
                    "checkpoint_shard_metadata",
                    format!("cannot stat shard {}: {error}", expected.filename),
                )
            })?;
            if metadata.len() != expected.size_bytes {
                return Err(checkpoint_error(
                    "checkpoint_shard_size",
                    format!(
                        "shard {} size {} differs from expected {}",
                        expected.filename,
                        metadata.len(),
                        expected.size_bytes
                    ),
                ));
            }
            let (actual_sha256, hash_bytes, hash_requests) = sha256_file_with_metrics(&path)
                .map_err(|error| {
                    checkpoint_error(
                        "checkpoint_shard_hash",
                        format!("shard {}: {error}", expected.filename),
                    )
                })?;
            identity_bytes_read = identity_bytes_read.checked_add(hash_bytes).ok_or_else(|| {
                checkpoint_error(
                    "checkpoint_identity_bytes_overflow",
                    "identity byte count overflow",
                )
            })?;
            identity_read_count =
                identity_read_count
                    .checked_add(hash_requests)
                    .ok_or_else(|| {
                        checkpoint_error(
                            "checkpoint_identity_requests_overflow",
                            "identity request count overflow",
                        )
                    })?;
            if actual_sha256 != expected.sha256 {
                return Err(checkpoint_error(
                    "checkpoint_shard_hash",
                    format!("shard {} SHA-256 differs", expected.filename),
                ));
            }
            set_hasher.update(actual_sha256.as_bytes());
            set_hasher.update(expected.size_bytes.to_string().as_bytes());
            let (header, bytes_read, read_count) = parse_header(&path, expected.size_bytes)?;
            header_bytes_read = header_bytes_read.checked_add(bytes_read).ok_or_else(|| {
                checkpoint_error(
                    "checkpoint_header_bytes_overflow",
                    "header byte count overflow",
                )
            })?;
            identity_bytes_read = identity_bytes_read.checked_add(bytes_read).ok_or_else(|| {
                checkpoint_error(
                    "checkpoint_identity_bytes_overflow",
                    "identity byte count overflow",
                )
            })?;
            identity_read_count = identity_read_count.checked_add(read_count).ok_or_else(|| {
                checkpoint_error(
                    "checkpoint_identity_requests_overflow",
                    "identity request count overflow",
                )
            })?;
            validate_local_tensor_ranges(
                &header,
                expected.size_bytes,
                &expected.filename,
                &mut names,
            )?;
            shard_headers.push(header);
            shards.push(VerifiedShard {
                filename: expected.filename.clone(),
                path,
                size_bytes: expected.size_bytes,
                sha256: actual_sha256,
                base,
            });
            base = base.checked_add(expected.size_bytes).ok_or_else(|| {
                checkpoint_error("checkpoint_size_overflow", "logical shard base overflow")
            })?;
        }

        let actual_set = format!("{:x}", set_hasher.finalize());
        if actual_set != manifest.checkpoint_set_sha256 {
            return Err(checkpoint_error(
                "checkpoint_set_hash",
                "checkpoint-set SHA-256 differs",
            ));
        }
        let bases = shards.iter().map(|shard| shard.base).collect::<Vec<_>>();
        let catalog = Gguf::merge_split(shard_headers, &bases);
        if catalog.architecture() != Some(manifest.architecture.as_str()) {
            return Err(checkpoint_error(
                "checkpoint_catalog_architecture",
                "merged GGUF architecture differs from manifest",
            ));
        }
        if catalog.tensors.len() as u64 != manifest.tensor_count {
            return Err(checkpoint_error(
                "checkpoint_tensor_count",
                format!(
                    "catalog has {} tensors; manifest requires {}",
                    catalog.tensors.len(),
                    manifest.tensor_count
                ),
            ));
        }
        let actual_catalog = catalog_sha256(&catalog.tensors);
        if actual_catalog != manifest.catalog_sha256 {
            return Err(checkpoint_error(
                "checkpoint_catalog_hash",
                "tensor catalog SHA-256 differs",
            ));
        }

        Ok(Self {
            manifest,
            root,
            shards,
            catalog,
            header_bytes_read,
            identity_bytes_read,
            identity_read_count,
        })
    }

    pub fn evidence_identity(&self) -> CheckpointEvidence {
        CheckpointEvidence {
            accessed: true,
            revision: Some(self.manifest.immutable_revision.clone()),
            checkpoint_set_sha256: Some(self.manifest.checkpoint_set_sha256.clone()),
            catalog_sha256: Some(self.manifest.catalog_sha256.clone()),
            architecture: Some(self.manifest.architecture.clone()),
            tokenizer_identity: Some(self.manifest.tokenizer_identity.clone()),
            tensor_count: Some(self.manifest.tensor_count),
            tensor_map: TensorMapEvidence::default(),
            shards: self
                .shards
                .iter()
                .map(|shard| ShardEvidence {
                    filename: shard.filename.clone(),
                    size_bytes: shard.size_bytes,
                    sha256: shard.sha256.clone(),
                })
                .collect(),
        }
    }
}

pub fn catalog_sha256(tensors: &[TensorInfo]) -> String {
    let mut hasher = Sha256::new();
    for tensor in tensors {
        hasher.update(tensor.name.as_bytes());
        hasher.update([0]);
        hasher.update((tensor.dims.len() as u64).to_le_bytes());
        for dimension in &tensor.dims {
            hasher.update(dimension.to_le_bytes());
        }
        hasher.update(tensor.ty.to_id().to_le_bytes());
        hasher.update(tensor.offset.to_le_bytes());
        hasher.update(tensor.byte_size().unwrap_or(u64::MAX).to_le_bytes());
    }
    format!("{:x}", hasher.finalize())
}

fn parse_header(path: &Path, file_length: u64) -> Result<(Gguf, u64, u64), RunnerError> {
    let file = File::open(path)
        .map_err(|error| checkpoint_error("checkpoint_header_open", error.to_string()))?;
    let maximum = usize::try_from(file_length.min(MAX_HEADER_BYTES as u64))
        .map_err(|_| checkpoint_error("checkpoint_header_size", "header bound exceeds usize"))?;
    let mut size = INITIAL_HEADER_BYTES.min(maximum);
    let mut total_bytes = 0_u64;
    let mut read_count = 0_u64;
    loop {
        if size == 0 {
            return Err(checkpoint_error(
                "checkpoint_header_empty",
                "GGUF shard is empty",
            ));
        }
        let mut bytes = vec![0_u8; size];
        read_exact_at(&file, &mut bytes, 0).map_err(|error| {
            checkpoint_error(
                "checkpoint_header_read",
                format!("cannot read GGUF header: {error}"),
            )
        })?;
        total_bytes = total_bytes.checked_add(size as u64).ok_or_else(|| {
            checkpoint_error(
                "checkpoint_header_bytes_overflow",
                "header byte count overflow",
            )
        })?;
        read_count = read_count.checked_add(1).ok_or_else(|| {
            checkpoint_error(
                "checkpoint_header_requests_overflow",
                "header request count overflow",
            )
        })?;
        match Gguf::parse(&bytes) {
            Ok(header) => return Ok((header, total_bytes, read_count)),
            Err(gguf::Error::Truncated { .. }) if size < maximum => {
                size = size.saturating_mul(2).min(maximum);
            }
            Err(error) => {
                return Err(checkpoint_error(
                    "checkpoint_header_parse",
                    error.to_string(),
                ))
            }
        }
    }
}

fn validate_local_tensor_ranges(
    header: &Gguf,
    file_length: u64,
    filename: &str,
    names: &mut HashSet<String>,
) -> Result<(), RunnerError> {
    for tensor in &header.tensors {
        if !names.insert(tensor.name.clone()) {
            return Err(checkpoint_error(
                "checkpoint_duplicate_tensor",
                format!("duplicate tensor name {:?}", tensor.name),
            ));
        }
        let bytes = tensor.byte_size().ok_or_else(|| {
            checkpoint_error(
                "checkpoint_tensor_type",
                format!("tensor {} has unsupported byte layout", tensor.name),
            )
        })?;
        let start = header
            .data_offset
            .checked_add(tensor.offset)
            .ok_or_else(|| {
                checkpoint_error(
                    "checkpoint_tensor_range",
                    format!("tensor {} offset overflow", tensor.name),
                )
            })?;
        let end = start.checked_add(bytes).ok_or_else(|| {
            checkpoint_error(
                "checkpoint_tensor_range",
                format!("tensor {} range overflow", tensor.name),
            )
        })?;
        if end > file_length {
            return Err(checkpoint_error(
                "checkpoint_tensor_range",
                format!("tensor {} exceeds shard {}", tensor.name, filename),
            ));
        }
    }
    Ok(())
}

fn is_safe_basename(value: &str) -> bool {
    let path = Path::new(value);
    !value.is_empty()
        && !path.is_absolute()
        && path.components().count() == 1
        && matches!(path.components().next(), Some(Component::Normal(_)))
}

fn validate_sha256(value: &str, field: &str) -> Result<(), RunnerError> {
    if value.len() != 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return Err(checkpoint_error(
            "checkpoint_hash_format",
            format!("{field} must be lowercase SHA-256"),
        ));
    }
    Ok(())
}

fn checkpoint_error(code: &'static str, message: impl Into<String>) -> RunnerError {
    RunnerError::new(FailureClass::CheckpointIdentity, code, message)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn manifest_rejects_paths_duplicates_and_bad_hashes() {
        let mut manifest = CheckpointManifest {
            schema: MANIFEST_SCHEMA.to_owned(),
            schema_version: MANIFEST_VERSION.to_owned(),
            kind: CheckpointKind::Fixture,
            immutable_revision: "fixture-v1".to_owned(),
            architecture: "glm-dsa".to_owned(),
            tokenizer_identity: "exact-token-ids".to_owned(),
            checkpoint_set_sha256: "a".repeat(64),
            catalog_sha256: "b".repeat(64),
            tensor_count: 1,
            shards: vec![CheckpointShard {
                filename: "one.gguf".to_owned(),
                size_bytes: 1,
                sha256: "c".repeat(64),
            }],
        };
        assert!(manifest.validate().is_ok());
        manifest.shards[0].filename = "../one.gguf".to_owned();
        assert!(manifest.validate().is_err());
        manifest.shards[0].filename = "one.gguf".to_owned();
        manifest.catalog_sha256 = "BAD".to_owned();
        assert!(manifest.validate().is_err());
    }
}
