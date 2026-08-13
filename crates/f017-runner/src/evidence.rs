use crate::cli::{mode_environment_policy, Config, EnvironmentPolicy};
use crate::contract_bindings::r12_contract_bindings;
use crate::environment::{LoadedLibraryEvidence, ValidatedEnvironment};
use crate::numerical_classification::{
    validate_classification_applicability, GreedyApplicability, GreedyIdentityEvidence,
    NumericalClassification,
};
use crate::{FailureClass, RunnerError};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::PathBuf;

pub const EVIDENCE_SCHEMA: &str = "pulsarmlx.f017.canonical-runner-evidence";
pub const EVIDENCE_SCHEMA_VERSION: &str = "1.3.0";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Evidence {
    pub schema: String,
    pub schema_version: String,
    pub identity: IdentityEvidence,
    pub admission: AdmissionEvidence,
    pub input: InputEvidence,
    pub execution: ExecutionEvidence,
    pub residency: ResidencyEvidence,
    pub lifecycle: LifecycleEvidence,
    pub result: ResultEvidence,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct IdentityEvidence {
    pub source_sha: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub compiled_runtime_sha: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub tooling_sha: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub authorization_head_sha: Option<String>,
    pub source_clean: bool,
    pub runner_version: String,
    pub environment_kind: String,
    pub environment_manifest_sha256: String,
    pub platform: BTreeMap<String, String>,
    pub toolchain: BTreeMap<String, String>,
    pub loaded_libraries: Vec<LoadedLibraryEvidence>,
    pub checkpoint: CheckpointEvidence,
    #[serde(default)]
    pub prior_evidence: BTreeMap<String, String>,
    #[serde(default)]
    pub artifact_paths: Vec<ArtifactPathEvidence>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub execution_config_sha256: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ArtifactPathEvidence {
    pub path_kind: String,
    pub symbolic_path: String,
    pub content_sha256: String,
    pub logical_role: String,
    pub repository_identity: Option<String>,
    pub package_artifact_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CheckpointEvidence {
    pub accessed: bool,
    pub revision: Option<String>,
    pub checkpoint_set_sha256: Option<String>,
    pub catalog_sha256: Option<String>,
    pub architecture: Option<String>,
    pub tokenizer_identity: Option<String>,
    pub tensor_count: Option<u64>,
    pub tensor_map: TensorMapEvidence,
    pub shards: Vec<ShardEvidence>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
pub struct TensorMapEvidence {
    pub status: TensorMapStatus,
    pub version: Option<String>,
    pub contract_sha256: Option<String>,
    pub validated_tensor_count: Option<u64>,
}

#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum TensorMapStatus {
    Validated,
    NotApplicable,
    #[default]
    Unavailable,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ShardEvidence {
    pub filename: String,
    pub size_bytes: u64,
    pub sha256: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AdmissionEvidence {
    pub telemetry_source: String,
    pub physical_memory_bytes: u64,
    pub memory_floor_bytes: u64,
    pub available_memory_bytes: u64,
    pub compressed_memory_bytes: u64,
    pub memory_pressure: String,
    pub swap_used_bytes: u64,
    pub checkpoint_volume_free_bytes: Option<u64>,
    pub evidence_volume_free_bytes: u64,
    pub load_averages: [f64; 3],
    pub competing_processes_clear: bool,
    pub competing_processes: Vec<String>,
    pub port_1234_listener: bool,
    pub thermal_state: String,
    pub performance_warning: bool,
    pub stream_mode: String,
    pub singleton_initially_unclaimed: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct InputEvidence {
    pub tokens: Vec<u32>,
    pub n_new: u32,
    pub expected_token: Option<u32>,
    pub validation_mode: String,
    pub mode: String,
    pub numerical_mode: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ExecutionEvidence {
    pub layers: Vec<LayerEvidence>,
    pub timings: BTreeMap<String, f64>,
    pub storage: StorageEvidence,
    pub dispatch: DispatchEvidence,
    pub generated_token: Option<u32>,
    pub numerical_classification: Option<NumericalClassification>,
    pub numerical: NumericalEvidence,
    pub progress_state: String,
    #[serde(default)]
    pub attempt_state: String,
    #[serde(default)]
    pub attempt_consumed: bool,
    #[serde(default)]
    pub projection_count: u64,
    #[serde(default)]
    pub quant_decode_count: u64,
    #[serde(default)]
    pub expert_execution_count: u64,
    #[serde(default)]
    pub layer_execution_count: u64,
    #[serde(default)]
    pub logits_count: u64,
    #[serde(default)]
    pub p1: bool,
    #[serde(default)]
    pub p2: bool,
    #[serde(default)]
    pub golden_eight: bool,
    #[serde(default)]
    pub feature_018: bool,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct NumericalEvidence {
    pub greedy_applicability: Option<GreedyApplicability>,
    pub greedy_identity: Option<GreedyIdentityEvidence>,
    pub oracle_generator_sha: Option<String>,
    pub scaffold_version: Option<String>,
    pub production_backend_version: Option<String>,
    pub frozen_contract_version: Option<String>,
    pub frozen_contract_versions: BTreeMap<String, String>,
    pub bit_mismatch_count: Option<u64>,
    pub max_abs_error: Option<f64>,
    pub relative_error: Option<f64>,
    pub rmse: Option<f64>,
    pub cosine_similarity: Option<f64>,
    pub deterministic_repeat_count: Option<u64>,
    pub first_divergence: Option<serde_json::Value>,
    #[serde(default)]
    pub repeat_integrity: RepeatIntegrityEvidence,
    #[serde(default)]
    pub oracle_ordering: OracleOrderingEvidence,
    #[serde(default)]
    pub expert_repeat_integrity: ExpertRepeatIntegrityEvidence,
    #[serde(default)]
    pub expert_payload_sha256: BTreeMap<String, String>,
    #[serde(default)]
    pub expert_decoded_sha256: BTreeMap<String, String>,
    #[serde(default)]
    pub expert_reference_sha256: BTreeMap<String, String>,
    #[serde(default)]
    pub expert_bound_sha256: BTreeMap<String, String>,
    #[serde(default)]
    pub expert_stage_metrics: BTreeMap<String, ExpertStageMetricsEvidence>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct ExpertStageMetricsEvidence {
    pub bit_mismatch_count: u64,
    pub signed_zero_mismatch_count: u64,
    pub max_abs_error: f64,
    pub rmse: f64,
    pub cosine_similarity: Option<f64>,
    pub passed: bool,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
pub struct RepeatIntegrityEvidence {
    pub repeat_count_required: u64,
    pub repeat_count_observed: u64,
    pub outputs: Vec<RepeatOutputEvidence>,
    pub all_repeat_hashes_equal: bool,
    pub selected_output_sha256: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RepeatOutputEvidence {
    pub ordinal: u64,
    pub output_sha256: String,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
pub struct OracleOrderingEvidence {
    pub oracle_package_sha256: Option<String>,
    pub oracle_completed_at: Option<String>,
    pub oracle_completion_marker: Option<String>,
    pub oracle_validated_before_candidate: bool,
    pub candidate_started_at: Option<String>,
    pub candidate_start_marker: Option<String>,
    pub structural_order_valid: bool,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
pub struct ExpertRepeatIntegrityEvidence {
    pub repeat_count_required: u64,
    pub repeat_count_observed: u64,
    pub native_dispatch_count_expected: u64,
    pub conceptual_expert_count: u64,
    pub outputs: Vec<ExpertRepeatOutputEvidence>,
    pub gate_all_equal: bool,
    pub up_all_equal: bool,
    pub activated_hidden_all_equal: bool,
    pub final_output_all_equal: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ExpertRepeatOutputEvidence {
    pub ordinal: u64,
    pub gate_sha256: String,
    pub up_sha256: String,
    pub activated_hidden_sha256: String,
    pub final_output_sha256: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct LayerEvidence {
    pub layer: u32,
    pub total_seconds: f64,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
pub struct StorageEvidence {
    pub read_bytes: u64,
    pub read_count: u64,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
pub struct DispatchEvidence {
    pub native: u64,
    pub direct: u64,
    pub qualification_scaffold: u64,
    pub explicit_reference: u64,
    pub fallback: u64,
    pub errors: u64,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
pub struct ResidencyEvidence {
    pub compressed: u64,
    pub decoded_hot: u64,
    pub native_ready_hot: u64,
    pub transient: u64,
    pub protected_shared: u64,
    pub hits: u64,
    pub misses: u64,
    pub evictions: u64,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
pub struct LifecycleEvidence {
    pub pre: LifecycleCounters,
    pub post: LifecycleCounters,
    pub reconciled: bool,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
pub struct LifecycleCounters {
    pub managed_created: u64,
    pub managed_destroyed: u64,
    pub derived_created: u64,
    pub derived_destroyed: u64,
    pub callback_count: u64,
    pub default_cpu_stream_created: u64,
    pub default_cpu_stream_freed: u64,
    pub default_gpu_stream_created: u64,
    pub default_gpu_stream_freed: u64,
    pub owned_stream_created: u64,
    pub owned_stream_freed: u64,
    pub active_contexts: u64,
    pub singleton_claimed: bool,
    pub active_registrations: ObservedCounter,
    pub pending_registration_destructions: ObservedCounter,
    pub in_flight_work: ObservedCounter,
    pub live_owner_tokens: ObservedCounter,
    pub stale_generations: ObservedCounter,
}

#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ObservationStatus {
    MeasuredZero,
    MeasuredNonzero,
    NotApplicable,
    #[default]
    Unavailable,
}

#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize, PartialEq, Eq)]
pub struct ObservedCounter {
    pub status: ObservationStatus,
    pub value: Option<u64>,
}

impl ObservedCounter {
    pub const fn measured(value: u64) -> Self {
        Self {
            status: if value == 0 {
                ObservationStatus::MeasuredZero
            } else {
                ObservationStatus::MeasuredNonzero
            },
            value: Some(value),
        }
    }

    pub const fn not_applicable() -> Self {
        Self {
            status: ObservationStatus::NotApplicable,
            value: None,
        }
    }

    fn valid(self) -> bool {
        matches!(
            (self.status, self.value),
            (ObservationStatus::MeasuredZero, Some(0))
                | (ObservationStatus::MeasuredNonzero, Some(1..))
                | (
                    ObservationStatus::NotApplicable | ObservationStatus::Unavailable,
                    None
                )
        )
    }

    fn pass_zero_or_not_applicable(self) -> bool {
        matches!(
            (self.status, self.value),
            (ObservationStatus::MeasuredZero, Some(0)) | (ObservationStatus::NotApplicable, None)
        )
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ResultEvidence {
    pub classification: ResultClassification,
    pub first_failure: Option<FailureRecord>,
    pub stop_reason: Option<String>,
    pub completed: bool,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ResultClassification {
    Pass,
    FailAdmissionEnvironment,
    FailCheckpointIdentity,
    FailLifecycleOwnership,
    FailNumericalBehavioral,
    FailInfrastructureEvidence,
    Cancelled,
    Incomplete,
}

impl ResultClassification {
    fn requires_success_invariants(self) -> bool {
        matches!(self, Self::Pass | Self::Incomplete)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct FailureRecord {
    pub code: String,
    pub message: String,
}

impl Evidence {
    pub fn initial(config: &Config, environment_manifest_sha256: String) -> Self {
        let mut platform = BTreeMap::new();
        platform.insert("architecture".to_owned(), std::env::consts::ARCH.to_owned());
        platform.insert("os".to_owned(), std::env::consts::OS.to_owned());
        let mut toolchain = BTreeMap::new();
        toolchain.insert(
            "rust_package".to_owned(),
            env!("CARGO_PKG_VERSION").to_owned(),
        );
        Self::initial_with_identity(
            config,
            environment_manifest_sha256,
            "checkpoint_free_fixture",
            platform,
            toolchain,
        )
    }

    pub fn initial_with_environment(config: &Config, environment: &ValidatedEnvironment) -> Self {
        let platform = environment.public_platform();
        let mut toolchain = environment.public_toolchain();
        toolchain.insert(
            "rust_package".to_owned(),
            env!("CARGO_PKG_VERSION").to_owned(),
        );
        Self::initial_with_identity(
            config,
            environment.manifest_sha256.clone(),
            if environment.production {
                "production_reviewed"
            } else {
                "checkpoint_free_fixture"
            },
            platform,
            toolchain,
        )
    }

    fn initial_with_identity(
        config: &Config,
        environment_manifest_sha256: String,
        environment_kind: &str,
        platform: BTreeMap<String, String>,
        toolchain: BTreeMap<String, String>,
    ) -> Self {
        Self {
            schema: EVIDENCE_SCHEMA.to_owned(),
            schema_version: EVIDENCE_SCHEMA_VERSION.to_owned(),
            identity: IdentityEvidence {
                source_sha: env!("PULSARMLX_SOURCE_SHA").to_owned(),
                compiled_runtime_sha: None,
                tooling_sha: None,
                authorization_head_sha: None,
                source_clean: source_worktree_clean(),
                runner_version: env!("CARGO_PKG_VERSION").to_owned(),
                environment_kind: environment_kind.to_owned(),
                environment_manifest_sha256,
                platform,
                toolchain,
                loaded_libraries: Vec::new(),
                checkpoint: CheckpointEvidence {
                    accessed: false,
                    revision: None,
                    checkpoint_set_sha256: None,
                    catalog_sha256: None,
                    architecture: None,
                    tokenizer_identity: None,
                    tensor_count: None,
                    tensor_map: TensorMapEvidence::default(),
                    shards: Vec::new(),
                },
                prior_evidence: BTreeMap::new(),
                artifact_paths: Vec::new(),
                execution_config_sha256: config
                    .execution_config
                    .as_ref()
                    .map(|binding| binding.sha256.clone()),
            },
            admission: AdmissionEvidence {
                telemetry_source: "unavailable".to_owned(),
                physical_memory_bytes: 0,
                memory_floor_bytes: config.memory_floor_bytes,
                available_memory_bytes: 0,
                compressed_memory_bytes: 0,
                memory_pressure: "unknown".to_owned(),
                swap_used_bytes: 0,
                checkpoint_volume_free_bytes: None,
                evidence_volume_free_bytes: 0,
                load_averages: [0.0; 3],
                competing_processes_clear: false,
                competing_processes: Vec::new(),
                port_1234_listener: false,
                thermal_state: "unavailable".to_owned(),
                performance_warning: false,
                stream_mode: config.stream_mode.as_str().to_owned(),
                singleton_initially_unclaimed: false,
            },
            input: InputEvidence {
                tokens: config.tokens.clone(),
                n_new: config.n_new,
                expected_token: config.expected_token,
                validation_mode: config.validation_mode.as_str().to_owned(),
                mode: config.mode.as_str().to_owned(),
                numerical_mode: config.numerical_mode.map(|mode| mode.as_str().to_owned()),
            },
            execution: ExecutionEvidence {
                layers: Vec::new(),
                timings: BTreeMap::new(),
                storage: StorageEvidence::default(),
                dispatch: DispatchEvidence::default(),
                generated_token: None,
                numerical_classification: None,
                numerical: NumericalEvidence::default(),
                progress_state: "initialized".to_owned(),
                attempt_state: "not_applicable".to_owned(),
                attempt_consumed: false,
                projection_count: 0,
                quant_decode_count: 0,
                expert_execution_count: 0,
                layer_execution_count: 0,
                logits_count: 0,
                p1: false,
                p2: false,
                golden_eight: false,
                feature_018: false,
            },
            residency: ResidencyEvidence::default(),
            lifecycle: LifecycleEvidence::default(),
            result: ResultEvidence {
                classification: ResultClassification::Incomplete,
                first_failure: None,
                stop_reason: None,
                completed: false,
            },
        }
    }

    pub fn validate(&self) -> Result<(), RunnerError> {
        if self.schema != EVIDENCE_SCHEMA || self.schema_version != EVIDENCE_SCHEMA_VERSION {
            return Err(evidence_error(
                "evidence_schema",
                "evidence schema identity differs",
            ));
        }
        if !(40..=64).contains(&self.identity.source_sha.len())
            || !self
                .identity
                .source_sha
                .bytes()
                .all(|byte| byte.is_ascii_hexdigit())
            || self.identity.environment_manifest_sha256.len() != 64
            || !self
                .identity
                .environment_manifest_sha256
                .bytes()
                .all(|byte| byte.is_ascii_hexdigit())
        {
            return Err(evidence_error(
                "evidence_identity",
                "evidence source or environment identity is malformed",
            ));
        }
        if self.admission.memory_floor_bytes == 0 || self.execution.progress_state.is_empty() {
            return Err(evidence_error(
                "evidence_required_field",
                "required evidence fields are empty",
            ));
        }
        for counters in [&self.lifecycle.pre, &self.lifecycle.post] {
            for counter in [
                counters.active_registrations,
                counters.pending_registration_destructions,
                counters.in_flight_work,
                counters.live_owner_tokens,
                counters.stale_generations,
            ] {
                if !counter.valid() {
                    return Err(evidence_error(
                        "lifecycle_observation",
                        "lifecycle observation status/value is inconsistent",
                    ));
                }
            }
        }
        match (
            self.execution.numerical_classification,
            self.execution.numerical.greedy_applicability,
        ) {
            (Some(classification), Some(applicability)) => {
                validate_classification_applicability(
                    classification,
                    applicability,
                    self.execution.numerical.greedy_identity.as_ref(),
                )
                .map_err(|message| evidence_error("numerical_classification", message))?;
            }
            (None, None) if self.execution.numerical.greedy_identity.is_none() => {}
            _ => {
                return Err(evidence_error(
                    "numerical_classification",
                    "classification, applicability, and identity evidence are inconsistent",
                ));
            }
        }
        if self.execution.numerical_classification
            == Some(NumericalClassification::NumericallyQualifiedGreedyDivergent)
            && self.input.validation_mode == "golden_strict"
            && self.result.classification != ResultClassification::FailNumericalBehavioral
        {
            return Err(evidence_error(
                "numerical_classification",
                "golden-strict greedy divergence must be a numerical/behavioral failure",
            ));
        }
        if self.input.mode == "fixture"
            && self.input.numerical_mode.as_deref() == Some("production_mlx_tier_b")
            && self.execution.progress_state == "r12_tiny_model_complete"
        {
            if self.execution.numerical.frozen_contract_versions != r12_contract_bindings() {
                return Err(evidence_error(
                    "r12_contract_bindings",
                    "production R12 evidence must bind the complete inherited contract set",
                ));
            }
        }
        if matches!(
            self.input.mode.as_str(),
            "fixture_projection" | "real_projection"
        ) {
            let expected_prior = BTreeMap::from([
                (
                    "m1_a".to_owned(),
                    "aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805".to_owned(),
                ),
                (
                    "m1_b".to_owned(),
                    "9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770".to_owned(),
                ),
                (
                    "m1_c".to_owned(),
                    "343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e".to_owned(),
                ),
            ]);
            if self.execution.progress_state == "m1d_one_projection_complete"
                && self.result.classification.requires_success_invariants()
                && (self.identity.prior_evidence != expected_prior
                    || !valid_m1d_artifact_paths(
                        &self.identity.artifact_paths,
                        &self.identity.source_sha,
                    )
                    || self.execution.projection_count != 1
                    || self.execution.quant_decode_count != 1
                    || self.execution.expert_execution_count != 0
                    || self.execution.layer_execution_count != 0
                    || self.execution.logits_count != 0
                    || self.execution.p1
                    || self.execution.numerical.greedy_applicability
                        != Some(GreedyApplicability::NotApplicable)
                    || self.execution.numerical_classification
                        != Some(NumericalClassification::NumericallyQualifiedGreedyNotApplicable)
                    || validate_m1d_repeat_integrity(
                        &self.execution.numerical.repeat_integrity,
                        self.execution.dispatch.native,
                    )
                    .is_err()
                    || validate_m1d_oracle_ordering(&self.execution.numerical.oracle_ordering)
                        .is_err())
            {
                return Err(evidence_error(
                    "m1d_isolation",
                    "M1-D PASS requires exactly one projection/decode and no expert/layer/logits/P1 execution",
                ));
            }
        }
        if matches!(self.input.mode.as_str(), "fixture_expert" | "real_expert")
            && self.execution.progress_state == "m1e_one_expert_complete"
            && self.result.classification.requires_success_invariants()
            && (self.identity.prior_evidence
                != BTreeMap::from([
                    (
                        "m1_a".into(),
                        "aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805".into(),
                    ),
                    (
                        "m1_b".into(),
                        "9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770".into(),
                    ),
                    (
                        "m1_c".into(),
                        "343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e".into(),
                    ),
                    (
                        "m1_d".into(),
                        "dc5c4900da0cb0c2d293108a4abbdeccccd3c23899db265a84f73fda24ada53c".into(),
                    ),
                    (
                        "m1_e_attempt_1".into(),
                        "346d6302648d463738b0ee0f7fc04a34f664675cccb60a181e3393b88b02b119".into(),
                    ),
                    (
                        "m1_e_attempt_2".into(),
                        "8912e523963cfa8822fe6472ec30be31a78c4c3648fba34caf6c41055efd7e00".into(),
                    ),
                ])
                || self.identity.compiled_runtime_sha.as_deref()
                    != Some(self.identity.source_sha.as_str())
                || self.identity.tooling_sha.as_deref().is_none()
                || self.identity.authorization_head_sha.as_deref().is_none()
                || !valid_m1e_artifact_paths(
                    &self.identity.artifact_paths,
                    self.identity
                        .authorization_head_sha
                        .as_deref()
                        .unwrap_or(""),
                )
                || self.execution.projection_count != 3
                || self.execution.quant_decode_count != 3
                || self.execution.expert_execution_count != 1
                || self.execution.layer_execution_count != 0
                || self.execution.logits_count != 0
                || self.execution.p1
                || self.execution.p2
                || self.execution.golden_eight
                || self.execution.feature_018
                || self.execution.dispatch.native != 30
                || !self.execution.attempt_consumed
                || self.execution.attempt_state != "execution_started"
                || self.execution.numerical.expert_payload_sha256.len() != 3
                || self.execution.numerical.expert_decoded_sha256.len() != 3
                || self.execution.numerical.expert_reference_sha256.len() != 4
                || self.execution.numerical.expert_bound_sha256.len() != 4
                || self.execution.numerical.expert_stage_metrics.len() != 4
                || self
                    .execution
                    .numerical
                    .expert_stage_metrics
                    .values()
                    .any(|metrics| !metrics.passed)
                || !valid_m1e_timings(&self.execution.timings)
                || self.execution.numerical.greedy_applicability
                    != Some(GreedyApplicability::NotApplicable)
                || self.execution.numerical_classification
                    != Some(NumericalClassification::NumericallyQualifiedGreedyNotApplicable)
                || validate_m1e_repeat_integrity(&self.execution.numerical.expert_repeat_integrity)
                    .is_err()
                || validate_m1e_oracle_ordering(&self.execution.numerical.oracle_ordering).is_err())
        {
            return Err(evidence_error(
                "m1e_isolation",
                "M1-E PASS requires one expert, three bounded tensors, thirty native dispatches, ten equal stage hashes, and no layer/logits/P1",
            ));
        }
        Ok(())
    }

    pub fn validate_success_ready(&self) -> Result<(), RunnerError> {
        self.validate()?;
        if !self.lifecycle.reconciled
            || self.lifecycle.post.managed_created != self.lifecycle.post.managed_destroyed
            || self.lifecycle.post.derived_created != self.lifecycle.post.derived_destroyed
            || self.lifecycle.post.callback_count != self.lifecycle.post.managed_created
            || self.lifecycle.post.default_cpu_stream_created
                != self.lifecycle.post.default_cpu_stream_freed
            || self.lifecycle.post.default_gpu_stream_created
                != self.lifecycle.post.default_gpu_stream_freed
            || self.lifecycle.post.owned_stream_created != self.lifecycle.post.owned_stream_freed
            || self.lifecycle.post.active_contexts != 0
            || self.lifecycle.post.singleton_claimed
            || !self
                .lifecycle
                .post
                .active_registrations
                .pass_zero_or_not_applicable()
            || !self
                .lifecycle
                .post
                .pending_registration_destructions
                .pass_zero_or_not_applicable()
            || !self
                .lifecycle
                .post
                .in_flight_work
                .pass_zero_or_not_applicable()
            || !self
                .lifecycle
                .post
                .live_owner_tokens
                .pass_zero_or_not_applicable()
            || !self
                .lifecycle
                .post
                .stale_generations
                .pass_zero_or_not_applicable()
            || self.execution.dispatch.fallback != 0
            || self.execution.dispatch.errors != 0
        {
            return Err(lifecycle_error(
                "pass_reconciliation",
                "PASS requires fully reconciled lifecycle and dispatch state",
            ));
        }
        let production_execution = self.input.mode == "adapter_preflight"
            || self.input.mode == "p1"
            || self.input.mode == "real_projection"
            || self.input.mode == "fixture_projection"
            || self.input.mode == "real_expert"
            || self.input.mode == "fixture_expert"
            || (self.input.mode == "fixture"
                && self.input.numerical_mode.as_deref() == Some("production_mlx_tier_b"));
        if production_execution
            && (self.execution.dispatch.qualification_scaffold != 0
                || self.execution.dispatch.explicit_reference != 0)
        {
            return Err(evidence_error(
                "pass_production_dispatch",
                "production PASS forbids scaffold/reference dispatch",
            ));
        }
        let environment_policy = mode_environment_policy(&self.input.mode).ok_or_else(|| {
            evidence_error(
                "pass_environment_policy",
                "PASS evidence has an unknown runner mode",
            )
        })?;
        if environment_policy == EnvironmentPolicy::ProductionReviewed {
            if self.identity.environment_kind != "production_reviewed" {
                return Err(evidence_error(
                    "pass_environment_kind",
                    "production stage PASS requires the reviewed production environment",
                ));
            }
            if !self.identity.source_clean
                || self.admission.telemetry_source != "measured_host"
                || self.admission.available_memory_bytes < self.admission.memory_floor_bytes
                || !self.admission.competing_processes_clear
                || self.admission.port_1234_listener
                || !loaded_libraries_verified(&self.identity.loaded_libraries)
            {
                return Err(evidence_error(
                    "pass_admission",
                    "production PASS requires admitted measured host and loaded-library identity",
                ));
            }
        } else if environment_policy == EnvironmentPolicy::CheckpointFreeFixture
            && self.identity.environment_kind != "checkpoint_free_fixture"
        {
            return Err(evidence_error(
                "pass_environment_kind",
                "fixture identity PASS requires the checkpoint-free fixture environment",
            ));
        }
        if self.input.mode == "checkpoint_identity"
            && (self.identity.checkpoint.tensor_map.status != TensorMapStatus::Validated
                || self.identity.checkpoint.tensor_map.validated_tensor_count != Some(1_809))
        {
            return Err(evidence_error(
                "pass_tensor_map",
                "production identity PASS requires the complete GLM52 tensor map",
            ));
        }
        Ok(())
    }
}

fn valid_m1e_artifact_paths(paths: &[ArtifactPathEvidence], source_sha: &str) -> bool {
    let expected = BTreeMap::from([
        (
            "attempt_3_handoff",
            "docs/architecture/reviews/f017-m1-e-attempt-3-handoff.md",
        ),
        (
            "activation_fixture",
            "specs/017-rust-native-inference-runtime/fixtures/f017-m1e-activation-v1.json",
        ),
        (
            "activation_generator",
            "scripts/research/generate_f017_m1e_activation.py",
        ),
        (
            "authorized_launcher",
            "scripts/research/run_f017_m1e_authorized.py",
        ),
        (
            "execution_config_preparer",
            "scripts/research/prepare_f017_m1e_execution.py",
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
            "evidence_schema",
            "specs/017-rust-native-inference-runtime/contracts/m1e-evidence-v1.schema.json",
        ),
        (
            "execution_config_schema",
            "specs/017-rust-native-inference-runtime/contracts/m1e-execution-config-v3.schema.json",
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
        (
            "path_resolution_contract",
            "specs/017-rust-native-inference-runtime/contracts/m1d-artifact-path-resolution-v1.json",
        ),
        (
            "preparer_input_contract",
            "specs/017-rust-native-inference-runtime/contracts/m1e-real-reference-preparer-input-v3.json",
        ),
        (
            "trusted_repository_identity_contract",
            "specs/017-rust-native-inference-runtime/contracts/trusted-repository-identity-v2.json",
        ),
        (
            "real_reference_preparer",
            "scripts/research/prepare_f017_m1e_real_reference.py",
        ),
        (
            "repeat_integrity_contract",
            "specs/017-rust-native-inference-runtime/contracts/m1e-repeat-integrity-v1.json",
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
            "timing_contract",
            "specs/017-rust-native-inference-runtime/contracts/m1e-timing-v1.json",
        ),
    ]);
    if paths.len() != expected.len() {
        return false;
    }
    paths.iter().all(|path| {
        expected.get(path.logical_role.as_str()).copied() == Some(path.symbolic_path.as_str())
            && path.path_kind == "repository_relative"
            && path.repository_identity.as_deref() == Some(source_sha)
            && path.package_artifact_id.is_none()
            && path.content_sha256.len() == 64
            && path
                .content_sha256
                .bytes()
                .all(|byte| byte.is_ascii_hexdigit())
    })
}

fn valid_m1e_timings(timings: &BTreeMap<String, f64>) -> bool {
    let required = [
        "storage_seconds",
        "decoder_gate_seconds",
        "decoder_up_seconds",
        "decoder_down_seconds",
        "oracle_gate_seconds",
        "oracle_up_seconds",
        "oracle_activation_seconds",
        "oracle_down_seconds",
        "production_import_seconds",
        "production_gate_compute_sync_readback_seconds",
        "production_up_compute_sync_readback_seconds",
        "production_activation_orchestration_seconds",
        "production_down_compute_sync_readback_seconds",
        "teardown_seconds",
        "total_wall_seconds",
    ];
    required.iter().all(|name| {
        timings
            .get(*name)
            .is_some_and(|value| value.is_finite() && *value >= 0.0)
    })
}

fn valid_m1d_artifact_paths(paths: &[ArtifactPathEvidence], source_sha: &str) -> bool {
    let repository_roles = [
        "path_resolution_contract",
        "boundary_contract",
        "decoder_contract",
        "scaffold_contract",
        "tier_b_contract",
    ];
    let repositories_ok = repository_roles.iter().all(|role| {
        paths.iter().any(|entry| {
            entry.logical_role == *role
                && entry.path_kind == "repository_relative"
                && entry.repository_identity.as_deref() == Some(source_sha)
                && entry.package_artifact_id.is_none()
                && is_sha256(&entry.content_sha256)
                && safe_symbolic_path(&entry.symbolic_path)
        })
    });
    let package_ok = paths.iter().any(|entry| {
        entry.logical_role == "independent_oracle"
            && entry.path_kind == "package_relative"
            && entry.repository_identity.is_none()
            && entry
                .package_artifact_id
                .as_deref()
                .is_some_and(|id| !id.is_empty())
            && is_sha256(&entry.content_sha256)
            && safe_symbolic_path(&entry.symbolic_path)
    });
    repositories_ok && package_ok && paths.len() == repository_roles.len() + 1
}

fn safe_symbolic_path(path: &str) -> bool {
    let path = std::path::Path::new(path);
    !path.as_os_str().is_empty()
        && !path.is_absolute()
        && path
            .components()
            .all(|component| matches!(component, std::path::Component::Normal(_)))
}

fn is_sha256(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn validate_m1d_repeat_integrity(
    repeats: &RepeatIntegrityEvidence,
    native_dispatches: u64,
) -> Result<(), RunnerError> {
    let expected_ordinals = 0_u64..10;
    let hashes = repeats
        .outputs
        .iter()
        .map(|entry| entry.output_sha256.as_str())
        .collect::<Vec<_>>();
    if repeats.repeat_count_required != 10
        || repeats.repeat_count_observed != 10
        || native_dispatches != 10
        || repeats.outputs.len() != 10
        || !repeats
            .outputs
            .iter()
            .zip(expected_ordinals)
            .all(|(entry, ordinal)| entry.ordinal == ordinal && valid_sha256(&entry.output_sha256))
        || !repeats.all_repeat_hashes_equal
        || hashes.first().is_none()
        || !hashes.iter().all(|hash| Some(hash) == hashes.first())
        || repeats.selected_output_sha256.as_deref() != hashes.last().copied()
    {
        return Err(evidence_error(
            "m1d_repeat_integrity",
            "M1-D PASS requires exactly ten ordinal native outputs with identical hashes",
        ));
    }
    Ok(())
}

fn validate_m1d_oracle_ordering(ordering: &OracleOrderingEvidence) -> Result<(), RunnerError> {
    let oracle_completed = ordering
        .oracle_completed_at
        .as_deref()
        .and_then(|value| value.parse::<u128>().ok());
    let candidate_started = ordering
        .candidate_started_at
        .as_deref()
        .and_then(|value| value.parse::<u128>().ok());
    if !ordering
        .oracle_package_sha256
        .as_deref()
        .is_some_and(valid_sha256)
        || ordering.oracle_completion_marker.as_deref() != Some("oracle_finalized_sequence_0")
        || ordering.candidate_start_marker.as_deref() != Some("candidate_started_sequence_1")
        || !ordering.oracle_validated_before_candidate
        || !ordering.structural_order_valid
        || !matches!((oracle_completed, candidate_started), (Some(a), Some(b)) if a < b)
    {
        return Err(evidence_error(
            "m1d_oracle_ordering",
            "M1-D PASS requires a finalized oracle package structurally validated before candidate start",
        ));
    }
    Ok(())
}

fn validate_m1e_oracle_ordering(ordering: &OracleOrderingEvidence) -> Result<(), RunnerError> {
    let completed = ordering
        .oracle_completed_at
        .as_deref()
        .and_then(|v| v.parse::<u128>().ok());
    let started = ordering
        .candidate_started_at
        .as_deref()
        .and_then(|v| v.parse::<u128>().ok());
    if !ordering
        .oracle_package_sha256
        .as_deref()
        .is_some_and(valid_sha256)
        || ordering.oracle_completion_marker.as_deref() != Some("oracle_finalized_sequence_0")
        || ordering.candidate_start_marker.as_deref() != Some("candidate_started_sequence_1")
        || !ordering.oracle_validated_before_candidate
        || !ordering.structural_order_valid
        || !matches!((completed, started), (Some(a), Some(b)) if a < b)
    {
        return Err(evidence_error(
            "m1e_oracle_ordering",
            "M1-E oracle must be finalized and structurally validated before candidate start",
        ));
    }
    Ok(())
}

fn validate_m1e_repeat_integrity(value: &ExpertRepeatIntegrityEvidence) -> Result<(), RunnerError> {
    let first = value.outputs.first();
    let hashes_valid = value.outputs.iter().enumerate().all(|(ordinal, entry)| {
        entry.ordinal == ordinal as u64
            && [
                &entry.gate_sha256,
                &entry.up_sha256,
                &entry.activated_hidden_sha256,
                &entry.final_output_sha256,
            ]
            .iter()
            .all(|hash| valid_sha256(hash))
    });
    let equal = |select: fn(&ExpertRepeatOutputEvidence) -> &str| {
        first.is_some_and(|first| {
            value
                .outputs
                .iter()
                .all(|entry| select(entry) == select(first))
        })
    };
    if value.repeat_count_required != 10
        || value.repeat_count_observed != 10
        || value.native_dispatch_count_expected != 30
        || value.conceptual_expert_count != 1
        || value.outputs.len() != 10
        || !hashes_valid
        || !value.gate_all_equal
        || !value.up_all_equal
        || !value.activated_hidden_all_equal
        || !value.final_output_all_equal
        || !equal(|entry| &entry.gate_sha256)
        || !equal(|entry| &entry.up_sha256)
        || !equal(|entry| &entry.activated_hidden_sha256)
        || !equal(|entry| &entry.final_output_sha256)
    {
        return Err(evidence_error(
            "m1e_repeat_integrity",
            "M1-E requires ten bit-identical hashes at every expert stage",
        ));
    }
    Ok(())
}

fn loaded_libraries_verified(libraries: &[LoadedLibraryEvidence]) -> bool {
    if libraries.len() != 2 {
        return false;
    }
    let mut identities = libraries
        .iter()
        .map(|library| {
            (
                library.artifact.as_str(),
                library.resolved_basename.as_str(),
            )
        })
        .collect::<Vec<_>>();
    identities.sort_unstable();
    identities == [("mlx_c", "libmlxc.dylib"), ("mlx_native", "libmlx.dylib")]
        && libraries.iter().all(|library| {
            library.actual_sha256 == library.expected_sha256
                && library.actual_sha256.len() == 64
                && library
                    .actual_sha256
                    .bytes()
                    .all(|byte| byte.is_ascii_hexdigit())
                && library.architecture == "arm64"
        })
}

fn source_worktree_clean() -> bool {
    std::process::Command::new("git")
        .args(["-C", env!("PULSARMLX_SOURCE_ROOT"), "status", "--porcelain"])
        .output()
        .is_ok_and(|output| output.status.success() && output.stdout.is_empty())
}

pub struct AtomicEvidenceWriter {
    target: PathBuf,
    update: u64,
}

impl AtomicEvidenceWriter {
    pub fn create(target: PathBuf, evidence: &Evidence) -> Result<Self, RunnerError> {
        let parent = target.parent().unwrap_or_else(|| std::path::Path::new("."));
        let metadata = fs::symlink_metadata(parent)
            .map_err(|error| evidence_error("evidence_parent", error.to_string()))?;
        if !metadata.is_dir() || metadata.file_type().is_symlink() {
            return Err(evidence_error(
                "evidence_parent",
                "evidence parent must be a real directory",
            ));
        }
        let bytes = serialize(evidence)?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&target)
            .map_err(|error| {
                evidence_error(
                    "evidence_create",
                    format!("cannot create fresh evidence: {error}"),
                )
            })?;
        file.write_all(&bytes)
            .and_then(|_| file.sync_all())
            .map_err(|error| {
                evidence_error(
                    "evidence_write",
                    format!("cannot write initial evidence: {error}"),
                )
            })?;
        Ok(Self { target, update: 0 })
    }

    pub fn update(&mut self, evidence: &Evidence) -> Result<(), RunnerError> {
        let bytes = serialize(evidence)?;
        self.update = self.update.checked_add(1).ok_or_else(|| {
            evidence_error(
                "evidence_update_overflow",
                "evidence update counter overflow",
            )
        })?;
        let name = self
            .target
            .file_name()
            .and_then(|value| value.to_str())
            .ok_or_else(|| evidence_error("evidence_path", "evidence filename must be UTF-8"))?;
        let temporary = self.target.with_file_name(format!(
            ".{name}.{}.{}.tmp",
            std::process::id(),
            self.update
        ));
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temporary)
            .map_err(|error| {
                evidence_error(
                    "evidence_temp_create",
                    format!("cannot create atomic evidence update: {error}"),
                )
            })?;
        if let Err(error) = file.write_all(&bytes).and_then(|_| file.sync_all()) {
            let _ = fs::remove_file(&temporary);
            return Err(evidence_error(
                "evidence_temp_write",
                format!("cannot write atomic evidence update: {error}"),
            ));
        }
        drop(file);
        fs::rename(&temporary, &self.target).map_err(|error| {
            let _ = fs::remove_file(&temporary);
            evidence_error(
                "evidence_rename",
                format!("cannot publish atomic evidence update: {error}"),
            )
        })?;
        Ok(())
    }
}

fn serialize(evidence: &Evidence) -> Result<Vec<u8>, RunnerError> {
    evidence.validate()?;
    let mut bytes = serde_json::to_vec_pretty(evidence)
        .map_err(|error| evidence_error("evidence_serialize", error.to_string()))?;
    bytes.push(b'\n');
    Ok(bytes)
}

fn evidence_error(code: &'static str, message: impl Into<String>) -> RunnerError {
    RunnerError::new(FailureClass::InfrastructureEvidence, code, message)
}

fn lifecycle_error(code: &'static str, message: impl Into<String>) -> RunnerError {
    RunnerError::new(FailureClass::LifecycleOwnership, code, message)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn terminal_failures_can_be_banked_without_reapplying_pass_invariants() {
        assert!(ResultClassification::Pass.requires_success_invariants());
        assert!(ResultClassification::Incomplete.requires_success_invariants());
        for classification in [
            ResultClassification::FailAdmissionEnvironment,
            ResultClassification::FailCheckpointIdentity,
            ResultClassification::FailLifecycleOwnership,
            ResultClassification::FailNumericalBehavioral,
            ResultClassification::FailInfrastructureEvidence,
            ResultClassification::Cancelled,
        ] {
            assert!(!classification.requires_success_invariants());
        }
    }
    use crate::cli::{Config, RunnerMode, StreamMode, ValidationMode};
    use crate::json::parse_json_no_duplicates;
    use std::sync::{Arc, Barrier};
    use std::thread;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn config(out: PathBuf) -> Config {
        Config {
            out,
            validation_mode: ValidationMode::GoldenStrict,
            stream_mode: StreamMode::OwnedDevice,
            memory_floor_bytes: 1,
            environment_manifest: PathBuf::from("environment.json"),
            repository_root: None,
            checkpoint_manifest: None,
            tokens: Vec::new(),
            n_new: 0,
            expected_token: None,
            numerical_mode: None,
            mode: RunnerMode::DryRun,
            execution_config: None,
        }
    }

    #[test]
    fn evidence_round_trips_and_atomic_writer_refuses_overwrite() {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "f017-evidence-{}-{suffix}.json",
            std::process::id()
        ));
        let evidence = Evidence::initial(&config(path.clone()), "a".repeat(64));
        let mut writer = AtomicEvidenceWriter::create(path.clone(), &evidence).unwrap();
        assert!(AtomicEvidenceWriter::create(path.clone(), &evidence).is_err());
        writer.update(&evidence).unwrap();
        let bytes = fs::read(&path).unwrap();
        let parsed: Evidence = parse_json_no_duplicates(&bytes).unwrap();
        assert_eq!(parsed, evidence);
        fs::remove_file(path).unwrap();
    }

    fn classified_evidence(
        classification: NumericalClassification,
        applicability: GreedyApplicability,
        identity: Option<GreedyIdentityEvidence>,
    ) -> Evidence {
        let mut evidence = Evidence::initial(&config(PathBuf::from("unused.json")), "a".repeat(64));
        evidence.execution.numerical_classification = Some(classification);
        evidence.execution.numerical.greedy_applicability = Some(applicability);
        evidence.execution.numerical.greedy_identity = identity;
        evidence
    }

    #[test]
    fn evidence_rejects_non_applicable_greedy_identical() {
        let evidence = classified_evidence(
            NumericalClassification::NumericallyQualifiedGreedyIdentical,
            GreedyApplicability::NotApplicable,
            None,
        );
        assert!(evidence.validate().is_err());
    }

    #[test]
    fn evidence_rejects_applicable_greedy_identical_without_identity() {
        let evidence = classified_evidence(
            NumericalClassification::NumericallyQualifiedGreedyIdentical,
            GreedyApplicability::Applicable,
            None,
        );
        assert!(evidence.validate().is_err());
    }

    #[test]
    fn evidence_accepts_non_applicable_numerical_qualification() {
        let evidence = classified_evidence(
            NumericalClassification::NumericallyQualifiedGreedyNotApplicable,
            GreedyApplicability::NotApplicable,
            None,
        );
        assert!(evidence.validate().is_ok());
    }

    #[test]
    fn evidence_accepts_applicable_exact_greedy_identity() {
        let evidence = classified_evidence(
            NumericalClassification::NumericallyQualifiedGreedyIdentical,
            GreedyApplicability::Applicable,
            Some(GreedyIdentityEvidence {
                top_k_ids_exact: true,
                argmax_exact: true,
            }),
        );
        assert!(evidence.validate().is_ok());
    }

    #[test]
    fn evidence_rejects_changed_greedy_choice_as_not_applicable() {
        let evidence = classified_evidence(
            NumericalClassification::NumericallyQualifiedGreedyNotApplicable,
            GreedyApplicability::Applicable,
            Some(GreedyIdentityEvidence {
                top_k_ids_exact: false,
                argmax_exact: false,
            }),
        );
        assert!(evidence.validate().is_err());

        let mut divergent = classified_evidence(
            NumericalClassification::NumericallyQualifiedGreedyDivergent,
            GreedyApplicability::Applicable,
            Some(GreedyIdentityEvidence {
                top_k_ids_exact: false,
                argmax_exact: false,
            }),
        );
        assert!(divergent.validate().is_err());
        divergent.result.classification = ResultClassification::FailNumericalBehavioral;
        assert!(divergent.validate().is_ok());
    }

    #[test]
    fn exclusive_create_has_one_winner_under_race() {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "f017-evidence-race-{}-{suffix}.json",
            std::process::id()
        ));
        let evidence = Arc::new(Evidence::initial(&config(path.clone()), "a".repeat(64)));
        let barrier = Arc::new(Barrier::new(3));
        let handles = (0..2)
            .map(|_| {
                let path = path.clone();
                let evidence = Arc::clone(&evidence);
                let barrier = Arc::clone(&barrier);
                thread::spawn(move || {
                    barrier.wait();
                    AtomicEvidenceWriter::create(path, &evidence).is_ok()
                })
            })
            .collect::<Vec<_>>();
        barrier.wait();
        assert_eq!(
            handles
                .into_iter()
                .map(|handle| handle.join().unwrap())
                .filter(|won| *won)
                .count(),
            1
        );
        fs::remove_file(path).unwrap();
    }

    #[test]
    fn exclusive_create_rejects_non_directory_parent_and_symlink_target() {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let parent = std::env::temp_dir().join(format!(
            "f017-evidence-parent-{}-{suffix}",
            std::process::id()
        ));
        fs::write(&parent, b"not a directory").unwrap();
        let target = parent.join("evidence.json");
        let evidence = Evidence::initial(&config(target.clone()), "a".repeat(64));
        assert!(AtomicEvidenceWriter::create(target, &evidence).is_err());
        fs::remove_file(parent).unwrap();

        #[cfg(unix)]
        {
            use std::os::unix::fs::symlink;
            let real = std::env::temp_dir().join(format!(
                "f017-evidence-real-{}-{suffix}.json",
                std::process::id()
            ));
            let link = std::env::temp_dir().join(format!(
                "f017-evidence-link-{}-{suffix}.json",
                std::process::id()
            ));
            fs::write(&real, b"preserve").unwrap();
            symlink(&real, &link).unwrap();
            let evidence = Evidence::initial(&config(link.clone()), "a".repeat(64));
            assert!(AtomicEvidenceWriter::create(link.clone(), &evidence).is_err());
            assert_eq!(fs::read(&real).unwrap(), b"preserve");
            fs::remove_file(link).unwrap();
            fs::remove_file(real).unwrap();
        }
    }

    #[test]
    fn interrupted_temporary_update_cannot_replace_acquired_target() {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "f017-evidence-interrupted-{}-{suffix}.json",
            std::process::id()
        ));
        let evidence = Evidence::initial(&config(path.clone()), "a".repeat(64));
        let before = serialize(&evidence).unwrap();
        let mut writer = AtomicEvidenceWriter::create(path.clone(), &evidence).unwrap();
        let name = path.file_name().unwrap().to_str().unwrap();
        let interrupted = path.with_file_name(format!(".{name}.{}.1.tmp", std::process::id()));
        fs::write(&interrupted, b"incomplete").unwrap();
        assert!(writer.update(&evidence).is_err());
        assert_eq!(fs::read(&path).unwrap(), before);
        fs::remove_file(interrupted).unwrap();
        fs::remove_file(path).unwrap();
    }

    fn success_ready(mode: &str) -> Evidence {
        let mut evidence = Evidence::initial(&config(PathBuf::from("unused.json")), "a".repeat(64));
        evidence.input.mode = mode.to_owned();
        evidence.lifecycle.reconciled = true;
        for counters in [&mut evidence.lifecycle.pre, &mut evidence.lifecycle.post] {
            counters.active_registrations = ObservedCounter::not_applicable();
            counters.pending_registration_destructions = ObservedCounter::not_applicable();
            counters.in_flight_work = ObservedCounter::not_applicable();
            counters.live_owner_tokens = ObservedCounter::not_applicable();
            counters.stale_generations = ObservedCounter::not_applicable();
        }
        evidence
    }

    fn production_success_ready(mode: &str) -> Evidence {
        let mut evidence = success_ready(mode);
        evidence.identity.source_clean = true;
        evidence.identity.environment_kind = "production_reviewed".to_owned();
        evidence.admission.telemetry_source = "measured_host".to_owned();
        evidence.admission.physical_memory_bytes = 128;
        evidence.admission.available_memory_bytes = evidence.admission.memory_floor_bytes;
        evidence.admission.memory_pressure = "normal".to_owned();
        evidence.admission.evidence_volume_free_bytes = 16 * 1024 * 1024;
        evidence.admission.competing_processes_clear = true;
        evidence.identity.loaded_libraries = vec![
            LoadedLibraryEvidence {
                artifact: "mlx_native".to_owned(),
                resolved_basename: "libmlx.dylib".to_owned(),
                actual_sha256: "1".repeat(64),
                expected_sha256: "1".repeat(64),
                architecture: "arm64".to_owned(),
            },
            LoadedLibraryEvidence {
                artifact: "mlx_c".to_owned(),
                resolved_basename: "libmlxc.dylib".to_owned(),
                actual_sha256: "2".repeat(64),
                expected_sha256: "2".repeat(64),
                architecture: "arm64".to_owned(),
            },
        ];
        evidence.execution.dispatch.native = 1;
        evidence
    }

    #[test]
    fn pass_validation_rejects_every_unreconciled_domain() {
        let baseline = success_ready("dry_run");
        assert!(baseline.validate_success_ready().is_ok());
        let mut cases = Vec::new();
        let mut value = baseline.clone();
        value.lifecycle.post.managed_created = 1;
        cases.push(value);
        let mut value = baseline.clone();
        value.lifecycle.post.derived_created = 1;
        cases.push(value);
        let mut value = baseline.clone();
        value.lifecycle.post.callback_count = 1;
        cases.push(value);
        let mut value = baseline.clone();
        value.lifecycle.post.owned_stream_created = 1;
        cases.push(value);
        let mut value = baseline.clone();
        value.lifecycle.post.active_contexts = 1;
        cases.push(value);
        let mut value = baseline.clone();
        value.lifecycle.post.singleton_claimed = true;
        cases.push(value);
        let mut value = baseline.clone();
        value.lifecycle.post.active_registrations = ObservedCounter::measured(1);
        cases.push(value);
        let mut value = baseline.clone();
        value.lifecycle.post.in_flight_work = ObservedCounter::measured(1);
        cases.push(value);
        let mut value = baseline.clone();
        value.lifecycle.post.stale_generations = ObservedCounter::measured(1);
        cases.push(value);
        let mut value = baseline.clone();
        value.execution.dispatch.fallback = 1;
        cases.push(value);
        let mut value = baseline.clone();
        value.execution.dispatch.errors = 1;
        cases.push(value);
        let mut value = baseline.clone();
        value.lifecycle.reconciled = false;
        cases.push(value);
        for value in cases {
            let error = value.validate_success_ready().unwrap_err();
            assert_eq!(error.class, FailureClass::LifecycleOwnership);
        }
    }

    #[test]
    fn production_pass_rejects_scaffold_and_reference_dispatch() {
        let mut evidence = success_ready("fixture");
        evidence.input.numerical_mode = Some("production_mlx_tier_b".to_owned());
        evidence.execution.dispatch.qualification_scaffold = 1;
        assert!(evidence.validate_success_ready().is_err());
        evidence.execution.dispatch.qualification_scaffold = 0;
        evidence.execution.dispatch.explicit_reference = 1;
        assert!(evidence.validate_success_ready().is_err());
    }

    #[test]
    fn measured_zero_cannot_hide_unavailable_or_nonzero_state() {
        let baseline = success_ready("dry_run");
        let mut unavailable = baseline.clone();
        unavailable.lifecycle.post.live_owner_tokens = ObservedCounter::default();
        assert!(unavailable.validate_success_ready().is_err());
        let mut malformed = baseline;
        malformed.lifecycle.post.live_owner_tokens = ObservedCounter {
            status: ObservationStatus::MeasuredZero,
            value: None,
        };
        assert!(malformed.validate().is_err());
    }

    #[test]
    fn production_stage_pass_rejects_fixture_environment_and_synthetic_telemetry() {
        for mode in ["adapter_preflight", "checkpoint_identity", "p1"] {
            let mut evidence = production_success_ready(mode);
            evidence.identity.environment_kind = "checkpoint_free_fixture".to_owned();
            evidence.admission.telemetry_source = "synthetic_fixture".to_owned();
            evidence.identity.loaded_libraries.clear();
            assert_eq!(
                evidence.validate_success_ready().unwrap_err().code,
                "pass_environment_kind"
            );
        }

        let mut evidence = production_success_ready("adapter_preflight");
        evidence.admission.telemetry_source = "synthetic_fixture".to_owned();
        assert_eq!(
            evidence.validate_success_ready().unwrap_err().code,
            "pass_admission"
        );
    }

    #[test]
    fn production_stage_pass_requires_exact_loaded_library_evidence() {
        let mut missing = production_success_ready("adapter_preflight");
        missing.identity.loaded_libraries.clear();
        assert!(missing.validate_success_ready().is_err());

        let mut mismatch = production_success_ready("adapter_preflight");
        mismatch.identity.loaded_libraries[0].actual_sha256 = "3".repeat(64);
        assert!(mismatch.validate_success_ready().is_err());

        let valid = production_success_ready("adapter_preflight");
        assert!(valid.validate_success_ready().is_ok());
    }

    #[test]
    fn checkpoint_identity_pass_requires_production_environment_and_validated_map() {
        let mut valid = production_success_ready("checkpoint_identity");
        valid.identity.checkpoint.tensor_map = TensorMapEvidence {
            status: TensorMapStatus::Validated,
            version: Some("f017-glm52-tensor-map-v1".to_owned()),
            contract_sha256: Some("4".repeat(64)),
            validated_tensor_count: Some(1_809),
        };
        assert!(valid.validate_success_ready().is_ok());

        valid.identity.environment_kind = "checkpoint_free_fixture".to_owned();
        valid.admission.telemetry_source = "synthetic_fixture".to_owned();
        valid.identity.loaded_libraries.clear();
        assert_eq!(
            valid.validate_success_ready().unwrap_err().code,
            "pass_environment_kind"
        );
    }

    #[test]
    fn fixture_checkpoint_identity_pass_requires_fixture_environment() {
        let mut valid = success_ready("fixture_checkpoint_identity");
        valid.identity.environment_kind = "checkpoint_free_fixture".to_owned();
        assert!(valid.validate_success_ready().is_ok());
        valid.identity.environment_kind = "production_reviewed".to_owned();
        assert!(valid.validate_success_ready().is_err());
    }

    fn valid_repeats() -> RepeatIntegrityEvidence {
        RepeatIntegrityEvidence {
            repeat_count_required: 10,
            repeat_count_observed: 10,
            outputs: (0..10)
                .map(|ordinal| RepeatOutputEvidence {
                    ordinal,
                    output_sha256: "a".repeat(64),
                })
                .collect(),
            all_repeat_hashes_equal: true,
            selected_output_sha256: Some("a".repeat(64)),
        }
    }

    fn valid_oracle_ordering() -> OracleOrderingEvidence {
        OracleOrderingEvidence {
            oracle_package_sha256: Some("b".repeat(64)),
            oracle_completed_at: Some("100".to_owned()),
            oracle_completion_marker: Some("oracle_finalized_sequence_0".to_owned()),
            oracle_validated_before_candidate: true,
            candidate_started_at: Some("101".to_owned()),
            candidate_start_marker: Some("candidate_started_sequence_1".to_owned()),
            structural_order_valid: true,
        }
    }

    #[test]
    fn m1d_repeat_integrity_rejects_missing_extra_divergent_and_dispatch_mismatch() {
        let baseline = valid_repeats();
        assert!(validate_m1d_repeat_integrity(&baseline, 10).is_ok());
        let mut cases = Vec::new();
        let mut value = baseline.clone();
        value.outputs.pop();
        value.repeat_count_observed = 9;
        cases.push((value, 10));
        let mut value = baseline.clone();
        value.outputs.push(RepeatOutputEvidence {
            ordinal: 10,
            output_sha256: "a".repeat(64),
        });
        value.repeat_count_observed = 11;
        cases.push((value, 10));
        let mut value = baseline.clone();
        value.outputs[5].output_sha256 = "c".repeat(64);
        cases.push((value, 10));
        cases.push((baseline.clone(), 9));
        let mut value = baseline.clone();
        value.all_repeat_hashes_equal = false;
        cases.push((value, 10));
        let mut value = baseline;
        value.outputs[9].output_sha256 = "d".repeat(64);
        value.selected_output_sha256 = Some("a".repeat(64));
        cases.push((value, 10));
        for (value, dispatches) in cases {
            assert!(validate_m1d_repeat_integrity(&value, dispatches).is_err());
        }
    }

    #[test]
    fn m1d_oracle_ordering_rejects_boolean_only_equal_late_changed_and_stale_proof() {
        let baseline = valid_oracle_ordering();
        assert!(validate_m1d_oracle_ordering(&baseline).is_ok());
        let mut cases = Vec::new();
        let mut value = baseline.clone();
        value.oracle_completion_marker = None;
        cases.push(value);
        let mut value = baseline.clone();
        value.oracle_completed_at = Some("101".to_owned());
        cases.push(value);
        let mut value = baseline.clone();
        value.oracle_completed_at = Some("102".to_owned());
        cases.push(value);
        let mut value = baseline.clone();
        value.oracle_package_sha256 = Some("stale".to_owned());
        cases.push(value);
        let mut value = baseline.clone();
        value.candidate_started_at = None;
        cases.push(value);
        let mut value = baseline;
        value.structural_order_valid = false;
        cases.push(value);
        for value in cases {
            assert!(validate_m1d_oracle_ordering(&value).is_err());
        }
    }
}
