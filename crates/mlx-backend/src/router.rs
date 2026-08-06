//! Bounded, model-neutral contracts for the Feature 002 router boundary.
//!
//! This module admits an already-observed complete F32 router range and
//! validates bounded output/evidence values.  It does not discover, acquire,
//! or execute an external checkpoint.

use backend::{ContractError, ErrorCategory};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::File;
use std::io::{self, ErrorKind};
use std::mem::size_of;
#[cfg(unix)]
use std::os::unix::fs::FileExt;

pub const ROUTER_CONTRACT_ID: &str = "qwen3moe-layer0-router-parity-v1";
pub const ROUTER_TENSOR_NAME: &str = "blk.0.ffn_gate_inp.weight";
pub const ROUTER_HIDDEN_WIDTH: usize = 2_048;
pub const ROUTER_EXPERT_COUNT: usize = 128;
pub const ROUTER_TOP_K: usize = 8;
pub const ROUTER_TENSOR_ELEMENTS: u64 = 262_144;
pub const ROUTER_TENSOR_BYTES: u64 = 1_048_576;
pub const ROUTER_MAX_ROWS: usize = 2;

const ROUTER_SEMANTIC_ROLE: &str = "layer_0_router_projection";
const ROUTER_GGUF_TYPE: &str = "F32";
const ROUTER_QUANTIZATION: &str = "none_f32";
const ROUTER_BYTE_ORDER: &str = "little";
const ROUTER_ORIENTATION: &str = "expert_major_rows_input_columns";
const WEIGHT_SUM_TOLERANCE: f64 = 1.0e-6;
const PROBABILITY_ABSOLUTE_TOLERANCE: f64 = 1.0e-6;
const PROBABILITY_RELATIVE_TOLERANCE: f64 = 1.0e-6;
const MAX_CASE_ID_CHARS: usize = 128;
const MAX_TIMING_REASON_CHARS: usize = 512;
const MAX_TIMING_OBSERVATIONS: usize = 1_024;
const MAX_TIMING_SERIES_BYTES: usize = 1_024 * 1_024;
const ROUTER_TIMING_CLOCK: &str = "perf_counter_ns";
const ROUTER_F32_DEQUANTIZATION_REASON: &str = "f32_router_requires_no_dequantization";
const ROUTER_STAGE_DIAGNOSTIC_KEYS: [&str; 13] = [
    "setup_admission",
    "file_io",
    "storage_validation_f32_decode",
    "dequantization",
    "host_to_device",
    "graph_construction",
    "compilation",
    "router_projection",
    "top_k",
    "normalization",
    "total_evaluated_router",
    "synchronized_readback",
    "end_to_end_router_command",
];
const ROUTER_COSTLY_EXTERNAL_KEYS: [&str; 6] = [
    "file_io",
    "storage_validation_f32_decode",
    "dequantization",
    "host_to_device",
    "total_evaluated_router",
    "end_to_end_router_command",
];

pub const ROUTER_MAJOR_SINGLE_ROW_BENCHMARK_ID: &str = "f002-major-single-row-minimal-v1";
pub const ROUTER_MAJOR_TWO_ROW_BENCHMARK_ID: &str = "f002-major-two-row-minimal-v1";
pub const ROUTER_REAL_SINGLE_ROW_CASE_ID: &str = "qwen3moe-layer0-router-token0-row0-v1";
pub const ROUTER_REAL_TWO_ROW_CASE_ID: &str = "qwen3moe-layer0-router-token0-token1-batch-v1";
pub const ROUTER_GENERATED_SINGLE_ROW_CASE_ID: &str = "generated-qwen3moe-router-single-row-v1";
pub const ROUTER_GENERATED_TWO_ROW_CASE_ID: &str = "generated-qwen3moe-router-two-row-v1";

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub enum RouterTimingSeriesKind {
    MajorMinimallyInstrumented,
    InexpensiveSynthetic,
    CostlyReal,
    FirstProcessCostly,
    StageDiagnostic,
}

impl RouterTimingSeriesKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::MajorMinimallyInstrumented => "major_minimally_instrumented",
            Self::InexpensiveSynthetic => "inexpensive_synthetic",
            Self::CostlyReal => "costly_real",
            Self::FirstProcessCostly => "first_process_costly",
            Self::StageDiagnostic => "stage_diagnostic",
        }
    }
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub enum RouterTimingReplicationRole {
    Primary,
    CleanProcessReplication,
}

impl RouterTimingReplicationRole {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Primary => "primary",
            Self::CleanProcessReplication => "clean_process_replication",
        }
    }
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub enum RouterTimingProcessState {
    FreshProcess,
    ReusedProcess,
}

impl RouterTimingProcessState {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::FreshProcess => "fresh_process",
            Self::ReusedProcess => "reused_process",
        }
    }
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub enum RouterTimingCondition {
    Warm,
    FirstReadNewProcessOsCacheUncontrolled,
    ControlledCold,
}

impl RouterTimingCondition {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Warm => "warm",
            Self::FirstReadNewProcessOsCacheUncontrolled => {
                "first_read_new_process_os_cache_uncontrolled"
            }
            Self::ControlledCold => "controlled_cold",
        }
    }
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub enum RouterTimingInstrumentationMode {
    MinimallyInstrumented,
    StageInstrumented,
}

impl RouterTimingInstrumentationMode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::MinimallyInstrumented => "minimally_instrumented",
            Self::StageInstrumented => "stage_instrumented",
        }
    }
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RouterTimingObservationKind {
    Warmup,
    Measurement,
    CleanProcessReplication,
}

impl RouterTimingObservationKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Warmup => "warmup",
            Self::Measurement => "measurement",
            Self::CleanProcessReplication => "clean_process_replication",
        }
    }
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RouterTimingObservationStatus {
    Passed,
    Failed,
    Aborted,
    Excluded,
}

impl RouterTimingObservationStatus {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Passed => "passed",
            Self::Failed => "failed",
            Self::Aborted => "aborted",
            Self::Excluded => "excluded",
        }
    }
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(tag = "status", rename_all = "snake_case")]
pub enum RouterTimingStageObservation {
    Observed { duration_ns: u64 },
    Unavailable { reason: String },
    NotApplicable { reason: String },
}

impl RouterTimingStageObservation {
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

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct RouterTimingFailure {
    code: String,
    message: String,
    stage: String,
}

impl RouterTimingFailure {
    pub fn code(&self) -> &str {
        &self.code
    }

    pub fn message(&self) -> &str {
        &self.message
    }

    pub fn stage(&self) -> &str {
        &self.stage
    }
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct RouterTimingObservation {
    observation_id: String,
    run_index: usize,
    observation_kind: RouterTimingObservationKind,
    process_replication_id: String,
    process_state: RouterTimingProcessState,
    condition: RouterTimingCondition,
    instrumentation_mode: RouterTimingInstrumentationMode,
    monotonic_clock: String,
    stages: BTreeMap<String, RouterTimingStageObservation>,
    status: RouterTimingObservationStatus,
    requested_device: String,
    selected_device: String,
    fallback_used: bool,
    evaluated: bool,
    synchronized: bool,
    output_sha256: Option<String>,
    correctness_passed: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    failure: Option<RouterTimingFailure>,
}

impl RouterTimingObservation {
    pub fn observation_id(&self) -> &str {
        &self.observation_id
    }

    pub fn run_index(&self) -> usize {
        self.run_index
    }

    pub const fn observation_kind(&self) -> RouterTimingObservationKind {
        self.observation_kind
    }

    pub fn process_replication_id(&self) -> &str {
        &self.process_replication_id
    }

    pub const fn process_state(&self) -> RouterTimingProcessState {
        self.process_state
    }

    pub const fn condition(&self) -> RouterTimingCondition {
        self.condition
    }

    pub const fn instrumentation_mode(&self) -> RouterTimingInstrumentationMode {
        self.instrumentation_mode
    }

    pub fn monotonic_clock(&self) -> &str {
        &self.monotonic_clock
    }

    pub fn stages(&self) -> &BTreeMap<String, RouterTimingStageObservation> {
        &self.stages
    }

    pub const fn status(&self) -> RouterTimingObservationStatus {
        self.status
    }

    pub fn requested_device(&self) -> &str {
        &self.requested_device
    }

    pub fn selected_device(&self) -> &str {
        &self.selected_device
    }

    pub const fn fallback_used(&self) -> bool {
        self.fallback_used
    }

    pub const fn evaluated(&self) -> bool {
        self.evaluated
    }

    pub const fn synchronized(&self) -> bool {
        self.synchronized
    }

    pub fn output_sha256(&self) -> Option<&str> {
        self.output_sha256.as_deref()
    }

    pub fn correctness_passed(&self) -> Option<bool> {
        self.correctness_passed
    }

