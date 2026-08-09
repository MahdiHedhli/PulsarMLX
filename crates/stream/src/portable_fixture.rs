use std::collections::HashSet;
use std::error::Error;
use std::fmt;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

pub const PORTABLE_FIXTURE_SCHEMA: &str = "pulsarmlx.runtime.portable-fixture-v1";
pub const PORTABLE_FIXTURE_SET_SCHEMA: &str = "pulsarmlx.runtime.portable-fixture-set-v1";
pub const PORTABLE_FIXTURE_SCHEMA_VERSION: u32 = 1;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ByteRange {
    pub offset: u64,
    pub length: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TrunkInventoryReference {
    pub path: String,
    pub content_sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ArtifactRecord {
    pub byte_length: u64,
    pub content_sha256: String,
    #[serde(default)]
    pub path: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case", deny_unknown_fields)]
pub struct PortableFixtureBoundaryArtifacts {
    pub input_residual: ArtifactRecord,
    pub normalized_activation: ArtifactRecord,
    pub attention_or_mla_output: ArtifactRecord,
    pub router_logits: ArtifactRecord,
    pub routed_expert_ids: ArtifactRecord,
    pub routed_weights: ArtifactRecord,
    pub selected_expert_output: ArtifactRecord,
    pub shared_expert_output: ArtifactRecord,
    pub moe_aggregate: ArtifactRecord,
    pub residual_output: ArtifactRecord,
    pub final_hidden_state: ArtifactRecord,
    pub final_norm_output: ArtifactRecord,
    pub topk_logits: ArtifactRecord,
    pub topk_argmax: ArtifactRecord,
    pub margins: ArtifactRecord,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PortableFixtureManifest {
    pub schema: String,
    pub schema_version: u32,
    pub feature_id: String,
    pub spec_version: String,
    pub source_commit: String,
    pub source_catalog: String,
    pub source_catalog_sha256: String,
    pub checkpoint_set_sha256: String,
    pub checkpoint_revision: String,
    pub trunk_inventory_reference: TrunkInventoryReference,

    pub tensor_name: String,
    pub tensor_shard: String,
    pub tensor_range: ByteRange,
    pub tensor_shape: Vec<u64>,
    pub quantization: String,
    pub dtype: String,

    pub payload_sha256: String,
    pub generation_position: u64,
    pub layer: u64,
    pub redistributable: bool,
    pub fixture_id: String,
    pub payload: ArtifactRecord,

    #[serde(rename = "required_fields")]
    pub required_boundaries: PortableFixtureBoundaryArtifacts,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PortableFixtureManifestSet {
    pub schema: String,
    pub schema_version: u32,
    pub fixtures: Vec<PortableFixtureManifest>,
}

#[derive(Debug)]
pub struct FixtureManifestPolicy {
    pub verify_payload_hashes: bool,
    pub verify_local_paths: bool,
}

impl Default for FixtureManifestPolicy {
    fn default() -> Self {
        Self {
            verify_payload_hashes: false,
            verify_local_paths: false,
        }
    }
}

#[derive(Debug)]
pub enum PortableFixtureValidationError {
    Parse(String),
    SchemaMismatch {
        expected_schema: String,
        expected_version: u32,
        got_schema: String,
        got_version: u32,
    },
    DuplicateFixtureId(String),
    InvalidFeature,
    MissingField(String),
    InvalidSha256 { field: String, value: String },
    InvalidCommitHash(String),
    EmptyField(String),
    InvalidTensorShape,
    ZeroLengthRange {
        tensor_name: String,
    },
    MissingPayloadPath {
        fixture_id: String,
    },
    InvalidLocalPayloadPath {
        fixture_id: String,
        path: String,
    },
    PayloadLengthMismatch {
        fixture_id: String,
        expected: u64,
        actual: u64,
        path: PathBuf,
    },
    PayloadShaMismatch {
        fixture_id: String,
        expected: String,
        actual: String,
        path: PathBuf,
    },
    Io {
        path: PathBuf,
        source: io::Error,
    },
}

impl PortableFixtureManifest {
    pub fn from_json(data: &str) -> Result<Self, PortableFixtureValidationError> {
        serde_json::from_str::<PortableFixtureManifest>(data)
            .map_err(|source| PortableFixtureValidationError::Parse(source.to_string()))
    }

    pub fn validate_identity(&self) -> Result<(), PortableFixtureValidationError> {
        if self.schema != PORTABLE_FIXTURE_SCHEMA {
            return Err(PortableFixtureValidationError::SchemaMismatch {
                expected_schema: PORTABLE_FIXTURE_SCHEMA.to_owned(),
                expected_version: PORTABLE_FIXTURE_SCHEMA_VERSION,
                got_schema: self.schema.clone(),
                got_version: self.schema_version,
            });
        }
        if self.schema_version != PORTABLE_FIXTURE_SCHEMA_VERSION {
            return Err(PortableFixtureValidationError::SchemaMismatch {
                expected_schema: PORTABLE_FIXTURE_SCHEMA.to_owned(),
                expected_version: PORTABLE_FIXTURE_SCHEMA_VERSION,
                got_schema: self.schema.clone(),
                got_version: self.schema_version,
            });
        }
        if self.feature_id != "017" {
            return Err(PortableFixtureValidationError::InvalidFeature);
        }

        self.ensure_non_empty("spec_version", &self.spec_version)?;
        self.ensure_non_empty("source_catalog", &self.source_catalog)?;
        self.ensure_non_empty("checkpoint_revision", &self.checkpoint_revision)?;
        self.ensure_non_empty("tensor_shard", &self.tensor_shard)?;
        self.ensure_non_empty("tensor_name", &self.tensor_name)?;
        self.ensure_non_empty("quantization", &self.quantization)?;
        self.ensure_non_empty("dtype", &self.dtype)?;
        self.ensure_non_empty("fixture_id", &self.fixture_id)?;
        self.ensure_non_empty("source_commit", &self.source_commit)?;
        self.ensure_non_empty("source_catalog_sha256", &self.source_catalog_sha256)?;
        self.ensure_non_empty("checkpoint_set_sha256", &self.checkpoint_set_sha256)?;
        self.ensure_non_empty(
            "trunk_inventory_reference.path",
            &self.trunk_inventory_reference.path,
        )?;
        self.ensure_non_empty(
            "payload.path",
            self.payload.path.as_deref().unwrap_or_default(),
        )?;
        if self.tensor_shape.is_empty() {
            return Err(PortableFixtureValidationError::MissingField("tensor_shape".to_owned()));
        }

        if self.tensor_range.length == 0 {
            return Err(PortableFixtureValidationError::ZeroLengthRange {
                tensor_name: self.tensor_name.clone(),
            });
        }
        if self
            .tensor_range
            .offset
            .checked_add(self.tensor_range.length)
            .is_none()
        {
            return Err(PortableFixtureValidationError::InvalidTensorShape);
        }

        validate_commit_sha(&self.source_commit, "source_commit")?;
        validate_sha256(&self.source_catalog_sha256, "source_catalog_sha256")?;
        validate_sha256(&self.checkpoint_set_sha256, "checkpoint_set_sha256")?;
        validate_sha256(&self.trunk_inventory_reference.content_sha256, "trunk_inventory_reference.content_sha256")?;
        validate_sha256(&self.payload_sha256, "payload_sha256")?;
        validate_artifact_record("payload", &self.payload)?;
        if self.payload_sha256 != self.payload.content_sha256 {
            return Err(PortableFixtureValidationError::InvalidSha256 {
                field: "payload_sha256 mismatch payload.content_sha256".to_owned(),
                value: self.payload.content_sha256.clone(),
            });
        }

        validate_artifact_record("input_residual", &self.required_boundaries.input_residual)?;
        validate_artifact_record(
            "normalized_activation",
            &self.required_boundaries.normalized_activation,
        )?;
        validate_artifact_record(
            "attention_or_mla_output",
            &self.required_boundaries.attention_or_mla_output,
        )?;
        validate_artifact_record("router_logits", &self.required_boundaries.router_logits)?;
        validate_artifact_record(
            "routed_expert_ids",
            &self.required_boundaries.routed_expert_ids,
        )?;
        validate_artifact_record(
            "routed_weights",
            &self.required_boundaries.routed_weights,
        )?;
        validate_artifact_record(
            "selected_expert_output",
            &self.required_boundaries.selected_expert_output,
        )?;
        validate_artifact_record(
            "shared_expert_output",
            &self.required_boundaries.shared_expert_output,
        )?;
        validate_artifact_record(
            "moe_aggregate",
            &self.required_boundaries.moe_aggregate,
        )?;
        validate_artifact_record("residual_output", &self.required_boundaries.residual_output)?;
        validate_artifact_record("final_hidden_state", &self.required_boundaries.final_hidden_state)?;
        validate_artifact_record("final_norm_output", &self.required_boundaries.final_norm_output)?;
        validate_artifact_record("topk_logits", &self.required_boundaries.topk_logits)?;
        validate_artifact_record("topk_argmax", &self.required_boundaries.topk_argmax)?;
        validate_artifact_record("margins", &self.required_boundaries.margins)?;
        Ok(())
    }

    pub fn payload_path(&self, root: &Path) -> Option<PathBuf> {
        let artifact_path = self.payload.path.as_deref()?;
        let candidate = Path::new(artifact_path);
        if candidate.is_absolute() {
            Some(candidate.to_path_buf())
        } else {
            Some(root.join(candidate))
        }
    }

    pub fn verify_payload(
        &self,
        root: &Path,
        policy: &FixtureManifestPolicy,
    ) -> Result<(), PortableFixtureValidationError> {
        let should_read = policy.verify_payload_hashes || policy.verify_local_paths;
        if !should_read {
            return Ok(());
        }

        if !self.redistributable
            && !self
                .payload
                .path
                .as_deref()
                .is_some_and(|value| Path::new(value).is_absolute())
        {
            return Err(PortableFixtureValidationError::InvalidLocalPayloadPath {
                fixture_id: self.fixture_id.clone(),
                path: self.payload.path.clone().unwrap_or_default(),
            });
        }

        let path = self.payload_path(root).ok_or_else(|| PortableFixtureValidationError::MissingPayloadPath {
            fixture_id: self.fixture_id.clone(),
        })?;

        let bytes = fs::read(&path).map_err(|source| PortableFixtureValidationError::Io {
            path: path.clone(),
            source,
        })?;
        self.verify_bytes_against_artifact(&bytes, &self.payload, &path)
    }

    fn verify_bytes_against_artifact(
        &self,
        bytes: &[u8],
        artifact: &ArtifactRecord,
        path: &Path,
    ) -> Result<(), PortableFixtureValidationError> {
        let actual_len = bytes.len();
        let actual_len_u64 = u64::try_from(actual_len).unwrap_or(u64::MAX);
        if artifact.byte_length != actual_len_u64 {
            return Err(PortableFixtureValidationError::PayloadLengthMismatch {
                fixture_id: self.fixture_id.clone(),
                expected: artifact.byte_length,
                actual: actual_len_u64,
                path: path.to_path_buf(),
            });
        }
        let actual_sha256 = format!("{:x}", Sha256::digest(bytes));
        if actual_sha256 != artifact.content_sha256 {
            return Err(PortableFixtureValidationError::PayloadShaMismatch {
                fixture_id: self.fixture_id.clone(),
                expected: artifact.content_sha256.clone(),
                actual: actual_sha256,
                path: path.to_path_buf(),
            });
        }
        Ok(())
    }

    fn ensure_non_empty(&self, field: &str, value: &str) -> Result<(), PortableFixtureValidationError> {
        if value.trim().is_empty() {
            return Err(PortableFixtureValidationError::EmptyField(field.to_owned()));
        }
        Ok(())
    }
}

impl PortableFixtureManifestSet {
    pub fn from_json(data: &str) -> Result<Self, PortableFixtureValidationError> {
        serde_json::from_str::<PortableFixtureManifestSet>(data)
            .map_err(|source| PortableFixtureValidationError::Parse(source.to_string()))
    }

    pub fn validate(&self) -> Result<(), PortableFixtureValidationError> {
        if self.schema != PORTABLE_FIXTURE_SET_SCHEMA {
            return Err(PortableFixtureValidationError::SchemaMismatch {
                expected_schema: PORTABLE_FIXTURE_SET_SCHEMA.to_owned(),
                expected_version: PORTABLE_FIXTURE_SCHEMA_VERSION,
                got_schema: self.schema.clone(),
                got_version: self.schema_version,
            });
        }
        if self.schema_version != PORTABLE_FIXTURE_SCHEMA_VERSION {
            return Err(PortableFixtureValidationError::SchemaMismatch {
                expected_schema: PORTABLE_FIXTURE_SET_SCHEMA.to_owned(),
                expected_version: PORTABLE_FIXTURE_SCHEMA_VERSION,
                got_schema: self.schema.clone(),
                got_version: self.schema_version,
            });
        }

        let mut seen = HashSet::new();
        for fixture in &self.fixtures {
            fixture.validate_identity()?;
            if !seen.insert(fixture.fixture_id.clone()) {
                return Err(PortableFixtureValidationError::DuplicateFixtureId(
                    fixture.fixture_id.clone(),
                ));
            }
        }
        Ok(())
    }

    pub fn verify_payloads(
        &self,
        root: &Path,
        policy: &FixtureManifestPolicy,
    ) -> Result<(), PortableFixtureValidationError> {
        for fixture in &self.fixtures {
            fixture.verify_payload(root, policy)?;
        }
        Ok(())
    }
}

impl fmt::Display for PortableFixtureValidationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Parse(source) => write!(formatter, "portable fixture manifest is not valid JSON: {source}"),
            Self::SchemaMismatch { expected_schema, expected_version, got_schema, got_version } => write!(
                formatter,
                "fixture schema mismatch: expected {expected_schema}/{expected_version}, got {got_schema}/{got_version}",
            ),
            Self::DuplicateFixtureId(fixture_id) => {
                write!(formatter, "duplicate fixture_id '{fixture_id}' in set")
            }
            Self::InvalidFeature => write!(formatter, "fixture feature_id must be '017'"),
            Self::MissingField(field) => write!(formatter, "missing required field: {field}"),
            Self::InvalidCommitHash(field) => {
                write!(formatter, "invalid commit SHA in '{field}', expected 40 hex chars")
            }
            Self::InvalidSha256 { field, value } => {
                write!(formatter, "invalid SHA-256 in '{field}', got '{value}'")
            }
            Self::EmptyField(field) => write!(formatter, "field '{field}' must not be empty"),
            Self::InvalidTensorShape => write!(formatter, "tensor_shape must not be empty"),
            Self::ZeroLengthRange { tensor_name } => {
                write!(formatter, "tensor_range.length must be >0 for {tensor_name}")
            }
            Self::MissingPayloadPath { fixture_id } => {
                write!(formatter, "fixture '{fixture_id}' is missing payload.path")
            }
            Self::InvalidLocalPayloadPath { fixture_id, path } => {
                write!(formatter, "fixture '{fixture_id}' local path must be absolute, got '{path}'")
            }
            Self::PayloadLengthMismatch {
                fixture_id,
                expected,
                actual,
                path,
            } => write!(
                formatter,
                "fixture '{fixture_id}' payload length mismatch at '{}': expected {expected}, got {actual}",
                path.display()
            ),
            Self::PayloadShaMismatch {
                fixture_id,
                expected,
                actual,
                path,
            } => write!(
                formatter,
                "fixture '{fixture_id}' payload hash mismatch at '{}': expected {expected}, got {actual}",
                path.display()
            ),
            Self::Io { path, source } => {
                write!(formatter, "failed reading payload file '{}': {source}", path.display())
            }
        }
    }
}

impl Error for PortableFixtureValidationError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Io { source, .. } => Some(source),
            _ => None,
        }
    }
}

