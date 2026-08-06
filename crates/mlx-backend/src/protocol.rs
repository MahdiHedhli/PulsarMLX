//! Bounded protocol-v1 envelopes for the persistent MLX worker.

use crate::model::{QWEN_ENCODED_SLICE_BYTES, QWEN_FILE_BYTES};
use crate::router::{
    canonical_f32le_sha256, ROUTER_EXPERT_COUNT, ROUTER_HIDDEN_WIDTH, ROUTER_MAX_ROWS, ROUTER_TOP_K,
};
use serde::de::{self, MapAccess, SeqAccess, Visitor};
use serde::{Deserialize, Deserializer, Serialize};
use serde_json::{Map, Number, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

pub const PROTOCOL_VERSION: u32 = 1;
pub const MAX_REQUEST_BYTES: usize = 64 * 1024;
pub const MAX_RESPONSE_BYTES: usize = 1024 * 1024;
pub const MAX_PROTOCOL_MESSAGE_CHARS: usize = 512;

const MAX_IDENTIFIER_CHARS: usize = 128;
const MAX_NESTING_DEPTH: usize = 16;
const MAX_LIST_ITEMS: usize = 4096;
const MAX_DEVICE_COUNT: usize = 64;
const MAX_CAPABILITY_COUNT: usize = 256;
const APPLE_MLX_BACKEND_ID: &str = "apple-mlx";
const APPLE_MLX_DEVICE_ID: &str = "gpu";
pub const MODEL_SLICE_ID: &str = "qwen3-30b-a3b-q8_0-blk0-gate-expert0-prefix-v1";
const MODEL_SLICE_OPERATION: &str = "q8_0_expert_projection_matvec";
const MODEL_SLICE_TENSOR: &str = "blk.0.ffn_gate_exps.weight";
const MODEL_SLICE_OUTPUT: &str = "blk0_ffn_gate_expert0_rows0_16_matvec";
const MODEL_SLICE_ACTIVATION_SHA256: &str =
    "3821796e8415d1214890e0e2fc97cddbb9ec773f2e941203dac41c1c7b36a92e";
const MODEL_SLICE_OUTPUT_COUNT: usize = 16;
const MODEL_SLICE_DECODED_BYTES: u64 = 131_072;
const MODEL_SLICE_ACTIVATION_BYTES: u64 = 8_192;
const MODEL_SLICE_OUTPUT_BYTES: u64 = 64;
const MODEL_TEMPORARY_CURRENT_CAP: u64 = 1_073_741_824;
const MODEL_TEMPORARY_PEAK_CAP: u64 = 2_147_483_648;
const MODEL_MLX_ACTIVE_CAP: u64 = 3_221_225_472;
const MODEL_MLX_CACHE_CAP: u64 = 1_342_177_280;
const MODEL_MLX_PEAK_CAP: u64 = 4_294_967_296;
const MODEL_PHYSICAL_FOOTPRINT_CAP: u64 = 8_589_934_592;
pub const ROUTER_SINGLE_ROW_CASE_ID: &str = "generated-qwen3moe-router-single-row-v1";
pub const ROUTER_TWO_ROW_CASE_ID: &str = "generated-qwen3moe-router-two-row-v1";
const ROUTER_OPERATION: &str = "complete_router_projection_topk";
const ROUTER_OUTPUT_DTYPE: &str = "float32";
const ROUTER_PROBABILITY_SUM_TOLERANCE: f64 = 1.0e-6;
const ROUTER_PROBABILITY_ABSOLUTE_TOLERANCE: f64 = 1.0e-6;
const ROUTER_PROBABILITY_RELATIVE_TOLERANCE: f64 = 1.0e-6;
const ROUTER_TIMING_CLOCK: &str = "perf_counter_ns";
const ROUTER_F32_DEQUANTIZATION_REASON: &str = "f32_router_requires_no_dequantization";
const MAX_ROUTER_TIMING_STAGES: usize = 13;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WorkerErrorKind {
    Spawn,
    Io,
    HelloNegotiation,
    Protocol,
    MessageTooLarge,
    RequestIdMismatch,
    Timeout,
    UnexpectedEof,
    NonZeroExit,
    ProcessCrashed,
    StdoutContamination,
    Remote,
}

#[derive(Debug, Clone, PartialEq)]
pub struct WorkerError {
    kind: WorkerErrorKind,
    worker_code: Option<String>,
    message: String,
    retryable: Option<bool>,
    details: Option<Value>,
    exit_code: Option<i32>,
}

impl WorkerError {
    pub(crate) fn new(kind: WorkerErrorKind, message: impl AsRef<str>) -> Self {
        Self {
            kind,
            worker_code: None,
            message: sanitize_message(message.as_ref()),
            retryable: None,
            details: None,
            exit_code: None,
        }
    }

    pub fn with_exit_code(mut self, exit_code: i32) -> Self {
        self.exit_code = Some(exit_code);
        self
    }

    fn from_remote(error: RemoteErrorEnvelope) -> Result<Self, Self> {
        if !stable_worker_error_code(&error.code) {
            return Err(Self::new(
                WorkerErrorKind::StdoutContamination,
                "worker returned an unknown error code",
            ));
        }
        if error.message.trim().is_empty() {
            return Err(Self::new(
                WorkerErrorKind::StdoutContamination,
                "worker returned an empty error message",
            ));
        }
        if !error.details.is_object() {
            return Err(Self::new(
                WorkerErrorKind::StdoutContamination,
                "worker error details must be an object",
            ));
        }

        Ok(Self {
            kind: WorkerErrorKind::Remote,
            worker_code: Some(error.code),
            message: sanitize_message(&error.message),
            retryable: Some(error.retryable),
            details: Some(sanitize_json(error.details)),
            exit_code: None,
        })
    }

    pub fn kind(&self) -> WorkerErrorKind {
        self.kind
    }

    pub fn worker_code(&self) -> Option<&str> {
        self.worker_code.as_deref()
    }

    pub fn message(&self) -> &str {
        &self.message
    }

    pub fn retryable(&self) -> Option<bool> {
        self.retryable
    }

    pub fn details(&self) -> Option<&Value> {
        self.details.as_ref()
    }

    pub fn exit_code(&self) -> Option<i32> {
        self.exit_code
    }
}

impl fmt::Display for WorkerError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        if let Some(code) = self.worker_code() {
            write!(formatter, "{code}: {}", self.message)
        } else {
            write!(formatter, "{}", self.message)
        }
    }
}

impl std::error::Error for WorkerError {}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ProtocolLimits {
    max_request_bytes: usize,
    max_response_bytes: usize,
    max_nesting_depth: usize,
    max_list_items: usize,
}

impl Default for ProtocolLimits {
    fn default() -> Self {
        Self {
            max_request_bytes: MAX_REQUEST_BYTES,
            max_response_bytes: MAX_RESPONSE_BYTES,
            max_nesting_depth: MAX_NESTING_DEPTH,
            max_list_items: MAX_LIST_ITEMS,
        }
    }
}

impl ProtocolLimits {
    pub fn max_request_bytes(&self) -> usize {
        self.max_request_bytes
    }

    pub fn max_response_bytes(&self) -> usize {
        self.max_response_bytes
    }

