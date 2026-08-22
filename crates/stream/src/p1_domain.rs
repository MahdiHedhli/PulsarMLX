//! One-process bounded-P1 attempt, accounting, receipt, and terminal domain.
//!
//! The expensive tensor-math boundary is injected through [`BoundedP1Math`].
//! Attempt ownership, native context lifetime, live accounting, receipt
//! emission, and terminalization are never supplied by a mock backend.

use crate::{MlxContext, MlxDevice, MlxStreamMode, P1AccountingSnapshot};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

pub const RECEIPT_SCHEMA: &str = "pulsarmlx.f017.native-bounded-p1-execution-receipt/2.0.0";
pub const TERMINAL_SCHEMA: &str = "pulsarmlx.f017.native-bounded-p1-terminal/1.0.0";
pub const EVIDENCED_RECEIPT_SCHEMA: &str =
    "pulsarmlx.f017.native-bounded-p1-execution-receipt/3.0.0";
pub const EVIDENCED_TERMINAL_SCHEMA: &str = "pulsarmlx.f017.native-bounded-p1-terminal/2.0.0";
pub const SNAPSHOT_SCHEMA: &str = "pulsarmlx.f017.native-bounded-p1-accounting-snapshot/1.0.0";
pub const ACCESS_EVENT_SCHEMA: &str = "pulsarmlx.f017.native-bounded-p1-access-event/1.0.0";
pub const ACCESS_CENSUS_SCHEMA: &str = "pulsarmlx.f017.native-bounded-p1-access-census/1.0.0";
pub const DIAGNOSTIC_SCHEMA: &str = "pulsarmlx.f017.native-bounded-p1-diagnostic-manifest/1.0.0";
pub const PROMPT_TOKEN: u32 = 9703;
pub const EXPECTED_TOKEN: u32 = 21615;

#[derive(Debug)]
pub enum P1DomainError {
    Io(std::io::Error),
    Json(serde_json::Error),
    Rejected(String),
}

impl std::fmt::Display for P1DomainError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(error) => write!(f, "I/O: {error}"),
            Self::Json(error) => write!(f, "JSON: {error}"),
            Self::Rejected(message) => f.write_str(message),
        }
    }
}

impl std::error::Error for P1DomainError {}

impl From<std::io::Error> for P1DomainError {
    fn from(value: std::io::Error) -> Self {
        Self::Io(value)
    }
}

