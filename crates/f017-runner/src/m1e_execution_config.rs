//! Immutable, config-only command assembly and non-consuming preflight for M1-E.

use crate::artifact_paths::{
    ArtifactReference, TrustedRepositoryIdentity, TrustedRepositoryRoot,
    TRUSTED_REPOSITORY_IDENTITY_VERSION,
};
use crate::cli::{
    Config, ExecutionConfigBinding, NumericalMode, RunnerMode, StreamMode, ValidationMode,
};
use crate::json::{parse_json_no_duplicates, sha256_bytes, sha256_file};
use crate::{FailureClass, RunnerError};
use serde::Deserialize;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

pub const SCHEMA: &str = "pulsarmlx.f017.m1e-execution-config";
pub const VERSION: &str = "3.0.0";
pub const ATTEMPT: u64 = 2;
pub const DECODER_CONTRACT_SHA256: &str =
    "9a92bacda92e999a9062c154acd1b52c86e1d644f0d4d697defb2db40a85ce84";
pub const READY: &str = "READY_TO_EXECUTE_M1_E";
pub const ACTIVATION_PATH: &str =
    "specs/017-rust-native-inference-runtime/fixtures/f017-m1e-activation-v1.json";
pub const ACTIVATION_ARTIFACT_SHA256: &str =
    "a5946ba6f07d4be7c13da28549a0585b90a4ca8fa3824f52d2afd0f0b582f5c8";