fn validate_sha256(value: &str, field: &str) -> Result<(), PortableFixtureValidationError> {
    if value.len() != 64 {
        return Err(PortableFixtureValidationError::InvalidSha256 {
            field: field.to_owned(),
            value: value.to_owned(),
        });
    }
    if !value.chars().all(|ch| ch.is_ascii_hexdigit()) {
        return Err(PortableFixtureValidationError::InvalidSha256 {
            field: field.to_owned(),
            value: value.to_owned(),
        });
    }
    Ok(())
}

fn validate_commit_sha(value: &str, field: &str) -> Result<(), PortableFixtureValidationError> {
    if value.len() != 40 || !value.chars().all(|ch| ch.is_ascii_hexdigit()) {
        return Err(PortableFixtureValidationError::InvalidCommitHash(field.to_owned()));
    }
    Ok(())
}

fn validate_artifact_record(
    field: &str,
    artifact: &ArtifactRecord,
) -> Result<(), PortableFixtureValidationError> {
    if artifact.byte_length == 0 {
        return Err(PortableFixtureValidationError::MissingField(format!("{field}.byte_length")));
    }
    validate_sha256(&artifact.content_sha256, &format!("{field}.content_sha256"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::env;
    use std::fs;
    use std::path::PathBuf;

    fn fixture_dir() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../specs/017-rust-native-inference-runtime/fixtures")
            .into()
    }

    fn test_source_catalog() -> &'static str {
        "docs/research/glm52/raw/f016-c01-catalog-0001.json"
    }

    fn synthetic_manifest_text() -> String {
        fs::read_to_string(
            fixture_dir()
                .join("portable-fixture-synthetic-v1.json")
                .as_path(),
        )
        .expect("read synthetic fixture manifest")
    }

    fn set_manifest_text() -> String {
        fs::read_to_string(
            fixture_dir()
                .join("portable-fixture-set-v1.json")
                .as_path(),
        )
        .expect("read synthetic fixture set manifest")
    }

    #[test]
    fn parse_and_validate_synthetic_manifest_examples() {
        let fixture = PortableFixtureManifest::from_json(&synthetic_manifest_text())
            .expect("synthetic manifest parses");
        fixture.validate_identity().expect("synthetic manifest validates");

        let payload_policy = FixtureManifestPolicy {
            verify_payload_hashes: true,
            verify_local_paths: false,
        };
        fixture
            .verify_payload(fixture_dir().as_path(), &payload_policy)
            .expect("synthetic manifest payload verifies");

        assert_eq!(fixture.source_catalog, test_source_catalog());
    }

    #[test]
    fn parse_local_only_manifest_examples() {
        let data = fs::read_to_string(fixture_dir().join("portable-fixture-local-only-v1.json"))
            .expect("read local-only fixture manifest");
        let fixture = PortableFixtureManifest::from_json(&data)
            .expect("local-only manifest parses");
        fixture.validate_identity().expect("local-only manifest validates");
        assert!(!fixture.redistributable);
    }

    #[test]
    fn reject_relative_local_only_payload_path_when_verifying() {
        let data = fs::read_to_string(fixture_dir().join("portable-fixture-local-only-v1.json"))
            .expect("read local-only fixture manifest");
        let mut fixture = PortableFixtureManifest::from_json(&data)
            .expect("local-only manifest parses");
        fixture.payload.path = Some("relative-local-only.bin".to_owned());

        let policy = FixtureManifestPolicy {
            verify_payload_hashes: true,
            verify_local_paths: false,
        };
        assert!(matches!(
            fixture.verify_payload(fixture_dir().as_path(), &policy),
            Err(PortableFixtureValidationError::InvalidLocalPayloadPath { .. })
        ));
    }

    #[test]
    fn reject_malformed_manifest_documents() {
        assert!(PortableFixtureManifest::from_json("{").is_err());
    }

    #[test]
    fn reject_unsigned_manifest_documents() {
        let missing_field = "{\n\t\"schema\": \"pulsarmlx.runtime.portable-fixture-v1\",\n\t\"schema_version\": 1,\n\t\"feature_id\": \"017\",\n\t\"spec_version\": \"1.0.0\",\n\t\"source_catalog\": \"x\"\n}";
        assert!(PortableFixtureManifest::from_json(missing_field).is_err());
    }

    #[test]
    fn reject_duplicate_fixture_ids() {
        let set = PortableFixtureManifestSet::from_json(&set_manifest_text())
            .expect("fixture set parses");
        let duplicate = PortableFixtureManifestSet {
            fixtures: vec![set.fixtures[0].clone(), set.fixtures[0].clone()],
            ..set
        };
        assert!(matches!(
            duplicate.validate(),
            Err(PortableFixtureValidationError::DuplicateFixtureId(_))
        ));
    }

    #[test]
    fn detect_payload_hash_mismatch() {
        let manifest = PortableFixtureManifest::from_json(&synthetic_manifest_text())
            .expect("synthetic manifest parses");
        let mut broken = manifest;
        broken.payload.content_sha256 = "f".repeat(64);

        let policy = FixtureManifestPolicy {
            verify_payload_hashes: true,
            verify_local_paths: false,
        };

        assert!(matches!(
            broken.verify_payload(fixture_dir().as_path(), &policy),
            Err(PortableFixtureValidationError::PayloadShaMismatch { .. })
        ));
    }

    #[test]
    fn validate_manifest_set_and_hashes() {
        let set = PortableFixtureManifestSet::from_json(&set_manifest_text())
            .expect("fixture set parses");
        set.validate().expect("set validates");

        let policy = FixtureManifestPolicy {
            verify_payload_hashes: true,
            verify_local_paths: false,
        };
        set.fixtures
            .iter()
            .filter(|fixture| fixture.redistributable)
            .try_for_each(|fixture| fixture.verify_payload(fixture_dir().as_path(), &policy))
            .expect("public fixture payload hashes verify");
    }
}
