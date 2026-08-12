pub mod admission;
pub mod artifact_paths;
pub mod checkpoint;
pub mod cli;
pub mod contract_bindings;
pub mod evidence;
pub mod expert_boundary;
pub mod final_output_qualification;
pub mod fixture;
pub mod glm52_map;
pub mod json;
pub mod layer_qualification;
pub mod local_boundary;
pub mod m1d_execution_config;
pub mod m1e_execution_config;
pub mod numerical_classification;
pub mod projection_boundary;
pub mod qualification;
pub mod store;
pub mod tiny_model;

use crate::admission::HostAdmission;
use crate::checkpoint::{CheckpointKind, CheckpointManifest, VerifiedCheckpoint};
use crate::cli::{Config, RunnerMode};
use crate::environment::ValidatedEnvironment;
use crate::evidence::{AtomicEvidenceWriter, Evidence, ResultClassification};
use crate::glm52_map::{Glm52TensorMap, GLM52_TENSOR_COUNT, GLM52_TENSOR_MAP_VERSION};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FailureClass {
    AdmissionEnvironment,
    CheckpointIdentity,
    LifecycleOwnership,
    NumericalBehavioral,
    InfrastructureEvidence,
    Cancelled,
}

impl FailureClass {
    pub const fn exit_code(self) -> i32 {
        match self {
            Self::AdmissionEnvironment => 10,
            Self::CheckpointIdentity => 11,
            Self::LifecycleOwnership => 12,
            Self::NumericalBehavioral => 13,
            Self::InfrastructureEvidence => 14,
            Self::Cancelled => 15,
        }
    }

    pub const fn result_classification(self) -> ResultClassification {
        match self {
            Self::AdmissionEnvironment => ResultClassification::FailAdmissionEnvironment,
            Self::CheckpointIdentity => ResultClassification::FailCheckpointIdentity,
            Self::LifecycleOwnership => ResultClassification::FailLifecycleOwnership,
            Self::NumericalBehavioral => ResultClassification::FailNumericalBehavioral,
            Self::InfrastructureEvidence => ResultClassification::FailInfrastructureEvidence,
            Self::Cancelled => ResultClassification::Cancelled,
        }
    }
}

#[derive(Debug)]
pub struct RunnerError {
    pub class: FailureClass,
    pub code: &'static str,
    pub message: String,
}

impl RunnerError {
    pub fn new(class: FailureClass, code: &'static str, message: impl Into<String>) -> Self {
        Self {
            class,
            code,
            message: message.into(),
        }
    }
}

impl std::fmt::Display for RunnerError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{}: {}", self.code, self.message)
    }
}

impl std::error::Error for RunnerError {}

