use mlx_backend::protocol::MAX_RESPONSE_BYTES;
use mlx_backend::router::{
    compare_router_outputs, validate_major_router_timing_series, RouterCaseScope,
    RouterNumericComparison, RouterOutput, RouterOutputComparison, RouterTimingInstrumentationMode,
    RouterTimingObservationStatus, RouterTimingReplicationRole, RouterTimingSeries,
    RouterTimingSeriesKind, RouterTolerancePolicy, ROUTER_MAJOR_SINGLE_ROW_BENCHMARK_ID,
    ROUTER_MAJOR_TWO_ROW_BENCHMARK_ID, ROUTER_REAL_SINGLE_ROW_CASE_ID, ROUTER_REAL_TWO_ROW_CASE_ID,
};
use mlx_backend::{
    frozen_qwen_model_memory_budget, inspect_external_qwen_model, validate_device_smoke,
    CleanupOutcome, DeviceHello, DeviceProbe, ExternalModelInspection, ModelSliceRequest,
    ModelSliceResult, RouterRequest, RouterResult, SyntheticMoeRequest, TensorFixtureRequest,
    WorkerClient, WorkerConfig, MODEL_FILE_DESCRIPTOR, MODEL_SLICE_ID, PINNED_MLX_VERSION,
    QWEN_FILENAME, QWEN_FILE_BYTES, QWEN_REPOSITORY_ID, QWEN_REVISION, QWEN_SHA256,
    ROUTER_SINGLE_ROW_CASE_ID, ROUTER_TWO_ROW_CASE_ID,
};
use serde::de::{DeserializeOwned, Error as DeError, MapAccess, SeqAccess, Visitor};
use serde::{Deserialize, Deserializer};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::ffi::OsString;
use std::fmt;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Component, Path, PathBuf};
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
const ROUTER_FIXTURE_ID: &str = "generated-qwen3moe-router-v1";
const ROUTER_EXPECTED_RESULTS_ID: &str = "generated-qwen3moe-router-expected-results-v1";
const ROUTER_SYNTHETIC_TIE_ID: &str = "generated-qwen3moe-router-synthetic-cutoff-v1";
const ROUTER_FIXTURE_MAX_EVIDENCE_BYTES: usize = 256 * 1024;
#[cfg_attr(not(test), allow(dead_code))]
const ROUTER_CORRECTNESS_WARMUPS: usize = 5;
#[cfg_attr(not(test), allow(dead_code))]
const ROUTER_CORRECTNESS_REPETITIONS: usize = 10;
#[cfg_attr(not(test), allow(dead_code))]
const ROUTER_CORRECTNESS_ATTEMPTS: usize =
    ROUTER_CORRECTNESS_WARMUPS + ROUTER_CORRECTNESS_REPETITIONS;
#[cfg_attr(not(test), allow(dead_code))]
const ROUTER_FIRST_PROCESS_REPETITIONS: usize = 10;
#[cfg_attr(not(test), allow(dead_code))]
const ROUTER_BENCHMARK_ORDER_SEED: u64 = 22_002;
#[cfg_attr(not(test), allow(dead_code))]
const ROUTER_PRIMARY_BATCH_ID: &str = "batch-a";
const ROUTER_FIXTURE_FILES: [&str; 11] = [
    "golden/expected_results.json",
    "golden/hidden_states.json",
    "golden/weight_recipe.json",
    "malformed/invalid-control-type.json",
    "malformed/invalid-hidden-shape.json",
    "malformed/invalid-orientation.json",
    "malformed/invalid-top-k.json",
    "malformed/non-finite-hidden-state.json",
    "malformed/overlong-router-range.json",
    "malformed/truncated-router-range.json",
    "synthetic-tie.json",
];
const ROUTER_NEGATIVE_EXPECTATIONS: [(&str, &str, &str, &str); 7] = [
    (
        "malformed/invalid-control-type.json",
        "malformed_scalar_type",
        "malformed_request",
        "worker_control_admission",
    ),
    (
        "malformed/invalid-hidden-shape.json",
        "malformed_hidden_shape",
        "invalid_shape",
        "worker_hidden_state_admission",
    ),
    (
        "malformed/invalid-orientation.json",
        "transposed_router_orientation",
        "invalid_layout",
        "host_tensor_descriptor_admission",
    ),
    (
        "malformed/invalid-top-k.json",
        "invalid_top_k",
        "model_tensor_mismatch",
        "host_tensor_descriptor_admission",
    ),
    (
        "malformed/non-finite-hidden-state.json",
        "non_finite_hidden_state",
        "invalid_dtype",
        "worker_hidden_state_admission",
    ),
    (
        "malformed/overlong-router-range.json",
        "overlong_router_range",
        "invalid_byte_count",
        "host_positional_range_read",
    ),
    (
        "malformed/truncated-router-range.json",
        "truncated_router_range",
        "invalid_byte_count",
        "host_positional_range_read",
    ),
];

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
        Some("inspect-router") => run_planned_inspect_router(parse_inspect_router(arguments)?),
        Some("validate-router-fixtures") => {
            run_planned_validate_router_fixtures(parse_validate_router_fixtures(arguments)?)
        }
        Some("validate-router") => run_planned_validate_router(parse_validate_router(arguments)?),
        _ => Err(usage()),
    }
}

fn project_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn lexical_project_root() -> &'static Path {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .expect("the mlx-backend manifest has a workspace root")
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
    "usage: pulsar-mlx device-smoke --backend apple-mlx --device gpu --evidence PATH\n       pulsar-mlx validate-fixtures --manifest fixtures/mlx/manifest.json --evidence PATH\n       pulsar-mlx validate-synthetic-moe --fixture fixtures/mlx/routed-moe-v1.json --evidence PATH\n       pulsar-mlx inspect-model --model ABSOLUTE_EXTERNAL_GGUF --evidence PATH\n       pulsar-mlx validate-model-slice --model ABSOLUTE_EXTERNAL_GGUF --evidence PATH\n       pulsar-mlx inspect-router --model ABSOLUTE_EXTERNAL_GGUF --evidence ABSOLUTE_EXTERNAL_JSON\n       pulsar-mlx validate-router-fixtures --manifest fixtures/research/router-v1/manifest.json --evidence ABSOLUTE_EXTERNAL_JSON\n       pulsar-mlx validate-router --model ABSOLUTE_EXTERNAL_GGUF --oracle ABSOLUTE_EXTERNAL_JSON --evidence-dir ABSOLUTE_EXTERNAL_DIRECTORY".to_owned()
}

const ROUTER_FIXTURE_MANIFEST: &str = "fixtures/research/router-v1/manifest.json";

#[derive(Debug, PartialEq, Eq)]
struct InspectRouterCommand {
    model: PathBuf,
    evidence: PathBuf,
}

#[derive(Debug, PartialEq, Eq)]
struct ValidateRouterFixturesCommand {
    manifest: PathBuf,
    evidence: PathBuf,
}

