use mlx_backend::{
    frozen_qwen_model_memory_budget, inspect_external_qwen_model, validate_device_smoke,
    CleanupOutcome, DeviceHello, DeviceProbe, ExternalModelInspection, ModelSliceRequest,
    ModelSliceResult, SyntheticMoeRequest, TensorFixtureRequest, WorkerClient, WorkerConfig,
    MODEL_SLICE_ID, PINNED_MLX_VERSION, QWEN_FILENAME, QWEN_FILE_BYTES, QWEN_REPOSITORY_ID,
    QWEN_REVISION, QWEN_SHA256,
};
use serde::Deserialize;
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::env;
use std::ffi::OsString;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::Command;

const BACKEND_ID: &str = "apple-mlx";
const GPU_DEVICE: &str = "gpu";
const FIXTURE_ID: &str = "nonsymmetric-f32-matmul-v1";
const FIXTURE_SET_ID: &str = "mlx-tensor-fixtures-v1";
const SYNTHETIC_MOE_FIXTURE_ID: &str = "synthetic-routed-moe-v1";
const MAX_MANIFEST_BYTES: usize = 1024 * 1024;
const MAX_REFERENCE_BYTES: usize = 256 * 1024;
const REFERENCE_RESULT_PATH: &str =
    "docs/validation/models/qwen3-30b-a3b-q8_0-reference-result.json";
const REFERENCE_REVISION: &str = "b06aa774c03dbbb624e726664b714a57d1f49815";
const PROMPT_SHA256: &str = "e5516410f283666d437d3cb5cbde9c121d8b12791cacbc2a0a81f2b9de2140bd";
const ACTIVATION_SHA256: &str = "3821796e8415d1214890e0e2fc97cddbb9ec773f2e941203dac41c1c7b36a92e";
const REAL_TENSOR_NAME: &str = "blk.0.ffn_gate_exps.weight";
const REAL_OUTPUT_NAME: &str = "blk0_ffn_gate_expert0_rows0_16_matvec";
const REAL_OUTPUT_COUNT: usize = 16;
const REAL_ATOL: f64 = 0.0005;
const REAL_RTOL: f64 = 0.0005;

fn main() {
    if let Err(error) = run(env::args_os().skip(1).collect()) {
        eprintln!("pulsar-mlx: {error}");
        std::process::exit(2);
    }
}

fn run(arguments: Vec<OsString>) -> Result<(), String> {
    match arguments.first().and_then(|value| value.to_str()) {
        Some("device-smoke") => run_device_smoke(parse_device_smoke(arguments)?),
        Some("validate-fixtures") => run_validate_fixtures(parse_validate_fixtures(arguments)?),
        Some("validate-synthetic-moe") => {
            run_validate_synthetic_moe(parse_validate_synthetic_moe(arguments)?)
        }
        Some("inspect-model") => {
            run_inspect_model(parse_external_model_command(arguments, "inspect-model")?)
        }
        Some("validate-model-slice") => run_validate_model_slice(parse_external_model_command(
            arguments,
            "validate-model-slice",
        )?),
        _ => Err(usage()),
    }
}

fn project_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn worker_config(project_root: &Path) -> Result<WorkerConfig, String> {
    let python = project_root.join(".venv/bin/python");
    if !python.is_file() {
        return Err(
            "the frozen project Python environment is unavailable; run `uv sync --frozen`"
                .to_owned(),
        );
    }

    Ok(WorkerConfig::new(
        python,
        vec![
            OsString::from("-u"),
            OsString::from("-m"),
            OsString::from("pulsar_mlx_worker"),
        ],
    )
    .with_expected_worker_version(env!("CARGO_PKG_VERSION"))
    .with_expected_mlx_version(PINNED_MLX_VERSION)
    .with_current_dir(project_root)
    .with_env("PYTHONPATH", "python"))
}

fn run_device_smoke(command: DeviceSmokeCommand) -> Result<(), String> {
    let project_root = project_root();
    let config = worker_config(&project_root)?;
    let mut client = WorkerClient::spawn(config).map_err(|error| error.to_string())?;
    let validation = execute_device_smoke(&mut client, &command);
    let cleanup = client.shutdown();
    let evidence = validation?;
    if cleanup.outcome() != CleanupOutcome::Graceful || cleanup.exit_code() != Some(0) {
        return Err(cleanup
            .error()
            .map(ToString::to_string)
            .unwrap_or_else(|| "MLX worker did not shut down cleanly".to_owned()));
    }

    write_evidence(&command.evidence, &evidence)?;
    println!("device-smoke: evaluated apple-mlx GPU probe passed");
    Ok(())
}

struct DeviceSmokeCommand {
    backend: String,
    device: String,
    evidence: PathBuf,
}

fn parse_device_smoke(arguments: Vec<OsString>) -> Result<DeviceSmokeCommand, String> {
    let values = arguments
        .into_iter()
        .map(|value| {
            value
                .into_string()
                .map_err(|_| "command arguments must be valid UTF-8".to_owned())
        })
        .collect::<Result<Vec<_>, _>>()?;
    if values.len() != 7 || values.first().map(String::as_str) != Some("device-smoke") {
        return Err(usage());
    }

    let mut backend = None;
    let mut device = None;
    let mut evidence = None;
    let mut index = 1;
    while index < values.len() {
        let key = &values[index];
        let value = values.get(index + 1).ok_or_else(usage)?.to_owned();
        match key.as_str() {
            "--backend" if backend.is_none() => backend = Some(value),
            "--device" if device.is_none() => device = Some(value),
            "--evidence" if evidence.is_none() => evidence = Some(PathBuf::from(value)),
            _ => return Err(usage()),
        }
        index += 2;
    }

    let backend = backend.ok_or_else(usage)?;
    let device = device.ok_or_else(usage)?;
    let evidence = evidence.ok_or_else(usage)?;
    if backend != BACKEND_ID {
        return Err("device-smoke requires explicit `--backend apple-mlx`".to_owned());
    }
    if device != GPU_DEVICE {
        return Err(
            "device-smoke requires explicit `--device gpu`; fallback is forbidden".to_owned(),
        );
    }
    if evidence.as_os_str().is_empty() {
        return Err("the evidence path must not be empty".to_owned());
    }
    Ok(DeviceSmokeCommand {
        backend,
        device,
        evidence,
    })
}

fn usage() -> String {
    "usage: pulsar-mlx device-smoke --backend apple-mlx --device gpu --evidence PATH\n       pulsar-mlx validate-fixtures --manifest fixtures/mlx/manifest.json --evidence PATH\n       pulsar-mlx validate-synthetic-moe --fixture fixtures/mlx/routed-moe-v1.json --evidence PATH\n       pulsar-mlx inspect-model --model ABSOLUTE_EXTERNAL_GGUF --evidence PATH\n       pulsar-mlx validate-model-slice --model ABSOLUTE_EXTERNAL_GGUF --evidence PATH".to_owned()
}

struct ExternalModelCommand {
    model: PathBuf,
    evidence: PathBuf,
}

