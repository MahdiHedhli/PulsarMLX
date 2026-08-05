//! Explicit backend selection and immutable capability-state evidence.

use crate::error::{ContractError, ErrorCategory};

const CAPABILITY_SCHEMA_VERSION: u32 = 1;
const MAX_ID_CHARS: usize = 128;
const MAX_METADATA_CHARS: usize = 256;
const MAX_CAPABILITY_ITEMS: usize = 128;
const MAX_EXCLUSIONS: usize = 64;

/// An explicit backend and device request.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BackendSelection {
    backend_id: String,
    requested_device: Option<String>,
    allow_fallback: bool,
}

impl BackendSelection {
    pub fn new(
        backend_id: String,
        requested_device: Option<String>,
        allow_fallback: bool,
    ) -> Result<Self, ContractError> {
        validate_id(&backend_id, "backend ID", ErrorCategory::InvalidSelection)?;
        if let Some(device) = requested_device.as_deref() {
            validate_id(device, "requested device", ErrorCategory::InvalidSelection)?;
        }
        if backend_id == "apple-mlx" && requested_device.is_none() {
            return Err(ContractError::new(
                ErrorCategory::InvalidSelection,
                "missing_requested_device",
                "apple-mlx requires an explicit requested device",
            ));
        }

        Ok(Self {
            backend_id,
            requested_device,
            allow_fallback,
        })
    }

    pub fn backend_id(&self) -> &str {
        &self.backend_id
    }

    pub fn requested_device(&self) -> Option<&str> {
        self.requested_device.as_deref()
    }

    pub fn allow_fallback(&self) -> bool {
        self.allow_fallback
    }

    /// Validate this selection for correctness or benchmark evidence.
    pub fn validate_for_evidence(&self) -> Result<(), ContractError> {
        if self.allow_fallback {
            return Err(ContractError::new(
                ErrorCategory::InvalidSelection,
                "fallback_not_allowed",
                "validation and benchmark evidence must set allow_fallback to false",
            ));
        }
        Ok(())
    }
}

/// What this process has actually proved about the selected device.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DeviceState {
    Unavailable,
    AvailableUnevaluated,
    Evaluated,
}

/// Bounded facts from one explicit device probe.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CapabilityProbe {
    case_id: String,
    backend_id: String,
    device_id: String,
    evaluated: bool,
    synchronized: bool,
    comparison_passed: bool,
}

impl CapabilityProbe {
    pub fn new(
        case_id: String,
        backend_id: String,
        device_id: String,
        evaluated: bool,
        synchronized: bool,
        comparison_passed: bool,
    ) -> Result<Self, ContractError> {
        validate_id(&case_id, "probe case ID", ErrorCategory::InvalidCapability)?;
        validate_id(
            &backend_id,
            "probe backend ID",
            ErrorCategory::InvalidCapability,
        )?;
        validate_id(
            &device_id,
            "probe device ID",
            ErrorCategory::InvalidCapability,
        )?;

        Ok(Self {
            case_id,
            backend_id,
            device_id,
            evaluated,
            synchronized,
            comparison_passed,
        })
    }

    pub fn case_id(&self) -> &str {
        &self.case_id
    }

    pub fn passed(&self) -> bool {
        self.evaluated && self.synchronized && self.comparison_passed
    }
}

/// Immutable evidence describing the selected backend in this process.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BackendCapabilityReport {
    selection: BackendSelection,
    schema_version: u32,
    runtime_version: Option<String>,
    host_arch: String,
    os_version: String,
    device_id: Option<String>,
    device_state: DeviceState,
    supported_ops: Vec<String>,
    supported_dtypes: Vec<String>,
    supported_quantizations: Vec<String>,
    exclusions: Vec<String>,
    probe_case_id: Option<String>,
}

