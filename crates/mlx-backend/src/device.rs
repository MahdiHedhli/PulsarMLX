//! Pure validation for an evaluated Apple MLX device proof.

use backend::DeviceState;
use std::fmt;

pub const PINNED_MLX_VERSION: &str = "0.32.0";
const MAX_PROBE_VALUES: usize = 1_024;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeviceHello {
    pub python_arch: String,
    pub mlx_version: String,
    pub metal_available: bool,
    pub gpu_count: u32,
}

#[derive(Debug, Clone, PartialEq)]
pub struct DeviceProbe {
    pub backend_id: String,
    pub requested_device: String,
    pub selected_device: String,
    pub fallback_used: bool,
    pub operation_id: String,
    pub evaluated: bool,
    pub synchronized: bool,
    pub expected: Vec<f64>,
    pub actual: Vec<f64>,
    pub absolute_tolerance: f64,
    pub relative_tolerance: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DeviceSmokeErrorCode {
    UnsupportedHost,
    RuntimeVersionMismatch,
    MetalUnavailable,
    DeviceUnavailable,
    FallbackForbidden,
    DeviceSelectionMismatch,
    EvaluationIncomplete,
    SynchronizationIncomplete,
    ComparisonFailed,
    MalformedEvidence,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeviceSmokeError {
    code: DeviceSmokeErrorCode,
    message: &'static str,
}

impl DeviceSmokeError {
    fn new(code: DeviceSmokeErrorCode, message: &'static str) -> Self {
        Self { code, message }
    }

    pub fn code(&self) -> DeviceSmokeErrorCode {
        self.code
    }
}

impl fmt::Display for DeviceSmokeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.message)
    }
}

impl std::error::Error for DeviceSmokeError {}

#[derive(Debug, Clone, PartialEq)]
pub struct DeviceSmokeReport {
    backend_id: String,
    selected_device: String,
    device_state: DeviceState,
    compared_count: usize,
    comparison_passed: bool,
    fallback_used: bool,
    max_absolute_error: f64,
    max_relative_error: f64,
}

impl DeviceSmokeReport {
    pub fn backend_id(&self) -> &str {
        &self.backend_id
    }

    pub fn selected_device(&self) -> &str {
        &self.selected_device
    }

    pub fn device_state(&self) -> DeviceState {
        self.device_state
    }

    pub fn compared_count(&self) -> usize {
        self.compared_count
    }

    pub fn comparison_passed(&self) -> bool {
        self.comparison_passed
    }

    pub fn fallback_used(&self) -> bool {
        self.fallback_used
    }

    pub fn max_absolute_error(&self) -> f64 {
        self.max_absolute_error
    }

    pub fn max_relative_error(&self) -> f64 {
        self.max_relative_error
    }
}

pub fn validate_device_smoke(
    hello: &DeviceHello,
    probe: &DeviceProbe,
) -> Result<DeviceSmokeReport, DeviceSmokeError> {
    if hello.python_arch != "arm64" {
        return Err(DeviceSmokeError::new(
            DeviceSmokeErrorCode::UnsupportedHost,
            "the MLX worker is not a native arm64 process",
        ));
    }
    if hello.mlx_version != PINNED_MLX_VERSION {
        return Err(DeviceSmokeError::new(
            DeviceSmokeErrorCode::RuntimeVersionMismatch,
            "the MLX runtime version does not match the project pin",
        ));
    }
    if !hello.metal_available {
        return Err(DeviceSmokeError::new(
            DeviceSmokeErrorCode::MetalUnavailable,
            "the MLX Metal backend is unavailable",
        ));
    }
    if hello.gpu_count == 0 {
        return Err(DeviceSmokeError::new(
            DeviceSmokeErrorCode::DeviceUnavailable,
            "the MLX worker reported no GPU device",
        ));
    }
    if probe.fallback_used {
        return Err(DeviceSmokeError::new(
            DeviceSmokeErrorCode::FallbackForbidden,
            "device-smoke evidence forbids fallback",
        ));
    }
    if probe.backend_id != "apple-mlx"
        || probe.requested_device != "gpu"
        || probe.selected_device != "gpu"
        || probe.selected_device != probe.requested_device
    {
        return Err(DeviceSmokeError::new(
            DeviceSmokeErrorCode::DeviceSelectionMismatch,
            "the evaluated device does not match explicit apple-mlx GPU selection",
        ));
    }
    if probe.operation_id != "nonsymmetric-f32-matmul" {
        return Err(DeviceSmokeError::new(
            DeviceSmokeErrorCode::MalformedEvidence,
            "the device probe operation identity is not admitted",
        ));
    }
    if !probe.evaluated {
        return Err(DeviceSmokeError::new(
            DeviceSmokeErrorCode::EvaluationIncomplete,
            "the MLX result graph was not explicitly evaluated",
        ));
    }
    if !probe.synchronized {
        return Err(DeviceSmokeError::new(
            DeviceSmokeErrorCode::SynchronizationIncomplete,
            "the selected GPU was not explicitly synchronized",
        ));
    }
    if probe.expected.is_empty()
        || probe.expected.len() != probe.actual.len()
        || probe.expected.len() > MAX_PROBE_VALUES
        || !valid_tolerance(probe.absolute_tolerance)
        || !valid_tolerance(probe.relative_tolerance)
    {
        return Err(DeviceSmokeError::new(
            DeviceSmokeErrorCode::MalformedEvidence,
            "the bounded comparison descriptor is invalid",
        ));
    }

    let mut max_absolute_error = 0.0_f64;
    let mut max_relative_error = 0.0_f64;
    for (&expected, &actual) in probe.expected.iter().zip(&probe.actual) {
        if !expected.is_finite() || !actual.is_finite() {
            return Err(DeviceSmokeError::new(
                DeviceSmokeErrorCode::ComparisonFailed,
                "device probe comparison values must be finite",
            ));
        }
        let absolute_error = (actual - expected).abs();
        let relative_error = if expected == 0.0 {
            if absolute_error == 0.0 {
                0.0
            } else {
                f64::INFINITY
            }
        } else {
            absolute_error / expected.abs()
        };
        max_absolute_error = max_absolute_error.max(absolute_error);
        max_relative_error = max_relative_error.max(relative_error);
        if absolute_error > probe.absolute_tolerance && relative_error > probe.relative_tolerance {
            return Err(DeviceSmokeError::new(
                DeviceSmokeErrorCode::ComparisonFailed,
                "the evaluated GPU result does not match the independent oracle",
            ));
        }
    }

    Ok(DeviceSmokeReport {
        backend_id: probe.backend_id.clone(),
        selected_device: probe.selected_device.clone(),
        device_state: DeviceState::Evaluated,
        compared_count: probe.expected.len(),
        comparison_passed: true,
        fallback_used: false,
        max_absolute_error,
        max_relative_error,
    })
}

fn valid_tolerance(value: f64) -> bool {
    value.is_finite() && value >= 0.0
}