impl From<serde_json::Error> for P1DomainError {
    fn from(value: serde_json::Error) -> Self {
        Self::Json(value)
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct P1AttemptAuthority {
    pub authorization_id: String,
    pub attempt_id: String,
    pub domain_declaration_sha256: String,
    pub final_review_sha256: String,
    pub human_approval_sha256: String,
    pub contract_sha256: String,
    pub executor_sha256: String,
    pub git_head: String,
    pub historical_master_ledger_sha256: String,
    pub d0_sha256: String,
    pub d1_sha256: String,
    pub d2_sha256: String,
    pub d3_5_result_sha256: String,
    pub d3_5_acceptance_sha256: String,
    pub synthetic_full_graph_result_sha256: String,
    pub checkpoint_manifest_sha256: String,
    pub checkpoint_catalog_sha256: String,
    pub checkpoint_set_sha256: String,
    pub historical_master_terminal_value: u64,
    pub prompt_token: u32,
    pub expected_token: u32,
    pub attempts: u32,
    pub retries: u32,
    pub resume: bool,
    pub mandatory_stop: bool,
    pub real_event_authorized: bool,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct P1RuntimeIdentity {
    pub mlx_version: String,
    pub mlx_c_version: String,
    pub architecture: String,
    pub machine_brand: String,
    pub stream_origin: String,
    pub native_handle_owned: bool,
    pub deallocation_responsibility: String,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BoundedP1Receipt {
    pub schema: String,
    pub event_class: String,
    pub authorization_id: String,
    pub attempt_id: String,
    pub domain_declaration_sha256: String,
    pub final_review_sha256: String,
    pub human_approval_sha256: String,
    pub contract_sha256: String,
    pub executor_sha256: String,
    pub git_head: String,
    pub historical_master_ledger_sha256: String,
    pub d0_sha256: String,
    pub d1_sha256: String,
    pub d2_sha256: String,
    pub d3_5_result_sha256: String,
    pub d3_5_acceptance_sha256: String,
    pub synthetic_full_graph_result_sha256: String,
    pub checkpoint_manifest_sha256: String,
    pub checkpoint_catalog_sha256: String,
    pub checkpoint_set_sha256: String,
    pub runtime: P1RuntimeIdentity,
    pub accounting_before: P1AccountingSnapshot,
    pub accounting_after: P1AccountingSnapshot,
    pub prompt_token: u32,
    pub result_token: u32,
    pub generated_token_count: u32,
    pub native_event_delta: u32,
    pub historical_master_before: u64,
    pub historical_master_after: u64,
    pub historical_master_delta: u64,
    pub mandatory_stop_observed: bool,
    pub execution_result: String,
    pub terminal_state: String,
    pub started_at_unix_ns: u128,
    pub completed_at_unix_ns: u128,
}

/// A durably recorded access action. Events are written one-per-file before
/// the associated operation can be forgotten by a later failure path.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct P1AccessEvent {
    pub schema: String,
    pub sequence: u64,
    pub kind: String,
    pub authority_id: String,
    pub sha256: String,
    pub size_bytes: u64,
    pub tensor_name: Option<String>,
    pub result: String,
    pub recorded_at_unix_ns: u128,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct P1AccessCensus {
    pub schema: String,
    pub authorization_id: String,
    pub attempt_id: String,
    pub event_count: u64,
    pub shard_open_count: u64,
    pub shard_identity_rehash_count: u64,
    pub read_only_private_map_count: u64,
    pub tensor_lookup_count: u64,
    pub tensor_first_use_count: u64,
    pub tensor_reuse_count: u64,
    pub page_residency_observation_count: u64,
    pub historical_explicit_payload_extraction_count: u64,
    pub unexpected_access_attempt_count: u64,
    pub fallback_attempt_count: u64,
    pub alternate_root_attempt_count: u64,
    pub events: Vec<P1AccessEvent>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct P1DurableSnapshot {
    pub schema: String,
    pub phase: String,
    pub authorization_id: String,
    pub attempt_id: String,
    pub captured_at_unix_ns: u128,
    pub counters: P1AccountingSnapshot,
}

/// Stable production-buffer fingerprints. The executor supplies hashes of
/// buffers it already produced; the evidence layer never recomputes math.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct P1LayerDiagnostic {
    pub layer: u32,
    pub layer_input_sha256: String,
    pub post_attention_residual_sha256: String,
    pub router_normalized_input_sha256: String,
    pub selected_expert_ids: Vec<u32>,
    pub routing_weight_f32_bits: Vec<u32>,
    pub routed_aggregate_sha256: String,
    pub shared_expert_sha256: String,
    pub layer_output_sha256: String,
    pub hidden_width: u64,
    pub dtype: String,
    pub byte_order: String,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct P1NumericalDiagnosticManifest {
    pub schema: String,
    pub backend: String,
    pub serialization: String,
    pub synchronization: String,
    pub direct_production_bytes: bool,
    pub layers: Vec<P1LayerDiagnostic>,
    pub final_hidden_state_sha256: String,
    pub final_norm_sha256: String,
    pub full_logits_sha256: String,
    pub logits_dtype: String,
    pub logits_shape: Vec<u64>,
    pub top_token_ids: Vec<u32>,
    pub top_logit_f32_bits: Vec<u32>,
    pub selected_token: Option<u32>,
    pub expected_token: u32,
    pub tie_rule: String,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EvidencedBoundedP1Receipt {
    pub schema: String,
    pub event_class: String,
    pub authorization_id: String,
    pub attempt_id: String,
    pub contract_sha256: String,
    pub executor_sha256: String,
    pub git_head: String,
    pub checkpoint_manifest_sha256: String,
    pub checkpoint_catalog_sha256: String,
    pub checkpoint_set_sha256: String,
    pub historical_master_ledger_sha256: String,
    pub historical_master_before: u64,
    pub historical_master_after: u64,
    pub historical_master_delta: u64,
    pub native_event_delta: u32,
    pub runtime: P1RuntimeIdentity,
    pub pre_snapshot_sha256: String,
    pub post_snapshot_sha256: String,
    pub access_census_sha256: String,
    pub numerical_diagnostic_manifest_sha256: String,
    pub prompt_token: u32,
    pub expected_token: u32,
    pub produced_token: Option<u32>,
    pub generated_token_count: u32,
    pub execution_result: String,
    pub error_class: Option<String>,
    pub mandatory_stop_observed: bool,
    pub terminal_state: String,
    pub started_at_unix_ns: u128,
    pub completed_at_unix_ns: u128,
}

#[derive(Serialize)]
struct AttemptClaim<'a> {
    schema: &'static str,
    state: &'static str,
    authorization_id: &'a str,
    attempt_id: &'a str,
    owner_pid: u32,
    ownership_nonce: String,
    started_at_unix_ns: u128,
    retries: u32,
    resume: bool,
}

#[derive(Serialize)]
struct Terminal<'a> {
    schema: &'static str,
    state: &'a str,
    authorization_id: &'a str,
    attempt_id: &'a str,
    owner_pid: u32,
    ownership_nonce: &'a str,
    receipt_count: u32,
    receipt_sha256: Option<&'a str>,
    terminalized_at_unix_ns: u128,
    retry_permitted: bool,
}

#[derive(Serialize)]
struct EvidencedTerminal<'a> {
    schema: &'static str,
    state: &'a str,
    authorization_id: &'a str,
    attempt_id: &'a str,
    owner_pid: u32,
    ownership_nonce: &'a str,
    receipt_count: u32,
    receipt_sha256: &'a str,
    pre_snapshot_sha256: &'a str,
    post_snapshot_sha256: &'a str,
    access_census_sha256: &'a str,
    numerical_diagnostic_manifest_sha256: &'a str,
    produced_token: Option<u32>,
    error_class: Option<&'a str>,
    terminalized_at_unix_ns: u128,
    retry_permitted: bool,
}

/// Only the tensor/kernel computation is replaceable. It receives an already
/// owned native context and returns exactly one token or fails.
pub trait BoundedP1Math {
    fn backend_id(&self) -> &'static str;
    fn execute_one(&mut self, context: &MlxContext, prompt_token: u32) -> Result<u32, String>;
}

/// Forward-only producer contract used by executor generation v3. The
/// recorder belongs to the RN1-owned attempt; math can report access and
/// already-produced numerical fingerprints but cannot author receipts.
pub trait EvidencedP1Math {
    fn backend_id(&self) -> &'static str;
    fn execute_one_evidenced(
        &mut self,
        context: &MlxContext,
        prompt_token: u32,
        recorder: &mut P1EvidenceRecorder,
    ) -> Result<(u32, P1NumericalDiagnosticManifest), String>;
}

pub struct P1EvidenceRecorder {
    event_dir: PathBuf,
    diagnostic_layer_dir: PathBuf,
    authorization_id: String,
    attempt_id: String,
    events: Vec<P1AccessEvent>,
}

impl P1EvidenceRecorder {
    fn new(attempt_dir: &Path, authority: &P1AttemptAuthority) -> Result<Self, P1DomainError> {
        let event_dir = attempt_dir.join("access-events");
        let diagnostic_layer_dir = attempt_dir.join("diagnostic-layers");
        fs::create_dir(&event_dir)?;
        fs::create_dir(&diagnostic_layer_dir)?;
        fs::set_permissions(&event_dir, fs::Permissions::from_mode(0o700))?;
        fs::set_permissions(&diagnostic_layer_dir, fs::Permissions::from_mode(0o700))?;
        fsync_directory(attempt_dir)?;
        Ok(Self {
            event_dir,
            diagnostic_layer_dir,
            authorization_id: authority.authorization_id.clone(),
            attempt_id: authority.attempt_id.clone(),
            events: Vec::new(),
        })
    }

    pub fn diagnostic_layer_directory(&self) -> PathBuf {
        self.diagnostic_layer_dir.clone()
    }

    pub fn bank_layer_diagnostic(&self, diagnostic: &P1LayerDiagnostic) -> Result<PathBuf, String> {
        if diagnostic.layer >= 79
            || diagnostic.hidden_width == 0
            || diagnostic.dtype != "little-endian-f32"
        {
            return Err("invalid layer diagnostic".into());
        }
        let path = self
            .diagnostic_layer_dir
            .join(format!("{:08}.json", diagnostic.layer));
        write_exclusive(&path, diagnostic).map_err(|error| error.to_string())?;
        if sha256(&path).map_err(|error| error.to_string())?.len() != 64 {
            return Err("layer diagnostic readback failed".into());
        }
        Ok(path)
    }

    pub fn record(
        &mut self,
        kind: &str,
        authority_id: &str,
        content_sha256: &str,
        size_bytes: u64,
        tensor_name: Option<&str>,
        result: &str,
    ) -> Result<(), String> {
        let allowed = [
            "SHARD_OPEN",
            "SHARD_IDENTITY_REHASH",
            "READ_ONLY_PRIVATE_MMAP",
            "TENSOR_LOOKUP",
            "TENSOR_FIRST_USE",
            "TENSOR_REUSE",
            "PAGE_RESIDENCY_OBSERVATION",
            "HISTORICAL_EXPLICIT_PAYLOAD_EXTRACTION",
            "UNEXPECTED_ACCESS_ATTEMPT",
            "FALLBACK_ATTEMPT",
            "ALTERNATE_ROOT_ATTEMPT",
        ];
        if !allowed.contains(&kind)
            || authority_id.is_empty()
            || (!content_sha256.is_empty() && content_sha256.len() != 64)
        {
            return Err("invalid access event".into());
        }
        let event = P1AccessEvent {
            schema: ACCESS_EVENT_SCHEMA.into(),
            sequence: self.events.len() as u64,
            kind: kind.into(),
            authority_id: authority_id.into(),
            sha256: content_sha256.into(),
            size_bytes,
            tensor_name: tensor_name.map(str::to_owned),
            result: result.into(),
            recorded_at_unix_ns: now_ns().map_err(|error| error.to_string())?,
        };
        let path = self.event_dir.join(format!("{:08}.json", event.sequence));
        write_exclusive(&path, &event).map_err(|error| error.to_string())?;
        if sha256(&path).map_err(|error| error.to_string())?.len() != 64 {
            return Err("access event readback failed".into());
        }
        self.events.push(event);
        Ok(())
    }

    fn census(&self) -> P1AccessCensus {
        let count = |kind: &str| {
            self.events
                .iter()
                .filter(|event| event.kind == kind)
                .count() as u64
        };
        P1AccessCensus {
            schema: ACCESS_CENSUS_SCHEMA.into(),
            authorization_id: self.authorization_id.clone(),
            attempt_id: self.attempt_id.clone(),
            event_count: self.events.len() as u64,
            shard_open_count: count("SHARD_OPEN"),
            shard_identity_rehash_count: count("SHARD_IDENTITY_REHASH"),
            read_only_private_map_count: count("READ_ONLY_PRIVATE_MMAP"),
            tensor_lookup_count: count("TENSOR_LOOKUP"),
            tensor_first_use_count: count("TENSOR_FIRST_USE"),
            tensor_reuse_count: count("TENSOR_REUSE"),
            page_residency_observation_count: count("PAGE_RESIDENCY_OBSERVATION"),
            historical_explicit_payload_extraction_count: count(
                "HISTORICAL_EXPLICIT_PAYLOAD_EXTRACTION",
            ),
            unexpected_access_attempt_count: count("UNEXPECTED_ACCESS_ATTEMPT"),
            fallback_attempt_count: count("FALLBACK_ATTEMPT"),
            alternate_root_attempt_count: count("ALTERNATE_ROOT_ATTEMPT"),
            events: self.events.clone(),
        }
    }
}

struct OwnedAttempt {
    root: PathBuf,
    attempt_dir: PathBuf,
    authorization_id: String,
    attempt_id: String,
    owner_pid: u32,
    ownership_nonce: String,
    terminalized: bool,
}

fn now_ns() -> Result<u128, P1DomainError> {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|value| value.as_nanos())
        .map_err(|_| P1DomainError::Rejected("system clock precedes Unix epoch".into()))
}

fn canonical_json<T: Serialize>(value: &T) -> Result<Vec<u8>, P1DomainError> {
    let mut data = serde_json::to_vec(value)?;
    data.push(b'\n');
    Ok(data)
}

fn fsync_directory(path: &Path) -> Result<(), P1DomainError> {
    File::open(path)?.sync_all()?;
    Ok(())
}

fn write_exclusive(path: &Path, value: &impl Serialize) -> Result<(), P1DomainError> {
    let mut output = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o400)
        .open(path)?;
    output.write_all(&canonical_json(value)?)?;
    output.sync_all()?;
    fsync_directory(
        path.parent()
            .ok_or_else(|| P1DomainError::Rejected("path has no parent".into()))?,
    )
}

fn sha256(path: &Path) -> Result<String, P1DomainError> {
    let mut digest = Sha256::new();
    let mut input = File::open(path)?;
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let count = input.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    Ok(format!("{:x}", digest.finalize()))
}

impl OwnedAttempt {
    fn claim(root: &Path, authority: &P1AttemptAuthority) -> Result<Self, P1DomainError> {
        if root.exists() {
            let metadata = fs::symlink_metadata(root)?;
            if metadata.file_type().is_symlink() || !metadata.is_dir() {
                return Err(P1DomainError::Rejected("unsafe attempt state root".into()));
            }
        } else {
            fs::create_dir(root)?;
            fs::set_permissions(root, fs::Permissions::from_mode(0o700))?;
            fsync_directory(
                root.parent()
                    .ok_or_else(|| P1DomainError::Rejected("state root has no parent".into()))?,
            )?;
        }
        let owner_pid = std::process::id();
        let started = now_ns()?;
        let ownership_nonce = format!("{}-{}-{}", authority.authorization_id, owner_pid, started);
        let claim = AttemptClaim {
            schema: "pulsarmlx.f017.native-bounded-p1-owned-claim/1.0.0",
            state: "CONSUMING",
            authorization_id: &authority.authorization_id,
            attempt_id: &authority.attempt_id,
            owner_pid,
            ownership_nonce: ownership_nonce.clone(),
            started_at_unix_ns: started,
            retries: 0,
            resume: false,
        };
        write_exclusive(&root.join("p1-once.claim.json"), &claim)?;
        let attempt_dir = root.join(&authority.attempt_id);
        fs::create_dir(&attempt_dir)?;
        fs::set_permissions(&attempt_dir, fs::Permissions::from_mode(0o700))?;
        fsync_directory(root)?;
        write_exclusive(&attempt_dir.join("durable-attempt-start.json"), &claim)?;
        Ok(Self {
            root: root.to_path_buf(),
            attempt_dir,
            authorization_id: authority.authorization_id.clone(),
            attempt_id: authority.attempt_id.clone(),
            owner_pid,
            ownership_nonce,
            terminalized: false,
        })
    }

