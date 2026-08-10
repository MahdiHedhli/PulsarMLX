use crate::{ContractError, ErrorCategory};
use std::time::Duration;

const SHA256_HEX_LENGTH: usize = 64;
const MAX_RUNTIME_ID_CHARS: usize = 256;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CheckpointIdentity {
    pub checkpoint_set_sha256: String,
    pub immutable_revision: String,
}

impl CheckpointIdentity {
    pub fn try_new(
        checkpoint_set_sha256: impl Into<String>,
        immutable_revision: impl Into<String>,
    ) -> Result<Self, ContractError> {
        let checkpoint_set_sha256 = checkpoint_set_sha256.into();
        let immutable_revision = immutable_revision.into();
        if !is_sha256(&checkpoint_set_sha256) {
            return Err(contract_error(
                ErrorCategory::InvalidModel,
                "invalid_checkpoint_hash",
                "checkpoint set identity must be a SHA-256 digest",
            ));
        }
        validate_id(&immutable_revision, "invalid_checkpoint_revision")?;
        Ok(Self {
            checkpoint_set_sha256,
            immutable_revision,
        })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TensorRange {
    pub offset: u64,
    pub length: u64,
}

impl TensorRange {
    pub fn end(self) -> Result<u64, ContractError> {
        self.offset.checked_add(self.length).ok_or_else(|| {
            contract_error(
                ErrorCategory::ArithmeticOverflow,
                "tensor_range_overflow",
                "tensor range end overflow",
            )
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RuntimeTensor {
    pub name: String,
    pub shard: String,
    pub range: TensorRange,
    pub shape: Vec<u64>,
    pub quantization: String,
}

pub trait TensorCatalog {
    fn tensor(&self, name: &str) -> Result<Option<RuntimeTensor>, ContractError>;
}

pub trait TensorStore {
    fn read_range(
        &self,
        tensor: &RuntimeTensor,
        destination: &mut [u8],
        cancellation: &CancellationToken,
    ) -> Result<usize, ContractError>;
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MemoryBudget {
    pub host_total_bytes: u64,
    pub safety_reserve_bytes: u64,
    pub max_resident_bytes: u64,
}

impl MemoryBudget {
    pub fn try_new(
        host_total_bytes: u64,
        safety_reserve_bytes: u64,
        max_resident_bytes: u64,
    ) -> Result<Self, ContractError> {
        if safety_reserve_bytes >= host_total_bytes
            || max_resident_bytes > host_total_bytes - safety_reserve_bytes
        {
            return Err(contract_error(
                ErrorCategory::ResourceLimit,
                "invalid_memory_budget",
                "memory budget exceeds host headroom",
            ));
        }
        Ok(Self {
            host_total_bytes,
            safety_reserve_bytes,
            max_resident_bytes,
        })
    }

    pub const fn admits(self, resident_bytes: u64) -> bool {
        resident_bytes <= self.max_resident_bytes
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RuntimeDevice {
    Cpu,
    AppleGpu,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RuntimeBackend {
    Reference,
    NativeMlx,
    Metal,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ValidationPolicy {
    GoldenStrict,
    TeacherForcedValidation,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RuntimeConfig {
    pub checkpoint: CheckpointIdentity,
    pub memory: MemoryBudget,
    pub device: RuntimeDevice,
    pub backend: RuntimeBackend,
    pub validation: ValidationPolicy,
    pub deterministic: bool,
}

#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct CancellationToken {
    cancelled: bool,
}

impl CancellationToken {
    pub const fn new() -> Self {
        Self { cancelled: false }
    }

    pub const fn is_cancelled(self) -> bool {
        self.cancelled
    }

    pub fn cancel(&mut self) {
        self.cancelled = true;
    }

    pub fn check(self) -> Result<(), ContractError> {
        if self.cancelled {
            Err(contract_error(
                ErrorCategory::InvalidStateTransition,
                "cancelled",
                "runtime operation was cancelled",
            ))
        } else {
            Ok(())
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct LayerRequest {
    pub layer: u32,
    pub generation_position: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RuntimeBuffer {
    pub slot_id: u64,
    pub byte_length: u64,
}

pub trait ArchitecturePlugin {
    fn architecture_id(&self) -> &str;
}

#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct Glm52Plugin;

impl ArchitecturePlugin for Glm52Plugin {
    fn architecture_id(&self) -> &str {
        "glm52"
    }
}

pub trait LayerExecutor {
    fn execute_layer(
        &mut self,
        request: LayerRequest,
        cancellation: &CancellationToken,
    ) -> Result<RuntimeBuffer, ContractError>;
}

pub trait AttentionState {
    fn position(&self) -> u64;
    fn reset(&mut self);
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ExpertRequest {
    pub layer: u32,
    pub expert: u32,
    pub bytes: u64,
}

pub trait ExpertRuntime {
    fn resolve(
        &mut self,
        request: ExpertRequest,
        cancellation: &CancellationToken,
    ) -> Result<RuntimeBuffer, ContractError>;
}

#[derive(Debug, Clone, PartialEq)]
pub struct LogitsOutput {
    pub topk: Vec<(u32, f32)>,
    pub argmax: u32,
}

pub trait LogitsRuntime {
    fn logits(&mut self, cancellation: &CancellationToken) -> Result<LogitsOutput, ContractError>;
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct GenerationState {
    tokens: Vec<u32>,
    position: u64,
}

impl GenerationState {
    pub fn push_token(&mut self, token: u32) -> Result<(), ContractError> {
        self.tokens.push(token);
        self.position = self.position.checked_add(1).ok_or_else(|| {
            contract_error(
                ErrorCategory::ArithmeticOverflow,
                "generation_position_overflow",
                "generation position overflow",
            )
        })?;
        Ok(())
    }

    pub fn tokens(&self) -> &[u32] {
        &self.tokens
    }

    pub const fn position(&self) -> u64 {
        self.position
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TelemetryCategory {
    Storage,
    Decode,
    Materialization,
    BackendImportBuild,
    Compute,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TelemetryScope {
    pub layer: Option<u32>,
    pub expert: Option<u32>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RuntimeTelemetryEvent {
    pub category: TelemetryCategory,
    pub scope: TelemetryScope,
    pub elapsed: Duration,
    pub bytes: u64,
    pub requests: u64,
}

pub trait TelemetrySink {
    fn record(&mut self, event: RuntimeTelemetryEvent) -> Result<(), ContractError>;
}

fn is_sha256(value: &str) -> bool {
    value.len() == SHA256_HEX_LENGTH && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn validate_id(value: &str, code: &'static str) -> Result<(), ContractError> {
    if value.is_empty()
        || value.chars().count() > MAX_RUNTIME_ID_CHARS
        || !value.chars().all(|character| {
            character.is_ascii_alphanumeric() || matches!(character, '.' | '-' | '_' | '/')
        })
    {
        return Err(contract_error(
            ErrorCategory::InvalidModel,
            code,
            "runtime identity is empty or malformed",
        ));
    }
    Ok(())
}

fn contract_error(
    category: ErrorCategory,
    code: &'static str,
    message: &'static str,
) -> ContractError {
    ContractError::new(category, code, message)
}

#[cfg(test)]
mod tests {
    use super::*;

    const CHECKPOINT: &str = "0b38dfc3b79bf6dd3eac3c80cd2b62cb6eb46b2f84e3e51c1a340ad1876c1a42";

    #[test]
    fn checkpoint_and_budget_contracts_fail_closed() {
        assert!(CheckpointIdentity::try_new(CHECKPOINT, "f016-gguf-trunk-inventory-0001").is_ok());
        assert!(CheckpointIdentity::try_new("bad", "revision").is_err());
        assert!(MemoryBudget::try_new(64, 24, 40).is_ok());
        assert!(MemoryBudget::try_new(64, 24, 41).is_err());
    }

    #[test]
    fn tensor_range_and_cancellation_are_checked() {
        assert_eq!(
            TensorRange {
                offset: 4,
                length: 8
            }
            .end()
            .unwrap(),
            12
        );
        assert!(TensorRange {
            offset: u64::MAX,
            length: 1,
        }
        .end()
        .is_err());
        let mut token = CancellationToken::new();
        assert!(token.check().is_ok());
        token.cancel();
        assert!(token.check().is_err());
    }

    #[test]
    fn generation_state_is_monotonic_and_telemetry_is_attributed() {
        let mut state = GenerationState::default();
        state.push_token(9703).unwrap();
        state.push_token(21615).unwrap();
        assert_eq!(state.tokens(), [9703, 21615]);
        assert_eq!(state.position(), 2);
        let event = RuntimeTelemetryEvent {
            category: TelemetryCategory::Decode,
            scope: TelemetryScope {
                layer: Some(3),
                expert: Some(15),
            },
            elapsed: Duration::from_millis(1),
            bytes: 64,
            requests: 1,
        };
        assert_eq!(event.scope.layer, Some(3));
        assert_eq!(event.scope.expert, Some(15));
    }

    #[test]
    fn glm_plugin_is_only_an_architecture_boundary_stub() {
        assert_eq!(Glm52Plugin.architecture_id(), "glm52");
    }
}