fn parse_external_model_command(
    arguments: Vec<OsString>,
    command_name: &str,
) -> Result<ExternalModelCommand, String> {
    let values = arguments
        .into_iter()
        .map(|value| {
            value
                .into_string()
                .map_err(|_| "command arguments must be valid UTF-8".to_owned())
        })
        .collect::<Result<Vec<_>, _>>()?;
    if values.len() != 5 || values.first().map(String::as_str) != Some(command_name) {
        return Err(usage());
    }
    let mut model = None;
    let mut evidence = None;
    let mut index = 1;
    while index < values.len() {
        let key = &values[index];
        let value = values.get(index + 1).ok_or_else(usage)?.to_owned();
        match key.as_str() {
            "--model" if model.is_none() => model = Some(PathBuf::from(value)),
            "--evidence" if evidence.is_none() => evidence = Some(PathBuf::from(value)),
            _ => return Err(usage()),
        }
        index += 2;
    }
    let model = model.ok_or_else(usage)?;
    let evidence = evidence.ok_or_else(usage)?;
    if !model.is_absolute() {
        return Err("the external model path must be absolute".to_owned());
    }
    if model.file_name().and_then(|name| name.to_str()) != Some(QWEN_FILENAME) {
        return Err("the external model must use the exact admitted filename".to_owned());
    }
    if evidence.as_os_str().is_empty() {
        return Err("the evidence path must not be empty".to_owned());
    }
    Ok(ExternalModelCommand { model, evidence })
}

fn inspect_admitted_model(
    project_root: &Path,
    model_path: &Path,
) -> Result<(ExternalModelInspection, String), String> {
    let available_disk_bytes = observe_available_disk_bytes(model_path)?;
    let host_unified_memory_bytes = observe_host_unified_memory_bytes()?;
    let pressure = observe_system_pressure()?;
    let budget = frozen_qwen_model_memory_budget(available_disk_bytes, host_unified_memory_bytes);
    let inspection = inspect_external_qwen_model(model_path, project_root, budget)
        .map_err(|error| error.to_string())?;
    Ok((inspection, pressure))
}

fn run_inspect_model(command: ExternalModelCommand) -> Result<(), String> {
    let project_root = project_root();
    ensure_distinct_model_and_evidence(&command.model, &command.evidence)?;
    let (inspection, pressure) = inspect_admitted_model(&project_root, &command.model)?;
    let descriptor = inspection.admission_descriptor();
    let tensor = descriptor
        .tensors
        .first()
        .ok_or_else(|| "the admitted model tensor inventory is unexpectedly empty".to_owned())?;
    let evidence = json!({
        "schema_version": 1,
        "validation": "qwen3-q8_0-external-model-inspection",
        "status": "compatible_for_bounded_slice_not_executed",
        "recorded_at_utc": utc_now()?,
        "artifact": {
            "repository_id": descriptor.identity.repository_id,
            "revision": descriptor.identity.revision,
            "filename": descriptor.identity.filename,
            "license_spdx": descriptor.identity.license_spdx,
            "size_bytes": descriptor.identity.actual_size_bytes,
            "sha256": descriptor.identity.actual_sha256,
            "location": format!("<external-model>/{QWEN_FILENAME}"),
            "stored_outside_repository": descriptor.identity.stored_outside_repository,
            "automatic_download": false,
        },
        "gguf": {
            "version": inspection.gguf_version(),
            "endianness": "little",
            "data_offset": inspection.data_offset(),
            "tensor_count": inspection.tensor_count(),
            "tensor_type_counts": {
                "F32": inspection.f32_tensor_count(),
                "Q8_0": inspection.q8_0_tensor_count(),
            },
            "metadata": {
                "general.architecture": {"type": descriptor.metadata.architecture_value_type, "value": descriptor.metadata.architecture},
                "qwen3moe.embedding_length": {"type": descriptor.metadata.embedding_length_value_type, "value": descriptor.metadata.embedding_length},
                "qwen3moe.expert_feed_forward_length": {"type": descriptor.metadata.expert_feed_forward_length_value_type, "value": descriptor.metadata.expert_feed_forward_length},
                "qwen3moe.expert_count": {"type": descriptor.metadata.expert_count_value_type, "value": descriptor.metadata.expert_count},
            },
        },
        "admitted_tensor": {
            "role": tensor.role,
            "name": tensor.name,
            "occurrences": tensor.occurrences,
            "quantization": tensor.quantization,
            "gguf_dimensions_fastest_axis_first": tensor.gguf_dimensions_fastest_axis_first,
            "reader_encoded_shape": tensor.reader_encoded_shape,
            "logical_elements": tensor.logical_elements,
            "encoded_bytes": tensor.encoded_bytes,
            "absolute_data_offset": tensor.absolute_data_offset,
            "encoded_slice_bytes": inspection.admitted().encoded_slice_bytes(),
            "encoded_slice_sha256": inspection.encoded_slice_sha256(),
        },
        "fresh_admission_observations": {
            "available_disk_bytes": descriptor.memory_budget.available_disk_bytes,
            "required_disk_bytes": descriptor.memory_budget.required_disk_bytes,
            "host_unified_memory_bytes": descriptor.memory_budget.host_unified_memory_bytes,
            "required_host_bytes": descriptor.memory_budget.required_host_bytes,
            "system_pressure": pressure,
        },
        "execution": {
            "performed": false,
            "trusted_reference_performed_by_this_command": false,
            "mlx_performed": false,
        },
        "warnings": [
            "The inherited Rust GGUF map does not independently retain duplicate metadata keys; exact full-file SHA-256 plus the pinned T055 gguf-py uniqueness check closes that artifact-specific boundary.",
            "Linux and CUDA execution are not established by this command."
        ],
        "exclusions": [
            "No tensor was dequantized or executed.",
            "No tokenizer, routing, full layer, logits, tokens, generation, serving, or benchmark was exercised."
        ]
    });
    inspection
        .verify_unchanged()
        .map_err(|error| error.to_string())?;
    ensure_no_private_paths(&evidence)?;
    write_evidence(&command.evidence, &evidence)?;
    println!("inspect-model: immutable external Qwen slice inventory admitted");
    Ok(())
}

struct FrozenReferenceResult {
    encoded_slice_sha256: String,
    decoded_slice_sha256: String,
    output_sha256: String,
    values: Vec<f64>,
}