    fn still_owns(&self) -> Result<bool, P1DomainError> {
        let raw = fs::read(self.root.join("p1-once.claim.json"))?;
        let value: serde_json::Value = serde_json::from_slice(&raw)?;
        Ok(
            value.get("owner_pid").and_then(|v| v.as_u64()) == Some(self.owner_pid as u64)
                && value.get("ownership_nonce").and_then(|v| v.as_str())
                    == Some(&self.ownership_nonce)
                && value.get("authorization_id").and_then(|v| v.as_str())
                    == Some(&self.authorization_id)
                && value.get("attempt_id").and_then(|v| v.as_str()) == Some(&self.attempt_id),
        )
    }

    fn terminalize(
        &mut self,
        state: &str,
        receipt_sha256: Option<&str>,
    ) -> Result<(), P1DomainError> {
        if self.terminalized || !self.still_owns()? {
            return Err(P1DomainError::Rejected(
                "terminalization rejected: invocation does not own this attempt".into(),
            ));
        }
        let receipt_count = fs::read_dir(&self.attempt_dir)?
            .filter_map(Result::ok)
            .filter(|entry| entry.file_name() == "execution-receipt.json")
            .count() as u32;
        if receipt_count != u32::from(receipt_sha256.is_some()) {
            return Err(P1DomainError::Rejected(
                "terminal receipt census does not match authoritative receipt".into(),
            ));
        }
        let terminal = Terminal {
            schema: TERMINAL_SCHEMA,
            state,
            authorization_id: &self.authorization_id,
            attempt_id: &self.attempt_id,
            owner_pid: self.owner_pid,
            ownership_nonce: &self.ownership_nonce,
            receipt_count,
            receipt_sha256,
            terminalized_at_unix_ns: now_ns()?,
            retry_permitted: false,
        };
        write_exclusive(&self.attempt_dir.join("terminal.json"), &terminal)?;
        self.terminalized = true;
        Ok(())
    }