pub fn execute(config: Config) -> Result<Evidence, RunnerError> {
    if let Some(binding) = &config.execution_config {
        if binding.attempt == 1
            && matches!(
                config.mode,
                RunnerMode::M1ePreflight
                    | RunnerMode::FixtureExpert { .. }
                    | RunnerMode::RealExpert { .. }
            )
        {
            m1e_execution_config::verify_unchanged(binding)?;
        } else {
            m1d_execution_config::verify_unchanged(binding)?;
        }
    }
    let environment = ValidatedEnvironment::load(&config.environment_manifest)?;
    environment.validate_for_mode(&config.mode)?;
    let mut evidence = Evidence::initial_with_environment(&config, &environment);
    let mut writer = AtomicEvidenceWriter::create(config.out.clone(), &evidence)?;

    let result = (|| {
        let admission = HostAdmission::collect(
            &config.mode,
            environment.production,
            config.checkpoint_manifest.as_deref(),
            &config.out,
        )?;
        admission.validate(
            &config.mode,
            environment.production,
            config.memory_floor_bytes,
        )?;
        evidence.admission.telemetry_source = admission.telemetry_source;
        evidence.admission.physical_memory_bytes = admission.physical_memory_bytes;
        evidence.admission.available_memory_bytes = admission.available_memory_bytes;
        evidence.admission.compressed_memory_bytes = admission.compressed_memory_bytes;
        evidence.admission.memory_pressure = admission.memory_pressure;
        evidence.admission.swap_used_bytes = admission.swap_used_bytes;
        evidence.admission.checkpoint_volume_free_bytes = admission.checkpoint_volume_free_bytes;
        evidence.admission.evidence_volume_free_bytes = admission.evidence_volume_free_bytes;
        evidence.admission.load_averages = admission.load_averages;
        evidence.admission.competing_processes_clear = admission.competing_processes_clear;
        evidence.admission.competing_processes = admission.competing_processes;
        evidence.admission.port_1234_listener = admission.port_1234_listener;
        evidence.admission.thermal_state = admission.thermal_state;
        evidence.admission.performance_warning = admission.performance_warning;
        if environment.production
            && matches!(
                config.mode,
                RunnerMode::AdapterPreflight
                    | RunnerMode::CheckpointIdentity
                    | RunnerMode::M1ePreflight
                    | RunnerMode::RealProjection { .. }
                    | RunnerMode::RealExpert { .. }
                    | RunnerMode::P1
            )
        {
            evidence.identity.loaded_libraries = environment.verify_loaded_libraries()?;
        }
        mark_non_registration_domains_not_applicable(&mut evidence);
        writer.update(&evidence)?;

        match config.mode {
            RunnerMode::DryRun => {
                evidence.lifecycle.reconciled = true;
                evidence.execution.progress_state = "dry_run_complete".to_owned();
                Ok(())
            }
            RunnerMode::M1ePreflight => {
                evidence.lifecycle.reconciled = true;
                evidence.execution.progress_state = "READY_TO_EXECUTE_M1_E".to_owned();
                Ok(())
            }
            RunnerMode::CheckpointIdentity | RunnerMode::FixtureCheckpointIdentity => {
                verify_checkpoint_mode(&config, &mut evidence)
            }
            RunnerMode::AdapterPreflight => run_adapter_preflight(&config, &mut evidence),
            RunnerMode::Fixture { ref manifest } => {
                fixture::run_projection_fixture(manifest, &config, &mut evidence)
            }
            RunnerMode::FixtureProjection { ref package }
            | RunnerMode::RealProjection { ref package } => {
                projection_boundary::run(package, &config, &mut evidence)
            }
            RunnerMode::FixtureExpert { ref package } | RunnerMode::RealExpert { ref package } => {
                expert_boundary::run(package, &config, &mut evidence)
            }
            RunnerMode::P1 => Err(RunnerError::new(
                FailureClass::InfrastructureEvidence,
                "p1_not_admitted",
                "real execution is fail-closed until R0 through R14 pass independent review",
            )),
        }
    })();

    let result = result
        .and_then(|()| {
            if let Some(binding) = &config.execution_config {
                if binding.attempt == 1
                    && matches!(
                        config.mode,
                        RunnerMode::M1ePreflight
                            | RunnerMode::FixtureExpert { .. }
                            | RunnerMode::RealExpert { .. }
                    )
                {
                    m1e_execution_config::verify_unchanged(binding)?;
                } else {
                    m1d_execution_config::verify_unchanged(binding)?;
                }
            }
            Ok(())
        })
        .and_then(|()| evidence.validate_success_ready());

    match result {
        Ok(()) => {
            evidence.result.classification = ResultClassification::Pass;
            evidence.result.completed = true;
            evidence.result.stop_reason = None;
            evidence.validate()?;
            writer.update(&evidence)?;
            Ok(evidence)
        }
        Err(error) => {
            evidence.result.classification = error.class.result_classification();
            evidence.result.completed = true;
            evidence.result.first_failure = Some(evidence::FailureRecord {
                code: error.code.to_owned(),
                message: error.message.clone(),
            });
            evidence.result.stop_reason = Some(error.message.clone());
            writer.update(&evidence)?;
            Err(error)
        }
    }
}

