use crate::cli::Config;
use crate::evidence::Evidence;
#[cfg(all(target_os = "macos", pulsar_native_mlx))]
use crate::json::{parse_json_no_duplicates, sha256_bytes};
use crate::{FailureClass, RunnerError};
#[cfg(all(target_os = "macos", pulsar_native_mlx))]
use serde::Deserialize;
use std::path::Path;
#[cfg(all(target_os = "macos", pulsar_native_mlx))]
use std::{fs, time::Instant};

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
#[derive(Debug, Deserialize)]
struct OracleFixture {
    schema: String,
    generator: OracleGenerator,
    boundaries: OracleBoundaries,
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
#[derive(Debug, Deserialize)]
struct OracleGenerator {
    source_commit: String,
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
#[derive(Debug, Deserialize)]
struct OracleBoundaries {
    projection: ProjectionBoundary,
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
#[derive(Debug, Deserialize)]
struct ProjectionBoundary {
    classification: String,
    dimensions: [usize; 2],
    dtype: String,
    fixture_version: String,
    quantization: String,
    inputs: ProjectionInputs,
    expected: ProjectionExpected,
    numerical_contract: NumericalContract,
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
#[derive(Debug, Deserialize)]
struct ProjectionInputs {
    activation: Vec<f32>,
    activation_sha256: String,
    packed_hex: String,
    packed_sha256: String,
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
#[derive(Debug, Deserialize)]
struct ProjectionExpected {
    decoded_sha256: String,
    output: Vec<f32>,
    output_sha256: String,
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
#[derive(Debug, Deserialize)]
struct NumericalContract {
    kind: String,
    atol: f64,
    rtol: f64,
}

pub fn run_projection_fixture(
    manifest: &Path,
    config: &Config,
    evidence: &mut Evidence,
) -> Result<(), RunnerError> {
    run_projection_fixture_impl(manifest, config, evidence)
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn run_projection_fixture_impl(
    manifest: &Path,
    config: &Config,
    evidence: &mut Evidence,
) -> Result<(), RunnerError> {
    use stream::{MlxContext, MlxDevice, MlxStreamMode};

    let bytes = fs::read(manifest).map_err(|error| {
        fixture_error(
            FailureClass::InfrastructureEvidence,
            "fixture_read",
            format!("cannot read fixture manifest: {error}"),
        )
    })?;
    let envelope: serde_json::Value = parse_json_no_duplicates(&bytes).map_err(|error| {
        fixture_error(FailureClass::InfrastructureEvidence, "fixture_json", error)
    })?;
    if envelope["schema"] == "pulsarmlx.f017.r12-tiny-model-oracle" {
        return crate::tiny_model::run_tiny_model_fixture(manifest, config, evidence);
    }
    let oracle: OracleFixture = parse_json_no_duplicates(&bytes).map_err(|error| {
        fixture_error(FailureClass::InfrastructureEvidence, "fixture_json", error)
    })?;
    let projection = oracle.boundaries.projection;
    validate_contract(&oracle.schema, &projection)?;

    let packed = decode_hex(&projection.inputs.packed_hex)?;
    require_hash(
        "fixture_packed_hash",
        &packed,
        &projection.inputs.packed_sha256,
    )?;
    require_hash(
        "fixture_activation_hash",
        &f32_bytes(&projection.inputs.activation),
        &projection.inputs.activation_sha256,
    )?;

    let [rows, columns] = projection.dimensions;
    let mut decoded = vec![
        0.0_f32;
        rows.checked_mul(columns).ok_or_else(|| {
            fixture_error(
                FailureClass::InfrastructureEvidence,
                "fixture_shape_overflow",
                "projection dimensions overflow",
            )
        })?
    ];
    let decode_started = Instant::now();
    quant::decode_q8_0_matrix(&packed, rows, columns, &mut decoded).map_err(|error| {
        fixture_error(
            FailureClass::NumericalBehavioral,
            "fixture_decode",
            error.to_string(),
        )
    })?;
    evidence.execution.timings.insert(
        "decode_seconds".to_owned(),
        decode_started.elapsed().as_secs_f64(),
    );
    require_hash(
        "fixture_decoded_hash",
        &f32_bytes(&decoded),
        &projection.expected.decoded_sha256,
    )?;

    evidence.execution.numerical.oracle_generator_sha = Some(oracle.generator.source_commit);
    evidence.execution.numerical.scaffold_version =
        Some(crate::qualification::EXACT_SCAFFOLD_VERSION.to_owned());
    evidence.execution.numerical.frozen_contract_version =
        Some(crate::qualification::TIER_B_CONTRACT_VERSION.to_owned());
    match config.numerical_mode {
        Some(crate::cli::NumericalMode::ExactQualificationScaffold) => {
            let started = Instant::now();
            let mut output = vec![0.0_f32; rows];
            crate::qualification::exact_matvec_f32(
                &decoded,
                rows,
                columns,
                &projection.inputs.activation,
                &mut output,
            )
            .map_err(|error| {
                fixture_error(
                    FailureClass::NumericalBehavioral,
                    "fixture_exact_scaffold",
                    error.to_string(),
                )
            })?;
            evidence.execution.timings.insert(
                "qualification_scaffold_seconds".to_owned(),
                started.elapsed().as_secs_f64(),
            );
            require_exact_output(&output, &projection)?;
            evidence.execution.dispatch.qualification_scaffold = 1;
            evidence.execution.numerical_classification =
                Some(crate::numerical_classification::NumericalClassification::GoldenIdentical);
            evidence.execution.numerical.greedy_applicability =
                Some(crate::numerical_classification::GreedyApplicability::NotApplicable);
            evidence.execution.numerical.bit_mismatch_count = Some(0);
            evidence.execution.numerical.max_abs_error = Some(0.0);
            evidence.execution.numerical.relative_error = Some(0.0);
            evidence.execution.numerical.rmse = Some(0.0);
            evidence.execution.numerical.cosine_similarity = Some(1.0);
            evidence.execution.numerical.deterministic_repeat_count = Some(1);
            evidence.lifecycle.reconciled = true;
            evidence.execution.progress_state =
                format!("r5_projection_complete:{}", projection.fixture_version);
            return Ok(());
        }
        Some(crate::cli::NumericalMode::ProductionMlxTierB) => {}
        None => {
            return Err(fixture_error(
                FailureClass::InfrastructureEvidence,
                "fixture_numerical_mode",
                "fixture execution requires an explicit numerical mode",
            ))
        }
    }

    let stream_before = MlxContext::debug_stream_counters().map_err(adapter_error)?;
    if MlxContext::debug_context_active() {
        return Err(fixture_error(
            FailureClass::LifecycleOwnership,
            "fixture_context_nonzero",
            "fixture process did not begin with an unclaimed MLX singleton",
        ));
    }
    evidence.admission.singleton_initially_unclaimed = true;
    evidence.lifecycle.pre.default_cpu_stream_created = stream_before.default_cpu_created;
    evidence.lifecycle.pre.default_cpu_stream_freed = stream_before.default_cpu_freed;
    evidence.lifecycle.pre.default_gpu_stream_created = stream_before.default_gpu_created;
    evidence.lifecycle.pre.default_gpu_stream_freed = stream_before.default_gpu_freed;
    evidence.lifecycle.pre.owned_stream_created = stream_before.owned_created;
    evidence.lifecycle.pre.owned_stream_freed = stream_before.owned_freed;

    let adapter_started = Instant::now();
    let context = MlxContext::new(
        MlxDevice::Gpu,
        match config.stream_mode {
            crate::cli::StreamMode::DefaultGpu => MlxStreamMode::BorrowedDefault,
            crate::cli::StreamMode::OwnedDevice => MlxStreamMode::Owned,
        },
    )
    .map_err(adapter_error)?;
    let mut activation = projection.inputs.activation.clone();
    let matrix = context
        .import_f32_shaped(&mut decoded, &[rows, columns])
        .map_err(adapter_error)?;
    let vector = context
        .import_f32_shaped(&mut activation, &[columns])
        .map_err(adapter_error)?;
    evidence.execution.timings.insert(
        "backend_import_seconds".to_owned(),
        adapter_started.elapsed().as_secs_f64(),
    );

    let compute_started = Instant::now();
    let result = matrix.matvec(&vector).map_err(adapter_error)?;
    result.evaluate_sync().map_err(adapter_error)?;
    let mut output = vec![0.0_f32; rows];
    result.copy_f32(&mut output).map_err(adapter_error)?;
    evidence.execution.timings.insert(
        "backend_compute_sync_seconds".to_owned(),
        compute_started.elapsed().as_secs_f64(),
    );

    require_exact_output(&output, &projection)?;

    result.destroy().map_err(adapter_error)?;
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
        && ownership.derived_live == 0
        && ownership.callback_count == ownership.managed_created
        && stream_after.default_cpu_created - stream_before.default_cpu_created
            == stream_after.default_cpu_freed - stream_before.default_cpu_freed
        && stream_after.default_gpu_created - stream_before.default_gpu_created
            == stream_after.default_gpu_freed - stream_before.default_gpu_freed
        && stream_after.owned_created - stream_before.owned_created
            == stream_after.owned_freed - stream_before.owned_freed
        && !evidence.lifecycle.post.singleton_claimed;
    if !evidence.lifecycle.reconciled {
        return Err(fixture_error(
            FailureClass::LifecycleOwnership,
            "fixture_lifecycle",
            "projection fixture lifecycle did not reconcile",
        ));
    }

    evidence.execution.dispatch.native = 1;
    evidence.execution.numerical_classification =
        Some(crate::numerical_classification::NumericalClassification::GoldenIdentical);
    evidence.execution.numerical.greedy_applicability =
        Some(crate::numerical_classification::GreedyApplicability::NotApplicable);
    evidence.execution.numerical.production_backend_version =
        Some("mlx-c-matmul; mlx-native-0.31.2; mlx-c-0.6.0".to_owned());
    evidence.execution.numerical.bit_mismatch_count = Some(0);
    evidence.execution.numerical.max_abs_error = Some(0.0);
    evidence.execution.numerical.relative_error = Some(0.0);
    evidence.execution.numerical.rmse = Some(0.0);
    evidence.execution.numerical.cosine_similarity = Some(1.0);
    evidence.execution.numerical.deterministic_repeat_count = Some(1);
    evidence.execution.progress_state =
        format!("r5_projection_complete:{}", projection.fixture_version);
    Ok(())
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn require_exact_output(
    output: &[f32],
    projection: &ProjectionBoundary,
) -> Result<(), RunnerError> {
    if output
        .iter()
        .map(|value| value.to_bits())
        .collect::<Vec<_>>()
        != projection
            .expected
            .output
            .iter()
            .map(|value| value.to_bits())
            .collect::<Vec<_>>()
    {
        return Err(fixture_error(
            FailureClass::NumericalBehavioral,
            "fixture_output_bits",
            "selected numerical mode differs from independent exact-f32 oracle",
        ));
    }
    require_hash(
        "fixture_output_hash",
        &f32_bytes(output),
        &projection.expected.output_sha256,
    )
}

#[cfg(not(all(target_os = "macos", pulsar_native_mlx)))]
fn run_projection_fixture_impl(
    _manifest: &Path,
    _config: &Config,
    _evidence: &mut Evidence,
) -> Result<(), RunnerError> {
    Err(fixture_error(
        FailureClass::AdmissionEnvironment,
        "native_mlx_unavailable",
        "fixture mode requires the production native MLX adapter",
    ))
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn validate_contract(schema: &str, projection: &ProjectionBoundary) -> Result<(), RunnerError> {
    if schema != "glm52-f017-independent-oracle-v1"
        || projection.classification != "INDEPENDENT"
        || projection.dtype != "f32"
        || projection.quantization != "Q8_0"
        || projection.numerical_contract.kind != "exact_f32_bits"
        || projection.numerical_contract.atol != 0.0
        || projection.numerical_contract.rtol != 0.0
        || projection.dimensions[0] == 0
        || projection.dimensions[1] == 0
        || projection.inputs.activation.len() != projection.dimensions[1]
        || projection.expected.output.len() != projection.dimensions[0]
    {
        return Err(fixture_error(
            FailureClass::InfrastructureEvidence,
            "fixture_contract",
            "projection fixture differs from the frozen independent Q8_0 contract",
        ));
    }
    Ok(())
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn require_hash(code: &'static str, bytes: &[u8], expected: &str) -> Result<(), RunnerError> {
    if sha256_bytes(bytes) != expected {
        return Err(fixture_error(
            FailureClass::NumericalBehavioral,
            code,
            "fixture hash differs from the frozen independent oracle",
        ));
    }
    Ok(())
}

#[cfg(any(test, all(target_os = "macos", pulsar_native_mlx)))]
fn decode_hex(encoded: &str) -> Result<Vec<u8>, RunnerError> {
    if encoded.is_empty() || !encoded.len().is_multiple_of(2) {
        return Err(fixture_error(
            FailureClass::InfrastructureEvidence,
            "fixture_hex",
            "packed fixture hex must be non-empty and even length",
        ));
    }
    encoded
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let text = std::str::from_utf8(pair).map_err(|_| {
                fixture_error(
                    FailureClass::InfrastructureEvidence,
                    "fixture_hex",
                    "packed fixture hex must be ASCII",
                )
            })?;
            u8::from_str_radix(text, 16).map_err(|_| {
                fixture_error(
                    FailureClass::InfrastructureEvidence,
                    "fixture_hex",
                    "packed fixture contains a non-hex byte",
                )
            })
        })
        .collect()
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn f32_bytes(values: &[f32]) -> Vec<u8> {
    values
        .iter()
        .flat_map(|value| value.to_le_bytes())
        .collect()
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn adapter_error(message: String) -> RunnerError {
    fixture_error(FailureClass::LifecycleOwnership, "fixture_adapter", message)
}

fn fixture_error(
    class: FailureClass,
    code: &'static str,
    message: impl Into<String>,
) -> RunnerError {
    RunnerError::new(class, code, message)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn malformed_hex_is_rejected_without_partial_decode() {
        assert!(decode_hex("").is_err());
        assert!(decode_hex("0").is_err());
        assert!(decode_hex("gg").is_err());
        assert_eq!(decode_hex("00ff").unwrap(), [0, 255]);
    }
}