impl BackendCapabilityReport {
    pub fn unavailable(
        selection: BackendSelection,
        schema_version: u32,
        runtime_version: Option<String>,
        host_arch: String,
        os_version: String,
        exclusions: Vec<String>,
    ) -> Result<Self, ContractError> {
        selection.validate_for_evidence()?;
        validate_schema_version(schema_version)?;
        if let Some(version) = runtime_version.as_deref() {
            validate_metadata(version, "runtime version")?;
        }
        validate_metadata(&host_arch, "host architecture")?;
        validate_metadata(&os_version, "OS version")?;
        validate_exclusions(&exclusions, true)?;

        Ok(Self {
            selection,
            schema_version,
            runtime_version,
            host_arch,
            os_version,
            device_id: None,
            device_state: DeviceState::Unavailable,
            supported_ops: Vec::new(),
            supported_dtypes: Vec::new(),
            supported_quantizations: Vec::new(),
            exclusions,
            probe_case_id: None,
        })
    }

    #[allow(clippy::too_many_arguments)]
    pub fn available_unevaluated(
        selection: BackendSelection,
        schema_version: u32,
        runtime_version: String,
        host_arch: String,
        os_version: String,
        device_id: String,
        supported_ops: Vec<String>,
        supported_dtypes: Vec<String>,
        supported_quantizations: Vec<String>,
        exclusions: Vec<String>,
    ) -> Result<Self, ContractError> {
        selection.validate_for_evidence()?;
        validate_schema_version(schema_version)?;
        validate_metadata(&runtime_version, "runtime version")?;
        validate_metadata(&host_arch, "host architecture")?;
        validate_metadata(&os_version, "OS version")?;
        validate_id(&device_id, "device ID", ErrorCategory::InvalidCapability)?;
        if selection.requested_device() != Some(device_id.as_str()) {
            return Err(ContractError::new(
                ErrorCategory::InvalidCapability,
                "device_identity_mismatch",
                "reported device does not match the explicitly requested device",
            ));
        }
        validate_id_set(&supported_ops, "supported operation")?;
        validate_id_set(&supported_dtypes, "supported dtype")?;
        validate_id_set(&supported_quantizations, "supported quantization")?;
        validate_exclusions(&exclusions, false)?;

        Ok(Self {
            selection,
            schema_version,
            runtime_version: Some(runtime_version),
            host_arch,
            os_version,
            device_id: Some(device_id),
            device_state: DeviceState::AvailableUnevaluated,
            supported_ops,
            supported_dtypes,
            supported_quantizations,
            exclusions,
            probe_case_id: None,
        })
    }

    pub fn schema_version(&self) -> u32 {
        self.schema_version
    }

    pub fn backend_id(&self) -> &str {
        self.selection.backend_id()
    }

    pub fn runtime_version(&self) -> Option<&str> {
        self.runtime_version.as_deref()
    }

    pub fn host_arch(&self) -> &str {
        &self.host_arch
    }

    pub fn os_version(&self) -> &str {
        &self.os_version
    }

    pub fn device_id(&self) -> Option<&str> {
        self.device_id.as_deref()
    }

    pub fn device_state(&self) -> DeviceState {
        self.device_state
    }

    pub fn supported_ops(&self) -> &[String] {
        &self.supported_ops
    }

    pub fn supported_dtypes(&self) -> &[String] {
        &self.supported_dtypes
    }

    pub fn supported_quantizations(&self) -> &[String] {
        &self.supported_quantizations
    }

    pub fn exclusions(&self) -> &[String] {
        &self.exclusions
    }

    pub fn probe_case_id(&self) -> Option<&str> {
        self.probe_case_id.as_deref()
    }

