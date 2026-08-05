use mlx_backend::router::{
    compare_router_outputs, RouterCaseScope, RouterNumericComparison, RouterOutput,
    RouterOutputComparison, RouterTolerancePolicy,
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
    let logits = f32_rows(result.logits(), "worker router logits")?;
    let probabilities = f32_rows(result.full_probabilities(), "worker router probabilities")?;
    let selected = f32_rows(
        result.selected_probabilities(),
        "worker selected probabilities",
    )?;
    let normalized = f32_rows(result.normalized_weights(), "worker normalized weights")?;
    let output = RouterOutput::try_new(
        result.router_case_id(),
        RouterCaseScope::SyntheticFixture,
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
        attempt.positive_cases.push(json!({
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
            "comparison": router_comparison_evidence(&comparison),
            "memory_gauges": router_memory_evidence(&result),
            "status": "passed",
        }));
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

fn run_planned_validate_router(command: ValidateRouterCommand) -> Result<(), String> {
    // As with inspection, resolving any path here would cross the T074 gate.
    let _parsed_paths = (command.model, command.oracle, command.evidence_dir);
    Err("validate-router is parsed but correctness-gated orchestration remains deferred to T066 and execution to T083; no checkpoint was accessed and no MLX worker was started".to_owned())
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
        assert!(router_error.contains("T066"));
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