    pub fn negotiated(&self, advertised: &WorkerAdvertisedLimits) -> Result<Self, WorkerError> {
        let max_request_bytes = usize::try_from(advertised.max_request_bytes)
            .map_err(|_| hello_error("worker request limit is not representable"))?;
        let max_response_bytes = usize::try_from(advertised.max_response_bytes)
            .map_err(|_| hello_error("worker response limit is not representable"))?;
        if max_request_bytes == 0
            || max_response_bytes == 0
            || max_request_bytes > self.max_request_bytes
            || max_response_bytes > self.max_response_bytes
        {
            return Err(hello_error("worker limits exceed the protocol-v1 bounds"));
        }
        Ok(Self {
            max_request_bytes,
            max_response_bytes,
            max_nesting_depth: self.max_nesting_depth,
            max_list_items: self.max_list_items,
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HelloExpectation {
    protocol: u32,
    worker_version: String,
    mlx_version: String,
}

impl HelloExpectation {
    pub fn new(
        protocol: u32,
        worker_version: impl Into<String>,
        mlx_version: impl Into<String>,
    ) -> Result<Self, WorkerError> {
        let worker_version = worker_version.into();
        let mlx_version = mlx_version.into();
        if protocol != PROTOCOL_VERSION {
            return Err(hello_error("unsupported expected protocol version"));
        }
        validate_identifier(
            &worker_version,
            "worker version",
            WorkerErrorKind::HelloNegotiation,
        )?;
        validate_identifier(
            &mlx_version,
            "MLX version",
            WorkerErrorKind::HelloNegotiation,
        )?;
        Ok(Self {
            protocol,
            worker_version,
            mlx_version,
        })
    }
}

#[derive(Debug, Clone, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct RequestEnvelope {
    protocol: u32,
    request_id: u64,
    op: String,
    params: Map<String, Value>,
}

impl RequestEnvelope {
    pub fn new(
        request_id: u64,
        op: impl Into<String>,
        params: Map<String, Value>,
    ) -> Result<Self, WorkerError> {
        let op = op.into();
        validate_operation(&op)?;
        validate_value_limits(&Value::Object(params.clone()), &ProtocolLimits::default())?;
        Ok(Self {
            protocol: PROTOCOL_VERSION,
            request_id,
            op,
            params,
        })
    }

    pub fn empty(request_id: u64, op: impl Into<String>) -> Result<Self, WorkerError> {
        Self::new(request_id, op, Map::new())
    }

    pub fn protocol(&self) -> u32 {
        self.protocol
    }

    pub fn request_id(&self) -> u64 {
        self.request_id
    }

    pub fn op(&self) -> &str {
        &self.op
    }

    pub fn params(&self) -> &Map<String, Value> {
        &self.params
    }

    pub fn encode_line(&self, limits: &ProtocolLimits) -> Result<Vec<u8>, WorkerError> {
        let mut encoded = serde_json::to_vec(self).map_err(|_| {
            WorkerError::new(
                WorkerErrorKind::Protocol,
                "request envelope could not be encoded",
            )
        })?;
        if encoded.len() > limits.max_request_bytes {
            return Err(WorkerError::new(
                WorkerErrorKind::MessageTooLarge,
                "request line exceeds the configured byte limit",
            ));
        }
        encoded.push(b'\n');
        Ok(encoded)
    }
}

/// Bounded control-only request for one committed tensor fixture.
///
/// Tensor values and encoded weights deliberately are not members of this
/// type. The worker resolves the immutable fixture from its negotiated local
/// fixture set.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TensorFixtureRequest {
    fixture_set_id: String,
    case_id: String,
    operation: String,
    device: String,
}

impl TensorFixtureRequest {
    pub fn new(
        fixture_set_id: impl Into<String>,
        case_id: impl Into<String>,
        operation: impl Into<String>,
        device: impl Into<String>,
    ) -> Result<Self, WorkerError> {
        let fixture_set_id = fixture_set_id.into();
        let case_id = case_id.into();
        let operation = operation.into();
        let device = device.into();

        validate_fixture_identifier(&fixture_set_id, "fixture-set ID")?;
        validate_fixture_identifier(&case_id, "fixture case ID")?;
        validate_fixture_operation(&operation)?;
        if device != APPLE_MLX_DEVICE_ID {
            return Err(fixture_protocol_error(
                "tensor fixtures require the explicit MLX GPU device",
            ));
        }

        Ok(Self {
            fixture_set_id,
            case_id,
            operation,
            device,
        })
    }

    pub fn fixture_set_id(&self) -> &str {
        &self.fixture_set_id
    }

    pub fn case_id(&self) -> &str {
        &self.case_id
    }

    pub fn operation(&self) -> &str {
        &self.operation
    }

    pub fn device(&self) -> &str {
        &self.device
    }

    pub const fn allow_fallback(&self) -> bool {
        false
    }

    pub(crate) fn protocol_params(&self) -> Map<String, Value> {
        Map::from_iter([
            (
                "fixture_set_id".to_owned(),
                Value::String(self.fixture_set_id.clone()),
            ),
            ("case_id".to_owned(), Value::String(self.case_id.clone())),
            ("device".to_owned(), Value::String(self.device.clone())),
            ("allow_fallback".to_owned(), Value::Bool(false)),
        ])
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct TensorFixtureComparison {
    oracle_id: String,
    mode: String,
    absolute_tolerance: f64,
    relative_tolerance: f64,
    non_finite_policy: String,
    compared_count: u64,
    max_absolute_error: f64,
    max_relative_error: f64,
    first_mismatch_index: Option<u64>,
    passed: bool,
}

impl TensorFixtureComparison {
    pub fn oracle_id(&self) -> &str {
        &self.oracle_id
    }

    pub fn mode(&self) -> &str {
        &self.mode
    }

    pub fn absolute_tolerance(&self) -> f64 {
        self.absolute_tolerance
    }

    pub fn relative_tolerance(&self) -> f64 {
        self.relative_tolerance
    }

    pub fn non_finite_policy(&self) -> &str {
        &self.non_finite_policy
    }

    pub fn compared_count(&self) -> u64 {
        self.compared_count
    }

    pub fn max_absolute_error(&self) -> f64 {
        self.max_absolute_error
    }

    pub fn max_relative_error(&self) -> f64 {
        self.max_relative_error
    }

    pub fn first_mismatch_index(&self) -> Option<u64> {
        self.first_mismatch_index
    }

    pub fn passed(&self) -> bool {
        self.passed
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct TensorFixtureMemoryGauges {
    mlx_active_bytes: Option<u64>,
    mlx_cache_bytes: Option<u64>,
    mlx_peak_bytes: Option<u64>,
    process_footprint_bytes: Option<u64>,
    process_footprint_source: Option<String>,
    system_pressure: Option<String>,
    reported_summed_total_bytes: Option<u64>,
}

impl TensorFixtureMemoryGauges {
    pub fn mlx_active_bytes(&self) -> Option<u64> {
        self.mlx_active_bytes
    }

    pub fn mlx_cache_bytes(&self) -> Option<u64> {
        self.mlx_cache_bytes
    }

    pub fn mlx_peak_bytes(&self) -> Option<u64> {
        self.mlx_peak_bytes
    }

    pub fn process_footprint_bytes(&self) -> Option<u64> {
        self.process_footprint_bytes
    }

    pub fn process_footprint_source(&self) -> Option<&str> {
        self.process_footprint_source.as_deref()
    }

    pub fn system_pressure(&self) -> Option<&str> {
        self.system_pressure.as_deref()
    }

    pub fn reported_summed_total_bytes(&self) -> Option<u64> {
        self.reported_summed_total_bytes
    }
}

/// Validated bounded readback and comparison summary for one fixture case.
#[derive(Debug, Clone, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct TensorFixtureResult {
    fixture_set_id: String,
    case_id: String,
    operation: String,
    backend_id: String,
    requested_device: String,
    selected_device: String,
    fallback_used: bool,
    output_shape: Vec<u64>,
    input_dtype: String,
    accumulation_dtype: String,
    output_dtype: String,
    evaluated: bool,
    synchronized: bool,
    actual: Vec<f64>,
    comparison: TensorFixtureComparison,
    memory_gauges: TensorFixtureMemoryGauges,
    #[serde(default)]
    selected_expert_ids: Option<Vec<u64>>,
    #[serde(default)]
    decoded: Option<Vec<f64>>,
    passed: bool,
}

impl TensorFixtureResult {
    pub fn fixture_set_id(&self) -> &str {
        &self.fixture_set_id
    }

    pub fn case_id(&self) -> &str {
        &self.case_id
    }

    pub fn operation(&self) -> &str {
        &self.operation
    }

    pub fn backend_id(&self) -> &str {
        &self.backend_id
    }

    pub fn requested_device(&self) -> &str {
        &self.requested_device
    }

    pub fn selected_device(&self) -> &str {
        &self.selected_device
    }

    pub fn fallback_used(&self) -> bool {
        self.fallback_used
    }

    pub fn output_shape(&self) -> &[u64] {
        &self.output_shape
    }

    pub fn input_dtype(&self) -> &str {
        &self.input_dtype
    }

    pub fn accumulation_dtype(&self) -> &str {
        &self.accumulation_dtype
    }

    pub fn output_dtype(&self) -> &str {
        &self.output_dtype
    }

    pub fn evaluated(&self) -> bool {
        self.evaluated
    }

    pub fn synchronized(&self) -> bool {
        self.synchronized
    }

    pub fn actual(&self) -> &[f64] {
        &self.actual
    }

    pub fn comparison(&self) -> &TensorFixtureComparison {
        &self.comparison
    }

    pub fn memory_gauges(&self) -> &TensorFixtureMemoryGauges {
        &self.memory_gauges
    }

    pub fn selected_expert_ids(&self) -> Option<&[u64]> {
        self.selected_expert_ids.as_deref()
    }

    pub fn decoded(&self) -> Option<&[f64]> {
        self.decoded.as_deref()
    }

    pub fn passed(&self) -> bool {
        self.passed
    }
}

pub(crate) fn parse_tensor_fixture_result(
    value: Value,
    request: &TensorFixtureRequest,
    max_fixture_elements: u64,
) -> Result<TensorFixtureResult, WorkerError> {
    let result: TensorFixtureResult = serde_json::from_value(value).map_err(|_| {
        fixture_protocol_error("worker fixture result does not match the protocol-v1 schema")
    })?;
    validate_tensor_fixture_result(&result, request, max_fixture_elements)?;
    Ok(result)
}

/// Control-only request for the committed synthetic routed-MoE fixture.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SyntheticMoeRequest {
    fixture_id: String,
    device: String,
}

/// Control-only request for the one admitted real-model slice.
///
/// The model file is inherited on a fixed descriptor. No path, model bytes,
/// checksum, prompt, or depth selector is admitted to the NDJSON request.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ModelSliceRequest {
    slice_id: String,
    device: String,
}

impl ModelSliceRequest {
    pub fn new(
        slice_id: impl Into<String>,
        device: impl Into<String>,
    ) -> Result<Self, WorkerError> {
        let slice_id = slice_id.into();
        let device = device.into();
        if slice_id != MODEL_SLICE_ID {
            return Err(fixture_protocol_error(
                "model-slice validation accepts only the frozen slice identity",
            ));
        }
        if device != APPLE_MLX_DEVICE_ID {
            return Err(fixture_protocol_error(
                "model-slice validation requires the explicit MLX GPU device",
            ));
        }
        Ok(Self { slice_id, device })
    }

    pub fn slice_id(&self) -> &str {
        &self.slice_id
    }

    pub fn device(&self) -> &str {
        &self.device
    }

    pub const fn allow_fallback(&self) -> bool {
        false
    }

    pub(crate) fn protocol_params(&self) -> Map<String, Value> {
        Map::from_iter([
            ("slice_id".to_owned(), Value::String(self.slice_id.clone())),
            ("device".to_owned(), Value::String(self.device.clone())),
            ("allow_fallback".to_owned(), Value::Bool(false)),
        ])
    }
}

/// Control-only request for one committed bounded router case.
///
/// Hidden states, tensor values, model paths, output-depth selectors, hashes,
/// and benchmark-count overrides are deliberately absent.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RouterRequest {
    router_case_id: String,
    device: String,
}

impl RouterRequest {
    pub fn new(
        router_case_id: impl Into<String>,
        device: impl Into<String>,
    ) -> Result<Self, WorkerError> {
        let router_case_id = router_case_id.into();
        let device = device.into();
        if !matches!(
            router_case_id.as_str(),
            ROUTER_SINGLE_ROW_CASE_ID | ROUTER_TWO_ROW_CASE_ID
        ) {
            return Err(fixture_protocol_error(
                "router validation accepts only a committed bounded case identity",
            ));
        }
        if device != APPLE_MLX_DEVICE_ID {
            return Err(fixture_protocol_error(
                "router validation requires the explicit MLX GPU device",
            ));
        }
        Ok(Self {
            router_case_id,
            device,
        })
    }

    pub fn router_case_id(&self) -> &str {
        &self.router_case_id
    }

    pub fn device(&self) -> &str {
        &self.device
    }

    pub const fn allow_fallback(&self) -> bool {
        false
    }

    pub(crate) fn protocol_params(&self) -> Map<String, Value> {
        Map::from_iter([
            (
                "router_case_id".to_owned(),
                Value::String(self.router_case_id.clone()),
            ),
            ("device".to_owned(), Value::String(self.device.clone())),
            ("allow_fallback".to_owned(), Value::Bool(false)),
        ])
    }

    fn expected_rows(&self) -> usize {
        match self.router_case_id.as_str() {
            ROUTER_SINGLE_ROW_CASE_ID => 1,
            ROUTER_TWO_ROW_CASE_ID => 2,
            _ => unreachable!("constructor admits only registered router cases"),
        }
    }
}

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RouterInstrumentationMode {
    MinimallyInstrumented,
    StageInstrumented,
}

impl RouterInstrumentationMode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::MinimallyInstrumented => "minimally_instrumented",
            Self::StageInstrumented => "stage_instrumented",
        }
    }
}

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq)]
enum RouterMonotonicClock {
    #[serde(rename = "perf_counter_ns")]
    PerfCounterNs,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RouterTimingStageStatus {
    Observed,
    Unavailable,
    NotApplicable,
}

impl RouterTimingStageStatus {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Observed => "observed",
            Self::Unavailable => "unavailable",
            Self::NotApplicable => "not_applicable",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RouterTimingStage {
    Observed { duration_ns: u64 },
    Unavailable { reason: String },
    NotApplicable { reason: String },
}

impl RouterTimingStage {
    pub const fn status(&self) -> RouterTimingStageStatus {
        match self {
            Self::Observed { .. } => RouterTimingStageStatus::Observed,
            Self::Unavailable { .. } => RouterTimingStageStatus::Unavailable,
            Self::NotApplicable { .. } => RouterTimingStageStatus::NotApplicable,
        }
    }

    pub const fn duration_ns(&self) -> Option<u64> {
        match self {
            Self::Observed { duration_ns } => Some(*duration_ns),
            Self::Unavailable { .. } | Self::NotApplicable { .. } => None,
        }
    }

    pub fn reason(&self) -> Option<&str> {
        match self {
            Self::Observed { .. } => None,
            Self::Unavailable { reason } | Self::NotApplicable { reason } => Some(reason),
        }
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RawRouterTimingStage {
    status: String,
    #[serde(default)]
    duration_ns: PresentRouterTimingField<u64>,
    #[serde(default)]
    reason: PresentRouterTimingField<String>,
}

#[derive(Default)]
enum PresentRouterTimingField<T> {
    #[default]
    Missing,
    Present(T),
}

impl<'de, T> Deserialize<'de> for PresentRouterTimingField<T>
where
    T: Deserialize<'de>,
{
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        T::deserialize(deserializer).map(Self::Present)
    }
}

impl<'de> Deserialize<'de> for RouterTimingStage {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let raw = RawRouterTimingStage::deserialize(deserializer)?;
        match (raw.status.as_str(), raw.duration_ns, raw.reason) {
            (
                "observed",
                PresentRouterTimingField::Present(duration_ns),
                PresentRouterTimingField::Missing,
            ) => Ok(Self::Observed { duration_ns }),
            (
                "unavailable",
                PresentRouterTimingField::Missing,
                PresentRouterTimingField::Present(reason),
            ) => Ok(Self::Unavailable { reason }),
            (
                "not_applicable",
                PresentRouterTimingField::Missing,
                PresentRouterTimingField::Present(reason),
            ) => Ok(Self::NotApplicable { reason }),
            _ => Err(de::Error::custom(
                "router timing stage fields contradict its status",
            )),
        }
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct RouterExecutionTiming {
    monotonic_clock: RouterMonotonicClock,
    instrumentation_mode: RouterInstrumentationMode,
    evaluated: bool,
    synchronized: bool,
    stages: BTreeMap<String, RouterTimingStage>,
}

impl RouterExecutionTiming {
    pub const fn monotonic_clock(&self) -> &'static str {
        match self.monotonic_clock {
            RouterMonotonicClock::PerfCounterNs => ROUTER_TIMING_CLOCK,
        }
    }

    pub const fn instrumentation_mode(&self) -> RouterInstrumentationMode {
        self.instrumentation_mode
    }

    pub const fn evaluated(&self) -> bool {
        self.evaluated
    }

    pub const fn synchronized(&self) -> bool {
        self.synchronized
    }

    pub fn stages(&self) -> &BTreeMap<String, RouterTimingStage> {
        &self.stages
    }

    pub fn stage(&self, name: &str) -> Option<&RouterTimingStage> {
        self.stages.get(name)
    }
}

/// Strict complete raw-worker result for one bounded router request.
///
/// `passed` confirms the evaluated GPU/no-fallback execution envelope and the
/// internal complete-output invariants. Golden-fixture or oracle agreement is
/// an independent host evidence gate.
#[derive(Debug, Clone, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct RouterResult {
    router_case_id: String,
    operation: String,
    requested_device: String,
    selected_device: String,
    fallback_used: bool,
    evaluated: bool,
    synchronized: bool,
    batch_size: u64,
    hidden_width: u64,
    expert_count: u64,
    top_k: u64,
    output_dtype: String,
    logits: Vec<Vec<f64>>,
    full_probabilities: Vec<Vec<f64>>,
    selected_expert_ids: Vec<Vec<u64>>,
    selected_probabilities: Vec<Vec<f64>>,
    normalized_weights: Vec<Vec<f64>>,
    logits_f32le_sha256: String,
    full_probabilities_f32le_sha256: String,
    selected_probabilities_f32le_sha256: String,
    normalized_weights_f32le_sha256: String,
    memory_gauges: TensorFixtureMemoryGauges,
    timing: RouterExecutionTiming,
    passed: bool,
}

impl RouterResult {
    pub fn router_case_id(&self) -> &str {
        &self.router_case_id
    }

    pub fn operation(&self) -> &str {
        &self.operation
    }

    pub fn requested_device(&self) -> &str {
        &self.requested_device
    }

    pub fn selected_device(&self) -> &str {
        &self.selected_device
    }

    pub fn fallback_used(&self) -> bool {
        self.fallback_used
    }