    pub fn failure(&self) -> Option<&RouterTimingFailure> {
        self.failure.as_ref()
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RouterTimingSeries {
    benchmark_id: String,
    case_id: String,
    row_count: usize,
    series_kind: RouterTimingSeriesKind,
    replication_role: RouterTimingReplicationRole,
    process_replication_id: String,
    process_state: RouterTimingProcessState,
    condition: RouterTimingCondition,
    instrumentation_mode: RouterTimingInstrumentationMode,
    warmup_count: usize,
    measurement_count: usize,
    raw_timing_observations: Vec<RouterTimingObservation>,
}

impl RouterTimingSeries {
    pub fn try_from_value(value: Value) -> Result<Self, ContractError> {
        let encoded_len = serde_json::to_vec(&value)
            .map_err(|_| invalid_timing_evidence("router timing series could not be encoded"))?
            .len();
        if encoded_len > MAX_TIMING_SERIES_BYTES {
            return Err(invalid_timing_evidence(
                "router timing series exceeds the bounded response size",
            ));
        }
        let raw: RawRouterTimingSeries = serde_json::from_value(value).map_err(|_| {
            invalid_timing_evidence("router timing series does not match its closed schema")
        })?;
        Self::try_from_raw(raw)
    }

    pub fn benchmark_id(&self) -> &str {
        &self.benchmark_id
    }

    pub fn case_id(&self) -> &str {
        &self.case_id
    }

    pub fn row_count(&self) -> usize {
        self.row_count
    }

    pub const fn series_kind(&self) -> RouterTimingSeriesKind {
        self.series_kind
    }

    pub const fn replication_role(&self) -> RouterTimingReplicationRole {
        self.replication_role
    }

    pub fn process_replication_id(&self) -> &str {
        &self.process_replication_id
    }

    pub const fn process_state(&self) -> RouterTimingProcessState {
        self.process_state
    }

    pub const fn condition(&self) -> RouterTimingCondition {
        self.condition
    }

    pub const fn instrumentation_mode(&self) -> RouterTimingInstrumentationMode {
        self.instrumentation_mode
    }

    pub fn warmup_count(&self) -> usize {
        self.warmup_count
    }

    pub fn measurement_count(&self) -> usize {
        self.measurement_count
    }

    pub fn raw_timing_observations(&self) -> &[RouterTimingObservation] {
        &self.raw_timing_observations
    }

    pub fn try_to_value(&self) -> Result<Value, ContractError> {
        let encoded = serde_json::to_vec(&SerializableRouterTimingSeries::from(self))
            .map_err(|_| invalid_timing_evidence("router timing series could not be serialized"))?;
        if encoded.len() > MAX_TIMING_SERIES_BYTES {
            return Err(invalid_timing_evidence(
                "router timing series exceeds the bounded response size",
            ));
        }
        serde_json::from_slice(&encoded)
            .map_err(|_| invalid_timing_evidence("router timing series could not be serialized"))
    }

    pub fn successful_warmup_count(&self) -> usize {
        self.successful_count(RouterTimingObservationKind::Warmup)
    }

    pub fn successful_measurement_count(&self) -> usize {
        self.successful_count(RouterTimingObservationKind::Measurement)
    }

    pub fn has_complete_success_samples(&self) -> bool {
        self.successful_warmup_count() == self.warmup_count
            && self.successful_measurement_count() == self.measurement_count
    }

    pub fn passing_output_sha256(&self) -> Option<&str> {
        self.raw_timing_observations
            .iter()
            .find(|observation| observation.status == RouterTimingObservationStatus::Passed)
            .and_then(RouterTimingObservation::output_sha256)
    }

    fn try_from_raw(mut raw: RawRouterTimingSeries) -> Result<Self, ContractError> {
        validate_timing_series_identity(&raw)?;
        validate_timing_series_policy(&raw)?;
        let required_successes = raw
            .warmup_count
            .checked_add(raw.measurement_count)
            .ok_or_else(|| invalid_timing_evidence("router timing sample count overflows"))?;
        if required_successes == 0
            || required_successes > MAX_TIMING_OBSERVATIONS
            || raw.raw_timing_observations.is_empty()
            || raw.raw_timing_observations.len() > MAX_TIMING_OBSERVATIONS
        {
            return Err(invalid_timing_evidence(
                "router timing observations violate the frozen response bounds",
            ));
        }

        let mut observations = Vec::with_capacity(raw.raw_timing_observations.len());
        let mut observation_ids = BTreeSet::new();
        let mut passed_hash = None::<String>;
        let mut next_warmup_index = 0_usize;
        let mut next_measurement_index = 0_usize;
        let mut successful_warmups = 0_usize;
        let mut successful_measurements = 0_usize;
        let mut retained_unsuccessful = false;
        let mut measurements_started = false;
        let raw_observations = std::mem::take(&mut raw.raw_timing_observations);
        for raw_observation in raw_observations {
            let (expected_kind, expected_index) = match raw_observation.observation_kind {
                RouterTimingObservationKind::Warmup if !measurements_started => {
                    let index = next_warmup_index;
                    next_warmup_index += 1;
                    (RouterTimingObservationKind::Warmup, index)
                }
                RouterTimingObservationKind::Measurement => {
                    measurements_started = true;
                    let index = next_measurement_index;
                    next_measurement_index += 1;
                    (RouterTimingObservationKind::Measurement, index)
                }
                _ => {
                    return Err(invalid_timing_evidence(
                        "router timing observations violate their frozen kind order",
                    ));
                }
            };
            let observation =
                validate_timing_observation(raw_observation, expected_kind, expected_index, &raw)?;
            if !observation_ids.insert(observation.observation_id.clone()) {
                return Err(invalid_timing_evidence(
                    "router timing observation identity is duplicated",
                ));
            }
            if observation.status == RouterTimingObservationStatus::Passed {
                match observation.observation_kind {
                    RouterTimingObservationKind::Warmup => successful_warmups += 1,
                    RouterTimingObservationKind::Measurement => successful_measurements += 1,
                    RouterTimingObservationKind::CleanProcessReplication => unreachable!(
                        "the closed kind-order validation rejects replication observations"
                    ),
                }
                match (&passed_hash, &observation.output_sha256) {
                    (None, Some(hash)) => passed_hash = Some(hash.clone()),
                    (Some(expected), Some(actual)) if expected == actual => {}
                    _ => {
                        return Err(invalid_timing_evidence(
                            "passing router timing output hashes are inconsistent",
                        ));
                    }
                }
            } else {
                retained_unsuccessful = true;
            }
            observations.push(observation);
        }

        if successful_warmups > raw.warmup_count
            || successful_measurements > raw.measurement_count
            || (!retained_unsuccessful
                && (successful_warmups != raw.warmup_count
                    || successful_measurements != raw.measurement_count))
        {
            return Err(invalid_timing_evidence(
                "router timing successful samples do not match the frozen policy",
            ));
        }

        Ok(Self {
            benchmark_id: raw.benchmark_id,
            case_id: raw.case_id,
            row_count: raw.row_count,
            series_kind: raw.series_kind,
            replication_role: raw.replication_role,
            process_replication_id: raw.process_replication_id,
            process_state: raw.process_state,
            condition: raw.condition,
            instrumentation_mode: raw.instrumentation_mode,
            warmup_count: raw.warmup_count,
            measurement_count: raw.measurement_count,
            raw_timing_observations: observations,
        })
    }

    fn successful_count(&self, kind: RouterTimingObservationKind) -> usize {
        self.raw_timing_observations
            .iter()
            .filter(|observation| {
                observation.observation_kind == kind
                    && observation.status == RouterTimingObservationStatus::Passed
            })
            .count()
    }
}

#[derive(Serialize)]
struct SerializableRouterTimingSeries<'a> {
    benchmark_id: &'a str,
    case_id: &'a str,
    row_count: usize,
    series_kind: RouterTimingSeriesKind,
    replication_role: RouterTimingReplicationRole,
    process_replication_id: &'a str,
    process_state: RouterTimingProcessState,
    condition: RouterTimingCondition,
    instrumentation_mode: RouterTimingInstrumentationMode,
    warmup_count: usize,
    measurement_count: usize,
    raw_timing_observations: &'a [RouterTimingObservation],
}

impl<'a> From<&'a RouterTimingSeries> for SerializableRouterTimingSeries<'a> {
    fn from(series: &'a RouterTimingSeries) -> Self {
        Self {
            benchmark_id: &series.benchmark_id,
            case_id: &series.case_id,
            row_count: series.row_count,
            series_kind: series.series_kind,
            replication_role: series.replication_role,
            process_replication_id: &series.process_replication_id,
            process_state: series.process_state,
            condition: series.condition,
            instrumentation_mode: series.instrumentation_mode,
            warmup_count: series.warmup_count,
            measurement_count: series.measurement_count,
            raw_timing_observations: &series.raw_timing_observations,
        }
    }
}

pub fn validate_major_router_timing_series(
    series: &[RouterTimingSeries],
) -> Result<(), ContractError> {
    if series.len() != 4 {
        return Err(invalid_timing_evidence(
            "the exact two major benchmarks and clean replications are incomplete",
        ));
    }

    let required = BTreeSet::from([
        (
            ROUTER_MAJOR_SINGLE_ROW_BENCHMARK_ID,
            RouterTimingReplicationRole::Primary,
        ),
        (
            ROUTER_MAJOR_TWO_ROW_BENCHMARK_ID,
            RouterTimingReplicationRole::Primary,
        ),
        (
            ROUTER_MAJOR_SINGLE_ROW_BENCHMARK_ID,
            RouterTimingReplicationRole::CleanProcessReplication,
        ),
        (
            ROUTER_MAJOR_TWO_ROW_BENCHMARK_ID,
            RouterTimingReplicationRole::CleanProcessReplication,
        ),
    ]);
    let mut actual = BTreeSet::new();
    let mut observation_ids = BTreeSet::new();
    for item in series {
        if item.series_kind != RouterTimingSeriesKind::MajorMinimallyInstrumented
            || !actual.insert((item.benchmark_id.as_str(), item.replication_role))
        {
            return Err(invalid_timing_evidence(
                "major router timing series are duplicated or mislabeled",
            ));
        }
        if item
            .raw_timing_observations
            .iter()
            .any(|observation| observation.status != RouterTimingObservationStatus::Passed)
            || !item.has_complete_success_samples()
        {
            return Err(invalid_timing_evidence(
                "major router timing series contains an unsuccessful attempt",
            ));
        }
        for observation in &item.raw_timing_observations {
            if !observation_ids.insert(observation.observation_id.as_str()) {
                return Err(invalid_timing_evidence(
                    "major router observation identity is duplicated across series",
                ));
            }
        }
    }
    if actual != required {
        return Err(invalid_timing_evidence(
            "the exact two major benchmarks and clean replications are incomplete",
        ));
    }

    let primary_process_ids = series
        .iter()
        .filter(|item| item.replication_role == RouterTimingReplicationRole::Primary)
        .map(|item| item.process_replication_id.as_str())
        .collect::<BTreeSet<_>>();
    let mut clean_process_ids = BTreeSet::new();
    for replica in series.iter().filter(|item| {
        item.replication_role == RouterTimingReplicationRole::CleanProcessReplication
    }) {
        if primary_process_ids.contains(replica.process_replication_id.as_str())
            || !clean_process_ids.insert(replica.process_replication_id.as_str())
        {
            return Err(invalid_timing_evidence(
                "major router clean-process identity is not independent",
            ));
        }
    }

    for benchmark_id in [
        ROUTER_MAJOR_SINGLE_ROW_BENCHMARK_ID,
        ROUTER_MAJOR_TWO_ROW_BENCHMARK_ID,
    ] {
        let primary = series.iter().find(|item| {
            item.benchmark_id == benchmark_id
                && item.replication_role == RouterTimingReplicationRole::Primary
        });
        let replica = series.iter().find(|item| {
            item.benchmark_id == benchmark_id
                && item.replication_role == RouterTimingReplicationRole::CleanProcessReplication
        });
        let Some(primary_hash) = primary.and_then(RouterTimingSeries::passing_output_sha256) else {
            return Err(invalid_timing_evidence(
                "major router primary series lacks a passing output identity",
            ));
        };
        let Some(replica_hash) = replica.and_then(RouterTimingSeries::passing_output_sha256) else {
            return Err(invalid_timing_evidence(
                "major router clean-process series lacks a passing output identity",
            ));
        };
        if primary_hash != replica_hash {
            return Err(invalid_timing_evidence(
                "major router clean-process output identity differs from its primary series",
            ));
        }
    }
    Ok(())
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RawRouterTimingSeries {
    benchmark_id: String,
    case_id: String,
    row_count: usize,
    series_kind: RouterTimingSeriesKind,
    replication_role: RouterTimingReplicationRole,
    process_replication_id: String,
    process_state: RouterTimingProcessState,
    condition: RouterTimingCondition,
    instrumentation_mode: RouterTimingInstrumentationMode,
    warmup_count: usize,
    measurement_count: usize,
    raw_timing_observations: Vec<RawRouterTimingObservation>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RawRouterTimingObservation {
    observation_id: String,
    run_index: usize,
    observation_kind: RouterTimingObservationKind,
    process_replication_id: String,
    process_state: RouterTimingProcessState,
    condition: RouterTimingCondition,
    instrumentation_mode: RouterTimingInstrumentationMode,
    monotonic_clock: String,
    stages: BTreeMap<String, RawRouterTimingStage>,
    status: RouterTimingObservationStatus,
    requested_device: String,
    selected_device: String,
    fallback_used: bool,
    evaluated: bool,
    synchronized: bool,
    output_sha256: Value,
    correctness_passed: Value,
    #[serde(default)]
    failure: PresentTimingField<RawRouterTimingFailure>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RawRouterTimingFailure {
    code: String,
    message: String,
    stage: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RawRouterTimingStage {
    status: String,
    #[serde(default)]
    duration_ns: PresentTimingField<u64>,
    #[serde(default)]
    reason: PresentTimingField<String>,
}

#[derive(Default)]
enum PresentTimingField<T> {
    #[default]
    Missing,
    Present(T),
}

impl<'de, T> Deserialize<'de> for PresentTimingField<T>
where
    T: Deserialize<'de>,
{
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        T::deserialize(deserializer).map(Self::Present)
    }
}

fn validate_timing_series_identity(raw: &RawRouterTimingSeries) -> Result<(), ContractError> {
    for value in [
        raw.benchmark_id.as_str(),
        raw.case_id.as_str(),
        raw.process_replication_id.as_str(),
    ] {
        if !is_timing_identifier(value) {
            return Err(invalid_timing_evidence(
                "router timing series identity is invalid",
            ));
        }
    }
    let (expected_rows, generated_case) = match raw.case_id.as_str() {
        ROUTER_REAL_SINGLE_ROW_CASE_ID => (1, false),
        ROUTER_REAL_TWO_ROW_CASE_ID => (2, false),
        ROUTER_GENERATED_SINGLE_ROW_CASE_ID => (1, true),
        ROUTER_GENERATED_TWO_ROW_CASE_ID => (2, true),
        _ => {
            return Err(invalid_timing_evidence(
                "router timing case is outside the frozen real-router scope",
            ));
        }
    };
    if raw.row_count != expected_rows {
        return Err(invalid_timing_evidence(
            "router timing row count contradicts its case identity",
        ));
    }
    if generated_case != (raw.series_kind == RouterTimingSeriesKind::InexpensiveSynthetic) {
        return Err(invalid_timing_evidence(
            "router timing series kind contradicts its fixture provenance",
        ));
    }
    if raw.series_kind == RouterTimingSeriesKind::MajorMinimallyInstrumented {
        let expected_benchmark = if expected_rows == 1 {
            ROUTER_MAJOR_SINGLE_ROW_BENCHMARK_ID
        } else {
            ROUTER_MAJOR_TWO_ROW_BENCHMARK_ID
        };
        if raw.benchmark_id != expected_benchmark {
            return Err(invalid_timing_evidence(
                "major router timing benchmark identity is invalid",
            ));
        }
    }
    Ok(())
}

fn validate_timing_series_policy(raw: &RawRouterTimingSeries) -> Result<(), ContractError> {
    let expected_counts = match raw.series_kind {
        RouterTimingSeriesKind::MajorMinimallyInstrumented
        | RouterTimingSeriesKind::InexpensiveSynthetic => (5, 30),
        RouterTimingSeriesKind::CostlyReal | RouterTimingSeriesKind::StageDiagnostic => (5, 10),
        RouterTimingSeriesKind::FirstProcessCostly => (0, 1),
    };
    if (raw.warmup_count, raw.measurement_count) != expected_counts {
        return Err(invalid_timing_evidence(
            "router timing series overrides its frozen sample policy",
        ));
    }

    let expected_mode = if raw.series_kind == RouterTimingSeriesKind::StageDiagnostic {
        RouterTimingInstrumentationMode::StageInstrumented
    } else {
        RouterTimingInstrumentationMode::MinimallyInstrumented
    };
    if raw.instrumentation_mode != expected_mode {
        return Err(invalid_timing_evidence(
            "router timing series mixes instrumentation modes",
        ));
    }

    let labels_are_valid = match (raw.series_kind, raw.replication_role) {
        (
            RouterTimingSeriesKind::MajorMinimallyInstrumented,
            RouterTimingReplicationRole::CleanProcessReplication,
        ) => {
            raw.process_state == RouterTimingProcessState::FreshProcess
                && raw.condition == RouterTimingCondition::Warm
        }
        (RouterTimingSeriesKind::FirstProcessCostly, RouterTimingReplicationRole::Primary) => {
            raw.process_state == RouterTimingProcessState::FreshProcess
                && raw.condition == RouterTimingCondition::FirstReadNewProcessOsCacheUncontrolled
        }
        (_, RouterTimingReplicationRole::Primary) => {
            raw.process_state == RouterTimingProcessState::ReusedProcess
                && raw.condition == RouterTimingCondition::Warm
        }
        _ => false,
    };
    if !labels_are_valid {
        return Err(invalid_timing_evidence(
            "router timing process, condition, and replication labels are incompatible",
        ));
    }
    Ok(())
}

fn validate_timing_observation(
    raw: RawRouterTimingObservation,
    expected_kind: RouterTimingObservationKind,
    expected_index: usize,
    series: &RawRouterTimingSeries,
) -> Result<RouterTimingObservation, ContractError> {
    if !is_timing_identifier(&raw.observation_id)
        || raw.run_index != expected_index
        || raw.observation_kind != expected_kind
        || raw.process_replication_id != series.process_replication_id
        || raw.process_state != series.process_state
        || raw.condition != series.condition
        || raw.instrumentation_mode != series.instrumentation_mode
        || raw.monotonic_clock != ROUTER_TIMING_CLOCK
        || raw.requested_device != "gpu"
        || raw.fallback_used
        || (raw.synchronized && !raw.evaluated)
    {
        return Err(invalid_timing_evidence(
            "router timing observation labels or execution envelope are invalid",
        ));
    }
    let output_sha256 = match raw.output_sha256 {
        Value::String(value) if is_lower_hex_sha256(&value) => Some(value),
        Value::Null => None,
        _ => {
            return Err(invalid_timing_evidence(
                "router timing output hash is invalid",
            ));
        }
    };
    let correctness_passed = match raw.correctness_passed {
        Value::Bool(value) => Some(value),
        Value::Null => None,
        _ => {
            return Err(invalid_timing_evidence(
                "router timing correctness state is invalid",
            ));
        }
    };
    let failure = match raw.failure {
        PresentTimingField::Missing => None,
        PresentTimingField::Present(value) => {
            if !valid_timing_failure_code(&value.code)
                || !valid_timing_failure_stage(&value.stage)
                || !valid_timing_text(&value.message)
            {
                return Err(invalid_timing_evidence(
                    "router timing failure evidence is invalid",
                ));
            }
            Some(RouterTimingFailure {
                code: value.code,
                message: value.message,
                stage: value.stage,
            })
        }
    };
    let stages = validate_timing_stages(
        raw.stages,
        series.series_kind,
        series.instrumentation_mode,
        raw.status,
        raw.evaluated,
        raw.synchronized,
        failure.as_ref().map(RouterTimingFailure::stage),
    )?;

    match raw.status {
        RouterTimingObservationStatus::Passed => {
            if raw.selected_device != "gpu"
                || !raw.evaluated
                || !raw.synchronized
                || output_sha256.is_none()
                || correctness_passed != Some(true)
                || failure.is_some()
            {
                return Err(invalid_timing_evidence(
                    "passing router timing observation contradicts its evidence",
                ));
            }
        }
        RouterTimingObservationStatus::Failed | RouterTimingObservationStatus::Aborted => {
            if failure.is_none() || correctness_passed == Some(true) {
                return Err(invalid_timing_evidence(
                    "unsuccessful router timing observation lacks failure evidence",
                ));
            }
            if raw.selected_device == "not_available" {
                if raw.evaluated
                    || raw.synchronized
                    || output_sha256.is_some()
                    || correctness_passed.is_some()
                {
                    return Err(invalid_timing_evidence(
                        "unavailable router timing observation contradicts completed work",
                    ));
                }
            } else if raw.selected_device != "gpu" {
                return Err(invalid_timing_evidence(
                    "unsuccessful router timing selected device is invalid",
                ));
            } else if output_sha256.is_some()
                && (raw.status != RouterTimingObservationStatus::Failed
                    || !raw.evaluated
                    || !raw.synchronized
                    || correctness_passed != Some(false))
            {
                return Err(invalid_timing_evidence(
                    "unsuccessful router timing output evidence is inconsistent",
                ));
            } else if output_sha256.is_none() && correctness_passed.is_some() {
                return Err(invalid_timing_evidence(
                    "unsuccessful router timing correctness evidence is incomplete",
                ));
            }
        }
        RouterTimingObservationStatus::Excluded => {
            return Err(invalid_timing_evidence(
                "frozen router timing protocol declares no exclusion rule",
            ));
        }
    }

    Ok(RouterTimingObservation {
        observation_id: raw.observation_id,
        run_index: raw.run_index,
        observation_kind: raw.observation_kind,
        process_replication_id: raw.process_replication_id,
        process_state: raw.process_state,
        condition: raw.condition,
        instrumentation_mode: raw.instrumentation_mode,
        monotonic_clock: raw.monotonic_clock,
        stages,
        status: raw.status,
        requested_device: raw.requested_device,
        selected_device: raw.selected_device,
        fallback_used: raw.fallback_used,
        evaluated: raw.evaluated,
        synchronized: raw.synchronized,
        output_sha256,
        correctness_passed,
        failure,
    })
}

fn validate_timing_stages(
    raw: BTreeMap<String, RawRouterTimingStage>,
    series_kind: RouterTimingSeriesKind,
    instrumentation_mode: RouterTimingInstrumentationMode,
    status: RouterTimingObservationStatus,
    evaluated: bool,
    synchronized: bool,
    failure_stage: Option<&str>,
) -> Result<BTreeMap<String, RouterTimingStageObservation>, ContractError> {
    if raw.is_empty() || raw.len() > 13 {
        return Err(invalid_timing_evidence(
            "router timing stage set is empty or unbounded",
        ));
    }
    let mut stages = BTreeMap::new();
    for (name, stage) in raw {
        if !valid_timing_stage_name(&name) {
            return Err(invalid_timing_evidence(
                "router timing stage name is invalid",
            ));
        }
        let value = match (stage.status.as_str(), stage.duration_ns, stage.reason) {
            ("observed", PresentTimingField::Present(duration_ns), PresentTimingField::Missing)
                if duration_ns > 0 =>
            {
                RouterTimingStageObservation::Observed { duration_ns }
            }
            ("unavailable", PresentTimingField::Missing, PresentTimingField::Present(reason))
                if valid_timing_text(&reason) =>
            {
                RouterTimingStageObservation::Unavailable { reason }
            }
            (
                "not_applicable",
                PresentTimingField::Missing,
                PresentTimingField::Present(reason),
            ) if name == "dequantization" && reason == ROUTER_F32_DEQUANTIZATION_REASON => {
                RouterTimingStageObservation::NotApplicable { reason }
            }
            _ => {
                return Err(invalid_timing_evidence(
                    "router timing stage fields contradict their status",
                ));
            }
        };
        stages.insert(name, value);
    }

    if (!evaluated || !synchronized)
        && stages.iter().any(|(name, value)| {
            evaluated_timing_stage_name(name)
                && matches!(value, RouterTimingStageObservation::Observed { .. })
        })
    {
        return Err(invalid_timing_evidence(
            "router timing reports evaluated stage duration without both barriers",
        ));
    }
    if let Some(stage_name) = failure_stage.filter(|stage| valid_timing_stage_name(stage)) {
        if !matches!(
            stages.get(stage_name),
            Some(RouterTimingStageObservation::Unavailable { .. })
        ) {
            return Err(invalid_timing_evidence(
                "router timing failure stage lacks matching unavailable evidence",
            ));
        }
    }

    match stages.get("dequantization") {
        Some(RouterTimingStageObservation::NotApplicable { reason })
            if reason == ROUTER_F32_DEQUANTIZATION_REASON => {}
        _ => {
            return Err(invalid_timing_evidence(
                "router timing lacks canonical F32 dequantization evidence",
            ));
        }
    }
    if status == RouterTimingObservationStatus::Passed {
        match instrumentation_mode {
            RouterTimingInstrumentationMode::MinimallyInstrumented => {
                let evaluated_total_is_observed = matches!(
                    stages.get("total_evaluated_router"),
                    Some(RouterTimingStageObservation::Observed { .. })
                );
                let external_read_is_observed = matches!(
                    stages.get("file_io"),
                    Some(RouterTimingStageObservation::Observed { .. })
                );
                let external_command_is_observed = matches!(
                    stages.get("end_to_end_router_command"),
                    Some(RouterTimingStageObservation::Observed { .. })
                );
                let stages_match_kind = match series_kind {
                    RouterTimingSeriesKind::FirstProcessCostly
                    | RouterTimingSeriesKind::CostlyReal => {
                        stages.len() == ROUTER_COSTLY_EXTERNAL_KEYS.len()
                            && ROUTER_COSTLY_EXTERNAL_KEYS
                                .iter()
                                .all(|stage| stages.contains_key(*stage))
                            && external_read_is_observed
                            && external_command_is_observed
                    }
                    _ => stages.len() == 2 && !stages.contains_key("file_io"),
                };
                if !stages_match_kind || !evaluated_total_is_observed {
                    return Err(invalid_timing_evidence(
                        "minimal router timing lacks its frozen evaluated total or first-process read",
                    ));
                }
            }
            RouterTimingInstrumentationMode::StageInstrumented => {
                if stages.len() != ROUTER_STAGE_DIAGNOSTIC_KEYS.len()
                    || ROUTER_STAGE_DIAGNOSTIC_KEYS
                        .iter()
                        .any(|stage| !stages.contains_key(*stage))
                {
                    return Err(invalid_timing_evidence(
                        "stage router timing omits a required observed-or-unavailable boundary",
                    ));
                }
                let observed_diagnostic = stages.iter().any(|(name, value)| {
                    name != "total_evaluated_router"
                        && name != "dequantization"
                        && matches!(value, RouterTimingStageObservation::Observed { .. })
                        && evaluated_timing_stage_name(name)
                });
                if !observed_diagnostic {
                    return Err(invalid_timing_evidence(
                        "stage router timing lacks an evaluated diagnostic",
                    ));
                }
            }
        }
    }
    Ok(stages)
}

fn valid_timing_stage_name(name: &str) -> bool {
    matches!(
        name,
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

fn evaluated_timing_stage_name(name: &str) -> bool {
    matches!(
        name,
        "host_to_device"
            | "graph_construction"
            | "compilation"
            | "router_projection"
            | "top_k"
            | "normalization"
            | "total_evaluated_router"
            | "synchronized_readback"
    )
}

fn valid_timing_failure_code(code: &str) -> bool {
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

fn valid_timing_failure_stage(stage: &str) -> bool {
    valid_timing_stage_name(stage)
        || matches!(
            stage,
            "protocol"
                | "worker_startup"
                | "resource_admission"
                | "router_execution"
                | "correctness_gate"
                | "orchestration"
        )
}

fn is_timing_identifier(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= MAX_CASE_ID_CHARS
        && value.trim() == value
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.' | b':'))
}

fn valid_timing_text(value: &str) -> bool {
    !value.is_empty()
        && value.trim() == value
        && value.chars().count() <= MAX_TIMING_REASON_CHARS
        && !value.chars().any(char::is_control)
        && !value.starts_with('/')
        && !value.starts_with("~/")
        && !value.contains("/Users/")
        && !value.contains("/home/")
        && !value.contains("\\Users\\")
        && value.split_whitespace().all(|token| {
            let uppercase = token.to_ascii_uppercase();
            !((uppercase.contains("TOKEN")
                || uppercase.contains("SECRET")
                || uppercase.contains("PASSWORD"))
                && token.contains('='))
        })
}

fn invalid_timing_evidence(message: &'static str) -> ContractError {
    ContractError::new(ErrorCategory::InvalidEvidence, "invalid_evidence", message)
}

/// Exact caller-observed identity for a complete router tensor range.
#[derive(Debug, Clone, PartialEq)]
pub struct RouterTensorDescriptor {
    pub name: String,
    pub semantic_role: String,
    pub occurrence_count: u64,
    pub gguf_dimensions_fastest_axis_first: Vec<u64>,
    pub reader_shape: Vec<u64>,
    pub execution_shape: Vec<u64>,
    pub gguf_type: String,
    pub quantization: String,
    pub logical_elements: u64,
    pub absolute_data_offset: u64,
    pub encoded_length: u64,
    pub encoded_sha256: String,
    pub byte_order: String,
    pub orientation: String,
    pub expert_count: u64,
    pub top_k: u64,
    pub weight_scale: f32,
    pub bias_present: bool,
    pub correction_bias_present: bool,
}

/// Host-observed resource gates required before router tensor execution.
///
/// The observations themselves are collected outside this model-neutral
/// module. This value only carries their fail-closed admission result so no
/// router runner can be reached after a failed disk, memory, or pressure gate.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RouterResourceAdmission {
    pub disk_headroom_satisfied: bool,
    pub unified_memory_headroom_satisfied: bool,
    pub memory_pressure_normal: bool,
}

/// A structurally admitted tensor range. External artifact identity remains a
/// separate pre-execution gate.
#[derive(Debug, Clone, PartialEq)]
pub struct AdmittedRouterTensor {
    descriptor: RouterTensorDescriptor,
    model_file_bytes: u64,
    exclusive_end_offset: u64,
}

impl AdmittedRouterTensor {
    pub fn name(&self) -> &str {
        &self.descriptor.name
    }

    pub fn semantic_role(&self) -> &str {
        &self.descriptor.semantic_role
    }

    pub fn gguf_dimensions(&self) -> &[u64] {
        &self.descriptor.gguf_dimensions_fastest_axis_first
    }

    pub fn reader_shape(&self) -> &[u64] {
        &self.descriptor.reader_shape
    }

    pub fn execution_shape(&self) -> &[u64] {
        &self.descriptor.execution_shape
    }

    pub fn gguf_type(&self) -> &str {
        &self.descriptor.gguf_type
    }

    pub fn quantization(&self) -> &str {
        &self.descriptor.quantization
    }

    pub fn logical_elements(&self) -> u64 {
        self.descriptor.logical_elements
    }

    pub fn absolute_data_offset(&self) -> u64 {
        self.descriptor.absolute_data_offset
    }

    pub fn encoded_length(&self) -> u64 {
        self.descriptor.encoded_length
    }

    pub fn model_file_bytes(&self) -> u64 {
        self.model_file_bytes
    }

    pub fn exclusive_end_offset(&self) -> u64 {
        self.exclusive_end_offset
    }

    pub fn encoded_sha256(&self) -> &str {
        &self.descriptor.encoded_sha256
    }

    pub fn expert_count(&self) -> u64 {
        self.descriptor.expert_count
    }

    pub fn top_k(&self) -> u64 {
        self.descriptor.top_k
    }

    pub fn weight_scale(&self) -> f32 {
        self.descriptor.weight_scale
    }

    pub fn bias_present(&self) -> bool {
        self.descriptor.bias_present
    }

    pub fn correction_bias_present(&self) -> bool {
        self.descriptor.correction_bias_present
    }
}

/// Admit only the exact complete version-1 F32 router contract.
pub fn admit_router_tensor(
    descriptor: &RouterTensorDescriptor,
    model_file_bytes: u64,
) -> Result<AdmittedRouterTensor, ContractError> {
    if descriptor.name != ROUTER_TENSOR_NAME || descriptor.semantic_role != ROUTER_SEMANTIC_ROLE {
        return Err(router_tensor_error(
            "missing_tensor_role",
            "the exact layer-0 router tensor role is missing",
        ));
    }
    match descriptor.occurrence_count {
        0 => {
            return Err(router_tensor_error(
                "missing_tensor_role",
                "the exact layer-0 router tensor role is missing",
            ));
        }
        1 => {}
        _ => {
            return Err(router_tensor_error(
                "duplicate_tensor_role",
                "the exact layer-0 router tensor role is not unique",
            ));
        }
    }
    if descriptor.gguf_dimensions_fastest_axis_first != [2_048, 128]
        || descriptor.reader_shape != [128, 2_048]
        || descriptor.execution_shape != [128, 2_048]
        || descriptor.logical_elements != ROUTER_TENSOR_ELEMENTS
    {
        return Err(router_tensor_error(
            "model_tensor_mismatch",
            "router tensor dimensions or element count differ from contract v1",
        ));
    }
    if descriptor.gguf_type != ROUTER_GGUF_TYPE || descriptor.quantization != ROUTER_QUANTIZATION {
        return Err(ContractError::new(
            ErrorCategory::InvalidQuantization,
            "unsupported_tensor_quantization",
            "router contract v1 admits only a complete F32 tensor",
        ));
    }
    if descriptor.byte_order != ROUTER_BYTE_ORDER || descriptor.orientation != ROUTER_ORIENTATION {
        return Err(ContractError::new(
            ErrorCategory::InvalidTensor,
            "invalid_layout",
            "router storage encoding or orientation differs from contract v1",
        ));
    }
    if descriptor.encoded_length != ROUTER_TENSOR_BYTES {
        return Err(router_tensor_error(
            "model_tensor_mismatch",
            "router tensor encoded byte length differs from complete F32 contract",
        ));
    }
    let exclusive_end_offset = descriptor
        .absolute_data_offset
        .checked_add(descriptor.encoded_length)
        .ok_or_else(|| {
            ContractError::new(
                ErrorCategory::ArithmeticOverflow,
                "invalid_tensor_range",
                "router tensor range overflows the artifact address space",
            )
        })?;
    if descriptor.absolute_data_offset >= model_file_bytes
        || exclusive_end_offset > model_file_bytes
    {
        return Err(ContractError::new(
            ErrorCategory::InvalidTensor,
            "invalid_tensor_range",
            "router tensor range is outside the immutable artifact",
        ));
    }
    if !is_lower_hex_sha256(&descriptor.encoded_sha256) {
        return Err(router_tensor_error(
            "model_checksum_mismatch",
            "router tensor range hash is not a canonical SHA-256 identity",
        ));
    }
    if descriptor.expert_count != ROUTER_EXPERT_COUNT as u64
        || descriptor.top_k != ROUTER_TOP_K as u64
        || descriptor.weight_scale.to_bits() != 1.0_f32.to_bits()
        || descriptor.bias_present
        || descriptor.correction_bias_present
    {
        return Err(router_tensor_error(
            "model_tensor_mismatch",
            "router expert count, top-k, scale, or bias metadata differs from contract v1",
        ));
    }

    Ok(AdmittedRouterTensor {
        descriptor: descriptor.clone(),
        model_file_bytes,
        exclusive_end_offset,
    })
}

/// Positional-read one exact bounded range without changing a file cursor.
///
/// Interrupted reads are retried, partial reads advance, and zero progress or
/// early EOF fails closed. The caller must separately verify file identity
/// before and after this operation.
#[cfg(unix)]
pub fn read_exact_range_at(
    file: &File,
    offset: u64,
    length: usize,
) -> Result<Vec<u8>, ContractError> {
    positional_read_exact(offset, length, |position, buffer| {
        file.read_at(buffer, position)
    })
}

/// Read, hash-bind, and decode the exact range carried by an admitted router.
///
/// The open file's current length must still match the length observed during
/// admission. Callers that also possess a frozen whole-artifact identity must
/// recheck that identity before and after execution.
#[cfg(unix)]
pub fn read_admitted_router_tensor_f32(
    file: &File,
    admitted: &AdmittedRouterTensor,
) -> Result<Vec<f32>, ContractError> {
    let metadata = file.metadata().map_err(|_| {
        router_tensor_error(
            "model_read_failed",
            "admitted router artifact metadata could not be rechecked",
        )
    })?;
    if !metadata.is_file() || metadata.len() != admitted.model_file_bytes {
        return Err(router_tensor_error(
            "model_size_mismatch",
            "admitted router artifact length changed before positional read",
        ));
    }
    let length = usize::try_from(admitted.descriptor.encoded_length).map_err(|_| {
        ContractError::new(
            ErrorCategory::ArithmeticOverflow,
            "invalid_tensor_range",
            "admitted router tensor length is not representable",
        )
    })?;
    let bytes = read_exact_range_at(file, admitted.descriptor.absolute_data_offset, length)?;
    if format!("{:x}", Sha256::digest(&bytes)) != admitted.descriptor.encoded_sha256 {
        return Err(router_tensor_error(
            "model_checksum_mismatch",
            "admitted router tensor bytes differ from the frozen range identity",
        ));
    }
    if bytes.len() != ROUTER_TENSOR_BYTES as usize || bytes.len() % size_of::<f32>() != 0 {
        return Err(invalid_byte_count(
            "admitted router tensor did not yield the exact complete F32 byte count",
        ));
    }

    let mut values = Vec::with_capacity(ROUTER_TENSOR_ELEMENTS as usize);
    for encoded in bytes.chunks_exact(size_of::<f32>()) {
        let value = f32::from_le_bytes(
            encoded
                .try_into()
                .expect("chunks_exact yields one complete float32 value"),
        );
        if !value.is_finite() {
            return Err(ContractError::new(
                ErrorCategory::InvalidTensor,
                "invalid_dtype",
                "admitted router tensor contains a non-finite float32 value",
            ));
        }
        values.push(value);
    }
    if values.len() != ROUTER_TENSOR_ELEMENTS as usize {
        return Err(invalid_byte_count(
            "admitted router tensor decoded element count differs from contract v1",
        ));
    }
    Ok(values)
}

/// Validate, resource-admit, read, and finite-decode one router tensor before
/// invoking its execution seam.
///
/// The callback is never called unless the descriptor, declared artifact
/// length, resource observations, positional range hash, byte count, and all
/// decoded F32 values satisfy the complete version-1 contract.
#[cfg(unix)]
pub fn with_admitted_router_tensor_f32<T, F>(
    file: &File,
    descriptor: &RouterTensorDescriptor,
    model_file_bytes: u64,
    resources: &RouterResourceAdmission,
    runner: F,
) -> Result<T, ContractError>
where
    F: FnOnce(&AdmittedRouterTensor, &[f32]) -> Result<T, ContractError>,
{
    let admitted = admit_router_tensor(descriptor, model_file_bytes)?;
    validate_router_resources(resources)?;
    let values = read_admitted_router_tensor_f32(file, &admitted)?;
    runner(&admitted, &values)
}

fn validate_router_resources(resources: &RouterResourceAdmission) -> Result<(), ContractError> {
    if !resources.disk_headroom_satisfied
        || !resources.unified_memory_headroom_satisfied
        || !resources.memory_pressure_normal
    {
        return Err(ContractError::new(
            ErrorCategory::ResourceLimit,
            "model_budget_exceeded",
            "router execution requires sufficient disk and unified-memory headroom under normal memory pressure",
        ));
    }
    Ok(())
}

/// Testable core for an exact positional range read.
pub fn positional_read_exact<F>(
    offset: u64,
    length: usize,
    mut read_at: F,
) -> Result<Vec<u8>, ContractError>
where
    F: FnMut(u64, &mut [u8]) -> io::Result<usize>,
{
    if length == 0 {
        return Err(invalid_byte_count("router tensor reads must be nonempty"));
    }
    if (length as u128) > u128::from(ROUTER_TENSOR_BYTES) {
        return Err(invalid_byte_count(
            "router tensor read exceeds the complete bounded F32 range",
        ));
    }
    let length_u64 = u64::try_from(length).map_err(|_| {
        ContractError::new(
            ErrorCategory::ArithmeticOverflow,
            "invalid_tensor_range",
            "router tensor read length is not representable",
        )
    })?;
    offset.checked_add(length_u64).ok_or_else(|| {
        ContractError::new(
            ErrorCategory::ArithmeticOverflow,
            "invalid_tensor_range",
            "router tensor read range overflows",
        )
    })?;

    let mut bytes = Vec::new();
    bytes.try_reserve_exact(length).map_err(|_| {
        ContractError::new(
            ErrorCategory::ResourceLimit,
            "model_budget_exceeded",
            "router tensor read buffer could not be reserved within resource limits",
        )
    })?;
    bytes.resize(length, 0_u8);
    let mut consumed = 0_usize;
    while consumed < length {
        let position = offset
            .checked_add(u64::try_from(consumed).map_err(|_| {
                ContractError::new(
                    ErrorCategory::ArithmeticOverflow,
                    "invalid_tensor_range",
                    "router tensor read position is not representable",
                )
            })?)
            .ok_or_else(|| {
                ContractError::new(
                    ErrorCategory::ArithmeticOverflow,
                    "invalid_tensor_range",
                    "router tensor read position overflows",
                )
            })?;
        match read_at(position, &mut bytes[consumed..]) {
            Ok(0) => {
                return Err(invalid_byte_count(
                    "router tensor positional read ended before the exact range was complete",
                ));
            }
            Ok(read) if read <= length - consumed => consumed += read,
            Ok(_) => {
                return Err(invalid_byte_count(
                    "router tensor positional reader returned an impossible byte count",
                ));
            }
            Err(error) if error.kind() == ErrorKind::Interrupted => continue,
            Err(_) => {
                return Err(invalid_byte_count(
                    "router tensor positional read failed before completion",
                ));
            }
        }
    }
    Ok(bytes)
}

/// Canonical SHA-256 over finite IEEE-754 float32 little-endian values.
pub fn canonical_f32le_sha256(values: &[f32]) -> Result<String, ContractError> {
    if values.iter().any(|value| !value.is_finite()) {
        return Err(ContractError::new(
            ErrorCategory::InvalidComparison,
            "invalid_dtype",
            "canonical router output hashing rejects non-finite float32 values",
        ));
    }
    let mut digest = Sha256::new();
    for value in values {
        digest.update(value.to_le_bytes());
    }
    Ok(format!("{:x}", digest.finalize()))
}

/// Provenance boundary controlling the version-1 rank-8/rank-9 tie policy.
///
/// Synthetic fixtures exercise the deterministic lower-expert-ID rule. A
/// real-checkpoint cutoff tie is instead a cross-runtime stop condition and
/// must never be converted into passing evidence by that synthetic rule.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum RouterCaseScope {
    SyntheticFixture,
    RealCheckpoint,
}

/// Complete bounded router output for one generated or admitted case.
#[derive(Debug, Clone, PartialEq)]
pub struct RouterOutput {
    case_id: String,
    case_scope: RouterCaseScope,
    row_count: usize,
    logits_shape: [usize; 2],
    full_probabilities_shape: [usize; 2],
    logits: Vec<f32>,
    full_probabilities: Vec<f32>,
    selected_expert_ids: Vec<Vec<u64>>,
    selected_probabilities: Vec<Vec<f32>>,
    normalized_weights: Vec<Vec<f32>>,
    logits_f32le_sha256: String,
    full_probabilities_f32le_sha256: String,
    selected_probabilities_f32le_sha256: String,
    normalized_weights_f32le_sha256: String,
}

impl RouterOutput {
    #[allow(clippy::too_many_arguments)]
    pub fn try_new(
        case_id: impl Into<String>,
        case_scope: RouterCaseScope,
        row_count: usize,
        logits: Vec<f32>,
        full_probabilities: Vec<f32>,
        selected_expert_ids: Vec<Vec<u64>>,
        selected_probabilities: Vec<Vec<f32>>,
        normalized_weights: Vec<Vec<f32>>,
    ) -> Result<Self, ContractError> {
        let case_id = case_id.into();
        validate_case_id(&case_id)?;
        if !(1..=ROUTER_MAX_ROWS).contains(&row_count) {
            return Err(invalid_shape(
                "router output row count exceeds the bounded contract",
            ));
        }
        let complete_count = row_count.checked_mul(ROUTER_EXPERT_COUNT).ok_or_else(|| {
            ContractError::new(
                ErrorCategory::ArithmeticOverflow,
                "invalid_shape",
                "router output element count overflows",
            )
        })?;
        if logits.len() != complete_count || full_probabilities.len() != complete_count {
            return Err(invalid_shape(
                "router output must retain all 128 logits and probabilities per row",
            ));
        }
        if selected_expert_ids.len() != row_count
            || selected_probabilities.len() != row_count
            || normalized_weights.len() != row_count
        {
            return Err(invalid_shape(
                "router selected-output row count differs from the complete output",
            ));
        }
        ensure_finite(&logits, "router logits contain a non-finite value")?;
        ensure_finite(
            &full_probabilities,
            "router probabilities contain a non-finite value",
        )?;

        for row_index in 0..row_count {
            let ids = &selected_expert_ids[row_index];
            let selected = &selected_probabilities[row_index];
            let normalized = &normalized_weights[row_index];
            if ids.len() != ROUTER_TOP_K
                || selected.len() != ROUTER_TOP_K
                || normalized.len() != ROUTER_TOP_K
            {
                return Err(invalid_shape(
                    "router selected outputs must contain exactly eight values per row",
                ));
            }
            let unique: BTreeSet<u64> = ids.iter().copied().collect();
            if unique.len() != ROUTER_TOP_K
                || ids
                    .iter()
                    .any(|expert_id| *expert_id >= ROUTER_EXPERT_COUNT as u64)
            {
                return Err(ContractError::new(
                    ErrorCategory::InvalidSelection,
                    "comparison_failed",
                    "router selected expert IDs are duplicated or out of range",
                ));
            }
            ensure_finite(selected, "selected router probabilities are non-finite")?;
            ensure_finite(normalized, "normalized router weights are non-finite")?;
            let logits_row =
                &logits[row_index * ROUTER_EXPERT_COUNT..(row_index + 1) * ROUTER_EXPERT_COUNT];
            let probability_row = &full_probabilities
                [row_index * ROUTER_EXPERT_COUNT..(row_index + 1) * ROUTER_EXPERT_COUNT];
            validate_complete_softmax(logits_row, probability_row)?;

            let mut ranked_ids = (0..ROUTER_EXPERT_COUNT).collect::<Vec<_>>();
            ranked_ids.sort_by(|left, right| {
                probability_row[*right]
                    .partial_cmp(&probability_row[*left])
                    .expect("router probabilities were proven finite")
                    .then_with(|| left.cmp(right))
            });
            if case_scope == RouterCaseScope::RealCheckpoint
                && probability_row[ranked_ids[ROUTER_TOP_K - 1]]
                    == probability_row[ranked_ids[ROUTER_TOP_K]]
            {
                return Err(ContractError::new(
                    ErrorCategory::InvalidComparison,
                    "comparison_failed",
                    "an exact float32 probability tie crosses real router ranks eight and nine",
                ));
            }
            let expected_ids = &ranked_ids[..ROUTER_TOP_K];
            if ids
                .iter()
                .copied()
                .ne(expected_ids.iter().map(|expert_id| *expert_id as u64))
            {
                return Err(ContractError::new(
                    ErrorCategory::InvalidSelection,
                    "comparison_failed",
                    "router selected expert IDs do not match deterministic complete-softmax order",
                ));
            }
            for (rank, expert_id) in ids.iter().enumerate() {
                let expert_index = usize::try_from(*expert_id).map_err(|_| {
                    invalid_shape("router expert ID is not representable on this host")
                })?;
                if selected[rank].to_bits() != probability_row[expert_index].to_bits() {
                    return Err(ContractError::new(
                        ErrorCategory::InvalidComparison,
                        "comparison_failed",
                        "selected router probability does not match the complete softmax output",
                    ));
                }
            }
            if selected.iter().any(|value| *value < 0.0)
                || normalized.iter().any(|value| *value < 0.0)
            {
                return Err(ContractError::new(
                    ErrorCategory::InvalidComparison,
                    "comparison_failed",
                    "router probabilities and weights must be nonnegative",
                ));
            }
            let selected_sum = selected.iter().copied().map(f64::from).sum::<f64>();
            let normalized_sum = normalized.iter().copied().map(f64::from).sum::<f64>();
            if !selected_sum.is_finite()
                || selected_sum <= 0.0
                || !normalized_sum.is_finite()
                || (normalized_sum - 1.0).abs() > WEIGHT_SUM_TOLERANCE
            {
                return Err(ContractError::new(
                    ErrorCategory::InvalidComparison,
                    "comparison_failed",
                    "router selected sum or normalized weight sum is invalid",
                ));
            }
            for (selected_value, normalized_value) in selected.iter().zip(normalized) {
                let expected = f64::from(*selected_value) / selected_sum;
                if (f64::from(*normalized_value) - expected).abs() > WEIGHT_SUM_TOLERANCE {
                    return Err(ContractError::new(
                        ErrorCategory::InvalidComparison,
                        "comparison_failed",
                        "normalized router weight does not match selected-probability renormalization",
                    ));
                }
            }
        }

        let selected_flat = selected_probabilities
            .iter()
            .flatten()
            .copied()
            .collect::<Vec<_>>();
        let normalized_flat = normalized_weights
            .iter()
            .flatten()
            .copied()
            .collect::<Vec<_>>();
        let logits_f32le_sha256 = canonical_f32le_sha256(&logits)?;
        let full_probabilities_f32le_sha256 = canonical_f32le_sha256(&full_probabilities)?;
        let selected_probabilities_f32le_sha256 = canonical_f32le_sha256(&selected_flat)?;
        let normalized_weights_f32le_sha256 = canonical_f32le_sha256(&normalized_flat)?;

        Ok(Self {
            case_id,
            case_scope,
            row_count,
            logits_shape: [row_count, ROUTER_EXPERT_COUNT],
            full_probabilities_shape: [row_count, ROUTER_EXPERT_COUNT],
            logits,
            full_probabilities,
            selected_expert_ids,
            selected_probabilities,
            normalized_weights,
            logits_f32le_sha256,
            full_probabilities_f32le_sha256,
            selected_probabilities_f32le_sha256,
            normalized_weights_f32le_sha256,
        })
    }

    pub fn case_id(&self) -> &str {
        &self.case_id
    }

    pub fn case_scope(&self) -> RouterCaseScope {
        self.case_scope
    }

    pub fn row_count(&self) -> usize {
        self.row_count
    }

    pub fn logits_shape(&self) -> &[usize; 2] {
        &self.logits_shape
    }

    pub fn full_probabilities_shape(&self) -> &[usize; 2] {
        &self.full_probabilities_shape
    }

    pub fn logits(&self) -> &[f32] {
        &self.logits
    }

    pub fn full_probabilities(&self) -> &[f32] {
        &self.full_probabilities
    }

    pub fn selected_expert_ids(&self) -> &[Vec<u64>] {
        &self.selected_expert_ids
    }

    pub fn selected_probabilities(&self) -> &[Vec<f32>] {
        &self.selected_probabilities
    }

    pub fn normalized_weights(&self) -> &[Vec<f32>] {
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

    pub fn repeat_identity(&self) -> RouterRepeatIdentity {
        RouterRepeatIdentity {
            case_id: self.case_id.clone(),
            case_scope: self.case_scope,
            row_count: self.row_count,
            logits_f32le_sha256: self.logits_f32le_sha256.clone(),
            full_probabilities_f32le_sha256: self.full_probabilities_f32le_sha256.clone(),
            selected_probabilities_f32le_sha256: self.selected_probabilities_f32le_sha256.clone(),
            normalized_weights_f32le_sha256: self.normalized_weights_f32le_sha256.clone(),
            selected_expert_ids: self.selected_expert_ids.clone(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RouterRepeatIdentity {
    case_id: String,
    case_scope: RouterCaseScope,
    row_count: usize,
    logits_f32le_sha256: String,
    full_probabilities_f32le_sha256: String,
    selected_probabilities_f32le_sha256: String,
    normalized_weights_f32le_sha256: String,
    selected_expert_ids: Vec<Vec<u64>>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RouterRepeatSummary {
    repeat_count: usize,
    unique_output_identity_count: usize,
    identical: bool,
}

impl RouterRepeatSummary {
    pub fn repeat_count(&self) -> usize {
        self.repeat_count
    }

    pub fn unique_output_identity_count(&self) -> usize {
        self.unique_output_identity_count
    }

    pub fn identical(&self) -> bool {
        self.identical
    }
}

pub fn validate_repeat_identities(
    identities: &[RouterRepeatIdentity],
) -> Result<RouterRepeatSummary, ContractError> {
    if identities.len() < 10 {
        return Err(ContractError::new(
            ErrorCategory::InvalidComparison,
            "comparison_failed",
            "router repeatability requires at least ten measured identities",
        ));
    }
    let first = identities.first().expect("length checked above");
    let unique_output_identity_count = identities
        .iter()
        .map(|identity| {
            (
                identity.case_id.as_str(),
                identity.case_scope,
                identity.row_count,
                identity.logits_f32le_sha256.as_str(),
                identity.full_probabilities_f32le_sha256.as_str(),
                identity.selected_probabilities_f32le_sha256.as_str(),
                identity.normalized_weights_f32le_sha256.as_str(),
                &identity.selected_expert_ids,
            )
        })
        .collect::<BTreeSet<_>>()
        .len();
    if identities.iter().any(|identity| identity != first) {
        return Err(ContractError::new(
            ErrorCategory::InvalidComparison,
            "comparison_failed",
            "router measured repetitions are not bitwise identical",
        ));
    }
    Ok(RouterRepeatSummary {
        repeat_count: identities.len(),
        unique_output_identity_count,
        identical: true,
    })
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct NumericTolerance {
    absolute: f64,
    relative: f64,
}

impl NumericTolerance {
    pub fn absolute(&self) -> f64 {
        self.absolute
    }

    pub fn relative(&self) -> f64 {
        self.relative
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct RouterTolerancePolicy {
    logits: NumericTolerance,
    full_probabilities: NumericTolerance,
    selected_probabilities: NumericTolerance,
    normalized_weights: NumericTolerance,
}

impl RouterTolerancePolicy {
    pub const fn contract_v1() -> Self {
        Self {
            logits: NumericTolerance {
                absolute: 5.0e-4,
                relative: 5.0e-4,
            },
            full_probabilities: NumericTolerance {
                absolute: 1.0e-6,
                relative: 1.0e-6,
            },
            selected_probabilities: NumericTolerance {
                absolute: 1.0e-6,
                relative: 1.0e-6,
            },
            normalized_weights: NumericTolerance {
                absolute: 1.0e-6,
                relative: 1.0e-6,
            },
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct RouterMismatch {
    row_index: usize,
    column_index: usize,
    reference: f32,
    candidate: f32,
}

impl RouterMismatch {
    pub fn row_index(&self) -> usize {
        self.row_index
    }

    pub fn column_index(&self) -> usize {
        self.column_index
    }

    pub fn reference(&self) -> f32 {
        self.reference
    }

    pub fn candidate(&self) -> f32 {
        self.candidate
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct RouterNumericComparison {
    compared_count: usize,
    mismatch_count: usize,
    first_mismatch: Option<RouterMismatch>,
    maximum_absolute_error: f64,
    mean_absolute_error: f64,
    rmse: f64,
    maximum_relative_error: Option<f64>,
    tolerance: NumericTolerance,
}

impl RouterNumericComparison {
    pub fn compared_count(&self) -> usize {
        self.compared_count
    }

    pub fn mismatch_count(&self) -> usize {
        self.mismatch_count
    }

    pub fn first_mismatch(&self) -> Option<&RouterMismatch> {
        self.first_mismatch.as_ref()
    }

    pub fn maximum_absolute_error(&self) -> f64 {
        self.maximum_absolute_error
    }

    pub fn mean_absolute_error(&self) -> f64 {
        self.mean_absolute_error
    }

    pub fn rmse(&self) -> f64 {
        self.rmse
    }

    pub fn maximum_relative_error(&self) -> Option<f64> {
        self.maximum_relative_error
    }

    pub fn tolerance(&self) -> NumericTolerance {
        self.tolerance
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct RouterOutputComparison {
    logits: RouterNumericComparison,
    full_probabilities: RouterNumericComparison,
    selected_probabilities: RouterNumericComparison,
    normalized_weights: RouterNumericComparison,
    id_mismatch_count: usize,
    order_mismatch_count: usize,
    passed: bool,
}

impl RouterOutputComparison {
    pub fn logits(&self) -> &RouterNumericComparison {
        &self.logits
    }

    pub fn full_probabilities(&self) -> &RouterNumericComparison {
        &self.full_probabilities
    }

    pub fn selected_probabilities(&self) -> &RouterNumericComparison {
        &self.selected_probabilities
    }

    pub fn normalized_weights(&self) -> &RouterNumericComparison {
        &self.normalized_weights
    }

    pub fn id_mismatch_count(&self) -> usize {
        self.id_mismatch_count
    }

    pub fn order_mismatch_count(&self) -> usize {
        self.order_mismatch_count
    }

    pub fn passed(&self) -> bool {
        self.passed
    }
}

pub fn compare_router_outputs(
    reference: &RouterOutput,
    candidate: &RouterOutput,
    policy: &RouterTolerancePolicy,
) -> Result<RouterOutputComparison, ContractError> {
    if reference.case_id != candidate.case_id
        || reference.case_scope != candidate.case_scope
        || reference.row_count != candidate.row_count
        || reference.logits_shape != candidate.logits_shape
        || reference.full_probabilities_shape != candidate.full_probabilities_shape
    {
        return Err(ContractError::new(
            ErrorCategory::InvalidComparison,
            "comparison_failed",
            "router outputs have incompatible identities or shapes",
        ));
    }

    let logits = compare_numeric(
        &reference.logits,
        &candidate.logits,
        ROUTER_EXPERT_COUNT,
        policy.logits,
    )?;
    let full_probabilities = compare_numeric(
        &reference.full_probabilities,
        &candidate.full_probabilities,
        ROUTER_EXPERT_COUNT,
        policy.full_probabilities,
    )?;
    let reference_selected = flatten_rows(&reference.selected_probabilities);
    let candidate_selected = flatten_rows(&candidate.selected_probabilities);
    let selected_probabilities = compare_numeric(
        &reference_selected,
        &candidate_selected,
        ROUTER_TOP_K,
        policy.selected_probabilities,
    )?;
    let reference_normalized = flatten_rows(&reference.normalized_weights);
    let candidate_normalized = flatten_rows(&candidate.normalized_weights);
    let normalized_weights = compare_numeric(
        &reference_normalized,
        &candidate_normalized,
        ROUTER_TOP_K,
        policy.normalized_weights,
    )?;

    let mut id_mismatch_count = 0_usize;
    let mut order_mismatch_count = 0_usize;
    for (reference_ids, candidate_ids) in reference
        .selected_expert_ids
        .iter()
        .zip(&candidate.selected_expert_ids)
    {
        let reference_set = reference_ids.iter().copied().collect::<BTreeSet<_>>();
        let candidate_set = candidate_ids.iter().copied().collect::<BTreeSet<_>>();
        id_mismatch_count += reference_set.difference(&candidate_set).count();
        order_mismatch_count += reference_ids
            .iter()
            .zip(candidate_ids)
            .filter(|(left, right)| left != right)
            .count();
    }

    let passed = id_mismatch_count == 0
        && order_mismatch_count == 0
        && logits.mismatch_count == 0
        && full_probabilities.mismatch_count == 0
        && selected_probabilities.mismatch_count == 0
        && normalized_weights.mismatch_count == 0;
    Ok(RouterOutputComparison {
        logits,
        full_probabilities,
        selected_probabilities,
        normalized_weights,
        id_mismatch_count,
        order_mismatch_count,
        passed,
    })
}

fn compare_numeric(
    reference: &[f32],
    candidate: &[f32],
    row_width: usize,
    tolerance: NumericTolerance,
) -> Result<RouterNumericComparison, ContractError> {
    if reference.len() != candidate.len() || reference.is_empty() || row_width == 0 {
        return Err(invalid_shape(
            "router numeric comparison inputs have incompatible lengths",
        ));
    }
    ensure_finite(reference, "router reference contains a non-finite value")?;
    ensure_finite(candidate, "router candidate contains a non-finite value")?;

    let mut mismatch_count = 0_usize;
    let mut first_mismatch = None;
    let mut maximum_absolute_error = 0.0_f64;
    let mut absolute_error_sum = 0.0_f64;
    let mut squared_error_sum = 0.0_f64;
    let mut maximum_relative_error = None::<f64>;
    for (index, (reference_value, candidate_value)) in reference.iter().zip(candidate).enumerate() {
        let reference_f64 = f64::from(*reference_value);
        let candidate_f64 = f64::from(*candidate_value);
        let absolute_error = (candidate_f64 - reference_f64).abs();
        let admitted = tolerance.absolute + tolerance.relative * reference_f64.abs();
        if absolute_error > admitted {
            mismatch_count += 1;
            first_mismatch.get_or_insert(RouterMismatch {
                row_index: index / row_width,
                column_index: index % row_width,
                reference: *reference_value,
                candidate: *candidate_value,
            });
        }
        maximum_absolute_error = maximum_absolute_error.max(absolute_error);
        absolute_error_sum += absolute_error;
        squared_error_sum += absolute_error * absolute_error;
        if reference_f64 != 0.0 {
            let relative_error = absolute_error / reference_f64.abs();
            maximum_relative_error =
                Some(maximum_relative_error.unwrap_or(0.0).max(relative_error));
        }
    }
    let compared_count = reference.len();
    let compared_f64 = compared_count as f64;
    Ok(RouterNumericComparison {
        compared_count,
        mismatch_count,
        first_mismatch,
        maximum_absolute_error,
        mean_absolute_error: absolute_error_sum / compared_f64,
        rmse: (squared_error_sum / compared_f64).sqrt(),
        maximum_relative_error,
        tolerance,
    })
}

fn flatten_rows(rows: &[Vec<f32>]) -> Vec<f32> {
    rows.iter().flatten().copied().collect()
}

fn validate_complete_softmax(logits: &[f32], probabilities: &[f32]) -> Result<(), ContractError> {
    if logits.len() != ROUTER_EXPERT_COUNT || probabilities.len() != ROUTER_EXPERT_COUNT {
        return Err(invalid_shape(
            "router softmax inputs must contain all 128 experts",
        ));
    }
    if probabilities.iter().any(|value| *value < 0.0) {
        return Err(ContractError::new(
            ErrorCategory::InvalidComparison,
            "comparison_failed",
            "complete router probabilities must be nonnegative",
        ));
    }

    let maximum = logits
        .iter()
        .copied()
        .map(f64::from)
        .reduce(f64::max)
        .expect("complete router row is nonempty");
    let exponentials = logits
        .iter()
        .map(|value| (f64::from(*value) - maximum).exp())
        .collect::<Vec<_>>();
    let denominator = exponentials.iter().sum::<f64>();
    if !denominator.is_finite() || denominator <= 0.0 {
        return Err(ContractError::new(
            ErrorCategory::InvalidComparison,
            "comparison_failed",
            "router logits do not define a finite complete softmax",
        ));
    }

    let probability_sum = probabilities.iter().copied().map(f64::from).sum::<f64>();
    if !probability_sum.is_finite() || (probability_sum - 1.0).abs() > WEIGHT_SUM_TOLERANCE {
        return Err(ContractError::new(
            ErrorCategory::InvalidComparison,
            "comparison_failed",
            "complete router probabilities do not sum to one",
        ));
    }
    for (candidate, exponential) in probabilities.iter().zip(exponentials) {
        let expected = exponential / denominator;
        let error = (f64::from(*candidate) - expected).abs();
        let admitted =
            PROBABILITY_ABSOLUTE_TOLERANCE + PROBABILITY_RELATIVE_TOLERANCE * expected.abs();
        if error > admitted {
            return Err(ContractError::new(
                ErrorCategory::InvalidComparison,
                "comparison_failed",
                "complete router probabilities are not the full softmax of the logits",
            ));
        }
    }
    Ok(())
}

fn ensure_finite(values: &[f32], message: &'static str) -> Result<(), ContractError> {
    if values.iter().any(|value| !value.is_finite()) {
        return Err(ContractError::new(
            ErrorCategory::InvalidComparison,
            "invalid_dtype",
            message,
        ));
    }
    Ok(())
}

fn validate_case_id(case_id: &str) -> Result<(), ContractError> {
    if case_id.is_empty()
        || case_id.len() > MAX_CASE_ID_CHARS
        || !case_id
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'-')
    {
        return Err(ContractError::new(
            ErrorCategory::InvalidEvidence,
            "unsupported_operation",
            "router case identity is not a bounded stable identifier",
        ));
    }
    Ok(())
}

fn is_lower_hex_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn router_tensor_error(code: &'static str, message: &'static str) -> ContractError {
    ContractError::new(ErrorCategory::InvalidTensor, code, message)
}

fn invalid_shape(message: &'static str) -> ContractError {
    ContractError::new(ErrorCategory::InvalidTensor, "invalid_shape", message)
}

fn invalid_byte_count(message: &'static str) -> ContractError {
    ContractError::new(ErrorCategory::InvalidTensor, "invalid_byte_count", message)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::VecDeque;
    #[cfg(unix)]
    use std::fs::{self, OpenOptions};
    #[cfg(unix)]
    use std::io::Write;
    #[cfg(unix)]
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn positional_read_retries_interruptions_and_joins_partial_reads() {
        let mut events = VecDeque::from([
            Err(io::Error::from(ErrorKind::Interrupted)),
            Ok(vec![1_u8, 2]),
            Ok(vec![3_u8, 4]),
        ]);
        let bytes = positional_read_exact(100, 4, |position, destination| {
            let event = events.pop_front().expect("fixture event remains")?;
            let expected_position = if destination.len() == 4 { 100 } else { 102 };
            assert_eq!(position, expected_position);
            destination[..event.len()].copy_from_slice(&event);
            Ok(event.len())
        })
        .expect("partial exact read succeeds");
        assert_eq!(bytes, [1, 2, 3, 4]);
    }

    #[test]
    fn positional_read_rejects_zero_progress() {
        let error = positional_read_exact(0, 1, |_position, _destination| Ok(0))
            .expect_err("zero progress must fail");
        assert_eq!(error.code(), "invalid_byte_count");
    }

    #[cfg(unix)]
    #[test]
    fn admitted_router_range_is_positionally_read_and_hash_bound() {
        let prefix = vec![0xa5_u8; 32];
        let encoded = vec![0_u8; ROUTER_TENSOR_BYTES as usize];
        let suffix = vec![0x5a_u8; 16];
        let model_file_bytes = (prefix.len() + encoded.len() + suffix.len()) as u64;
        let descriptor = RouterTensorDescriptor {
            name: ROUTER_TENSOR_NAME.to_owned(),
            semantic_role: ROUTER_SEMANTIC_ROLE.to_owned(),
            occurrence_count: 1,
            gguf_dimensions_fastest_axis_first: vec![2_048, 128],
            reader_shape: vec![128, 2_048],
            execution_shape: vec![128, 2_048],
            gguf_type: ROUTER_GGUF_TYPE.to_owned(),
            quantization: ROUTER_QUANTIZATION.to_owned(),
            logical_elements: ROUTER_TENSOR_ELEMENTS,
            absolute_data_offset: prefix.len() as u64,
            encoded_length: ROUTER_TENSOR_BYTES,
            encoded_sha256: format!("{:x}", Sha256::digest(&encoded)),
            byte_order: ROUTER_BYTE_ORDER.to_owned(),
            orientation: ROUTER_ORIENTATION.to_owned(),
            expert_count: ROUTER_EXPERT_COUNT as u64,
            top_k: ROUTER_TOP_K as u64,
            weight_scale: 1.0,
            bias_present: false,
            correction_bias_present: false,
        };
        let admitted = admit_router_tensor(&descriptor, model_file_bytes)
            .expect("complete exact descriptor is admitted");

        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("test clock is after the Unix epoch")
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "pulsarmlx-router-range-{}-{nonce}.bin",
            std::process::id()
        ));
        let mut file = OpenOptions::new()
            .create_new(true)
            .read(true)
            .write(true)
            .open(&path)
            .expect("create isolated router fixture");
        file.write_all(&prefix).expect("write fixture prefix");
        file.write_all(&encoded)
            .expect("write router fixture bytes");
        file.write_all(&suffix).expect("write fixture suffix");
        file.sync_all().expect("synchronize router fixture");

        let values = read_admitted_router_tensor_f32(&file, &admitted)
            .expect("the exact admitted range is read and hash-bound");
        assert_eq!(values.len(), ROUTER_TENSOR_ELEMENTS as usize);
        assert!(values.iter().all(|value| value.to_bits() == 0));
        drop(file);
        fs::remove_file(path).expect("remove isolated router fixture");
    }
}