fn load_frozen_reference(project_root: &Path) -> Result<FrozenReferenceResult, String> {
    let path = project_root.join(REFERENCE_RESULT_PATH);
    let bytes = fs::read(path).map_err(|_| {
        "the committed trusted-reference result is unavailable; run T061 first".to_owned()
    })?;
    if bytes.is_empty() || bytes.len() > MAX_REFERENCE_BYTES {
        return Err("the trusted-reference result violates its byte bound".to_owned());
    }
    let record: Value = serde_json::from_slice(&bytes)
        .map_err(|_| "the trusted-reference result is not valid bounded JSON".to_owned())?;
    ensure_no_private_paths(&record)?;
    let exact_string = |pointer: &str, expected: &str| -> Result<(), String> {
        if record.pointer(pointer).and_then(Value::as_str) != Some(expected) {
            return Err(format!(
                "the trusted-reference field {pointer} differs from its frozen identity"
            ));
        }
        Ok(())
    };
    if record.get("schema_version").and_then(Value::as_u64) != Some(1) {
        return Err("the trusted-reference schema version is not supported".to_owned());
    }
    exact_string("/record_type", "trusted_reference_result")?;
    exact_string("/status", "passed")?;
    exact_string("/trusted_reference/immutable_revision", REFERENCE_REVISION)?;
    exact_string("/artifact/repository_id", QWEN_REPOSITORY_ID)?;
    exact_string("/artifact/revision", QWEN_REVISION)?;
    exact_string("/artifact/filename", QWEN_FILENAME)?;
    exact_string("/artifact/sha256", QWEN_SHA256)?;
    if record
        .pointer("/artifact/size_bytes")
        .and_then(Value::as_u64)
        != Some(QWEN_FILE_BYTES)
    {
        return Err("the trusted-reference artifact size differs".to_owned());
    }
    exact_string("/input/prompt_utf8_sha256", PROMPT_SHA256)?;
    exact_string("/input/activation_sha256", ACTIVATION_SHA256)?;
    exact_string("/tensor/name", REAL_TENSOR_NAME)?;
    exact_string("/tensor/quantization", "Q8_0")?;
    exact_string("/output/name", REAL_OUTPUT_NAME)?;
    exact_string("/output/dtype", "float32")?;
    exact_string("/comparison_policy/mode", "absolute_plus_relative")?;
    exact_string("/comparison_policy/non_finite_policy", "reject")?;
    if record
        .pointer("/comparison_policy/absolute_tolerance")
        .and_then(Value::as_f64)
        != Some(REAL_ATOL)
        || record
            .pointer("/comparison_policy/relative_tolerance")
            .and_then(Value::as_f64)
            != Some(REAL_RTOL)
        || record
            .pointer("/self_check/passed")
            .and_then(Value::as_bool)
            != Some(true)
    {
        return Err("the trusted-reference comparison or self-check policy differs".to_owned());
    }
    let output_shape = record
        .pointer("/output/shape")
        .and_then(Value::as_array)
        .ok_or_else(|| "the trusted-reference output shape is missing".to_owned())?;
    if output_shape.as_slice() != [json!(REAL_OUTPUT_COUNT)] {
        return Err("the trusted-reference output shape differs".to_owned());
    }
    let values = record
        .pointer("/output/values")
        .and_then(Value::as_array)
        .ok_or_else(|| "the trusted-reference output values are missing".to_owned())?
        .iter()
        .map(|value| {
            let number = value
                .as_f64()
                .filter(|number| number.is_finite())
                .ok_or_else(|| {
                    "the trusted-reference output contains a non-finite value".to_owned()
                })?;
            let canonical = number as f32;
            if !canonical.is_finite() {
                return Err("the trusted-reference output is outside float32 range".to_owned());
            }
            Ok(f64::from(canonical))
        })
        .collect::<Result<Vec<_>, _>>()?;
    if values.len() != REAL_OUTPUT_COUNT {
        return Err("the trusted-reference output cardinality differs".to_owned());
    }
    let encoded_slice_sha256 = reference_sha256(&record, "/tensor/encoded_slice_sha256")?;
    let decoded_slice_sha256 = reference_sha256(&record, "/tensor/decoded_slice_sha256")?;
    let output_sha256 = reference_sha256(&record, "/output/sha256")?;
    if output_f32_sha256(&values) != output_sha256 {
        return Err("the trusted-reference output checksum does not match its values".to_owned());
    }
    Ok(FrozenReferenceResult {
        encoded_slice_sha256,
        decoded_slice_sha256,
        output_sha256,
        values,
    })
}

fn reference_sha256(record: &Value, pointer: &str) -> Result<String, String> {
    let value = record
        .pointer(pointer)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("the trusted-reference field {pointer} is missing"))?;
    if value.len() != 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(format!(
            "the trusted-reference field {pointer} is not lowercase SHA-256"
        ));
    }
    Ok(value.to_owned())
}

struct AdditiveComparison {
    passed: bool,
    mismatch_count: usize,
    max_absolute_error: f64,
    max_relative_error: f64,
    first_mismatch: Option<Value>,
}

fn compare_model_slice(reference: &[f64], candidate: &[f64]) -> AdditiveComparison {
    let mut mismatch_count = 0;
    let mut max_absolute_error = 0.0_f64;
    let mut max_relative_error = 0.0_f64;
    let mut first_mismatch = None;
    for (index, (expected, actual)) in reference.iter().zip(candidate).enumerate() {
        let absolute_error = (actual - expected).abs();
        let relative_error = absolute_error / expected.abs().max(f64::from(f32::MIN_POSITIVE));
        max_absolute_error = max_absolute_error.max(absolute_error);
        max_relative_error = max_relative_error.max(relative_error);
        let admitted_error = REAL_ATOL + REAL_RTOL * expected.abs();
        if absolute_error > admitted_error {
            mismatch_count += 1;
            if first_mismatch.is_none() {
                first_mismatch = Some(json!({
                    "index": index,
                    "reference": expected,
                    "candidate": actual,
                    "absolute_error": absolute_error,
                    "admitted_error": admitted_error,
                }));
            }
        }
    }
    AdditiveComparison {
        passed: reference.len() == candidate.len() && mismatch_count == 0,
        mismatch_count,
        max_absolute_error,
        max_relative_error,
        first_mismatch,
    }
}

fn run_validate_model_slice(command: ExternalModelCommand) -> Result<(), String> {
    let project_root = project_root();
    ensure_distinct_model_and_evidence(&command.model, &command.evidence)?;
    let reference = load_frozen_reference(&project_root)?;
    let source_commit = clean_source_commit(&project_root)?;
    let (inspection, pressure) = inspect_admitted_model(&project_root, &command.model)?;
    if pressure != "normal" {
        return Err("real-model execution requires normal system memory pressure".to_owned());
    }
    if inspection.encoded_slice_sha256() != reference.encoded_slice_sha256 {
        return Err(
            "the trusted reference and admitted file use different encoded slice bytes".to_owned(),
        );
    }

    let config = worker_config(&project_root)?.with_model_file(
        inspection
            .try_clone_file()
            .map_err(|error| error.to_string())?,
    );
    let mut client = WorkerClient::spawn(config).map_err(|error| error.to_string())?;
    let hello = client.hello().clone();
    let validation = execute_real_model_slice(&mut client, inspection.encoded_slice_sha256());
    let cleanup = client.shutdown();
    let result = validation?;
    if cleanup.outcome() != CleanupOutcome::Graceful || cleanup.exit_code() != Some(0) {
        return Err(cleanup
            .error()
            .map(ToString::to_string)
            .unwrap_or_else(|| "MLX worker did not shut down cleanly".to_owned()));
    }
    inspection
        .verify_unchanged()
        .map_err(|error| error.to_string())?;

    let numeric = compare_model_slice(&reference.values, result.actual());
    let identities_passed = result.encoded_slice_sha256() == reference.encoded_slice_sha256
        && result.decoded_slice_sha256() == reference.decoded_slice_sha256
        && result.activation_sha256() == ACTIVATION_SHA256;
    let passed = numeric.passed && identities_passed;
    let memory = serde_json::to_value(result.memory_gauges())
        .map_err(|_| "model-slice memory evidence could not be serialized".to_owned())?;
    let evidence = json!({
        "schema_version": 1,
        "validation": "qwen3-30b-a3b-q8_0-bounded-mlx-slice",
        "status": if passed { "passed" } else { "failed" },
        "recorded_at_utc": utc_now()?,
        "source_commit": source_commit,
        "source_worktree_clean_before_execution": true,
        "command": format!("cargo run -p mlx-backend --bin pulsar-mlx -- validate-model-slice --model <external-model>/{QWEN_FILENAME} --evidence docs/validation/qwen3-30b-a3b-q8_0-slice.json"),
        "artifact": {
            "repository_id": QWEN_REPOSITORY_ID,
            "revision": QWEN_REVISION,
            "filename": QWEN_FILENAME,
            "size_bytes": QWEN_FILE_BYTES,
            "sha256": QWEN_SHA256,
            "location": format!("<external-model>/{QWEN_FILENAME}"),
            "identity_rechecked_after_execution": true,
        },
        "runtime": {
            "protocol": hello.protocol(),
            "worker_version": hello.worker_version(),
            "python_version": hello.python_version(),
            "python_arch": hello.python_arch(),
            "mlx_version": hello.mlx_version(),
            "macos_version": hello.macos_version(),
            "metal_available": hello.metal_available(),
            "gpu_count": hello.gpu_count(),
            "selected_device": result.selected_device(),
            "fallback_used": result.fallback_used(),
            "evaluated": result.evaluated(),
            "synchronized": result.synchronized(),
        },
        "slice": {
            "slice_id": result.slice_id(),
            "operation": result.operation(),
            "tensor_name": result.tensor_name(),
            "output_name": result.output_name(),
            "execution_depth": "layer_0_expert_0_gate_rows_0_16_matvec",
            "output_shape": result.output_shape(),
            "output_dtype": result.output_dtype(),
            "encoded_slice_sha256": result.encoded_slice_sha256(),
            "decoded_slice_sha256": result.decoded_slice_sha256(),
            "activation_sha256": result.activation_sha256(),
            "output_sha256": result.output_sha256(),
            "actual": result.actual(),
        },
        "reference": {
            "record": REFERENCE_RESULT_PATH,
            "immutable_revision": REFERENCE_REVISION,
            "output_sha256": reference.output_sha256,
            "values": reference.values,
        },
        "comparison": {
            "mode": "absolute_plus_relative",
            "pass_expression": "abs(candidate-reference) <= absolute_tolerance + relative_tolerance * abs(reference)",
            "absolute_tolerance": REAL_ATOL,
            "relative_tolerance": REAL_RTOL,
            "non_finite_policy": "reject",
            "compared_count": REAL_OUTPUT_COUNT,
            "mismatch_count": numeric.mismatch_count,
            "max_absolute_error": numeric.max_absolute_error,
            "max_relative_error": numeric.max_relative_error,
            "first_mismatch": numeric.first_mismatch,
            "input_identities_passed": identities_passed,
            "passed": passed,
        },
        "memory_gauges": memory,
        "fresh_admission_observations": {
            "available_disk_bytes": inspection.admission_descriptor().memory_budget.available_disk_bytes,
            "required_disk_bytes": inspection.admission_descriptor().memory_budget.required_disk_bytes,
            "host_unified_memory_bytes": inspection.admission_descriptor().memory_budget.host_unified_memory_bytes,
            "required_host_bytes": inspection.admission_descriptor().memory_budget.required_host_bytes,
            "system_pressure": pressure,
        },
        "warnings": [
            "Linux and CUDA execution are not established by this Apple-only command."
        ],
        "exclusions": [
            "The prompt is consumed by a transparent SHA-256 probe adapter, not Qwen tokenization or embedding.",
            "No router, full expert, full layer, attention, logits, tokens, generation, serving, or benchmark was exercised.",
            "This bounded intermediate does not establish giant-model inference."
        ]
    });
    ensure_no_private_paths(&evidence)?;
    write_evidence(&command.evidence, &evidence)?;
    if !passed {
        return Err("validate-model-slice: bounded real-model comparison failed".to_owned());
    }
    println!("validate-model-slice: bounded real-model MLX intermediate passed");
    Ok(())
}