    pub fn evaluated(&self) -> bool {
        self.evaluated
    }

    pub fn synchronized(&self) -> bool {
        self.synchronized
    }

    pub fn batch_size(&self) -> u64 {
        self.batch_size
    }

    pub fn hidden_width(&self) -> u64 {
        self.hidden_width
    }

    pub fn expert_count(&self) -> u64 {
        self.expert_count
    }

    pub fn top_k(&self) -> u64 {
        self.top_k
    }

    pub fn output_dtype(&self) -> &str {
        &self.output_dtype
    }

    pub fn logits(&self) -> &[Vec<f64>] {
        &self.logits
    }

    pub fn full_probabilities(&self) -> &[Vec<f64>] {
        &self.full_probabilities
    }

    pub fn selected_expert_ids(&self) -> &[Vec<u64>] {
        &self.selected_expert_ids
    }

    pub fn selected_probabilities(&self) -> &[Vec<f64>] {
        &self.selected_probabilities
    }

    pub fn normalized_weights(&self) -> &[Vec<f64>] {
        &self.normalized_weights
    }

    pub fn logits_f32le_sha256(&self) -> &str {
        &self.logits_f32le_sha256
    }

    pub fn full_probabilities_f32le_sha256(&self) -> &str {
        &self.full_probabilities_f32le_sha256
    }

    pub fn selected_probabilities_f32le_sha256(&self) -> &str {
        &self.selected_probabilities_f32le_sha256
    }

    pub fn normalized_weights_f32le_sha256(&self) -> &str {
        &self.normalized_weights_f32le_sha256
    }

    pub fn memory_gauges(&self) -> &TensorFixtureMemoryGauges {
        &self.memory_gauges
    }

    pub fn timing(&self) -> &RouterExecutionTiming {
        &self.timing
    }

