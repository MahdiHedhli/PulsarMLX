use crate::cli::Config;
use crate::{FailureClass, RunnerError};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::PathBuf;

pub const EVIDENCE_SCHEMA: &str = "pulsarmlx.f017.canonical-runner-evidence";
pub const EVIDENCE_SCHEMA_VERSION: &str = "1.1.0";

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
    pub source_clean: bool,
    pub runner_version: String,
    pub environment_manifest_sha256: String,
    pub platform: BTreeMap<String, String>,
    pub toolchain: BTreeMap<String, String>,
    pub checkpoint: CheckpointEvidence,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CheckpointEvidence {
    pub accessed: bool,
    pub revision: Option<String>,
    pub checkpoint_set_sha256: Option<String>,
    pub catalog_sha256: Option<String>,
    pub shards: Vec<ShardEvidence>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ShardEvidence {
    pub filename: String,
    pub size_bytes: u64,
    pub sha256: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AdmissionEvidence {
    pub memory_floor_bytes: u64,
    pub available_memory_bytes: u64,
    pub memory_pressure: String,
    pub swap_used_bytes: u64,
    pub disk_free_bytes: u64,
    pub load_averages: [f64; 3],
    pub competing_processes_clear: bool,
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
    pub numerical_classification: Option<String>,
    pub numerical: NumericalEvidence,
    pub progress_state: String,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct NumericalEvidence {
    pub oracle_generator_sha: Option<String>,
    pub scaffold_version: Option<String>,
    pub production_backend_version: Option<String>,
    pub frozen_contract_version: Option<String>,
    pub bit_mismatch_count: Option<u64>,
    pub max_abs_error: Option<f64>,
    pub relative_error: Option<f64>,
    pub rmse: Option<f64>,
    pub cosine_similarity: Option<f64>,
    pub deterministic_repeat_count: Option<u64>,
    pub first_divergence: Option<serde_json::Value>,
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
    pub active_registrations: u64,
    pub pending_registration_destructions: u64,
    pub in_flight_work: u64,
    pub live_owner_tokens: u64,
    pub stale_generations: u64,
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
        Self {
            schema: EVIDENCE_SCHEMA.to_owned(),
            schema_version: EVIDENCE_SCHEMA_VERSION.to_owned(),
            identity: IdentityEvidence {
                source_sha: env!("PULSARMLX_SOURCE_SHA").to_owned(),
                source_clean: source_worktree_clean(),
                runner_version: env!("CARGO_PKG_VERSION").to_owned(),
                environment_manifest_sha256,
                platform,
                toolchain,
                checkpoint: CheckpointEvidence {
                    accessed: false,
                    revision: None,
                    checkpoint_set_sha256: None,
                    catalog_sha256: None,
                    shards: Vec::new(),
                },
            },
            admission: AdmissionEvidence {
                memory_floor_bytes: config.memory_floor_bytes,
                available_memory_bytes: 0,
                memory_pressure: "unknown".to_owned(),
                swap_used_bytes: 0,
                disk_free_bytes: 0,
                load_averages: [0.0; 3],
                competing_processes_clear: false,
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
        Ok(())
    }
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
        if target.exists() {
            return Err(evidence_error(
                "output_exists",
                "evidence target already exists",
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cli::{Config, RunnerMode, StreamMode, ValidationMode};
    use crate::json::parse_json_no_duplicates;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn config(out: PathBuf) -> Config {
        Config {
            out,
            validation_mode: ValidationMode::GoldenStrict,
            stream_mode: StreamMode::OwnedDevice,
            memory_floor_bytes: 1,
            environment_manifest: PathBuf::from("environment.json"),
            checkpoint_manifest: None,
            tokens: Vec::new(),
            n_new: 0,
            expected_token: None,
            numerical_mode: None,
            mode: RunnerMode::DryRun,
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
}