#[derive(Debug, PartialEq, Eq)]
struct ValidateRouterCommand {
    model: PathBuf,
    oracle: PathBuf,
    evidence_dir: PathBuf,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RouterFixtureManifestIndex {
    schema: String,
    schema_version: String,
    fixture_id: String,
    provenance: RouterFixtureProvenanceIndex,
    contract: RouterFixtureContractIndex,
    cases: Vec<RouterFixtureCaseIndex>,
    expected_results: RouterExpectedResultsIndex,
    hidden_state_fixture: Value,
    weight_fixture: Value,
    files: Vec<RouterFixtureFileIndex>,
    scope: Value,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RouterFixtureProvenanceIndex {
    kind: String,
    generator: String,
    generator_sha256: String,
    generation_command: String,
    independence: String,
    model_free: bool,
    external_checkpoint_access_required: bool,
    redistributable: bool,
    license: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RouterFixtureContractIndex {
    contract_id: String,
    hidden_width: u64,
    expert_count: u64,
    top_k: u64,
    weight_dtype: String,
    weight_byte_order: String,
    weight_layout: String,
    tie_rule: String,
    normalization: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RouterFixtureCaseIndex {
    case_id: String,
    hidden_shape: [u64; 2],
    hidden_row_ids: Vec<String>,
    hidden_f32le_sha256: String,
    expected_result_key: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RouterExpectedResultsIndex {
    path: String,
    arithmetic: String,
    independently_computed: bool,
    complete_values: bool,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RouterFixtureFileIndex {
    path: String,
    byte_length: u64,
    sha256: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RouterGoldenDocument {
    schema: String,
    schema_version: String,
    fixture_id: String,
    contract: Value,
    cases: BTreeMap<String, RouterGoldenCase>,
    provenance: Value,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RouterGoldenCase {
    case_id: String,
    hidden_row_ids: Vec<String>,
    hidden_shape: [usize; 2],
    logits_shape: [usize; 2],
    logits: Vec<Vec<f64>>,
    full_softmax_probabilities: Vec<Vec<f64>>,
    selected_expert_ids: Vec<Vec<u64>>,
    selected_probabilities: Vec<Vec<f64>>,
    normalized_weights: Vec<Vec<f64>>,
    hashes: RouterGoldenHashes,
    provenance: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RouterGoldenHashes {
    logits_f32le_sha256: String,
    full_softmax_probabilities_f32le_sha256: String,
    selected_expert_ids_u32le_sha256: String,
    selected_probabilities_f32le_sha256: String,
    normalized_weights_f32le_sha256: String,
    float_output_bundle_f32le_sha256: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RouterTieDocument {
    schema: String,
    schema_version: String,
    fixture_id: String,
    contract: Value,
    bounds: Value,
    provenance: Value,
    cases: Vec<RouterTieCase>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RouterTieCase {
    case_id: String,
    kind: String,
    provenance: String,
    logits_shape: [usize; 2],
    logits: Vec<Vec<f64>>,
    full_softmax_probabilities: Vec<Vec<f64>>,
    selected_expert_ids: Vec<Vec<u64>>,
    selected_probabilities: Vec<Vec<f64>>,
    normalized_weights: Vec<Vec<f64>>,
    hashes: RouterGoldenHashes,
    cutoff: RouterTieCutoff,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RouterTieCutoff {
    rank_8_expert_id: u64,
    rank_9_expert_id: u64,
    rank_8_logit_f32_bits: String,
    rank_9_logit_f32_bits: String,
    rank_8_probability_f32_bits: String,
    rank_9_probability_f32_bits: String,
    relation: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RouterNegativeDocument {
    schema: String,
    schema_version: String,
    fixture_id: String,
    contract_id: String,
    bounds: Value,
    provenance: RouterNegativeProvenance,
    case: RouterNegativeCase,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RouterNegativeProvenance {
    kind: String,
    evidence_level: String,
    model_free: bool,
    external_checkpoint_access_required: bool,
    raw_model_or_tensor_bytes_committed: bool,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RouterNegativeCase {
    category: String,
    validation_surface: String,
    mutation: Value,
    expected_failure: RouterExpectedFailure,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RouterExpectedFailure {
    code: String,
    accepted_result: bool,
    router_runner_called: bool,
    must_precede: String,
}

struct RouterFixtureBundle {
    manifest_sha256: String,
    manifest_files: Vec<Value>,
    case_order: Vec<String>,
    golden_cases: BTreeMap<String, RouterGoldenCase>,
    tie_cases: Vec<RouterTieCase>,
    negative_cases: Vec<Value>,
}

#[derive(Debug, Clone)]
struct RetainedRouterFixtureFailure {
    status: &'static str,
    stage: &'static str,
    code: String,
    message: String,
}

struct RouterFixtureAttempt {
    manifest_sha256: Option<String>,
    manifest_files: Vec<Value>,
    runtime: Option<Value>,
    positive_cases: Vec<Value>,
    tie_cases: Vec<Value>,
    negative_cases: Vec<Value>,
    cleanup: Value,
    failure: Option<RetainedRouterFixtureFailure>,
}

struct UniqueJsonValue(Value);

impl<'de> Deserialize<'de> for UniqueJsonValue {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        struct UniqueValueVisitor;

        impl<'de> Visitor<'de> for UniqueValueVisitor {
            type Value = Value;

            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("JSON without duplicate object keys")
            }

            fn visit_bool<E>(self, value: bool) -> Result<Self::Value, E> {
                Ok(Value::Bool(value))
            }

            fn visit_i64<E>(self, value: i64) -> Result<Self::Value, E> {
                Ok(Value::Number(value.into()))
            }

            fn visit_u64<E>(self, value: u64) -> Result<Self::Value, E> {
                Ok(Value::Number(value.into()))
            }

            fn visit_f64<E>(self, value: f64) -> Result<Self::Value, E>
            where
                E: DeError,
            {
                serde_json::Number::from_f64(value)
                    .map(Value::Number)
                    .ok_or_else(|| E::custom("JSON number is not finite"))
            }

            fn visit_str<E>(self, value: &str) -> Result<Self::Value, E>
            where
                E: DeError,
            {
                Ok(Value::String(value.to_owned()))
            }

            fn visit_string<E>(self, value: String) -> Result<Self::Value, E> {
                Ok(Value::String(value))
            }

            fn visit_none<E>(self) -> Result<Self::Value, E> {
                Ok(Value::Null)
            }

            fn visit_unit<E>(self) -> Result<Self::Value, E> {
                Ok(Value::Null)
            }

            fn visit_seq<A>(self, mut sequence: A) -> Result<Self::Value, A::Error>
            where
                A: SeqAccess<'de>,
            {
                let mut values = Vec::new();
                while let Some(value) = sequence.next_element::<UniqueJsonValue>()? {
                    values.push(value.0);
                }
                Ok(Value::Array(values))
            }

            fn visit_map<A>(self, mut object: A) -> Result<Self::Value, A::Error>
            where
                A: MapAccess<'de>,
            {
                let mut values = Map::new();
                while let Some((key, value)) = object.next_entry::<String, UniqueJsonValue>()? {
                    if values.insert(key, value.0).is_some() {
                        return Err(A::Error::custom("duplicate JSON object key"));
                    }
                }
                Ok(Value::Object(values))
            }
        }

        deserializer.deserialize_any(UniqueValueVisitor).map(Self)
    }
}

fn parse_unique_json<T: DeserializeOwned>(bytes: &[u8], label: &str) -> Result<T, String> {
    let value: UniqueJsonValue = serde_json::from_slice(bytes)
        .map_err(|_| format!("the {label} is not duplicate-free bounded JSON"))?;
    serde_json::from_value(value.0)
        .map_err(|_| format!("the {label} does not match its frozen contract"))
}

impl RouterFixtureAttempt {
    fn new() -> Self {
        Self {
            manifest_sha256: None,
            manifest_files: Vec::new(),
            runtime: None,
            positive_cases: Vec::new(),
            tie_cases: Vec::new(),
            negative_cases: Vec::new(),
            cleanup: json!({
                "attempted": false,
                "outcome": "not_started",
                "exit_code": null,
            }),
            failure: None,
        }
    }

    fn retain_failure(&mut self, failure: RetainedRouterFixtureFailure) {
        if self.failure.is_none() {
            self.failure = Some(failure);
        }
    }

    fn evidence(&self) -> Value {
        let status = self
            .failure
            .as_ref()
            .map_or("passed", |failure| failure.status);
        let failure = self.failure.as_ref().map(|failure| {
            json!({
                "stage": failure.stage,
                "code": failure.code,
                "message": failure.message,
            })
        });
        json!({
            "schema_version": 1,
            "validation": "qwen3moe-router-fixtures",
            "status": status,
            "passed": self.failure.is_none(),
            "fixture_kind": "synthetic",
            "evidence_level": "synthetic_fixture_only",
            "model_free": true,
            "real_checkpoint_evidence": false,
            "external_checkpoint_accessed": false,
            "manifest": ROUTER_FIXTURE_MANIFEST,
            "manifest_sha256": self.manifest_sha256,
            "manifest_files": self.manifest_files,
            "runtime": self.runtime,
            "positive_cases": self.positive_cases,
            "synthetic_tie_cases": self.tie_cases,
            "negative_cases": self.negative_cases,
            "cleanup": self.cleanup,
            "failure": failure,
            "warnings": [
                "Tie cases use host contract validation and are not represented as MLX execution.",
                "Negative fixture records verify the frozen failure contract; focused tests prove rejection ordering and runner-not-called behavior."
            ],
            "exclusions": [
                "No external checkpoint, model descriptor, model weight, or real hidden state was accessed.",
                "Synthetic results are not real-checkpoint router evidence.",
                "No expert, complete layer, generation, serving, or non-Apple backend execution was established."
            ]
        })
    }
}

fn parse_router_arguments(arguments: Vec<OsString>) -> Result<Vec<String>, String> {
    arguments
        .into_iter()
        .map(|value| {
            value
                .into_string()
                .map_err(|_| "command arguments must be valid UTF-8".to_owned())
        })
        .collect()
}

#[derive(Debug)]
struct CanonicalPathIdentity {
    resolved: PathBuf,
    #[cfg(unix)]
    existing_object: Option<(u64, u64)>,
}

impl CanonicalPathIdentity {
    fn aliases_or_contains(&self, other: &Self) -> bool {
        if self.resolved == other.resolved
            || self.resolved.starts_with(&other.resolved)
            || other.resolved.starts_with(&self.resolved)
        {
            return true;
        }

        #[cfg(unix)]
        if self.existing_object.is_some() && self.existing_object == other.existing_object {
            return true;
        }

        false
    }
}

fn canonical_path_identity(path: &Path, kind: &str) -> Result<CanonicalPathIdentity, String> {
    let direct_metadata = match fs::symlink_metadata(path) {
        Ok(metadata) => {
            if metadata.file_type().is_symlink() {
                return Err(format!("the {kind} path must not be a symbolic-link alias"));
            }
            Some(metadata)
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => None,
        Err(_) => return Err(format!("the {kind} path metadata could not be inspected")),
    };

    let mut existing_prefix = path;
    while fs::symlink_metadata(existing_prefix)
        .is_err_and(|error| error.kind() == std::io::ErrorKind::NotFound)
    {
        existing_prefix = existing_prefix
            .parent()
            .ok_or_else(|| format!("the {kind} path has no resolvable parent"))?;
    }
    let resolved_prefix = fs::canonicalize(existing_prefix)
        .map_err(|_| format!("the {kind} path could not be resolved without following it"))?;
    let unresolved_suffix = path
        .strip_prefix(existing_prefix)
        .map_err(|_| format!("the {kind} path could not be resolved safely"))?;
    let resolved = resolved_prefix.join(unresolved_suffix);

    #[cfg(unix)]
    let existing_object = direct_metadata.as_ref().map(|metadata| {
        use std::os::unix::fs::MetadataExt;

        (metadata.dev(), metadata.ino())
    });

    Ok(CanonicalPathIdentity {
        resolved,
        #[cfg(unix)]
        existing_object,
    })
}

fn validate_external_path_syntax(path: &Path, kind: &str) -> Result<(), String> {
    if !path.is_absolute() {
        return Err(format!("the {kind} path must be absolute and external"));
    }
    if path.components().any(|component| {
        matches!(
            component,
            Component::CurDir | Component::ParentDir | Component::Prefix(_)
        )
    }) {
        return Err(format!(
            "the {kind} path must not contain ambiguous path components"
        ));
    }
    if path.starts_with(lexical_project_root()) || lexical_project_root().starts_with(path) {
        return Err(format!(
            "the {kind} path must remain outside the repository"
        ));
    }
    Ok(())
}

fn validate_external_json_path_syntax(path: &Path, kind: &str) -> Result<(), String> {
    validate_external_path_syntax(path, kind)?;
    if path.extension().and_then(|extension| extension.to_str()) != Some("json") {
        return Err(format!("the {kind} path must name a JSON file"));
    }
    Ok(())
}

fn validate_router_model_path_syntax(path: &Path) -> Result<(), String> {
    validate_external_path_syntax(path, "external model")?;
    if path.file_name().and_then(|name| name.to_str()) != Some(QWEN_FILENAME) {
        return Err("the external model must use the exact admitted filename".to_owned());
    }
    Ok(())
}

fn paths_are_lexically_distinct(paths: &[&Path]) -> bool {
    paths.iter().enumerate().all(|(index, path)| {
        paths[index + 1..]
            .iter()
            .all(|other| path != other && !path.starts_with(other) && !other.starts_with(path))
    })
}

fn validate_external_path_identity(
    path: &Path,
    kind: &str,
) -> Result<CanonicalPathIdentity, String> {
    validate_external_path_syntax(path, kind)?;
    let identity = canonical_path_identity(path, kind)?;
    let repository_root = fs::canonicalize(lexical_project_root())
        .map_err(|_| "the repository root could not be resolved safely".to_owned())?;
    if identity.resolved.starts_with(&repository_root)
        || repository_root.starts_with(&identity.resolved)
    {
        return Err(format!(
            "the {kind} path must remain outside the repository"
        ));
    }
    Ok(identity)
}

fn validate_external_json_path_identity(
    path: &Path,
    kind: &str,
) -> Result<CanonicalPathIdentity, String> {
    validate_external_json_path_syntax(path, kind)?;
    validate_external_path_identity(path, kind)
}

fn validate_router_model_path_identity(path: &Path) -> Result<CanonicalPathIdentity, String> {
    validate_router_model_path_syntax(path)?;
    validate_external_path_identity(path, "external model")
}

fn paths_are_distinct(paths: &[&CanonicalPathIdentity]) -> bool {
    paths.iter().enumerate().all(|(index, path)| {
        paths[index + 1..]
            .iter()
            .all(|other| !path.aliases_or_contains(other))
    })
}

#[allow(dead_code)] // Called only after the T074 external-access gate is implemented.
fn validate_inspect_router_path_identities(command: &InspectRouterCommand) -> Result<(), String> {
    let model_identity = validate_router_model_path_identity(&command.model)?;
    let evidence_identity =
        validate_external_json_path_identity(&command.evidence, "router inspection evidence")?;
    if !paths_are_distinct(&[&model_identity, &evidence_identity]) {
        return Err("router inspection paths must be distinct".to_owned());
    }
    Ok(())
}

fn validate_router_fixture_path_identities(
    command: &ValidateRouterFixturesCommand,
) -> Result<(), String> {
    let manifest_identity = canonical_path_identity(
        &lexical_project_root().join(&command.manifest),
        "committed router manifest",
    )?;
    let evidence_identity =
        validate_external_json_path_identity(&command.evidence, "router fixture evidence")?;
    if !paths_are_distinct(&[&manifest_identity, &evidence_identity]) {
        return Err("router fixture paths must be distinct".to_owned());
    }
    Ok(())
}

#[allow(dead_code)] // Called only after the T083 external-execution gate is implemented.
fn validate_router_path_identities(command: &ValidateRouterCommand) -> Result<(), String> {
    let model_identity = validate_router_model_path_identity(&command.model)?;
    let oracle_identity = validate_external_json_path_identity(&command.oracle, "router oracle")?;
    let evidence_identity =
        validate_external_path_identity(&command.evidence_dir, "router evidence directory")?;
    if !paths_are_distinct(&[&model_identity, &oracle_identity, &evidence_identity]) {
        return Err("router model, oracle, and evidence paths must be distinct".to_owned());
    }
    Ok(())
}

fn parse_inspect_router(arguments: Vec<OsString>) -> Result<InspectRouterCommand, String> {
    let values = parse_router_arguments(arguments)?;
    if values.len() != 5 || values.first().map(String::as_str) != Some("inspect-router") {
        return Err(usage());
    }

    let mut model = None;
    let mut evidence = None;
    let mut index = 1;
    while index < values.len() {
        let value = values.get(index + 1).ok_or_else(usage)?.to_owned();
        match values[index].as_str() {
            "--model" if model.is_none() => model = Some(PathBuf::from(value)),
            "--evidence" if evidence.is_none() => evidence = Some(PathBuf::from(value)),
            _ => return Err(usage()),
        }
        index += 2;
    }

    let model = model.ok_or_else(usage)?;
    let evidence = evidence.ok_or_else(usage)?;
    validate_router_model_path_syntax(&model)?;
    validate_external_json_path_syntax(&evidence, "router inspection evidence")?;
    if !paths_are_lexically_distinct(&[&model, &evidence]) {
        return Err("router inspection paths must be distinct".to_owned());
    }
    Ok(InspectRouterCommand { model, evidence })
}

fn parse_validate_router_fixtures(
    arguments: Vec<OsString>,
) -> Result<ValidateRouterFixturesCommand, String> {
    let values = parse_router_arguments(arguments)?;
    if values.len() != 5 || values.first().map(String::as_str) != Some("validate-router-fixtures") {
        return Err(usage());
    }

    let mut manifest = None;
    let mut evidence = None;
    let mut index = 1;
    while index < values.len() {
        let value = values.get(index + 1).ok_or_else(usage)?.to_owned();
        match values[index].as_str() {
            "--manifest" if manifest.is_none() => manifest = Some(PathBuf::from(value)),
            "--evidence" if evidence.is_none() => evidence = Some(PathBuf::from(value)),
            _ => return Err(usage()),
        }
        index += 2;
    }

    let manifest = manifest.ok_or_else(usage)?;
    let evidence = evidence.ok_or_else(usage)?;
    if manifest != Path::new(ROUTER_FIXTURE_MANIFEST) {
        return Err(
            "validate-router-fixtures accepts only the committed router manifest".to_owned(),
        );
    }
    validate_external_json_path_syntax(&evidence, "router fixture evidence")?;
    Ok(ValidateRouterFixturesCommand { manifest, evidence })
}

fn parse_validate_router(arguments: Vec<OsString>) -> Result<ValidateRouterCommand, String> {
    let values = parse_router_arguments(arguments)?;
    if values.len() != 7 || values.first().map(String::as_str) != Some("validate-router") {
        return Err(usage());
    }

    let mut model = None;
    let mut oracle = None;
    let mut evidence_dir = None;
    let mut index = 1;
    while index < values.len() {
        let value = values.get(index + 1).ok_or_else(usage)?.to_owned();
        match values[index].as_str() {
            "--model" if model.is_none() => model = Some(PathBuf::from(value)),
            "--oracle" if oracle.is_none() => oracle = Some(PathBuf::from(value)),
            "--evidence-dir" if evidence_dir.is_none() => evidence_dir = Some(PathBuf::from(value)),
            _ => return Err(usage()),
        }
        index += 2;
    }

    let model = model.ok_or_else(usage)?;
    let oracle = oracle.ok_or_else(usage)?;
    let evidence_dir = evidence_dir.ok_or_else(usage)?;
    validate_router_model_path_syntax(&model)?;
    validate_external_json_path_syntax(&oracle, "router oracle")?;
    validate_external_path_syntax(&evidence_dir, "router evidence directory")?;
    if !paths_are_lexically_distinct(&[&model, &oracle, &evidence_dir]) {
        return Err("router model, oracle, and evidence paths must be distinct".to_owned());
    }
    Ok(ValidateRouterCommand {
        model,
        oracle,
        evidence_dir,
    })
}

fn retained_fixture_failure(
    status: &'static str,
    stage: &'static str,
    code: impl Into<String>,
    message: impl Into<String>,
) -> RetainedRouterFixtureFailure {
    RetainedRouterFixtureFailure {
        status,
        stage,
        code: code.into(),
        message: message.into(),
    }
}

fn sha256_bytes(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn canonical_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn read_bounded_regular_file(
    fixture_root: &Path,
    relative_path: &str,
    maximum_bytes: usize,
) -> Result<Vec<u8>, String> {
    let relative = Path::new(relative_path);
    if relative.as_os_str().is_empty()
        || relative.is_absolute()
        || relative
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err("a router fixture path is not a bounded relative file path".to_owned());
    }
    let path = fixture_root.join(relative);
    let metadata = fs::symlink_metadata(&path)
        .map_err(|_| "a committed router fixture file is unavailable".to_owned())?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err("a committed router fixture must be a regular non-link file".to_owned());
    }
    let resolved = fs::canonicalize(&path)
        .map_err(|_| "a committed router fixture file could not be resolved".to_owned())?;
    if !resolved.starts_with(fixture_root) {
        return Err("a committed router fixture escapes its fixture root".to_owned());
    }
    let bytes = fs::read(&resolved)
        .map_err(|_| "a committed router fixture file could not be read".to_owned())?;
    if bytes.is_empty() || bytes.len() > maximum_bytes {
        return Err("a committed router fixture file violates its byte bound".to_owned());
    }
    Ok(bytes)
}

fn load_router_fixture_bundle(
    root: &Path,
    requested_manifest: &Path,
) -> Result<RouterFixtureBundle, String> {
    let expected_manifest = fs::canonicalize(root.join(ROUTER_FIXTURE_MANIFEST))
        .map_err(|_| "the committed router fixture manifest is unavailable".to_owned())?;
    let requested = fs::canonicalize(root.join(requested_manifest))
        .map_err(|_| "the requested router fixture manifest is unavailable".to_owned())?;
    if requested != expected_manifest {
        return Err(
            "validate-router-fixtures accepts only the committed router manifest".to_owned(),
        );
    }
    let manifest_metadata = fs::symlink_metadata(root.join(requested_manifest))
        .map_err(|_| "the router fixture manifest metadata is unavailable".to_owned())?;
    if manifest_metadata.file_type().is_symlink() || !manifest_metadata.is_file() {
        return Err(
            "the committed router fixture manifest must be a regular non-link file".to_owned(),
        );
    }
    let manifest_bytes = fs::read(&requested)
        .map_err(|_| "the committed router fixture manifest could not be read".to_owned())?;
    if manifest_bytes.is_empty() || manifest_bytes.len() > MAX_MANIFEST_BYTES {
        return Err("the router fixture manifest violates its byte bound".to_owned());
    }
    let manifest: RouterFixtureManifestIndex =
        parse_unique_json(&manifest_bytes, "router fixture manifest")?;
    validate_router_fixture_manifest(&manifest)?;

    let fixture_root = requested
        .parent()
        .ok_or_else(|| "the router fixture manifest has no fixture root".to_owned())?;
    let mut payloads = BTreeMap::new();
    let mut manifest_files = Vec::with_capacity(manifest.files.len());
    for (entry, expected_path) in manifest.files.iter().zip(ROUTER_FIXTURE_FILES) {
        if entry.path != expected_path || entry.byte_length == 0 || !canonical_sha256(&entry.sha256)
        {
            return Err("the router fixture file inventory is not admitted".to_owned());
        }
        let bytes = read_bounded_regular_file(fixture_root, &entry.path, MAX_MANIFEST_BYTES)?;
        let observed_length = u64::try_from(bytes.len())
            .map_err(|_| "a router fixture byte length is not representable".to_owned())?;
        let observed_sha256 = sha256_bytes(&bytes);
        if observed_length != entry.byte_length || observed_sha256 != entry.sha256 {
            return Err("a committed router fixture file differs from its manifest".to_owned());
        }
        manifest_files.push(json!({
            "path": entry.path,
            "byte_length": observed_length,
            "sha256": observed_sha256,
        }));
        payloads.insert(entry.path.clone(), bytes);
    }

    let generator_bytes = read_bounded_regular_file(
        fixture_root,
        &manifest.provenance.generator,
        MAX_MANIFEST_BYTES,
    )?;
    if sha256_bytes(&generator_bytes) != manifest.provenance.generator_sha256 {
        return Err("the router fixture generator differs from its manifest".to_owned());
    }

    let expected_bytes = payloads
        .get(&manifest.expected_results.path)
        .ok_or_else(|| "the router fixture expected results are absent".to_owned())?;
    let expected: RouterGoldenDocument =
        parse_unique_json(expected_bytes, "router expected results")?;
    validate_router_golden_document(&manifest, &expected)?;

    let tie_bytes = payloads
        .get("synthetic-tie.json")
        .ok_or_else(|| "the synthetic router tie fixture is absent".to_owned())?;
    let ties: RouterTieDocument = parse_unique_json(tie_bytes, "synthetic router tie fixture")?;
    validate_router_tie_document(&ties)?;

    let mut negative_cases = Vec::with_capacity(ROUTER_NEGATIVE_EXPECTATIONS.len());
    for (path, expected_category, expected_code, expected_surface) in ROUTER_NEGATIVE_EXPECTATIONS {
        let bytes = payloads
            .get(path)
            .ok_or_else(|| "a required negative router fixture is absent".to_owned())?;
        let negative: RouterNegativeDocument = parse_unique_json(bytes, "negative router fixture")?;
        validate_router_negative_document(
            &negative,
            expected_category,
            expected_code,
            expected_surface,
        )?;
        negative_cases.push(json!({
            "fixture": path,
            "fixture_id": negative.fixture_id,
            "category": negative.case.category,
            "validation_surface": negative.case.validation_surface,
            "expected_code": negative.case.expected_failure.code,
            "must_precede": negative.case.expected_failure.must_precede,
            "accepted_result": false,
            "router_runner_called": false,
            "validation_mode": "fixture_contract_validation",
            "mlx_executed": false,
            "mutation": negative.case.mutation,
            "status": "covered",
        }));
    }

    Ok(RouterFixtureBundle {
        manifest_sha256: sha256_bytes(&manifest_bytes),
        manifest_files,
        case_order: manifest
            .cases
            .iter()
            .map(|case| case.case_id.clone())
            .collect(),
        golden_cases: expected.cases,
        tie_cases: ties.cases,
        negative_cases,
    })
}

fn validate_router_fixture_manifest(manifest: &RouterFixtureManifestIndex) -> Result<(), String> {
    let expected_case_ids = [ROUTER_SINGLE_ROW_CASE_ID, ROUTER_TWO_ROW_CASE_ID];
    if manifest.schema != "pulsarmlx.fixture.router-manifest"
        || manifest.schema_version != "1.0.0"
        || manifest.fixture_id != ROUTER_FIXTURE_ID
        || manifest.provenance.kind != "synthetic_generated"
        || manifest.provenance.generator != "golden/generate.py"
        || !canonical_sha256(&manifest.provenance.generator_sha256)
        || manifest.provenance.generation_command
            != "python3 fixtures/research/router-v1/golden/generate.py --write"
        || manifest.provenance.independence.trim().is_empty()
        || !manifest.provenance.model_free
        || manifest.provenance.external_checkpoint_access_required
        || !manifest.provenance.redistributable
        || manifest.provenance.license != "MIT"
        || manifest.contract.contract_id != "qwen3moe-layer0-router-parity-v1"
        || manifest.contract.hidden_width != 2_048
        || manifest.contract.expert_count != 128
        || manifest.contract.top_k != 8
        || manifest.contract.weight_dtype != "float32"
        || manifest.contract.weight_byte_order != "little"
        || manifest.contract.weight_layout != "expert_major_rows_input_columns"
        || manifest.contract.tie_rule != "probability_descending_then_expert_id_ascending"
        || manifest.contract.normalization
            != "full_128_way_softmax_then_selected_probability_renormalization"
        || manifest.expected_results.path != "golden/expected_results.json"
        || manifest.expected_results.arithmetic != "scalar_float32"
        || !manifest.expected_results.independently_computed
        || !manifest.expected_results.complete_values
        || !manifest.hidden_state_fixture.is_object()
        || !manifest.weight_fixture.is_object()
        || !manifest.scope.is_object()
        || manifest.files.len() != ROUTER_FIXTURE_FILES.len()
        || manifest.cases.len() != expected_case_ids.len()
    {
        return Err("the router fixture manifest identity or contract is not admitted".to_owned());
    }
    for (index, (case, expected_id)) in manifest.cases.iter().zip(expected_case_ids).enumerate() {
        let rows = index + 1;
        if case.case_id != expected_id
            || case.expected_result_key != expected_id
            || case.hidden_shape != [rows as u64, 2_048]
            || case.hidden_row_ids.len() != rows
            || !canonical_sha256(&case.hidden_f32le_sha256)
        {
            return Err("the router fixture case inventory is not admitted".to_owned());
        }
    }
    Ok(())
}

fn validate_router_golden_document(
    manifest: &RouterFixtureManifestIndex,
    document: &RouterGoldenDocument,
) -> Result<(), String> {
    if document.schema != "pulsarmlx.fixture.router-expected-results"
        || document.schema_version != "1.0.0"
        || document.fixture_id != ROUTER_EXPECTED_RESULTS_ID
        || !document.contract.is_object()
        || document.provenance.as_str() != Some("synthetic_generated_model_free_independent_scalar")
        || document.cases.len() != manifest.cases.len()
    {
        return Err("the router expected-results identity is not admitted".to_owned());
    }
    for case in &manifest.cases {
        let golden = document
            .cases
            .get(&case.expected_result_key)
            .ok_or_else(|| "a router expected result is missing".to_owned())?;
        if golden.case_id != case.case_id
            || golden.hidden_shape != case.hidden_shape.map(|value| value as usize)
            || golden.hidden_row_ids != case.hidden_row_ids
            || golden.logits_shape != [golden.hidden_shape[0], 128]
            || golden.provenance != "synthetic_generated_model_free"
        {
            return Err("a router expected result contradicts its manifest case".to_owned());
        }
        let _ = output_from_router_values(
            &golden.case_id,
            golden.logits_shape,
            &golden.logits,
            &golden.full_softmax_probabilities,
            &golden.selected_expert_ids,
            &golden.selected_probabilities,
            &golden.normalized_weights,
            &golden.hashes,
        )?;
    }
    Ok(())
}

fn validate_router_tie_document(document: &RouterTieDocument) -> Result<(), String> {
    if document.schema != "pulsarmlx.fixture.router-synthetic-tie"
        || document.schema_version != "1.0.0"
        || document.fixture_id != ROUTER_SYNTHETIC_TIE_ID
        || document.contract
            != json!({
                "contract_id": "qwen3moe-layer0-router-parity-v1",
                "non_finite_policy": "reject",
                "normalization": "full_128_way_softmax_then_selected_probability_renormalization",
                "tie_rule": "probability_descending_then_expert_id_ascending",
            })
        || document.bounds
            != json!({
                "case_count": 2,
                "expert_count": 128,
                "maximum_fixture_bytes": 65_536,
                "maximum_rows_per_case": 1,
                "top_k": 8,
            })
        || document.provenance
            != json!({
                "evidence_level": "synthetic_tie_fixture_only",
                "external_checkpoint_access_required": false,
                "kind": "synthetic_generated",
                "model_free": true,
                "proves_real_checkpoint_routing": false,
            })
        || document.cases.len() != 2
        || document.cases[0].kind != "exact_tie"
        || document.cases[1].kind != "near_tie"
    {
        return Err("the synthetic router tie fixture identity is not admitted".to_owned());
    }
    Ok(())
}

fn validate_router_negative_document(
    document: &RouterNegativeDocument,
    category: &str,
    code: &str,
    validation_surface: &str,
) -> Result<(), String> {
    if document.schema != "pulsarmlx.fixture.router-negative-case"
        || document.schema_version != "1.0.0"
        || document.contract_id != "qwen3moe-layer0-router-parity-v1"
        || document.fixture_id.len() > 128
        || !document
            .fixture_id
            .starts_with("generated-qwen3moe-router-")
        || !document.bounds.is_object()
        || document.provenance.kind != "synthetic_generated_malformed"
        || document.provenance.evidence_level != "synthetic_negative_fixture_only"
        || !document.provenance.model_free
        || document.provenance.external_checkpoint_access_required
        || document.provenance.raw_model_or_tensor_bytes_committed
        || document.case.category != category
        || document.case.validation_surface != validation_surface
        || !document.case.mutation.is_object()
        || document.case.expected_failure.code != code
        || document.case.expected_failure.accepted_result
        || document.case.expected_failure.router_runner_called
        || document.case.expected_failure.must_precede != "before_router_mlx_array_construction"
    {
        return Err("a negative router fixture contract is not admitted".to_owned());
    }
    Ok(())
}

fn f32_rows(rows: &[Vec<f64>], label: &str) -> Result<Vec<Vec<f32>>, String> {
    rows.iter()
        .enumerate()
        .map(|(row_index, row)| {
            row.iter()
                .enumerate()
                .map(|(column_index, value)| {
                    let canonical = *value as f32;
                    if !value.is_finite()
                        || !canonical.is_finite()
                        || f64::from(canonical) != *value
                    {
                        return Err(format!(
                            "{label}[{row_index}][{column_index}] is not canonical finite F32"
                        ));
                    }
                    Ok(canonical)
                })
                .collect()
        })
        .collect()
}

fn flatten_f32(rows: &[Vec<f32>]) -> Vec<f32> {
    rows.iter().flatten().copied().collect()
}

fn selected_id_sha256(rows: &[Vec<u64>]) -> Result<String, String> {
    let mut digest = Sha256::new();
    for expert_id in rows.iter().flatten() {
        let value = u32::try_from(*expert_id)
            .map_err(|_| "a router expert ID is outside the bounded U32 range".to_owned())?;
        digest.update(value.to_le_bytes());
    }
    Ok(format!("{:x}", digest.finalize()))
}

fn float_output_bundle_sha256(output: &RouterOutput) -> String {
    let mut digest = Sha256::new();
    for value in output.logits() {
        digest.update(value.to_le_bytes());
    }
    for value in output.full_probabilities() {
        digest.update(value.to_le_bytes());
    }
    for value in output.selected_probabilities().iter().flatten() {
        digest.update(value.to_le_bytes());
    }
    for value in output.normalized_weights().iter().flatten() {
        digest.update(value.to_le_bytes());
    }
    format!("{:x}", digest.finalize())
}

#[allow(clippy::too_many_arguments)]
fn output_from_router_values(
    case_id: &str,
    logits_shape: [usize; 2],
    logits: &[Vec<f64>],
    probabilities: &[Vec<f64>],
    selected_ids: &[Vec<u64>],
    selected_probabilities: &[Vec<f64>],
    normalized_weights: &[Vec<f64>],
    hashes: &RouterGoldenHashes,
) -> Result<RouterOutput, String> {
    if logits_shape[0] == 0 || logits_shape[1] != 128 || logits.len() != logits_shape[0] {
        return Err("a router fixture has an invalid complete-output shape".to_owned());
    }
    let logits = f32_rows(logits, "router logits")?;
    let probabilities = f32_rows(probabilities, "router probabilities")?;
    let selected_probabilities = f32_rows(selected_probabilities, "selected probabilities")?;
    let normalized_weights = f32_rows(normalized_weights, "normalized weights")?;
    let output = RouterOutput::try_new(
        case_id,
        RouterCaseScope::SyntheticFixture,
        logits_shape[0],
        flatten_f32(&logits),
        flatten_f32(&probabilities),
        selected_ids.to_vec(),
        selected_probabilities,
        normalized_weights,
    )
    .map_err(|_| "a committed router output violates the bounded Rust contract".to_owned())?;
    if ![
        &hashes.logits_f32le_sha256,
        &hashes.full_softmax_probabilities_f32le_sha256,
        &hashes.selected_expert_ids_u32le_sha256,
        &hashes.selected_probabilities_f32le_sha256,
        &hashes.normalized_weights_f32le_sha256,
        &hashes.float_output_bundle_f32le_sha256,
    ]
    .iter()
    .all(|hash| canonical_sha256(hash))
        || output.logits_f32le_sha256() != hashes.logits_f32le_sha256
        || output.full_probabilities_f32le_sha256()
            != hashes.full_softmax_probabilities_f32le_sha256
        || selected_id_sha256(output.selected_expert_ids())?
            != hashes.selected_expert_ids_u32le_sha256
        || output.selected_probabilities_f32le_sha256()
            != hashes.selected_probabilities_f32le_sha256
        || output.normalized_weights_f32le_sha256() != hashes.normalized_weights_f32le_sha256
        || float_output_bundle_sha256(&output) != hashes.float_output_bundle_f32le_sha256
    {
        return Err("a committed router output differs from its canonical hashes".to_owned());
    }
    Ok(output)
}

fn output_from_worker_result(result: &RouterResult) -> Result<RouterOutput, String> {
    output_from_worker_result_with_scope(result, RouterCaseScope::SyntheticFixture)
}

fn output_from_worker_result_with_scope(
    result: &RouterResult,
    case_scope: RouterCaseScope,
) -> Result<RouterOutput, String> {
    let logits = f32_rows(result.logits(), "worker router logits")?;
    let probabilities = f32_rows(result.full_probabilities(), "worker router probabilities")?;
    let selected = f32_rows(
        result.selected_probabilities(),
        "worker selected probabilities",
    )?;
    let normalized = f32_rows(result.normalized_weights(), "worker normalized weights")?;
    let output = RouterOutput::try_new(
        result.router_case_id(),
        case_scope,
        usize::try_from(result.batch_size())
            .map_err(|_| "the worker router batch size is not representable".to_owned())?,
        flatten_f32(&logits),
        flatten_f32(&probabilities),
        result.selected_expert_ids().to_vec(),
        selected,
        normalized,
    )
    .map_err(|_| "the worker router output violates the bounded Rust contract".to_owned())?;
    if output.logits_f32le_sha256() != result.logits_f32le_sha256()
        || output.full_probabilities_f32le_sha256() != result.full_probabilities_f32le_sha256()
        || output.selected_probabilities_f32le_sha256()
            != result.selected_probabilities_f32le_sha256()
        || output.normalized_weights_f32le_sha256() != result.normalized_weights_f32le_sha256()
    {
        return Err("the worker router output differs from its protocol hashes".to_owned());
    }
    Ok(output)
}

// The real `RouterResult` adapter remains intentionally dormant until T083.
#[allow(dead_code)]
fn complete_router_output_sha256(output: &RouterOutput) -> Result<String, String> {
    let mut digest = Sha256::new();
    for value in output.logits() {
        digest.update(value.to_le_bytes());
    }
    for value in output.full_probabilities() {
        digest.update(value.to_le_bytes());
    }
    for expert_id in output.selected_expert_ids().iter().flatten() {
        digest.update(
            u32::try_from(*expert_id)
                .map_err(|_| "a router expert ID is outside the bounded U32 range".to_owned())?
                .to_le_bytes(),
        );
    }
    for value in output.selected_probabilities().iter().flatten() {
        digest.update(value.to_le_bytes());
    }
    for value in output.normalized_weights().iter().flatten() {
        digest.update(value.to_le_bytes());
    }
    Ok(format!("{:x}", digest.finalize()))
}

fn numeric_comparison_evidence(comparison: &RouterNumericComparison) -> Value {
    let first_mismatch = comparison.first_mismatch().map(|mismatch| {
        json!({
            "row_index": mismatch.row_index(),
            "column_index": mismatch.column_index(),
            "reference": mismatch.reference(),
            "candidate": mismatch.candidate(),
        })
    });
    json!({
        "compared_count": comparison.compared_count(),
        "mismatch_count": comparison.mismatch_count(),
        "first_mismatch": first_mismatch,
        "maximum_absolute_error": comparison.maximum_absolute_error(),
        "mean_absolute_error": comparison.mean_absolute_error(),
        "rmse": comparison.rmse(),
        "maximum_relative_error": comparison.maximum_relative_error(),
        "absolute_tolerance": comparison.tolerance().absolute(),
        "relative_tolerance": comparison.tolerance().relative(),
    })
}

fn router_comparison_evidence(comparison: &RouterOutputComparison) -> Value {
    json!({
        "logits": numeric_comparison_evidence(comparison.logits()),
        "full_probabilities": numeric_comparison_evidence(comparison.full_probabilities()),
        "selected_probabilities": numeric_comparison_evidence(comparison.selected_probabilities()),
        "normalized_weights": numeric_comparison_evidence(comparison.normalized_weights()),
        "id_mismatch_count": comparison.id_mismatch_count(),
        "order_mismatch_count": comparison.order_mismatch_count(),
        "passed": comparison.passed(),
    })
}

fn range_numeric_comparison_evidence(
    reference: &[f32],
    candidate: &[f32],
    row_count: usize,
    range_start: usize,
    range_end: usize,
    absolute_tolerance: f64,
    relative_tolerance: f64,
) -> Value {
    let mut compared_count = 0_usize;
    let mut mismatch_count = 0_usize;
    let mut first_mismatch = None;
    let mut maximum_absolute_error = 0.0_f64;
    let mut absolute_error_sum = 0.0_f64;
    let mut squared_error_sum = 0.0_f64;
    let mut maximum_relative_error = None::<f64>;
    for row_index in 0..row_count {
        for column_index in range_start..range_end {
            let index = row_index * 128 + column_index;
            let reference_value = f64::from(reference[index]);
            let candidate_value = f64::from(candidate[index]);
            let absolute_error = (candidate_value - reference_value).abs();
            let allowed_error = absolute_tolerance + relative_tolerance * reference_value.abs();
            compared_count += 1;
            maximum_absolute_error = maximum_absolute_error.max(absolute_error);
            absolute_error_sum += absolute_error;
            squared_error_sum += absolute_error * absolute_error;
            if reference_value != 0.0 {
                let relative_error = absolute_error / reference_value.abs();
                maximum_relative_error = Some(
                    maximum_relative_error
                        .map_or(relative_error, |current| current.max(relative_error)),
                );
            }
            if absolute_error > allowed_error {
                mismatch_count += 1;
                if first_mismatch.is_none() {
                    first_mismatch = Some(json!({
                        "row_index": row_index,
                        "column_index": column_index,
                        "reference": reference_value,
                        "candidate": candidate_value,
                    }));
                }
            }
        }
    }
    let count = compared_count as f64;
    json!({
        "compared_count": compared_count,
        "mismatch_count": mismatch_count,
        "first_mismatch": first_mismatch,
        "maximum_absolute_error": maximum_absolute_error,
        "mean_absolute_error": absolute_error_sum / count,
        "rmse": (squared_error_sum / count).sqrt(),
        "maximum_relative_error": maximum_relative_error,
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
    })
}

fn router_comparison_evidence_with_ranges(
    comparison: &RouterOutputComparison,
    reference: &RouterOutput,
    candidate: &RouterOutput,
) -> Value {
    let mut evidence = router_comparison_evidence(comparison);
    let ranges = [("0..16", 0_usize, 16_usize), ("64..80", 64, 80)];
    let range_evidence = ranges
        .into_iter()
        .map(|(label, start, end)| {
            let logits = range_numeric_comparison_evidence(
                reference.logits(),
                candidate.logits(),
                reference.row_count(),
                start,
                end,
                5.0e-4,
                5.0e-4,
            );
            let probabilities = range_numeric_comparison_evidence(
                reference.full_probabilities(),
                candidate.full_probabilities(),
                reference.row_count(),
                start,
                end,
                1.0e-6,
                1.0e-6,
            );
            let passed = logits["mismatch_count"] == 0 && probabilities["mismatch_count"] == 0;
            (
                label.to_owned(),
                json!({
                    "logits": logits,
                    "full_probabilities": probabilities,
                    "passed": passed,
                }),
            )
        })
        .collect::<Map<String, Value>>();
    evidence["expert_range_comparisons"] = Value::Object(range_evidence);
    evidence
}

fn router_memory_evidence(result: &RouterResult) -> Value {
    let memory = result.memory_gauges();
    json!({
        "mlx_active_bytes": memory.mlx_active_bytes(),
        "mlx_cache_bytes": memory.mlx_cache_bytes(),
        "mlx_peak_bytes": memory.mlx_peak_bytes(),
        "process_footprint_bytes": memory.process_footprint_bytes(),
        "process_footprint_source": memory.process_footprint_source(),
        "system_pressure": memory.system_pressure(),
        "reported_summed_total_bytes": memory.reported_summed_total_bytes(),
    })
}

fn router_positive_case_evidence(
    result: &RouterResult,
    comparison: &RouterOutputComparison,
) -> Value {
    json!({
        "backend": BACKEND_ID,
        "case_id": result.router_case_id(),
        "fixture_kind": "synthetic",
        "case_scope": "synthetic_fixture",
        "validation_mode": "mlx_gpu_execution_and_host_golden_comparison",
        "real_checkpoint_evidence": false,
        "requested_device": result.requested_device(),
        "selected_device": result.selected_device(),
        "fallback_used": result.fallback_used(),
        "evaluated": result.evaluated(),
        "synchronized": result.synchronized(),
        "operation": result.operation(),
        "batch_size": result.batch_size(),
        "hidden_width": result.hidden_width(),
        "expert_count": result.expert_count(),
        "top_k": result.top_k(),
        "output_dtype": result.output_dtype(),
        "selected_expert_ids": result.selected_expert_ids(),
        "hashes": {
            "logits_f32le_sha256": result.logits_f32le_sha256(),
            "full_probabilities_f32le_sha256": result.full_probabilities_f32le_sha256(),
            "selected_probabilities_f32le_sha256": result.selected_probabilities_f32le_sha256(),
            "normalized_weights_f32le_sha256": result.normalized_weights_f32le_sha256(),
        },
        "comparison": router_comparison_evidence(comparison),
        "memory_gauges": router_memory_evidence(result),
        "status": "passed",
    })
}

fn ensure_model_free_worker_descriptor() -> Result<(), String> {
    #[cfg(unix)]
    {
        let status = unsafe { libc::fcntl(MODEL_FILE_DESCRIPTOR, libc::F_GETFD) };
        if status != -1 || std::io::Error::last_os_error().raw_os_error() != Some(libc::EBADF) {
            return Err("the model-free worker descriptor boundary is not closed".to_owned());
        }
    }
    Ok(())
}

fn validate_tie_cases(bundle: &RouterFixtureBundle) -> Result<Vec<Value>, String> {
    let mut evidence = Vec::with_capacity(bundle.tie_cases.len());
    let expected = [
        (
            "generated-qwen3moe-router-exact-tie-v1",
            "exact_tie",
            7_u64,
            8_u64,
            "exact_f32_equal",
        ),
        (
            "generated-qwen3moe-router-near-tie-v1",
            "near_tie",
            8_u64,
            7_u64,
            "one_f32_ulp_logit_above",
        ),
    ];
    for (case, (case_id, kind, rank_8_id, rank_9_id, relation)) in
        bundle.tie_cases.iter().zip(expected)
    {
        if case.provenance != "synthetic_generated_model_free"
            || case.case_id != case_id
            || case.kind != kind
            || case.logits_shape != [1, 128]
            || case.cutoff.rank_8_expert_id != rank_8_id
            || case.cutoff.rank_9_expert_id != rank_9_id
            || case.cutoff.relation != relation
            || ![
                &case.cutoff.rank_8_logit_f32_bits,
                &case.cutoff.rank_9_logit_f32_bits,
                &case.cutoff.rank_8_probability_f32_bits,
                &case.cutoff.rank_9_probability_f32_bits,
            ]
            .iter()
            .all(|bits| bits.len() == 8 && bits.bytes().all(|byte| byte.is_ascii_hexdigit()))
        {
            return Err("a synthetic router tie case is not admitted".to_owned());
        }
        let output = output_from_router_values(
            &case.case_id,
            case.logits_shape,
            &case.logits,
            &case.full_softmax_probabilities,
            &case.selected_expert_ids,
            &case.selected_probabilities,
            &case.normalized_weights,
            &case.hashes,
        )?;
        let probability_row = output.full_probabilities();
        let logit_row = output.logits();
        let mut ranked_ids = (0..128_usize).collect::<Vec<_>>();
        ranked_ids.sort_by(|left, right| {
            probability_row[*right]
                .partial_cmp(&probability_row[*left])
                .expect("validated finite synthetic probabilities")
                .then_with(|| left.cmp(right))
        });
        let rank_8 = ranked_ids[7];
        let rank_9 = ranked_ids[8];
        if rank_8 as u64 != case.cutoff.rank_8_expert_id
            || rank_9 as u64 != case.cutoff.rank_9_expert_id
            || format!("{:08x}", logit_row[rank_8].to_bits()) != case.cutoff.rank_8_logit_f32_bits
            || format!("{:08x}", logit_row[rank_9].to_bits()) != case.cutoff.rank_9_logit_f32_bits
            || format!("{:08x}", probability_row[rank_8].to_bits())
                != case.cutoff.rank_8_probability_f32_bits
            || format!("{:08x}", probability_row[rank_9].to_bits())
                != case.cutoff.rank_9_probability_f32_bits
            || (case.kind == "exact_tie" && probability_row[rank_8] != probability_row[rank_9])
            || (case.kind == "near_tie" && probability_row[rank_8] <= probability_row[rank_9])
        {
            return Err("a synthetic router tie cutoff declaration is inconsistent".to_owned());
        }
        evidence.push(json!({
            "case_id": output.case_id(),
            "kind": case.kind,
            "fixture_kind": "synthetic",
            "case_scope": "synthetic_fixture",
            "validation_mode": "host_contract_validation",
            "mlx_executed": false,
            "real_checkpoint_evidence": false,
            "cutoff": {
                "rank_8_expert_id": case.cutoff.rank_8_expert_id,
                "rank_9_expert_id": case.cutoff.rank_9_expert_id,
                "relation": case.cutoff.relation,
            },
            "selected_expert_ids": output.selected_expert_ids(),
            "hashes": {
                "logits_f32le_sha256": output.logits_f32le_sha256(),
                "full_probabilities_f32le_sha256": output.full_probabilities_f32le_sha256(),
                "selected_probabilities_f32le_sha256": output.selected_probabilities_f32le_sha256(),
                "normalized_weights_f32le_sha256": output.normalized_weights_f32le_sha256(),
            },
            "status": "passed",
        }));
    }
    Ok(evidence)
}

fn execute_router_positive_cases(
    client: &mut WorkerClient,
    bundle: &RouterFixtureBundle,
    attempt: &mut RouterFixtureAttempt,
) -> Result<(), RetainedRouterFixtureFailure> {
    let hello = client.hello().clone();
    let operations = hello.capabilities().operations();
    if !operations.iter().any(|operation| operation == "run_router")
        || operations
            .iter()
            .any(|operation| operation == "run_model_slice")
    {
        return Err(retained_fixture_failure(
            "aborted",
            "worker_negotiation",
            "unsupported_operation",
            "the model-free worker capability boundary is not admitted",
        ));
    }
    attempt.runtime = Some(json!({
        "protocol": hello.protocol(),
        "worker_version": hello.worker_version(),
        "python_version": hello.python_version(),
        "python_arch": hello.python_arch(),
        "mlx_version": hello.mlx_version(),
        "macos_version": hello.macos_version(),
        "metal_available": hello.metal_available(),
        "gpu_count": hello.gpu_count(),
        "operations": operations,
        "model_operation_advertised": false,
    }));
    let health = client.health().map_err(|error| {
        retained_fixture_failure(
            "aborted",
            "worker_health",
            error.worker_code().unwrap_or("device_unavailable"),
            error.message(),
        )
    })?;
    if !health.ready() {
        return Err(retained_fixture_failure(
            "aborted",
            "worker_health",
            "device_unavailable",
            "the negotiated model-free MLX worker is not ready",
        ));
    }

    for case_id in &bundle.case_order {
        let request = RouterRequest::new(case_id, GPU_DEVICE).map_err(|error| {
            retained_fixture_failure(
                "failed",
                "router_request",
                error.worker_code().unwrap_or("malformed_request"),
                error.message(),
            )
        })?;
        let result = client.run_router(&request).map_err(|error| {
            retained_fixture_failure(
                "failed",
                "router_execution",
                error.worker_code().unwrap_or("evaluation_failed"),
                error.message(),
            )
        })?;
        let golden = bundle.golden_cases.get(case_id).ok_or_else(|| {
            retained_fixture_failure(
                "failed",
                "golden_comparison",
                "comparison_failed",
                "the committed golden router case is unavailable",
            )
        })?;
        let reference = output_from_router_values(
            &golden.case_id,
            golden.logits_shape,
            &golden.logits,
            &golden.full_softmax_probabilities,
            &golden.selected_expert_ids,
            &golden.selected_probabilities,
            &golden.normalized_weights,
            &golden.hashes,
        )
        .map_err(|message| {
            retained_fixture_failure("failed", "golden_comparison", "comparison_failed", message)
        })?;
        let candidate = output_from_worker_result(&result).map_err(|message| {
            retained_fixture_failure("failed", "worker_result", "comparison_failed", message)
        })?;
        let comparison = compare_router_outputs(
            &reference,
            &candidate,
            &RouterTolerancePolicy::contract_v1(),
        )
        .map_err(|error| {
            retained_fixture_failure("failed", "golden_comparison", error.code(), error.message())
        })?;
        if !comparison.passed() || !result.passed() {
            return Err(retained_fixture_failure(
                "failed",
                "golden_comparison",
                "comparison_failed",
                "the evaluated synthetic router output differs from its committed golden case",
            ));
        }
        attempt
            .positive_cases
            .push(router_positive_case_evidence(&result, &comparison));
    }
    Ok(())
}

fn cleanup_outcome_name(outcome: CleanupOutcome) -> &'static str {
    match outcome {
        CleanupOutcome::Graceful => "graceful",
        CleanupOutcome::ForcedTermination => "forced_termination",
        CleanupOutcome::Failed => "failed",
    }
}

fn run_planned_inspect_router(command: InspectRouterCommand) -> Result<(), String> {
    // Keep this pre-gate path lexical-only: the filesystem identity validator
    // above must not run until T074 authorizes resolving the checkpoint.
    let _parsed_paths = (command.model, command.evidence);
    Err("inspect-router is parsed but remains blocked until the notified T074 external-artifact admission; no checkpoint was accessed".to_owned())
}

fn run_planned_validate_router_fixtures(
    command: ValidateRouterFixturesCommand,
) -> Result<(), String> {
    validate_router_fixture_path_identities(&command)?;
    if fs::symlink_metadata(&command.evidence).is_ok() {
        return Err("the router fixture evidence destination already exists".to_owned());
    }

    let root = project_root();
    let mut attempt = RouterFixtureAttempt::new();
    let bundle = match load_router_fixture_bundle(&root, &command.manifest) {
        Ok(bundle) => {
            attempt.manifest_sha256 = Some(bundle.manifest_sha256.clone());
            attempt.manifest_files = bundle.manifest_files.clone();
            attempt.negative_cases = bundle.negative_cases.clone();
            match validate_tie_cases(&bundle) {
                Ok(tie_cases) => attempt.tie_cases = tie_cases,
                Err(message) => attempt.retain_failure(retained_fixture_failure(
                    "failed",
                    "synthetic_tie_validation",
                    "comparison_failed",
                    message,
                )),
            }
            Some(bundle)
        }
        Err(message) => {
            attempt.retain_failure(retained_fixture_failure(
                "failed",
                "manifest_admission",
                "comparison_failed",
                message,
            ));
            None
        }
    };

    if attempt.failure.is_none() {
        if let Err(message) = ensure_model_free_worker_descriptor() {
            attempt.retain_failure(retained_fixture_failure(
                "aborted",
                "model_free_boundary",
                "model_identity_mismatch",
                message,
            ));
        }
    }

    if attempt.failure.is_none() {
        let config = match worker_config(&root) {
            Ok(config) => Some(config.with_env("PULSARMLX_MODEL_GGUF", "")),
            Err(message) => {
                attempt.retain_failure(retained_fixture_failure(
                    "aborted",
                    "worker_configuration",
                    "device_unavailable",
                    message,
                ));
                None
            }
        };
        if let (Some(config), Some(bundle)) = (config, bundle.as_ref()) {
            match WorkerClient::spawn(config) {
                Ok(mut client) => {
                    let validation =
                        execute_router_positive_cases(&mut client, bundle, &mut attempt);
                    let cleanup = client.shutdown();
                    let cleanup_message = cleanup.error().map(|error| error.message().to_owned());
                    attempt.cleanup = json!({
                        "attempted": true,
                        "outcome": cleanup_outcome_name(cleanup.outcome()),
                        "exit_code": cleanup.exit_code(),
                        "message": cleanup_message,
                    });
                    if let Err(failure) = validation {
                        attempt.retain_failure(failure);
                    }
                    if cleanup.outcome() != CleanupOutcome::Graceful
                        || cleanup.exit_code() != Some(0)
                    {
                        attempt.retain_failure(retained_fixture_failure(
                            "aborted",
                            "worker_cleanup",
                            "evaluation_failed",
                            cleanup
                                .error()
                                .map(|error| error.message())
                                .unwrap_or("the model-free MLX worker did not shut down cleanly"),
                        ));
                    }
                }
                Err(error) => attempt.retain_failure(retained_fixture_failure(
                    "aborted",
                    "worker_spawn",
                    error.worker_code().unwrap_or("device_unavailable"),
                    error.message(),
                )),
            }
        }
    }

    let evidence = attempt.evidence();
    ensure_no_private_paths(&evidence)?;
    let encoded = serde_json::to_vec(&evidence)
        .map_err(|_| "the router fixture evidence could not be encoded".to_owned())?;
    if encoded.len() > ROUTER_FIXTURE_MAX_EVIDENCE_BYTES {
        return Err("the router fixture evidence exceeds its byte bound".to_owned());
    }
    validate_router_fixture_path_identities(&command)?;
    write_evidence_exclusive(&command.evidence, &evidence)?;

    if let Some(failure) = attempt.failure {
        return Err(format!(
            "validate-router-fixtures: {} evidence retained ({} at {})",
            failure.status, failure.code, failure.stage
        ));
    }
    println!("validate-router-fixtures: 2 evaluated MLX router cases passed; synthetic tie and negative contracts retained");
    Ok(())
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum OrchestratedRouterCase {
    SingleRow,
    TwoRow,
}

#[cfg_attr(not(test), allow(dead_code))]
impl OrchestratedRouterCase {
    const fn case_id(self) -> &'static str {
        match self {
            Self::SingleRow => ROUTER_REAL_SINGLE_ROW_CASE_ID,
            Self::TwoRow => ROUTER_REAL_TWO_ROW_CASE_ID,
        }
    }

    const fn benchmark_id(self) -> &'static str {
        match self {
            Self::SingleRow => ROUTER_MAJOR_SINGLE_ROW_BENCHMARK_ID,
            Self::TwoRow => ROUTER_MAJOR_TWO_ROW_BENCHMARK_ID,
        }
    }

    const fn row_count(self) -> usize {
        match self {
            Self::SingleRow => 1,
            Self::TwoRow => 2,
        }
    }
}

const ROUTER_CORRECTNESS_ORDER: [OrchestratedRouterCase; 2] = [
    OrchestratedRouterCase::SingleRow,
    OrchestratedRouterCase::TwoRow,
];
const ROUTER_COSTLY_ORDER: [OrchestratedRouterCase; 2] = [
    OrchestratedRouterCase::SingleRow,
    OrchestratedRouterCase::TwoRow,
];
const ROUTER_PRIMARY_MAJOR_ORDER: [(OrchestratedRouterCase, RouterTimingReplicationRole); 2] = [
    (
        OrchestratedRouterCase::SingleRow,
        RouterTimingReplicationRole::Primary,
    ),
    (
        OrchestratedRouterCase::TwoRow,
        RouterTimingReplicationRole::Primary,
    ),
];
const ROUTER_STAGE_DIAGNOSTIC_ORDER: [OrchestratedRouterCase; 2] = [
    OrchestratedRouterCase::SingleRow,
    OrchestratedRouterCase::TwoRow,
];
const ROUTER_CLEAN_MAJOR_ORDER: [(OrchestratedRouterCase, RouterTimingReplicationRole); 2] = [
    (
        OrchestratedRouterCase::SingleRow,
        RouterTimingReplicationRole::CleanProcessReplication,
    ),
    (
        OrchestratedRouterCase::TwoRow,
        RouterTimingReplicationRole::CleanProcessReplication,
    ),
];
#[cfg_attr(not(test), allow(dead_code))]
const ROUTER_SECOND_CORRECTNESS_ORDER: [OrchestratedRouterCase; 2] = [
    OrchestratedRouterCase::TwoRow,
    OrchestratedRouterCase::SingleRow,
];
#[cfg_attr(not(test), allow(dead_code))]
const ROUTER_SECOND_COSTLY_ORDER: [OrchestratedRouterCase; 2] = [
    OrchestratedRouterCase::TwoRow,
    OrchestratedRouterCase::SingleRow,
];
#[cfg_attr(not(test), allow(dead_code))]
const ROUTER_SECOND_PRIMARY_MAJOR_ORDER: [(OrchestratedRouterCase, RouterTimingReplicationRole);
    2] = [
    (
        OrchestratedRouterCase::TwoRow,
        RouterTimingReplicationRole::Primary,
    ),
    (
        OrchestratedRouterCase::SingleRow,
        RouterTimingReplicationRole::Primary,
    ),
];
#[cfg_attr(not(test), allow(dead_code))]
const ROUTER_SECOND_STAGE_DIAGNOSTIC_ORDER: [OrchestratedRouterCase; 2] = [
    OrchestratedRouterCase::TwoRow,
    OrchestratedRouterCase::SingleRow,
];
#[cfg_attr(not(test), allow(dead_code))]
const ROUTER_SECOND_CLEAN_MAJOR_ORDER: [(OrchestratedRouterCase, RouterTimingReplicationRole); 2] = [
    (
        OrchestratedRouterCase::TwoRow,
        RouterTimingReplicationRole::CleanProcessReplication,
    ),
    (
        OrchestratedRouterCase::SingleRow,
        RouterTimingReplicationRole::CleanProcessReplication,
    ),
];

#[derive(Debug, Clone, PartialEq)]
struct RouterCorrectnessAttempt {
    case_id: String,
    process_replication_id: String,
    logits_f32le_sha256: String,
    full_probabilities_f32le_sha256: String,
    selected_expert_ids: Vec<Vec<u64>>,
    selected_expert_ids_u32le_sha256: String,
    selected_probabilities_f32le_sha256: String,
    normalized_weights_f32le_sha256: String,
    complete_output_sha256: String,
    canonical_output: RouterOutput,
    comparison: Value,
    memory_gauges: Value,
    result_passed: bool,
    requested_device: String,
    selected_device: String,
    fallback_used: bool,
    evaluated: bool,
    synchronized: bool,
}

// The adapter is covered by the protocol/output contracts and becomes live at T083.
#[allow(dead_code)]
impl RouterCorrectnessAttempt {
    fn observation_role(attempt_index: usize) -> (&'static str, usize) {
        if attempt_index < ROUTER_CORRECTNESS_WARMUPS {
            ("warmup", attempt_index)
        } else {
            ("measurement", attempt_index - ROUTER_CORRECTNESS_WARMUPS)
        }
    }

    fn observation_id(&self, batch_id: &str, attempt_index: usize) -> String {
        let (observation_kind, run_index) = Self::observation_role(attempt_index);
        format!(
            "{batch_id}-{}-correctness-{observation_kind}-{run_index:02}",
            self.case_id,
        )
    }

    fn from_result(
        result: &RouterResult,
        reference: &RouterOutput,
        process_replication_id: impl Into<String>,
    ) -> Result<Self, String> {
        let output = output_from_worker_result_with_scope(result, RouterCaseScope::RealCheckpoint)?;
        let comparison =
            compare_router_outputs(reference, &output, &RouterTolerancePolicy::contract_v1())
                .map_err(|error| error.to_string())?;
        let comparison_evidence =
            router_comparison_evidence_with_ranges(&comparison, reference, &output);
        Ok(Self {
            case_id: result.router_case_id().to_owned(),
            process_replication_id: process_replication_id.into(),
            logits_f32le_sha256: output.logits_f32le_sha256().to_owned(),
            full_probabilities_f32le_sha256: output.full_probabilities_f32le_sha256().to_owned(),
            selected_expert_ids: output.selected_expert_ids().to_vec(),
            selected_expert_ids_u32le_sha256: selected_id_sha256(output.selected_expert_ids())?,
            selected_probabilities_f32le_sha256: output
                .selected_probabilities_f32le_sha256()
                .to_owned(),
            normalized_weights_f32le_sha256: output.normalized_weights_f32le_sha256().to_owned(),
            complete_output_sha256: complete_router_output_sha256(&output)?,
            canonical_output: output,
            comparison: comparison_evidence,
            memory_gauges: router_memory_evidence(result),
            result_passed: result.passed(),
            requested_device: result.requested_device().to_owned(),
            selected_device: result.selected_device().to_owned(),
            fallback_used: result.fallback_used(),
            evaluated: result.evaluated(),
            synchronized: result.synchronized(),
        })
    }

    fn passes_gate(&self, batch_id: &str, case: OrchestratedRouterCase) -> bool {
        let selected_ids_are_valid = self.selected_expert_ids.len() == case.row_count()
            && self.selected_expert_ids.iter().all(|row| {
                row.len() == 8
                    && row.iter().copied().collect::<BTreeSet<_>>().len() == 8
                    && row.iter().all(|expert_id| *expert_id < 128)
            });
        [
            &self.logits_f32le_sha256,
            &self.full_probabilities_f32le_sha256,
            &self.selected_expert_ids_u32le_sha256,
            &self.selected_probabilities_f32le_sha256,
            &self.normalized_weights_f32le_sha256,
            &self.complete_output_sha256,
        ]
        .into_iter()
        .all(|hash| canonical_sha256(hash))
            && selected_ids_are_valid
            && self.case_id == case.case_id()
            && self.process_replication_id == correctness_process_identity(batch_id)
            && self.canonical_output.case_scope() == RouterCaseScope::RealCheckpoint
            && self.canonical_output.case_id() == self.case_id
            && self.canonical_output.row_count() == case.row_count()
            && self.canonical_output.logits_f32le_sha256() == self.logits_f32le_sha256
            && self.canonical_output.full_probabilities_f32le_sha256()
                == self.full_probabilities_f32le_sha256
            && self.canonical_output.selected_expert_ids() == self.selected_expert_ids
            && selected_id_sha256(self.canonical_output.selected_expert_ids()).as_deref()
                == Ok(self.selected_expert_ids_u32le_sha256.as_str())
            && self.canonical_output.selected_probabilities_f32le_sha256()
                == self.selected_probabilities_f32le_sha256
            && self.canonical_output.normalized_weights_f32le_sha256()
                == self.normalized_weights_f32le_sha256
            && complete_router_output_sha256(&self.canonical_output).as_deref()
                == Ok(self.complete_output_sha256.as_str())
            && passing_router_comparison_evidence(&self.comparison, case.row_count())
            && valid_router_memory_evidence(&self.memory_gauges)
            && self.result_passed
            && self.requested_device == GPU_DEVICE
            && self.selected_device == GPU_DEVICE
            && !self.fallback_used
            && self.evaluated
            && self.synchronized
    }

    fn repeat_identity_matches(&self, other: &Self) -> bool {
        self.case_id == other.case_id
            && self.process_replication_id == other.process_replication_id
            && self.logits_f32le_sha256 == other.logits_f32le_sha256
            && self.full_probabilities_f32le_sha256 == other.full_probabilities_f32le_sha256
            && self.selected_expert_ids == other.selected_expert_ids
            && self.selected_expert_ids_u32le_sha256 == other.selected_expert_ids_u32le_sha256
            && self.selected_probabilities_f32le_sha256 == other.selected_probabilities_f32le_sha256
            && self.normalized_weights_f32le_sha256 == other.normalized_weights_f32le_sha256
            && self.complete_output_sha256 == other.complete_output_sha256
            && self.canonical_output == other.canonical_output
    }

    fn evidence(&self, batch_id: &str, attempt_index: usize) -> Value {
        let (observation_kind, run_index) = Self::observation_role(attempt_index);
        let passed = self.passes_gate(
            batch_id,
            match self.case_id.as_str() {
                ROUTER_REAL_SINGLE_ROW_CASE_ID => OrchestratedRouterCase::SingleRow,
                ROUTER_REAL_TWO_ROW_CASE_ID => OrchestratedRouterCase::TwoRow,
                _ => return json!({"status": "failed", "code": "invalid_case_identity"}),
            },
        );
        let failure = (!passed).then(|| {
            json!({
                "code": "comparison_failed",
                "stage": "correctness_gate",
                "message": "the retained correctness attempt did not satisfy the frozen gate"
            })
        });
        json!({
            "backend": BACKEND_ID,
            "attempt_id": self.observation_id(batch_id, attempt_index),
            "attempt_index": attempt_index,
            "observation_kind": observation_kind,
            "run_index": run_index,
            "case_id": self.case_id,
            "process_replication_id": self.process_replication_id,
            "logits_f32le_sha256": self.logits_f32le_sha256,
            "full_probabilities_f32le_sha256": self.full_probabilities_f32le_sha256,
            "selected_expert_ids": self.selected_expert_ids,
            "selected_expert_ids_u32le_sha256": self.selected_expert_ids_u32le_sha256,
            "selected_probabilities_f32le_sha256": self.selected_probabilities_f32le_sha256,
            "normalized_weights_f32le_sha256": self.normalized_weights_f32le_sha256,
            "complete_output_sha256": self.complete_output_sha256,
            "comparison": self.comparison,
            "memory_gauges": self.memory_gauges,
            "result_passed": self.result_passed,
            "requested_device": self.requested_device,
            "selected_device": self.selected_device,
            "fallback_used": self.fallback_used,
            "evaluated": self.evaluated,
            "synchronized": self.synchronized,
            "status": if passed { "passed" } else { "failed" },
            "failure": failure,
            "passed": passed,
        })
    }
}

fn valid_router_memory_evidence(memory: &Value) -> bool {
    let Some(fields) = memory.as_object() else {
        return false;
    };
    let exact_fields = [
        "mlx_active_bytes",
        "mlx_cache_bytes",
        "mlx_peak_bytes",
        "process_footprint_bytes",
        "process_footprint_source",
        "system_pressure",
        "reported_summed_total_bytes",
    ];
    if fields.len() != exact_fields.len()
        || exact_fields
            .iter()
            .any(|field| !fields.contains_key(*field))
        || !memory["reported_summed_total_bytes"].is_null()
        || ensure_no_private_paths(memory).is_err()
    {
        return false;
    }
    let optional_u64 = |field: &str| memory[field].is_null() || memory[field].as_u64().is_some();
    if ![
        "mlx_active_bytes",
        "mlx_cache_bytes",
        "mlx_peak_bytes",
        "process_footprint_bytes",
    ]
    .into_iter()
    .all(optional_u64)
    {
        return false;
    }
    if let (Some(active), Some(peak)) = (
        memory["mlx_active_bytes"].as_u64(),
        memory["mlx_peak_bytes"].as_u64(),
    ) {
        if peak < active {
            return false;
        }
    }
    let footprint_pair = (
        memory["process_footprint_bytes"].as_u64(),
        memory["process_footprint_source"].as_str(),
    );
    if !matches!(footprint_pair, (Some(_), Some(_)) | (None, None)) {
        return false;
    }
    ["process_footprint_source", "system_pressure"]
        .into_iter()
        .all(|field| {
            memory[field].is_null()
                || memory[field]
                    .as_str()
                    .is_some_and(stable_orchestration_identifier)
        })
}

fn passing_router_comparison_evidence(comparison: &Value, row_count: usize) -> bool {
    let Some(root) = comparison.as_object() else {
        return false;
    };
    if root.len() != 8
        || comparison["passed"] != true
        || comparison["id_mismatch_count"].as_u64() != Some(0)
        || comparison["order_mismatch_count"].as_u64() != Some(0)
    {
        return false;
    }
    let numeric_passes = |value: &Value, compared_count: usize, absolute: f64, relative: f64| {
        let Some(numeric) = value.as_object() else {
            return false;
        };
        let nonnegative_finite = |field: &str| {
            value[field]
                .as_f64()
                .is_some_and(|metric| metric.is_finite() && metric >= 0.0)
        };
        numeric.len() == 9
            && value["compared_count"].as_u64() == u64::try_from(compared_count).ok()
            && value["mismatch_count"].as_u64() == Some(0)
            && value["first_mismatch"].is_null()
            && value["absolute_tolerance"].as_f64() == Some(absolute)
            && value["relative_tolerance"].as_f64() == Some(relative)
            && nonnegative_finite("maximum_absolute_error")
            && nonnegative_finite("mean_absolute_error")
            && nonnegative_finite("rmse")
            && (value["maximum_relative_error"].is_null()
                || nonnegative_finite("maximum_relative_error"))
    };
    let whole_checks = [
        ("logits", row_count * 128, 5.0e-4, 5.0e-4),
        ("full_probabilities", row_count * 128, 1.0e-6, 1.0e-6),
        ("selected_probabilities", row_count * 8, 1.0e-6, 1.0e-6),
        ("normalized_weights", row_count * 8, 1.0e-6, 1.0e-6),
    ];
    let whole_passes = whole_checks
        .into_iter()
        .all(|(name, count, absolute, relative)| {
            numeric_passes(&comparison[name], count, absolute, relative)
        });
    let Some(ranges) = comparison["expert_range_comparisons"].as_object() else {
        return false;
    };
    let ranges_pass = ranges.len() == 2
        && ["0..16", "64..80"].into_iter().all(|range| {
            comparison["expert_range_comparisons"][range]["passed"] == true
                && comparison["expert_range_comparisons"][range]
                    .as_object()
                    .is_some_and(|fields| fields.len() == 3)
                && numeric_passes(
                    &comparison["expert_range_comparisons"][range]["logits"],
                    row_count * 16,
                    5.0e-4,
                    5.0e-4,
                )
                && numeric_passes(
                    &comparison["expert_range_comparisons"][range]["full_probabilities"],
                    row_count * 16,
                    1.0e-6,
                    1.0e-6,
                )
        });
    whole_passes && ranges_pass
}

#[derive(Debug, Clone, PartialEq)]
struct RouterCorrectnessGate {
    batch_id: String,
    case: OrchestratedRouterCase,
    complete_output_sha256: String,
    attempts: Vec<RouterCorrectnessAttempt>,
}

#[cfg_attr(not(test), allow(dead_code))]
impl RouterCorrectnessGate {
    fn try_new(
        batch_id: &str,
        case: OrchestratedRouterCase,
        attempts: Vec<RouterCorrectnessAttempt>,
    ) -> Result<Self, String> {
        if attempts.len() != ROUTER_CORRECTNESS_ATTEMPTS {
            return Err(
                "router correctness requires exactly five retained warmups and ten retained measurements"
                    .to_owned(),
            );
        }
        let expected_case_id = case.case_id();
        let measured_attempts = &attempts[ROUTER_CORRECTNESS_WARMUPS..];
        let first_hash = measured_attempts
            .first()
            .map(|attempt| attempt.complete_output_sha256.as_str())
            .ok_or_else(|| "router correctness attempts are unavailable".to_owned())?;
        let first = measured_attempts
            .first()
            .ok_or_else(|| "router correctness attempts are unavailable".to_owned())?;
        if !canonical_sha256(first_hash)
            || expected_case_id != first.case_id
            || attempts
                .iter()
                .any(|attempt| !attempt.passes_gate(batch_id, case))
            || measured_attempts
                .iter()
                .any(|attempt| !attempt.repeat_identity_matches(first))
        {
            return Err(
                "router correctness attempts do not establish passing warmups and ten identical evaluated GPU measurements"
                    .to_owned(),
            );
        }
        Ok(Self {
            batch_id: batch_id.to_owned(),
            case,
            complete_output_sha256: first_hash.to_owned(),
            attempts,
        })
    }

    fn evidence(&self) -> Value {
        let attempts = self
            .attempts
            .iter()
            .enumerate()
            .map(|(attempt_index, attempt)| attempt.evidence(&self.batch_id, attempt_index))
            .collect::<Vec<_>>();
        json!({
            "batch_id": self.batch_id,
            "case_id": self.case.case_id(),
            "attempt_count": self.attempts.len(),
            "warmup_count": ROUTER_CORRECTNESS_WARMUPS,
            "measurement_count": ROUTER_CORRECTNESS_REPETITIONS,
            "complete_output_sha256": self.complete_output_sha256,
            "canonical_output": canonical_router_output_evidence(
                &self.attempts[ROUTER_CORRECTNESS_WARMUPS].canonical_output,
            ),
            "requested_device": GPU_DEVICE,
            "selected_device": GPU_DEVICE,
            "fallback_used": false,
            "evaluated": true,
            "synchronized": true,
            "comparison_passed": true,
            "passed": true,
            "attempts": attempts,
        })
    }
}

fn canonical_router_output_evidence(output: &RouterOutput) -> Value {
    json!({
        "case_id": output.case_id(),
        "case_scope": "real_checkpoint",
        "row_count": output.row_count(),
        "logits_shape": output.logits_shape(),
        "logits": output.logits(),
        "logits_f32le_sha256": output.logits_f32le_sha256(),
        "full_probabilities_shape": output.full_probabilities_shape(),
        "full_probabilities": output.full_probabilities(),
        "full_probabilities_f32le_sha256": output.full_probabilities_f32le_sha256(),
        "selected_expert_ids": output.selected_expert_ids(),
        "selected_expert_ids_u32le_sha256": selected_id_sha256(output.selected_expert_ids())
            .expect("validated bounded expert IDs have a canonical hash"),
        "selected_probabilities": output.selected_probabilities(),
        "selected_probabilities_f32le_sha256": output.selected_probabilities_f32le_sha256(),
        "normalized_weights": output.normalized_weights(),
        "normalized_weights_f32le_sha256": output.normalized_weights_f32le_sha256(),
        "complete_output_sha256": complete_router_output_sha256(output)
            .expect("validated bounded router output has a canonical hash"),
    })
}

#[derive(Debug, Clone, PartialEq)]
enum RouterLaterBatchState {
    Pending,
    Recorded(Box<RouterRecordedBatch>),
    Failed(Box<RouterFailedBatch>),
    Unavailable { reason: String },
}

#[derive(Debug, Clone, PartialEq)]
struct RouterRecordedBatch {
    batch_id: String,
    ordered_observations: Vec<RouterOrderedObservation>,
    primary_first_process_series: Vec<RouterTimingSeries>,
    correctness_gates: Vec<RouterCorrectnessGate>,
    costly_series: Vec<RouterTimingSeries>,
    primary_major_series: Vec<RouterTimingSeries>,
    stage_diagnostic_series: Vec<RouterTimingSeries>,
    clean_first_process_series: Vec<RouterTimingSeries>,
    clean_major_series: Vec<RouterTimingSeries>,
}

#[derive(Debug, Clone, PartialEq)]
struct RouterFailedBatch {
    batch_id: String,
    candidate: Box<RouterBenchmarkOrchestrator>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct RouterOrderedObservation {
    global_order_index: usize,
    observation_id: String,
    case_id: String,
    process_replication_id: String,
    schedule_step: &'static str,
    source_kind: &'static str,
    observation_kind: &'static str,
    run_index: usize,
    source_status: &'static str,
    orchestration_status: &'static str,
    identity_duplicate: bool,
}

impl RouterOrderedObservation {
    fn evidence(&self, batch_id: &str) -> Value {
        let mut evidence = json!({
            "global_order_index": self.global_order_index,
            "observation_id": self.observation_id,
            "case_id": self.case_id,
            "batch_id": batch_id,
            "process_replication_id": self.process_replication_id,
            "schedule_step": self.schedule_step,
            "source_kind": self.source_kind,
            "observation_kind": self.observation_kind,
            "run_index": self.run_index,
            "status": self.source_status,
            "orchestration_status": self.orchestration_status,
        });
        if self.identity_duplicate {
            evidence["identity_duplicate"] = json!(true);
        }
        evidence
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum RouterBatchOrder {
    SingleRowFirst,
    TwoRowFirst,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[cfg_attr(not(test), allow(dead_code))]
enum RouterSecondBatchUnavailableReason {
    QuietWindowUnavailable,
    ResourceAdmissionUnavailable,
    ThermalOrPowerStateUnavailable,
    ExternalInterferenceObserved,
}

impl RouterSecondBatchUnavailableReason {
    const fn public_reason(self) -> &'static str {
        match self {
            Self::QuietWindowUnavailable => {
                "the later independent collection window was unavailable"
            }
            Self::ResourceAdmissionUnavailable => {
                "the later batch did not pass the frozen resource-admission gate"
            }
            Self::ThermalOrPowerStateUnavailable => {
                "the later batch did not match the admitted thermal or power state"
            }
            Self::ExternalInterferenceObserved => {
                "the later batch was unavailable because external interference was observed"
            }
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
struct RouterBenchmarkOrchestrator {
    batch_id: String,
    batch_order: RouterBatchOrder,
    ordered_observations: Vec<RouterOrderedObservation>,
    primary_first_process_series: Vec<RouterTimingSeries>,
    correctness_gates: Vec<RouterCorrectnessGate>,
    pending_correctness_attempts: Vec<RouterCorrectnessAttempt>,
    correctness_failed: bool,
    timing_failed: bool,
    terminal_failure: Option<RouterOrchestrationFailure>,
    costly_series: Vec<RouterTimingSeries>,
    primary_major_series: Vec<RouterTimingSeries>,
    stage_diagnostic_series: Vec<RouterTimingSeries>,
    clean_first_process_series: Vec<RouterTimingSeries>,
    clean_major_series: Vec<RouterTimingSeries>,
    rejected_timing_series: Vec<RouterRejectedTimingSeries>,
    later_batch: RouterLaterBatchState,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct RouterOrchestrationFailure {
    code: String,
    stage: String,
    message: String,
}

#[derive(Debug, Clone, PartialEq)]
struct RouterRejectedTimingSeries {
    series: RouterTimingSeries,
    failure: RouterOrchestrationFailure,
}

impl RouterOrchestrationFailure {
    fn comparison(stage: &str, error: &str) -> Self {
        Self {
            code: "comparison_failed".to_owned(),
            stage: "orchestration".to_owned(),
            message: format!("{stage}: {error}"),
        }
    }

    fn from_timing_series(stage: &str, series: &RouterTimingSeries, error: &str) -> Self {
        series
            .raw_timing_observations()
            .iter()
            .find_map(|observation| observation.failure())
            .map_or_else(
                || Self::comparison(stage, error),
                |failure| Self {
                    code: failure.code().to_owned(),
                    stage: failure.stage().to_owned(),
                    message: failure.message().to_owned(),
                },
            )
    }

    fn evidence(&self) -> Value {
        json!({
            "code": self.code,
            "stage": self.stage,
            "message": self.message,
        })
    }
}

type RouterSecondBatchCandidate = RouterBenchmarkOrchestrator;

// T066 freezes and unit-tests this state machine before the T083 execution
// gate may connect it to a real checkpoint and worker lifecycle.
#[cfg_attr(not(test), allow(dead_code))]
impl RouterBenchmarkOrchestrator {
    fn new() -> Self {
        Self::new_batch(
            ROUTER_PRIMARY_BATCH_ID.to_owned(),
            RouterBatchOrder::SingleRowFirst,
        )
    }

    fn new_second(batch_id: impl Into<String>) -> Result<Self, String> {
        let batch_id = batch_id.into();
        if batch_id == ROUTER_PRIMARY_BATCH_ID || !stable_orchestration_identifier(&batch_id) {
            return Err("later router batch identity is invalid or reused".to_owned());
        }
        Ok(Self::new_batch(batch_id, RouterBatchOrder::TwoRowFirst))
    }

    fn new_batch(batch_id: String, batch_order: RouterBatchOrder) -> Self {
        Self {
            batch_id,
            batch_order,
            ordered_observations: Vec::new(),
            primary_first_process_series: Vec::with_capacity(ROUTER_FIRST_PROCESS_REPETITIONS),
            correctness_gates: Vec::with_capacity(ROUTER_CORRECTNESS_ORDER.len()),
            pending_correctness_attempts: Vec::with_capacity(ROUTER_CORRECTNESS_ATTEMPTS),
            correctness_failed: false,
            timing_failed: false,
            terminal_failure: None,
            costly_series: Vec::with_capacity(ROUTER_COSTLY_ORDER.len()),
            primary_major_series: Vec::with_capacity(ROUTER_PRIMARY_MAJOR_ORDER.len()),
            stage_diagnostic_series: Vec::with_capacity(ROUTER_STAGE_DIAGNOSTIC_ORDER.len()),
            clean_first_process_series: Vec::with_capacity(ROUTER_CLEAN_MAJOR_ORDER.len()),
            clean_major_series: Vec::with_capacity(ROUTER_CLEAN_MAJOR_ORDER.len()),
            rejected_timing_series: Vec::new(),
            later_batch: RouterLaterBatchState::Pending,
        }
    }

    const fn correctness_order(&self) -> [OrchestratedRouterCase; 2] {
        match self.batch_order {
            RouterBatchOrder::SingleRowFirst => ROUTER_CORRECTNESS_ORDER,
            RouterBatchOrder::TwoRowFirst => ROUTER_SECOND_CORRECTNESS_ORDER,
        }
    }

    const fn costly_order(&self) -> [OrchestratedRouterCase; 2] {
        match self.batch_order {
            RouterBatchOrder::SingleRowFirst => ROUTER_COSTLY_ORDER,
            RouterBatchOrder::TwoRowFirst => ROUTER_SECOND_COSTLY_ORDER,
        }
    }

    const fn primary_major_order(
        &self,
    ) -> [(OrchestratedRouterCase, RouterTimingReplicationRole); 2] {
        match self.batch_order {
            RouterBatchOrder::SingleRowFirst => ROUTER_PRIMARY_MAJOR_ORDER,
            RouterBatchOrder::TwoRowFirst => ROUTER_SECOND_PRIMARY_MAJOR_ORDER,
        }
    }

    const fn stage_diagnostic_order(&self) -> [OrchestratedRouterCase; 2] {
        match self.batch_order {
            RouterBatchOrder::SingleRowFirst => ROUTER_STAGE_DIAGNOSTIC_ORDER,
            RouterBatchOrder::TwoRowFirst => ROUTER_SECOND_STAGE_DIAGNOSTIC_ORDER,
        }
    }

    const fn clean_major_order(
        &self,
    ) -> [(OrchestratedRouterCase, RouterTimingReplicationRole); 2] {
        match self.batch_order {
            RouterBatchOrder::SingleRowFirst => ROUTER_CLEAN_MAJOR_ORDER,
            RouterBatchOrder::TwoRowFirst => ROUTER_SECOND_CLEAN_MAJOR_ORDER,
        }
    }

    fn next_step(&self) -> &'static str {
        if self.correctness_failed || self.timing_failed {
            return "failed_stop_condition";
        }
        let correctness_order = self.correctness_order();
        if self.correctness_gates.len() < correctness_order.len() {
            return match correctness_order[self.correctness_gates.len()] {
                OrchestratedRouterCase::SingleRow => "single_row_correctness",
                OrchestratedRouterCase::TwoRow => "two_row_correctness",
            };
        }
        if self.primary_first_process_series.len() < ROUTER_FIRST_PROCESS_REPETITIONS {
            return "primary_first_process_os_cache_uncontrolled";
        }
        let costly_order = self.costly_order();
        if self.costly_series.len() < costly_order.len() {
            return match costly_order[self.costly_series.len()] {
                OrchestratedRouterCase::SingleRow => "single_row_costly_real",
                OrchestratedRouterCase::TwoRow => "two_row_costly_real",
            };
        }
        let primary_major_order = self.primary_major_order();
        if self.primary_major_series.len() < primary_major_order.len() {
            let (case, role) = primary_major_order[self.primary_major_series.len()];
            return match (case, role) {
                (OrchestratedRouterCase::SingleRow, RouterTimingReplicationRole::Primary) => {
                    "single_row_primary_major"
                }
                (OrchestratedRouterCase::TwoRow, RouterTimingReplicationRole::Primary) => {
                    "two_row_primary_major"
                }
                (_, RouterTimingReplicationRole::CleanProcessReplication) => {
                    unreachable!("primary major order contains only primary series")
                }
            };
        }
        let stage_diagnostic_order = self.stage_diagnostic_order();
        if self.stage_diagnostic_series.len() < stage_diagnostic_order.len() {
            return match stage_diagnostic_order[self.stage_diagnostic_series.len()] {
                OrchestratedRouterCase::SingleRow => "single_row_stage_diagnostic",
                OrchestratedRouterCase::TwoRow => "two_row_stage_diagnostic",
            };
        }
        let clean_major_order = self.clean_major_order();
        if self.clean_major_series.len() < clean_major_order.len() {
            let current = clean_major_order[self.clean_major_series.len()];
            let required_first_process_count =
                (self.clean_major_series.len() + 1) * ROUTER_FIRST_PROCESS_REPETITIONS;
            if self.clean_first_process_series.len() < required_first_process_count {
                return match current.0 {
                    OrchestratedRouterCase::SingleRow => {
                        "single_row_clean_first_process_os_cache_uncontrolled"
                    }
                    OrchestratedRouterCase::TwoRow => {
                        "two_row_clean_first_process_os_cache_uncontrolled"
                    }
                };
            }
            return match current {
                (
                    OrchestratedRouterCase::SingleRow,
                    RouterTimingReplicationRole::CleanProcessReplication,
                ) => "single_row_clean_process_major",
                (
                    OrchestratedRouterCase::TwoRow,
                    RouterTimingReplicationRole::CleanProcessReplication,
                ) => "two_row_clean_process_major",
                (_, RouterTimingReplicationRole::Primary) => {
                    unreachable!("clean major order contains only clean replications")
                }
            };
        }
        if self.batch_order == RouterBatchOrder::TwoRowFirst {
            return "batch_complete";
        }
        match self.later_batch {
            RouterLaterBatchState::Pending => "later_batch_or_unavailable_reason",
            RouterLaterBatchState::Recorded(_)
            | RouterLaterBatchState::Failed(_)
            | RouterLaterBatchState::Unavailable { .. } => "complete",
        }
    }

    fn ensure_active(&self) -> Result<(), String> {
        if self.correctness_failed || self.timing_failed {
            return Err(
                "router orchestration already reached a retained stop condition".to_owned(),
            );
        }
        Ok(())
    }

    fn append_ordered_observation(&mut self, mut observation: RouterOrderedObservation) {
        observation.global_order_index = self.ordered_observations.len();
        observation.identity_duplicate = self
            .ordered_observations
            .iter()
            .any(|existing| existing.observation_id == observation.observation_id);
        self.ordered_observations.push(observation);
    }

    fn append_correctness_observation(
        &mut self,
        schedule_step: &'static str,
        attempt: &RouterCorrectnessAttempt,
        attempt_index: usize,
        source_passed: bool,
        accepted: bool,
    ) {
        let (observation_kind, run_index) =
            RouterCorrectnessAttempt::observation_role(attempt_index);
        self.append_ordered_observation(RouterOrderedObservation {
            global_order_index: 0,
            observation_id: attempt.observation_id(&self.batch_id, attempt_index),
            case_id: attempt.case_id.clone(),
            process_replication_id: attempt.process_replication_id.clone(),
            schedule_step,
            source_kind: "correctness_attempt",
            observation_kind,
            run_index,
            source_status: if source_passed { "passed" } else { "failed" },
            orchestration_status: if accepted { "accepted" } else { "rejected" },
            identity_duplicate: false,
        });
    }

    fn append_timing_observations(
        &mut self,
        schedule_step: &'static str,
        series: &RouterTimingSeries,
        accepted: bool,
    ) {
        for observation in series.raw_timing_observations() {
            self.append_ordered_observation(RouterOrderedObservation {
                global_order_index: 0,
                observation_id: observation.observation_id().to_owned(),
                case_id: series.case_id().to_owned(),
                process_replication_id: observation.process_replication_id().to_owned(),
                schedule_step,
                source_kind: "timing_series",
                observation_kind: observation.observation_kind().as_str(),
                run_index: observation.run_index(),
                source_status: observation.status().as_str(),
                orchestration_status: if accepted { "accepted" } else { "rejected" },
                identity_duplicate: false,
            });
        }
    }

    fn mark_last_observations_rejected(&mut self, count: usize) {
        let start = self.ordered_observations.len().saturating_sub(count);
        for observation in &mut self.ordered_observations[start..] {
            observation.orchestration_status = "rejected";
        }
    }

    fn retain_timing_failure(&mut self, stage: &str, error: String) -> Result<(), String> {
        let failure = RouterOrchestrationFailure::comparison(stage, &error);
        self.retain_failure_record(failure, error)
    }

    fn retain_failure_record(
        &mut self,
        failure: RouterOrchestrationFailure,
        error: String,
    ) -> Result<(), String> {
        self.timing_failed = true;
        self.terminal_failure = Some(failure);
        Err(error)
    }

    fn reject_timing_series(
        &mut self,
        stage: &'static str,
        series: RouterTimingSeries,
        error: String,
    ) -> Result<(), String> {
        let failure = RouterOrchestrationFailure::comparison(stage, &error);
        self.append_timing_observations(stage, &series, false);
        self.rejected_timing_series
            .push(RouterRejectedTimingSeries {
                series,
                failure: failure.clone(),
            });
        self.timing_failed = true;
        self.terminal_failure = Some(failure);
        Err(error)
    }

    fn retain_correctness_failure(&mut self, error: String) -> Result<(), String> {
        self.correctness_failed = true;
        self.terminal_failure = Some(RouterOrchestrationFailure {
            code: "comparison_failed".to_owned(),
            stage: "correctness_gate".to_owned(),
            message: error.clone(),
        });
        Err(error)
    }

    fn record_primary_first_process_series(
        &mut self,
        series: RouterTimingSeries,
    ) -> Result<(), String> {
        self.ensure_active()?;
        if self.correctness_gates.len() != self.correctness_order().len() {
            return self.reject_timing_series(
                "primary_first_process",
                series,
                "primary first-process timing is blocked until correctness passes".to_owned(),
            );
        }
        if self.primary_first_process_series.len() >= ROUTER_FIRST_PROCESS_REPETITIONS
            || !self.costly_series.is_empty()
            || !self.primary_major_series.is_empty()
        {
            return self.reject_timing_series(
                "primary_first_process",
                series,
                "primary first-process evidence is already recorded or late".to_owned(),
            );
        }
        let case = self.costly_order()[0];
        let repetition_index = self.primary_first_process_series.len();
        let validation = validate_auxiliary_series_identity(
            &series,
            case,
            RouterTimingSeriesKind::FirstProcessCostly,
            RouterTimingInstrumentationMode::MinimallyInstrumented,
        )
        .and_then(|()| {
            validate_first_process_identity(
                &series,
                &primary_first_process_identity(&self.batch_id, repetition_index),
            )
        })
        .and_then(|()| {
            self.validate_auxiliary_series(
                &series,
                case,
                RouterTimingSeriesKind::FirstProcessCostly,
                RouterTimingInstrumentationMode::MinimallyInstrumented,
            )
        });
        let failure = validation.as_ref().err().map(|error| {
            RouterOrchestrationFailure::from_timing_series("primary_first_process", &series, error)
        });
        self.append_timing_observations("primary_first_process", &series, validation.is_ok());
        self.primary_first_process_series.push(series);
        match validation {
            Ok(()) => Ok(()),
            Err(error) => self.retain_failure_record(
                failure.expect("failed validation has a retained failure record"),
                error,
            ),
        }
    }

    fn record_correctness_attempt(
        &mut self,
        case: OrchestratedRouterCase,
        attempt: RouterCorrectnessAttempt,
    ) -> Result<(), String> {
        self.ensure_active()?;
        let expected = self
            .correctness_order()
            .get(self.correctness_gates.len())
            .copied();
        let schedule_step = match expected.unwrap_or(case) {
            OrchestratedRouterCase::SingleRow => "single_row_correctness",
            OrchestratedRouterCase::TwoRow => "two_row_correctness",
        };
        let source_passed =
            attempt.case_id == case.case_id() && attempt.passes_gate(&self.batch_id, case);
        let passed = expected == Some(case) && source_passed;
        self.append_correctness_observation(
            schedule_step,
            &attempt,
            self.pending_correctness_attempts.len(),
            source_passed,
            passed,
        );
        self.pending_correctness_attempts.push(attempt);
        if !passed {
            return self.retain_correctness_failure(
                if expected.is_none() {
                    "router correctness attempt occurred after the frozen gates completed"
                } else if expected != Some(case) {
                    "router correctness attempt violated the frozen case order"
                } else {
                    "router correctness attempt failed and triggered the retained stop condition"
                }
                .to_owned(),
            );
        }
        if self.pending_correctness_attempts.len() == ROUTER_CORRECTNESS_ATTEMPTS {
            let attempts = std::mem::take(&mut self.pending_correctness_attempts);
            match RouterCorrectnessGate::try_new(&self.batch_id, case, attempts.clone()) {
                Ok(gate) => self.correctness_gates.push(gate),
                Err(error) => {
                    self.pending_correctness_attempts = attempts;
                    self.mark_last_observations_rejected(ROUTER_CORRECTNESS_ATTEMPTS);
                    return self.retain_correctness_failure(error);
                }
            }
        }
        Ok(())
    }

    fn record_costly_series(&mut self, series: RouterTimingSeries) -> Result<(), String> {
        self.ensure_active()?;
        if self.primary_first_process_series.len() != ROUTER_FIRST_PROCESS_REPETITIONS {
            return self.reject_timing_series(
                "costly_real",
                series,
                "costly router timing is blocked until first-process evidence passes".to_owned(),
            );
        }
        let Some(case) = self.costly_order().get(self.costly_series.len()).copied() else {
            return self.reject_timing_series(
                "costly_real",
                series,
                "costly router timing series are already complete".to_owned(),
            );
        };
        let validation = validate_auxiliary_series_identity(
            &series,
            case,
            RouterTimingSeriesKind::CostlyReal,
            RouterTimingInstrumentationMode::MinimallyInstrumented,
        )
        .and_then(|()| validate_primary_process_identity(&self.batch_id, &series))
        .and_then(|()| {
            self.validate_auxiliary_series(
                &series,
                case,
                RouterTimingSeriesKind::CostlyReal,
                RouterTimingInstrumentationMode::MinimallyInstrumented,
            )
        });
        let failure = validation.as_ref().err().map(|error| {
            RouterOrchestrationFailure::from_timing_series("costly_real", &series, error)
        });
        self.append_timing_observations("costly_real", &series, validation.is_ok());
        self.costly_series.push(series);
        match validation {
            Ok(()) => Ok(()),
            Err(error) => self.retain_failure_record(
                failure.expect("failed validation has a retained failure record"),
                error,
            ),
        }
    }

    fn record_primary_major_series(&mut self, series: RouterTimingSeries) -> Result<(), String> {
        self.ensure_active()?;
        if self.costly_series.len() != self.costly_order().len() {
            return self.reject_timing_series(
                "primary_major",
                series,
                "router major timing is blocked until both costly series pass".to_owned(),
            );
        }
        let Some(expected) = self
            .primary_major_order()
            .get(self.primary_major_series.len())
            .copied()
        else {
            return self.reject_timing_series(
                "primary_major",
                series,
                "primary router major series are already complete".to_owned(),
            );
        };
        let validation = validate_major_series_identity(&series, expected)
            .and_then(|()| validate_primary_process_identity(&self.batch_id, &series))
            .and_then(|()| self.validate_series_for_step(&series, expected));
        let failure = validation.as_ref().err().map(|error| {
            RouterOrchestrationFailure::from_timing_series("primary_major", &series, error)
        });
        self.append_timing_observations("primary_major", &series, validation.is_ok());
        self.primary_major_series.push(series);
        match validation {
            Ok(()) => Ok(()),
            Err(error) => self.retain_failure_record(
                failure.expect("failed validation has a retained failure record"),
                error,
            ),
        }
    }

    fn record_stage_diagnostic_series(&mut self, series: RouterTimingSeries) -> Result<(), String> {
        self.ensure_active()?;
        if self.primary_major_series.len() != self.primary_major_order().len() {
            return self.reject_timing_series(
                "stage_diagnostic",
                series,
                "stage diagnostics are blocked until both primary major series pass".to_owned(),
            );
        }
        let Some(case) = self
            .stage_diagnostic_order()
            .get(self.stage_diagnostic_series.len())
            .copied()
        else {
            return self.reject_timing_series(
                "stage_diagnostic",
                series,
                "router stage diagnostics are already complete".to_owned(),
            );
        };
        let validation = validate_auxiliary_series_identity(
            &series,
            case,
            RouterTimingSeriesKind::StageDiagnostic,
            RouterTimingInstrumentationMode::StageInstrumented,
        )
        .and_then(|()| validate_primary_process_identity(&self.batch_id, &series))
        .and_then(|()| {
            self.validate_auxiliary_series(
                &series,
                case,
                RouterTimingSeriesKind::StageDiagnostic,
                RouterTimingInstrumentationMode::StageInstrumented,
            )
        });
        let failure = validation.as_ref().err().map(|error| {
            RouterOrchestrationFailure::from_timing_series("stage_diagnostic", &series, error)
        });
        self.append_timing_observations("stage_diagnostic", &series, validation.is_ok());
        self.stage_diagnostic_series.push(series);
        match validation {
            Ok(()) => Ok(()),
            Err(error) => self.retain_failure_record(
                failure.expect("failed validation has a retained failure record"),
                error,
            ),
        }
    }

    fn record_clean_first_process_series(
        &mut self,
        series: RouterTimingSeries,
    ) -> Result<(), String> {
        self.ensure_active()?;
        if self.stage_diagnostic_series.len() != self.stage_diagnostic_order().len() {
            return self.reject_timing_series(
                "clean_first_process",
                series,
                "clean first-process evidence is blocked until stage diagnostics pass".to_owned(),
            );
        }
        let case_index = self.clean_major_series.len();
        let Some(expected) = self.clean_major_order().get(case_index).copied() else {
            return self.reject_timing_series(
                "clean_first_process",
                series,
                "clean first-process evidence is already complete".to_owned(),
            );
        };
        let group_start = case_index * ROUTER_FIRST_PROCESS_REPETITIONS;
        let repetition_index = self
            .clean_first_process_series
            .len()
            .saturating_sub(group_start);
        if self.clean_first_process_series.len() < group_start
            || repetition_index >= ROUTER_FIRST_PROCESS_REPETITIONS
        {
            return self.reject_timing_series(
                "clean_first_process",
                series,
                "the current clean worker cohort must complete its major replication before another starts"
                    .to_owned(),
            );
        }
        let validation = validate_auxiliary_series_identity(
            &series,
            expected.0,
            RouterTimingSeriesKind::FirstProcessCostly,
            RouterTimingInstrumentationMode::MinimallyInstrumented,
        )
        .and_then(|()| {
            validate_first_process_identity(
                &series,
                &clean_first_process_identity(&self.batch_id, expected.0, repetition_index),
            )
        })
        .and_then(|()| {
            self.validate_auxiliary_series(
                &series,
                expected.0,
                RouterTimingSeriesKind::FirstProcessCostly,
                RouterTimingInstrumentationMode::MinimallyInstrumented,
            )
        });
        let failure = validation.as_ref().err().map(|error| {
            RouterOrchestrationFailure::from_timing_series("clean_first_process", &series, error)
        });
        self.append_timing_observations("clean_first_process", &series, validation.is_ok());
        self.clean_first_process_series.push(series);
        match validation {
            Ok(()) => Ok(()),
            Err(error) => self.retain_failure_record(
                failure.expect("failed validation has a retained failure record"),
                error,
            ),
        }
    }

    fn record_clean_major_series(&mut self, series: RouterTimingSeries) -> Result<(), String> {
        self.ensure_active()?;
        if self.stage_diagnostic_series.len() != self.stage_diagnostic_order().len() {
            return self.reject_timing_series(
                "clean_major",
                series,
                "clean router replications are blocked until stage diagnostics pass".to_owned(),
            );
        }
        let required_first_process_count =
            (self.clean_major_series.len() + 1) * ROUTER_FIRST_PROCESS_REPETITIONS;
        if self.clean_first_process_series.len() != required_first_process_count {
            return self.reject_timing_series(
                "clean_major",
                series,
                "clean major timing is blocked until its first-process evidence passes".to_owned(),
            );
        }
        let Some(expected) = self
            .clean_major_order()
            .get(self.clean_major_series.len())
            .copied()
        else {
            return self.reject_timing_series(
                "clean_major",
                series,
                "clean router major series are already complete".to_owned(),
            );
        };
        let validation = validate_major_series_identity(&series, expected)
            .and_then(|()| validate_clean_process_identity(&self.batch_id, expected.0, &series))
            .and_then(|()| self.validate_series_for_step(&series, expected));
        let failure = validation.as_ref().err().map(|error| {
            RouterOrchestrationFailure::from_timing_series("clean_major", &series, error)
        });
        let observation_count = series.raw_timing_observations().len();
        self.append_timing_observations("clean_major", &series, validation.is_ok());
        self.clean_major_series.push(series);
        if let Err(error) = validation {
            return self.retain_failure_record(
                failure.expect("failed validation has a retained failure record"),
                error,
            );
        }
        if self.clean_major_series.len() == self.clean_major_order().len() {
            let completion =
                validate_major_router_timing_series(&self.complete_primary_major_matrix())
                    .map_err(|error| error.to_string())
                    .and_then(|()| self.require_primary_complete());
            if let Err(error) = completion {
                self.mark_last_observations_rejected(observation_count);
                return self.retain_timing_failure("clean_major_matrix", error);
            }
        }
        Ok(())
    }

    fn ordered_observation_evidence(&self) -> Result<Vec<Value>, String> {
        let correctness_count = self
            .correctness_gates
            .iter()
            .map(|gate| gate.attempts.len())
            .sum::<usize>()
            .checked_add(self.pending_correctness_attempts.len())
            .ok_or_else(|| "router correctness observation count overflows".to_owned())?;
        let timing_count = self
            .primary_first_process_series
            .iter()
            .chain(&self.costly_series)
            .chain(&self.primary_major_series)
            .chain(&self.stage_diagnostic_series)
            .chain(&self.clean_first_process_series)
            .chain(&self.clean_major_series)
            .map(|series| series.raw_timing_observations().len())
            .chain(
                self.rejected_timing_series
                    .iter()
                    .map(|item| item.series.raw_timing_observations().len()),
            )
            .sum::<usize>();
        let expected_count = correctness_count
            .checked_add(timing_count)
            .ok_or_else(|| "router ordered observation count overflows".to_owned())?;
        if self.ordered_observations.len() != expected_count {
            return Err(
                "router ordered observation ledger is incomplete or non-contiguous".to_owned(),
            );
        }
        serialize_ordered_observations(&self.batch_id, &self.ordered_observations)
    }

    fn retained_batch_snapshot(&self) -> Result<Value, String> {
        let status = if self.correctness_failed || self.timing_failed {
            "failed"
        } else if self.require_primary_complete().is_ok() {
            "complete_candidate"
        } else {
            "incomplete"
        };
        let snapshot = json!({
            "status": status,
            "batch_id": self.batch_id,
            "order": match self.batch_order {
                RouterBatchOrder::SingleRowFirst => "single_row_first",
                RouterBatchOrder::TwoRowFirst => "two_row_first",
            },
            "next_step": self.next_step(),
            "raw_observations": self.ordered_observation_evidence()?,
            "failure": self.terminal_failure.as_ref().map(RouterOrchestrationFailure::evidence),
            "correctness_gates": self.correctness_gates
                .iter()
                .map(RouterCorrectnessGate::evidence)
                .collect::<Vec<_>>(),
            "pending_correctness_attempts": self.retained_correctness_attempt_evidence(),
            "first_process_series": serialize_timing_series(
                &self.primary_first_process_series
                    .iter()
                    .chain(&self.clean_first_process_series)
                    .cloned()
                    .collect::<Vec<_>>(),
            )?,
            "costly_series": serialize_timing_series(&self.costly_series)?,
            "primary_major_series": serialize_timing_series(&self.primary_major_series)?,
            "stage_diagnostic_series": serialize_timing_series(&self.stage_diagnostic_series)?,
            "clean_major_series": serialize_timing_series(&self.clean_major_series)?,
            "rejected_timing_series": serialize_rejected_timing_series(
                &self.rejected_timing_series,
            )?,
        });
        ensure_no_private_paths(&snapshot)?;
        if serde_json::to_vec(&snapshot)
            .map_err(|_| "router batch snapshot could not be encoded".to_owned())?
            .len()
            > MAX_RESPONSE_BYTES
        {
            return Err("router batch snapshot exceeds the protocol cap".to_owned());
        }
        Ok(snapshot)
    }

    fn retained_correctness_attempt_evidence(&self) -> Vec<Value> {
        let rejected_index = self
            .correctness_failed
            .then(|| self.pending_correctness_attempts.len().checked_sub(1))
            .flatten();
        self.pending_correctness_attempts
            .iter()
            .enumerate()
            .map(|(index, attempt)| {
                let mut evidence = attempt.evidence(&self.batch_id, index);
                if rejected_index == Some(index) {
                    evidence["status"] = json!("failed");
                    evidence["passed"] = json!(false);
                    evidence["failure"] = self
                        .terminal_failure
                        .as_ref()
                        .map(RouterOrchestrationFailure::evidence)
                        .unwrap_or_else(|| {
                            json!({
                                "code": "comparison_failed",
                                "stage": "correctness_gate",
                                "message": "correctness attempt triggered a retained stop condition",
                            })
                        });
                }
                evidence
            })
            .collect()
    }

    fn record_later_batch(&mut self, candidate: &RouterSecondBatchCandidate) -> Result<(), String> {
        self.ensure_active()?;
        if self.later_batch != RouterLaterBatchState::Pending {
            return Err("later router batch disposition is already recorded".to_owned());
        }
        match self.validate_and_record_later_batch(candidate) {
            Ok(()) => Ok(()),
            Err(error) => {
                let failure = candidate.terminal_failure.clone().unwrap_or_else(|| {
                    RouterOrchestrationFailure::comparison("later_batch", &error)
                });
                self.later_batch = RouterLaterBatchState::Failed(Box::new(RouterFailedBatch {
                    batch_id: candidate.batch_id.clone(),
                    candidate: Box::new(candidate.clone()),
                }));
                self.retain_failure_record(failure, error)
            }
        }
    }

    fn validate_and_record_later_batch(
        &mut self,
        candidate: &RouterSecondBatchCandidate,
    ) -> Result<(), String> {
        if self.batch_order != RouterBatchOrder::SingleRowFirst {
            return Err("only the primary batch can accept a second batch".to_owned());
        }
        self.require_primary_complete()?;
        if self.later_batch != RouterLaterBatchState::Pending {
            return Err("later router batch disposition is already recorded".to_owned());
        }
        let batch_id = candidate.batch_id.as_str();
        if candidate.batch_order != RouterBatchOrder::TwoRowFirst
            || candidate.later_batch != RouterLaterBatchState::Pending
            || batch_id == ROUTER_PRIMARY_BATCH_ID
            || !stable_orchestration_identifier(batch_id)
        {
            return Err("later router batch identity is invalid or reused".to_owned());
        }
        candidate.require_primary_complete()?;
        if candidate.correctness_gates.len() != ROUTER_SECOND_CORRECTNESS_ORDER.len()
            || candidate.costly_series.len() != ROUTER_SECOND_COSTLY_ORDER.len()
            || candidate.primary_major_series.len() != ROUTER_SECOND_PRIMARY_MAJOR_ORDER.len()
            || candidate.stage_diagnostic_series.len() != ROUTER_SECOND_STAGE_DIAGNOSTIC_ORDER.len()
            || candidate.clean_major_series.len() != ROUTER_SECOND_CLEAN_MAJOR_ORDER.len()
        {
            return Err("later router batch is not a complete reversed schedule".to_owned());
        }
        if candidate.primary_first_process_series.len() != ROUTER_FIRST_PROCESS_REPETITIONS {
            return Err("later batch lacks its complete primary first-process cohort".to_owned());
        }
        for (index, primary_first_process) in
            candidate.primary_first_process_series.iter().enumerate()
        {
            validate_auxiliary_series_identity(
                primary_first_process,
                ROUTER_SECOND_CORRECTNESS_ORDER[0],
                RouterTimingSeriesKind::FirstProcessCostly,
                RouterTimingInstrumentationMode::MinimallyInstrumented,
            )?;
            validate_first_process_series(primary_first_process)?;
            validate_first_process_identity(
                primary_first_process,
                &primary_first_process_identity(batch_id, index),
            )?;
        }
        for (gate, expected) in candidate
            .correctness_gates
            .iter()
            .zip(ROUTER_SECOND_CORRECTNESS_ORDER)
        {
            if gate.case != expected
                || RouterCorrectnessGate::try_new(batch_id, gate.case, gate.attempts.clone())?
                    != *gate
                || self
                    .correctness_gates
                    .iter()
                    .find(|primary| primary.case == gate.case)
                    .is_none_or(|primary| {
                        primary.complete_output_sha256 != gate.complete_output_sha256
                    })
            {
                return Err(
                    "later router correctness gates violate order or repeat identity".to_owned(),
                );
            }
        }
        let first_case_gate = candidate
            .correctness_gates
            .iter()
            .find(|gate| gate.case == ROUTER_SECOND_CORRECTNESS_ORDER[0])
            .ok_or_else(|| "later batch lacks its first-case correctness gate".to_owned())?;
        if candidate.primary_first_process_series.iter().any(|series| {
            series.passing_output_sha256() != Some(first_case_gate.complete_output_sha256.as_str())
        }) {
            return Err(
                "later primary first-process output differs from its correctness gate".to_owned(),
            );
        }
        for (series, case) in candidate
            .costly_series
            .iter()
            .zip(ROUTER_SECOND_COSTLY_ORDER)
        {
            validate_auxiliary_series_against_gates(
                series,
                case,
                RouterTimingSeriesKind::CostlyReal,
                RouterTimingInstrumentationMode::MinimallyInstrumented,
                &candidate.correctness_gates,
            )?;
            validate_primary_process_identity(batch_id, series)?;
        }
        for (series, expected) in candidate
            .primary_major_series
            .iter()
            .zip(ROUTER_SECOND_PRIMARY_MAJOR_ORDER)
        {
            validate_major_series_against_gates(series, expected, &candidate.correctness_gates)?;
            validate_primary_process_identity(batch_id, series)?;
        }
        for (series, case) in candidate
            .stage_diagnostic_series
            .iter()
            .zip(ROUTER_SECOND_STAGE_DIAGNOSTIC_ORDER)
        {
            validate_auxiliary_series_against_gates(
                series,
                case,
                RouterTimingSeriesKind::StageDiagnostic,
                RouterTimingInstrumentationMode::StageInstrumented,
                &candidate.correctness_gates,
            )?;
            validate_primary_process_identity(batch_id, series)?;
        }
        if candidate.clean_first_process_series.len()
            != ROUTER_SECOND_CLEAN_MAJOR_ORDER.len() * ROUTER_FIRST_PROCESS_REPETITIONS
        {
            return Err("later batch lacks complete clean first-process cohorts".to_owned());
        }
        for (series_group, expected) in candidate
            .clean_first_process_series
            .chunks_exact(ROUTER_FIRST_PROCESS_REPETITIONS)
            .zip(ROUTER_SECOND_CLEAN_MAJOR_ORDER)
        {
            for (index, series) in series_group.iter().enumerate() {
                validate_auxiliary_series_against_gates(
                    series,
                    expected.0,
                    RouterTimingSeriesKind::FirstProcessCostly,
                    RouterTimingInstrumentationMode::MinimallyInstrumented,
                    &candidate.correctness_gates,
                )?;
                validate_first_process_identity(
                    series,
                    &clean_first_process_identity(batch_id, expected.0, index),
                )?;
            }
        }
        for (series, expected) in candidate
            .clean_major_series
            .iter()
            .zip(ROUTER_SECOND_CLEAN_MAJOR_ORDER)
        {
            validate_major_series_against_gates(series, expected, &candidate.correctness_gates)?;
            validate_clean_process_identity(batch_id, expected.0, series)?;
        }
        let major_series = candidate
            .primary_major_series
            .iter()
            .chain(&candidate.clean_major_series)
            .cloned()
            .collect::<Vec<_>>();
        validate_major_router_timing_series(&major_series).map_err(|error| error.to_string())?;
        validate_orchestrated_process_matrix(&major_series)?;
        let primary_schedule = self
            .primary_first_process_series
            .iter()
            .chain(&self.costly_series)
            .chain(&self.primary_major_series)
            .chain(&self.stage_diagnostic_series)
            .chain(&self.clean_first_process_series)
            .chain(&self.clean_major_series)
            .collect::<Vec<_>>();
        let second_schedule = candidate
            .primary_first_process_series
            .iter()
            .chain(&candidate.costly_series)
            .chain(&candidate.primary_major_series)
            .chain(&candidate.stage_diagnostic_series)
            .chain(&candidate.clean_first_process_series)
            .chain(&candidate.clean_major_series)
            .collect::<Vec<_>>();
        validate_independent_later_batch(&primary_schedule, &second_schedule)?;
        validate_unique_observation_identities(
            candidate
                .primary_first_process_series
                .iter()
                .chain(&candidate.costly_series)
                .chain(&candidate.primary_major_series)
                .chain(&candidate.stage_diagnostic_series)
                .chain(&candidate.clean_first_process_series)
                .chain(&candidate.clean_major_series),
        )?;
        self.later_batch = RouterLaterBatchState::Recorded(Box::new(RouterRecordedBatch {
            batch_id: candidate.batch_id.clone(),
            ordered_observations: candidate.ordered_observations.clone(),
            primary_first_process_series: candidate.primary_first_process_series.clone(),
            correctness_gates: candidate.correctness_gates.clone(),
            costly_series: candidate.costly_series.clone(),
            primary_major_series: candidate.primary_major_series.clone(),
            stage_diagnostic_series: candidate.stage_diagnostic_series.clone(),
            clean_first_process_series: candidate.clean_first_process_series.clone(),
            clean_major_series: candidate.clean_major_series.clone(),
        }));
        Ok(())
    }

    fn record_later_batch_unavailable(
        &mut self,
        reason: RouterSecondBatchUnavailableReason,
    ) -> Result<(), String> {
        self.ensure_active()?;
        if let Err(error) = self.require_primary_complete() {
            return self.retain_timing_failure("later_batch_unavailable", error);
        }
        if self.later_batch != RouterLaterBatchState::Pending {
            return Err("later router batch disposition is already recorded".to_owned());
        }
        let reason = reason.public_reason().to_owned();
        ensure_no_private_paths(&Value::String(reason.clone()))?;
        self.later_batch = RouterLaterBatchState::Unavailable { reason };
        Ok(())
    }

    fn evidence(&self) -> Result<Value, String> {
        if self.correctness_failed || self.timing_failed {
            let retained_major_series = self.complete_primary_major_matrix();
            let failure = self
                .terminal_failure
                .as_ref()
                .ok_or_else(|| "router terminal failure lacks a stable error record".to_owned())?;
            let evidence = json!({
                "schema_version": 1,
                "orchestration": "qwen3moe-router-frozen-schedule",
                "status": "failed",
                "batch_id": self.batch_id,
                "order": match self.batch_order {
                    RouterBatchOrder::SingleRowFirst => "single_row_first",
                    RouterBatchOrder::TwoRowFirst => "two_row_first",
                },
                "stage": failure.stage,
                "failure": failure.evidence(),
                "order_seed": ROUTER_BENCHMARK_ORDER_SEED,
                "raw_observations": self.ordered_observation_evidence()?,
                "completed_correctness_gates": self
                    .correctness_gates
                    .iter()
                    .map(RouterCorrectnessGate::evidence)
                    .collect::<Vec<_>>(),
                "retained_current_case_attempts": self.retained_correctness_attempt_evidence(),
                "retained_timing": {
                    "first_process_series": serialize_timing_series(
                        &self.primary_first_process_series
                            .iter()
                            .chain(&self.clean_first_process_series)
                            .cloned()
                            .collect::<Vec<_>>(),
                    )?,
                    "costly_series": serialize_timing_series(&self.costly_series)?,
                    "major_series": serialize_timing_series(&retained_major_series)?,
                    "stage_diagnostic_series": serialize_timing_series(
                        &self.stage_diagnostic_series,
                    )?,
                    "rejected_series": serialize_rejected_timing_series(
                        &self.rejected_timing_series,
                    )?,
                },
                "second_batch": match &self.later_batch {
                    RouterLaterBatchState::Failed(failed) => {
                        let retained_evidence = failed.candidate.retained_batch_snapshot()?;
                        json!({
                            "status": "failed",
                            "batch_id": failed.batch_id,
                            "retained_evidence": retained_evidence,
                        })
                    }
                    _ => Value::Null,
                },
                "first_process_observation_started": !self.primary_first_process_series.is_empty()
                    || !self.clean_first_process_series.is_empty()
                    || self.rejected_timing_series.iter().any(|item| {
                        item.series.series_kind() == RouterTimingSeriesKind::FirstProcessCostly
                    }),
                "timing_started": !self.primary_first_process_series.is_empty()
                    || !self.costly_series.is_empty()
                    || !self.primary_major_series.is_empty()
                    || !self.stage_diagnostic_series.is_empty()
                    || !self.clean_first_process_series.is_empty()
                    || !self.clean_major_series.is_empty()
                    || !self.rejected_timing_series.is_empty(),
                "passed": false,
            });
            ensure_no_private_paths(&evidence)?;
            if serde_json::to_vec(&evidence)
                .map_err(|_| "router failure evidence could not be encoded".to_owned())?
                .len()
                > MAX_RESPONSE_BYTES
            {
                return Err("router failure evidence exceeds the protocol cap".to_owned());
            }
            return Ok(evidence);
        }
        self.require_primary_complete()?;
        let primary_major_matrix = self.complete_primary_major_matrix();
        let primary_series = serialize_timing_series(&primary_major_matrix)?;
        let later_batch = match &self.later_batch {
            RouterLaterBatchState::Pending => {
                return Err(
                    "later router batch requires recorded evidence or an unavailable reason"
                        .to_owned(),
                );
            }
            RouterLaterBatchState::Recorded(recorded) => json!({
                "status": "recorded",
                "batch_id": recorded.batch_id,
                "order": "two_row_before_single_row_within_each_major_pair",
                "raw_observations": serialize_ordered_observations(
                    &recorded.batch_id,
                    &recorded.ordered_observations,
                )?,
                "between_batch_variation_measured": true,
                "first_process_series": serialize_timing_series(
                    &recorded.primary_first_process_series
                        .iter()
                        .chain(&recorded.clean_first_process_series)
                        .cloned()
                        .collect::<Vec<_>>(),
                )?,
                "correctness_gates": recorded.correctness_gates
                    .iter()
                    .map(RouterCorrectnessGate::evidence)
                    .collect::<Vec<_>>(),
                "costly_series": serialize_timing_series(&recorded.costly_series)?,
                "major_series": serialize_timing_series(
                    &recorded.primary_major_series
                        .iter()
                        .chain(&recorded.clean_major_series)
                        .cloned()
                        .collect::<Vec<_>>(),
                )?,
                "stage_diagnostic_series": serialize_timing_series(
                    &recorded.stage_diagnostic_series,
                )?,
            }),
            RouterLaterBatchState::Failed(_) => {
                return Err("failed later router batch must use terminal evidence".to_owned());
            }
            RouterLaterBatchState::Unavailable { reason } => json!({
                "status": "unavailable",
                "reason": reason,
                "between_batch_variation_measured": false,
            }),
        };
        let evidence = json!({
            "schema_version": 1,
            "orchestration": "qwen3moe-router-frozen-schedule",
            "status": "passed",
            "order_seed": ROUTER_BENCHMARK_ORDER_SEED,
            "correctness_gates": self
                .correctness_gates
                .iter()
                .map(RouterCorrectnessGate::evidence)
                .collect::<Vec<_>>(),
            "primary_batch": {
                "batch_id": self.batch_id,
                "order": "single_row_before_two_row_within_each_major_pair",
                "raw_observations": self.ordered_observation_evidence()?,
                "first_process_series": serialize_timing_series(
                    &self.primary_first_process_series
                        .iter()
                        .chain(&self.clean_first_process_series)
                        .cloned()
                        .collect::<Vec<_>>(),
                )?,
                "costly_series": serialize_timing_series(&self.costly_series)?,
                "major_series": primary_series,
                "stage_diagnostic_series": serialize_timing_series(&self.stage_diagnostic_series)?,
            },
            "second_batch": later_batch,
        });
        ensure_no_private_paths(&evidence)?;
        if serde_json::to_vec(&evidence)
            .map_err(|_| "router orchestration evidence could not be encoded".to_owned())?
            .len()
            > MAX_RESPONSE_BYTES
        {
            return Err("router orchestration evidence exceeds the protocol cap".to_owned());
        }
        Ok(evidence)
    }

    fn validate_series_for_step(
        &self,
        series: &RouterTimingSeries,
        expected: (OrchestratedRouterCase, RouterTimingReplicationRole),
    ) -> Result<(), String> {
        validate_major_series_against_gates(series, expected, &self.correctness_gates)
    }

    fn validate_auxiliary_series(
        &self,
        series: &RouterTimingSeries,
        case: OrchestratedRouterCase,
        series_kind: RouterTimingSeriesKind,
        instrumentation_mode: RouterTimingInstrumentationMode,
    ) -> Result<(), String> {
        validate_auxiliary_series_against_gates(
            series,
            case,
            series_kind,
            instrumentation_mode,
            &self.correctness_gates,
        )
    }

    fn complete_primary_major_matrix(&self) -> Vec<RouterTimingSeries> {
        self.primary_major_series
            .iter()
            .chain(&self.clean_major_series)
            .cloned()
            .collect()
    }

    fn require_primary_complete(&self) -> Result<(), String> {
        self.ordered_observation_evidence()?;
        if self.correctness_failed
            || self.timing_failed
            || self.ordered_observations.iter().any(|observation| {
                observation.orchestration_status != "accepted" || observation.identity_duplicate
            })
            || self.primary_first_process_series.len() != ROUTER_FIRST_PROCESS_REPETITIONS
            || self.correctness_gates.len() != self.correctness_order().len()
            || self.costly_series.len() != self.costly_order().len()
            || self.primary_major_series.len() != self.primary_major_order().len()
            || self.stage_diagnostic_series.len() != self.stage_diagnostic_order().len()
            || self.clean_first_process_series.len()
                != self.clean_major_order().len() * ROUTER_FIRST_PROCESS_REPETITIONS
            || self.clean_major_series.len() != self.clean_major_order().len()
        {
            return Err("primary router frozen schedule is incomplete".to_owned());
        }
        let major_matrix = self.complete_primary_major_matrix();
        validate_major_router_timing_series(&major_matrix).map_err(|error| error.to_string())?;
        validate_orchestrated_process_matrix(&major_matrix)?;
        validate_unique_observation_identities(
            self.primary_first_process_series
                .iter()
                .chain(&self.costly_series)
                .chain(&self.primary_major_series)
                .chain(&self.stage_diagnostic_series)
                .chain(&self.clean_first_process_series)
                .chain(&self.clean_major_series),
        )
    }
}

fn serialize_ordered_observations(
    batch_id: &str,
    observations: &[RouterOrderedObservation],
) -> Result<Vec<Value>, String> {
    if observations
        .iter()
        .enumerate()
        .any(|(index, observation)| observation.global_order_index != index)
    {
        return Err("router ordered observation ledger is non-contiguous".to_owned());
    }
    Ok(observations
        .iter()
        .map(|observation| observation.evidence(batch_id))
        .collect())
}

#[cfg_attr(not(test), allow(dead_code))]
fn validate_major_series_identity(
    series: &RouterTimingSeries,
    expected: (OrchestratedRouterCase, RouterTimingReplicationRole),
) -> Result<(), String> {
    let (case, role) = expected;
    if series.case_id() != case.case_id()
        || series.benchmark_id() != case.benchmark_id()
        || series.series_kind() != RouterTimingSeriesKind::MajorMinimallyInstrumented
        || series.replication_role() != role
        || series.instrumentation_mode() != RouterTimingInstrumentationMode::MinimallyInstrumented
    {
        return Err("router major series violates its frozen step identity".to_owned());
    }
    Ok(())
}

#[cfg_attr(not(test), allow(dead_code))]
fn validate_major_series_against_gates(
    series: &RouterTimingSeries,
    expected: (OrchestratedRouterCase, RouterTimingReplicationRole),
    gates: &[RouterCorrectnessGate],
) -> Result<(), String> {
    let (case, role) = expected;
    validate_major_series_identity(series, expected)?;
    let gate = gates
        .iter()
        .find(|gate| gate.case == case)
        .ok_or_else(|| "router timing lacks its matching correctness gate".to_owned())?;
    if series.replication_role() != role
        || !series.has_complete_success_samples()
        || series
            .raw_timing_observations()
            .iter()
            .any(|observation| observation.status() != RouterTimingObservationStatus::Passed)
        || series.passing_output_sha256() != Some(gate.complete_output_sha256.as_str())
    {
        return Err(
            "router major series contradicts its correctness gate or frozen step".to_owned(),
        );
    }
    Ok(())
}

#[cfg_attr(not(test), allow(dead_code))]
fn validate_auxiliary_series_identity(
    series: &RouterTimingSeries,
    case: OrchestratedRouterCase,
    series_kind: RouterTimingSeriesKind,
    instrumentation_mode: RouterTimingInstrumentationMode,
) -> Result<(), String> {
    if series.case_id() != case.case_id()
        || series.series_kind() != series_kind
        || series.replication_role() != RouterTimingReplicationRole::Primary
        || series.instrumentation_mode() != instrumentation_mode
    {
        return Err("router auxiliary series violates its frozen step identity".to_owned());
    }
    Ok(())
}

#[cfg_attr(not(test), allow(dead_code))]
fn validate_first_process_series(series: &RouterTimingSeries) -> Result<(), String> {
    if !series.has_complete_success_samples()
        || series
            .raw_timing_observations()
            .iter()
            .any(|observation| observation.status() != RouterTimingObservationStatus::Passed)
        || series
            .passing_output_sha256()
            .is_none_or(|hash| !canonical_sha256(hash))
    {
        return Err("router first-process series contains a retained failure".to_owned());
    }
    Ok(())
}

#[cfg_attr(not(test), allow(dead_code))]
fn validate_auxiliary_series_against_gates(
    series: &RouterTimingSeries,
    case: OrchestratedRouterCase,
    series_kind: RouterTimingSeriesKind,
    instrumentation_mode: RouterTimingInstrumentationMode,
    gates: &[RouterCorrectnessGate],
) -> Result<(), String> {
    validate_auxiliary_series_identity(series, case, series_kind, instrumentation_mode)?;
    let gate = gates
        .iter()
        .find(|gate| gate.case == case)
        .ok_or_else(|| "router timing lacks its matching correctness gate".to_owned())?;
    if !series.has_complete_success_samples()
        || series
            .raw_timing_observations()
            .iter()
            .any(|observation| observation.status() != RouterTimingObservationStatus::Passed)
        || series.passing_output_sha256() != Some(gate.complete_output_sha256.as_str())
    {
        return Err(
            "router auxiliary series contradicts its correctness gate or frozen step".to_owned(),
        );
    }
    Ok(())
}

#[cfg_attr(not(test), allow(dead_code))]
fn validate_unique_observation_identities<'a>(
    series: impl Iterator<Item = &'a RouterTimingSeries>,
) -> Result<(), String> {
    let mut identities = BTreeSet::new();
    if series
        .flat_map(RouterTimingSeries::raw_timing_observations)
        .any(|observation| !identities.insert(observation.observation_id()))
    {
        return Err("router schedule reuses an observation identity across series".to_owned());
    }
    Ok(())
}

fn primary_process_identity(batch_id: &str) -> String {
    primary_first_process_identity(batch_id, 0)
}

fn correctness_process_identity(batch_id: &str) -> String {
    format!("{batch_id}-correctness-worker")
}

fn clean_process_identity(batch_id: &str, case: OrchestratedRouterCase) -> String {
    clean_first_process_identity(batch_id, case, 0)
}

fn primary_first_process_identity(batch_id: &str, repetition_index: usize) -> String {
    format!("{batch_id}-primary-first-read-worker-{repetition_index:02}")
}

fn clean_first_process_identity(
    batch_id: &str,
    case: OrchestratedRouterCase,
    repetition_index: usize,
) -> String {
    match case {
        OrchestratedRouterCase::SingleRow => {
            format!("{batch_id}-single-row-clean-first-read-worker-{repetition_index:02}")
        }
        OrchestratedRouterCase::TwoRow => {
            format!("{batch_id}-two-row-clean-first-read-worker-{repetition_index:02}")
        }
    }
}

fn validate_first_process_identity(
    series: &RouterTimingSeries,
    expected_process_id: &str,
) -> Result<(), String> {
    if series.process_replication_id() != expected_process_id {
        return Err(
            "router first-process series does not use its orchestration-issued process identity"
                .to_owned(),
        );
    }
    Ok(())
}

#[cfg_attr(not(test), allow(dead_code))]
fn validate_primary_process_identity(
    batch_id: &str,
    series: &RouterTimingSeries,
) -> Result<(), String> {
    if series.process_replication_id() != primary_process_identity(batch_id) {
        return Err(
            "router primary series does not use its orchestration-issued process identity"
                .to_owned(),
        );
    }
    Ok(())
}

#[cfg_attr(not(test), allow(dead_code))]
fn validate_clean_process_identity(
    batch_id: &str,
    case: OrchestratedRouterCase,
    series: &RouterTimingSeries,
) -> Result<(), String> {
    if series.process_replication_id() != clean_process_identity(batch_id, case) {
        return Err(
            "router clean series does not use its orchestration-issued process identity".to_owned(),
        );
    }
    Ok(())
}

#[cfg_attr(not(test), allow(dead_code))]
fn validate_orchestrated_process_matrix(series: &[RouterTimingSeries]) -> Result<(), String> {
    let primary_processes = series
        .iter()
        .filter(|item| item.replication_role() == RouterTimingReplicationRole::Primary)
        .map(RouterTimingSeries::process_replication_id)
        .collect::<BTreeSet<_>>();
    let clean_processes = series
        .iter()
        .filter(|item| {
            item.replication_role() == RouterTimingReplicationRole::CleanProcessReplication
        })
        .map(RouterTimingSeries::process_replication_id)
        .collect::<BTreeSet<_>>();
    if primary_processes.len() != 1
        || clean_processes.len() != 2
        || primary_processes
            .iter()
            .any(|process| clean_processes.contains(process))
    {
        return Err(
            "router major orchestration requires one persistent and two clean processes".to_owned(),
        );
    }
    Ok(())
}

#[cfg_attr(not(test), allow(dead_code))]
fn serialize_timing_series(series: &[RouterTimingSeries]) -> Result<Vec<Value>, String> {
    series
        .iter()
        .map(|item| item.try_to_value().map_err(|error| error.to_string()))
        .collect()
}

fn serialize_rejected_timing_series(
    series: &[RouterRejectedTimingSeries],
) -> Result<Vec<Value>, String> {
    series
        .iter()
        .map(|item| {
            Ok(json!({
                "status": "failed",
                "failure": item.failure.evidence(),
                "series": item.series.try_to_value().map_err(|error| error.to_string())?,
            }))
        })
        .collect()
}

#[cfg_attr(not(test), allow(dead_code))]
fn validate_independent_later_batch(
    primary: &[&RouterTimingSeries],
    later: &[&RouterTimingSeries],
) -> Result<(), String> {
    let primary_processes = primary
        .iter()
        .map(|series| series.process_replication_id())
        .collect::<BTreeSet<_>>();
    if later
        .iter()
        .any(|series| primary_processes.contains(series.process_replication_id()))
    {
        return Err("later router batch reuses a primary-batch process identity".to_owned());
    }
    let primary_observations = primary
        .iter()
        .flat_map(|series| series.raw_timing_observations())
        .map(|observation| observation.observation_id())
        .collect::<BTreeSet<_>>();
    if later
        .iter()
        .flat_map(|series| series.raw_timing_observations())
        .any(|observation| primary_observations.contains(observation.observation_id()))
    {
        return Err("later router batch reuses a primary-batch observation identity".to_owned());
    }
    Ok(())
}

#[cfg_attr(not(test), allow(dead_code))]
fn stable_orchestration_identifier(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value.trim() == value
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.' | b':'))
}

fn run_planned_validate_router(command: ValidateRouterCommand) -> Result<(), String> {
    // As with inspection, resolving any path here would cross the T074 gate.
    let orchestration = RouterBenchmarkOrchestrator::new();
    debug_assert_eq!(orchestration.next_step(), "single_row_correctness");
    let _parsed_paths = (command.model, command.oracle, command.evidence_dir);
    Err("validate-router correctness-gated orchestration is frozen, but checkpoint admission remains blocked until notified T074 and execution until T083; no checkpoint was accessed and no MLX worker was started".to_owned())
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
    let started_at = utc_now()?;
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
    let failures = if passed {
        Vec::<String>::new()
    } else {
        vec!["The bounded Apple/reference comparison did not pass.".to_owned()]
    };
    let evidence = json!({
        "schema_version": 1,
        "case_id": MODEL_SLICE_ID,
        "validation": "qwen3-30b-a3b-q8_0-bounded-mlx-slice",
        "claim_scope": "Evaluated Apple MLX Q8_0 reference parity for one layer-0 expert-0 gate-projection matvec over output rows 0 through 15",
        "status": if passed { "passed" } else { "failed" },
        "actual_status": if passed { "passed" } else { "failed" },
        "recorded_at_utc": utc_now()?,
        "started_at_and_timezone": {
            "value": started_at,
            "timezone": "UTC",
        },
        "commit": source_commit,
        "git_dirty_state": "clean_before_execution",
        "source_commit": source_commit,
        "source_worktree_clean_before_execution": true,
        "host_architecture": hello.python_arch(),
        "os_version": format!("macOS {}", hello.macos_version()),
        "tool_and_dependency_versions": {
            "pulsar_mlx_worker": hello.worker_version(),
            "protocol": hello.protocol(),
            "python": hello.python_version(),
            "mlx": hello.mlx_version(),
        },
        "backend_and_selected_device": {
            "backend": BACKEND_ID,
            "requested_device": GPU_DEVICE,
            "selected_device": result.selected_device(),
            "fallback_used": result.fallback_used(),
        },
        "command": format!("cargo run --release -p mlx-backend --bin pulsar-mlx -- validate-model-slice --model <external-model>/{QWEN_FILENAME} --evidence docs/validation/qwen3-30b-a3b-q8_0-slice.json"),
        "exact_command": {
            "shell": "zsh",
            "command": format!("cargo run --release -p mlx-backend --bin pulsar-mlx -- validate-model-slice --model <external-model>/{QWEN_FILENAME} --evidence docs/validation/qwen3-30b-a3b-q8_0-slice.json"),
            "exit_code_from_status": if passed { 0 } else { 2 },
        },
        "artifact": {
            "repository_id": QWEN_REPOSITORY_ID,
            "revision": QWEN_REVISION,
            "filename": QWEN_FILENAME,
            "size_bytes": QWEN_FILE_BYTES,
            "sha256": QWEN_SHA256,
            "location": format!("<external-model>/{QWEN_FILENAME}"),
            "identity_rechecked_after_execution": true,
        },
        "input_identity": {
            "artifact_sha256": QWEN_SHA256,
            "tensor_name": REAL_TENSOR_NAME,
            "encoded_slice_sha256": result.encoded_slice_sha256(),
            "decoded_slice_sha256": result.decoded_slice_sha256(),
            "prompt_utf8_sha256": PROMPT_SHA256,
            "activation_sha256": result.activation_sha256(),
        },
        "oracle_identity": {
            "record": REFERENCE_RESULT_PATH,
            "project": "ggml-org/llama.cpp",
            "component": "gguf-py",
            "immutable_revision": REFERENCE_REVISION,
            "output_sha256": reference.output_sha256,
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
        "comparison_policy": {
            "mode": "absolute_plus_relative",
            "pass_expression": "abs(candidate-reference) <= absolute_tolerance + relative_tolerance * abs(reference)",
            "absolute_tolerance": REAL_ATOL,
            "relative_tolerance": REAL_RTOL,
            "non_finite_policy": "reject",
            "required_compared_count": REAL_OUTPUT_COUNT,
            "allowed_mismatch_count": 0,
        },
        "actual_values_or_bounded_summary": {
            "output_value_count": result.actual().len(),
            "output_sha256": result.output_sha256(),
            "mismatch_count": numeric.mismatch_count,
            "max_absolute_error": numeric.max_absolute_error,
            "max_relative_error": numeric.max_relative_error,
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
        "failures": failures,
        "exclusions": [
            "The prompt is consumed by a transparent SHA-256 probe adapter, not Qwen tokenization or embedding.",
            "No router, full expert, full layer, attention, logits, tokens, generation, serving, or benchmark was exercised.",
            "This bounded intermediate does not establish giant-model inference."
        ],
        "artifact_paths": [
            "docs/validation/models/qwen3-30b-a3b-q8_0-reference-result.json",
            "docs/validation/qwen3-30b-a3b-q8_0-slice.json",
            format!("<external-model>/{QWEN_FILENAME}"),
        ],
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

fn write_evidence_exclusive(path: &Path, evidence: &Value) -> Result<(), String> {
    let parent = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    if !parent.is_dir() {
        return Err("the evidence parent directory does not exist".to_owned());
    }
    if fs::symlink_metadata(path).is_ok() {
        return Err("the router fixture evidence destination already exists".to_owned());
    }
    let filename = path
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(|| "the evidence path must name a UTF-8 file".to_owned())?;
    let mut encoded = serde_json::to_vec(evidence)
        .map_err(|_| "the validated evidence could not be encoded".to_owned())?;
    encoded.push(b'\n');

    let mut temporary = None;
    for attempt in 0..32_u32 {
        let candidate = parent.join(format!(
            ".{filename}.pulsarmlx-exclusive-{}-{attempt}.tmp",
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
    if temporary_file
        .write_all(&encoded)
        .and_then(|()| temporary_file.sync_all())
        .is_err()
    {
        drop(temporary_file);
        let _ = fs::remove_file(&temporary_path);
        return Err("the requested evidence file could not be written".to_owned());
    }
    drop(temporary_file);

    let installed = fs::hard_link(&temporary_path, path);
    let _ = fs::remove_file(&temporary_path);
    match installed {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
            Err("the router fixture evidence destination already exists".to_owned())
        }
        Err(_) => Err("the requested evidence file could not be installed atomically".to_owned()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::LazyLock;

    static ORCHESTRATION_SINGLE_OUTPUT: LazyLock<RouterOutput> =
        LazyLock::new(|| build_orchestration_output(OrchestratedRouterCase::SingleRow));
    static ORCHESTRATION_TWO_ROW_OUTPUT: LazyLock<RouterOutput> =
        LazyLock::new(|| build_orchestration_output(OrchestratedRouterCase::TwoRow));
    static ORCHESTRATION_SINGLE_HASH: LazyLock<String> = LazyLock::new(|| {
        complete_router_output_sha256(&ORCHESTRATION_SINGLE_OUTPUT)
            .expect("single-row orchestration output hash")
    });
    static ORCHESTRATION_TWO_ROW_HASH: LazyLock<String> = LazyLock::new(|| {
        complete_router_output_sha256(&ORCHESTRATION_TWO_ROW_OUTPUT)
            .expect("two-row orchestration output hash")
    });

    #[derive(Clone, Copy)]
    struct OrchestrationTimingLabels<'a> {
        process_state: &'a str,
        condition: &'a str,
        external_costly: bool,
    }

    fn args(values: &[&str]) -> Vec<OsString> {
        values.iter().map(OsString::from).collect()
    }

    fn build_orchestration_output(case: OrchestratedRouterCase) -> RouterOutput {
        let mut logits = Vec::with_capacity(case.row_count() * 128);
        let mut full_probabilities = Vec::with_capacity(case.row_count() * 128);
        let mut selected_expert_ids = Vec::with_capacity(case.row_count());
        let mut selected_probabilities = Vec::with_capacity(case.row_count());
        let mut normalized_weights = Vec::with_capacity(case.row_count());
        for row in 0..case.row_count() {
            let row_logits = (0..128)
                .map(|expert| 4.0_f32 - expert as f32 * 0.05 + row as f32 * 0.001)
                .collect::<Vec<_>>();
            let maximum = row_logits.iter().copied().reduce(f32::max).unwrap();
            let exponentials = row_logits
                .iter()
                .map(|value| (f64::from(*value) - f64::from(maximum)).exp())
                .collect::<Vec<_>>();
            let denominator = exponentials.iter().sum::<f64>();
            let probabilities = exponentials
                .iter()
                .map(|value| (value / denominator) as f32)
                .collect::<Vec<_>>();
            let ids = (0_u64..8).collect::<Vec<_>>();
            let selected = probabilities[..8].to_vec();
            let selected_sum = selected.iter().copied().map(f64::from).sum::<f64>();
            let normalized = selected
                .iter()
                .map(|value| (f64::from(*value) / selected_sum) as f32)
                .collect::<Vec<_>>();
            logits.extend(row_logits);
            full_probabilities.extend(probabilities);
            selected_expert_ids.push(ids);
            selected_probabilities.push(selected);
            normalized_weights.push(normalized);
        }
        RouterOutput::try_new(
            case.case_id(),
            RouterCaseScope::RealCheckpoint,
            case.row_count(),
            logits,
            full_probabilities,
            selected_expert_ids,
            selected_probabilities,
            normalized_weights,
        )
        .expect("valid bounded orchestration output")
    }

    fn orchestration_output(case: OrchestratedRouterCase) -> &'static RouterOutput {
        match case {
            OrchestratedRouterCase::SingleRow => &ORCHESTRATION_SINGLE_OUTPUT,
            OrchestratedRouterCase::TwoRow => &ORCHESTRATION_TWO_ROW_OUTPUT,
        }
    }

    fn orchestration_hash(case: OrchestratedRouterCase) -> &'static str {
        match case {
            OrchestratedRouterCase::SingleRow => ORCHESTRATION_SINGLE_HASH.as_str(),
            OrchestratedRouterCase::TwoRow => ORCHESTRATION_TWO_ROW_HASH.as_str(),
        }
    }

    fn router_result_from_output(output: &RouterOutput) -> RouterResult {
        let complete_rows = |values: &[f32]| {
            values
                .chunks_exact(128)
                .map(|row| row.iter().copied().map(f64::from).collect::<Vec<_>>())
                .collect::<Vec<_>>()
        };
        let selected_rows = |values: &[Vec<f32>]| {
            values
                .iter()
                .map(|row| row.iter().copied().map(f64::from).collect::<Vec<_>>())
                .collect::<Vec<_>>()
        };
        serde_json::from_value(json!({
            "router_case_id": output.case_id(),
            "operation": "complete_router_projection_topk",
            "requested_device": GPU_DEVICE,
            "selected_device": GPU_DEVICE,
            "fallback_used": false,
            "evaluated": true,
            "synchronized": true,
            "batch_size": output.row_count(),
            "hidden_width": 2048,
            "expert_count": 128,
            "top_k": 8,
            "output_dtype": "float32",
            "logits": complete_rows(output.logits()),
            "full_probabilities": complete_rows(output.full_probabilities()),
            "selected_expert_ids": output.selected_expert_ids(),
            "selected_probabilities": selected_rows(output.selected_probabilities()),
            "normalized_weights": selected_rows(output.normalized_weights()),
            "logits_f32le_sha256": output.logits_f32le_sha256(),
            "full_probabilities_f32le_sha256": output.full_probabilities_f32le_sha256(),
            "selected_probabilities_f32le_sha256": output.selected_probabilities_f32le_sha256(),
            "normalized_weights_f32le_sha256": output.normalized_weights_f32le_sha256(),
            "memory_gauges": {
                "mlx_active_bytes": null,
                "mlx_cache_bytes": null,
                "mlx_peak_bytes": null,
                "process_footprint_bytes": null,
                "process_footprint_source": null,
                "system_pressure": null,
                "reported_summed_total_bytes": null
            },
            "timing": {
                "monotonic_clock": "perf_counter_ns",
                "instrumentation_mode": "minimally_instrumented",
                "evaluated": true,
                "synchronized": true,
                "stages": {
                    "dequantization": {
                        "status": "not_applicable",
                        "reason": "f32_router_requires_no_dequantization"
                    },
                    "total_evaluated_router": {
                        "status": "observed",
                        "duration_ns": 1_000
                    }
                }
            },
            "passed": true
        }))
        .expect("bounded worker result fixture")
    }

    fn correctness_attempts(
        batch_id: &str,
        case: OrchestratedRouterCase,
    ) -> Vec<RouterCorrectnessAttempt> {
        let output = orchestration_output(case);
        let numeric_comparison = |compared_count: usize, absolute: f64, relative: f64| {
            json!({
                "compared_count": compared_count,
                "mismatch_count": 0,
                "first_mismatch": null,
                "maximum_absolute_error": 0.0,
                "mean_absolute_error": 0.0,
                "rmse": 0.0,
                "maximum_relative_error": 0.0,
                "absolute_tolerance": absolute,
                "relative_tolerance": relative,
            })
        };
        let comparison = json!({
            "logits": numeric_comparison(case.row_count() * 128, 5.0e-4, 5.0e-4),
            "full_probabilities": numeric_comparison(case.row_count() * 128, 1.0e-6, 1.0e-6),
            "selected_probabilities": numeric_comparison(case.row_count() * 8, 1.0e-6, 1.0e-6),
            "normalized_weights": numeric_comparison(case.row_count() * 8, 1.0e-6, 1.0e-6),
            "expert_range_comparisons": {
                "0..16": {
                    "logits": numeric_comparison(case.row_count() * 16, 5.0e-4, 5.0e-4),
                    "full_probabilities": numeric_comparison(
                        case.row_count() * 16,
                        1.0e-6,
                        1.0e-6,
                    ),
                    "passed": true,
                },
                "64..80": {
                    "logits": numeric_comparison(case.row_count() * 16, 5.0e-4, 5.0e-4),
                    "full_probabilities": numeric_comparison(
                        case.row_count() * 16,
                        1.0e-6,
                        1.0e-6,
                    ),
                    "passed": true,
                },
            },
            "id_mismatch_count": 0,
            "order_mismatch_count": 0,
            "passed": true,
        });
        (0..ROUTER_CORRECTNESS_ATTEMPTS)
            .map(|_| RouterCorrectnessAttempt {
                case_id: case.case_id().to_owned(),
                process_replication_id: correctness_process_identity(batch_id),
                logits_f32le_sha256: output.logits_f32le_sha256().to_owned(),
                full_probabilities_f32le_sha256: output
                    .full_probabilities_f32le_sha256()
                    .to_owned(),
                selected_expert_ids: output.selected_expert_ids().to_vec(),
                selected_expert_ids_u32le_sha256: selected_id_sha256(output.selected_expert_ids())
                    .expect("bounded selected expert ID hash"),
                selected_probabilities_f32le_sha256: output
                    .selected_probabilities_f32le_sha256()
                    .to_owned(),
                normalized_weights_f32le_sha256: output
                    .normalized_weights_f32le_sha256()
                    .to_owned(),
                complete_output_sha256: orchestration_hash(case).to_owned(),
                canonical_output: output.clone(),
                comparison: comparison.clone(),
                memory_gauges: json!({
                    "mlx_active_bytes": null,
                    "mlx_cache_bytes": null,
                    "mlx_peak_bytes": null,
                    "process_footprint_bytes": null,
                    "process_footprint_source": null,
                    "system_pressure": null,
                    "reported_summed_total_bytes": null,
                }),
                result_passed: true,
                requested_device: GPU_DEVICE.to_owned(),
                selected_device: GPU_DEVICE.to_owned(),
                fallback_used: false,
                evaluated: true,
                synchronized: true,
            })
            .collect()
    }

    fn orchestration_timing_observation(
        series_id: &str,
        kind: &str,
        run_index: usize,
        process_replication_id: &str,
        labels: OrchestrationTimingLabels<'_>,
        instrumentation_mode: &str,
        output_sha256: &str,
    ) -> Value {
        let stages = if instrumentation_mode == "stage_instrumented" {
            json!({
                "setup_admission": {
                    "status": "unavailable",
                    "reason": "not_separately_observed_in_model_free_fixture"
                },
                "file_io": {
                    "status": "unavailable",
                    "reason": "not_separately_observed_in_model_free_fixture"
                },
                "storage_validation_f32_decode": {
                    "status": "unavailable",
                    "reason": "not_separately_observed_in_model_free_fixture"
                },
                "dequantization": {
                    "status": "not_applicable",
                    "reason": "f32_router_requires_no_dequantization"
                },
                "host_to_device": {
                    "status": "unavailable",
                    "reason": "not_separately_observed_in_model_free_fixture"
                },
                "graph_construction": {
                    "status": "unavailable",
                    "reason": "not_separately_observed_in_model_free_fixture"
                },
                "compilation": {
                    "status": "unavailable",
                    "reason": "not_separately_observed_in_model_free_fixture"
                },
                "router_projection": {
                    "status": "observed",
                    "duration_ns": 500_u64 + u64::try_from(run_index).unwrap()
                },
                "top_k": {
                    "status": "unavailable",
                    "reason": "not_separately_observed_in_model_free_fixture"
                },
                "normalization": {
                    "status": "unavailable",
                    "reason": "not_separately_observed_in_model_free_fixture"
                },
                "total_evaluated_router": {
                    "status": "observed",
                    "duration_ns": 1_000_u64 + u64::try_from(run_index).unwrap()
                },
                "synchronized_readback": {
                    "status": "unavailable",
                    "reason": "not_separately_observed_in_model_free_fixture"
                },
                "end_to_end_router_command": {
                    "status": "unavailable",
                    "reason": "not_separately_observed_in_model_free_fixture"
                }
            })
        } else if labels.external_costly {
            json!({
                "file_io": {
                    "status": "observed",
                    "duration_ns": 250_u64 + u64::try_from(run_index).unwrap()
                },
                "storage_validation_f32_decode": {
                    "status": "observed",
                    "duration_ns": 300_u64 + u64::try_from(run_index).unwrap()
                },
                "dequantization": {
                    "status": "not_applicable",
                    "reason": "f32_router_requires_no_dequantization"
                },
                "host_to_device": {
                    "status": "unavailable",
                    "reason": "not_separately_observed_in_model_free_fixture"
                },
                "total_evaluated_router": {
                    "status": "observed",
                    "duration_ns": 1_000_u64 + u64::try_from(run_index).unwrap()
                },
                "end_to_end_router_command": {
                    "status": "observed",
                    "duration_ns": 2_000_u64 + u64::try_from(run_index).unwrap()
                }
            })
        } else {
            json!({
                "dequantization": {
                    "status": "not_applicable",
                    "reason": "f32_router_requires_no_dequantization"
                },
                "total_evaluated_router": {
                    "status": "observed",
                    "duration_ns": 1_000_u64 + u64::try_from(run_index).unwrap()
                }
            })
        };
        json!({
            "observation_id": format!(
                "{process_replication_id}-{series_id}-{kind}-{run_index:02}"
            ),
            "run_index": run_index,
            "observation_kind": kind,
            "process_replication_id": process_replication_id,
            "process_state": labels.process_state,
            "condition": labels.condition,
            "instrumentation_mode": instrumentation_mode,
            "monotonic_clock": "perf_counter_ns",
            "stages": stages,
            "status": "passed",
            "requested_device": GPU_DEVICE,
            "selected_device": GPU_DEVICE,
            "fallback_used": false,
            "evaluated": true,
            "synchronized": true,
            "output_sha256": output_sha256,
            "correctness_passed": true
        })
    }

    fn orchestration_major_series(
        case: OrchestratedRouterCase,
        role: RouterTimingReplicationRole,
        process_replication_id: &str,
        output_sha256: &str,
    ) -> RouterTimingSeries {
        let process_state = match role {
            RouterTimingReplicationRole::Primary => "reused_process",
            RouterTimingReplicationRole::CleanProcessReplication => "fresh_process",
        };
        let mut observations = Vec::with_capacity(35);
        observations.extend((0..5).map(|index| {
            orchestration_timing_observation(
                case.benchmark_id(),
                "warmup",
                index,
                process_replication_id,
                OrchestrationTimingLabels {
                    process_state,
                    condition: "warm",
                    external_costly: false,
                },
                "minimally_instrumented",
                output_sha256,
            )
        }));
        observations.extend((0..30).map(|index| {
            orchestration_timing_observation(
                case.benchmark_id(),
                "measurement",
                index,
                process_replication_id,
                OrchestrationTimingLabels {
                    process_state,
                    condition: "warm",
                    external_costly: false,
                },
                "minimally_instrumented",
                output_sha256,
            )
        }));
        RouterTimingSeries::try_from_value(json!({
            "benchmark_id": case.benchmark_id(),
            "case_id": case.case_id(),
            "row_count": case.row_count(),
            "series_kind": "major_minimally_instrumented",
            "replication_role": match role {
                RouterTimingReplicationRole::Primary => "primary",
                RouterTimingReplicationRole::CleanProcessReplication => {
                    "clean_process_replication"
                }
            },
            "process_replication_id": process_replication_id,
            "process_state": process_state,
            "condition": "warm",
            "instrumentation_mode": "minimally_instrumented",
            "warmup_count": 5,
            "measurement_count": 30,
            "raw_timing_observations": observations
        }))
        .expect("valid orchestration timing series")
    }

    fn orchestration_auxiliary_series(
        case: OrchestratedRouterCase,
        series_kind: RouterTimingSeriesKind,
        process_replication_id: &str,
    ) -> RouterTimingSeries {
        let (kind, mode, benchmark_prefix, process_state, condition, warmups, measurements) =
            match series_kind {
                RouterTimingSeriesKind::CostlyReal => (
                    "costly_real",
                    "minimally_instrumented",
                    "f002-costly-real",
                    "reused_process",
                    "warm",
                    5,
                    10,
                ),
                RouterTimingSeriesKind::FirstProcessCostly => (
                    "first_process_costly",
                    "minimally_instrumented",
                    "f002-first-process-costly",
                    "fresh_process",
                    "first_read_new_process_os_cache_uncontrolled",
                    0,
                    1,
                ),
                RouterTimingSeriesKind::StageDiagnostic => (
                    "stage_diagnostic",
                    "stage_instrumented",
                    "f002-stage-diagnostic",
                    "reused_process",
                    "warm",
                    5,
                    10,
                ),
                _ => panic!("test helper accepts only orchestration auxiliary series"),
            };
        let case_label = match case {
            OrchestratedRouterCase::SingleRow => "single-row",
            OrchestratedRouterCase::TwoRow => "two-row",
        };
        let benchmark_id = format!("{benchmark_prefix}-{case_label}-v1");
        let mut observations = Vec::with_capacity(warmups + measurements);
        observations.extend((0..warmups).map(|index| {
            orchestration_timing_observation(
                &benchmark_id,
                "warmup",
                index,
                process_replication_id,
                OrchestrationTimingLabels {
                    process_state,
                    condition,
                    external_costly: matches!(
                        series_kind,
                        RouterTimingSeriesKind::CostlyReal
                            | RouterTimingSeriesKind::FirstProcessCostly
                    ),
                },
                mode,
                orchestration_hash(case),
            )
        }));
        observations.extend((0..measurements).map(|index| {
            orchestration_timing_observation(
                &benchmark_id,
                "measurement",
                index,
                process_replication_id,
                OrchestrationTimingLabels {
                    process_state,
                    condition,
                    external_costly: matches!(
                        series_kind,
                        RouterTimingSeriesKind::CostlyReal
                            | RouterTimingSeriesKind::FirstProcessCostly
                    ),
                },
                mode,
                orchestration_hash(case),
            )
        }));
        RouterTimingSeries::try_from_value(json!({
            "benchmark_id": benchmark_id,
            "case_id": case.case_id(),
            "row_count": case.row_count(),
            "series_kind": kind,
            "replication_role": "primary",
            "process_replication_id": process_replication_id,
            "process_state": process_state,
            "condition": condition,
            "instrumentation_mode": mode,
            "warmup_count": warmups,
            "measurement_count": measurements,
            "raw_timing_observations": observations
        }))
        .expect("valid orchestration auxiliary series")
    }

    fn retained_failed_series(
        series: &RouterTimingSeries,
        failure_code: &str,
        failure_stage: &str,
    ) -> RouterTimingSeries {
        let mut value = series.try_to_value().expect("serialized timing series");
        let failure_index = if series.raw_timing_observations().len() > 6 {
            6
        } else {
            0
        };
        value["raw_timing_observations"][failure_index]["status"] = json!("failed");
        value["raw_timing_observations"][failure_index]["correctness_passed"] = json!(false);
        value["raw_timing_observations"][failure_index]["failure"] = json!({
            "code": failure_code,
            "message": "bounded retained orchestration failure",
            "stage": failure_stage
        });
        RouterTimingSeries::try_from_value(value).expect("retained failed timing series")
    }

    fn orchestrator_with_correctness_gates() -> RouterBenchmarkOrchestrator {
        let mut orchestration = RouterBenchmarkOrchestrator::new();
        for case in ROUTER_CORRECTNESS_ORDER {
            for attempt in correctness_attempts(ROUTER_PRIMARY_BATCH_ID, case) {
                orchestration
                    .record_correctness_attempt(case, attempt)
                    .expect("correctness attempt in frozen order");
            }
        }
        orchestration
    }

    fn orchestrator_with_correctness() -> RouterBenchmarkOrchestrator {
        let mut orchestration = orchestrator_with_correctness_gates();
        for repetition_index in 0..ROUTER_FIRST_PROCESS_REPETITIONS {
            orchestration
                .record_primary_first_process_series(orchestration_auxiliary_series(
                    ROUTER_COSTLY_ORDER[0],
                    RouterTimingSeriesKind::FirstProcessCostly,
                    &primary_first_process_identity(ROUTER_PRIMARY_BATCH_ID, repetition_index),
                ))
                .expect("correctness gates each fresh primary timing worker first read");
        }
        orchestration
    }

    fn record_primary_schedule(orchestration: &mut RouterBenchmarkOrchestrator) {
        let primary_process = primary_process_identity(ROUTER_PRIMARY_BATCH_ID);
        for case in ROUTER_COSTLY_ORDER {
            orchestration
                .record_costly_series(orchestration_auxiliary_series(
                    case,
                    RouterTimingSeriesKind::CostlyReal,
                    &primary_process,
                ))
                .expect("costly series in frozen order");
        }
        for (case, role) in ROUTER_PRIMARY_MAJOR_ORDER {
            orchestration
                .record_primary_major_series(orchestration_major_series(
                    case,
                    role,
                    &primary_process,
                    orchestration_hash(case),
                ))
                .expect("major series in frozen order");
        }
        for case in ROUTER_STAGE_DIAGNOSTIC_ORDER {
            orchestration
                .record_stage_diagnostic_series(orchestration_auxiliary_series(
                    case,
                    RouterTimingSeriesKind::StageDiagnostic,
                    &primary_process,
                ))
                .expect("stage diagnostic in frozen order");
        }
        for (case, role) in ROUTER_CLEAN_MAJOR_ORDER {
            let clean_process = clean_process_identity(ROUTER_PRIMARY_BATCH_ID, case);
            for repetition_index in 0..ROUTER_FIRST_PROCESS_REPETITIONS {
                orchestration
                    .record_clean_first_process_series(orchestration_auxiliary_series(
                        case,
                        RouterTimingSeriesKind::FirstProcessCostly,
                        &clean_first_process_identity(
                            ROUTER_PRIMARY_BATCH_ID,
                            case,
                            repetition_index,
                        ),
                    ))
                    .expect("clean first-process cohort in frozen order");
            }
            orchestration
                .record_clean_major_series(orchestration_major_series(
                    case,
                    role,
                    &clean_process,
                    orchestration_hash(case),
                ))
                .expect("clean major series in frozen order");
        }
    }

    fn second_batch_candidate(batch_id: &str) -> RouterSecondBatchCandidate {
        let mut candidate = RouterBenchmarkOrchestrator::new_second(batch_id)
            .expect("valid independent second-batch identity");
        let primary_process = primary_process_identity(batch_id);
        for case in ROUTER_SECOND_CORRECTNESS_ORDER {
            for attempt in correctness_attempts(batch_id, case) {
                candidate
                    .record_correctness_attempt(case, attempt)
                    .expect("second correctness attempt in reversed order");
            }
        }
        for repetition_index in 0..ROUTER_FIRST_PROCESS_REPETITIONS {
            candidate
                .record_primary_first_process_series(orchestration_auxiliary_series(
                    ROUTER_SECOND_COSTLY_ORDER[0],
                    RouterTimingSeriesKind::FirstProcessCostly,
                    &primary_first_process_identity(batch_id, repetition_index),
                ))
                .expect("second correctness gates each fresh primary worker first read");
        }
        for case in ROUTER_SECOND_COSTLY_ORDER {
            candidate
                .record_costly_series(orchestration_auxiliary_series(
                    case,
                    RouterTimingSeriesKind::CostlyReal,
                    &primary_process,
                ))
                .expect("second costly series in reversed order");
        }
        for (case, role) in ROUTER_SECOND_PRIMARY_MAJOR_ORDER {
            candidate
                .record_primary_major_series(orchestration_major_series(
                    case,
                    role,
                    &primary_process,
                    orchestration_hash(case),
                ))
                .expect("second primary major in reversed order");
        }
        for case in ROUTER_SECOND_STAGE_DIAGNOSTIC_ORDER {
            candidate
                .record_stage_diagnostic_series(orchestration_auxiliary_series(
                    case,
                    RouterTimingSeriesKind::StageDiagnostic,
                    &primary_process,
                ))
                .expect("second stage diagnostic in reversed order");
        }
        for (case, role) in ROUTER_SECOND_CLEAN_MAJOR_ORDER {
            let clean_process = clean_process_identity(batch_id, case);
            for repetition_index in 0..ROUTER_FIRST_PROCESS_REPETITIONS {
                candidate
                    .record_clean_first_process_series(orchestration_auxiliary_series(
                        case,
                        RouterTimingSeriesKind::FirstProcessCostly,
                        &clean_first_process_identity(batch_id, case, repetition_index),
                    ))
                    .expect("second clean first-process cohort");
            }
            candidate
                .record_clean_major_series(orchestration_major_series(
                    case,
                    role,
                    &clean_process,
                    orchestration_hash(case),
                ))
                .expect("second clean major in reversed order");
        }
        candidate
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
    fn feature_002_router_commands_accept_only_the_frozen_argument_surfaces() {
        let model = format!("/tmp/pulsarmlx-feature-002/{QWEN_FILENAME}");
        let inspection = parse_inspect_router(args(&[
            "inspect-router",
            "--evidence",
            "/tmp/pulsarmlx-feature-002/router-inspection.json",
            "--model",
            &model,
        ]))
        .expect("exact inspect-router surface");
        assert_eq!(inspection.model, PathBuf::from(&model));

        let fixtures = parse_validate_router_fixtures(args(&[
            "validate-router-fixtures",
            "--manifest",
            ROUTER_FIXTURE_MANIFEST,
            "--evidence",
            "/tmp/pulsarmlx-feature-002/router-fixtures.json",
        ]))
        .expect("exact fixture surface");
        assert_eq!(fixtures.manifest, PathBuf::from(ROUTER_FIXTURE_MANIFEST));

        let validation = parse_validate_router(args(&[
            "validate-router",
            "--oracle",
            "/tmp/pulsarmlx-feature-002/oracle.json",
            "--evidence-dir",
            "/tmp/pulsarmlx-feature-002/attempts",
            "--model",
            &model,
        ]))
        .expect("exact validate-router surface");
        assert_eq!(validation.model, PathBuf::from(model));

        let repository_evidence = lexical_project_root().join("router-inspection.json");
        for invalid in [
            args(&[
                "inspect-router",
                "--model",
                QWEN_FILENAME,
                "--evidence",
                "/tmp/router-inspection.json",
            ]),
            args(&[
                "inspect-router",
                "--model",
                &format!("/tmp/../tmp/{QWEN_FILENAME}"),
                "--evidence",
                "/tmp/router-inspection.json",
            ]),
            args(&[
                "inspect-router",
                "--model",
                "/tmp/not-the-admitted-model.gguf",
                "--evidence",
                "/tmp/router-inspection.json",
            ]),
            args(&[
                "inspect-router",
                "--model",
                &format!("/tmp/{QWEN_FILENAME}"),
                "--evidence",
                repository_evidence
                    .to_str()
                    .expect("repository test path is UTF-8"),
            ]),
            args(&[
                "validate-router-fixtures",
                "--manifest",
                "fixtures/research/router-v1/other.json",
                "--evidence",
                "/tmp/router-fixtures.json",
            ]),
            args(&[
                "validate-router-fixtures",
                "--manifest",
                ROUTER_FIXTURE_MANIFEST,
                "--evidence",
                "relative-router-fixtures.json",
            ]),
            args(&[
                "validate-router",
                "--model",
                &format!("/tmp/{QWEN_FILENAME}"),
                "--oracle",
                "/tmp/oracle.json",
                "--warmups",
                "1",
            ]),
            args(&[
                "validate-router",
                "--model",
                &format!("/tmp/{QWEN_FILENAME}"),
                "--oracle",
                "/tmp/oracle.json",
                "--evidence-dir",
                &format!("/tmp/{QWEN_FILENAME}"),
            ]),
        ] {
            let command = invalid
                .first()
                .and_then(|value| value.to_str())
                .expect("test command");
            let result = match command {
                "inspect-router" => parse_inspect_router(invalid).map(|_| ()),
                "validate-router-fixtures" => parse_validate_router_fixtures(invalid).map(|_| ()),
                "validate-router" => parse_validate_router(invalid).map(|_| ()),
                _ => unreachable!("bounded command inventory"),
            };
            assert!(result.is_err());
        }
    }

    #[cfg(unix)]
    #[test]
    fn feature_002_router_paths_reject_symlink_hard_link_and_containment_aliases() {
        use std::os::unix::fs::symlink;
        use std::time::{SystemTime, UNIX_EPOCH};

        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system clock")
            .as_nanos();
        let directory = env::temp_dir().join(format!(
            "pulsarmlx-router-path-safety-{}-{nonce}",
            std::process::id()
        ));
        let model_directory = directory.join("model");
        fs::create_dir_all(&model_directory).expect("create model directory");
        let model = model_directory.join(QWEN_FILENAME);
        fs::write(&model, b"bounded-model-stand-in").expect("write model stand-in");

        let ordinary_evidence = directory.join("ordinary-evidence.json");
        let ordinary_command = parse_inspect_router(args(&[
            "inspect-router",
            "--model",
            model.to_str().expect("UTF-8 model path"),
            "--evidence",
            ordinary_evidence.to_str().expect("UTF-8 evidence path"),
        ]))
        .expect("ordinary distinct external paths remain accepted");
        validate_inspect_router_path_identities(&ordinary_command)
            .expect("ordinary filesystem identities remain accepted");

        let symlink_directory = directory.join("symlink-model");
        fs::create_dir(&symlink_directory).expect("create symlink directory");
        let symlink_model = symlink_directory.join(QWEN_FILENAME);
        symlink(&model, &symlink_model).expect("create model symlink");
        let symlink_command = parse_inspect_router(args(&[
            "inspect-router",
            "--model",
            symlink_model.to_str().expect("UTF-8 symlink path"),
            "--evidence",
            ordinary_evidence.to_str().expect("UTF-8 evidence path"),
        ]))
        .expect("the pre-T074 parser remains lexical-only");
        let gated_error = run(args(&[
            "inspect-router",
            "--model",
            symlink_model.to_str().expect("UTF-8 symlink path"),
            "--evidence",
            ordinary_evidence.to_str().expect("UTF-8 evidence path"),
        ]))
        .expect_err("pre-T074 dispatch remains task gated");
        assert!(gated_error.contains("T074"));
        assert!(gated_error.contains("no checkpoint was accessed"));
        let symlink_error = validate_inspect_router_path_identities(&symlink_command)
            .expect_err("post-gate symbolic-link model alias must fail closed");
        assert!(symlink_error.contains("symbolic-link alias"));

        let hard_link_evidence = directory.join("hard-link-evidence.json");
        fs::hard_link(&model, &hard_link_evidence).expect("create evidence hard link");
        let hard_link_command = parse_inspect_router(args(&[
            "inspect-router",
            "--model",
            model.to_str().expect("UTF-8 model path"),
            "--evidence",
            hard_link_evidence
                .to_str()
                .expect("UTF-8 hard-link evidence path"),
        ]))
        .expect("the pre-T074 parser remains lexical-only");
        let hard_link_error = validate_inspect_router_path_identities(&hard_link_command)
            .expect_err("post-gate hard-link model/evidence alias must fail closed");
        assert_eq!(hard_link_error, "router inspection paths must be distinct");

        let oracle = model_directory.join("oracle.json");
        fs::write(&oracle, b"{}").expect("write oracle stand-in");
        let containment_command = ValidateRouterCommand {
            model: model.clone(),
            oracle: oracle.clone(),
            evidence_dir: model_directory.clone(),
        };
        let containment_error = validate_router_path_identities(&containment_command)
            .expect_err("a result directory containing inputs must fail closed");
        assert_eq!(
            containment_error,
            "router model, oracle, and evidence paths must be distinct"
        );
        assert!(parse_validate_router(args(&[
            "validate-router",
            "--model",
            model.to_str().expect("UTF-8 model path"),
            "--oracle",
            oracle.to_str().expect("UTF-8 oracle path"),
            "--evidence-dir",
            model_directory
                .to_str()
                .expect("UTF-8 containing directory path"),
        ]))
        .is_err());

        let repository_link = directory.join("repository-link");
        symlink(
            fs::canonicalize(lexical_project_root()).expect("canonical repository root"),
            &repository_link,
        )
        .expect("create repository link");
        let linked_repository_command = parse_validate_router_fixtures(args(&[
            "validate-router-fixtures",
            "--manifest",
            ROUTER_FIXTURE_MANIFEST,
            "--evidence",
            repository_link
                .join("router-evidence.json")
                .to_str()
                .expect("UTF-8 linked repository path"),
        ]))
        .expect("the pre-T045 parser remains lexical-only");
        let linked_repository_error =
            validate_router_fixture_path_identities(&linked_repository_command)
                .expect_err("a symlinked path into the repository must fail closed");
        assert!(linked_repository_error.contains("outside the repository"));

        let committed_manifest = lexical_project_root().join(ROUTER_FIXTURE_MANIFEST);
        let manifest_hard_link = directory.join("manifest-hard-link.json");
        fs::hard_link(&committed_manifest, &manifest_hard_link)
            .expect("create committed-manifest hard link");
        let manifest_alias_command = parse_validate_router_fixtures(args(&[
            "validate-router-fixtures",
            "--manifest",
            ROUTER_FIXTURE_MANIFEST,
            "--evidence",
            manifest_hard_link
                .to_str()
                .expect("UTF-8 manifest hard-link path"),
        ]))
        .expect("the pre-T045 parser remains lexical-only");
        let manifest_alias_error = validate_router_fixture_path_identities(&manifest_alias_command)
            .expect_err("hard-link alias to committed input must fail closed");
        assert_eq!(
            manifest_alias_error,
            "router fixture paths must be distinct"
        );

        fs::remove_dir_all(&directory).expect("remove path-safety fixture directory");
    }

    #[cfg(unix)]
    #[test]
    fn feature_002_router_parsers_reject_non_utf8_arguments() {
        use std::os::unix::ffi::OsStringExt;

        let invalid = vec![
            OsString::from("inspect-router"),
            OsString::from("--model"),
            OsString::from_vec(vec![0xff]),
            OsString::from("--evidence"),
            OsString::from("/tmp/router-inspection.json"),
        ];
        assert_eq!(
            parse_inspect_router(invalid).expect_err("non-UTF-8 must fail"),
            "command arguments must be valid UTF-8"
        );
    }

    #[test]
    fn router_benchmark_orchestration_requires_exact_correctness_before_timing() {
        let single = OrchestratedRouterCase::SingleRow;
        let two_row = OrchestratedRouterCase::TwoRow;

        let produced_result = router_result_from_output(orchestration_output(single));
        let adapted = RouterCorrectnessAttempt::from_result(
            &produced_result,
            orchestration_output(single),
            correctness_process_identity(ROUTER_PRIMARY_BATCH_ID),
        )
        .expect("real-result adapter computes its own exact comparison and canonical output");
        assert!(adapted.passes_gate(ROUTER_PRIMARY_BATCH_ID, single));
        assert_eq!(adapted.canonical_output, *orchestration_output(single));
        assert_eq!(
            adapted.evidence(ROUTER_PRIMARY_BATCH_ID, 0)["backend"],
            BACKEND_ID
        );
        let self_comparison = compare_router_outputs(
            orchestration_output(single),
            orchestration_output(single),
            &RouterTolerancePolicy::contract_v1(),
        )
        .expect("self comparison");
        assert_eq!(
            router_positive_case_evidence(&produced_result, &self_comparison)["backend"],
            BACKEND_ID
        );

        let mut short = correctness_attempts(ROUTER_PRIMARY_BATCH_ID, single);
        short.pop();
        assert!(RouterCorrectnessGate::try_new(ROUTER_PRIMARY_BATCH_ID, single, short).is_err());

        let mut changed_hash = correctness_attempts(ROUTER_PRIMARY_BATCH_ID, single);
        changed_hash[9].complete_output_sha256 = orchestration_hash(two_row).to_owned();
        assert!(
            RouterCorrectnessGate::try_new(ROUTER_PRIMARY_BATCH_ID, single, changed_hash).is_err()
        );

        let mut changed_component = correctness_attempts(ROUTER_PRIMARY_BATCH_ID, single);
        changed_component[9].logits_f32le_sha256 = "c".repeat(64);
        assert!(
            RouterCorrectnessGate::try_new(ROUTER_PRIMARY_BATCH_ID, single, changed_component,)
                .is_err()
        );

        let mut changed_ids = correctness_attempts(ROUTER_PRIMARY_BATCH_ID, single);
        changed_ids[9].selected_expert_ids[0].swap(0, 1);
        assert!(
            RouterCorrectnessGate::try_new(ROUTER_PRIMARY_BATCH_ID, single, changed_ids,).is_err()
        );

        let mut invalid_metrics = correctness_attempts(ROUTER_PRIMARY_BATCH_ID, single);
        invalid_metrics[3].comparison["logits"]["mismatch_count"] = json!(1);
        assert!(
            RouterCorrectnessGate::try_new(ROUTER_PRIMARY_BATCH_ID, single, invalid_metrics,)
                .is_err()
        );

        let mut relabeled_process = correctness_attempts(ROUTER_PRIMARY_BATCH_ID, single);
        relabeled_process[0].process_replication_id = "caller-supplied-process".to_owned();
        assert!(
            RouterCorrectnessGate::try_new(ROUTER_PRIMARY_BATCH_ID, single, relabeled_process,)
                .is_err()
        );

        for mutation in [
            |attempt: &mut RouterCorrectnessAttempt| attempt.comparison["passed"] = json!(false),
            |attempt: &mut RouterCorrectnessAttempt| attempt.result_passed = false,
            |attempt: &mut RouterCorrectnessAttempt| attempt.fallback_used = true,
            |attempt: &mut RouterCorrectnessAttempt| attempt.evaluated = false,
            |attempt: &mut RouterCorrectnessAttempt| attempt.synchronized = false,
        ] {
            let mut attempts = correctness_attempts(ROUTER_PRIMARY_BATCH_ID, single);
            mutation(&mut attempts[4]);
            assert!(
                RouterCorrectnessGate::try_new(ROUTER_PRIMARY_BATCH_ID, single, attempts).is_err()
            );
        }

        let mut premature_timing = RouterBenchmarkOrchestrator::new();
        let premature = orchestration_major_series(
            single,
            RouterTimingReplicationRole::Primary,
            "primary-process",
            orchestration_hash(single),
        );
        assert!(premature_timing
            .record_primary_major_series(premature)
            .is_err());
        let premature_evidence = premature_timing
            .evidence()
            .expect("premature timing is retained as terminal evidence");
        assert_eq!(premature_evidence["failure"]["code"], "comparison_failed");
        assert_eq!(
            premature_evidence["retained_timing"]["rejected_series"]
                .as_array()
                .expect("retained premature series")
                .len(),
            1
        );
        assert!(premature_evidence["raw_observations"]
            .as_array()
            .is_some_and(|observations| {
                observations.len() == 35
                    && observations.iter().enumerate().all(|(index, observation)| {
                        observation["global_order_index"] == index
                            && observation["batch_id"] == ROUTER_PRIMARY_BATCH_ID
                            && observation["schedule_step"] == "primary_major"
                            && observation["orchestration_status"] == "rejected"
                    })
            }));

        let mut wrong_order = RouterBenchmarkOrchestrator::new();
        assert!(wrong_order
            .record_correctness_attempt(
                two_row,
                correctness_attempts(ROUTER_PRIMARY_BATCH_ID, two_row).remove(0),
            )
            .is_err());
        let wrong_order_evidence = wrong_order
            .evidence()
            .expect("wrong-order attempt is terminal and retained");
        assert_eq!(
            wrong_order_evidence["retained_current_case_attempts"][0]["status"],
            "failed"
        );
        assert_eq!(
            wrong_order_evidence["raw_observations"][0]["global_order_index"],
            0
        );
        assert_eq!(
            wrong_order_evidence["raw_observations"][0]["case_id"],
            two_row.case_id()
        );
        assert_eq!(
            wrong_order_evidence["raw_observations"][0]["orchestration_status"],
            "rejected"
        );

        let mut orchestration = RouterBenchmarkOrchestrator::new();
        assert_eq!(orchestration.next_step(), "single_row_correctness");
        for attempt in correctness_attempts(ROUTER_PRIMARY_BATCH_ID, single) {
            orchestration
                .record_correctness_attempt(single, attempt)
                .expect("single-row correctness is first");
        }
        let mut duplicate_case = orchestration.clone();
        assert!(duplicate_case
            .record_correctness_attempt(
                single,
                correctness_attempts(ROUTER_PRIMARY_BATCH_ID, single).remove(0),
            )
            .is_err());
        let duplicate_evidence = duplicate_case
            .evidence()
            .expect("duplicate correctness identity remains ordered and retained");
        assert_eq!(
            duplicate_evidence["raw_observations"]
                .as_array()
                .expect("ordered duplicate ledger")
                .last()
                .expect("duplicate observation")["identity_duplicate"],
            true
        );
        for attempt in correctness_attempts(ROUTER_PRIMARY_BATCH_ID, two_row) {
            orchestration
                .record_correctness_attempt(two_row, attempt)
                .expect("two-row correctness is second");
        }
        assert_eq!(
            orchestration.next_step(),
            "primary_first_process_os_cache_uncontrolled"
        );

        let primary_process = primary_process_identity(ROUTER_PRIMARY_BATCH_ID);
        for repetition_index in 0..ROUTER_FIRST_PROCESS_REPETITIONS {
            orchestration
                .record_primary_first_process_series(orchestration_auxiliary_series(
                    single,
                    RouterTimingSeriesKind::FirstProcessCostly,
                    &primary_first_process_identity(ROUTER_PRIMARY_BATCH_ID, repetition_index),
                ))
                .expect("correctness gates each fresh timing worker first read");
        }
        assert_eq!(orchestration.next_step(), "single_row_costly_real");

        let mut premature_major = orchestration.clone();
        assert!(premature_major
            .record_primary_major_series(orchestration_major_series(
                single,
                RouterTimingReplicationRole::Primary,
                &primary_process,
                orchestration_hash(single),
            ))
            .is_err());
        for case in ROUTER_COSTLY_ORDER {
            orchestration
                .record_costly_series(orchestration_auxiliary_series(
                    case,
                    RouterTimingSeriesKind::CostlyReal,
                    &primary_process,
                ))
                .expect("costly series in frozen order");
        }
        assert_eq!(orchestration.next_step(), "single_row_primary_major");
        let mut ordered = orchestration.clone();

        let wrong_hash = orchestration_major_series(
            single,
            RouterTimingReplicationRole::Primary,
            &primary_process,
            orchestration_hash(two_row),
        );
        assert!(orchestration
            .record_primary_major_series(wrong_hash)
            .is_err());
        assert_eq!(orchestration.next_step(), "failed_stop_condition");
        let retained_wrong_hash = orchestration.evidence().expect("retained hash failure");
        assert_eq!(
            retained_wrong_hash["retained_timing"]["major_series"]
                .as_array()
                .expect("retained wrong-hash series")
                .len(),
            1
        );
        for (case, role) in ROUTER_PRIMARY_MAJOR_ORDER {
            ordered
                .record_primary_major_series(orchestration_major_series(
                    case,
                    role,
                    &primary_process,
                    orchestration_hash(case),
                ))
                .expect("primary majors in frozen order");
        }
        assert_eq!(ordered.next_step(), "single_row_stage_diagnostic");
        for case in ROUTER_STAGE_DIAGNOSTIC_ORDER {
            ordered
                .record_stage_diagnostic_series(orchestration_auxiliary_series(
                    case,
                    RouterTimingSeriesKind::StageDiagnostic,
                    &primary_process,
                ))
                .expect("stage diagnostics in frozen order");
        }
        assert_eq!(
            ordered.next_step(),
            "single_row_clean_first_process_os_cache_uncontrolled"
        );
        let mut premature_clean = ordered.clone();
        assert!(premature_clean
            .record_clean_major_series(orchestration_major_series(
                single,
                RouterTimingReplicationRole::CleanProcessReplication,
                &clean_process_identity(ROUTER_PRIMARY_BATCH_ID, single),
                orchestration_hash(single),
            ))
            .is_err());
        let failed_clean_first = retained_failed_series(
            &orchestration_auxiliary_series(
                single,
                RouterTimingSeriesKind::FirstProcessCostly,
                &clean_process_identity(ROUTER_PRIMARY_BATCH_ID, single),
            ),
            "resource_limit",
            "resource_admission",
        );
        assert!(ordered
            .record_clean_first_process_series(failed_clean_first)
            .is_err());
        let clean_first_failure = ordered
            .evidence()
            .expect("retained clean first-process failure");
        assert_eq!(clean_first_failure["failure"]["code"], "resource_limit");
        assert_eq!(
            clean_first_failure["failure"]["stage"],
            "resource_admission"
        );
        assert_eq!(
            clean_first_failure["retained_timing"]["first_process_series"]
                .as_array()
                .expect("retained first-process series")
                .last()
                .expect("failed clean first-process series")["raw_timing_observations"][0]
                ["failure"]["code"],
            "resource_limit"
        );
        assert_eq!(
            clean_first_failure["retained_timing"]["first_process_series"]
                .as_array()
                .expect("primary and failed clean first-process evidence")
                .len(),
            ROUTER_FIRST_PROCESS_REPETITIONS + 1
        );

        let mut retained_failure = RouterBenchmarkOrchestrator::new();
        let mut attempts = correctness_attempts(ROUTER_PRIMARY_BATCH_ID, single);
        attempts[4].comparison["passed"] = json!(false);
        for attempt in attempts.into_iter().take(4) {
            retained_failure
                .record_correctness_attempt(single, attempt)
                .expect("pre-failure attempt");
        }
        let failed_attempt = correctness_attempts(ROUTER_PRIMARY_BATCH_ID, single)
            .into_iter()
            .nth(4)
            .expect("fifth attempt");
        let mut failed_attempt = failed_attempt;
        failed_attempt.comparison["passed"] = json!(false);
        assert!(retained_failure
            .record_correctness_attempt(single, failed_attempt)
            .is_err());
        assert_eq!(retained_failure.next_step(), "failed_stop_condition");
        let retained = retained_failure
            .evidence()
            .expect("retained failure evidence");
        assert_eq!(retained["status"], "failed");
        assert_eq!(retained["failure"]["code"], "comparison_failed");
        assert_eq!(retained["failure"]["stage"], "correctness_gate");
        assert_eq!(retained["first_process_observation_started"], false);
        assert_eq!(retained["timing_started"], false);
        assert_eq!(
            retained["retained_current_case_attempts"]
                .as_array()
                .expect("retained attempts")
                .len(),
            5
        );
        assert!(retained_failure
            .record_correctness_attempt(
                single,
                correctness_attempts(ROUTER_PRIMARY_BATCH_ID, single).remove(0),
            )
            .is_err());

        let mut repeat_failure = RouterBenchmarkOrchestrator::new();
        let mut repeated = correctness_attempts(ROUTER_PRIMARY_BATCH_ID, single);
        repeated[ROUTER_CORRECTNESS_ATTEMPTS - 1].normalized_weights_f32le_sha256 = "c".repeat(64);
        for attempt in repeated.into_iter().take(ROUTER_CORRECTNESS_ATTEMPTS - 1) {
            repeat_failure
                .record_correctness_attempt(single, attempt)
                .expect("matching pre-repeat attempts");
        }
        let mut final_measurement = correctness_attempts(ROUTER_PRIMARY_BATCH_ID, single)
            .remove(ROUTER_CORRECTNESS_ATTEMPTS - 1);
        final_measurement.normalized_weights_f32le_sha256 = "c".repeat(64);
        assert!(repeat_failure
            .record_correctness_attempt(single, final_measurement)
            .is_err());
        assert_eq!(repeat_failure.next_step(), "failed_stop_condition");
        let repeat_evidence = repeat_failure.evidence().expect("repeat failure evidence");
        assert_eq!(
            repeat_evidence["retained_current_case_attempts"]
                .as_array()
                .expect("retained repeat attempts")
                .len(),
            ROUTER_CORRECTNESS_ATTEMPTS
        );
        assert_eq!(repeat_evidence["failure"]["code"], "comparison_failed");

        let mut first_process_failure = orchestrator_with_correctness_gates();
        let failed_first_process = retained_failed_series(
            &orchestration_auxiliary_series(
                single,
                RouterTimingSeriesKind::FirstProcessCostly,
                &primary_process_identity(ROUTER_PRIMARY_BATCH_ID),
            ),
            "evaluation_failed",
            "router_execution",
        );
        assert!(first_process_failure
            .record_primary_first_process_series(failed_first_process)
            .is_err());
        assert_eq!(first_process_failure.next_step(), "failed_stop_condition");
        let first_process_evidence = first_process_failure
            .evidence()
            .expect("retained first-process failure evidence");
        assert_eq!(
            first_process_evidence["first_process_observation_started"],
            true
        );
        assert_eq!(first_process_evidence["timing_started"], true);
        assert_eq!(
            first_process_evidence["retained_timing"]["first_process_series"]
                .as_array()
                .expect("retained failed first-process series")
                .len(),
            1
        );
        assert_eq!(
            first_process_evidence["failure"]["code"],
            "evaluation_failed"
        );
        assert_eq!(
            first_process_evidence["failure"]["stage"],
            "router_execution"
        );

        let mut wrong_first_process = orchestration_auxiliary_series(
            single,
            RouterTimingSeriesKind::FirstProcessCostly,
            &primary_process_identity(ROUTER_PRIMARY_BATCH_ID),
        )
        .try_to_value()
        .expect("serialized first-process series");
        for observation in wrong_first_process["raw_timing_observations"]
            .as_array_mut()
            .expect("first-process observations")
        {
            observation["output_sha256"] = json!(orchestration_hash(two_row));
        }
        let mut gated_hash_failure = orchestrator_with_correctness_gates();
        assert!(gated_hash_failure
            .record_primary_first_process_series(
                RouterTimingSeries::try_from_value(wrong_first_process)
                    .expect("locally valid mismatching first-process series"),
            )
            .is_err());
        let gated_hash_evidence = gated_hash_failure
            .evidence()
            .expect("retained first-process gate mismatch");
        assert_eq!(gated_hash_evidence["failure"]["code"], "comparison_failed");

        let mut timing_failure = orchestrator_with_correctness();
        let failed_costly = retained_failed_series(
            &orchestration_auxiliary_series(
                single,
                RouterTimingSeriesKind::CostlyReal,
                &primary_process_identity(ROUTER_PRIMARY_BATCH_ID),
            ),
            "evaluation_failed",
            "router_execution",
        );
        assert!(timing_failure.record_costly_series(failed_costly).is_err());
        assert_eq!(timing_failure.next_step(), "failed_stop_condition");
        let timing_evidence = timing_failure.evidence().expect("timing failure evidence");
        assert_eq!(timing_evidence["status"], "failed");
        assert_eq!(timing_evidence["failure"]["code"], "evaluation_failed");
        assert_eq!(timing_evidence["failure"]["stage"], "router_execution");
        assert_eq!(timing_evidence["timing_started"], true);
        assert_eq!(
            timing_evidence["retained_timing"]["costly_series"]
                .as_array()
                .expect("retained failed costly series")
                .len(),
            1
        );
        assert!(timing_failure
            .record_costly_series(orchestration_auxiliary_series(
                single,
                RouterTimingSeriesKind::CostlyReal,
                &primary_process_identity(ROUTER_PRIMARY_BATCH_ID),
            ))
            .is_err());
    }

    #[test]
    fn router_benchmark_orchestration_records_exact_major_matrix_and_unavailability() {
        let single = OrchestratedRouterCase::SingleRow;
        let two_row = OrchestratedRouterCase::TwoRow;
        let mut orchestration = orchestrator_with_correctness();
        record_primary_schedule(&mut orchestration);
        assert_eq!(
            orchestration.next_step(),
            "later_batch_or_unavailable_reason"
        );
        assert!(orchestration.evidence().is_err());

        orchestration
            .record_later_batch_unavailable(
                RouterSecondBatchUnavailableReason::QuietWindowUnavailable,
            )
            .expect("bounded public-safe unavailable reason");
        assert_eq!(orchestration.next_step(), "complete");
        assert!(orchestration
            .record_later_batch_unavailable(
                RouterSecondBatchUnavailableReason::ExternalInterferenceObserved,
            )
            .is_err());

        for reason in [
            RouterSecondBatchUnavailableReason::QuietWindowUnavailable,
            RouterSecondBatchUnavailableReason::ResourceAdmissionUnavailable,
            RouterSecondBatchUnavailableReason::ThermalOrPowerStateUnavailable,
            RouterSecondBatchUnavailableReason::ExternalInterferenceObserved,
        ] {
            let value = Value::String(reason.public_reason().to_owned());
            ensure_no_private_paths(&value).expect("allowlisted public-safe reason");
            assert!(reason.public_reason().chars().count() <= 512);
        }

        let evidence = orchestration.evidence().expect("complete evidence");
        let state_before_duplicate = evidence.clone();
        let duplicate_candidate =
            RouterBenchmarkOrchestrator::new_second("batch-after-unavailable")
                .expect("valid unused second-batch identity");
        assert!(orchestration
            .record_later_batch(&duplicate_candidate)
            .is_err());
        assert_eq!(
            orchestration
                .evidence()
                .expect("duplicate attempt preserves prior disposition"),
            state_before_duplicate
        );
        assert_eq!(evidence["order_seed"], ROUTER_BENCHMARK_ORDER_SEED);
        assert_eq!(
            evidence["correctness_gates"]
                .as_array()
                .expect("correctness gates")
                .len(),
            2
        );
        assert!(evidence["correctness_gates"]
            .as_array()
            .expect("correctness gates")
            .iter()
            .all(|gate| gate["attempts"]
                .as_array()
                .is_some_and(|items| items.len() == ROUTER_CORRECTNESS_ATTEMPTS)
                && gate["warmup_count"] == ROUTER_CORRECTNESS_WARMUPS
                && gate["measurement_count"] == ROUTER_CORRECTNESS_REPETITIONS));
        let ordered = evidence["primary_batch"]["raw_observations"]
            .as_array()
            .expect("primary ordered raw-observation ledger");
        assert_eq!(ordered.len(), 260);
        assert!(ordered.iter().enumerate().all(|(index, observation)| {
            observation["global_order_index"] == index
                && observation["batch_id"] == ROUTER_PRIMARY_BATCH_ID
                && observation["orchestration_status"] == "accepted"
                && observation.get("identity_duplicate").is_none()
        }));
        for (index, expected_step, expected_case) in [
            (0, "single_row_correctness", single.case_id()),
            (15, "two_row_correctness", two_row.case_id()),
            (30, "primary_first_process", single.case_id()),
            (40, "costly_real", single.case_id()),
            (55, "costly_real", two_row.case_id()),
            (70, "primary_major", single.case_id()),
            (105, "primary_major", two_row.case_id()),
            (140, "stage_diagnostic", single.case_id()),
            (155, "stage_diagnostic", two_row.case_id()),
            (170, "clean_first_process", single.case_id()),
            (180, "clean_major", single.case_id()),
            (215, "clean_first_process", two_row.case_id()),
            (225, "clean_major", two_row.case_id()),
        ] {
            assert_eq!(ordered[index]["schedule_step"], expected_step);
            assert_eq!(ordered[index]["case_id"], expected_case);
        }
        assert_eq!(
            evidence["primary_batch"]["major_series"]
                .as_array()
                .expect("major series")
                .len(),
            4
        );
        assert_eq!(
            evidence["primary_batch"]["costly_series"]
                .as_array()
                .expect("costly series")
                .len(),
            2
        );
        assert_eq!(
            evidence["primary_batch"]["stage_diagnostic_series"]
                .as_array()
                .expect("stage diagnostics")
                .len(),
            2
        );
        let first_process_series = evidence["primary_batch"]["first_process_series"]
            .as_array()
            .expect("first-process series");
        assert_eq!(
            first_process_series.len(),
            ROUTER_FIRST_PROCESS_REPETITIONS * 3
        );
        let process_ids = first_process_series
            .iter()
            .map(|series| {
                series["process_replication_id"]
                    .as_str()
                    .expect("first-process identity")
            })
            .collect::<BTreeSet<_>>();
        assert_eq!(process_ids.len(), ROUTER_FIRST_PROCESS_REPETITIONS * 3);
        assert!(first_process_series.iter().all(|series| {
            series["series_kind"] == "first_process_costly"
                && series["process_state"] == "fresh_process"
                && series["condition"] == "first_read_new_process_os_cache_uncontrolled"
                && series["warmup_count"] == 0
                && series["measurement_count"] == 1
                && series["raw_timing_observations"]
                    .as_array()
                    .is_some_and(|observations| {
                        observations.len() == 1
                            && observations.iter().all(|observation| {
                                observation["stages"]["file_io"]["status"] == "observed"
                            })
                    })
        }));
        for gate in evidence["correctness_gates"]
            .as_array()
            .expect("correctness gate evidence")
        {
            let attempts = gate["attempts"]
                .as_array()
                .expect("labeled correctness attempts");
            assert!(attempts[..ROUTER_CORRECTNESS_WARMUPS]
                .iter()
                .enumerate()
                .all(|(index, attempt)| {
                    attempt["observation_kind"] == "warmup"
                        && attempt["run_index"] == index
                        && attempt["attempt_index"] == index
                }));
            assert!(attempts[ROUTER_CORRECTNESS_WARMUPS..]
                .iter()
                .enumerate()
                .all(|(index, attempt)| {
                    attempt["observation_kind"] == "measurement"
                        && attempt["run_index"] == index
                        && attempt["attempt_index"] == index + ROUTER_CORRECTNESS_WARMUPS
                }));
            let canonical = &gate["canonical_output"];
            let rows = canonical["row_count"]
                .as_u64()
                .expect("canonical row count") as usize;
            assert_eq!(
                canonical["logits"]
                    .as_array()
                    .expect("complete logits")
                    .len(),
                rows * 128
            );
            assert_eq!(
                canonical["full_probabilities"]
                    .as_array()
                    .expect("complete probabilities")
                    .len(),
                rows * 128
            );
            assert_eq!(
                canonical["complete_output_sha256"],
                gate["complete_output_sha256"]
            );
            assert!(attempts
                .iter()
                .all(|attempt| attempt.get("canonical_output").is_none()));
        }
        assert_eq!(evidence["second_batch"]["status"], "unavailable");
        assert_eq!(
            evidence["second_batch"]["between_batch_variation_measured"],
            false
        );
        assert!(serde_json::to_vec(&evidence).unwrap().len() <= MAX_RESPONSE_BYTES);
    }

    #[test]
    fn router_benchmark_orchestration_requires_independent_reversed_later_batch() {
        let mut base = orchestrator_with_correctness();
        record_primary_schedule(&mut base);

        let mut second_order_failure = RouterBenchmarkOrchestrator::new_second("batch-order")
            .expect("valid second-batch order-failure identity");
        assert!(second_order_failure
            .record_correctness_attempt(
                OrchestratedRouterCase::SingleRow,
                correctness_attempts("batch-order", OrchestratedRouterCase::SingleRow).remove(0),
            )
            .is_err());
        assert_eq!(
            second_order_failure
                .evidence()
                .expect("retained second-batch order failure")["retained_current_case_attempts"][0]
                ["status"],
            "failed"
        );

        let mut event_driven_second =
            RouterBenchmarkOrchestrator::new_second("batch-event").expect("valid second batch");
        assert_eq!(event_driven_second.next_step(), "two_row_correctness");
        for case in ROUTER_SECOND_CORRECTNESS_ORDER {
            for attempt in correctness_attempts("batch-event", case) {
                event_driven_second
                    .record_correctness_attempt(case, attempt)
                    .expect("second batch correctness in reversed order");
            }
        }
        assert_eq!(
            event_driven_second.next_step(),
            "primary_first_process_os_cache_uncontrolled"
        );
        for repetition_index in 0..ROUTER_FIRST_PROCESS_REPETITIONS {
            event_driven_second
                .record_primary_first_process_series(orchestration_auxiliary_series(
                    OrchestratedRouterCase::TwoRow,
                    RouterTimingSeriesKind::FirstProcessCostly,
                    &primary_first_process_identity("batch-event", repetition_index),
                ))
                .expect("second correctness gates each fresh timing worker first read");
        }
        assert_eq!(event_driven_second.next_step(), "two_row_costly_real");

        let mut failed_second = RouterBenchmarkOrchestrator::new_second("batch-failed")
            .expect("valid failed second batch identity");
        for case in ROUTER_SECOND_CORRECTNESS_ORDER {
            for attempt in correctness_attempts("batch-failed", case) {
                failed_second
                    .record_correctness_attempt(case, attempt)
                    .expect("failed second batch first passes correctness");
            }
        }
        let failed_second_process = primary_process_identity("batch-failed");
        for repetition_index in 0..ROUTER_FIRST_PROCESS_REPETITIONS {
            failed_second
                .record_primary_first_process_series(orchestration_auxiliary_series(
                    OrchestratedRouterCase::TwoRow,
                    RouterTimingSeriesKind::FirstProcessCostly,
                    &primary_first_process_identity("batch-failed", repetition_index),
                ))
                .expect("failed second batch retains its first-process cohort");
        }
        assert!(failed_second
            .record_costly_series(retained_failed_series(
                &orchestration_auxiliary_series(
                    OrchestratedRouterCase::TwoRow,
                    RouterTimingSeriesKind::CostlyReal,
                    &failed_second_process,
                ),
                "resource_limit",
                "resource_admission",
            ))
            .is_err());
        let failed_second_evidence = failed_second
            .evidence()
            .expect("failed second-batch evidence remains caller-owned");
        assert_eq!(failed_second_evidence["failure"]["code"], "resource_limit");
        assert_eq!(
            failed_second_evidence["retained_timing"]["costly_series"]
                .as_array()
                .expect("retained failed second costly series")
                .len(),
            1
        );
        let mut failed_outer = base.clone();
        assert!(failed_outer.record_later_batch(&failed_second).is_err());
        let failed_outer_evidence = failed_outer
            .evidence()
            .expect("primary and failed second batch remain one terminal experiment");
        assert_eq!(failed_outer_evidence["second_batch"]["status"], "failed");
        assert_eq!(failed_outer_evidence["failure"]["code"], "resource_limit");
        assert_eq!(
            failed_outer_evidence["failure"]["stage"],
            "resource_admission"
        );
        assert_eq!(
            failed_outer_evidence["second_batch"]["retained_evidence"]["status"],
            "failed"
        );
        assert!(failed_outer
            .record_later_batch_unavailable(
                RouterSecondBatchUnavailableReason::QuietWindowUnavailable,
            )
            .is_err());
        assert_eq!(
            failed_second
                .evidence()
                .expect("second failure survives outer rejection"),
            failed_second_evidence
        );

        let mut oversized_candidate = second_batch_candidate("batch-oversized");
        let repeated_costly = oversized_candidate.costly_series[0].clone();
        for _ in 2..128 {
            oversized_candidate.append_timing_observations("costly_real", &repeated_costly, false);
            oversized_candidate
                .costly_series
                .push(repeated_costly.clone());
        }
        assert!(oversized_candidate.retained_batch_snapshot().is_err());
        let mut oversized_outer = base.clone();
        assert!(oversized_outer
            .record_later_batch(&oversized_candidate)
            .is_err());
        assert!(matches!(
            &oversized_outer.later_batch,
            RouterLaterBatchState::Failed(failed)
                if failed.candidate.costly_series.len() == 128
        ));
        assert!(oversized_outer
            .evidence()
            .expect_err("oversized retained evidence must fail rather than truncate")
            .contains("exceeds the protocol cap"));

        let mut split_primary = orchestrator_with_correctness();
        let expected_primary = primary_process_identity(ROUTER_PRIMARY_BATCH_ID);
        for case in ROUTER_COSTLY_ORDER {
            split_primary
                .record_costly_series(orchestration_auxiliary_series(
                    case,
                    RouterTimingSeriesKind::CostlyReal,
                    &expected_primary,
                ))
                .expect("costly series");
        }
        split_primary
            .record_primary_major_series(orchestration_major_series(
                OrchestratedRouterCase::SingleRow,
                RouterTimingReplicationRole::Primary,
                &expected_primary,
                orchestration_hash(OrchestratedRouterCase::SingleRow),
            ))
            .expect("first primary process");
        assert!(split_primary
            .record_primary_major_series(orchestration_major_series(
                OrchestratedRouterCase::TwoRow,
                RouterTimingReplicationRole::Primary,
                "different-primary-process",
                orchestration_hash(OrchestratedRouterCase::TwoRow),
            ))
            .is_err());

        let mut wrong_order = base.clone();
        let mut primary_order = second_batch_candidate("batch-b");
        primary_order.primary_major_series.swap(0, 1);
        assert!(wrong_order.record_later_batch(&primary_order).is_err());

        let mut reused_process = base.clone();
        let mut relabeled_process = second_batch_candidate("batch-b");
        relabeled_process.costly_series[0] = orchestration_auxiliary_series(
            OrchestratedRouterCase::TwoRow,
            RouterTimingSeriesKind::CostlyReal,
            "batch-a-primary-worker",
        );
        assert!(reused_process
            .record_later_batch(&relabeled_process)
            .is_err());

        let mut reused_observation = second_batch_candidate("batch-b");
        let primary_observation_id = base.costly_series[0].raw_timing_observations()[0]
            .observation_id()
            .to_owned();
        let mut changed = reused_observation.costly_series[0]
            .try_to_value()
            .expect("serialized costly series");
        changed["raw_timing_observations"][0]["observation_id"] = json!(primary_observation_id);
        reused_observation.costly_series[0] =
            RouterTimingSeries::try_from_value(changed).expect("locally valid changed identity");
        let mut cross_batch_duplicate = base.clone();
        assert!(cross_batch_duplicate
            .record_later_batch(&reused_observation)
            .is_err());

        base.record_later_batch(&second_batch_candidate("batch-b"))
            .expect("independent reversed later batch");
        let evidence = base.evidence().expect("recorded later-batch evidence");
        assert_eq!(evidence["second_batch"]["status"], "recorded");
        assert_eq!(evidence["second_batch"]["batch_id"], "batch-b");
        assert_eq!(
            evidence["second_batch"]["between_batch_variation_measured"],
            true
        );
        assert_eq!(
            evidence["second_batch"]["major_series"]
                .as_array()
                .expect("later major series")
                .len(),
            4
        );
        assert_eq!(
            evidence["second_batch"]["correctness_gates"]
                .as_array()
                .expect("second correctness gates")
                .len(),
            2
        );
        assert_eq!(
            evidence["second_batch"]["costly_series"]
                .as_array()
                .expect("second costly series")
                .len(),
            2
        );
        assert_eq!(
            evidence["second_batch"]["first_process_series"]
                .as_array()
                .expect("second first-process series")
                .len(),
            ROUTER_FIRST_PROCESS_REPETITIONS * 3
        );
        assert_eq!(
            evidence["second_batch"]["stage_diagnostic_series"]
                .as_array()
                .expect("second stage diagnostics")
                .len(),
            2
        );
        let second_ordered = evidence["second_batch"]["raw_observations"]
            .as_array()
            .expect("second ordered raw-observation ledger");
        assert_eq!(second_ordered.len(), 260);
        assert!(second_ordered
            .iter()
            .enumerate()
            .all(|(index, observation)| {
                observation["global_order_index"] == index
                    && observation["batch_id"] == "batch-b"
                    && observation["orchestration_status"] == "accepted"
                    && observation.get("identity_duplicate").is_none()
            }));
        assert_eq!(
            second_ordered[0]["case_id"],
            OrchestratedRouterCase::TwoRow.case_id()
        );
        assert_eq!(
            second_ordered[15]["case_id"],
            OrchestratedRouterCase::SingleRow.case_id()
        );
        assert_eq!(second_ordered[30]["schedule_step"], "primary_first_process");
        assert_eq!(
            second_ordered[30]["case_id"],
            OrchestratedRouterCase::TwoRow.case_id()
        );
    }

    #[test]
    fn feature_002_external_dispatch_remains_fail_closed_without_access() {
        let model = format!("/tmp/pulsarmlx-never-accessed/{QWEN_FILENAME}");
        let inspect_error = run(args(&[
            "inspect-router",
            "--model",
            &model,
            "--evidence",
            "/tmp/pulsarmlx-never-accessed/inspection.json",
        ]))
        .expect_err("inspection remains task gated");
        assert!(inspect_error.contains("T074"));
        assert!(inspect_error.contains("no checkpoint was accessed"));

        let router_error = run(args(&[
            "validate-router",
            "--model",
            &model,
            "--oracle",
            "/tmp/pulsarmlx-never-accessed/oracle.json",
            "--evidence-dir",
            "/tmp/pulsarmlx-never-accessed/attempts",
        ]))
        .expect_err("router execution remains task gated");
        assert!(router_error.contains("orchestration is frozen"));
        assert!(router_error.contains("T074"));
        assert!(router_error.contains("T083"));
        assert!(router_error.contains("no checkpoint was accessed"));

        assert!(run(args(&["--help"]))
            .expect_err("help is usage-only")
            .starts_with("usage:"));
    }

    #[test]
    fn router_fixture_bundle_admits_exact_inventory_and_honest_scopes() {
        let bundle =
            load_router_fixture_bundle(&project_root(), Path::new(ROUTER_FIXTURE_MANIFEST))
                .expect("committed router fixture bundle");
        assert_eq!(bundle.case_order.len(), 2);
        assert_eq!(bundle.manifest_files.len(), ROUTER_FIXTURE_FILES.len());
        assert_eq!(bundle.negative_cases.len(), 7);
        assert!(canonical_sha256(&bundle.manifest_sha256));

        let ties = validate_tie_cases(&bundle).expect("synthetic tie contracts");
        assert_eq!(ties.len(), 2);
        assert!(ties.iter().all(|case| {
            case["fixture_kind"] == "synthetic"
                && case["validation_mode"] == "host_contract_validation"
                && case["mlx_executed"] == false
                && case["real_checkpoint_evidence"] == false
        }));
        assert!(bundle.negative_cases.iter().all(|case| {
            case["validation_mode"] == "fixture_contract_validation"
                && case["mlx_executed"] == false
                && case["accepted_result"] == false
                && case["router_runner_called"] == false
        }));
    }

    #[test]
    fn router_fixture_json_rejects_duplicate_keys_at_any_depth() {
        let duplicate_root = br#"{"schema":"one","schema":"two"}"#;
        assert!(parse_unique_json::<Value>(duplicate_root, "test document").is_err());
        let duplicate_nested = br#"{"outer":{"code":"one","code":"two"}}"#;
        assert!(parse_unique_json::<Value>(duplicate_nested, "test document").is_err());
    }

    #[test]
    fn router_fixture_failure_evidence_retains_partial_success_without_overclaim() {
        let mut attempt = RouterFixtureAttempt::new();
        attempt.positive_cases.push(json!({
            "case_id": ROUTER_SINGLE_ROW_CASE_ID,
            "status": "passed",
        }));
        attempt.retain_failure(retained_fixture_failure(
            "failed",
            "router_execution",
            "comparison_failed",
            "bounded synthetic failure",
        ));
        let evidence = attempt.evidence();
        assert_eq!(evidence["status"], "failed");
        assert_eq!(evidence["passed"], false);
        assert_eq!(evidence["positive_cases"].as_array().unwrap().len(), 1);
        assert_eq!(evidence["fixture_kind"], "synthetic");
        assert_eq!(evidence["model_free"], true);
        assert_eq!(evidence["real_checkpoint_evidence"], false);
        assert_eq!(evidence["external_checkpoint_accessed"], false);
        assert_eq!(evidence["failure"]["code"], "comparison_failed");
        ensure_no_private_paths(&evidence).expect("retained failure remains private-safe");
    }

    #[test]
    fn router_fixture_evidence_install_is_exclusive_and_leaves_no_temporary_file() {
        use std::time::{SystemTime, UNIX_EPOCH};

        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system clock")
            .as_nanos();
        let directory = env::temp_dir().join(format!(
            "pulsarmlx-router-evidence-exclusive-{}-{nonce}",
            std::process::id()
        ));
        fs::create_dir(&directory).expect("create exclusive evidence directory");
        let destination = directory.join("router-fixtures.json");
        write_evidence_exclusive(&destination, &json!({"status": "passed"}))
            .expect("first exclusive install");
        let original = fs::read(&destination).expect("read installed evidence");
        let error = write_evidence_exclusive(&destination, &json!({"status": "failed"}))
            .expect_err("existing destination must be refused");
        assert!(error.contains("already exists"));
        assert_eq!(fs::read(&destination).unwrap(), original);
        assert_eq!(fs::read_dir(&directory).unwrap().count(), 1);
        fs::remove_file(destination).expect("remove evidence");
        fs::remove_dir(directory).expect("remove evidence directory");
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