fn run_adapter_preflight(config: &Config, evidence: &mut Evidence) -> Result<(), RunnerError> {
    let mode = match config.stream_mode {
        cli::StreamMode::DefaultGpu => stream::NativeMlxPreflightMode::DefaultGpu,
        cli::StreamMode::OwnedDevice => stream::NativeMlxPreflightMode::OwnedDevice,
    };
    let report = stream::run_native_mlx_preflight(mode).map_err(|error| {
        let (class, code) = if error.contains("was not compiled") {
            (FailureClass::AdmissionEnvironment, "native_mlx_unavailable")
        } else {
            (FailureClass::LifecycleOwnership, "adapter_preflight_failed")
        };
        RunnerError::new(class, code, error)
    })?;
    if report.default_cpu_created_before != 0
        || report.default_cpu_freed_before != 0
        || report.default_gpu_created_before != 0
        || report.default_gpu_freed_before != 0
        || report.owned_created_before != 0
        || report.owned_freed_before != 0
        || report.context_initially_active
    {
        return Err(RunnerError::new(
            FailureClass::LifecycleOwnership,
            "adapter_preflight_nonzero_baseline",
            "fresh adapter-preflight process did not begin at zero state",
        ));
    }
    evidence.admission.singleton_initially_unclaimed = true;
    evidence.lifecycle.pre.default_cpu_stream_created = report.default_cpu_created_before;
    evidence.lifecycle.pre.default_cpu_stream_freed = report.default_cpu_freed_before;
    evidence.lifecycle.pre.default_gpu_stream_created = report.default_gpu_created_before;
    evidence.lifecycle.pre.default_gpu_stream_freed = report.default_gpu_freed_before;
    evidence.lifecycle.pre.owned_stream_created = report.owned_created_before;
    evidence.lifecycle.pre.owned_stream_freed = report.owned_freed_before;
    evidence.lifecycle.post.managed_created = report.managed_created;
    evidence.lifecycle.post.managed_destroyed = report.managed_destroyed;
    evidence.lifecycle.post.derived_created = report.derived_created;
    evidence.lifecycle.post.derived_destroyed = report.derived_destroyed;
    evidence.lifecycle.post.callback_count = report.callback_count;
    evidence.lifecycle.post.default_cpu_stream_created = report.default_cpu_created_after;
    evidence.lifecycle.post.default_cpu_stream_freed = report.default_cpu_freed_after;
    evidence.lifecycle.post.default_gpu_stream_created = report.default_gpu_created_after;
    evidence.lifecycle.post.default_gpu_stream_freed = report.default_gpu_freed_after;
    evidence.lifecycle.post.owned_stream_created = report.owned_created_after;
    evidence.lifecycle.post.owned_stream_freed = report.owned_freed_after;
    evidence.lifecycle.post.active_contexts = u64::from(report.context_active_after);
    evidence.lifecycle.post.singleton_claimed = report.context_active_after;
    evidence.lifecycle.reconciled = report.reconciled();
    evidence.execution.dispatch.native = 1;
    evidence.execution.progress_state = "adapter_preflight_complete".to_owned();
    if !evidence.lifecycle.reconciled {
        return Err(RunnerError::new(
            FailureClass::LifecycleOwnership,
            "adapter_preflight_reconciliation",
            "production adapter preflight did not return to zero",
        ));
    }
    Ok(())
}

fn verify_checkpoint_mode(config: &Config, evidence: &mut Evidence) -> Result<(), RunnerError> {
    let manifest_path = config.checkpoint_manifest.as_ref().ok_or_else(|| {
        RunnerError::new(
            FailureClass::InfrastructureEvidence,
            "missing_checkpoint_manifest",
            "checkpoint identity mode requires --checkpoint-manifest",
        )
    })?;
    let manifest = CheckpointManifest::load(manifest_path)?;
    let verified = VerifiedCheckpoint::verify(manifest_path, manifest)?;
    if verified.manifest.kind == CheckpointKind::Production && verified.manifest.shards.len() != 6 {
        return Err(RunnerError::new(
            FailureClass::CheckpointIdentity,
            "production_shard_count",
            "production GLM-5.2 manifests must contain exactly six shards",
        ));
    }
    evidence.identity.checkpoint = verified.evidence_identity();
    if verified.manifest.kind == CheckpointKind::Production {
        let map = Glm52TensorMap::from_gguf(&verified.catalog)?;
        evidence.identity.checkpoint.tensor_map.status = evidence::TensorMapStatus::Validated;
        evidence.identity.checkpoint.tensor_map.version = Some(GLM52_TENSOR_MAP_VERSION.to_owned());
        evidence.identity.checkpoint.tensor_map.contract_sha256 = Some(map.contract_sha256());
        evidence
            .identity
            .checkpoint
            .tensor_map
            .validated_tensor_count = Some(map.len() as u64);
        if map.len() != GLM52_TENSOR_COUNT {
            return Err(RunnerError::new(
                FailureClass::CheckpointIdentity,
                "tensor_map_count",
                "production GLM52 tensor map count differs",
            ));
        }
    } else {
        evidence.identity.checkpoint.tensor_map.status = evidence::TensorMapStatus::NotApplicable;
    }
    evidence.execution.storage.read_bytes = verified.identity_bytes_read;
    evidence.execution.storage.read_count = verified.identity_read_count;
    evidence.execution.progress_state = "checkpoint_identity_complete".to_owned();
    evidence.lifecycle.reconciled = true;
    Ok(())
}

fn mark_non_registration_domains_not_applicable(evidence: &mut Evidence) {
    use crate::evidence::ObservedCounter;
    for counters in [&mut evidence.lifecycle.pre, &mut evidence.lifecycle.post] {
        counters.active_registrations = ObservedCounter::not_applicable();
        counters.pending_registration_destructions = ObservedCounter::not_applicable();
        counters.in_flight_work = ObservedCounter::not_applicable();
        counters.live_owner_tokens = ObservedCounter::not_applicable();
        counters.stale_generations = ObservedCounter::not_applicable();
    }
}
pub mod environment;
