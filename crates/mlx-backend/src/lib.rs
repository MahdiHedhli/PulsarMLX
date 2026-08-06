//! Apple MLX worker client for PulsarMLX.

pub mod client;
pub mod device;
pub mod model;
pub mod protocol;
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
