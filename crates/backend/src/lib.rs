//! Backend-neutral contracts for PulsarMLX inference runtimes.

pub mod capability;
pub mod error;
pub mod evidence;
pub mod generation;
pub mod routing;
pub mod runtime;
pub mod tensor;

pub use capability::{BackendCapabilityReport, BackendSelection, CapabilityProbe, DeviceState};
pub use error::{ContractError, ErrorCategory, MAX_ERROR_MESSAGE_CHARS};
pub use evidence::{
    ActualStatus, BenchmarkDescriptor, BenchmarkRecord, CompatibilityCellDescriptor,
    CompatibilityEvidenceLevel, CompatibilityMatrix, CompatibilityMatrixDescriptor,
    CompatibilityStatus, EvidenceStatus, GitDirtyState, MemoryGaugeDescriptor, MemoryGauges,
    ModelCompatibilityDescriptor, ModelCompatibilityRecord, ModelSupportStatus,
    QuantizationCompatibilityDescriptor, QuantizationCompatibilityRecord, QuantizationStatus,
    ValidationCase, ValidationDescriptor,
};
pub use generation::{
    generate_greedy, GenerationRequest, GenerationResult, GenerationStep, TerminationReason,
    MAX_NEW_TOKENS, MAX_PROMPT_TOKENS, MAX_TOPK,
};
pub use routing::RoutingPlan;
pub use runtime::{
    ArchitecturePlugin, AttentionState, CancellationToken, CheckpointIdentity, ExpertRequest,
    ExpertRuntime, GenerationState, Glm52Plugin, LayerExecutor, LayerRequest, LogitsOutput,
    LogitsRuntime, MemoryBudget, RuntimeBackend, RuntimeBuffer, RuntimeConfig, RuntimeDevice,
    RuntimeTelemetryEvent, RuntimeTensor, TelemetryCategory, TelemetryScope, TelemetrySink,
    TensorCatalog, TensorRange, TensorStore, ValidationPolicy,
};
pub use tensor::{
    BroadcastRule, ComparisonMode, ComparisonPolicy, ComparisonResult, DType, FirstMismatch,
    NonFinitePolicy, QuantizationId, SynchronizationRule, TensorContract, TensorDescriptor,
    TensorLayout,
};