fn execute_real_model_slice(
    client: &mut WorkerClient,
    encoded_slice_sha256: &str,
) -> Result<ModelSliceResult, String> {
    let health = client.health().map_err(|error| error.to_string())?;
    if !health.ready() {
        return Err("the negotiated MLX worker is not ready".to_owned());
    }
    let request =
        ModelSliceRequest::new(MODEL_SLICE_ID, GPU_DEVICE).map_err(|error| error.to_string())?;
    client
        .run_model_slice(&request, encoded_slice_sha256)
        .map_err(|error| error.to_string())
}

fn observe_available_disk_bytes(path: &Path) -> Result<u64, String> {
    let output = Command::new("/bin/df")
        .args(["-Pk"])
        .arg(path)
        .output()
        .map_err(|_| "available disk could not be observed".to_owned())?;
    if !output.status.success() {
        return Err("available disk observation failed".to_owned());
    }
    let stdout = String::from_utf8(output.stdout)
        .map_err(|_| "available disk observation was not UTF-8".to_owned())?;
    let fields = stdout
        .lines()
        .rfind(|line| !line.trim().is_empty())
        .ok_or_else(|| "available disk observation was empty".to_owned())?
        .split_whitespace()
        .collect::<Vec<_>>();
    let available_kib = fields
        .get(3)
        .ok_or_else(|| "available disk observation was malformed".to_owned())?
        .parse::<u64>()
        .map_err(|_| "available disk observation was malformed".to_owned())?;
    available_kib
        .checked_mul(1024)
        .ok_or_else(|| "available disk byte count overflowed".to_owned())
}

fn observe_host_unified_memory_bytes() -> Result<u64, String> {
    let output = Command::new("/usr/sbin/sysctl")
        .args(["-n", "hw.memsize"])
        .output()
        .map_err(|_| "host unified memory could not be observed".to_owned())?;
    if !output.status.success() {
        return Err("host unified-memory observation failed".to_owned());
    }
    String::from_utf8(output.stdout)
        .map_err(|_| "host unified-memory observation was not UTF-8".to_owned())?
        .trim()
        .parse::<u64>()
        .map_err(|_| "host unified-memory observation was malformed".to_owned())
}

fn observe_system_pressure() -> Result<String, String> {
    let output = Command::new("/usr/sbin/sysctl")
        .args(["-n", "kern.memorystatus_vm_pressure_level"])
        .output()
        .map_err(|_| "system memory pressure could not be observed".to_owned())?;
    if !output.status.success() {
        return Err("system memory-pressure observation failed".to_owned());
    }
    let level = String::from_utf8(output.stdout)
        .map_err(|_| "system memory-pressure observation was not UTF-8".to_owned())?
        .trim()
        .parse::<u32>()
        .map_err(|_| "system memory-pressure observation was malformed".to_owned())?;
    match level {
        1 => Ok("normal".to_owned()),
        2 => Ok("warning".to_owned()),
        4 => Ok("critical".to_owned()),
        _ => Err("system memory-pressure level is unknown".to_owned()),
    }
}

fn utc_now() -> Result<String, String> {
    let output = Command::new("/bin/date")
        .args(["-u", "+%Y-%m-%dT%H:%M:%SZ"])
        .output()
        .map_err(|_| "UTC timestamp could not be observed".to_owned())?;
    if !output.status.success() {
        return Err("UTC timestamp observation failed".to_owned());
    }
    let value = String::from_utf8(output.stdout)
        .map_err(|_| "UTC timestamp observation was not UTF-8".to_owned())?;
    let value = value.trim();
    if value.len() != 20 || !value.ends_with('Z') {
        return Err("UTC timestamp observation was malformed".to_owned());
    }
    Ok(value.to_owned())
}

fn clean_source_commit(project_root: &Path) -> Result<String, String> {
    let status = Command::new("git")
        .args(["status", "--porcelain"])
        .current_dir(project_root)
        .output()
        .map_err(|_| "source cleanliness could not be observed".to_owned())?;
    if !status.status.success() || !status.stdout.is_empty() {
        return Err("validate-model-slice requires a clean source worktree".to_owned());
    }
    let revision = Command::new("git")
        .args(["rev-parse", "HEAD"])
        .current_dir(project_root)
        .output()
        .map_err(|_| "source commit could not be observed".to_owned())?;
    if !revision.status.success() {
        return Err("source commit observation failed".to_owned());
    }
    let revision = String::from_utf8(revision.stdout)
        .map_err(|_| "source commit observation was not UTF-8".to_owned())?;
    let revision = revision.trim();
    if revision.len() != 40
        || !revision
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err("source commit observation was malformed".to_owned());
    }
    Ok(revision.to_owned())
}

