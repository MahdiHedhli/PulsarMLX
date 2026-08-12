//! Immutable, config-only command assembly for M1-D attempt 3.

use crate::artifact_paths::{ArtifactReference, TrustedRepositoryRoot};
use crate::cli::{
    Config, ExecutionConfigBinding, NumericalMode, RunnerMode, StreamMode, ValidationMode,
};
use crate::json::{parse_json_no_duplicates, sha256_bytes, sha256_file};
use crate::{FailureClass, RunnerError};
use serde::Deserialize;
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

pub const EXECUTION_CONFIG_SCHEMA: &str = "pulsarmlx.f017.m1d-execution-config";
pub const EXECUTION_CONFIG_VERSION: &str = "1.0.0";
pub const EXECUTION_CONFIG_READY: &str = "READY_TO_EXECUTE_ATTEMPT_3";
pub const ACTIVATION_SYMBOLIC_PATH: &str =
    "specs/017-rust-native-inference-runtime/fixtures/f017-m1d-projection-oracle-v1.json";
const ACTIVATION_ARTIFACT_SHA256: &str =
    "1727e63a5daee0ffbb0bf6dea11ea5ecf1b559850632785d5c8864c2bbaf503a";
const ACTIVATION_PAYLOAD_SHA256: &str =
    "dfc1df6cc6efa38c5c0f5bf086757ed78baf4cfc6f721da1e0ae7f73560193c2";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LoadedExecutionConfig {
    pub config: Config,
    pub document: ExecutionConfigDocument,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ExecutionConfigDocument {
    pub schema: String,
    pub schema_version: String,
    pub status: String,
    pub attempt: u64,
    pub attempt_consumed: bool,
    pub runtime_sha: String,
    pub tooling_sha: String,
    pub repository_root: RootBinding,
    pub package_root: RootBinding,
    pub activation_fixture: ArtifactReference,
    pub activation_payload_sha256: String,
    pub provenance: Provenance,
    pub repository_artifacts: BTreeMap<String, ArtifactReference>,
    pub local_artifacts: LocalArtifacts,
    pub prior_evidence: BTreeMap<String, String>,
    pub checkpoint_bindings: BTreeMap<String, String>,
    pub runner: RunnerBinding,
    pub execution: ExecutionBounds,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct RootBinding {
    pub path_kind: String,
    pub path: PathBuf,
    pub identity: String,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Provenance {
    pub activation_generation_source_sha256: String,
    pub fixture_finalization_source_sha256: String,
    pub real_reference_preparer_sha256: String,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct LocalArtifacts {
    pub environment_manifest: LocalFile,
    pub checkpoint_manifest: LocalFile,
    pub target_shard: TargetShard,
    pub oracle_output: PathBuf,
    pub package_output: PathBuf,
    pub evidence_output: PathBuf,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct LocalFile {
    pub path_kind: String,
    pub path: PathBuf,
    pub content_sha256: String,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct TargetShard {
    pub path_kind: String,
    pub path: PathBuf,
    pub basename: String,
    pub ordinal: u64,
    pub byte_size: u64,
    pub sha256: String,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct RunnerBinding {
    pub mode: String,
    pub validation_mode: String,
    pub stream_mode: String,
    pub numerical_mode: String,
    pub memory_floor_bytes: u64,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ExecutionBounds {
    pub conceptual_projection_count: u64,
    pub repeat_count: u64,
    pub native_dispatch_count: u64,
    pub auto_retry: bool,
    pub stop_before_m1_e: bool,
}

pub fn load(path: &Path, expected_sha256: &str) -> Result<LoadedExecutionConfig, RunnerError> {
    require_sha(expected_sha256, "execution config SHA-256")?;
    let bytes = fs::read(path).map_err(|error| config_error("m1d_execution_config_read", error))?;
    if sha256_bytes(&bytes) != expected_sha256 {
        return Err(config_message(
            "m1d_execution_config_hash",
            "immutable execution config SHA-256 mismatch",
        ));
    }
    let document: ExecutionConfigDocument = parse_json_no_duplicates(&bytes)
        .map_err(|error| config_error("m1d_execution_config_schema", error))?;
    validate(&document)?;
    let package = document.local_artifacts.package_output.clone();
    let mode = match document.runner.mode.as_str() {
        "fixture_projection" => RunnerMode::FixtureProjection { package },
        "real_projection" => RunnerMode::RealProjection { package },
        _ => {
            return Err(config_message(
                "m1d_execution_mode",
                "unsupported execution mode",
            ))
        }
    };
    let config = Config {
        out: document.local_artifacts.evidence_output.clone(),
        validation_mode: ValidationMode::GoldenStrict,
        stream_mode: StreamMode::OwnedDevice,
        memory_floor_bytes: document.runner.memory_floor_bytes,
        environment_manifest: document.local_artifacts.environment_manifest.path.clone(),
        repository_root: Some(document.repository_root.path.clone()),
        checkpoint_manifest: Some(document.local_artifacts.checkpoint_manifest.path.clone()),
        tokens: Vec::new(),
        n_new: 0,
        expected_token: None,
        numerical_mode: Some(NumericalMode::ProductionMlxTierB),
        mode,
        execution_config: Some(ExecutionConfigBinding {
            path: path.to_owned(),
            sha256: expected_sha256.to_owned(),
            attempt: 3,
        }),
    };
    Ok(LoadedExecutionConfig { config, document })
}

pub fn verify_unchanged(binding: &ExecutionConfigBinding) -> Result<(), RunnerError> {
    let actual = sha256_file(&binding.path)
        .map_err(|error| config_error("m1d_execution_config_rehash", error))?;
    if actual != binding.sha256 {
        return Err(config_message(
            "m1d_execution_config_mutated",
            "execution config changed after preflight",
        ));
    }
    Ok(())
}

fn validate(document: &ExecutionConfigDocument) -> Result<(), RunnerError> {
    if document.schema != EXECUTION_CONFIG_SCHEMA
        || document.schema_version != EXECUTION_CONFIG_VERSION
        || document.status != EXECUTION_CONFIG_READY
        || document.attempt != 3
        || document.attempt_consumed
    {
        return Err(config_message(
            "m1d_execution_config_state",
            "execution config is not the unconsumed attempt-3 schema",
        ));
    }
    if document.runtime_sha != env!("PULSARMLX_SOURCE_SHA") || !is_git_sha(&document.tooling_sha) {
        return Err(config_message(
            "m1d_execution_identity",
            "runtime/tooling identity mismatch",
        ));
    }
    if document.repository_root.path_kind != "absolute_private_local"
        || document.repository_root.identity != document.runtime_sha
        || document.package_root.path_kind != "absolute_private_local"
        || document.package_root.identity != "m1d_attempt_3_private_package_root"
    {
        return Err(config_message(
            "m1d_execution_roots",
            "typed root binding mismatch",
        ));
    }
    reject_symlink(
        &document.repository_root.path,
        "m1d_execution_repository_symlink",
    )?;
    reject_symlink(&document.package_root.path, "m1d_execution_package_symlink")?;
    let repository = TrustedRepositoryRoot::open(&document.repository_root.path)?;
    if document.activation_fixture.symbolic_path != Path::new(ACTIVATION_SYMBOLIC_PATH)
        || document.activation_fixture.content_sha256 != ACTIVATION_ARTIFACT_SHA256
        || document.activation_fixture.logical_role != "activation_fixture"
        || document.activation_payload_sha256 != ACTIVATION_PAYLOAD_SHA256
    {
        return Err(config_message(
            "m1d_activation_binding",
            "activation symbolic path/content binding mismatch",
        ));
    }
    repository.resolve(&document.activation_fixture)?;
    validate_provenance(&document.provenance)?;
    validate_repository_artifacts(&repository, document)?;
    validate_prior_bindings(document)?;
    validate_runner(document)?;
    validate_local_artifacts(document)?;
    Ok(())
}

fn validate_provenance(value: &Provenance) -> Result<(), RunnerError> {
    if value.activation_generation_source_sha256
        != "29c5c51a8f440e06d6584a71e0b79283d2bd6f806a2435c15ff93f3a0cae7984"
        || value.fixture_finalization_source_sha256
            != "0299066d46211d1921ded772ab907fcd9e9f1c8e3d2c497d979914a30c3dbd92"
        || require_sha(&value.real_reference_preparer_sha256, "preparer SHA-256").is_err()
    {
        return Err(config_message(
            "m1d_execution_provenance",
            "provenance binding mismatch",
        ));
    }
    Ok(())
}

fn validate_repository_artifacts(
    repository: &TrustedRepositoryRoot,
    document: &ExecutionConfigDocument,
) -> Result<(), RunnerError> {
    let expected: [(&str, &str, Option<&str>); 11] = [
        ("fixture_finalization_source", "scripts/research/generate_f017_m1d_projection_oracle.py", Some("0299066d46211d1921ded772ab907fcd9e9f1c8e3d2c497d979914a30c3dbd92")),
        ("real_reference_preparer", "scripts/research/prepare_f017_m1d_real_reference.py", None),
        ("boundary_contract", "specs/017-rust-native-inference-runtime/contracts/m1d-projection-boundary-v1.json", Some("d4333ab9a6cd8638434f61c4c78f729869c5690305cc6de7ba86add611443613")),
        ("decoder_contract", "specs/017-rust-native-inference-runtime/contracts/m1d-q8-0-decoder-v1.json", Some("aac49f628446cc41c295e690114632673aefc4e3f08663bd11216db9fd9cfbdd")),
        ("scaffold_contract", "specs/017-rust-native-inference-runtime/contracts/m1d-exact-scaffold-v1.json", Some("3948039430cf48509a63757d97a21099b6e08ea46fcf6f022df06493a5f8a6b5")),
        ("tier_b_contract", "specs/017-rust-native-inference-runtime/contracts/production-m1d-projection-tier-b-v1.json", Some("f93e7a90684c93e78c03e054f62be932b3e16a120e63f41ba1d64f6d6e26a28b")),
        ("repeat_integrity_contract", "specs/017-rust-native-inference-runtime/contracts/m1d-repeat-integrity-v1.json", Some("1e8ceff5bca49d8c22c38342c3e938af189b819333c075558e1e242869a6685f")),
        ("oracle_ordering_contract", "specs/017-rust-native-inference-runtime/contracts/m1d-oracle-ordering-v1.json", Some("f8b2d48d4a3ff4ef502c33c4b29c4f2390f80ff4d03a2964c988a189ea341528")),
        ("path_resolution_contract", "specs/017-rust-native-inference-runtime/contracts/m1d-artifact-path-resolution-v1.json", Some("40c66a00ea9dcc2b58dc01c7f336cdb5a9098c0ea59920c384727e6ef9cc360d")),
        ("package_schema", "specs/017-rust-native-inference-runtime/contracts/m1d-projection-package-v2.schema.json", Some("eec3ae97ac8c2ecb04ac982abe8b1bcec313a57888fa5bb66370e31485fc2e2a")),
        ("command_assembly_contract", "specs/017-rust-native-inference-runtime/contracts/m1d-command-assembly-v1.json", None),
    ];
    if document.repository_artifacts.len() != expected.len() + 1
        || !document
            .repository_artifacts
            .contains_key("execution_config_schema")
    {
        return Err(config_message(
            "m1d_execution_artifact_set",
            "repository artifact set mismatch",
        ));
    }
    for (role, path, digest) in expected {
        let reference = document.repository_artifacts.get(role).ok_or_else(|| {
            config_message("m1d_execution_artifact_set", format!("missing {role}"))
        })?;
        if reference.logical_role != role || reference.symbolic_path != Path::new(path) {
            return Err(config_message(
                "m1d_execution_artifact_path",
                format!("{role} symbolic path mismatch"),
            ));
        }
        if digest.is_some_and(|digest| reference.content_sha256 != digest) {
            return Err(config_message(
                "m1d_execution_artifact_hash",
                format!("{role} frozen hash mismatch"),
            ));
        }
        repository.resolve(reference)?;
    }
    let schema = &document.repository_artifacts["execution_config_schema"];
    if schema.logical_role != "execution_config_schema"
        || schema.symbolic_path != Path::new("specs/017-rust-native-inference-runtime/contracts/m1d-execution-config-v1.schema.json")
    {
        return Err(config_message("m1d_execution_artifact_path", "execution config schema path mismatch"));
    }
    repository.resolve(schema)?;
    if document.repository_artifacts["real_reference_preparer"].content_sha256
        != document.provenance.real_reference_preparer_sha256
    {
        return Err(config_message(
            "m1d_execution_provenance",
            "preparer artifact/provenance mismatch",
        ));
    }
    Ok(())
}

fn validate_prior_bindings(document: &ExecutionConfigDocument) -> Result<(), RunnerError> {
    let prior = [
        (
            "attempt_1",
            "a5aefaaf59583dad87765303e159986c895017c20ea80eb874cd447ad80f9a62",
        ),
        (
            "attempt_2",
            "6a87c36c380fb43393bc79cdc4e22e59bb81c0425ad0285017d6a1bc00dd79f6",
        ),
        (
            "m1_a",
            "aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805",
        ),
        (
            "m1_b",
            "9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770",
        ),
        (
            "m1_c",
            "343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e",
        ),
    ];
    let checkpoint = [
        (
            "checkpoint_set_sha256",
            "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee",
        ),
        (
            "catalog_sha256",
            "0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0",
        ),
        (
            "tensor_map_sha256",
            "ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223",
        ),
    ];
    if document.prior_evidence.len() != prior.len()
        || prior.iter().any(|(key, value)| {
            document.prior_evidence.get(*key).map(String::as_str) != Some(*value)
        })
        || document.checkpoint_bindings.len() != checkpoint.len()
        || checkpoint.iter().any(|(key, value)| {
            document.checkpoint_bindings.get(*key).map(String::as_str) != Some(*value)
        })
    {
        return Err(config_message(
            "m1d_execution_bindings",
            "prior/checkpoint binding mismatch",
        ));
    }
    Ok(())
}

fn validate_runner(document: &ExecutionConfigDocument) -> Result<(), RunnerError> {
    if document.runner.validation_mode != "golden_strict"
        || document.runner.stream_mode != "owned_device"
        || document.runner.numerical_mode != "production_mlx_tier_b"
        || !matches!(
            document.runner.mode.as_str(),
            "fixture_projection" | "real_projection"
        )
        || document.execution.conceptual_projection_count != 1
        || document.execution.repeat_count != 10
        || document.execution.native_dispatch_count != 10
        || document.execution.auto_retry
        || !document.execution.stop_before_m1_e
    {
        return Err(config_message(
            "m1d_execution_bounds",
            "runner/execution bound mismatch",
        ));
    }
    let expected_floor = if document.runner.mode == "real_projection" {
        17_179_869_184
    } else {
        1
    };
    if document.runner.memory_floor_bytes != expected_floor {
        return Err(config_message(
            "m1d_execution_memory",
            "memory floor mismatch",
        ));
    }
    Ok(())
}

fn validate_local_artifacts(document: &ExecutionConfigDocument) -> Result<(), RunnerError> {
    let package_root = fs::canonicalize(&document.package_root.path)
        .map_err(|error| config_error("m1d_execution_package_root", error))?;
    for (role, artifact) in [
        (
            "environment_manifest",
            &document.local_artifacts.environment_manifest,
        ),
        (
            "checkpoint_manifest",
            &document.local_artifacts.checkpoint_manifest,
        ),
    ] {
        if artifact.path_kind != "absolute_private_local" || !artifact.path.is_absolute() {
            return Err(config_message(
                "m1d_execution_local_path",
                format!("{role} path kind mismatch"),
            ));
        }
        reject_symlink(&artifact.path, "m1d_execution_local_symlink")?;
        let actual = sha256_file(&artifact.path)
            .map_err(|error| config_error("m1d_execution_local_hash", error))?;
        if actual != artifact.content_sha256 {
            return Err(config_message(
                "m1d_execution_local_hash",
                format!("{role} hash mismatch"),
            ));
        }
    }
    let shard = &document.local_artifacts.target_shard;
    if shard.path_kind != "absolute_private_local"
        || !shard.path.is_absolute()
        || shard.ordinal != 2
    {
        return Err(config_message(
            "m1d_execution_shard",
            "target shard binding mismatch",
        ));
    }
    reject_symlink(&shard.path, "m1d_execution_shard_symlink")?;
    let metadata =
        fs::metadata(&shard.path).map_err(|error| config_error("m1d_execution_shard", error))?;
    if !metadata.is_file()
        || metadata.len() != shard.byte_size
        || shard.path.file_name().and_then(|value| value.to_str()) != Some(&shard.basename)
        || require_sha(&shard.sha256, "target shard SHA-256").is_err()
    {
        return Err(config_message(
            "m1d_execution_shard",
            "target shard metadata mismatch",
        ));
    }
    for path in [
        &document.local_artifacts.oracle_output,
        &document.local_artifacts.package_output,
    ] {
        if !path.is_absolute()
            || path
                .parent()
                .and_then(|parent| fs::canonicalize(parent).ok())
                .as_deref()
                != Some(package_root.as_path())
        {
            return Err(config_message(
                "m1d_execution_package_output",
                "private output escapes package root",
            ));
        }
    }
    if !document.local_artifacts.evidence_output.is_absolute() {
        return Err(config_message(
            "m1d_execution_evidence_output",
            "evidence output must be explicit",
        ));
    }
    Ok(())
}

fn reject_symlink(path: &Path, code: &'static str) -> Result<(), RunnerError> {
    let metadata = fs::symlink_metadata(path).map_err(|error| config_error(code, error))?;
    if metadata.file_type().is_symlink() {
        return Err(config_message(code, "symlink is forbidden"));
    }
    Ok(())
}

fn require_sha(value: &str, role: &str) -> Result<(), RunnerError> {
    if value.len() != 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return Err(config_message(
            "m1d_execution_sha",
            format!("{role} is not a lowercase SHA-256"),
        ));
    }
    Ok(())
}

fn is_git_sha(value: &str) -> bool {
    value.len() == 40
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn config_error(code: &'static str, error: impl std::fmt::Display) -> RunnerError {
    config_message(code, error.to_string())
}

fn config_message(code: &'static str, message: impl Into<String>) -> RunnerError {
    RunnerError::new(FailureClass::InfrastructureEvidence, code, message)
}