    /// Return a new report after one legal, fully passing probe transition.
    pub fn transition_to(
        &self,
        target: DeviceState,
        probe: Option<&CapabilityProbe>,
    ) -> Result<Self, ContractError> {
        if self.device_state != DeviceState::AvailableUnevaluated
            || target != DeviceState::Evaluated
        {
            return Err(ContractError::new(
                ErrorCategory::InvalidStateTransition,
                "invalid_capability_transition",
                "only available_unevaluated may transition to evaluated",
            ));
        }

        let probe = probe.ok_or_else(|| {
            ContractError::new(
                ErrorCategory::InvalidStateTransition,
                "missing_capability_probe",
                "an evaluated capability claim requires a passed probe",
            )
        })?;
        if !probe.passed() {
            return Err(ContractError::new(
                ErrorCategory::InvalidStateTransition,
                "failed_capability_probe",
                "the capability probe was not evaluated, synchronized, and numerically passing",
            ));
        }
        if probe.backend_id != self.selection.backend_id
            || self.device_id.as_deref() != Some(probe.device_id.as_str())
        {
            return Err(ContractError::new(
                ErrorCategory::InvalidStateTransition,
                "probe_identity_mismatch",
                "probe backend and device must match the capability report",
            ));
        }

        let mut evaluated = self.clone();
        evaluated.device_state = DeviceState::Evaluated;
        evaluated.probe_case_id = Some(probe.case_id.clone());
        Ok(evaluated)
    }
}

fn validate_schema_version(schema_version: u32) -> Result<(), ContractError> {
    if schema_version != CAPABILITY_SCHEMA_VERSION {
        return Err(ContractError::new(
            ErrorCategory::InvalidCapability,
            "unsupported_capability_schema",
            "capability schema version must be exactly 1",
        ));
    }
    Ok(())
}

fn validate_id(
    value: &str,
    field: &'static str,
    category: ErrorCategory,
) -> Result<(), ContractError> {
    let valid = !value.is_empty()
        && value.trim() == value
        && value.chars().count() <= MAX_ID_CHARS
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.' | b':'));
    if !valid {
        return Err(ContractError::new(
            category,
            "invalid_capability_id",
            format!("{field} must be a bounded stable identifier"),
        ));
    }
    Ok(())
}

fn validate_metadata(value: &str, field: &'static str) -> Result<(), ContractError> {
    let valid = !value.is_empty()
        && value.trim() == value
        && value.chars().count() <= MAX_METADATA_CHARS
        && !value.chars().any(char::is_control);
    if !valid {
        return Err(ContractError::new(
            ErrorCategory::InvalidCapability,
            "invalid_capability_metadata",
            format!("{field} must be nonempty and bounded"),
        ));
    }
    Ok(())
}

fn validate_id_set(values: &[String], field: &'static str) -> Result<(), ContractError> {
    if values.len() > MAX_CAPABILITY_ITEMS {
        return Err(ContractError::new(
            ErrorCategory::ResourceLimit,
            "capability_item_limit",
            format!("{field} list exceeds its bounded item limit"),
        ));
    }
    for value in values {
        validate_id(value, field, ErrorCategory::InvalidCapability)?;
    }
    if has_duplicates(values) {
        return Err(ContractError::new(
            ErrorCategory::InvalidCapability,
            "duplicate_capability_item",
            format!("{field} list contains duplicate identifiers"),
        ));
    }
    Ok(())
}

fn validate_exclusions(exclusions: &[String], required: bool) -> Result<(), ContractError> {
    if required && exclusions.is_empty() {
        return Err(ContractError::new(
            ErrorCategory::InvalidCapability,
            "missing_capability_exclusion",
            "an unavailable capability report requires an explicit exclusion",
        ));
    }
    if exclusions.len() > MAX_EXCLUSIONS {
        return Err(ContractError::new(
            ErrorCategory::ResourceLimit,
            "capability_exclusion_limit",
            "capability exclusions exceed their bounded item limit",
        ));
    }
    for exclusion in exclusions {
        validate_metadata(exclusion, "capability exclusion")?;
    }
    if has_duplicates(exclusions) {
        return Err(ContractError::new(
            ErrorCategory::InvalidCapability,
            "duplicate_capability_exclusion",
            "capability exclusions contain duplicate entries",
        ));
    }
    Ok(())
}

fn has_duplicates(values: &[String]) -> bool {
    values
        .iter()
        .enumerate()
        .any(|(index, value)| values[index + 1..].contains(value))
}
