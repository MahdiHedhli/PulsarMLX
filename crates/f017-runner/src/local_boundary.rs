use crate::json::{parse_json_no_duplicates, sha256_file};
use serde::{Deserialize, Serialize};
use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};

pub const LOCAL_BOUNDARY_SCHEMA: &str = "pulsarmlx.f017.local-real-boundary-fixture";
pub const LOCAL_BOUNDARY_SCHEMA_VERSION: u32 = 1;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LocalBoundaryFixtureManifest {
    pub schema: String,
    pub schema_version: u32,
    pub source_sha: String,
    pub checkpoint_set_sha256: String,
    pub checkpoint_revision: String,
    pub tensor: LocalTensorIdentity,
    pub decoder_contract: ContractIdentity,
    pub fixture: LocalFixtureIdentity,
    pub reference: ReferenceProvenance,
    pub privacy_classification: PrivacyClassification,
    pub redistributable: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LocalTensorIdentity {
    pub name: String,
    pub shard_id: String,
    pub shard_sha256: String,
    pub offset: u64,
    pub length: u64,
    pub quantization: String,
    pub dimensions: Vec<u64>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ContractIdentity {
    pub id: String,
    pub sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LocalFixtureIdentity {
    pub path: PathBuf,
    pub byte_length: u64,
    pub sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ReferenceProvenance {
    pub generator: String,
    pub generator_source_sha: String,
    pub independent: bool,
    pub input_sha256: String,
    pub expected_output_sha256: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PrivacyClassification {
    LocalOnlyPrivateCheckpointDerived,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum LocalBoundaryValidationError {
    Parse(String),
    Schema,
    Empty(&'static str),
    InvalidGitSha(&'static str),
    InvalidSha256(&'static str),
    InvalidTensorRange,
    InvalidDimensions,
    RedistributablePrivateFixture,
    NonIndependentReference,
    FixturePathNotAbsolute,
    FixturePathSymlink,
    FixturePathNotFile,
    FixtureLength { expected: u64, actual: u64 },
    FixtureHash { expected: String, actual: String },
    Io(String),
}

impl LocalBoundaryFixtureManifest {
    pub fn from_bytes(bytes: &[u8]) -> Result<Self, LocalBoundaryValidationError> {
        parse_json_no_duplicates(bytes).map_err(LocalBoundaryValidationError::Parse)
    }

    pub fn load(path: &Path) -> Result<Self, LocalBoundaryValidationError> {
        let bytes = fs::read(path)
            .map_err(|error| LocalBoundaryValidationError::Io(format!("read manifest: {error}")))?;
        Self::from_bytes(&bytes)
    }

    pub fn validate_identity(&self) -> Result<(), LocalBoundaryValidationError> {
        if self.schema != LOCAL_BOUNDARY_SCHEMA
            || self.schema_version != LOCAL_BOUNDARY_SCHEMA_VERSION
        {
            return Err(LocalBoundaryValidationError::Schema);
        }
        require_git_sha(&self.source_sha, "source_sha")?;
        require_sha256(&self.checkpoint_set_sha256, "checkpoint_set_sha256")?;
        require_nonempty(&self.checkpoint_revision, "checkpoint_revision")?;
        require_nonempty(&self.tensor.name, "tensor.name")?;
        require_nonempty(&self.tensor.shard_id, "tensor.shard_id")?;
        require_sha256(&self.tensor.shard_sha256, "tensor.shard_sha256")?;
        require_nonempty(&self.tensor.quantization, "tensor.quantization")?;
        if self.tensor.length == 0 || self.tensor.offset.checked_add(self.tensor.length).is_none() {
            return Err(LocalBoundaryValidationError::InvalidTensorRange);
        }
        if self.tensor.dimensions.is_empty() || self.tensor.dimensions.contains(&0) {
            return Err(LocalBoundaryValidationError::InvalidDimensions);
        }
        require_nonempty(&self.decoder_contract.id, "decoder_contract.id")?;
        require_sha256(&self.decoder_contract.sha256, "decoder_contract.sha256")?;
        require_sha256(&self.fixture.sha256, "fixture.sha256")?;
        if self.fixture.byte_length == 0 || self.fixture.byte_length != self.tensor.length {
            return Err(LocalBoundaryValidationError::InvalidTensorRange);
        }
        require_nonempty(&self.reference.generator, "reference.generator")?;
        require_git_sha(
            &self.reference.generator_source_sha,
            "reference.generator_source_sha",
        )?;
        require_sha256(&self.reference.input_sha256, "reference.input_sha256")?;
        require_sha256(
            &self.reference.expected_output_sha256,
            "reference.expected_output_sha256",
        )?;
        if !self.reference.independent {
            return Err(LocalBoundaryValidationError::NonIndependentReference);
        }
        if self.redistributable {
            return Err(LocalBoundaryValidationError::RedistributablePrivateFixture);
        }
        Ok(())
    }

    pub fn verify_local_fixture(&self) -> Result<(), LocalBoundaryValidationError> {
        self.validate_identity()?;
        if !self.fixture.path.is_absolute() {
            return Err(LocalBoundaryValidationError::FixturePathNotAbsolute);
        }
        let link_metadata = fs::symlink_metadata(&self.fixture.path).map_err(|error| {
            LocalBoundaryValidationError::Io(format!("fixture metadata: {error}"))
        })?;
        if link_metadata.file_type().is_symlink() {
            return Err(LocalBoundaryValidationError::FixturePathSymlink);
        }
        if !link_metadata.is_file() {
            return Err(LocalBoundaryValidationError::FixturePathNotFile);
        }
        let actual_length = link_metadata.len();
        if actual_length != self.fixture.byte_length {
            return Err(LocalBoundaryValidationError::FixtureLength {
                expected: self.fixture.byte_length,
                actual: actual_length,
            });
        }
        let actual = sha256_file(&self.fixture.path)
            .map_err(|error| LocalBoundaryValidationError::Io(format!("fixture hash: {error}")))?;
        if actual != self.fixture.sha256 {
            return Err(LocalBoundaryValidationError::FixtureHash {
                expected: self.fixture.sha256.clone(),
                actual,
            });
        }
        Ok(())
    }
}

impl fmt::Display for LocalBoundaryValidationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{self:?}")
    }
}

impl std::error::Error for LocalBoundaryValidationError {}

fn require_nonempty(value: &str, field: &'static str) -> Result<(), LocalBoundaryValidationError> {
    if value.trim().is_empty() {
        return Err(LocalBoundaryValidationError::Empty(field));
    }
    Ok(())
}

fn require_git_sha(value: &str, field: &'static str) -> Result<(), LocalBoundaryValidationError> {
    if value.len() != 40
        || !value.bytes().all(|byte| byte.is_ascii_hexdigit())
        || value.bytes().any(|byte| byte.is_ascii_uppercase())
    {
        return Err(LocalBoundaryValidationError::InvalidGitSha(field));
    }
    Ok(())
}

fn require_sha256(value: &str, field: &'static str) -> Result<(), LocalBoundaryValidationError> {
    if value.len() != 64
        || !value.bytes().all(|byte| byte.is_ascii_hexdigit())
        || value.bytes().any(|byte| byte.is_ascii_uppercase())
    {
        return Err(LocalBoundaryValidationError::InvalidSha256(field));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::json::sha256_bytes;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn fake_manifest(path: PathBuf, bytes: &[u8]) -> LocalBoundaryFixtureManifest {
        let fixture_sha = sha256_bytes(bytes);
        LocalBoundaryFixtureManifest {
            schema: LOCAL_BOUNDARY_SCHEMA.to_owned(),
            schema_version: LOCAL_BOUNDARY_SCHEMA_VERSION,
            source_sha: "1".repeat(40),
            checkpoint_set_sha256: "2".repeat(64),
            checkpoint_revision: "fake-r13-checkpoint-v1".to_owned(),
            tensor: LocalTensorIdentity {
                name: "blk.3.ffn_gate_exps.weight".to_owned(),
                shard_id: "fake-00002-of-00006.gguf".to_owned(),
                shard_sha256: "3".repeat(64),
                offset: 4096,
                length: bytes.len() as u64,
                quantization: "IQ2_XXS".to_owned(),
                dimensions: vec![256, 2048, 6144],
            },
            decoder_contract: ContractIdentity {
                id: "iq2_xxs-exact-f32-v1".to_owned(),
                sha256: "4".repeat(64),
            },
            fixture: LocalFixtureIdentity {
                path,
                byte_length: bytes.len() as u64,
                sha256: fixture_sha,
            },
            reference: ReferenceProvenance {
                generator: "scripts/research/f017_extract_boundary.py".to_owned(),
                generator_source_sha: "5".repeat(40),
                independent: true,
                input_sha256: "6".repeat(64),
                expected_output_sha256: "7".repeat(64),
            },
            privacy_classification: PrivacyClassification::LocalOnlyPrivateCheckpointDerived,
            redistributable: false,
        }
    }

    fn temp_fixture(bytes: &[u8]) -> PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "f017-r13-fake-shard-{}-{suffix}.bin",
            std::process::id()
        ));
        fs::write(&path, bytes).unwrap();
        path
    }

    #[test]
    fn fake_local_shard_manifest_and_payload_validate() {
        let bytes = b"public-safe fake quantized tensor bytes";
        let path = temp_fixture(bytes);
        let manifest = fake_manifest(path.clone(), bytes);
        manifest.validate_identity().unwrap();
        manifest.verify_local_fixture().unwrap();
        fs::remove_file(path).unwrap();
    }

    #[test]
    fn local_manifest_rejects_duplicate_keys_relative_paths_and_bad_hashes() {
        assert!(matches!(
            LocalBoundaryFixtureManifest::from_bytes(br#"{"schema":"a","schema":"b"}"#),
            Err(LocalBoundaryValidationError::Parse(_))
        ));

        let bytes = b"fake shard";
        let path = temp_fixture(bytes);
        let mut manifest = fake_manifest(PathBuf::from("relative.bin"), bytes);
        assert!(matches!(
            manifest.verify_local_fixture(),
            Err(LocalBoundaryValidationError::FixturePathNotAbsolute)
        ));

        manifest.fixture.path = path.clone();
        manifest.fixture.sha256 = "8".repeat(64);
        assert!(matches!(
            manifest.verify_local_fixture(),
            Err(LocalBoundaryValidationError::FixtureHash { .. })
        ));
        fs::remove_file(path).unwrap();
    }

    #[test]
    fn local_manifest_rejects_overflow_and_non_independent_provenance() {
        let bytes = b"fake shard";
        let path = temp_fixture(bytes);
        let mut manifest = fake_manifest(path.clone(), bytes);
        manifest.tensor.offset = u64::MAX;
        assert!(matches!(
            manifest.validate_identity(),
            Err(LocalBoundaryValidationError::InvalidTensorRange)
        ));
        manifest.tensor.offset = 0;
        manifest.reference.independent = false;
        assert!(matches!(
            manifest.validate_identity(),
            Err(LocalBoundaryValidationError::NonIndependentReference)
        ));
        fs::remove_file(path).unwrap();
    }

    #[test]
    fn local_manifest_rejects_noncanonical_uppercase_source_sha() {
        let bytes = b"fake shard";
        let path = temp_fixture(bytes);
        let mut manifest = fake_manifest(path.clone(), bytes);
        manifest.source_sha = "A".repeat(40);
        assert!(matches!(
            manifest.validate_identity(),
            Err(LocalBoundaryValidationError::InvalidGitSha("source_sha"))
        ));
        fs::remove_file(path).unwrap();
    }
}