    fn terminalize_evidenced(
        &mut self,
        state: &str,
        receipt_sha256: &str,
        pre_snapshot_sha256: &str,
        post_snapshot_sha256: &str,
        access_census_sha256: &str,
        diagnostic_sha256: &str,
        produced_token: Option<u32>,
        error_class: Option<&str>,
    ) -> Result<(), P1DomainError> {
        if self.terminalized || !self.still_owns()? {
            return Err(P1DomainError::Rejected(
                "terminalization rejected: invocation does not own this attempt".into(),
            ));
        }
        for (name, expected) in [
            ("execution-receipt.json", receipt_sha256),
            ("pre-accounting-snapshot.json", pre_snapshot_sha256),
            ("post-accounting-snapshot.json", post_snapshot_sha256),
            ("access-census.json", access_census_sha256),
            ("numerical-diagnostic-manifest.json", diagnostic_sha256),
        ] {
            let path = self.attempt_dir.join(name);
            if !path.is_file() || sha256(&path)? != expected {
                return Err(P1DomainError::Rejected(format!(
                    "terminal evidence binding mismatch: {name}"
                )));
            }
        }
        let terminal = EvidencedTerminal {
            schema: EVIDENCED_TERMINAL_SCHEMA,
            state,
            authorization_id: &self.authorization_id,
            attempt_id: &self.attempt_id,
            owner_pid: self.owner_pid,
            ownership_nonce: &self.ownership_nonce,
            receipt_count: 1,
            receipt_sha256,
            pre_snapshot_sha256,
            post_snapshot_sha256,
            access_census_sha256,
            numerical_diagnostic_manifest_sha256: diagnostic_sha256,
            produced_token,
            error_class,
            terminalized_at_unix_ns: now_ns()?,
            retry_permitted: false,
        };
        write_exclusive(&self.attempt_dir.join("terminal.json"), &terminal)?;
        self.terminalized = true;
        Ok(())
    }
}

fn validate_authority(
    authority: &P1AttemptAuthority,
    inert_test: bool,
) -> Result<(), P1DomainError> {
    let sha256_hashes = [
        &authority.domain_declaration_sha256,
        &authority.final_review_sha256,
        &authority.human_approval_sha256,
        &authority.contract_sha256,
        &authority.executor_sha256,
        &authority.historical_master_ledger_sha256,
        &authority.d0_sha256,
        &authority.d1_sha256,
        &authority.d2_sha256,
        &authority.d3_5_result_sha256,
        &authority.d3_5_acceptance_sha256,
        &authority.synthetic_full_graph_result_sha256,
        &authority.checkpoint_manifest_sha256,
        &authority.checkpoint_catalog_sha256,
        &authority.checkpoint_set_sha256,
    ];
    if sha256_hashes.iter().any(|value| value.len() != 64)
        || authority.git_head.len() != 40
        || !is_safe_authority_identifier(&authority.authorization_id)
        || !is_safe_authority_identifier(&authority.attempt_id)
        || authority.prompt_token != PROMPT_TOKEN
        || authority.expected_token != EXPECTED_TOKEN
        || authority.attempts != 1
        || authority.retries != 0
        || authority.resume
        || !authority.mandatory_stop
        || authority.historical_master_terminal_value != 175
        || authority.real_event_authorized == inert_test
    {
        return Err(P1DomainError::Rejected(
            "bounded P1 authority is invalid".into(),
        ));
    }
    Ok(())
}

/// Validate a real-event authority before checkpoint planning or opening.
pub fn validate_real_p1_authority(authority: &P1AttemptAuthority) -> Result<(), P1DomainError> {
    validate_authority(authority, false)
}

/// Authority identifiers become descriptor-relative durable-state names. Keep
/// them to a single, portable component before any state root is created.
fn is_safe_authority_identifier(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
}

fn validate_accounting(
    before: &P1AccountingSnapshot,
    after: &P1AccountingSnapshot,
) -> Result<(), P1DomainError> {
    let delta = |before: u64, after: u64| {
        after
            .checked_sub(before)
            .ok_or_else(|| P1DomainError::Rejected("P1 lifecycle counter regressed".into()))
    };
    let balanced = [
        (
            before.managed_created,
            after.managed_created,
            before.managed_destroyed,
            after.managed_destroyed,
        ),
        (
            before.derived_created,
            after.derived_created,
            before.derived_destroyed,
            after.derived_destroyed,
        ),
        (
            before.default_cpu_stream_created,
            after.default_cpu_stream_created,
            before.default_cpu_stream_freed,
            after.default_cpu_stream_freed,
        ),
        (
            before.default_gpu_stream_created,
            after.default_gpu_stream_created,
            before.default_gpu_stream_freed,
            after.default_gpu_stream_freed,
        ),
        (
            before.owned_stream_created,
            after.owned_stream_created,
            before.owned_stream_freed,
            after.owned_stream_freed,
        ),
        (
            before.registrations,
            after.registrations,
            before.teardowns,
            after.teardowns,
        ),
    ];
    for (bc, ac, bd, ad) in balanced {
        if delta(bc, ac)? != delta(bd, ad)? {
            return Err(P1DomainError::Rejected(
                "P1 lifecycle counters did not reconcile".into(),
            ));
        }
    }
    for (logical_before, logical_after, native_before, native_after) in [
        (
            before.default_cpu_stream_freed,
            after.default_cpu_stream_freed,
            before.native_default_cpu_stream_freed,
            after.native_default_cpu_stream_freed,
        ),
        (
            before.default_gpu_stream_freed,
            after.default_gpu_stream_freed,
            before.native_default_gpu_stream_freed,
            after.native_default_gpu_stream_freed,
        ),
        (
            before.owned_stream_freed,
            after.owned_stream_freed,
            before.native_owned_stream_freed,
            after.native_owned_stream_freed,
        ),
    ] {
        if delta(logical_before, logical_after)? != delta(native_before, native_after)? {
            return Err(P1DomainError::Rejected(
                "logical/native free delta mismatch".into(),
            ));
        }
    }
    if after.native_live_stream_handles != before.native_live_stream_handles
        || after.native_duplicate_free_attempts != before.native_duplicate_free_attempts
        || after.native_origin_mismatches != before.native_origin_mismatches
        || after.context_active != 0
        || after.in_flight_work != 0
        || after.stale_native_ready_generations != 0
    {
        return Err(P1DomainError::Rejected(
            "P1 native terminal accounting is not clean".into(),
        ));
    }
    let managed_created = delta(before.managed_created, after.managed_created)?;
    let managed_destroyed = delta(before.managed_destroyed, after.managed_destroyed)?;
    let callback_count = delta(before.callback_count, after.callback_count)?;
    let owned_created = delta(before.owned_stream_created, after.owned_stream_created)?;
    let owned_freed = delta(before.owned_stream_freed, after.owned_stream_freed)?;
    let native_owned_freed = delta(
        before.native_owned_stream_freed,
        after.native_owned_stream_freed,
    )?;
    let registrations = delta(before.registrations, after.registrations)?;
    let teardowns = delta(before.teardowns, after.teardowns)?;
    if managed_created == 0
        || managed_destroyed == 0
        || callback_count == 0
        || callback_count != managed_destroyed
        || owned_created == 0
        || owned_freed == 0
        || native_owned_freed == 0
        || registrations == 0
        || teardowns == 0
    {
        return Err(P1DomainError::Rejected(
            "P1 accounting lacks required live native lifecycle deltas".into(),
        ));
    }
    Ok(())
}

/// Execute one already-authorized bounded step. This function never creates
/// authorization and has no retry, resume, continuation, or second-token path.
pub fn execute_bounded_p1_once(
    state_root: &Path,
    authority: &P1AttemptAuthority,
    runtime: P1RuntimeIdentity,
    math: &mut impl BoundedP1Math,
) -> Result<BoundedP1Receipt, P1DomainError> {
    if math.backend_id().starts_with("INERT_NO_CHECKPOINT_") {
        return Err(P1DomainError::Rejected(
            "inert producer identity rejected by real execution path".into(),
        ));
    }
    execute_bounded_p1_impl(state_root, authority, runtime, math, false)
}

/// Execute the same ownership/accounting/receipt path with a math producer
/// that is statically identified as unable to access a checkpoint. This is
/// qualification authority, never real-event authority.
pub fn execute_inert_bounded_p1_once(
    state_root: &Path,
    authority: &P1AttemptAuthority,
    runtime: P1RuntimeIdentity,
    math: &mut impl BoundedP1Math,
) -> Result<BoundedP1Receipt, P1DomainError> {
    if !math.backend_id().starts_with("INERT_NO_CHECKPOINT_") {
        return Err(P1DomainError::Rejected(
            "inert producer identity rejected".into(),
        ));
    }
    execute_bounded_p1_impl(state_root, authority, runtime, math, true)
}

fn execute_bounded_p1_impl(
    state_root: &Path,
    authority: &P1AttemptAuthority,
    runtime: P1RuntimeIdentity,
    math: &mut impl BoundedP1Math,
    inert_test: bool,
) -> Result<BoundedP1Receipt, P1DomainError> {
    validate_authority(authority, inert_test)?;
    let mut attempt = OwnedAttempt::claim(state_root, authority)?;
    let started = now_ns()?;
    let result = (|| -> Result<BoundedP1Receipt, P1DomainError> {
        let before = P1AccountingSnapshot::capture().map_err(P1DomainError::Rejected)?;
        let token = {
            let context = MlxContext::new(MlxDevice::Gpu, MlxStreamMode::Owned)
                .map_err(P1DomainError::Rejected)?;
            let token = math
                .execute_one(&context, authority.prompt_token)
                .map_err(P1DomainError::Rejected)?;
            context.synchronize().map_err(P1DomainError::Rejected)?;
            token
        };
        let after = P1AccountingSnapshot::capture().map_err(P1DomainError::Rejected)?;
        validate_accounting(&before, &after)?;
        if token != authority.expected_token {
            return Err(P1DomainError::Rejected(format!(
                "bounded P1 token mismatch: expected {}, got {token}",
                authority.expected_token
            )));
        }
        Ok(BoundedP1Receipt {
            schema: RECEIPT_SCHEMA.into(),
            event_class: if inert_test {
                "NATIVE_P1_INERT_MATH_BOUNDARY_REHEARSAL"
            } else {
                "NATIVE_P1_EXECUTION_EVENT"
            }
            .into(),
            authorization_id: authority.authorization_id.clone(),
            attempt_id: authority.attempt_id.clone(),
            domain_declaration_sha256: authority.domain_declaration_sha256.clone(),
            final_review_sha256: authority.final_review_sha256.clone(),
            human_approval_sha256: authority.human_approval_sha256.clone(),
            contract_sha256: authority.contract_sha256.clone(),
            executor_sha256: authority.executor_sha256.clone(),
            git_head: authority.git_head.clone(),
            historical_master_ledger_sha256: authority.historical_master_ledger_sha256.clone(),
            d0_sha256: authority.d0_sha256.clone(),
            d1_sha256: authority.d1_sha256.clone(),
            d2_sha256: authority.d2_sha256.clone(),
            d3_5_result_sha256: authority.d3_5_result_sha256.clone(),
            d3_5_acceptance_sha256: authority.d3_5_acceptance_sha256.clone(),
            synthetic_full_graph_result_sha256: authority
                .synthetic_full_graph_result_sha256
                .clone(),
            checkpoint_manifest_sha256: authority.checkpoint_manifest_sha256.clone(),
            checkpoint_catalog_sha256: authority.checkpoint_catalog_sha256.clone(),
            checkpoint_set_sha256: authority.checkpoint_set_sha256.clone(),
            runtime,
            accounting_before: before,
            accounting_after: after,
            prompt_token: PROMPT_TOKEN,
            result_token: token,
            generated_token_count: 1,
            native_event_delta: u32::from(!inert_test),
            historical_master_before: authority.historical_master_terminal_value,
            historical_master_after: authority.historical_master_terminal_value,
            historical_master_delta: 0,
            mandatory_stop_observed: true,
            execution_result: "EXPECTED_TOKEN_MATCH".into(),
            terminal_state: "COMPLETE_MANDATORY_STOP".into(),
            started_at_unix_ns: started,
            completed_at_unix_ns: now_ns()?,
        })
    })();
    match result {
        Ok(receipt) => {
            let receipt_path = attempt.attempt_dir.join("execution-receipt.json");
            write_exclusive(&receipt_path, &receipt)?;
            let receipt_sha = sha256(&receipt_path)?;
            attempt.terminalize("COMPLETE_MANDATORY_STOP", Some(&receipt_sha))?;
            Ok(receipt)
        }
        Err(error) => {
            attempt.terminalize("TERMINAL_FAILURE_NO_RETRY", None)?;
            Err(error)
        }
    }
}

fn write_hashed(path: &Path, value: &impl Serialize) -> Result<String, P1DomainError> {
    write_exclusive(path, value)?;
    let digest = sha256(path)?;
    if digest.len() != 64 {
        return Err(P1DomainError::Rejected(
            "durable evidence readback failed".into(),
        ));
    }
    Ok(digest)
}

fn failure_diagnostic(
    backend: &str,
    authority: &P1AttemptAuthority,
    token: Option<u32>,
    layers: Vec<P1LayerDiagnostic>,
) -> P1NumericalDiagnosticManifest {
    P1NumericalDiagnosticManifest {
        schema: DIAGNOSTIC_SCHEMA.into(),
        backend: backend.into(),
        serialization: "F32_LE_DIRECT_PRODUCTION_BUFFER_HASHES".into(),
        synchronization: "CONTEXT_SYNCHRONIZED_BEFORE_POST_SNAPSHOT".into(),
        direct_production_bytes: true,
        layers,
        final_hidden_state_sha256: String::new(),
        final_norm_sha256: String::new(),
        full_logits_sha256: String::new(),
        logits_dtype: "little-endian-f32".into(),
        logits_shape: Vec::new(),
        top_token_ids: token.into_iter().collect(),
        top_logit_f32_bits: Vec::new(),
        selected_token: token,
        expected_token: authority.expected_token,
        tie_rule: "LOWEST_TOKEN_ID_ON_EQUAL_F32_LOGIT".into(),
    }
}

fn recover_layer_diagnostics(
    recorder: &P1EvidenceRecorder,
) -> Result<Vec<P1LayerDiagnostic>, P1DomainError> {
    let mut entries =
        fs::read_dir(&recorder.diagnostic_layer_dir)?.collect::<Result<Vec<_>, _>>()?;
    entries.sort_by_key(|entry| entry.file_name());
    let mut layers = Vec::with_capacity(entries.len());
    for (expected, entry) in entries.into_iter().enumerate() {
        let metadata = fs::symlink_metadata(entry.path())?;
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            return Err(P1DomainError::Rejected(
                "unsafe durable layer diagnostic".into(),
            ));
        }
        let layer: P1LayerDiagnostic = serde_json::from_slice(&fs::read(entry.path())?)?;
        if layer.layer as usize != expected {
            return Err(P1DomainError::Rejected(
                "durable layer diagnostic continuity failure".into(),
            ));
        }
        layers.push(layer);
    }
    Ok(layers)
}