fn output_f32_sha256(values: &[f64]) -> String {
    let mut bytes = Vec::with_capacity(values.len() * 4);
    for value in values {
        bytes.extend_from_slice(&(*value as f32).to_le_bytes());
    }
    format!("{:x}", Sha256::digest(bytes))
}

fn ensure_no_private_paths(value: &Value) -> Result<(), String> {
    match value {
        Value::String(string)
            if string.starts_with('/')
                || string.starts_with("~/")
                || string.contains("/Users/")
                || string.contains("/home/")
                || string.contains("\\Users\\") =>
        {
            Err("evidence contains a private absolute path".to_owned())
        }
        Value::Array(values) => {
            for value in values {
                ensure_no_private_paths(value)?;
            }
            Ok(())
        }
        Value::Object(values) => {
            for value in values.values() {
                ensure_no_private_paths(value)?;
            }
            Ok(())
        }
        _ => Ok(()),
    }
}

fn ensure_distinct_model_and_evidence(model: &Path, evidence: &Path) -> Result<(), String> {
    let canonical_model =
        fs::canonicalize(model).map_err(|_| "the external model file is unavailable".to_owned())?;
    let canonical_evidence = if evidence.exists() {
        fs::canonicalize(evidence)
            .map_err(|_| "the evidence path could not be resolved".to_owned())?
    } else {
        let parent = evidence
            .parent()
            .filter(|path| !path.as_os_str().is_empty())
            .unwrap_or_else(|| Path::new("."));
        let filename = evidence
            .file_name()
            .ok_or_else(|| "the evidence path must name a file".to_owned())?;
        fs::canonicalize(parent)
            .map_err(|_| "the evidence parent directory does not exist".to_owned())?
            .join(filename)
    };
    if canonical_evidence == canonical_model
        || existing_files_share_identity(&canonical_model, evidence)?
    {
        return Err("the evidence path must not alias the external model".to_owned());
    }
    Ok(())
}

#[cfg(unix)]
fn existing_files_share_identity(left: &Path, right: &Path) -> Result<bool, String> {
    use std::os::unix::fs::MetadataExt;

    if !right.exists() {
        return Ok(false);
    }
    let left =
        fs::metadata(left).map_err(|_| "the external model metadata is unavailable".to_owned())?;
    let right =
        fs::metadata(right).map_err(|_| "the evidence metadata is unavailable".to_owned())?;
    Ok(left.dev() == right.dev() && left.ino() == right.ino())
}

#[cfg(not(unix))]
fn existing_files_share_identity(_left: &Path, _right: &Path) -> Result<bool, String> {
    Ok(false)
}

struct ValidateFixturesCommand {
    manifest: PathBuf,
    evidence: PathBuf,
}

fn parse_validate_fixtures(arguments: Vec<OsString>) -> Result<ValidateFixturesCommand, String> {
    let values = arguments
        .into_iter()
        .map(|value| {
            value
                .into_string()
                .map_err(|_| "command arguments must be valid UTF-8".to_owned())
        })
        .collect::<Result<Vec<_>, _>>()?;
    if values.len() != 5 || values.first().map(String::as_str) != Some("validate-fixtures") {
        return Err(usage());
    }

    let mut manifest = None;
    let mut evidence = None;
    let mut index = 1;
    while index < values.len() {
        let key = &values[index];
        let value = values.get(index + 1).ok_or_else(usage)?.to_owned();
        match key.as_str() {
            "--manifest" if manifest.is_none() => manifest = Some(PathBuf::from(value)),
            "--evidence" if evidence.is_none() => evidence = Some(PathBuf::from(value)),
            _ => return Err(usage()),
        }
        index += 2;
    }
    Ok(ValidateFixturesCommand {
        manifest: manifest.ok_or_else(usage)?,
        evidence: evidence.ok_or_else(usage)?,
    })
}

struct ValidateSyntheticMoeCommand {
    fixture: PathBuf,
    evidence: PathBuf,
}

fn parse_validate_synthetic_moe(
    arguments: Vec<OsString>,
) -> Result<ValidateSyntheticMoeCommand, String> {
    let values = arguments
        .into_iter()
        .map(|value| {
            value
                .into_string()
                .map_err(|_| "command arguments must be valid UTF-8".to_owned())
        })
        .collect::<Result<Vec<_>, _>>()?;
    if values.len() != 5 || values.first().map(String::as_str) != Some("validate-synthetic-moe") {
        return Err(usage());
    }

    let mut fixture = None;
    let mut evidence = None;
    let mut index = 1;
    while index < values.len() {
        let key = &values[index];
        let value = values.get(index + 1).ok_or_else(usage)?.to_owned();
        match key.as_str() {
            "--fixture" if fixture.is_none() => fixture = Some(PathBuf::from(value)),
            "--evidence" if evidence.is_none() => evidence = Some(PathBuf::from(value)),
            _ => return Err(usage()),
        }
        index += 2;
    }
    Ok(ValidateSyntheticMoeCommand {
        fixture: fixture.ok_or_else(usage)?,
        evidence: evidence.ok_or_else(usage)?,
    })
}

#[derive(Debug, Deserialize)]
struct FixtureManifestIndex {
    schema_version: u32,
    fixture_set_id: String,
    backend_id: String,
    requested_device: String,
    allow_fallback: bool,
    maximum_fixture_elements: u64,
    operations: Vec<FixtureCaseIndex>,
}

#[derive(Debug, Deserialize)]
struct FixtureCaseIndex {
    case_id: String,
    operation: String,
}

fn load_fixture_index(
    project_root: &Path,
    requested_path: &Path,
) -> Result<FixtureManifestIndex, String> {
    let expected = fs::canonicalize(project_root.join("fixtures/mlx/manifest.json"))
        .map_err(|_| "the committed fixture manifest is unavailable")?;
    let requested = fs::canonicalize(requested_path)
        .map_err(|_| "the requested fixture manifest is unavailable")?;
    if requested != expected {
        return Err("validate-fixtures accepts only the committed fixture manifest".to_owned());
    }
    let bytes =
        fs::read(&requested).map_err(|_| "the committed fixture manifest could not be read")?;
    if bytes.is_empty() || bytes.len() > MAX_MANIFEST_BYTES {
        return Err("the fixture manifest violates its byte bound".to_owned());
    }
    let manifest: FixtureManifestIndex = serde_json::from_slice(&bytes)
        .map_err(|_| "the fixture manifest is not valid bounded JSON")?;
    let expected_operations = [
        ("elementwise-fma-nonsymmetric-f32-v1", "elementwise_fma"),
        ("matmul-nonsymmetric-f32-v1", "matmul"),
        ("embedding-gather-order-f32-v1", "embedding_gather"),
        ("rms-norm-weighted-f32-v1", "rms_norm"),
        ("residual-add-nonsymmetric-f32-v1", "residual_add"),
        ("router-topk-tie-f32-v1", "router_topk_softmax"),
        ("q8-0-two-block-row-v1", "q8_0_decode_dot"),
    ];
    if manifest.schema_version != 1
        || manifest.fixture_set_id != FIXTURE_SET_ID
        || manifest.backend_id != BACKEND_ID
        || manifest.requested_device != GPU_DEVICE
        || manifest.allow_fallback
        || manifest.maximum_fixture_elements != 4096
        || manifest.operations.len() != expected_operations.len()
        || manifest
            .operations
            .iter()
            .map(|case| (case.case_id.as_str(), case.operation.as_str()))
            .ne(expected_operations)
    {
        return Err(
            "the fixture manifest identity or ordered case inventory is not admitted".to_owned(),
        );
    }
    let unique = manifest
        .operations
        .iter()
        .map(|case| case.case_id.as_str())
        .collect::<BTreeSet<_>>();
    if unique.len() != manifest.operations.len() {
        return Err("the fixture manifest contains duplicate case identities".to_owned());
    }
    Ok(manifest)
}

