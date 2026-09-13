//! Apple MLX worker client for PulsarMLX.

pub mod client;
pub mod device;
pub mod model;
pub mod protocol;
pub mod qwen3moe;
pub mod qwen3moe_attention;
pub mod qwen3moe_context;
pub mod qwen3moe_runtime;
pub mod qwen3moe_storage;
pub mod router;

pub use backend::DeviceState;
pub use client::{
    CleanupOutcome, CleanupReport, HealthReport, WorkerClient, WorkerConfig, WorkerTimeouts,
    MODEL_FILE_DESCRIPTOR,
};
pub use device::{
    validate_device_smoke, DeviceHello, DeviceProbe, DeviceSmokeError, DeviceSmokeErrorCode,
    DeviceSmokeReport, PINNED_MLX_VERSION,
};
pub use model::{
    admit_qwen3_q8_0_slice, frozen_qwen_model_memory_budget, inspect_external_qwen_model,
    AdmittedModelSlice, ExternalFileIdentity, ExternalModelInspection, ExternalRouterInspection,
    ModelAdmissionDescriptor, ModelExecutionDepth, ModelIdentityDescriptor, ModelMemoryBudget,
    ModelMetadataDescriptor, ModelTensorDescriptor, QWEN_ENCODED_SLICE_BYTES, QWEN_FILENAME,
    QWEN_FILE_BYTES, QWEN_LICENSE_SPDX, QWEN_REPOSITORY_ID, QWEN_REVISION, QWEN_SHA256,
    QWEN_TENSOR_DATA_OFFSET,
};
pub use protocol::{
    FetchedExpertEvidence, ModelSliceMemoryGauges, ModelSliceRequest, ModelSliceResult,
    RouterRequest, RouterResult, SyntheticMoeComparison, SyntheticMoeRequest, SyntheticMoeResult,
    TensorFixtureComparison, TensorFixtureMemoryGauges, TensorFixtureRequest, TensorFixtureResult,
    WorkerError, WorkerErrorKind, WorkerHello, MODEL_SLICE_ID, ROUTER_SINGLE_ROW_CASE_ID,
    ROUTER_TWO_ROW_CASE_ID,
};
pub use qwen3moe::{
    admit_qwen3moe_adapter, admit_qwen3moe_full_graph, construct_qwen3moe_full_graph,
    Qwen3MoeAdapterDescriptor, Qwen3MoeAdmissionInput, Qwen3MoeArtifactBinding,
    Qwen3MoeFullGraphAdmissionInput, Qwen3MoeFullGraphDescriptor, Qwen3MoeGraphDescriptor,
    Qwen3MoeGraphNodeDescriptor, Qwen3MoeGraphOperation, Qwen3MoeLayerGraphDescriptor,
    Qwen3MoeMetadata, Qwen3MoeTensorBinding, Qwen3MoeTensorDescriptor, Qwen3MoeTensorRole,
    QWEN3MOE_ADAPTER_CONTRACT_ID, QWEN3MOE_ATTENTION_HEAD_COUNT, QWEN3MOE_ATTENTION_KV_HEAD_COUNT,
    QWEN3MOE_DATA_OFFSET, QWEN3MOE_EXPERT_COUNT, QWEN3MOE_EXPERT_FFN_WIDTH, QWEN3MOE_FILENAME,
    QWEN3MOE_FILE_BYTES, QWEN3MOE_FULL_GRAPH_CONTRACT_ID, QWEN3MOE_GLOBAL_GRAPH_OPERATIONS,
    QWEN3MOE_GRAPH_OPERATIONS_PER_LAYER, QWEN3MOE_HEAD_DIMENSION, QWEN3MOE_HIDDEN_WIDTH,
    QWEN3MOE_LAYER_COUNT, QWEN3MOE_REPOSITORY_ID, QWEN3MOE_REVISION, QWEN3MOE_ROPE_KIND,
    QWEN3MOE_SHA256, QWEN3MOE_TENSOR_COUNT, QWEN3MOE_TOP_K, QWEN3MOE_VOCAB_SIZE,
};
pub use qwen3moe_attention::{
    parse_qwen3moe_attention_kv_fixture, run_qwen3moe_attention_kv,
    validate_qwen3moe_attention_kv_fixture, Qwen3MoeAttentionExecutionDimensions,
    Qwen3MoeAttentionInputStep, Qwen3MoeAttentionKvFixture, Qwen3MoeAttentionKvResult,
    Qwen3MoeKvCacheSnapshot, Qwen3MoeAttentionOracle, Qwen3MoeAttentionOracleStep,
    Qwen3MoeAttentionRuntime, Qwen3MoeAttentionStepEvidence, Qwen3MoeAttentionTargetDimensions,
    Qwen3MoeAttentionTensors, QWEN3MOE_ATTENTION_KV_CONTRACT_ID,
    QWEN3MOE_ATTENTION_KV_FIXTURE_ID, QWEN3MOE_ATTENTION_KV_FIXTURE_SCHEMA,
    QWEN3MOE_ATTENTION_KV_MAX_ELEMENTS, QWEN3MOE_ATTENTION_KV_OPERATION_COUNT,
};
pub use qwen3moe_context::{
    Qwen3MoeExecutionContext, Qwen3MoePlugin, QWEN3MOE_ARCHITECTURE_ID,
};
pub use qwen3moe_runtime::{
    deterministic_top_k, parse_qwen3moe_synthetic_fixture, run_qwen3moe_synthetic_generation,
    run_qwen3moe_synthetic_generation_with_cancel_after_step, validate_qwen3moe_synthetic_fixture,
    Qwen3MoeExecutionDimensions, Qwen3MoeOracleLogit, Qwen3MoeRoutingContract,
    Qwen3MoeStepEvidence, Qwen3MoeSyntheticFixture, Qwen3MoeSyntheticGenerationResult,
    Qwen3MoeSyntheticInputStep, Qwen3MoeSyntheticOracle, Qwen3MoeSyntheticOracleStep,
    Qwen3MoeSyntheticRuntime, Qwen3MoeSyntheticTensors, Qwen3MoeTargetDimensions,
    QWEN3MOE_SYNTHETIC_FIXTURE_ID, QWEN3MOE_SYNTHETIC_FIXTURE_SCHEMA,
    QWEN3MOE_SYNTHETIC_MAX_ELEMENTS, QWEN3MOE_SYNTHETIC_OPERATION_COUNT,
};
pub use qwen3moe_storage::{
    decode_qwen3moe_tensor, Qwen3MoEDecodedTensor, Qwen3MoeContentHashMetadata,
    Qwen3MoeDecoderContract, Qwen3MoeDestinationPolicy, Qwen3MoeStorageRequest,
    QWEN3MOE_F32_HASH_ALGORITHM, QWEN3MOE_Q8_0_BLOCK_BYTES, QWEN3MOE_Q8_0_BLOCK_ELEMENTS,
    QWEN3MOE_Q8_0_DECODER_CONTRACT_ID, QWEN3MOE_Q8_0_DECODER_VERSION,
};
