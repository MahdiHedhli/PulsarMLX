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

pub const RECEIPT_SCHEMA: &str = "pulsarmlx.f017.native-bounded-p1-execution-receipt/1.0.0";
pub const TERMINAL_SCHEMA: &str = "pulsarmlx.f017.native-bounded-p1-terminal/1.0.0";
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
    pub contract_sha256: String,
    pub executor_sha256: String,
    pub git_head: String,
    pub historical_master_ledger_sha256: String,
    pub d0_sha256: String,
    pub d1_sha256: String,
    pub d2_sha256: String,
    pub checkpoint_manifest_sha256: String,
    pub checkpoint_set_sha256: String,
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
    pub contract_sha256: String,
    pub executor_sha256: String,
    pub git_head: String,
    pub historical_master_ledger_sha256: String,
    pub d0_sha256: String,
    pub d1_sha256: String,
    pub d2_sha256: String,
    pub checkpoint_manifest_sha256: String,
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

/// Only the tensor/kernel computation is replaceable. It receives an already
/// owned native context and returns exactly one token or fails.
pub trait BoundedP1Math {
    fn backend_id(&self) -> &'static str;
    fn execute_one(&mut self, context: &MlxContext, prompt_token: u32) -> Result<u32, String>;
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
}

fn validate_authority(
    authority: &P1AttemptAuthority,
    inert_test: bool,
) -> Result<(), P1DomainError> {
    let sha256_hashes = [
        &authority.contract_sha256,
        &authority.executor_sha256,
        &authority.historical_master_ledger_sha256,
        &authority.d0_sha256,
        &authority.d1_sha256,
        &authority.d2_sha256,
        &authority.checkpoint_manifest_sha256,
        &authority.checkpoint_set_sha256,
    ];
    if sha256_hashes.iter().any(|value| value.len() != 64)
        || authority.git_head.len() != 40
        || authority.authorization_id.is_empty()
        || authority.attempt_id.is_empty()
        || authority.prompt_token != PROMPT_TOKEN
        || authority.expected_token != EXPECTED_TOKEN
        || authority.attempts != 1
        || authority.retries != 0
        || authority.resume
        || !authority.mandatory_stop
        || authority.real_event_authorized == inert_test
    {
        return Err(P1DomainError::Rejected(
            "bounded P1 authority is invalid".into(),
        ));
    }
    Ok(())
}

fn validate_accounting(
    before: &P1AccountingSnapshot,
    after: &P1AccountingSnapshot,
) -> Result<(), P1DomainError> {
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
    if balanced.iter().any(|(bc, ac, bd, ad)| ac - bc != ad - bd) {
        return Err(P1DomainError::Rejected(
            "P1 lifecycle counters did not reconcile".into(),
        ));
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
        if logical_after - logical_before != native_after - native_before {
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
            contract_sha256: authority.contract_sha256.clone(),
            executor_sha256: authority.executor_sha256.clone(),
            git_head: authority.git_head.clone(),
            historical_master_ledger_sha256: authority.historical_master_ledger_sha256.clone(),
            d0_sha256: authority.d0_sha256.clone(),
            d1_sha256: authority.d1_sha256.clone(),
            d2_sha256: authority.d2_sha256.clone(),
            checkpoint_manifest_sha256: authority.checkpoint_manifest_sha256.clone(),
            checkpoint_set_sha256: authority.checkpoint_set_sha256.clone(),
            runtime,
            accounting_before: before,
            accounting_after: after,
            prompt_token: PROMPT_TOKEN,
            result_token: token,
            generated_token_count: 1,
            native_event_delta: u32::from(!inert_test),
            historical_master_before: 175,
            historical_master_after: 175,
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
            contract_sha256: "a".repeat(64),
            executor_sha256: "b".repeat(64),
            git_head: "c".repeat(40),
            historical_master_ledger_sha256: "d".repeat(64),
            d0_sha256: "e".repeat(64),
            d1_sha256: "f".repeat(64),
            d2_sha256: "1".repeat(64),
            checkpoint_manifest_sha256: "2".repeat(64),
            checkpoint_set_sha256: "3".repeat(64),
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
}