fn run_validate_fixtures(command: ValidateFixturesCommand) -> Result<(), String> {
    let project_root = project_root();
    let manifest = load_fixture_index(&project_root, &command.manifest)?;
    let config = worker_config(&project_root)?;
    let mut client = WorkerClient::spawn(config).map_err(|error| error.to_string())?;
    let validation = execute_fixture_suite(&mut client, &manifest);
    let cleanup = client.shutdown();
    let evidence = validation?;
    if cleanup.outcome() != CleanupOutcome::Graceful || cleanup.exit_code() != Some(0) {
        return Err(cleanup
            .error()
            .map(ToString::to_string)
            .unwrap_or_else(|| "MLX worker did not shut down cleanly".to_owned()));
    }
    write_evidence(&command.evidence, &evidence)?;
    println!("validate-fixtures: 7 evaluated MLX cases passed");
    Ok(())
}

fn execute_fixture_suite(
    client: &mut WorkerClient,
    manifest: &FixtureManifestIndex,
) -> Result<Value, String> {
    let hello = client.hello().clone();
    let health = client.health().map_err(|error| error.to_string())?;
    if !health.ready() {
        return Err("the negotiated MLX worker is not ready".to_owned());
    }
    let mut cases = Vec::with_capacity(manifest.operations.len());
    for case in &manifest.operations {
        let request = TensorFixtureRequest::new(
            &manifest.fixture_set_id,
            &case.case_id,
            &case.operation,
            GPU_DEVICE,
        )
        .map_err(|error| error.to_string())?;
        let result = client
            .run_fixture(&request)
            .map_err(|error| format!("{}: {error}", case.case_id))?;
        if !result.passed() {
            return Err(format!("{} did not produce passing evidence", case.case_id));
        }
        let comparison = result.comparison();
        let memory = result.memory_gauges();
        cases.push(json!({
            "case_id": result.case_id(),
            "operation": result.operation(),
            "backend_id": result.backend_id(),
            "requested_device": result.requested_device(),
            "selected_device": result.selected_device(),
            "fallback_used": result.fallback_used(),
            "output_shape": result.output_shape(),
            "input_dtype": result.input_dtype(),
            "accumulation_dtype": result.accumulation_dtype(),
            "output_dtype": result.output_dtype(),
            "evaluated": result.evaluated(),
            "synchronized": result.synchronized(),
            "actual": result.actual(),
            "comparison": {
                "oracle_id": comparison.oracle_id(),
                "mode": comparison.mode(),
                "absolute_tolerance": comparison.absolute_tolerance(),
                "relative_tolerance": comparison.relative_tolerance(),
                "non_finite_policy": comparison.non_finite_policy(),
                "compared_count": comparison.compared_count(),
                "max_absolute_error": comparison.max_absolute_error(),
                "max_relative_error": comparison.max_relative_error(),
                "first_mismatch_index": comparison.first_mismatch_index(),
                "passed": comparison.passed(),
            },
            "selected_expert_ids": result.selected_expert_ids(),
            "decoded": result.decoded(),
            "memory_gauges": {
                "mlx_active_bytes": memory.mlx_active_bytes(),
                "mlx_cache_bytes": memory.mlx_cache_bytes(),
                "mlx_peak_bytes": memory.mlx_peak_bytes(),
                "process_footprint_bytes": memory.process_footprint_bytes(),
                "process_footprint_source": memory.process_footprint_source(),
                "system_pressure": memory.system_pressure(),
                "reported_summed_total_bytes": memory.reported_summed_total_bytes(),
            },
            "passed": result.passed(),
        }));
    }
    Ok(json!({
        "schema_version": 1,
        "validation": "mlx-tensor-fixtures",
        "status": "passed",
        "fixture_set_id": manifest.fixture_set_id,
        "manifest": "fixtures/mlx/manifest.json",
        "backend_id": BACKEND_ID,
        "selected_device": GPU_DEVICE,
        "runtime": {
            "protocol": hello.protocol(),
            "worker_version": hello.worker_version(),
            "python_version": hello.python_version(),
            "python_arch": hello.python_arch(),
            "mlx_version": hello.mlx_version(),
            "macos_version": hello.macos_version(),
            "metal_available": hello.metal_available(),
            "gpu_count": hello.gpu_count(),
        },
        "case_count": cases.len(),
        "cases": cases,
        "exclusions": [
            "Fixtures are synthetic bounded tensors, not model weights.",
            "Q8_0 evidence covers only strict row decode and one row dot role.",
            "Linux and CUDA execution is not established by this command."
        ]
    }))
}

fn validate_synthetic_fixture_path(
    project_root: &Path,
    requested_path: &Path,
) -> Result<(), String> {
    let expected = fs::canonicalize(project_root.join("fixtures/mlx/routed-moe-v1.json"))
        .map_err(|_| "the committed synthetic MoE fixture is unavailable")?;
    let requested = fs::canonicalize(requested_path)
        .map_err(|_| "the requested synthetic MoE fixture is unavailable")?;
    if requested != expected {
        return Err(
            "validate-synthetic-moe accepts only the committed synthetic fixture".to_owned(),
        );
    }
    let bytes =
        fs::read(&requested).map_err(|_| "the committed synthetic fixture could not be read")?;
    if bytes.is_empty() || bytes.len() > MAX_MANIFEST_BYTES {
        return Err("the synthetic fixture violates its byte bound".to_owned());
    }
    let fixture: Value = serde_json::from_slice(&bytes)
        .map_err(|_| "the synthetic fixture is not valid bounded JSON")?;
    if fixture.get("schema_version").and_then(Value::as_u64) != Some(1)
        || fixture.get("fixture_id").and_then(Value::as_str) != Some(SYNTHETIC_MOE_FIXTURE_ID)
        || fixture.get("fixture_kind").and_then(Value::as_str) != Some("synthetic")
    {
        return Err("the synthetic fixture identity is not admitted".to_owned());
    }
    Ok(())
}

fn run_validate_synthetic_moe(command: ValidateSyntheticMoeCommand) -> Result<(), String> {
    let project_root = project_root();
    validate_synthetic_fixture_path(&project_root, &command.fixture)?;
    let config = worker_config(&project_root)?;
    let mut client = WorkerClient::spawn(config).map_err(|error| error.to_string())?;
    let validation = execute_synthetic_moe(&mut client);
    let cleanup = client.shutdown();
    let evidence = validation?;
    if cleanup.outcome() != CleanupOutcome::Graceful || cleanup.exit_code() != Some(0) {
        return Err(cleanup
            .error()
            .map(ToString::to_string)
            .unwrap_or_else(|| "MLX worker did not shut down cleanly".to_owned()));
    }
    write_evidence(&command.evidence, &evidence)?;
    println!("validate-synthetic-moe: evaluated routed MoE fixture passed");
    Ok(())
}

