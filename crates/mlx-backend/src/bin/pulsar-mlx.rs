use mlx_backend::{
    validate_device_smoke, CleanupOutcome, DeviceHello, DeviceProbe, SyntheticMoeRequest,
    TensorFixtureRequest, WorkerClient, WorkerConfig, PINNED_MLX_VERSION,
};
use serde::Deserialize;
use serde_json::{json, Map, Value};
use std::collections::BTreeSet;
use std::env;
use std::ffi::OsString;
use std::fs;
use std::path::{Path, PathBuf};

const BACKEND_ID: &str = "apple-mlx";
const GPU_DEVICE: &str = "gpu";
const FIXTURE_ID: &str = "nonsymmetric-f32-matmul-v1";
const FIXTURE_SET_ID: &str = "mlx-tensor-fixtures-v1";
const SYNTHETIC_MOE_FIXTURE_ID: &str = "synthetic-routed-moe-v1";
const MAX_MANIFEST_BYTES: usize = 1024 * 1024;

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
    "usage: pulsar-mlx device-smoke --backend apple-mlx --device gpu --evidence PATH\n       pulsar-mlx validate-fixtures --manifest fixtures/mlx/manifest.json --evidence PATH\n       pulsar-mlx validate-synthetic-moe --fixture fixtures/mlx/routed-moe-v1.json --evidence PATH".to_owned()
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
    if let Some(parent) = path.parent() {
        if !parent.as_os_str().is_empty() && !parent.is_dir() {
            return Err("the evidence parent directory does not exist".to_owned());
        }
    }
    let mut encoded =
        serde_json::to_vec(evidence).map_err(|_| "the validated evidence could not be encoded")?;
    encoded.push(b'\n');
    fs::write(path, encoded)
        .map_err(|_| "the requested evidence file could not be written".to_owned())
}