/// Forward-only execution generation. Once the RN1 claim exists, every
/// ordinary producer outcome, including token mismatch, banks pre/post
/// snapshots, the incremental access census, a diagnostic manifest, one
/// receipt, and a receipt-bound terminal before returning to the caller.
pub fn execute_evidenced_bounded_p1_once(
    state_root: &Path,
    authority: &P1AttemptAuthority,
    runtime: P1RuntimeIdentity,
    math: &mut impl EvidencedP1Math,
    inert_test: bool,
) -> Result<EvidencedBoundedP1Receipt, P1DomainError> {
    validate_authority(authority, inert_test)?;
    if inert_test != math.backend_id().starts_with("INERT_NO_CHECKPOINT_") {
        return Err(P1DomainError::Rejected(
            "evidenced producer class does not match authority".into(),
        ));
    }
    let mut attempt = OwnedAttempt::claim(state_root, authority)?;
    let started = now_ns()?;
    let before = P1AccountingSnapshot::capture().map_err(P1DomainError::Rejected)?;
    let pre = P1DurableSnapshot {
        schema: SNAPSHOT_SCHEMA.into(),
        phase: "PRE_EXECUTION".into(),
        authorization_id: authority.authorization_id.clone(),
        attempt_id: authority.attempt_id.clone(),
        captured_at_unix_ns: now_ns()?,
        counters: before.clone(),
    };
    let pre_sha = write_hashed(
        &attempt.attempt_dir.join("pre-accounting-snapshot.json"),
        &pre,
    )?;
    let mut recorder = P1EvidenceRecorder::new(&attempt.attempt_dir, authority)?;

    let execution = (|| {
        let context = MlxContext::new(MlxDevice::Gpu, MlxStreamMode::Owned)?;
        let result = math.execute_one_evidenced(&context, authority.prompt_token, &mut recorder);
        let sync_result = context.synchronize();
        drop(context);
        sync_result?;
        result
    })();
    let (produced_token, diagnostic, producer_error) = match execution {
        Ok((token, diagnostic)) => (Some(token), diagnostic, None),
        Err(error) => (
            None,
            failure_diagnostic(
                math.backend_id(),
                authority,
                None,
                recover_layer_diagnostics(&recorder)?,
            ),
            Some(error),
        ),
    };

    let after = P1AccountingSnapshot::capture().map_err(P1DomainError::Rejected)?;
    let post = P1DurableSnapshot {
        schema: SNAPSHOT_SCHEMA.into(),
        phase: "POST_SYNCHRONIZATION_PRE_TOKEN_COMPARISON".into(),
        authorization_id: authority.authorization_id.clone(),
        attempt_id: authority.attempt_id.clone(),
        captured_at_unix_ns: now_ns()?,
        counters: after.clone(),
    };
    let post_sha = write_hashed(
        &attempt.attempt_dir.join("post-accounting-snapshot.json"),
        &post,
    )?;
    let census = recorder.census();
    let census_sha = write_hashed(&attempt.attempt_dir.join("access-census.json"), &census)?;
    let diagnostic_sha = write_hashed(
        &attempt
            .attempt_dir
            .join("numerical-diagnostic-manifest.json"),
        &diagnostic,
    )?;

    let accounting_error = validate_accounting(&before, &after)
        .err()
        .map(|error| error.to_string());
    let (execution_result, terminal_state, error_class) = if let Some(error) = producer_error {
        (
            "PRODUCER_FAILURE",
            "TERMINAL_FAILURE_NO_RETRY",
            Some(format!("PRODUCER_FAILURE:{error}")),
        )
    } else if let Some(error) = accounting_error {
        (
            "ACCOUNTING_FAILURE",
            "TERMINAL_FAILURE_NO_RETRY",
            Some(format!("ACCOUNTING_FAILURE:{error}")),
        )
    } else if produced_token != Some(authority.expected_token) {
        (
            "TOKEN_MISMATCH",
            "TERMINAL_FAILURE_NO_RETRY",
            Some("TOKEN_MISMATCH".into()),
        )
    } else {
        ("EXPECTED_TOKEN_MATCH", "COMPLETE_MANDATORY_STOP", None)
    };
    let receipt = EvidencedBoundedP1Receipt {
        schema: EVIDENCED_RECEIPT_SCHEMA.into(),
        event_class: if inert_test {
            "NATIVE_P1_INERT_MATH_BOUNDARY_REHEARSAL"
        } else {
            "NATIVE_P1_EXECUTION_EVENT"
        }
        .into(),
        authorization_id: authority.authorization_id.clone(),
        attempt_id: authority.attempt_id.clone(),
        contract_sha256: authority.contract_sha256.clone(),
        executor_sha256: authority.executor_sha256.clone(),
        git_head: authority.git_head.clone(),
        checkpoint_manifest_sha256: authority.checkpoint_manifest_sha256.clone(),
        checkpoint_catalog_sha256: authority.checkpoint_catalog_sha256.clone(),
        checkpoint_set_sha256: authority.checkpoint_set_sha256.clone(),
        historical_master_ledger_sha256: authority.historical_master_ledger_sha256.clone(),
        historical_master_before: authority.historical_master_terminal_value,
        historical_master_after: authority.historical_master_terminal_value,
        historical_master_delta: 0,
        native_event_delta: u32::from(!inert_test),
        runtime,
        pre_snapshot_sha256: pre_sha.clone(),
        post_snapshot_sha256: post_sha.clone(),
        access_census_sha256: census_sha.clone(),
        numerical_diagnostic_manifest_sha256: diagnostic_sha.clone(),
        prompt_token: authority.prompt_token,
        expected_token: authority.expected_token,
        produced_token,
        generated_token_count: u32::from(produced_token.is_some()),
        execution_result: execution_result.into(),
        error_class: error_class.clone(),
        mandatory_stop_observed: true,
        terminal_state: terminal_state.into(),
        started_at_unix_ns: started,
        completed_at_unix_ns: now_ns()?,
    };
    let receipt_sha = write_hashed(
        &attempt.attempt_dir.join("execution-receipt.json"),
        &receipt,
    )?;
    attempt.terminalize_evidenced(
        terminal_state,
        &receipt_sha,
        &pre_sha,
        &post_sha,
        &census_sha,
        &diagnostic_sha,
        produced_token,
        error_class.as_deref(),
    )?;
    if error_class.is_some() {
        return Err(P1DomainError::Rejected(format!(
            "bounded P1 terminal evidence banked: {execution_result}"
        )));
    }
    Ok(receipt)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::MlxArray;
    use std::sync::Mutex;

    static NATIVE_CONTEXT_TEST_LOCK: Mutex<()> = Mutex::new(());

    struct InertMath {
        invocations: u32,
    }

    impl BoundedP1Math for InertMath {
        fn backend_id(&self) -> &'static str {
            "INERT_NO_CHECKPOINT_MATH"
        }

        fn execute_one(&mut self, context: &MlxContext, prompt_token: u32) -> Result<u32, String> {
            if prompt_token != PROMPT_TOKEN || self.invocations != 0 {
                return Err("inert bounded step rejected".into());
            }
            self.invocations += 1;
            let mut values = vec![1.0_f32, -1.0, 0.0, -0.0];
            let source: MlxArray<'_> = context.import_f32(&mut values)?;
            let derived = source.add_self()?;
            source.destroy()?;
            derived.destroy()?;
            Ok(EXPECTED_TOKEN)
        }
    }

    fn authority() -> P1AttemptAuthority {
        P1AttemptAuthority {
            authorization_id: "INERT-AUTH-1".into(),
            attempt_id: "INERT-ATTEMPT-1".into(),
            domain_declaration_sha256: "8".repeat(64),
            final_review_sha256: "9".repeat(64),
            human_approval_sha256: "0".repeat(64),
            contract_sha256: "a".repeat(64),
            executor_sha256: "b".repeat(64),
            git_head: "c".repeat(40),
            historical_master_ledger_sha256: "d".repeat(64),
            d0_sha256: "e".repeat(64),
            d1_sha256: "f".repeat(64),
            d2_sha256: "1".repeat(64),
            d3_5_result_sha256: "4".repeat(64),
            d3_5_acceptance_sha256: "5".repeat(64),
            synthetic_full_graph_result_sha256: "6".repeat(64),
            checkpoint_manifest_sha256: "2".repeat(64),
            checkpoint_catalog_sha256: "7".repeat(64),
            checkpoint_set_sha256: "3".repeat(64),
            historical_master_terminal_value: 175,
            prompt_token: PROMPT_TOKEN,
            expected_token: EXPECTED_TOKEN,
            attempts: 1,
            retries: 0,
            resume: false,
            mandatory_stop: true,
            real_event_authorized: false,
        }
    }

    fn runtime() -> P1RuntimeIdentity {
        P1RuntimeIdentity {
            mlx_version: "0.31.2".into(),
            mlx_c_version: "0.6.0".into(),
            architecture: "arm64".into(),
            machine_brand: "Apple M1 Ultra".into(),
            stream_origin: "OWNED_DEVICE".into(),
            native_handle_owned: true,
            deallocation_responsibility: "THIS_EXECUTOR".into(),
        }
    }

    #[test]
    fn inert_math_only_boundary_emits_real_receipt_and_replay_fails() {
        let _serial = NATIVE_CONTEXT_TEST_LOCK.lock().unwrap();
        let root = std::env::temp_dir().join(format!("f017-p1-inert-{}", now_ns().unwrap()));
        let mut math = InertMath { invocations: 0 };
        let receipt =
            execute_inert_bounded_p1_once(&root, &authority(), runtime(), &mut math).unwrap();
        assert_eq!(math.invocations, 1);
        assert_eq!(receipt.result_token, EXPECTED_TOKEN);
        assert_eq!(receipt.accounting_before.context_active, 0);
        assert_eq!(receipt.accounting_after.context_active, 0);
        assert_eq!(receipt.accounting_after.in_flight_work, 0);
        assert!(root
            .join("INERT-ATTEMPT-1/execution-receipt.json")
            .is_file());
        assert!(root.join("INERT-ATTEMPT-1/terminal.json").is_file());
        let mut second = InertMath { invocations: 0 };
        assert!(
            execute_inert_bounded_p1_once(&root, &authority(), runtime(), &mut second).is_err()
        );
        assert_eq!(second.invocations, 0);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn all_zero_or_stale_accounting_snapshot_is_rejected() {
        let snapshot = P1AccountingSnapshot::default();
        assert!(validate_accounting(&snapshot, &snapshot).is_err());
    }

    #[test]
    fn wrong_result_consumes_attempt_and_banks_failure_terminal() {
        let _serial = NATIVE_CONTEXT_TEST_LOCK.lock().unwrap();
        struct Wrong;
        impl BoundedP1Math for Wrong {
            fn backend_id(&self) -> &'static str {
                "INERT_NO_CHECKPOINT_WRONG"
            }
            fn execute_one(
                &mut self,
                _context: &MlxContext,
                _prompt_token: u32,
            ) -> Result<u32, String> {
                Ok(7)
            }
        }
        let root = std::env::temp_dir().join(format!("f017-p1-wrong-{}", now_ns().unwrap()));
        assert!(execute_inert_bounded_p1_once(&root, &authority(), runtime(), &mut Wrong).is_err());
        let terminal = fs::read_to_string(root.join("INERT-ATTEMPT-1/terminal.json")).unwrap();
        assert!(terminal.contains("TERMINAL_FAILURE_NO_RETRY"));
        assert!(execute_inert_bounded_p1_once(&root, &authority(), runtime(), &mut Wrong).is_err());
        fs::remove_dir_all(root).unwrap();
    }

    struct EvidencedInertMath {
        token: u32,
        invocations: u32,
    }

    impl EvidencedP1Math for EvidencedInertMath {
        fn backend_id(&self) -> &'static str {
            "INERT_NO_CHECKPOINT_EVIDENCED_MATH"
        }

        fn execute_one_evidenced(
            &mut self,
            context: &MlxContext,
            prompt_token: u32,
            recorder: &mut P1EvidenceRecorder,
        ) -> Result<(u32, P1NumericalDiagnosticManifest), String> {
            if prompt_token != PROMPT_TOKEN || self.invocations != 0 {
                return Err("inert evidenced bounded step rejected".into());
            }
            self.invocations += 1;
            recorder.record(
                "TENSOR_FIRST_USE",
                "synthetic.tensor",
                &"a".repeat(64),
                16,
                Some("synthetic.tensor"),
                "PASS",
            )?;
            let mut values = vec![1.0_f32, -1.0, 0.0, -0.0];
            let source: MlxArray<'_> = context.import_f32(&mut values)?;
            let derived = source.add_self()?;
            source.destroy()?;
            derived.destroy()?;
            Ok((
                self.token,
                P1NumericalDiagnosticManifest {
                    schema: DIAGNOSTIC_SCHEMA.into(),
                    backend: self.backend_id().into(),
                    serialization: "F32_LE_DIRECT_PRODUCTION_BUFFER_HASHES".into(),
                    synchronization: "CONTEXT_SYNCHRONIZED_BEFORE_POST_SNAPSHOT".into(),
                    direct_production_bytes: true,
                    layers: Vec::new(),
                    final_hidden_state_sha256: "b".repeat(64),
                    final_norm_sha256: "c".repeat(64),
                    full_logits_sha256: "d".repeat(64),
                    logits_dtype: "little-endian-f32".into(),
                    logits_shape: vec![4],
                    top_token_ids: vec![self.token],
                    top_logit_f32_bits: vec![1.0_f32.to_bits()],
                    selected_token: Some(self.token),
                    expected_token: EXPECTED_TOKEN,
                    tie_rule: "LOWEST_TOKEN_ID_ON_EQUAL_F32_LOGIT".into(),
                },
            ))
        }
    }

    #[test]
    fn evidenced_token_mismatch_banks_complete_failure_evidence_before_returning() {
        let _serial = NATIVE_CONTEXT_TEST_LOCK.lock().unwrap();
        let root =
            std::env::temp_dir().join(format!("f017-p1-evidenced-mismatch-{}", now_ns().unwrap()));
        let mut math = EvidencedInertMath {
            token: 7,
            invocations: 0,
        };
        assert!(
            execute_evidenced_bounded_p1_once(&root, &authority(), runtime(), &mut math, true,)
                .is_err()
        );
        let attempt = root.join("INERT-ATTEMPT-1");
        for file in [
            "pre-accounting-snapshot.json",
            "post-accounting-snapshot.json",
            "access-census.json",
            "numerical-diagnostic-manifest.json",
            "execution-receipt.json",
            "terminal.json",
        ] {
            assert!(attempt.join(file).is_file(), "missing {file}");
        }
        let receipt = fs::read_to_string(attempt.join("execution-receipt.json")).unwrap();
        assert!(receipt.contains("TOKEN_MISMATCH"));
        assert!(receipt.contains("\"produced_token\":7"));
        let terminal = fs::read_to_string(attempt.join("terminal.json")).unwrap();
        assert!(terminal.contains("TERMINAL_FAILURE_NO_RETRY"));
        assert!(terminal.contains("receipt_sha256"));
        let mut second = EvidencedInertMath {
            token: EXPECTED_TOKEN,
            invocations: 0,
        };
        assert!(execute_evidenced_bounded_p1_once(
            &root,
            &authority(),
            runtime(),
            &mut second,
            true,
        )
        .is_err());
        assert_eq!(second.invocations, 0);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn evidenced_mid_execution_failure_retains_maximum_post_start_evidence() {
        let _serial = NATIVE_CONTEXT_TEST_LOCK.lock().unwrap();
        struct FailsAfterFirstUse;
        impl EvidencedP1Math for FailsAfterFirstUse {
            fn backend_id(&self) -> &'static str {
                "INERT_NO_CHECKPOINT_FAILURE_INJECTION"
            }
            fn execute_one_evidenced(
                &mut self,
                context: &MlxContext,
                _prompt_token: u32,
                recorder: &mut P1EvidenceRecorder,
            ) -> Result<(u32, P1NumericalDiagnosticManifest), String> {
                recorder.record(
                    "TENSOR_FIRST_USE",
                    "synthetic.middle-layer",
                    &"e".repeat(64),
                    16,
                    Some("synthetic.middle-layer"),
                    "PASS",
                )?;
                recorder.bank_layer_diagnostic(&P1LayerDiagnostic {
                    layer: 0,
                    layer_input_sha256: "f".repeat(64),
                    post_attention_residual_sha256: "f".repeat(64),
                    router_normalized_input_sha256: "f".repeat(64),
                    selected_expert_ids: vec![0],
                    routing_weight_f32_bits: vec![1.0_f32.to_bits()],
                    routed_aggregate_sha256: "f".repeat(64),
                    shared_expert_sha256: "f".repeat(64),
                    layer_output_sha256: "f".repeat(64),
                    hidden_width: 4,
                    dtype: "little-endian-f32".into(),
                    byte_order: "coordinate-major-contiguous".into(),
                })?;
                let mut values = vec![2.0_f32, -2.0, 0.5, -0.5];
                let source: MlxArray<'_> = context.import_f32(&mut values)?;
                let derived = source.add_self()?;
                source.destroy()?;
                derived.destroy()?;
                Err("INJECTED_MIDDLE_LAYER_FAILURE".into())
            }
        }
        let root =
            std::env::temp_dir().join(format!("f017-p1-evidenced-injected-{}", now_ns().unwrap()));
        assert!(execute_evidenced_bounded_p1_once(
            &root,
            &authority(),
            runtime(),
            &mut FailsAfterFirstUse,
            true,
        )
        .is_err());
        let attempt = root.join("INERT-ATTEMPT-1");
        let receipt = fs::read_to_string(attempt.join("execution-receipt.json")).unwrap();
        assert!(receipt.contains("PRODUCER_FAILURE"));
        assert!(receipt.contains("INJECTED_MIDDLE_LAYER_FAILURE"));
        assert!(attempt.join("pre-accounting-snapshot.json").is_file());
        assert!(attempt.join("post-accounting-snapshot.json").is_file());
        assert!(attempt.join("access-census.json").is_file());
        assert!(attempt.join("diagnostic-layers/00000000.json").is_file());
        let diagnostics =
            fs::read_to_string(attempt.join("numerical-diagnostic-manifest.json")).unwrap();
        assert!(diagnostics.contains("\"layer\":0"));
        assert!(attempt.join("terminal.json").is_file());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn evidenced_failure_matrix_banks_receipt_and_terminal_for_ordinary_post_start_failures() {
        let _serial = NATIVE_CONTEXT_TEST_LOCK.lock().unwrap();

        #[derive(Clone, Copy, Debug)]
        enum FailurePoint {
            FirstShardOpen,
            PartialMap,
            TensorPlan,
            FirstTensorUse,
            MiddleLayer,
            FinalNorm,
            Logits,
        }

        struct InjectedFailure(FailurePoint);
        impl EvidencedP1Math for InjectedFailure {
            fn backend_id(&self) -> &'static str {
                "INERT_NO_CHECKPOINT_FAILURE_MATRIX"
            }

            fn execute_one_evidenced(
                &mut self,
                context: &MlxContext,
                _prompt_token: u32,
                recorder: &mut P1EvidenceRecorder,
            ) -> Result<(u32, P1NumericalDiagnosticManifest), String> {
                // Exercise the real context, ownership, accounting, event writer,
                // snapshot, receipt, and terminal paths. Only tensor math and the
                // checkpoint substrate are inert.
                let mut values = vec![1.0_f32, -1.0, 0.25, -0.25];
                let source: MlxArray<'_> = context.import_f32(&mut values)?;
                let derived = source.add_self()?;
                source.destroy()?;
                derived.destroy()?;

                let (kind, authority, tensor, result) = match self.0 {
                    FailurePoint::FirstShardOpen => {
                        ("SHARD_OPEN", "synthetic.shard.0", None, "INJECTED_FAILURE")
                    }
                    FailurePoint::PartialMap => (
                        "READ_ONLY_PRIVATE_MMAP",
                        "synthetic.shard.0",
                        None,
                        "INJECTED_PARTIAL_MAP_FAILURE",
                    ),
                    FailurePoint::TensorPlan => (
                        "UNEXPECTED_ACCESS_ATTEMPT",
                        "synthetic.tensor-plan",
                        Some("synthetic.missing"),
                        "INJECTED_TENSOR_PLAN_FAILURE",
                    ),
                    FailurePoint::FirstTensorUse => (
                        "TENSOR_FIRST_USE",
                        "synthetic.tensor.0",
                        Some("synthetic.tensor.0"),
                        "INJECTED_FAILURE",
                    ),
                    FailurePoint::MiddleLayer => (
                        "TENSOR_FIRST_USE",
                        "synthetic.layer.39",
                        Some("synthetic.layer.39"),
                        "INJECTED_MIDDLE_LAYER_FAILURE",
                    ),
                    FailurePoint::FinalNorm => (
                        "TENSOR_FIRST_USE",
                        "synthetic.final_norm",
                        Some("synthetic.final_norm"),
                        "INJECTED_FINAL_NORM_FAILURE",
                    ),
                    FailurePoint::Logits => (
                        "TENSOR_FIRST_USE",
                        "synthetic.output",
                        Some("synthetic.output"),
                        "INJECTED_LOGITS_FAILURE",
                    ),
                };
                recorder.record(kind, authority, &"e".repeat(64), 16, tensor, result)?;
                Err(format!("INJECTED_{:?}", self.0))
            }
        }

        for point in [
            FailurePoint::FirstShardOpen,
            FailurePoint::PartialMap,
            FailurePoint::TensorPlan,
            FailurePoint::FirstTensorUse,
            FailurePoint::MiddleLayer,
            FailurePoint::FinalNorm,
            FailurePoint::Logits,
        ] {
            let root = std::env::temp_dir().join(format!(
                "f017-p1-evidenced-matrix-{point:?}-{}",
                now_ns().unwrap()
            ));
            assert!(execute_evidenced_bounded_p1_once(
                &root,
                &authority(),
                runtime(),
                &mut InjectedFailure(point),
                true,
            )
            .is_err());
            let attempt = root.join("INERT-ATTEMPT-1");
            for file in [
                "pre-accounting-snapshot.json",
                "post-accounting-snapshot.json",
                "access-census.json",
                "numerical-diagnostic-manifest.json",
                "execution-receipt.json",
                "terminal.json",
            ] {
                assert!(attempt.join(file).is_file(), "{point:?}: missing {file}");
            }
            let receipt: EvidencedBoundedP1Receipt =
                serde_json::from_slice(&fs::read(attempt.join("execution-receipt.json")).unwrap())
                    .unwrap();
            assert_eq!(receipt.execution_result, "PRODUCER_FAILURE");
            assert!(receipt.error_class.unwrap().contains("INJECTED_"));
            let terminal = fs::read_to_string(attempt.join("terminal.json")).unwrap();
            assert!(terminal.contains("TERMINAL_FAILURE_NO_RETRY"));
            assert!(terminal.contains("receipt_sha256"));
            fs::remove_dir_all(root).unwrap();
        }
    }

    #[test]
    fn authority_identifiers_cannot_escape_the_owned_state_root() {
        let _serial = NATIVE_CONTEXT_TEST_LOCK.lock().unwrap();
        for (authorization_id, attempt_id) in [
            ("INERT-AUTH-1", "../../ESCAPED"),
            ("INERT-AUTH-1", "/tmp/F017-ESCAPED"),
            ("../AUTH", "INERT-ATTEMPT-1"),
            ("INERT/AUTH", "INERT-ATTEMPT-1"),
            ("INERT\0AUTH", "INERT-ATTEMPT-1"),
        ] {
            let root = std::env::temp_dir().join(format!(
                "f017-p1-unsafe-id-{}-{}",
                std::process::id(),
                now_ns().unwrap()
            ));
            let mut candidate = authority();
            candidate.authorization_id = authorization_id.into();
            candidate.attempt_id = attempt_id.into();
            let mut math = InertMath { invocations: 0 };
            assert!(
                execute_inert_bounded_p1_once(&root, &candidate, runtime(), &mut math).is_err()
            );
            assert_eq!(math.invocations, 0);
            assert!(!root.exists(), "unsafe identifier created durable state");
        }
    }
}