fn execute_synthetic_moe(client: &mut WorkerClient) -> Result<Value, String> {
    let hello = client.hello().clone();
    let health = client.health().map_err(|error| error.to_string())?;
    if !health.ready() {
        return Err("the negotiated MLX worker is not ready".to_owned());
    }
    let request = SyntheticMoeRequest::new(SYNTHETIC_MOE_FIXTURE_ID, GPU_DEVICE)
        .map_err(|error| error.to_string())?;
    let result = client
        .run_synthetic_moe(&request)
        .map_err(|error| error.to_string())?;
    if !result.passed() {
        return Err("the synthetic MoE result did not pass its committed oracle".to_owned());
    }

    let comparison = result.comparison();
    let memory = result.memory_gauges();
    let fetched_experts = result
        .fetched_experts()
        .iter()
        .map(|expert| {
            json!({
                "expert_id": expert.expert_id(),
                "offset": expert.offset(),
                "length": expert.length(),
                "shard_id": expert.shard_id(),
                "payload_sha256": expert.payload_sha256(),
            })
        })
        .collect::<Vec<_>>();

    Ok(json!({
        "schema_version": 1,
        "validation": "synthetic-routed-moe",
        "status": "passed",
        "fixture": "fixtures/mlx/routed-moe-v1.json",
        "fixture_id": result.fixture_id(),
        "fixture_kind": "synthetic",
        "backend_id": result.backend_id(),
        "requested_device": result.requested_device(),
        "selected_device": result.selected_device(),
        "fallback_used": result.fallback_used(),
        "evaluated": result.evaluated(),
        "synchronized": result.synchronized(),
        "runtime": {
            "protocol": hello.protocol(),
            "worker_version": hello.worker_version(),
            "python_version": hello.python_version(),
            "python_arch": hello.python_arch(),
            "mlx_version": hello.mlx_version(),
            "macos_version": hello.macos_version(),
            "metal_available": hello.metal_available(),
            "gpu_count": hello.gpu_count(),
        },
        "topology": {
            "token_count": result.token_count(),
            "hidden_size": result.hidden_size(),
            "expert_count": result.expert_count(),
            "top_k": result.top_k(),
        },
        "selected_expert_ids": result.selected_expert_ids(),
        "normalized_weights": result.normalized_weights(),
        "fetched_experts": fetched_experts,
        "actual": result.actual(),
        "comparison": {
            "oracle_id": comparison.oracle_id(),
            "absolute_tolerance": comparison.absolute_tolerance(),
            "relative_tolerance": comparison.relative_tolerance(),
            "non_finite_policy": "reject",
            "compared_count": comparison.compared_count(),
            "max_absolute_error": comparison.max_absolute_error(),
            "max_relative_error": comparison.max_relative_error(),
            "first_mismatch_index": comparison.first_mismatch_index(),
            "passed": comparison.passed(),
        },
        "memory_gauges": {
            "mlx_active_bytes": memory.mlx_active_bytes(),
            "mlx_cache_bytes": memory.mlx_cache_bytes(),
            "mlx_peak_bytes": memory.mlx_peak_bytes(),
            "process_footprint_bytes": memory.process_footprint_bytes(),
            "process_footprint_source": memory.process_footprint_source(),
            "system_pressure": memory.system_pressure(),
            "reported_summed_total_bytes": memory.reported_summed_total_bytes(),
        },
        "request_ids": {
            "health": health.request_id(),
        },
        "passed": true,
        "warnings": [
            "Linux and CUDA execution are not established by this command."
        ],
        "exclusions": [
            "The fixture is synthetic and does not contain model weights.",
            "No tokenizer, model loader, token generation, or serving path was exercised.",
            "Only dense float32 expert matrices and the committed two-token route were evaluated."
        ]
    }))
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ProbeResult {
    fixture_id: String,
    backend_id: String,
    requested_device: String,
    selected_device: String,
    fallback_used: bool,
    operation_id: String,
    input_shapes: Vec<Vec<usize>>,
    output_shape: Vec<usize>,
    input_dtype: String,
    accumulation_dtype: String,
    output_dtype: String,
    evaluated: bool,
    synchronized: bool,
    expected: Vec<f64>,
    actual: Vec<f64>,
    comparison: ProbeComparison,
    comparison_passed: bool,
    memory_gauges: Value,
    passed: bool,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ProbeComparison {
    oracle_id: String,
    absolute_tolerance: f64,
    relative_tolerance: f64,
    non_finite_policy: String,
    compared_count: usize,
    max_absolute_error: f64,
    max_relative_error: f64,
    first_mismatch_index: Option<usize>,
    passed: bool,
}

fn execute_device_smoke(
    client: &mut WorkerClient,
    command: &DeviceSmokeCommand,
) -> Result<Value, String> {
    let hello = client.hello().clone();
    let health = client.health().map_err(|error| error.to_string())?;
    if !health.ready() {
        return Err("the negotiated MLX worker is not ready".to_owned());
    }

    let mut params = Map::new();
    params.insert(
        "fixture_id".to_owned(),
        Value::String(FIXTURE_ID.to_owned()),
    );
    params.insert("device".to_owned(), Value::String(command.device.clone()));
    let (probe_request_id, raw_probe) = client
        .request_operation("tensor_probe", params)
        .map_err(|error| error.to_string())?;
    let probe: ProbeResult = serde_json::from_value(raw_probe)
        .map_err(|_| "the worker tensor-probe response did not match its bounded schema")?;

    if probe.fixture_id != FIXTURE_ID
        || !probe.passed
        || !probe.comparison_passed
        || !probe.comparison.passed
        || probe.comparison.compared_count != probe.expected.len()
        || probe.comparison.first_mismatch_index.is_some()
        || probe.comparison.non_finite_policy != "reject"
    {
        return Err("the worker did not return a passing evaluated tensor proof".to_owned());
    }

    let gpu_count = u32::try_from(hello.gpu_count())
        .map_err(|_| "the worker GPU inventory exceeds the admitted range")?;
    let device_hello = DeviceHello {
        python_arch: hello.python_arch().to_owned(),
        mlx_version: hello.mlx_version().to_owned(),
        metal_available: hello.metal_available(),
        gpu_count,
    };
    let device_probe = DeviceProbe {
        backend_id: probe.backend_id.clone(),
        requested_device: probe.requested_device.clone(),
        selected_device: probe.selected_device.clone(),
        fallback_used: probe.fallback_used,
        operation_id: probe.operation_id.clone(),
        evaluated: probe.evaluated,
        synchronized: probe.synchronized,
        expected: probe.expected.clone(),
        actual: probe.actual.clone(),
        absolute_tolerance: probe.comparison.absolute_tolerance,
        relative_tolerance: probe.comparison.relative_tolerance,
    };
    let report = validate_device_smoke(&device_hello, &device_probe)
        .map_err(|error| format!("device proof was rejected: {error}"))?;
    if probe.comparison.max_absolute_error != report.max_absolute_error()
        || probe.comparison.max_relative_error != report.max_relative_error()
    {
        return Err("the worker comparison summary does not match the validated values".to_owned());
    }

    Ok(json!({
        "schema_version": 1,
        "validation": "mlx-device-smoke",
        "status": "passed",
        "backend_id": command.backend,
        "selected_device": report.selected_device(),
        "device_state": "evaluated",
        "runtime": {
            "protocol": hello.protocol(),
            "worker_version": hello.worker_version(),
            "python_version": hello.python_version(),
            "python_arch": hello.python_arch(),
            "mlx_version": hello.mlx_version(),
            "macos_version": hello.macos_version(),
            "metal_available": hello.metal_available(),
            "gpu_count": hello.gpu_count(),
        },
        "probe": {
            "fixture_id": probe.fixture_id,
            "operation_id": probe.operation_id,
            "input_shapes": probe.input_shapes,
            "output_shape": probe.output_shape,
            "input_dtype": probe.input_dtype,
            "accumulation_dtype": probe.accumulation_dtype,
            "output_dtype": probe.output_dtype,
            "evaluated": probe.evaluated,
            "synchronized": probe.synchronized,
            "fallback_used": report.fallback_used(),
            "comparison_passed": report.comparison_passed(),
            "expected": probe.expected,
            "actual": probe.actual,
            "comparison": {
                "oracle_id": probe.comparison.oracle_id,
                "absolute_tolerance": probe.comparison.absolute_tolerance,
                "relative_tolerance": probe.comparison.relative_tolerance,
                "non_finite_policy": probe.comparison.non_finite_policy,
                "compared_count": report.compared_count(),
                "max_absolute_error": report.max_absolute_error(),
                "max_relative_error": report.max_relative_error(),
                "first_mismatch_index": probe.comparison.first_mismatch_index,
                "passed": report.comparison_passed(),
            },
            "memory_gauges": probe.memory_gauges,
            "passed": true,
        },
        "request_ids": {
            "health": health.request_id(),
            "tensor_probe": probe_request_id,
        },
        "exclusions": [
            "No model was loaded.",
            "No token generation or inference serving was exercised.",
            "Linux and CUDA behavior were not executed by this command."
        ]
    }))
}

fn write_evidence(path: &Path, evidence: &Value) -> Result<(), String> {
    let parent = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    if !parent.is_dir() {
        return Err("the evidence parent directory does not exist".to_owned());
    }
    let filename = path
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(|| "the evidence path must name a UTF-8 file".to_owned())?;
    let mut encoded =
        serde_json::to_vec(evidence).map_err(|_| "the validated evidence could not be encoded")?;
    encoded.push(b'\n');

    let mut temporary = None;
    for attempt in 0..32_u32 {
        let candidate = parent.join(format!(
            ".{filename}.pulsarmlx-{}-{attempt}.tmp",
            std::process::id()
        ));
        match OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&candidate)
        {
            Ok(file) => {
                temporary = Some((candidate, file));
                break;
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(_) => return Err("the temporary evidence file could not be created".to_owned()),
        }
    }
    let (temporary_path, mut temporary_file) = temporary
        .ok_or_else(|| "a unique temporary evidence file could not be created".to_owned())?;
    let written = temporary_file
        .write_all(&encoded)
        .and_then(|()| temporary_file.sync_all());
    drop(temporary_file);
    if written.is_err() {
        let _ = fs::remove_file(&temporary_path);
        return Err("the requested evidence file could not be written".to_owned());
    }
    if fs::rename(&temporary_path, path).is_err() {
        let _ = fs::remove_file(&temporary_path);
        return Err("the requested evidence file could not be installed atomically".to_owned());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(values: &[&str]) -> Vec<OsString> {
        values.iter().map(OsString::from).collect()
    }

    #[test]
    fn external_model_commands_accept_only_the_exact_bounded_surface() {
        let model = format!("/tmp/{QWEN_FILENAME}");
        let parsed = parse_external_model_command(
            args(&[
                "inspect-model",
                "--model",
                &model,
                "--evidence",
                "/tmp/out.json",
            ]),
            "inspect-model",
        )
        .expect("exact inspect command");
        assert_eq!(parsed.model, PathBuf::from(model));

        for invalid in [
            args(&[
                "inspect-model",
                "--model",
                QWEN_FILENAME,
                "--evidence",
                "/tmp/out.json",
            ]),
            args(&[
                "inspect-model",
                "--model",
                "/tmp/other.gguf",
                "--evidence",
                "/tmp/out.json",
            ]),
            args(&[
                "validate-model-slice",
                "--model",
                &format!("/tmp/{QWEN_FILENAME}"),
                "--token",
                "secret",
            ]),
            args(&[
                "validate-model-slice",
                "--model",
                &format!("/tmp/{QWEN_FILENAME}"),
                "--depth",
                "generation",
            ]),
        ] {
            let command = invalid
                .first()
                .and_then(|value| value.to_str())
                .expect("test command")
                .to_owned();
            assert!(parse_external_model_command(invalid, &command).is_err());
        }
    }

    #[test]
    fn real_model_comparison_uses_additive_absolute_plus_relative_tolerance() {
        let reference = [2.0];
        let admitted = compare_model_slice(&reference, &[2.0014]);
        assert!(admitted.passed);
        assert_eq!(admitted.mismatch_count, 0);

        let rejected = compare_model_slice(&reference, &[2.0016]);
        assert!(!rejected.passed);
        assert_eq!(rejected.mismatch_count, 1);
        assert_eq!(rejected.first_mismatch.as_ref().unwrap()["index"], 0);

        let zero_reference = compare_model_slice(&[0.0], &[f64::from(f32::MIN_POSITIVE)]);
        assert_eq!(zero_reference.max_relative_error, 1.0);
    }

    #[cfg(unix)]
    #[test]
    fn evidence_aliases_are_rejected_and_atomic_writes_do_not_follow_symlinks() {
        use std::os::unix::fs::symlink;
        use std::time::{SystemTime, UNIX_EPOCH};

        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system clock")
            .as_nanos();
        let directory = env::temp_dir().join(format!(
            "pulsarmlx-evidence-alias-{}-{nonce}",
            std::process::id()
        ));
        fs::create_dir(&directory).expect("create test directory");
        let model = directory.join(QWEN_FILENAME);
        fs::write(&model, b"model-bytes").expect("write model stand-in");
        assert!(ensure_distinct_model_and_evidence(&model, &model).is_err());

        let hard_link = directory.join("hard-link.json");
        fs::hard_link(&model, &hard_link).expect("create hard link");
        assert!(ensure_distinct_model_and_evidence(&model, &hard_link).is_err());

        let symlink_path = directory.join("symlink.json");
        symlink(&model, &symlink_path).expect("create symlink");
        assert!(ensure_distinct_model_and_evidence(&model, &symlink_path).is_err());
        write_evidence(&symlink_path, &json!({"status": "passed"}))
            .expect("atomic write replaces the symlink itself");
        assert_eq!(fs::read(&model).expect("model remains"), b"model-bytes");

        fs::remove_file(&symlink_path).expect("remove evidence");
        fs::remove_file(&hard_link).expect("remove hard link");
        fs::remove_file(&model).expect("remove model stand-in");
        fs::remove_dir(&directory).expect("remove test directory");
    }

    #[test]
    fn evidence_private_path_scan_rejects_nested_machine_paths() {
        let safe = json!({"model": format!("<external-model>/{QWEN_FILENAME}")});
        assert!(ensure_no_private_paths(&safe).is_ok());
        let private = json!({"nested": [{"model": "/Users/private/model.gguf"}]});
        assert!(ensure_no_private_paths(&private).is_err());
    }

    #[test]
    fn committed_reference_result_matches_the_frozen_loader_contract() {
        let reference = load_frozen_reference(&project_root()).expect("committed reference result");
        assert_eq!(
            reference.encoded_slice_sha256,
            "14e9e5efa5b8cc65f02c6445f3697e729a045408af25b579a2e1d007c336fadf"
        );
        assert_eq!(
            reference.decoded_slice_sha256,
            "5aa54eb798fdf16d79b112a58338211fbab393b94161b9219b19c4700f46d91b"
        );
        assert_eq!(
            reference.output_sha256,
            "610357fb4919bf3906f869c81e13abaa46e6ab71dbe2741bc411037506045b51"
        );
        assert_eq!(reference.values.len(), REAL_OUTPUT_COUNT);
    }
}
