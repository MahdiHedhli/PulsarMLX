//! Apple MLX worker client for PulsarMLX.

pub mod client;
pub mod device;
pub mod protocol;

pub use backend::DeviceState;
pub use client::{
    CleanupOutcome, CleanupReport, HealthReport, WorkerClient, WorkerConfig, WorkerTimeouts,
};
pub use device::{
    validate_device_smoke, DeviceHello, DeviceProbe, DeviceSmokeError, DeviceSmokeErrorCode,
    DeviceSmokeReport, PINNED_MLX_VERSION,
};
pub use protocol::{
    FetchedExpertEvidence, SyntheticMoeComparison, SyntheticMoeRequest, SyntheticMoeResult,
    TensorFixtureComparison, TensorFixtureMemoryGauges, TensorFixtureRequest, TensorFixtureResult,
    WorkerError, WorkerErrorKind, WorkerHello,
};
