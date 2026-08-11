pub mod checkpoint;
pub mod cli;
pub mod evidence;
pub mod fixture;
pub mod glm52_map;
pub mod json;
pub mod qualification;
pub mod store;

use crate::checkpoint::{CheckpointKind, CheckpointManifest, VerifiedCheckpoint};
use crate::cli::{Config, RunnerMode};
use crate::evidence::{AtomicEvidenceWriter, Evidence, ResultClassification};
use crate::json::{parse_json_no_duplicates, sha256_file};
use std::fs;

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
    if config.out.exists() {
        return Err(RunnerError::new(
            FailureClass::InfrastructureEvidence,
            "output_exists",
            "--out must name a fresh path",
        ));
    }
    let environment_bytes = fs::read(&config.environment_manifest).map_err(|error| {
        RunnerError::new(
            FailureClass::AdmissionEnvironment,
            "environment_manifest_read",
            format!("cannot read environment manifest: {error}"),
        )
    })?;
    let _: serde_json::Value = parse_json_no_duplicates(&environment_bytes).map_err(|error| {
        RunnerError::new(
            FailureClass::AdmissionEnvironment,
            "environment_manifest_json",
            error,
        )
    })?;
    let environment_sha256 = sha256_file(&config.environment_manifest).map_err(|error| {
        RunnerError::new(
            FailureClass::AdmissionEnvironment,
            "environment_manifest_hash",
            error,
        )
    })?;

    let mut evidence = Evidence::initial(&config, environment_sha256);
    let mut writer = AtomicEvidenceWriter::create(config.out.clone(), &evidence)?;

    let result = match config.mode {
        RunnerMode::DryRun => {
            evidence.execution.progress_state = "dry_run_complete".to_owned();
            Ok(())
        }
        RunnerMode::CheckpointIdentity => verify_checkpoint_mode(&config, &mut evidence),
        RunnerMode::AdapterPreflight => run_adapter_preflight(&config, &mut evidence),
        RunnerMode::Fixture { ref manifest } => {
            fixture::run_projection_fixture(manifest, &config, &mut evidence)
        }
        RunnerMode::P1 => Err(RunnerError::new(
            FailureClass::InfrastructureEvidence,
            "p1_not_admitted",
            "real execution is fail-closed until R0 through R14 pass independent review",
        )),
    };

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
    evidence.execution.storage.read_bytes = verified.identity_bytes_read;
    evidence.execution.storage.read_count = verified.identity_read_count;
    evidence.execution.progress_state = "checkpoint_identity_complete".to_owned();
    Ok(())
}
