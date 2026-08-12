//! Canonical single-projection M1-D qualification path.
//!
//! The same package validator, bounded range reader, Q8_0 decoder, exact
//! scaffold, MLX adapter path, evidence accounting, and teardown are used by
//! checkpoint-free and later production-reviewed packages. Package kind is
//! the only admitted data-identity distinction.

use crate::checkpoint::{CheckpointKind, CheckpointManifest};
use crate::cli::{Config, RunnerMode};
use crate::evidence::Evidence;
use crate::json::{parse_json_no_duplicates, sha256_bytes};
use crate::numerical_classification::{GreedyApplicability, NumericalClassification};
use crate::qualification::{
    exact_matvec_f32, qualify_m1d_projection_tier_b, M1D_EXACT_SCAFFOLD_VERSION,
    M1D_TIER_B_CONTRACT_VERSION,
};
use crate::{FailureClass, RunnerError};
use serde::Deserialize;
use std::fs::{self, File};
use std::path::{Path, PathBuf};
use std::time::Instant;

pub const BOUNDARY_VERSION: &str = "f017-m1d-projection-boundary-v1";
pub const DECODER_VERSION: &str = "f017-q8-0-decoder-v1";
pub const ACTIVATION_SHA256: &str =
    "dfc1df6cc6efa38c5c0f5bf086757ed78baf4cfc6f721da1e0ae7f73560193c2";
