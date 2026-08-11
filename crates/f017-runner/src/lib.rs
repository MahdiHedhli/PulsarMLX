pub mod checkpoint;
pub mod cli;
pub mod evidence;
pub mod json;
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
        RunnerMode::AdapterPreflight => Err(RunnerError::new(
            FailureClass::InfrastructureEvidence,
            "adapter_preflight_not_implemented",
            "R1 adapter preflight is not yet bound to the canonical runner",
        )),
        RunnerMode::Fixture { .. } => Err(RunnerError::new(
            FailureClass::InfrastructureEvidence,
            "fixture_mode_not_implemented",
            "R12 fixture execution is not yet implemented",
        )),
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