    pub fn passed(&self) -> bool {
        self.passed
    }
}

pub(crate) fn parse_router_result(
    value: Value,
    request: &RouterRequest,
) -> Result<RouterResult, WorkerError> {
    let result: RouterResult = serde_json::from_value(value).map_err(|_| {
        fixture_protocol_error("router result does not match its bounded protocol-v1 schema")
    })?;
    validate_router_numeric_rows(&result.logits)?;
    validate_router_numeric_rows(&result.full_probabilities)?;
    validate_router_numeric_rows(&result.selected_probabilities)?;
    validate_router_numeric_rows(&result.normalized_weights)?;
    validate_router_result(&result, request)?;
    Ok(result)
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ModelSliceMemoryGauges {
    model_file_bytes: Option<u64>,
    mapped_virtual_bytes: u64,
    mapped_resident_bytes: u64,
    owned_compressed_bytes: u64,
    decoded_array_bytes: u64,
    activation_array_bytes: u64,
    output_bytes: u64,
    temporary_current_bytes: u64,
    temporary_peak_bytes: u64,
    mlx_active_bytes: Option<u64>,
    mlx_cache_bytes: Option<u64>,
    mlx_peak_bytes: Option<u64>,
    process_footprint_bytes: Option<u64>,
    process_footprint_source: Option<String>,
    process_physical_footprint_bytes: Option<u64>,
    process_physical_footprint_peak_bytes: Option<u64>,
    process_physical_footprint_source: Option<String>,
    system_pressure: Option<String>,
    reported_summed_total_bytes: Option<u64>,
}

impl ModelSliceMemoryGauges {
    pub fn model_file_bytes(&self) -> Option<u64> {
        self.model_file_bytes
    }

    pub fn mapped_virtual_bytes(&self) -> u64 {
        self.mapped_virtual_bytes
    }

    pub fn mapped_resident_bytes(&self) -> u64 {
        self.mapped_resident_bytes
    }

    pub fn owned_compressed_bytes(&self) -> u64 {
        self.owned_compressed_bytes
    }

    pub fn decoded_array_bytes(&self) -> u64 {
        self.decoded_array_bytes
    }

    pub fn activation_array_bytes(&self) -> u64 {
        self.activation_array_bytes
    }

    pub fn output_bytes(&self) -> u64 {
        self.output_bytes
    }

    pub fn temporary_current_bytes(&self) -> u64 {
        self.temporary_current_bytes
    }

    pub fn temporary_peak_bytes(&self) -> u64 {
        self.temporary_peak_bytes
    }

    pub fn mlx_active_bytes(&self) -> Option<u64> {
        self.mlx_active_bytes
    }

    pub fn mlx_cache_bytes(&self) -> Option<u64> {
        self.mlx_cache_bytes
    }

    pub fn mlx_peak_bytes(&self) -> Option<u64> {
        self.mlx_peak_bytes
    }

    pub fn process_footprint_bytes(&self) -> Option<u64> {
        self.process_footprint_bytes
    }

    pub fn process_footprint_source(&self) -> Option<&str> {
        self.process_footprint_source.as_deref()
    }

    pub fn process_physical_footprint_bytes(&self) -> Option<u64> {
        self.process_physical_footprint_bytes
    }

    pub fn process_physical_footprint_peak_bytes(&self) -> Option<u64> {
        self.process_physical_footprint_peak_bytes
    }

    pub fn process_physical_footprint_source(&self) -> Option<&str> {
        self.process_physical_footprint_source.as_deref()
    }

    pub fn system_pressure(&self) -> Option<&str> {
        self.system_pressure.as_deref()
    }

    pub fn reported_summed_total_bytes(&self) -> Option<u64> {
        self.reported_summed_total_bytes
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ModelSliceResult {
    slice_id: String,
    operation: String,
    tensor_name: String,
    output_name: String,
    requested_device: String,
    selected_device: String,
    fallback_used: bool,
    output_shape: Vec<u64>,
    output_dtype: String,
    evaluated: bool,
    synchronized: bool,
    actual: Vec<f64>,
    encoded_slice_sha256: String,
    decoded_slice_sha256: String,
    activation_sha256: String,
    output_sha256: String,
    memory_gauges: ModelSliceMemoryGauges,
}

impl ModelSliceResult {
    pub fn slice_id(&self) -> &str {
        &self.slice_id
    }

    pub fn operation(&self) -> &str {
        &self.operation
    }

    pub fn tensor_name(&self) -> &str {
        &self.tensor_name
    }

    pub fn output_name(&self) -> &str {
        &self.output_name
    }

    pub fn requested_device(&self) -> &str {
        &self.requested_device
    }

    pub fn selected_device(&self) -> &str {
        &self.selected_device
    }

    pub fn fallback_used(&self) -> bool {
        self.fallback_used
    }

    pub fn output_shape(&self) -> &[u64] {
        &self.output_shape
    }

    pub fn output_dtype(&self) -> &str {
        &self.output_dtype
    }

    pub fn evaluated(&self) -> bool {
        self.evaluated
    }

    pub fn synchronized(&self) -> bool {
        self.synchronized
    }

    pub fn actual(&self) -> &[f64] {
        &self.actual
    }

    pub fn encoded_slice_sha256(&self) -> &str {
        &self.encoded_slice_sha256
    }

    pub fn decoded_slice_sha256(&self) -> &str {
        &self.decoded_slice_sha256
    }

    pub fn activation_sha256(&self) -> &str {
        &self.activation_sha256
    }

    pub fn output_sha256(&self) -> &str {
        &self.output_sha256
    }

    pub fn memory_gauges(&self) -> &ModelSliceMemoryGauges {
        &self.memory_gauges
    }
}

pub(crate) fn parse_model_slice_result(
    value: Value,
    request: &ModelSliceRequest,
    expected_encoded_sha256: &str,
) -> Result<ModelSliceResult, WorkerError> {
    if !valid_sha256(expected_encoded_sha256) {
        return Err(fixture_protocol_error(
            "expected model-slice checksum is not lowercase SHA-256",
        ));
    }
    let mut result: ModelSliceResult = serde_json::from_value(value).map_err(|_| {
        fixture_protocol_error("model-slice result does not match its bounded schema")
    })?;
    for value in &mut result.actual {
        if !value.is_finite() {
            return Err(fixture_protocol_error(
                "model-slice readback contains a non-finite value",
            ));
        }
        let canonical = *value as f32;
        if !canonical.is_finite() {
            return Err(fixture_protocol_error(
                "model-slice readback is outside float32 range",
            ));
        }
        *value = f64::from(canonical);
    }
    validate_model_slice_result(&result, request, expected_encoded_sha256)?;
    Ok(result)
}

impl SyntheticMoeRequest {
    pub fn new(
        fixture_id: impl Into<String>,
        device: impl Into<String>,
    ) -> Result<Self, WorkerError> {
        let fixture_id = fixture_id.into();
        let device = device.into();
        validate_fixture_identifier(&fixture_id, "synthetic fixture ID")?;
        if fixture_id != "synthetic-routed-moe-v1" {
            return Err(fixture_protocol_error(
                "synthetic MoE validation accepts only the committed fixture",
            ));
        }
        if device != APPLE_MLX_DEVICE_ID {
            return Err(fixture_protocol_error(
                "synthetic MoE validation requires the explicit MLX GPU device",
            ));
        }
        Ok(Self { fixture_id, device })
    }

    pub fn fixture_id(&self) -> &str {
        &self.fixture_id
    }

    pub fn device(&self) -> &str {
        &self.device
    }

    pub const fn allow_fallback(&self) -> bool {
        false
    }

    pub(crate) fn protocol_params(&self) -> Map<String, Value> {
        Map::from_iter([
            (
                "fixture_id".to_owned(),
                Value::String(self.fixture_id.clone()),
            ),
            ("device".to_owned(), Value::String(self.device.clone())),
            ("allow_fallback".to_owned(), Value::Bool(false)),
        ])
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct FetchedExpertEvidence {
    expert_id: u64,
    offset: u64,
    length: u64,
    shard_id: String,
    payload_sha256: String,
}

impl FetchedExpertEvidence {
    pub fn expert_id(&self) -> u64 {
        self.expert_id
    }

    pub fn offset(&self) -> u64 {
        self.offset
    }

    pub fn length(&self) -> u64 {
        self.length
    }

    pub fn shard_id(&self) -> &str {
        &self.shard_id
    }

    pub fn payload_sha256(&self) -> &str {
        &self.payload_sha256
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct SyntheticMoeComparison {
    oracle_id: String,
    absolute_tolerance: f64,
    relative_tolerance: f64,
    compared_count: u64,
    max_absolute_error: f64,
    max_relative_error: f64,
    first_mismatch_index: Option<u64>,
    passed: bool,
}

impl SyntheticMoeComparison {
    pub fn oracle_id(&self) -> &str {
        &self.oracle_id
    }

    pub fn absolute_tolerance(&self) -> f64 {
        self.absolute_tolerance
    }

    pub fn relative_tolerance(&self) -> f64 {
        self.relative_tolerance
    }

    pub fn compared_count(&self) -> u64 {
        self.compared_count
    }

    pub fn max_absolute_error(&self) -> f64 {
        self.max_absolute_error
    }

    pub fn max_relative_error(&self) -> f64 {
        self.max_relative_error
    }

    pub fn first_mismatch_index(&self) -> Option<u64> {
        self.first_mismatch_index
    }

    pub fn passed(&self) -> bool {
        self.passed
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct SyntheticMoeResult {
    fixture_id: String,
    fixture_kind: String,
    backend_id: String,
    requested_device: String,
    selected_device: String,
    fallback_used: bool,
    evaluated: bool,
    synchronized: bool,
    token_count: u64,
    hidden_size: u64,
    expert_count: u64,
    top_k: u64,
    selected_expert_ids: Vec<Vec<u64>>,
    normalized_weights: Vec<Vec<f64>>,
    fetched_experts: Vec<FetchedExpertEvidence>,
    actual: Vec<f64>,
    comparison: SyntheticMoeComparison,
    memory_gauges: TensorFixtureMemoryGauges,
    passed: bool,
}

impl SyntheticMoeResult {
    pub fn fixture_id(&self) -> &str {
        &self.fixture_id
    }

    pub fn backend_id(&self) -> &str {
        &self.backend_id
    }

    pub fn requested_device(&self) -> &str {
        &self.requested_device
    }

    pub fn selected_device(&self) -> &str {
        &self.selected_device
    }

    pub fn fallback_used(&self) -> bool {
        self.fallback_used
    }

    pub fn token_count(&self) -> u64 {
        self.token_count
    }

    pub fn hidden_size(&self) -> u64 {
        self.hidden_size
    }

    pub fn expert_count(&self) -> u64 {
        self.expert_count
    }

    pub fn top_k(&self) -> u64 {
        self.top_k
    }

    pub fn selected_expert_ids(&self) -> &[Vec<u64>] {
        &self.selected_expert_ids
    }

    pub fn normalized_weights(&self) -> &[Vec<f64>] {
        &self.normalized_weights
    }

    pub fn fetched_experts(&self) -> &[FetchedExpertEvidence] {
        &self.fetched_experts
    }

    pub fn actual(&self) -> &[f64] {
        &self.actual
    }

    pub fn comparison(&self) -> &SyntheticMoeComparison {
        &self.comparison
    }

    pub fn memory_gauges(&self) -> &TensorFixtureMemoryGauges {
        &self.memory_gauges
    }

    pub fn evaluated(&self) -> bool {
        self.evaluated
    }

    pub fn synchronized(&self) -> bool {
        self.synchronized
    }

    pub fn passed(&self) -> bool {
        self.passed
    }
}

pub(crate) fn parse_synthetic_moe_result(
    value: Value,
    request: &SyntheticMoeRequest,
    max_fixture_elements: u64,
) -> Result<SyntheticMoeResult, WorkerError> {
    let result: SyntheticMoeResult = serde_json::from_value(value).map_err(|_| {
        fixture_protocol_error("synthetic MoE result does not match its bounded schema")
    })?;
    validate_synthetic_moe_result(&result, request, max_fixture_elements)?;
    Ok(result)
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct WorkerDevice {
    id: String,
    kind: String,
}

impl WorkerDevice {
    pub fn id(&self) -> &str {
        &self.id
    }

    pub fn kind(&self) -> &str {
        &self.kind
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct WorkerCapabilities {
    operations: Vec<String>,
    dtypes: Vec<String>,
}

impl WorkerCapabilities {
    pub fn operations(&self) -> &[String] {
        &self.operations
    }

    pub fn dtypes(&self) -> &[String] {
        &self.dtypes
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct WorkerAdvertisedLimits {
    max_request_bytes: u64,
    max_response_bytes: u64,
    max_fixture_elements: u64,
}

impl WorkerAdvertisedLimits {
    pub fn max_request_bytes(&self) -> u64 {
        self.max_request_bytes
    }

    pub fn max_response_bytes(&self) -> u64 {
        self.max_response_bytes
    }

    pub fn max_fixture_elements(&self) -> u64 {
        self.max_fixture_elements
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct WorkerHello {
    protocol: u32,
    op: String,
    worker_version: String,
    python_version: String,
    python_arch: String,
    mlx_version: String,
    macos_version: String,
    metal_available: bool,
    gpu_count: u64,
    devices: Vec<WorkerDevice>,
    capabilities: WorkerCapabilities,
    limits: WorkerAdvertisedLimits,
}

impl WorkerHello {
    pub fn protocol(&self) -> u32 {
        self.protocol
    }

    pub fn request_id(&self) -> Option<u64> {
        None
    }

    pub fn worker_version(&self) -> &str {
        &self.worker_version
    }

    pub fn python_version(&self) -> &str {
        &self.python_version
    }

    pub fn python_arch(&self) -> &str {
        &self.python_arch
    }

    pub fn mlx_version(&self) -> &str {
        &self.mlx_version
    }

    pub fn macos_version(&self) -> &str {
        &self.macos_version
    }

    pub fn metal_available(&self) -> bool {
        self.metal_available
    }

    pub fn gpu_count(&self) -> u64 {
        self.gpu_count
    }

    pub fn devices(&self) -> &[WorkerDevice] {
        &self.devices
    }

    pub fn capabilities(&self) -> &WorkerCapabilities {
        &self.capabilities
    }

    pub fn limits(&self) -> &WorkerAdvertisedLimits {
        &self.limits
    }
}

pub fn parse_hello_line(
    line: &[u8],
    expected: &HelloExpectation,
    limits: &ProtocolLimits,
) -> Result<WorkerHello, WorkerError> {
    let value = parse_stdout_json_line(line, limits.max_response_bytes, limits)?;
    let hello: WorkerHello = serde_json::from_value(value).map_err(|_| {
        WorkerError::new(
            WorkerErrorKind::StdoutContamination,
            "worker hello envelope is malformed",
        )
    })?;

    if hello.protocol != expected.protocol || hello.protocol != PROTOCOL_VERSION {
        return Err(hello_error(
            "worker protocol version does not match the pin",
        ));
    }
    if hello.op != "hello" {
        return Err(hello_error("first worker message is not a hello"));
    }
    if hello.worker_version != expected.worker_version {
        return Err(hello_error("worker version does not match the pin"));
    }
    if hello.mlx_version != expected.mlx_version {
        return Err(hello_error("MLX version does not match the pin"));
    }

    validate_hello_metadata(&hello, limits)?;
    Ok(hello)
}

#[derive(Debug, Clone, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
struct RawResponseEnvelope {
    protocol: u32,
    request_id: u64,
    ok: bool,
    result: Option<Value>,
    error: Option<RemoteErrorEnvelope>,
}

#[derive(Debug, Clone, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
struct RemoteErrorEnvelope {
    code: String,
    message: String,
    retryable: bool,
    details: Value,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ResponseEnvelope {
    protocol: u32,
    request_id: u64,
    result: Result<Value, WorkerError>,
}

impl ResponseEnvelope {
    pub fn protocol(&self) -> u32 {
        self.protocol
    }

    pub fn request_id(&self) -> u64 {
        self.request_id
    }

    pub fn into_result(self) -> Result<Value, WorkerError> {
        self.result
    }
}

pub fn parse_response_line(
    line: &[u8],
    expected_request_id: u64,
    limits: &ProtocolLimits,
) -> Result<ResponseEnvelope, WorkerError> {
    let value = parse_stdout_json_line(line, limits.max_response_bytes, limits)?;
    let raw: RawResponseEnvelope = serde_json::from_value(value).map_err(|_| {
        WorkerError::new(
            WorkerErrorKind::StdoutContamination,
            "worker response envelope is malformed",
        )
    })?;

    if raw.protocol != PROTOCOL_VERSION {
        return Err(WorkerError::new(
            WorkerErrorKind::Protocol,
            "worker response protocol version does not match",
        ));
    }
    if raw.request_id != expected_request_id {
        return Err(WorkerError::new(
            WorkerErrorKind::RequestIdMismatch,
            "worker response request ID does not match the active request",
        ));
    }

    let result = match (raw.ok, raw.result, raw.error) {
        (true, Some(result), None) if result.is_object() => Ok(result),
        (false, None, Some(error)) => Err(WorkerError::from_remote(error)?),
        _ => {
            return Err(WorkerError::new(
                WorkerErrorKind::StdoutContamination,
                "worker response success and error fields are inconsistent",
            ));
        }
    };

    Ok(ResponseEnvelope {
        protocol: raw.protocol,
        request_id: raw.request_id,
        result,
    })
}

fn validate_hello_metadata(
    hello: &WorkerHello,
    local_limits: &ProtocolLimits,
) -> Result<(), WorkerError> {
    for (value, label) in [
        (&hello.python_version, "Python version"),
        (&hello.python_arch, "Python architecture"),
        (&hello.macos_version, "macOS version"),
    ] {
        validate_identifier(value, label, WorkerErrorKind::HelloNegotiation)?;
    }

    if hello.devices.len() > MAX_DEVICE_COUNT
        || u64::try_from(hello.devices.len()).ok() != Some(hello.gpu_count)
    {
        return Err(hello_error("worker device inventory is inconsistent"));
    }
    for device in &hello.devices {
        validate_identifier(&device.id, "device ID", WorkerErrorKind::HelloNegotiation)?;
        validate_identifier(
            &device.kind,
            "device kind",
            WorkerErrorKind::HelloNegotiation,
        )?;
    }

    validate_capabilities(&hello.capabilities.operations, "operation")?;
    validate_capabilities(&hello.capabilities.dtypes, "dtype")?;
    for required in ["health", "shutdown"] {
        if !hello
            .capabilities
            .operations
            .iter()
            .any(|operation| operation == required)
        {
            return Err(hello_error("worker omits a required protocol operation"));
        }
    }

    let advertised_request = usize::try_from(hello.limits.max_request_bytes)
        .map_err(|_| hello_error("worker request limit is not representable"))?;
    let advertised_response = usize::try_from(hello.limits.max_response_bytes)
        .map_err(|_| hello_error("worker response limit is not representable"))?;
    if advertised_request == 0
        || advertised_response == 0
        || hello.limits.max_fixture_elements == 0
        || advertised_request > local_limits.max_request_bytes
        || advertised_response > local_limits.max_response_bytes
    {
        return Err(hello_error("worker limits exceed the protocol-v1 bounds"));
    }
    Ok(())
}

fn validate_capabilities(values: &[String], label: &str) -> Result<(), WorkerError> {
    if values.is_empty() || values.len() > MAX_CAPABILITY_COUNT {
        return Err(hello_error("worker capability inventory is not bounded"));
    }
    let mut unique = BTreeSet::new();
    for value in values {
        validate_identifier(value, label, WorkerErrorKind::HelloNegotiation)?;
        if !unique.insert(value.as_str()) {
            return Err(hello_error(
                "worker capability inventory contains duplicates",
            ));
        }
    }
    Ok(())
}

fn parse_stdout_json_line(
    line: &[u8],
    max_bytes: usize,
    limits: &ProtocolLimits,
) -> Result<Value, WorkerError> {
    let payload = framed_payload(line, max_bytes)?;
    let NoDuplicateValue(value) =
        serde_json::from_slice::<NoDuplicateValue>(payload).map_err(|_| {
            WorkerError::new(
                WorkerErrorKind::StdoutContamination,
                "worker stdout is not one valid JSON object",
            )
        })?;
    if !value.is_object() {
        return Err(WorkerError::new(
            WorkerErrorKind::StdoutContamination,
            "worker stdout JSON root must be an object",
        ));
    }
    validate_value_limits(&value, limits)?;
    Ok(value)
}

fn framed_payload(line: &[u8], max_bytes: usize) -> Result<&[u8], WorkerError> {
    let Some(payload) = line.strip_suffix(b"\n") else {
        return Err(WorkerError::new(
            WorkerErrorKind::StdoutContamination,
            "worker stdout message is not LF terminated",
        ));
    };
    if payload.is_empty() || payload.ends_with(b"\r") || payload.contains(&b'\n') {
        return Err(WorkerError::new(
            WorkerErrorKind::StdoutContamination,
            "worker stdout framing is invalid",
        ));
    }
    if payload.len() > max_bytes {
        return Err(WorkerError::new(
            WorkerErrorKind::MessageTooLarge,
            "worker stdout line exceeds the configured byte limit",
        ));
    }
    Ok(payload)
}

fn validate_value_limits(value: &Value, limits: &ProtocolLimits) -> Result<(), WorkerError> {
    fn visit(value: &Value, depth: usize, limits: &ProtocolLimits) -> Result<(), WorkerError> {
        if depth > limits.max_nesting_depth {
            return Err(WorkerError::new(
                WorkerErrorKind::MessageTooLarge,
                "protocol JSON nesting exceeds the configured bound",
            ));
        }
        match value {
            Value::Array(values) => {
                if values.len() > limits.max_list_items {
                    return Err(WorkerError::new(
                        WorkerErrorKind::MessageTooLarge,
                        "protocol JSON list exceeds the configured bound",
                    ));
                }
                for value in values {
                    visit(value, depth + 1, limits)?;
                }
            }
            Value::Object(values) => {
                if values.len() > limits.max_list_items {
                    return Err(WorkerError::new(
                        WorkerErrorKind::MessageTooLarge,
                        "protocol JSON object exceeds the configured bound",
                    ));
                }
                for value in values.values() {
                    visit(value, depth + 1, limits)?;
                }
            }
            _ => {}
        }
        Ok(())
    }
    visit(value, 1, limits)
}

fn validate_tensor_fixture_result(
    result: &TensorFixtureResult,
    request: &TensorFixtureRequest,
    max_fixture_elements: u64,
) -> Result<(), WorkerError> {
    if max_fixture_elements == 0 {
        return Err(fixture_protocol_error(
            "worker advertised an invalid fixture element bound",
        ));
    }
    if result.fixture_set_id != request.fixture_set_id {
        return Err(fixture_protocol_error(
            "worker fixture-set identity does not match the request",
        ));
    }
    if result.case_id != request.case_id {
        return Err(fixture_protocol_error(
            "worker fixture case identity does not match the request",
        ));
    }
    if result.operation != request.operation {
        return Err(fixture_protocol_error(
            "worker fixture operation does not match the request",
        ));
    }
    if result.backend_id != APPLE_MLX_BACKEND_ID {
        return Err(fixture_protocol_error(
            "worker fixture result identifies the wrong backend",
        ));
    }
    if result.requested_device != request.device || result.selected_device != request.device {
        return Err(fixture_protocol_error(
            "worker fixture result identifies the wrong device",
        ));
    }
    if result.fallback_used {
        return Err(fixture_protocol_error(
            "worker fixture result reports forbidden fallback",
        ));
    }
    if !result.evaluated || !result.synchronized {
        return Err(fixture_protocol_error(
            "worker fixture result lacks evaluated synchronized readback",
        ));
    }

    let output_elements = checked_fixture_shape_product(&result.output_shape)?;
    if output_elements > max_fixture_elements {
        return Err(WorkerError::new(
            WorkerErrorKind::MessageTooLarge,
            "worker fixture output exceeds the negotiated element bound",
        ));
    }
    let output_elements = usize::try_from(output_elements).map_err(|_| {
        fixture_protocol_error("worker fixture output cardinality is not representable")
    })?;
    if result.actual.len() != output_elements {
        return Err(fixture_protocol_error(
            "worker fixture readback cardinality does not match its shape",
        ));
    }
    if result.actual.iter().any(|value| !value.is_finite()) {
        return Err(fixture_protocol_error(
            "worker fixture readback contains a non-finite value",
        ));
    }

    validate_fixture_dtypes(result)?;
    validate_fixture_comparison(&result.comparison, output_elements)?;
    validate_fixture_memory_gauges(&result.memory_gauges)?;
    validate_operation_specific_result(result, max_fixture_elements)?;

    if result.passed != result.comparison.passed {
        return Err(fixture_protocol_error(
            "worker fixture result contradicts its comparison status",
        ));
    }
    Ok(())
}

fn validate_synthetic_moe_result(
    result: &SyntheticMoeResult,
    request: &SyntheticMoeRequest,
    max_fixture_elements: u64,
) -> Result<(), WorkerError> {
    if result.fixture_id != request.fixture_id
        || result.fixture_kind != "synthetic"
        || result.backend_id != APPLE_MLX_BACKEND_ID
        || result.requested_device != request.device
        || result.selected_device != request.device
    {
        return Err(fixture_protocol_error(
            "synthetic MoE result identity does not match its request",
        ));
    }
    if result.fallback_used || !result.evaluated || !result.synchronized {
        return Err(fixture_protocol_error(
            "synthetic MoE result lacks explicit evaluated GPU execution",
        ));
    }
    if result.token_count == 0
        || result.hidden_size == 0
        || result.expert_count == 0
        || result.top_k == 0
        || result.top_k > result.expert_count
    {
        return Err(fixture_protocol_error(
            "synthetic MoE dimensions or top-k are invalid",
        ));
    }
    if result.token_count != 2
        || result.hidden_size != 2
        || result.expert_count != 4
        || result.top_k != 2
    {
        return Err(fixture_protocol_error(
            "synthetic MoE dimensions differ from the committed fixture",
        ));
    }
    let output_count = result
        .token_count
        .checked_mul(result.hidden_size)
        .ok_or_else(|| fixture_protocol_error("synthetic MoE output cardinality overflows"))?;
    if output_count > max_fixture_elements
        || usize::try_from(output_count).ok() != Some(result.actual.len())
        || result.actual.iter().any(|value| !value.is_finite())
    {
        return Err(fixture_protocol_error(
            "synthetic MoE output is invalid or exceeds its bound",
        ));
    }
    let token_count = usize::try_from(result.token_count)
        .map_err(|_| fixture_protocol_error("synthetic token count is not representable"))?;
    let top_k = usize::try_from(result.top_k)
        .map_err(|_| fixture_protocol_error("synthetic top-k is not representable"))?;
    if result.selected_expert_ids.len() != token_count
        || result.normalized_weights.len() != token_count
    {
        return Err(fixture_protocol_error(
            "synthetic route row count does not match token count",
        ));
    }
    if result.selected_expert_ids != [vec![1, 2], vec![3, 1]] {
        return Err(fixture_protocol_error(
            "synthetic routes differ from the committed scalar oracle",
        ));
    }

    let mut routed_experts = BTreeSet::new();
    for (ids, weights) in result
        .selected_expert_ids
        .iter()
        .zip(&result.normalized_weights)
    {
        if ids.len() != top_k || weights.len() != top_k {
            return Err(fixture_protocol_error(
                "synthetic route width does not match top-k",
            ));
        }
        for id in ids {
            if *id >= result.expert_count {
                return Err(fixture_protocol_error(
                    "synthetic route contains an out-of-range expert",
                ));
            }
            routed_experts.insert(*id);
        }
        if weights
            .iter()
            .any(|weight| !weight.is_finite() || *weight < 0.0)
            || (weights.iter().sum::<f64>() - 1.0).abs() > 1.0e-6
        {
            return Err(fixture_protocol_error(
                "synthetic route weights are non-finite, negative, or unnormalized",
            ));
        }
    }

    let expected_weights = [0.5, 0.5, 0.731_058_578_630_004_8, 0.268_941_421_369_995_2];
    if result
        .normalized_weights
        .iter()
        .flatten()
        .zip(expected_weights)
        .any(|(actual, expected)| (actual - expected).abs() > 1.0e-6)
    {
        return Err(fixture_protocol_error(
            "synthetic route weights differ from the committed scalar oracle",
        ));
    }

    let mut fetched_experts = BTreeSet::new();
    for fetched in &result.fetched_experts {
        validate_fixture_identifier(&fetched.shard_id, "synthetic shard ID")?;
        if fetched.expert_id >= result.expert_count
            || fetched.length == 0
            || fetched.offset.checked_add(fetched.length).is_none()
            || fetched.payload_sha256.len() != 64
            || !fetched
                .payload_sha256
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
            || !fetched_experts.insert(fetched.expert_id)
        {
            return Err(fixture_protocol_error(
                "synthetic fetched-expert evidence is malformed or duplicated",
            ));
        }
    }
    if fetched_experts != routed_experts {
        return Err(fixture_protocol_error(
            "synthetic fetched experts do not match the unique routed experts",
        ));
    }
    let expected_fetches = [
        (
            1,
            16,
            16,
            "experts-00001-of-00002",
            "59f6b8505959d216462694b9e7b20728e6ce4199aa6fcf652386b0774e22f1c7",
        ),
        (
            2,
            32,
            16,
            "experts-00002-of-00002",
            "a527f6c2fbde17555714773e4d5ce06608d7f336389de936d73f09383fd17960",
        ),
        (
            3,
            48,
            16,
            "experts-00002-of-00002",
            "7cc507b4e456b5c69819f532111018c3d428adc29485bf9ec6b38112d66acbba",
        ),
    ];
    if result.fetched_experts.len() != expected_fetches.len()
        || result
            .fetched_experts
            .iter()
            .zip(expected_fetches)
            .any(|(actual, expected)| {
                actual.expert_id != expected.0
                    || actual.offset != expected.1
                    || actual.length != expected.2
                    || actual.shard_id != expected.3
                    || actual.payload_sha256 != expected.4
            })
    {
        return Err(fixture_protocol_error(
            "synthetic fetch evidence differs from the committed fixture",
        ));
    }

    validate_fixture_identifier(&result.comparison.oracle_id, "synthetic oracle ID")?;
    for value in [
        result.comparison.absolute_tolerance,
        result.comparison.relative_tolerance,
        result.comparison.max_absolute_error,
        result.comparison.max_relative_error,
    ] {
        if !value.is_finite() || value < 0.0 {
            return Err(fixture_protocol_error(
                "synthetic comparison contains an invalid metric",
            ));
        }
    }
    if result.comparison.compared_count != output_count
        || result.comparison.first_mismatch_index.is_some() == result.comparison.passed
        || result.passed != result.comparison.passed
    {
        return Err(fixture_protocol_error(
            "synthetic comparison contradicts its output or pass status",
        ));
    }
    if result.comparison.oracle_id != "committed-scalar-routed-moe-v1"
        || result.comparison.absolute_tolerance != 1.0e-5
        || result.comparison.relative_tolerance != 1.0e-5
    {
        return Err(fixture_protocol_error(
            "synthetic comparison contract differs from the committed oracle",
        ));
    }
    let expected_output = [2.0, 2.0, 4.069_116_116_437_53, 4.037_882_842_739_99];
    if result
        .actual
        .iter()
        .zip(expected_output)
        .any(|(actual, expected)| {
            let absolute_error = (actual - expected).abs();
            let relative_error = absolute_error / expected.abs().max(f64::MIN_POSITIVE);
            absolute_error > result.comparison.absolute_tolerance
                && relative_error > result.comparison.relative_tolerance
        })
    {
        return Err(fixture_protocol_error(
            "synthetic output differs from the committed scalar oracle",
        ));
    }
    if result.comparison.passed
        && result.comparison.max_absolute_error > result.comparison.absolute_tolerance
        && result.comparison.max_relative_error > result.comparison.relative_tolerance
    {
        return Err(fixture_protocol_error(
            "synthetic comparison exceeds its declared tolerances",
        ));
    }
    validate_fixture_memory_gauges(&result.memory_gauges)?;
    Ok(())
}

fn checked_fixture_shape_product(shape: &[u64]) -> Result<u64, WorkerError> {
    if shape.is_empty() || shape.len() > MAX_NESTING_DEPTH || shape.contains(&0) {
        return Err(fixture_protocol_error(
            "worker fixture output shape is empty, zero, or too deep",
        ));
    }
    shape.iter().try_fold(1_u64, |product, dimension| {
        product
            .checked_mul(*dimension)
            .ok_or_else(|| fixture_protocol_error("worker fixture output shape product overflows"))
    })
}

fn validate_fixture_dtypes(result: &TensorFixtureResult) -> Result<(), WorkerError> {
    let expected_input = if result.operation == "q8_0_decode_dot" {
        "q8_0"
    } else {
        "float32"
    };
    if result.input_dtype != expected_input
        || result.accumulation_dtype != "float32"
        || result.output_dtype != "float32"
    {
        return Err(fixture_protocol_error(
            "worker fixture result contains an unsupported dtype contract",
        ));
    }
    Ok(())
}

fn validate_fixture_comparison(
    comparison: &TensorFixtureComparison,
    output_elements: usize,
) -> Result<(), WorkerError> {
    validate_fixture_identifier(&comparison.oracle_id, "fixture oracle ID")?;
    if !matches!(comparison.mode.as_str(), "exact" | "abs_rel") {
        return Err(fixture_protocol_error(
            "worker fixture comparison mode is unsupported",
        ));
    }
    if comparison.non_finite_policy != "reject" {
        return Err(fixture_protocol_error(
            "worker fixture comparison must reject non-finite values",
        ));
    }
    for metric in [
        comparison.absolute_tolerance,
        comparison.relative_tolerance,
        comparison.max_absolute_error,
        comparison.max_relative_error,
    ] {
        if !metric.is_finite() || metric < 0.0 {
            return Err(fixture_protocol_error(
                "worker fixture comparison contains an invalid numeric metric",
            ));
        }
    }
    if comparison.mode == "exact"
        && (comparison.absolute_tolerance != 0.0 || comparison.relative_tolerance != 0.0)
    {
        return Err(fixture_protocol_error(
            "exact fixture comparison cannot declare nonzero tolerances",
        ));
    }

    let output_elements_u64 = u64::try_from(output_elements).map_err(|_| {
        fixture_protocol_error("worker fixture comparison cardinality is not representable")
    })?;
    if comparison.compared_count != output_elements_u64 {
        return Err(fixture_protocol_error(
            "worker fixture comparison cardinality does not match readback",
        ));
    }
    if let Some(index) = comparison.first_mismatch_index {
        if index >= comparison.compared_count {
            return Err(fixture_protocol_error(
                "worker fixture first mismatch index is out of bounds",
            ));
        }
    }

    if comparison.passed {
        if comparison.first_mismatch_index.is_some() {
            return Err(fixture_protocol_error(
                "passing fixture comparison reports a mismatch",
            ));
        }
        let within_policy = match comparison.mode.as_str() {
            "exact" => comparison.max_absolute_error == 0.0 && comparison.max_relative_error == 0.0,
            "abs_rel" => {
                comparison.max_absolute_error <= comparison.absolute_tolerance
                    || comparison.max_relative_error <= comparison.relative_tolerance
            }
            _ => false,
        };
        if !within_policy {
            return Err(fixture_protocol_error(
                "passing fixture comparison exceeds its declared tolerance",
            ));
        }
    } else if comparison.first_mismatch_index.is_none() {
        return Err(fixture_protocol_error(
            "failing fixture comparison omits its first mismatch",
        ));
    }
    Ok(())
}

fn validate_fixture_memory_gauges(memory: &TensorFixtureMemoryGauges) -> Result<(), WorkerError> {
    if memory.reported_summed_total_bytes.is_some() {
        return Err(fixture_protocol_error(
            "worker fixture memory gauges contain a forbidden summed total",
        ));
    }
    if let (Some(active), Some(peak)) = (memory.mlx_active_bytes, memory.mlx_peak_bytes) {
        if peak < active {
            return Err(fixture_protocol_error(
                "worker fixture MLX peak memory is below active memory",
            ));
        }
    }
    match (
        memory.process_footprint_bytes,
        memory.process_footprint_source.as_deref(),
    ) {
        (Some(_), Some(source)) => {
            validate_fixture_identifier(source, "process-footprint source")?;
        }
        (None, None) => {}
        _ => {
            return Err(fixture_protocol_error(
                "worker fixture process footprint and source are inconsistent",
            ));
        }
    }
    if let Some(pressure) = memory.system_pressure.as_deref() {
        validate_fixture_identifier(pressure, "system-pressure state")?;
    }
    Ok(())
}

fn validate_router_numeric_rows(rows: &[Vec<f64>]) -> Result<(), WorkerError> {
    for row in rows {
        for value in row {
            if !value.is_finite() {
                return Err(fixture_protocol_error(
                    "router result contains a non-finite numeric value",
                ));
            }
            let canonical = *value as f32;
            if !canonical.is_finite() {
                return Err(fixture_protocol_error(
                    "router result contains a value outside float32 range",
                ));
            }
            if f64::from(canonical).to_bits() != value.to_bits() {
                return Err(fixture_protocol_error(
                    "router result contains a noncanonical float32 wire value",
                ));
            }
        }
    }
    Ok(())
}

fn validate_router_execution_timing(timing: &RouterExecutionTiming) -> Result<(), WorkerError> {
    // The frozen `run_router` protocol-v1 operation is the minimally
    // instrumented execution boundary. Stage-instrumented observations are a
    // separate evidence-series mode and must never be relabeled as this result.
    if timing.monotonic_clock() != ROUTER_TIMING_CLOCK
        || timing.instrumentation_mode != RouterInstrumentationMode::MinimallyInstrumented
        || !timing.evaluated
        || !timing.synchronized
        || timing.stages.len() != 2
        || timing.stages.len() > MAX_ROUTER_TIMING_STAGES
    {
        return Err(fixture_protocol_error(
            "router timing contradicts the admitted minimal execution boundary",
        ));
    }

    for (stage_name, stage) in &timing.stages {
        if !valid_router_timing_stage_name(stage_name) {
            return Err(fixture_protocol_error(
                "router timing contains an unknown stage identity",
            ));
        }
        match stage {
            RouterTimingStage::Observed { duration_ns } => {
                if *duration_ns == 0 {
                    return Err(fixture_protocol_error(
                        "router timing contains a nonpositive observed duration",
                    ));
                }
            }
            RouterTimingStage::Unavailable { reason } => {
                validate_router_timing_reason(reason)?;
            }
            RouterTimingStage::NotApplicable { reason } => {
                validate_router_timing_reason(reason)?;
                if stage_name != "dequantization" {
                    return Err(fixture_protocol_error(
                        "router timing marks an unsupported stage not applicable",
                    ));
                }
            }
        }
    }

    match timing.stages.get("dequantization") {
        Some(RouterTimingStage::NotApplicable { reason })
            if reason == ROUTER_F32_DEQUANTIZATION_REASON => {}
        _ => {
            return Err(fixture_protocol_error(
                "router timing lacks canonical F32 dequantization evidence",
            ));
        }
    }
    match timing.stages.get("total_evaluated_router") {
        Some(RouterTimingStage::Observed { duration_ns }) if *duration_ns > 0 => {}
        _ => {
            return Err(fixture_protocol_error(
                "router timing lacks its positive evaluated total",
            ));
        }
    }
    Ok(())
}

fn valid_router_timing_stage_name(stage: &str) -> bool {
    matches!(
        stage,
        "setup_admission"
            | "file_io"
            | "storage_validation_f32_decode"
            | "dequantization"
            | "host_to_device"
            | "graph_construction"
            | "compilation"
            | "router_projection"
            | "top_k"
            | "normalization"
            | "total_evaluated_router"
            | "synchronized_readback"
            | "end_to_end_router_command"
    )
}

fn validate_router_timing_reason(reason: &str) -> Result<(), WorkerError> {
    if reason.is_empty()
        || reason.trim() != reason
        || reason.chars().count() > MAX_PROTOCOL_MESSAGE_CHARS
        || reason.chars().any(char::is_control)
        || sanitize_message(reason) != reason
    {
        return Err(fixture_protocol_error(
            "router timing contains an invalid or private reason",
        ));
    }
    Ok(())
}

fn validate_router_result(
    result: &RouterResult,
    request: &RouterRequest,
) -> Result<(), WorkerError> {
    validate_router_execution_timing(&result.timing)?;
    let expected_rows = request.expected_rows();
    if result.router_case_id != request.router_case_id
        || result.operation != ROUTER_OPERATION
        || result.requested_device != request.device
        || result.selected_device != APPLE_MLX_DEVICE_ID
        || result.fallback_used
        || !result.evaluated
        || !result.synchronized
        || result.batch_size != expected_rows as u64
        || result.batch_size == 0
        || result.batch_size > ROUTER_MAX_ROWS as u64
        || result.hidden_width != ROUTER_HIDDEN_WIDTH as u64
        || result.expert_count != ROUTER_EXPERT_COUNT as u64
        || result.top_k != ROUTER_TOP_K as u64
        || result.output_dtype != ROUTER_OUTPUT_DTYPE
        || result.evaluated != result.timing.evaluated
        || result.synchronized != result.timing.synchronized
        || !result.passed
    {
        return Err(fixture_protocol_error(
            "router result contradicts the exact admitted execution boundary",
        ));
    }
    if result.logits.len() != expected_rows
        || result.full_probabilities.len() != expected_rows
        || result.selected_expert_ids.len() != expected_rows
        || result.selected_probabilities.len() != expected_rows
        || result.normalized_weights.len() != expected_rows
    {
        return Err(fixture_protocol_error(
            "router result row count differs from the requested bounded case",
        ));
    }

    for row_index in 0..expected_rows {
        let logits = &result.logits[row_index];
        let probabilities = &result.full_probabilities[row_index];
        let ids = &result.selected_expert_ids[row_index];
        let selected = &result.selected_probabilities[row_index];
        let normalized = &result.normalized_weights[row_index];
        if logits.len() != ROUTER_EXPERT_COUNT
            || probabilities.len() != ROUTER_EXPERT_COUNT
            || ids.len() != ROUTER_TOP_K
            || selected.len() != ROUTER_TOP_K
            || normalized.len() != ROUTER_TOP_K
        {
            return Err(fixture_protocol_error(
                "router result omits a required complete or selected output",
            ));
        }
        if probabilities.iter().any(|value| *value < 0.0)
            || selected.iter().any(|value| *value < 0.0)
            || normalized.iter().any(|value| *value < 0.0)
        {
            return Err(fixture_protocol_error(
                "router probabilities or weights contain a negative value",
            ));
        }
        let probability_sum = probabilities.iter().sum::<f64>();
        let selected_sum = selected.iter().sum::<f64>();
        let normalized_sum = normalized.iter().sum::<f64>();
        if !probability_sum.is_finite()
            || (probability_sum - 1.0).abs() > ROUTER_PROBABILITY_SUM_TOLERANCE
            || !selected_sum.is_finite()
            || selected_sum <= 0.0
            || !normalized_sum.is_finite()
            || (normalized_sum - 1.0).abs() > ROUTER_PROBABILITY_SUM_TOLERANCE
        {
            return Err(fixture_protocol_error(
                "router probability or normalized-weight sum is invalid",
            ));
        }
        validate_router_softmax(logits, probabilities)?;

        let mut expected_ids = (0..ROUTER_EXPERT_COUNT).collect::<Vec<_>>();
        expected_ids.sort_by(|left, right| {
            let left_value = probabilities[*left] as f32;
            let right_value = probabilities[*right] as f32;
            right_value
                .total_cmp(&left_value)
                .then_with(|| left.cmp(right))
        });
        expected_ids.truncate(ROUTER_TOP_K);
        let unique = ids.iter().copied().collect::<BTreeSet<_>>();
        if unique.len() != ROUTER_TOP_K
            || ids
                .iter()
                .any(|expert_id| *expert_id >= ROUTER_EXPERT_COUNT as u64)
            || ids
                .iter()
                .copied()
                .ne(expected_ids.iter().map(|value| *value as u64))
        {
            return Err(fixture_protocol_error(
                "router selected expert IDs or ordering differ from complete probabilities",
            ));
        }
        for (rank, expert_id) in ids.iter().enumerate() {
            let expert_index = usize::try_from(*expert_id)
                .map_err(|_| fixture_protocol_error("router expert ID is not representable"))?;
            if (selected[rank] as f32).to_bits() != (probabilities[expert_index] as f32).to_bits() {
                return Err(fixture_protocol_error(
                    "router selected probability differs from its complete-softmax value",
                ));
            }
            let expected_weight = selected[rank] / selected_sum;
            if (normalized[rank] - expected_weight).abs() > ROUTER_PROBABILITY_SUM_TOLERANCE {
                return Err(fixture_protocol_error(
                    "router normalized weight differs from selected-probability normalization",
                ));
            }
        }
    }

    for checksum in [
        result.logits_f32le_sha256.as_str(),
        result.full_probabilities_f32le_sha256.as_str(),
        result.selected_probabilities_f32le_sha256.as_str(),
        result.normalized_weights_f32le_sha256.as_str(),
    ] {
        if !valid_sha256(checksum) {
            return Err(fixture_protocol_error(
                "router result contains a malformed SHA-256 identity",
            ));
        }
    }
    if hash_router_rows(&result.logits)? != result.logits_f32le_sha256
        || hash_router_rows(&result.full_probabilities)? != result.full_probabilities_f32le_sha256
        || hash_router_rows(&result.selected_probabilities)?
            != result.selected_probabilities_f32le_sha256
        || hash_router_rows(&result.normalized_weights)? != result.normalized_weights_f32le_sha256
    {
        return Err(fixture_protocol_error(
            "router result checksum does not match its complete float32 readback",
        ));
    }
    validate_fixture_memory_gauges(&result.memory_gauges)
}

fn validate_router_softmax(logits: &[f64], probabilities: &[f64]) -> Result<(), WorkerError> {
    if logits.len() != ROUTER_EXPERT_COUNT || probabilities.len() != ROUTER_EXPERT_COUNT {
        return Err(fixture_protocol_error(
            "router softmax inputs omit a required expert value",
        ));
    }
    let maximum = logits
        .iter()
        .copied()
        .reduce(f64::max)
        .expect("complete router row is nonempty");
    let exponentials = logits
        .iter()
        .map(|value| (*value - maximum).exp())
        .collect::<Vec<_>>();
    let denominator = exponentials.iter().sum::<f64>();
    if !denominator.is_finite() || denominator <= 0.0 {
        return Err(fixture_protocol_error(
            "router logits do not define a finite complete softmax",
        ));
    }
    for (candidate, exponential) in probabilities.iter().zip(exponentials) {
        let expected = exponential / denominator;
        let error = (*candidate - expected).abs();
        let admitted = ROUTER_PROBABILITY_ABSOLUTE_TOLERANCE
            + ROUTER_PROBABILITY_RELATIVE_TOLERANCE * expected.abs();
        if error > admitted {
            return Err(fixture_protocol_error(
                "router probabilities are not the full softmax of the complete logits",
            ));
        }
    }
    Ok(())
}

fn hash_router_rows(rows: &[Vec<f64>]) -> Result<String, WorkerError> {
    let values = rows
        .iter()
        .flatten()
        .map(|value| *value as f32)
        .collect::<Vec<_>>();
    canonical_f32le_sha256(&values)
        .map_err(|_| fixture_protocol_error("router result could not be canonically hashed"))
}

fn validate_model_slice_result(
    result: &ModelSliceResult,
    request: &ModelSliceRequest,
    expected_encoded_sha256: &str,
) -> Result<(), WorkerError> {
    if result.slice_id != request.slice_id
        || result.slice_id != MODEL_SLICE_ID
        || result.operation != MODEL_SLICE_OPERATION
        || result.tensor_name != MODEL_SLICE_TENSOR
        || result.output_name != MODEL_SLICE_OUTPUT
        || result.requested_device != request.device
        || result.selected_device != APPLE_MLX_DEVICE_ID
        || result.fallback_used
        || !result.evaluated
        || !result.synchronized
        || result.output_shape != [MODEL_SLICE_OUTPUT_COUNT as u64]
        || result.output_dtype != "float32"
    {
        return Err(fixture_protocol_error(
            "model-slice result contradicts the exact admitted execution boundary",
        ));
    }
    if result.actual.len() != MODEL_SLICE_OUTPUT_COUNT
        || result
            .actual
            .iter()
            .any(|value| !value.is_finite() || f64::from(*value as f32) != *value)
    {
        return Err(fixture_protocol_error(
            "model-slice readback is non-finite or has invalid cardinality",
        ));
    }
    for checksum in [
        result.encoded_slice_sha256.as_str(),
        result.decoded_slice_sha256.as_str(),
        result.activation_sha256.as_str(),
        result.output_sha256.as_str(),
    ] {
        if !valid_sha256(checksum) {
            return Err(fixture_protocol_error(
                "model-slice result contains a malformed SHA-256 identity",
            ));
        }
    }
    if result.encoded_slice_sha256 != expected_encoded_sha256
        || result.activation_sha256 != MODEL_SLICE_ACTIVATION_SHA256
    {
        return Err(fixture_protocol_error(
            "model-slice input identities differ from the admitted artifact and prompt",
        ));
    }
    let mut output_bytes = Vec::with_capacity(MODEL_SLICE_OUTPUT_BYTES as usize);
    for value in &result.actual {
        output_bytes.extend_from_slice(&(*value as f32).to_le_bytes());
    }
    if format!("{:x}", Sha256::digest(output_bytes)) != result.output_sha256 {
        return Err(fixture_protocol_error(
            "model-slice output checksum does not match its bounded float32 readback",
        ));
    }
    validate_model_slice_memory_gauges(&result.memory_gauges)
}

fn validate_model_slice_memory_gauges(memory: &ModelSliceMemoryGauges) -> Result<(), WorkerError> {
    if memory.model_file_bytes != Some(QWEN_FILE_BYTES)
        || memory.mapped_virtual_bytes != 0
        || memory.mapped_resident_bytes != 0
        || memory.owned_compressed_bytes != QWEN_ENCODED_SLICE_BYTES
        || memory.decoded_array_bytes != MODEL_SLICE_DECODED_BYTES
        || memory.activation_array_bytes != MODEL_SLICE_ACTIVATION_BYTES
        || memory.output_bytes != MODEL_SLICE_OUTPUT_BYTES
        || memory.temporary_current_bytes > MODEL_TEMPORARY_CURRENT_CAP
        || memory.temporary_current_bytes > memory.temporary_peak_bytes
        || memory.temporary_peak_bytes > MODEL_TEMPORARY_PEAK_CAP
        || memory.reported_summed_total_bytes.is_some()
    {
        return Err(fixture_protocol_error(
            "model-slice component memory gauges violate the frozen budget",
        ));
    }
    let (Some(mlx_active), Some(mlx_cache), Some(mlx_peak)) = (
        memory.mlx_active_bytes,
        memory.mlx_cache_bytes,
        memory.mlx_peak_bytes,
    ) else {
        return Err(fixture_protocol_error(
            "model-slice evidence omits required MLX allocator gauges",
        ));
    };
    if mlx_active > MODEL_MLX_ACTIVE_CAP
        || mlx_cache > MODEL_MLX_CACHE_CAP
        || mlx_peak > MODEL_MLX_PEAK_CAP
        || mlx_peak < mlx_active
    {
        return Err(fixture_protocol_error(
            "model-slice MLX allocator gauges violate the frozen budget",
        ));
    }
    match (
        memory.process_footprint_bytes,
        memory.process_footprint_source.as_deref(),
    ) {
        (Some(bytes), Some("ps-rss")) if bytes <= MODEL_PHYSICAL_FOOTPRINT_CAP => {}
        (None, None) => {}
        _ => {
            return Err(fixture_protocol_error(
                "model-slice RSS proxy gauge is malformed or exceeds its envelope",
            ));
        }
    }
    let (Some(physical), Some(physical_peak), Some(source)) = (
        memory.process_physical_footprint_bytes,
        memory.process_physical_footprint_peak_bytes,
        memory.process_physical_footprint_source.as_deref(),
    ) else {
        return Err(fixture_protocol_error(
            "model-slice evidence omits mandatory Darwin physical-footprint gauges",
        ));
    };
    if source != "proc_pid_rusage:RUSAGE_INFO_V4"
        || physical == 0
        || physical_peak == 0
        || physical > physical_peak
        || physical_peak > MODEL_PHYSICAL_FOOTPRINT_CAP
    {
        return Err(fixture_protocol_error(
            "model-slice physical-footprint gauges violate the frozen budget",
        ));
    }
    if memory.system_pressure.as_deref() != Some("normal") {
        return Err(fixture_protocol_error(
            "model-slice execution requires normal system memory pressure",
        ));
    }
    Ok(())
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn validate_operation_specific_result(
    result: &TensorFixtureResult,
    max_fixture_elements: u64,
) -> Result<(), WorkerError> {
    match result.operation.as_str() {
        "router_topk_softmax" => {
            let ids = result.selected_expert_ids.as_deref().ok_or_else(|| {
                fixture_protocol_error("router fixture result omits selected expert IDs")
            })?;
            if ids.is_empty() || ids.len() != result.actual.len() {
                return Err(fixture_protocol_error(
                    "router fixture expert-ID cardinality is invalid",
                ));
            }
            if result.decoded.is_some() {
                return Err(fixture_protocol_error(
                    "router fixture result contains an unrelated Q8_0 decode",
                ));
            }
        }
        "q8_0_decode_dot" => {
            let decoded = result.decoded.as_deref().ok_or_else(|| {
                fixture_protocol_error("Q8_0 fixture result omits bounded decoded values")
            })?;
            let decoded_len = u64::try_from(decoded.len()).map_err(|_| {
                fixture_protocol_error("Q8_0 decoded cardinality is not representable")
            })?;
            if decoded.is_empty()
                || decoded_len > max_fixture_elements
                || decoded.iter().any(|value| !value.is_finite())
            {
                return Err(fixture_protocol_error(
                    "Q8_0 fixture decoded readback is invalid or oversized",
                ));
            }
            if result.selected_expert_ids.is_some() {
                return Err(fixture_protocol_error(
                    "Q8_0 fixture result contains unrelated router IDs",
                ));
            }
        }
        _ => {
            if result.selected_expert_ids.is_some() || result.decoded.is_some() {
                return Err(fixture_protocol_error(
                    "fixture result contains operation-inapplicable fields",
                ));
            }
        }
    }
    Ok(())
}

fn validate_fixture_identifier(value: &str, label: &str) -> Result<(), WorkerError> {
    validate_identifier(value, label, WorkerErrorKind::Protocol)?;
    if !value
        .bytes()
        .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.' | b':'))
    {
        return Err(fixture_protocol_error(format!(
            "{label} is not a stable bounded identifier"
        )));
    }
    Ok(())
}

fn validate_fixture_operation(operation: &str) -> Result<(), WorkerError> {
    validate_operation(operation)?;
    if !matches!(
        operation,
        "elementwise_fma"
            | "matmul"
            | "embedding_gather"
            | "rms_norm"
            | "residual_add"
            | "router_topk_softmax"
            | "q8_0_decode_dot"
    ) {
        return Err(fixture_protocol_error(
            "fixture operation is not part of the protocol-v1 manifest",
        ));
    }
    Ok(())
}

fn fixture_protocol_error(message: impl AsRef<str>) -> WorkerError {
    WorkerError::new(WorkerErrorKind::Protocol, message)
}

fn validate_identifier(value: &str, label: &str, kind: WorkerErrorKind) -> Result<(), WorkerError> {
    if value.is_empty()
        || value.trim() != value
        || value.chars().count() > MAX_IDENTIFIER_CHARS
        || value.chars().any(char::is_control)
    {
        return Err(WorkerError::new(
            kind,
            format!("{label} is missing or invalid"),
        ));
    }
    Ok(())
}

fn validate_operation(operation: &str) -> Result<(), WorkerError> {
    validate_identifier(operation, "operation", WorkerErrorKind::Protocol)?;
    if !operation
        .bytes()
        .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'_')
    {
        return Err(WorkerError::new(
            WorkerErrorKind::Protocol,
            "request operation is not a stable protocol identifier",
        ));
    }
    Ok(())
}

fn hello_error(message: impl AsRef<str>) -> WorkerError {
    WorkerError::new(WorkerErrorKind::HelloNegotiation, message)
}

fn stable_worker_error_code(code: &str) -> bool {
    matches!(
        code,
        "protocol_mismatch"
            | "message_too_large"
            | "malformed_request"
            | "unsupported_operation"
            | "invalid_shape"
            | "invalid_dtype"
            | "invalid_layout"
            | "invalid_byte_count"
            | "runtime_version_mismatch"
            | "unsupported_host"
            | "metal_unavailable"
            | "device_unavailable"
            | "evaluation_failed"
            | "comparison_failed"
            | "resource_limit"
            | "internal_worker_error"
    )
}

fn sanitize_message(message: &str) -> String {
    let mut sanitized = String::new();
    for token in message.split_whitespace() {
        if !sanitized.is_empty() {
            sanitized.push(' ');
        }
        if sensitive_token(token) {
            sanitized.push_str("<redacted>");
        } else {
            sanitized.push_str(token);
        }
    }
    if sanitized.is_empty() {
        sanitized.push_str("worker operation failed");
    }

    let mut bounded: String = sanitized.chars().take(MAX_PROTOCOL_MESSAGE_CHARS).collect();
    if sanitized.chars().count() > MAX_PROTOCOL_MESSAGE_CHARS {
        bounded.pop();
        bounded.push('…');
    }
    bounded
}

fn sensitive_token(token: &str) -> bool {
    let uppercase = token.to_ascii_uppercase();
    token.starts_with('/')
        || token.starts_with("~/")
        || token.contains("/Users/")
        || token.contains("/home/")
        || token.contains("\\Users\\")
        || ((uppercase.contains("TOKEN")
            || uppercase.contains("SECRET")
            || uppercase.contains("PASSWORD"))
            && token.contains('='))
}

fn sanitize_json(value: Value) -> Value {
    match value {
        Value::String(value) => Value::String(sanitize_message(&value)),
        Value::Array(values) => Value::Array(values.into_iter().map(sanitize_json).collect()),
        Value::Object(values) => Value::Object(
            values
                .into_iter()
                .map(|(key, value)| {
                    let uppercase = key.to_ascii_uppercase();
                    let value = if uppercase.contains("TOKEN")
                        || uppercase.contains("SECRET")
                        || uppercase.contains("PASSWORD")
                    {
                        Value::String("<redacted>".to_owned())
                    } else {
                        sanitize_json(value)
                    };
                    (key, value)
                })
                .collect(),
        ),
        value => value,
    }
}

struct NoDuplicateValue(Value);

impl<'de> Deserialize<'de> for NoDuplicateValue {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        deserializer.deserialize_any(NoDuplicateVisitor)
    }
}

struct NoDuplicateVisitor;

impl<'de> Visitor<'de> for NoDuplicateVisitor {
    type Value = NoDuplicateValue;

    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("a JSON value without duplicate object keys")
    }

    fn visit_bool<E>(self, value: bool) -> Result<Self::Value, E> {
        Ok(NoDuplicateValue(Value::Bool(value)))
    }

    fn visit_i64<E>(self, value: i64) -> Result<Self::Value, E> {
        Ok(NoDuplicateValue(Value::Number(Number::from(value))))
    }

    fn visit_u64<E>(self, value: u64) -> Result<Self::Value, E> {
        Ok(NoDuplicateValue(Value::Number(Number::from(value))))
    }

    fn visit_f64<E>(self, value: f64) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Number::from_f64(value)
            .map(Value::Number)
            .map(NoDuplicateValue)
            .ok_or_else(|| E::custom("non-finite JSON number"))
    }

    fn visit_str<E>(self, value: &str) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        self.visit_string(value.to_owned())
    }

    fn visit_string<E>(self, value: String) -> Result<Self::Value, E> {
        Ok(NoDuplicateValue(Value::String(value)))
    }

    fn visit_none<E>(self) -> Result<Self::Value, E> {
        Ok(NoDuplicateValue(Value::Null))
    }

    fn visit_unit<E>(self) -> Result<Self::Value, E> {
        Ok(NoDuplicateValue(Value::Null))
    }

    fn visit_some<D>(self, deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: Deserializer<'de>,
    {
        NoDuplicateValue::deserialize(deserializer)
    }

    fn visit_seq<A>(self, mut sequence: A) -> Result<Self::Value, A::Error>
    where
        A: SeqAccess<'de>,
    {
        let mut values = Vec::new();
        while let Some(NoDuplicateValue(value)) = sequence.next_element()? {
            values.push(value);
        }
        Ok(NoDuplicateValue(Value::Array(values)))
    }

    fn visit_map<A>(self, mut map: A) -> Result<Self::Value, A::Error>
    where
        A: MapAccess<'de>,
    {
        let mut values = Map::new();
        while let Some((key, NoDuplicateValue(value))) = map.next_entry::<String, _>()? {
            if values.insert(key, value).is_some() {
                return Err(de::Error::custom("duplicate JSON object key"));
            }
        }
        Ok(NoDuplicateValue(Value::Object(values)))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    const HELLO: &str = r#"{"protocol":1,"op":"hello","worker_version":"fake-worker-v1","python_version":"3.12.0","python_arch":"arm64","mlx_version":"0.32.0","macos_version":"15.0","metal_available":true,"gpu_count":1,"devices":[{"id":"gpu","kind":"gpu"}],"capabilities":{"operations":["health","shutdown"],"dtypes":["float32"]},"limits":{"max_request_bytes":65536,"max_response_bytes":1048576,"max_fixture_elements":1024}}
"#;

    fn expectation() -> HelloExpectation {
        HelloExpectation::new(PROTOCOL_VERSION, "fake-worker-v1", "0.32.0").expect("valid pins")
    }

    fn router_result_value() -> Value {
        let logits = (0..ROUTER_EXPERT_COUNT)
            .map(|expert_id| (((expert_id * 37) % 128) as f32 - 64.0) / 16.0)
            .collect::<Vec<_>>();
        let maximum = logits.iter().copied().reduce(f32::max).expect("nonempty");
        let exponentials = logits
            .iter()
            .map(|value| (*value - maximum).exp())
            .collect::<Vec<_>>();
        let denominator = exponentials.iter().copied().sum::<f32>();
        let probabilities = exponentials
            .iter()
            .map(|value| *value / denominator)
            .collect::<Vec<_>>();
        let mut ids = (0..ROUTER_EXPERT_COUNT).collect::<Vec<_>>();
        ids.sort_by(|left, right| {
            probabilities[*right]
                .total_cmp(&probabilities[*left])
                .then_with(|| left.cmp(right))
        });
        ids.truncate(ROUTER_TOP_K);
        let selected = ids
            .iter()
            .map(|expert_id| probabilities[*expert_id])
            .collect::<Vec<_>>();
        let selected_sum = selected.iter().copied().sum::<f32>();
        let normalized = selected
            .iter()
            .map(|value| *value / selected_sum)
            .collect::<Vec<_>>();

        json!({
            "router_case_id": ROUTER_SINGLE_ROW_CASE_ID,
            "operation": ROUTER_OPERATION,
            "requested_device": "gpu",
            "selected_device": "gpu",
            "fallback_used": false,
            "evaluated": true,
            "synchronized": true,
            "batch_size": 1,
            "hidden_width": ROUTER_HIDDEN_WIDTH,
            "expert_count": ROUTER_EXPERT_COUNT,
            "top_k": ROUTER_TOP_K,
            "output_dtype": "float32",
            "logits": [logits],
            "full_probabilities": [probabilities],
            "selected_expert_ids": [ids],
            "selected_probabilities": [selected],
            "normalized_weights": [normalized],
            "logits_f32le_sha256": canonical_f32le_sha256(&logits).expect("hash"),
            "full_probabilities_f32le_sha256": canonical_f32le_sha256(&probabilities).expect("hash"),
            "selected_probabilities_f32le_sha256": canonical_f32le_sha256(&selected).expect("hash"),
            "normalized_weights_f32le_sha256": canonical_f32le_sha256(&normalized).expect("hash"),
            "memory_gauges": {
                "mlx_active_bytes": null,
                "mlx_cache_bytes": null,
                "mlx_peak_bytes": null,
                "process_footprint_bytes": null,
                "process_footprint_source": null,
                "system_pressure": "normal",
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
                        "duration_ns": 1_337
                    }
                }
            },
            "passed": true
        })
    }

    #[test]
    fn hello_negotiates_exact_pins_capabilities_and_limits() {
        let local_limits = ProtocolLimits::default();
        let hello =
            parse_hello_line(HELLO.as_bytes(), &expectation(), &local_limits).expect("valid hello");

        assert_eq!(hello.protocol(), PROTOCOL_VERSION);
        assert_eq!(hello.request_id(), None);
        assert_eq!(hello.worker_version(), "fake-worker-v1");
        assert_eq!(hello.capabilities().operations(), ["health", "shutdown"]);
        assert_eq!(hello.devices()[0].id(), "gpu");

        let effective = local_limits
            .negotiated(hello.limits())
            .expect("advertised limits are bounded");
        assert_eq!(effective.max_request_bytes(), MAX_REQUEST_BYTES);
        assert_eq!(effective.max_response_bytes(), MAX_RESPONSE_BYTES);
    }

    #[test]
    fn hello_rejects_mismatched_pins_and_duplicate_json_keys() {
        let limits = ProtocolLimits::default();
        let wrong = HelloExpectation::new(PROTOCOL_VERSION, "fake-worker-v2", "0.32.0")
            .expect("valid alternate pin");
        assert_eq!(
            parse_hello_line(HELLO.as_bytes(), &wrong, &limits)
                .expect_err("mismatched pin")
                .kind(),
            WorkerErrorKind::HelloNegotiation
        );

        let duplicate = b"{\"protocol\":1,\"protocol\":1}\n";
        assert_eq!(
            parse_hello_line(duplicate, &expectation(), &limits)
                .expect_err("duplicate key")
                .kind(),
            WorkerErrorKind::StdoutContamination
        );
    }

    #[test]
    fn request_encoding_is_one_bounded_protocol_line() {
        let request = RequestEnvelope::empty(7, "health").expect("valid request");
        let encoded = request
            .encode_line(&ProtocolLimits::default())
            .expect("bounded request");
        assert_eq!(
            encoded,
            b"{\"protocol\":1,\"request_id\":7,\"op\":\"health\",\"params\":{}}\n"
        );
    }

    #[test]
    fn response_ids_and_structured_remote_errors_are_enforced() {
        let limits = ProtocolLimits::default();
        let success =
            b"{\"protocol\":1,\"request_id\":7,\"ok\":true,\"result\":{\"ready\":true}}\n";
        assert_eq!(
            parse_response_line(success, 8, &limits)
                .expect_err("mismatched ID")
                .kind(),
            WorkerErrorKind::RequestIdMismatch
        );

        let remote = b"{\"protocol\":1,\"request_id\":7,\"ok\":false,\"error\":{\"code\":\"device_unavailable\",\"message\":\"failed at /Users/private/model.gguf TOKEN=value\",\"retryable\":false,\"details\":{\"path\":\"/private/model.gguf\"}}}\n";
        let error = parse_response_line(remote, 7, &limits)
            .expect("valid remote envelope")
            .into_result()
            .expect_err("remote failure stays an error");
        assert_eq!(error.kind(), WorkerErrorKind::Remote);
        assert_eq!(error.worker_code(), Some("device_unavailable"));
        assert_eq!(error.message(), "failed at <redacted> <redacted>");
        assert_eq!(error.retryable(), Some(false));
        assert!(!error
            .details()
            .expect("sanitized details")
            .to_string()
            .contains("/private"));
    }

    #[test]
    fn response_framing_and_line_limits_are_strict() {
        let limits = ProtocolLimits::default();
        assert_eq!(
            parse_response_line(b"{}", 1, &limits)
                .expect_err("missing LF")
                .kind(),
            WorkerErrorKind::StdoutContamination
        );

        let mut oversized = vec![b' '; MAX_RESPONSE_BYTES + 1];
        oversized.push(b'\n');
        assert_eq!(
            parse_response_line(&oversized, 1, &limits)
                .expect_err("oversized line")
                .kind(),
            WorkerErrorKind::MessageTooLarge
        );
    }

    #[test]
    fn router_request_is_control_only_and_complete_result_is_validated() {
        let request = RouterRequest::new(ROUTER_SINGLE_ROW_CASE_ID, "gpu")
            .expect("registered router request");
        let params = request.protocol_params();
        assert_eq!(
            params.keys().map(String::as_str).collect::<BTreeSet<_>>(),
            BTreeSet::from(["allow_fallback", "device", "router_case_id"])
        );
        assert_eq!(params.get("allow_fallback"), Some(&Value::Bool(false)));

        let result = parse_router_result(router_result_value(), &request)
            .expect("complete bounded router response");
        assert_eq!(result.logits().len(), 1);
        assert_eq!(result.logits()[0].len(), ROUTER_EXPERT_COUNT);
        assert_eq!(result.selected_expert_ids()[0].len(), ROUTER_TOP_K);
        let timing = result.timing();
        assert_eq!(timing.monotonic_clock(), "perf_counter_ns");
        assert_eq!(
            timing.instrumentation_mode(),
            RouterInstrumentationMode::MinimallyInstrumented
        );
        assert!(timing.evaluated());
        assert!(timing.synchronized());
        assert_eq!(timing.stages().len(), 2);
        let dequantization = timing
            .stage("dequantization")
            .expect("dequantization stage");
        assert_eq!(
            dequantization.status(),
            RouterTimingStageStatus::NotApplicable
        );
        assert_eq!(
            dequantization.reason(),
            Some("f32_router_requires_no_dequantization")
        );
        assert_eq!(dequantization.duration_ns(), None);
        let total = timing
            .stage("total_evaluated_router")
            .expect("evaluated total stage");
        assert_eq!(total.status(), RouterTimingStageStatus::Observed);
        assert_eq!(total.duration_ns(), Some(1_337));
        assert_eq!(total.reason(), None);
        assert!(result.passed());

        let mut incomplete = router_result_value();
        incomplete["logits"] = json!([[0.0]]);
        assert_eq!(
            parse_router_result(incomplete, &request)
                .expect_err("incomplete response")
                .kind(),
            WorkerErrorKind::Protocol
        );

        let mut unrelated_probabilities = router_result_value();
        let uniform = vec![1.0_f32 / ROUTER_EXPERT_COUNT as f32; ROUTER_EXPERT_COUNT];
        let ids = (0..ROUTER_TOP_K).collect::<Vec<_>>();
        let selected = vec![1.0_f32 / ROUTER_EXPERT_COUNT as f32; ROUTER_TOP_K];
        let normalized = vec![1.0_f32 / ROUTER_TOP_K as f32; ROUTER_TOP_K];
        let uniform_hash = canonical_f32le_sha256(&uniform).expect("uniform hash");
        let selected_hash = canonical_f32le_sha256(&selected).expect("selected hash");
        let normalized_hash = canonical_f32le_sha256(&normalized).expect("normalized hash");
        unrelated_probabilities["full_probabilities"] = json!([uniform]);
        unrelated_probabilities["selected_expert_ids"] = json!([ids]);
        unrelated_probabilities["selected_probabilities"] = json!([selected]);
        unrelated_probabilities["normalized_weights"] = json!([normalized]);
        unrelated_probabilities["full_probabilities_f32le_sha256"] = json!(uniform_hash);
        unrelated_probabilities["selected_probabilities_f32le_sha256"] = json!(selected_hash);
        unrelated_probabilities["normalized_weights_f32le_sha256"] = json!(normalized_hash);
        assert_eq!(
            parse_router_result(unrelated_probabilities, &request)
                .expect_err("self-consistent probabilities unrelated to logits must fail")
                .kind(),
            WorkerErrorKind::Protocol
        );

        let mut noncanonical_wire_value = router_result_value();
        noncanonical_wire_value["logits"][0][0] = json!(0.1_f64);
        assert_eq!(
            parse_router_result(noncanonical_wire_value, &request)
                .expect_err("higher-precision wire value must fail")
                .kind(),
            WorkerErrorKind::Protocol
        );
        assert!(RouterRequest::new("unregistered-router", "gpu").is_err());
        assert!(RouterRequest::new(ROUTER_SINGLE_ROW_CASE_ID, "cpu").is_err());
    }

    #[test]
    fn router_timing_envelope_is_closed_positive_and_semantically_coherent() {
        let request = RouterRequest::new(ROUTER_SINGLE_ROW_CASE_ID, "gpu")
            .expect("registered router request");

        let mut missing = router_result_value();
        missing
            .as_object_mut()
            .expect("router result object")
            .remove("timing");

        let mut wrong_clock = router_result_value();
        wrong_clock["timing"]["monotonic_clock"] = json!("system_time_ns");

        let mut unknown_field = router_result_value();
        unknown_field["timing"]["unreviewed"] = json!(true);

        let mut mismatched_barrier = router_result_value();
        mismatched_barrier["timing"]["synchronized"] = json!(false);

        let mut wrong_mode = router_result_value();
        wrong_mode["timing"]["instrumentation_mode"] = json!("stage_instrumented");

        let mut zero_total = router_result_value();
        zero_total["timing"]["stages"]["total_evaluated_router"]["duration_ns"] = json!(0);

        let mut contradictory_total = router_result_value();
        contradictory_total["timing"]["stages"]["total_evaluated_router"]["reason"] =
            json!("an observed stage cannot have a reason");

        let mut null_observed_reason = router_result_value();
        null_observed_reason["timing"]["stages"]["total_evaluated_router"]["reason"] = Value::Null;

        let mut wrong_dequantization = router_result_value();
        wrong_dequantization["timing"]["stages"]["dequantization"]["reason"] =
            json!("dequantization was skipped");

        let mut null_unavailable_duration = router_result_value();
        null_unavailable_duration["timing"]["stages"]["file_io"] = json!({
            "status": "unavailable",
            "duration_ns": null,
            "reason": "the phase was outside this operation"
        });

        let mut extra_stage = router_result_value();
        extra_stage["timing"]["stages"]["file_io"] = json!({
            "status": "unavailable",
            "reason": "the phase was outside this operation"
        });

        for (label, value) in [
            ("missing timing", missing),
            ("wrong clock", wrong_clock),
            ("unknown timing field", unknown_field),
            ("mismatched barrier", mismatched_barrier),
            ("unrequested timing mode", wrong_mode),
            ("zero total", zero_total),
            ("contradictory total", contradictory_total),
            ("null observed reason", null_observed_reason),
            ("wrong F32 dequantization", wrong_dequantization),
            ("null unavailable duration", null_unavailable_duration),
            ("extra minimal stage", extra_stage),
        ] {
            assert_eq!(
                parse_router_result(value, &request)
                    .expect_err(label)
                    .kind(),
                WorkerErrorKind::Protocol,
                "{label} must fail closed"
            );
        }

        let unavailable: RouterTimingStage = serde_json::from_value(json!({
            "status": "unavailable",
            "reason": "the phase is outside this operation"
        }))
        .expect("missing duration is valid for an unavailable stage");
        assert_eq!(unavailable.status(), RouterTimingStageStatus::Unavailable);
        assert_eq!(
            unavailable.reason(),
            Some("the phase is outside this operation")
        );
        assert_eq!(unavailable.duration_ns(), None);

        for (label, stage) in [
            (
                "null unavailable duration",
                json!({
                    "status": "unavailable",
                    "duration_ns": null,
                    "reason": "the phase is outside this operation"
                }),
            ),
            (
                "unknown stage field",
                json!({
                    "status": "observed",
                    "duration_ns": 1,
                    "unreviewed": true
                }),
            ),
            ("unknown stage status", json!({"status": "estimated"})),
            ("missing stage status", json!({"duration_ns": 1})),
        ] {
            assert!(
                serde_json::from_value::<RouterTimingStage>(stage).is_err(),
                "{label} must fail the timing-stage union directly"
            );
        }
    }
}