const ROWS: usize = 576;
const COLUMNS: usize = 6144;
const PACKED_LENGTH: usize = 3_760_128;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ProjectionPackage {
    schema: String,
    schema_version: String,
    package_kind: String,
    boundary_contract: ContractBinding,
    decoder_contract: ContractBinding,
    scaffold_contract: ContractBinding,
    tier_b_contract: ContractBinding,
    checkpoint_set_sha256: String,
    catalog_sha256: String,
    tensor_map_sha256: String,
    prior_evidence: PriorEvidence,
    tensor: TensorRange,
    oracle_path: PathBuf,
    oracle_sha256: String,
    activation_sha256: String,
    one_attempt: bool,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct PriorEvidence {
    m1_a_sha256: String,
    m1_b_sha256: String,
    m1_c_sha256: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ContractBinding {
    version: String,
    sha256: String,
    path: PathBuf,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct TensorRange {
    name: String,
    layer: u32,
    role: String,
    shard_ordinal: usize,
    offset: u64,
    packed_length: usize,
    quantization: String,
    gguf_shape: [usize; 2],
    matrix_shape: [usize; 2],
    output_shape: [usize; 1],
    packed_sha256: String,
}

#[derive(Debug, Deserialize)]
struct Oracle {
    schema: String,
    generator: OracleGenerator,
    boundary: OracleBoundary,
    activation: OracleActivation,
    synthetic_matrix: OracleMatrix,
    oracle: OracleOutput,
    tier_b: OracleTierB,
    policies: OraclePolicies,
    checkpoint_accessed: bool,
}

#[derive(Debug, Deserialize)]
struct OracleGenerator {
    source_sha256: String,
}

#[derive(Debug, Deserialize)]
struct OracleBoundary {
    contract_version: String,
    matrix_rows: usize,
    matrix_columns: usize,
    packed_length: usize,
    output_shape: [usize; 1],
}

#[derive(Debug, Deserialize)]
struct OracleActivation {
    bytes_hex: String,
    sha256: String,
    element_count: usize,
}

#[derive(Debug, Deserialize)]
struct OracleMatrix {
    packed_sha256: String,
    decoded_f32_sha256: String,
}

#[derive(Debug, Deserialize)]
struct OracleOutput {
    generated_before_candidate: bool,
    scaffold_version: String,
    decoder_contract_version: String,
    output_f32_hex: String,
    output_sha256: String,
}

#[derive(Debug, Deserialize)]
struct OracleTierB {
    contract_version: String,
    threshold_fit_to_observed_candidate: bool,
}

#[derive(Debug, Deserialize)]
struct OraclePolicies {
    signed_zero: String,
    nan_inf: String,
    deterministic_repeat_minimum: usize,
    greedy_applicability: String,
    success_classification: String,
}

pub fn run(
    package_path: &Path,
    config: &Config,
    evidence: &mut Evidence,
) -> Result<(), RunnerError> {
    run_impl(package_path, config, evidence)
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn run_impl(
    package_path: &Path,
    config: &Config,
    evidence: &mut Evidence,
) -> Result<(), RunnerError> {
    use stream::{MlxContext, MlxDevice, MlxStreamMode};

    let root = package_path
        .parent()
        .ok_or_else(|| error("m1d_package_path", "package has no parent"))?;
    let package_bytes =
        fs::read(package_path).map_err(|e| error("m1d_package_read", e.to_string()))?;
    let package: ProjectionPackage =
        parse_json_no_duplicates(&package_bytes).map_err(|e| error("m1d_package_json", e))?;
    validate_package(&package, root, &config.mode)?;
    evidence.identity.prior_evidence.insert(
        "m1_a".to_owned(),
        package.prior_evidence.m1_a_sha256.clone(),
    );
    evidence.identity.prior_evidence.insert(
        "m1_b".to_owned(),
        package.prior_evidence.m1_b_sha256.clone(),
    );
    evidence.identity.prior_evidence.insert(
        "m1_c".to_owned(),
        package.prior_evidence.m1_c_sha256.clone(),
    );
    let oracle_bytes = fs::read(root.join(&package.oracle_path))
        .map_err(|e| error("m1d_oracle_read", e.to_string()))?;
    require_hash("m1d_oracle_hash", &oracle_bytes, &package.oracle_sha256)?;
    let oracle: Oracle =
        parse_json_no_duplicates(&oracle_bytes).map_err(|e| error("m1d_oracle_json", e))?;
    validate_oracle(&oracle, &package)?;

    let manifest_path = config
        .checkpoint_manifest
        .as_ref()
        .expect("CLI requires manifest");
    let manifest = CheckpointManifest::load(manifest_path)?;
    validate_manifest(&manifest, &package, &config.mode)?;
    evidence.identity.checkpoint.accessed = true;
    evidence.identity.checkpoint.revision = Some(manifest.immutable_revision.clone());
    evidence.identity.checkpoint.checkpoint_set_sha256 =
        Some(manifest.checkpoint_set_sha256.clone());
    evidence.identity.checkpoint.catalog_sha256 = Some(manifest.catalog_sha256.clone());
    evidence.identity.checkpoint.architecture = Some(manifest.architecture.clone());
    evidence.identity.checkpoint.tokenizer_identity = Some(manifest.tokenizer_identity.clone());
    evidence.identity.checkpoint.tensor_count = Some(manifest.tensor_count);
    let shard = manifest
        .shards
        .get(package.tensor.shard_ordinal - 1)
        .ok_or_else(|| error("m1d_shard", "package shard ordinal is absent"))?;
    let shard_path = manifest_path
        .parent()
        .unwrap_or(Path::new("."))
        .join(&shard.filename);
    let read_started = Instant::now();
    let packed = read_exact_at(
        &shard_path,
        package.tensor.offset,
        package.tensor.packed_length,
    )?;
    evidence.execution.timings.insert(
        "storage_read_seconds".to_owned(),
        read_started.elapsed().as_secs_f64(),
    );
    evidence.execution.storage.read_bytes = packed.len() as u64;
    evidence.execution.storage.read_count = 1;
    require_hash("m1d_packed_hash", &packed, &package.tensor.packed_sha256)?;
    require_hash(
        "m1d_oracle_packed_hash",
        &packed,
        &oracle.synthetic_matrix.packed_sha256,
    )?;

    let activation_bytes = decode_hex(&oracle.activation.bytes_hex)?;
    require_hash("m1d_activation_hash", &activation_bytes, ACTIVATION_SHA256)?;
    let activation = f32_from_bytes(&activation_bytes)?;
    let output_bytes = decode_hex(&oracle.oracle.output_f32_hex)?;
    require_hash(
        "m1d_reference_output_hash",
        &output_bytes,
        &oracle.oracle.output_sha256,
    )?;
    let reference = f32_from_bytes(&output_bytes)?;

    let decode_started = Instant::now();
    let mut decoded = vec![0.0_f32; ROWS * COLUMNS];
    quant::decode_q8_0_matrix(&packed, ROWS, COLUMNS, &mut decoded)
        .map_err(|e| numerical("m1d_q8_decode", e.to_string()))?;
    evidence.execution.timings.insert(
        "decode_seconds".to_owned(),
        decode_started.elapsed().as_secs_f64(),
    );
    require_hash(
        "m1d_decoded_hash",
        &f32_bytes(&decoded),
        &oracle.synthetic_matrix.decoded_f32_sha256,
    )?;

    let scaffold_started = Instant::now();
    let mut scaffold = vec![0.0_f32; ROWS];
    for _ in 0..10 {
        exact_matvec_f32(&decoded, ROWS, COLUMNS, &activation, &mut scaffold)
            .map_err(|e| numerical("m1d_scaffold", e.to_string()))?;
        if f32_bytes(&scaffold) != output_bytes {
            return Err(numerical(
                "m1d_scaffold_parity",
                "exact scaffold differs from the independent oracle",
            ));
        }
    }
    evidence.execution.timings.insert(
        "qualification_scaffold_seconds".to_owned(),
        scaffold_started.elapsed().as_secs_f64(),
    );

    let stream_before = MlxContext::debug_stream_counters().map_err(adapter_error)?;
    if MlxContext::debug_context_active() {
        return Err(lifecycle(
            "m1d_singleton",
            "MLX singleton was claimed before projection",
        ));
    }
    evidence.admission.singleton_initially_unclaimed = true;
    // MLX retains mutable host ownership until explicit array teardown. Keep
    // immutable operands separately for candidate-independent qualification.
    let qualification_matrix = decoded.clone();
    let context = MlxContext::new(
        MlxDevice::Gpu,
        match config.stream_mode {
            crate::cli::StreamMode::DefaultGpu => MlxStreamMode::BorrowedDefault,
            crate::cli::StreamMode::OwnedDevice => MlxStreamMode::Owned,
        },
    )
    .map_err(adapter_error)?;
    let import_started = Instant::now();
    let mut activation_owned = activation.clone();
    let matrix = context
        .import_f32_shaped(&mut decoded, &[ROWS, COLUMNS])
        .map_err(adapter_error)?;
    let vector = context
        .import_f32_shaped(&mut activation_owned, &[COLUMNS])
        .map_err(adapter_error)?;
    evidence.execution.timings.insert(
        "backend_import_seconds".to_owned(),
        import_started.elapsed().as_secs_f64(),
    );
    let compute_started = Instant::now();
    let mut candidate = vec![0.0_f32; ROWS];
    for _ in 0..10 {
        let result = matrix.matvec(&vector).map_err(adapter_error)?;
        result.evaluate_sync().map_err(adapter_error)?;
        result.copy_f32(&mut candidate).map_err(adapter_error)?;
        result.destroy().map_err(adapter_error)?;
    }
    evidence.execution.timings.insert(
        "backend_compute_sync_readback_seconds".to_owned(),
        compute_started.elapsed().as_secs_f64(),
    );
    let qualification = qualify_m1d_projection_tier_b(
        &qualification_matrix,
        ROWS,
        COLUMNS,
        &activation,
        &reference,
        &candidate,
    )
    .map_err(|e| numerical("m1d_tier_b", e.to_string()))?;
    if !qualification.passes {
        return Err(numerical(
            "m1d_tier_b_failed",
            "production output violates the frozen M1-D Tier-B contract",
        ));
    }

    vector.destroy().map_err(adapter_error)?;
    matrix.destroy().map_err(adapter_error)?;
    let ownership = context.ownership_snapshot().map_err(adapter_error)?;
    context.synchronize().map_err(adapter_error)?;
    drop(context);
    let stream_after = MlxContext::debug_stream_counters().map_err(adapter_error)?;
    evidence.lifecycle.post.managed_created = ownership.managed_created;
    evidence.lifecycle.post.managed_destroyed = ownership.managed_destroyed;
    evidence.lifecycle.post.derived_created = ownership.derived_created;
    evidence.lifecycle.post.derived_destroyed = ownership.derived_destroyed;
    evidence.lifecycle.post.callback_count = ownership.callback_count;
    evidence.lifecycle.post.default_cpu_stream_created = stream_after.default_cpu_created;
    evidence.lifecycle.post.default_cpu_stream_freed = stream_after.default_cpu_freed;
    evidence.lifecycle.post.default_gpu_stream_created = stream_after.default_gpu_created;
    evidence.lifecycle.post.default_gpu_stream_freed = stream_after.default_gpu_freed;
    evidence.lifecycle.post.owned_stream_created = stream_after.owned_created;
    evidence.lifecycle.post.owned_stream_freed = stream_after.owned_freed;
    evidence.lifecycle.post.active_contexts = u64::from(MlxContext::debug_context_active());
    evidence.lifecycle.post.singleton_claimed = MlxContext::debug_context_active();
    evidence.lifecycle.reconciled = ownership.managed_created == ownership.managed_destroyed
        && ownership.derived_created == ownership.derived_destroyed
        && ownership.callback_count == ownership.managed_created
        && stream_after.default_cpu_created - stream_before.default_cpu_created
            == stream_after.default_cpu_freed - stream_before.default_cpu_freed
        && stream_after.default_gpu_created - stream_before.default_gpu_created
            == stream_after.default_gpu_freed - stream_before.default_gpu_freed
        && stream_after.owned_created - stream_before.owned_created
            == stream_after.owned_freed - stream_before.owned_freed
        && !evidence.lifecycle.post.singleton_claimed;
    if !evidence.lifecycle.reconciled {
        return Err(lifecycle(
            "m1d_lifecycle",
            "projection lifecycle did not reconcile",
        ));
    }

    evidence.execution.dispatch.native = 10;
    evidence.execution.projection_count = 1;
    evidence.execution.quant_decode_count = 1;
    evidence.execution.numerical_classification =
        Some(NumericalClassification::NumericallyQualifiedGreedyNotApplicable);
    evidence.execution.numerical.greedy_applicability = Some(GreedyApplicability::NotApplicable);
    evidence.execution.numerical.oracle_generator_sha = Some(oracle.generator.source_sha256);
    evidence.execution.numerical.scaffold_version = Some(M1D_EXACT_SCAFFOLD_VERSION.to_owned());
    evidence.execution.numerical.production_backend_version =
        Some("mlx-c-matmul; mlx-native-0.31.2; mlx-c-0.6.0".to_owned());
    evidence.execution.numerical.frozen_contract_version =
        Some(M1D_TIER_B_CONTRACT_VERSION.to_owned());
    evidence
        .execution
        .numerical
        .frozen_contract_versions
        .insert(
            package.boundary_contract.version,
            package.boundary_contract.sha256,
        );
    evidence
        .execution
        .numerical
        .frozen_contract_versions
        .insert(
            package.decoder_contract.version,
            package.decoder_contract.sha256,
        );
    evidence
        .execution
        .numerical
        .frozen_contract_versions
        .insert(
            package.scaffold_contract.version,
            package.scaffold_contract.sha256,
        );
    evidence
        .execution
        .numerical
        .frozen_contract_versions
        .insert(
            package.tier_b_contract.version,
            package.tier_b_contract.sha256,
        );
    evidence.execution.numerical.bit_mismatch_count =
        Some(qualification.metrics.bit_mismatch_count as u64);
    evidence.execution.numerical.max_abs_error = Some(qualification.metrics.max_abs_error);
    evidence.execution.numerical.relative_error = qualification.metrics.max_relative_error;
    evidence.execution.numerical.rmse = Some(qualification.metrics.rmse);
    evidence.execution.numerical.cosine_similarity = qualification.metrics.cosine_similarity;
    evidence.execution.numerical.deterministic_repeat_count = Some(10);
    evidence.execution.numerical.first_divergence = qualification
        .metrics
        .first_divergence
        .map(|v| serde_json::to_value(v).expect("serializable"));
    evidence.execution.progress_state = "m1d_one_projection_complete".to_owned();
    Ok(())
}

#[cfg(not(all(target_os = "macos", pulsar_native_mlx)))]
fn run_impl(
    _package: &Path,
    _config: &Config,
    _evidence: &mut Evidence,
) -> Result<(), RunnerError> {
    Err(RunnerError::new(
        FailureClass::AdmissionEnvironment,
        "native_mlx_unavailable",
        "M1-D projection requires the production native MLX adapter",
    ))
}

fn validate_package(
    package: &ProjectionPackage,
    root: &Path,
    mode: &RunnerMode,
) -> Result<(), RunnerError> {
    let expected_kind = if matches!(mode, RunnerMode::RealProjection { .. }) {
        "production_reviewed"
    } else {
        "checkpoint_free_fixture"
    };
    if package.schema != "pulsarmlx.f017.m1d-projection-package"
        || package.schema_version != "1.0.0"
        || package.package_kind != expected_kind
        || !package.one_attempt
        || package.boundary_contract.version != BOUNDARY_VERSION
        || package.decoder_contract.version != DECODER_VERSION
        || package.scaffold_contract.version != M1D_EXACT_SCAFFOLD_VERSION
        || package.tier_b_contract.version != M1D_TIER_B_CONTRACT_VERSION
        || package.tensor.name != "blk.0.attn_kv_a_mqa.weight"
        || package.tensor.layer != 0
        || package.tensor.role != "mla_kv_latent_projection"
        || package.tensor.quantization != "Q8_0"
        || package.tensor.gguf_shape != [COLUMNS, ROWS]
        || package.tensor.matrix_shape != [ROWS, COLUMNS]
        || package.tensor.output_shape != [ROWS]
        || package.tensor.packed_length != PACKED_LENGTH
        || package.activation_sha256 != ACTIVATION_SHA256
        || package.tensor_map_sha256
            != "ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223"
        || package.prior_evidence.m1_a_sha256
            != "aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805"
        || package.prior_evidence.m1_b_sha256
            != "9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770"
        || package.prior_evidence.m1_c_sha256
            != "343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e"
    {
        return Err(error(
            "m1d_package_contract",
            "projection package differs from the one admitted M1-D boundary",
        ));
    }
    for binding in [
        &package.boundary_contract,
        &package.decoder_contract,
        &package.scaffold_contract,
        &package.tier_b_contract,
    ] {
        let bytes = fs::read(root.join(&binding.path))
            .map_err(|e| error("m1d_contract_read", e.to_string()))?;
        require_hash("m1d_contract_hash", &bytes, &binding.sha256)?;
    }
    Ok(())
}

fn validate_oracle(oracle: &Oracle, package: &ProjectionPackage) -> Result<(), RunnerError> {
    if oracle.schema != "pulsarmlx.f017.m1d-projection-oracle"
        || oracle.boundary.contract_version != BOUNDARY_VERSION
        || oracle.boundary.matrix_rows != ROWS
        || oracle.boundary.matrix_columns != COLUMNS
        || oracle.boundary.packed_length != PACKED_LENGTH
        || oracle.boundary.output_shape != [ROWS]
        || oracle.activation.element_count != COLUMNS
        || oracle.activation.sha256 != ACTIVATION_SHA256
        || oracle.activation.bytes_hex.len() != COLUMNS * 8
        || oracle.oracle.scaffold_version != M1D_EXACT_SCAFFOLD_VERSION
        || oracle.oracle.decoder_contract_version != DECODER_VERSION
        || oracle.oracle.output_f32_hex.len() != ROWS * 8
        || oracle.oracle.output_sha256.len() != 64
        || oracle.tier_b.contract_version != M1D_TIER_B_CONTRACT_VERSION
        || oracle.tier_b.threshold_fit_to_observed_candidate
        || !oracle.oracle.generated_before_candidate
        || oracle.policies.signed_zero != "exact"
        || oracle.policies.nan_inf != "forbidden"
        || oracle.policies.deterministic_repeat_minimum != 10
        || oracle.policies.greedy_applicability != "not_applicable"
        || oracle.policies.success_classification != "numerically_qualified_greedy_not_applicable"
        || (package.package_kind == "checkpoint_free_fixture" && oracle.checkpoint_accessed)
        || (package.package_kind == "production_reviewed" && !oracle.checkpoint_accessed)
        || oracle.synthetic_matrix.packed_sha256 != package.tensor.packed_sha256
    {
        return Err(error(
            "m1d_oracle_contract",
            "oracle does not satisfy the frozen M1-D contract",
        ));
    }
    Ok(())
}

fn validate_manifest(
    manifest: &CheckpointManifest,
    package: &ProjectionPackage,
    mode: &RunnerMode,
) -> Result<(), RunnerError> {
    let expected_kind = if matches!(mode, RunnerMode::RealProjection { .. }) {
        CheckpointKind::Production
    } else {
        CheckpointKind::Fixture
    };
    if manifest.kind != expected_kind
        || manifest.checkpoint_set_sha256 != package.checkpoint_set_sha256
        || manifest.catalog_sha256 != package.catalog_sha256
    {
        return Err(error(
            "m1d_checkpoint_binding",
            "checkpoint manifest does not match the projection package",
        ));
    }
    Ok(())
}

fn read_exact_at(path: &Path, offset: u64, length: usize) -> Result<Vec<u8>, RunnerError> {
    use std::os::unix::fs::FileExt;
    let file = File::open(path).map_err(|e| error("m1d_shard_open", e.to_string()))?;
    let mut bytes = vec![0_u8; length];
    file.read_exact_at(&mut bytes, offset)
        .map_err(|e| error("m1d_short_read", e.to_string()))?;
    Ok(bytes)
}

fn decode_hex(value: &str) -> Result<Vec<u8>, RunnerError> {
    if !value.len().is_multiple_of(2) {
        return Err(error("m1d_hex", "hex length must be even"));
    }
    (0..value.len())
        .step_by(2)
        .map(|i| {
            u8::from_str_radix(&value[i..i + 2], 16).map_err(|_| error("m1d_hex", "invalid hex"))
        })
        .collect()
}

fn f32_from_bytes(bytes: &[u8]) -> Result<Vec<f32>, RunnerError> {
    if !bytes.len().is_multiple_of(4) {
        return Err(error("m1d_f32", "f32 bytes are not aligned"));
    }
    Ok(bytes
        .chunks_exact(4)
        .map(|b| f32::from_le_bytes(b.try_into().expect("four bytes")))
        .collect())
}

fn f32_bytes(values: &[f32]) -> Vec<u8> {
    values.iter().flat_map(|v| v.to_le_bytes()).collect()
}

fn require_hash(code: &'static str, bytes: &[u8], expected: &str) -> Result<(), RunnerError> {
    if expected.len() != 64 || sha256_bytes(bytes) != expected {
        return Err(error(code, "SHA-256 mismatch"));
    }
    Ok(())
}

fn adapter_error(message: String) -> RunnerError {
    RunnerError::new(FailureClass::InfrastructureEvidence, "m1d_backend", message)
}
fn error(code: &'static str, message: impl Into<String>) -> RunnerError {
    RunnerError::new(FailureClass::InfrastructureEvidence, code, message)
}
fn numerical(code: &'static str, message: impl Into<String>) -> RunnerError {
    RunnerError::new(FailureClass::NumericalBehavioral, code, message)
}
fn lifecycle(code: &'static str, message: impl Into<String>) -> RunnerError {
    RunnerError::new(FailureClass::LifecycleOwnership, code, message)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn package() -> (ProjectionPackage, PathBuf) {
        let root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../specs/017-rust-native-inference-runtime/fixtures");
        let bytes = fs::read(root.join("f017-m1d-projection-package-v1.json")).unwrap();
        (parse_json_no_duplicates(&bytes).unwrap(), root)
    }

    #[test]
    fn frozen_package_accepts_only_the_one_projection_contract() {
        let (value, root) = package();
        validate_package(
            &value,
            &root,
            &RunnerMode::FixtureProjection {
                package: PathBuf::new(),
            },
        )
        .unwrap();
    }

    #[test]
    fn wrong_activation_tensor_decoder_and_contract_fail_closed() {
        let (mut value, root) = package();
        value.activation_sha256 = "0".repeat(64);
        assert!(validate_package(
            &value,
            &root,
            &RunnerMode::FixtureProjection {
                package: PathBuf::new()
            }
        )
        .is_err());
        let (mut value, _) = package();
        value.tensor.name = "blk.0.attn_q_a.weight".to_owned();
        assert!(validate_package(
            &value,
            &root,
            &RunnerMode::FixtureProjection {
                package: PathBuf::new()
            }
        )
        .is_err());
        let (mut value, _) = package();
        value.tensor.matrix_shape = [575, 6144];
        assert!(validate_package(
            &value,
            &root,
            &RunnerMode::FixtureProjection {
                package: PathBuf::new()
            }
        )
        .is_err());
        let (mut value, _) = package();
        value.decoder_contract.version = "stale".to_owned();
        assert!(validate_package(
            &value,
            &root,
            &RunnerMode::FixtureProjection {
                package: PathBuf::new()
            }
        )
        .is_err());
        let (mut value, _) = package();
        value.tier_b_contract.version = "stale".to_owned();
        assert!(validate_package(
            &value,
            &root,
            &RunnerMode::FixtureProjection {
                package: PathBuf::new()
            }
        )
        .is_err());
        let (mut value, _) = package();
        value.prior_evidence.m1_c_sha256 = "0".repeat(64);
        assert!(validate_package(
            &value,
            &root,
            &RunnerMode::FixtureProjection {
                package: PathBuf::new()
            }
        )
        .is_err());
    }

    #[test]
    fn oracle_order_and_greedy_semantics_fail_closed() {
        let (package, root) = package();
        let bytes = fs::read(root.join(&package.oracle_path)).unwrap();
        let mut oracle: Oracle = parse_json_no_duplicates(&bytes).unwrap();
        oracle.oracle.generated_before_candidate = false;
        assert!(validate_oracle(&oracle, &package).is_err());
        let mut oracle: Oracle = parse_json_no_duplicates(&bytes).unwrap();
        oracle.policies.greedy_applicability = "applicable".to_owned();
        assert!(validate_oracle(&oracle, &package).is_err());
        let mut oracle: Oracle = parse_json_no_duplicates(&bytes).unwrap();
        oracle.oracle.output_f32_hex.clear();
        assert!(validate_oracle(&oracle, &package).is_err());
    }
}