pub const ACTIVATION_PAYLOAD_SHA256: &str =
    "732ed2b9a6d3df0d185c1e35628a0b6b2cf30717cb697200d45b0e8a74008149";

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Document {
    pub schema: String,
    pub schema_version: String,
    pub status: String,
    pub attempt: u64,
    pub attempt_consumed: bool,
    pub compiled_runtime_sha: String,
    pub tooling_sha: String,
    pub authorization_head_sha: String,
    pub trusted_repository_identity: TrustedRepositoryIdentity,
    pub executable_identity: ExecutableIdentity,
    pub repository_root: Root,
    pub package_root: Root,
    pub activation_fixture: ArtifactReference,
    pub activation_payload_sha256: String,
    pub repository_artifacts: BTreeMap<String, ArtifactReference>,
    pub local_artifacts: LocalArtifacts,
    pub prior_evidence: BTreeMap<String, String>,
    pub checkpoint_bindings: BTreeMap<String, String>,
    pub expert: ExpertBinding,
    pub tensors: Vec<TensorBinding>,
    pub runner: RunnerBinding,
    pub execution: ExecutionBinding,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ExecutableIdentity {
    pub sha256: String,
    pub build_profile: String,
    pub architecture: String,
    pub feature_flags: Vec<String>,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Root {
    pub path_kind: String,
    pub path: PathBuf,
    pub identity: String,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct LocalArtifacts {
    pub environment_manifest: LocalFile,
    pub checkpoint_manifest: LocalFile,
    pub runner_binary: LocalFile,
    pub oracle_launcher: LocalFile,
    pub target_shard: TargetShard,
    pub oracle_output: PathBuf,
    pub package_output: PathBuf,
    pub attempt_state_output: PathBuf,
    pub preflight_evidence_output: PathBuf,
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
    pub ordinal: u64,
    pub basename: String,
    pub byte_size: u64,
    pub content_sha256: String,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ExpertBinding {
    pub layer: u64,
    pub expert: u64,
    pub symbolic_id: String,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct TensorBinding {
    pub role: String,
    pub name: String,
    pub layer: u64,
    pub expert: u64,
    pub quantization: String,
    pub gguf_shape: Vec<u64>,
    pub logical_matrix_shape: [u64; 2],
    pub shard_ordinal: u64,
    pub offset: u64,
    pub packed_length: u64,
    pub packed_row_width: u64,
    pub catalog_entry_sha256: String,
    pub decoder_contract_sha256: String,
    pub path_kind: String,
    pub allowed_read_count: u64,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct RunnerBinding {
    pub mode: String,
    pub memory_floor_bytes: u64,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ExecutionBinding {
    pub conceptual_expert_count: u64,
    pub repeat_count: u64,
    pub native_dispatch_count: u64,
    pub maximum_payload_count: u64,
    pub maximum_positional_reads: u64,
    pub maximum_shard_opens: u64,
    pub compressed_byte_budget: u64,
    pub auto_retry: bool,
    pub stop_before_m1_f: bool,
}

pub struct Loaded {
    pub config: Config,
    pub document: Document,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct AttemptState {
    schema: String,
    schema_version: String,
    attempt: u64,
    state: String,
    execution_config_sha256: String,
}

pub fn load(
    path: &Path,
    expected_sha256: &str,
    preflight_only: bool,
) -> Result<Loaded, RunnerError> {
    require_sha(expected_sha256)?;
    let bytes = fs::read(path).map_err(|e| error("m1e_config_read", e))?;
    if sha256_bytes(&bytes) != expected_sha256 {
        return Err(message(
            "m1e_config_hash",
            "immutable execution config hash mismatch",
        ));
    }
    let document: Document =
        parse_json_no_duplicates(&bytes).map_err(|e| message("m1e_config_schema", e))?;
    validate(&document)?;
    if preflight_only {
        if document.local_artifacts.attempt_state_output.exists() {
            return Err(message(
                "m1e_attempt_consumed",
                "M1-E execution-state marker already exists",
            ));
        }
    } else {
        validate_attempt_state(
            &document.local_artifacts.attempt_state_output,
            expected_sha256,
        )?;
    }
    let package = document.local_artifacts.package_output.clone();
    let mode = if preflight_only {
        RunnerMode::M1ePreflight
    } else if document.runner.mode == "fixture_expert" {
        RunnerMode::FixtureExpert { package }
    } else {
        RunnerMode::RealExpert { package }
    };
    let config = Config {
        out: if preflight_only {
            document.local_artifacts.preflight_evidence_output.clone()
        } else {
            document.local_artifacts.evidence_output.clone()
        },
        validation_mode: ValidationMode::GoldenStrict,
        stream_mode: StreamMode::OwnedDevice,
        memory_floor_bytes: document.runner.memory_floor_bytes,
        environment_manifest: document.local_artifacts.environment_manifest.path.clone(),
        repository_root: Some(document.repository_root.path.clone()),
        checkpoint_manifest: Some(document.local_artifacts.checkpoint_manifest.path.clone()),
        tokens: vec![],
        n_new: 0,
        expected_token: None,
        numerical_mode: Some(NumericalMode::ProductionMlxTierB),
        mode,
        execution_config: Some(ExecutionConfigBinding {
            path: path.to_owned(),
            sha256: expected_sha256.to_owned(),
            attempt: ATTEMPT,
        }),
    };
    Ok(Loaded { config, document })
}

pub fn verify_unchanged(binding: &ExecutionConfigBinding) -> Result<(), RunnerError> {
    let actual = sha256_file(&binding.path).map_err(|e| error("m1e_config_rehash", e))?;
    if actual != binding.sha256 {
        return Err(message(
            "m1e_config_mutated",
            "execution config changed after preflight",
        ));
    }
    Ok(())
}

fn validate_attempt_state(path: &Path, config_sha256: &str) -> Result<(), RunnerError> {
    let bytes = fs::read(path).map_err(|e| error("m1e_attempt_state_read", e))?;
    let state: AttemptState =
        parse_json_no_duplicates(&bytes).map_err(|e| message("m1e_attempt_state_schema", e))?;
    if state.schema != "pulsarmlx.f017.m1e-attempt-state"
        || state.schema_version != "1.0.0"
        || state.attempt != ATTEMPT
        || state.state != "EXECUTION_STARTED"
        || state.execution_config_sha256 != config_sha256
    {
        return Err(message(
            "m1e_attempt_state",
            "M1-E execution-state marker binding mismatch",
        ));
    }
    Ok(())
}

fn validate(document: &Document) -> Result<(), RunnerError> {
    if document.schema != SCHEMA
        || document.schema_version != VERSION
        || document.status != READY
        || document.attempt != ATTEMPT
        || document.attempt_consumed
        || document.compiled_runtime_sha != env!("PULSARMLX_SOURCE_SHA")
        || document.tooling_sha.len() != 40
        || document.authorization_head_sha.len() != 40
    {
        return Err(message(
            "m1e_config_identity",
            "M1-E config identity/state mismatch",
        ));
    }
    if document.repository_root.path_kind != "absolute_private_local"
        || document.repository_root.identity != document.authorization_head_sha
        || document.package_root.path_kind != "absolute_private_local"
        || document.package_root.identity != "m1e_attempt_2_private_package_root"
    {
        return Err(message("m1e_config_roots", "typed root binding mismatch"));
    }
    reject_symlink(&document.repository_root.path)?;
    reject_symlink(&document.package_root.path)?;
    if document.trusted_repository_identity.contract_version != TRUSTED_REPOSITORY_IDENTITY_VERSION
        || document.trusted_repository_identity.compiled_runtime_sha
            != document.compiled_runtime_sha
        || document.trusted_repository_identity.tooling_sha != document.tooling_sha
        || document.trusted_repository_identity.authorization_head_sha
            != document.authorization_head_sha
    {
        return Err(message(
            "m1e_repository_identity_binding",
            "trusted repository identity does not match execution identities",
        ));
    }
    let (repository, _) = TrustedRepositoryRoot::open_v2(
        &document.repository_root.path,
        &document.trusted_repository_identity,
    )?;
    if document.activation_fixture.symbolic_path != Path::new(ACTIVATION_PATH)
        || document.activation_fixture.content_sha256 != ACTIVATION_ARTIFACT_SHA256
        || document.activation_fixture.logical_role != "activation_fixture"
        || document.activation_payload_sha256 != ACTIVATION_PAYLOAD_SHA256
    {
        return Err(message(
            "m1e_activation_binding",
            "activation path/payload binding mismatch",
        ));
    }
    repository.resolve(&document.activation_fixture)?;
    validate_artifacts(&repository, &document.repository_artifacts)?;
    if document
        .repository_artifacts
        .get("trusted_repository_identity_contract")
        .map(|artifact| artifact.content_sha256.as_str())
        != Some(
            document
                .trusted_repository_identity
                .contract_sha256
                .as_str(),
        )
    {
        return Err(message(
            "m1e_repository_identity_contract",
            "trusted repository contract hash is not directly bound",
        ));
    }
    validate_prior(document)?;
    validate_expert(document)?;
    validate_local(document)?;
    Ok(())
}

fn validate_artifacts(
    repository: &TrustedRepositoryRoot,
    artifacts: &BTreeMap<String, ArtifactReference>,
) -> Result<(), RunnerError> {
    let expected = [
        (
            "attempt_2_handoff",
            "docs/architecture/reviews/f017-m1-e-attempt-2-handoff.md",
        ),
        (
            "boundary_contract",
            "specs/017-rust-native-inference-runtime/contracts/m1e-expert-boundary-v1.json",
        ),
        (
            "decoder_contract",
            "specs/017-rust-native-inference-runtime/contracts/m1e-decoder-contract-v2.json",
        ),
        (
            "scaffold_contract",
            "specs/017-rust-native-inference-runtime/contracts/m1e-exact-scaffold-v1.json",
        ),
        (
            "tier_b_contract",
            "specs/017-rust-native-inference-runtime/contracts/m1e-expert-tier-b-v1.json",
        ),
        (
            "repeat_integrity_contract",
            "specs/017-rust-native-inference-runtime/contracts/m1e-repeat-integrity-v1.json",
        ),
        (
            "timing_contract",
            "specs/017-rust-native-inference-runtime/contracts/m1e-timing-v1.json",
        ),
        (
            "evidence_schema",
            "specs/017-rust-native-inference-runtime/contracts/m1e-evidence-v1.schema.json",
        ),
        (
            "execution_config_schema",
            "specs/017-rust-native-inference-runtime/contracts/m1e-execution-config-v3.schema.json",
        ),
        (
            "path_resolution_contract",
            "specs/017-rust-native-inference-runtime/contracts/m1d-artifact-path-resolution-v1.json",
        ),
        (
            "trusted_repository_identity_contract",
            "specs/017-rust-native-inference-runtime/contracts/trusted-repository-identity-v2.json",
        ),
        (
            "activation_generator",
            "scripts/research/generate_f017_m1e_activation.py",
        ),
        (
            "execution_config_preparer",
            "scripts/research/prepare_f017_m1e_execution.py",
        ),
        (
            "authorized_launcher",
            "scripts/research/run_f017_m1e_authorized.py",
        ),
        (
            "real_reference_preparer",
            "scripts/research/prepare_f017_m1e_real_reference.py",
        ),
        (
            "independent_iq2_decoder",
            "scripts/research/iq2_xxs_dequant.py",
        ),
        (
            "independent_iq3_decoder",
            "scripts/research/iq3_xxs_dequant.py",
        ),
        (
            "third_iq3_decoder",
            "scripts/research/iq3_xxs_spec_decoder.py",
        ),
        (
            "iq3_order_regression",
            "specs/017-rust-native-inference-runtime/fixtures/f017-iq3-xxs-order-regression-v1.json",
        ),
    ];
    if artifacts.len() != expected.len() {
        return Err(message(
            "m1e_artifact_set",
            "execution-controlling artifact set mismatch",
        ));
    }
    for (role, path) in expected {
        let artifact = artifacts
            .get(role)
            .ok_or_else(|| message("m1e_artifact_set", format!("missing {role}")))?;
        if artifact.logical_role != role || artifact.symbolic_path != Path::new(path) {
            return Err(message(
                "m1e_artifact_path",
                format!("{role} symbolic path mismatch"),
            ));
        }
        repository.resolve(artifact)?;
    }
    Ok(())
}

fn validate_prior(document: &Document) -> Result<(), RunnerError> {
    let prior = [
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
        (
            "m1_d",
            "dc5c4900da0cb0c2d293108a4abbdeccccd3c23899db265a84f73fda24ada53c",
        ),
        (
            "m1_e_attempt_1",
            "346d6302648d463738b0ee0f7fc04a34f664675cccb60a181e3393b88b02b119",
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
    if document.prior_evidence.len() != 5
        || prior
            .iter()
            .any(|(k, v)| document.prior_evidence.get(*k).map(String::as_str) != Some(*v))
        || document.checkpoint_bindings.len() != 3
        || checkpoint
            .iter()
            .any(|(k, v)| document.checkpoint_bindings.get(*k).map(String::as_str) != Some(*v))
    {
        return Err(message(
            "m1e_prior_binding",
            "prior evidence/checkpoint binding mismatch",
        ));
    }
    Ok(())
}

fn validate_expert(document: &Document) -> Result<(), RunnerError> {
    if document.expert.layer != 3
        || document.expert.expert != 15
        || document.expert.symbolic_id != "blk.3.expert.15"
        || document.tensors.len() != 3
        || document.execution.conceptual_expert_count != 1
        || document.execution.repeat_count != 10
        || document.execution.native_dispatch_count != 30
        || document.execution.maximum_payload_count != 3
        || document.execution.maximum_positional_reads != 3
        || document.execution.maximum_shard_opens != 1
        || document.execution.compressed_byte_budget != 11_304_960
        || document.execution.auto_retry
        || !document.execution.stop_before_m1_f
    {
        return Err(message(
            "m1e_execution_bounds",
            "one-expert execution bounds mismatch",
        ));
    }
    let expected = [
        (
            "gate",
            "blk.3.ffn_gate_exps.weight",
            "IQ2_XXS",
            3_423_197_024,
            3_244_032,
            1_584,
            "42e379023728565d323fff8b120f2c6dff6fa50f10d9ad1cceb3e3597af36354",
        ),
        (
            "up",
            "blk.3.ffn_up_exps.weight",
            "IQ2_XXS",
            4_268_636_000,
            3_244_032,
            1_584,
            "011ccab7ca2293da5b0d1112172b2dccd4b2cdb2482672dd217f996280223119",
        ),
        (
            "down",
            "blk.3.ffn_down_exps.weight",
            "IQ3_XXS",
            2_203_342_688,
            4_816_896,
            784,
            "1c7a04eb897d242a621a09c6dfb78c3e92b407dff44ddf8cf67187dae50081e1",
        ),
    ];
    let roles = document
        .tensors
        .iter()
        .map(|v| v.role.as_str())
        .collect::<BTreeSet<_>>();
    if roles != BTreeSet::from(["gate", "up", "down"]) {
        return Err(message(
            "m1e_tensor_set",
            "tensor roles must be unique and exact",
        ));
    }
    for (role, name, quant, offset, length, row, catalog) in expected {
        let t = document.tensors.iter().find(|t| t.role == role).unwrap();
        if t.name != name
            || t.layer != 3
            || t.expert != 15
            || t.quantization != quant
            || t.gguf_shape
                != if role == "down" {
                    vec![2048, 6144, 256]
                } else {
                    vec![6144, 2048, 256]
                }
            || t.logical_matrix_shape
                != if role == "down" {
                    [6144, 2048]
                } else {
                    [2048, 6144]
                }
            || t.shard_ordinal != 2
            || t.offset != offset
            || t.packed_length != length
            || t.packed_row_width != row
            || t.catalog_entry_sha256 != catalog
            || t.decoder_contract_sha256 != DECODER_CONTRACT_SHA256
            || t.path_kind != "bounded_checkpoint_range"
            || t.allowed_read_count != 1
        {
            return Err(message(
                "m1e_tensor_binding",
                format!("{role} tensor mismatch"),
            ));
        }
    }
    if !matches!(
        document.runner.mode.as_str(),
        "fixture_expert" | "real_expert"
    ) || document.runner.memory_floor_bytes
        != if document.runner.mode == "real_expert" {
            17_179_869_184
        } else {
            1
        }
    {
        return Err(message("m1e_runner", "runner mode/memory mismatch"));
    }
    Ok(())
}

fn validate_local(document: &Document) -> Result<(), RunnerError> {
    let package_root =
        fs::canonicalize(&document.package_root.path).map_err(|e| error("m1e_package_root", e))?;
    for file in [
        &document.local_artifacts.environment_manifest,
        &document.local_artifacts.checkpoint_manifest,
        &document.local_artifacts.runner_binary,
        &document.local_artifacts.oracle_launcher,
    ] {
        if file.path_kind != "absolute_private_local" || !file.path.is_absolute() {
            return Err(message("m1e_local_path", "local path binding mismatch"));
        }
        reject_symlink(&file.path)?;
        if sha256_file(&file.path).map_err(|e| error("m1e_local_hash", e))? != file.content_sha256 {
            return Err(message("m1e_local_hash", "local artifact hash mismatch"));
        }
    }
    if document.local_artifacts.runner_binary.content_sha256 != document.executable_identity.sha256
        || document.executable_identity.build_profile != "release"
        || document.executable_identity.architecture != std::env::consts::ARCH
        || document.executable_identity.feature_flags != vec!["pulsar_native_mlx".to_owned()]
    {
        return Err(message(
            "m1e_executable_identity",
            "compiled executable attestation mismatch",
        ));
    }
    let shard = &document.local_artifacts.target_shard;
    if shard.path_kind != "absolute_private_local" || !shard.path.is_absolute() {
        return Err(message(
            "m1e_shard_path",
            "target shard path binding mismatch",
        ));
    }
    reject_symlink(&shard.path)?;
    let metadata = fs::metadata(&shard.path).map_err(|e| error("m1e_shard_metadata", e))?;
    if !metadata.is_file()
        || shard.ordinal != 2
        || shard.basename != "GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf"
            && document.runner.mode == "real_expert"
        || metadata.len() != shard.byte_size
        || require_sha(&shard.content_sha256).is_err()
    {
        return Err(message(
            "m1e_shard_metadata",
            "target shard metadata/hash identity malformed",
        ));
    }
    for path in [
        &document.local_artifacts.oracle_output,
        &document.local_artifacts.package_output,
        &document.local_artifacts.attempt_state_output,
    ] {
        if !path.is_absolute()
            || path
                .parent()
                .and_then(|p| fs::canonicalize(p).ok())
                .as_deref()
                != Some(package_root.as_path())
        {
            return Err(message(
                "m1e_package_output",
                "private output escapes package root",
            ));
        }
    }
    if !document
        .local_artifacts
        .preflight_evidence_output
        .is_absolute()
        || !document.local_artifacts.evidence_output.is_absolute()
        || document.local_artifacts.preflight_evidence_output
            == document.local_artifacts.evidence_output
    {
        return Err(message(
            "m1e_evidence_output",
            "preflight and production evidence outputs must be distinct absolute paths",
        ));
    }
    let unique_outputs = [
        &document.local_artifacts.oracle_output,
        &document.local_artifacts.package_output,
        &document.local_artifacts.attempt_state_output,
        &document.local_artifacts.preflight_evidence_output,
        &document.local_artifacts.evidence_output,
    ]
    .into_iter()
    .collect::<BTreeSet<_>>();
    if unique_outputs.len() != 5 {
        return Err(message(
            "m1e_output_alias",
            "all M1-E output targets must be distinct",
        ));
    }
    Ok(())
}

fn reject_symlink(path: &Path) -> Result<(), RunnerError> {
    if fs::symlink_metadata(path)
        .map_err(|e| error("m1e_path_metadata", e))?
        .file_type()
        .is_symlink()
    {
        return Err(message("m1e_symlink", "symlinked bound path is forbidden"));
    }
    Ok(())
}
fn require_sha(value: &str) -> Result<(), RunnerError> {
    if value.len() != 64 || !value.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err(message("m1e_sha", "malformed SHA-256"));
    }
    Ok(())
}
fn error(code: &'static str, e: impl std::fmt::Display) -> RunnerError {
    RunnerError::new(FailureClass::InfrastructureEvidence, code, e.to_string())
}
fn message(code: &'static str, m: impl Into<String>) -> RunnerError {
    RunnerError::new(FailureClass::InfrastructureEvidence, code, m)
}
