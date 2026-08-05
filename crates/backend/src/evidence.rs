//! Compatibility, validation, memory, and benchmark evidence contracts.
//!
//! These types deliberately describe evidence rather than execute backend work.
//! Constructors reject states that could otherwise turn an incomplete or
//! unreproducible result into a capability or performance claim.

use std::collections::HashSet;
use std::path::{Component, Path};

use crate::error::{ContractError, ErrorCategory};
use crate::tensor::QuantizationId;

const MAX_FIELD_CHARS: usize = 4_096;
const MAX_LIST_ITEMS: usize = 4_096;

/// Maturity of the evidence for one quantization and tensor-role combination.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum QuantizationStatus {
    Planned,
    ScalarVerified,
    MlxVerified,
    Unsupported,
    Blocked,
}

/// Caller-provided quantization compatibility fields.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct QuantizationCompatibilityDescriptor {
    pub quantization: QuantizationId,
    pub tensor_roles: Vec<String>,
    pub block_elements: u64,
    pub block_bytes: u64,
    pub row_divisibility: u64,
    pub malformed_case_ids: Vec<String>,
    pub scalar_parity_case_ids: Vec<String>,
    pub mlx_parity_case_ids: Vec<String>,
    pub status: QuantizationStatus,
}

/// Validated compatibility evidence for an exact quantization layout.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct QuantizationCompatibilityRecord {
    descriptor: QuantizationCompatibilityDescriptor,
}

impl QuantizationCompatibilityRecord {
    pub fn try_new(descriptor: QuantizationCompatibilityDescriptor) -> Result<Self, ContractError> {
        validate_nonempty_unique_list(
            &descriptor.tensor_roles,
            "tensor_roles",
            ErrorCategory::InvalidQuantization,
            "invalid_quantization_roles",
        )?;
        validate_positive(
            descriptor.block_elements,
            "block_elements",
            ErrorCategory::InvalidQuantization,
            "invalid_quantization_layout",
        )?;
        validate_positive(
            descriptor.block_bytes,
            "block_bytes",
            ErrorCategory::InvalidQuantization,
            "invalid_quantization_layout",
        )?;
        validate_positive(
            descriptor.row_divisibility,
            "row_divisibility",
            ErrorCategory::InvalidQuantization,
            "invalid_quantization_layout",
        )?;

        validate_optional_unique_list(
            &descriptor.malformed_case_ids,
            "malformed_case_ids",
            ErrorCategory::InvalidQuantization,
            "invalid_quantization_evidence",
        )?;
        validate_optional_unique_list(
            &descriptor.scalar_parity_case_ids,
            "scalar_parity_case_ids",
            ErrorCategory::InvalidQuantization,
            "invalid_quantization_evidence",
        )?;
        validate_optional_unique_list(
            &descriptor.mlx_parity_case_ids,
            "mlx_parity_case_ids",
            ErrorCategory::InvalidQuantization,
            "invalid_quantization_evidence",
        )?;

        match &descriptor.quantization {
            QuantizationId::Q8Zero => {
                if descriptor.block_elements != 32
                    || descriptor.block_bytes != 34
                    || descriptor.row_divisibility != 32
                {
                    return Err(error(
                        ErrorCategory::InvalidQuantization,
                        "invalid_q8_zero_layout",
                        "Q8_0 requires 32 elements, 34 bytes, and row divisibility 32",
                    ));
                }
            }
            QuantizationId::Unsupported(name) => {
                validate_text(
                    name,
                    "unsupported quantization identity",
                    ErrorCategory::InvalidQuantization,
                    "invalid_quantization_id",
                )?;
                if !matches!(
                    descriptor.status,
                    QuantizationStatus::Unsupported | QuantizationStatus::Blocked
                ) {
                    return Err(error(
                        ErrorCategory::InvalidQuantization,
                        "unsupported_quantization_status",
                        "an unsupported quantization ID cannot carry a support status",
                    ));
                }
            }
        }

        match descriptor.status {
            QuantizationStatus::ScalarVerified => {
                require_case_ids(
                    &descriptor.malformed_case_ids,
                    "malformed-input",
                    ErrorCategory::InvalidQuantization,
                    "missing_quantization_evidence",
                )?;
                require_case_ids(
                    &descriptor.scalar_parity_case_ids,
                    "scalar-parity",
                    ErrorCategory::InvalidQuantization,
                    "missing_quantization_evidence",
                )?;
            }
            QuantizationStatus::MlxVerified => {
                require_case_ids(
                    &descriptor.malformed_case_ids,
                    "malformed-input",
                    ErrorCategory::InvalidQuantization,
                    "missing_quantization_evidence",
                )?;
                require_case_ids(
                    &descriptor.scalar_parity_case_ids,
                    "scalar-parity",
                    ErrorCategory::InvalidQuantization,
                    "missing_quantization_evidence",
                )?;
                require_case_ids(
                    &descriptor.mlx_parity_case_ids,
                    "MLX-parity",
                    ErrorCategory::InvalidQuantization,
                    "missing_quantization_evidence",
                )?;
            }
            QuantizationStatus::Planned
            | QuantizationStatus::Unsupported
            | QuantizationStatus::Blocked => {}
        }

        Ok(Self { descriptor })
    }

    pub fn descriptor(&self) -> &QuantizationCompatibilityDescriptor {
        &self.descriptor
    }

    pub fn quantization(&self) -> &QuantizationId {
        &self.descriptor.quantization
    }

    pub fn tensor_roles(&self) -> &[String] {
        &self.descriptor.tensor_roles
    }

    pub fn block_elements(&self) -> u64 {
        self.descriptor.block_elements
    }

    pub fn block_bytes(&self) -> u64 {
        self.descriptor.block_bytes
    }

    pub fn row_divisibility(&self) -> u64 {
        self.descriptor.row_divisibility
    }

    pub fn malformed_case_ids(&self) -> &[String] {
        &self.descriptor.malformed_case_ids
    }

    pub fn scalar_parity_case_ids(&self) -> &[String] {
        &self.descriptor.scalar_parity_case_ids
    }

    pub fn mlx_parity_case_ids(&self) -> &[String] {
        &self.descriptor.mlx_parity_case_ids
    }

    pub fn status(&self) -> QuantizationStatus {
        self.descriptor.status
    }
}

/// Independent memory observations. No field is defined as the sum of the
/// others because mappings, allocator caches, and process footprint overlap.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct MemoryGaugeDescriptor {
    pub model_file_bytes: Option<u64>,
    pub mapped_virtual_bytes: Option<u64>,
    pub mapped_resident_bytes: Option<u64>,
    pub owned_compressed_bytes: Option<u64>,
    pub decoded_array_bytes: Option<u64>,
    pub temporary_current_bytes: Option<u64>,
    pub temporary_peak_bytes: Option<u64>,
    pub mlx_active_bytes: Option<u64>,
    pub mlx_cache_bytes: Option<u64>,
    pub mlx_peak_bytes: Option<u64>,
    pub process_footprint_bytes: Option<u64>,
    pub system_pressure: Option<String>,
    /// Forbidden compatibility field retained so deserializers cannot mistake
    /// a sum of overlapping gauges for an authoritative total.
    pub reported_summed_total_bytes: Option<u64>,
}

/// Validated collection of independent memory gauges.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MemoryGauges {
    descriptor: MemoryGaugeDescriptor,
}

impl MemoryGauges {
    pub fn try_new(descriptor: MemoryGaugeDescriptor) -> Result<Self, ContractError> {
        if descriptor.reported_summed_total_bytes.is_some() {
            return Err(error(
                ErrorCategory::InvalidEvidence,
                "overlapping_memory_total",
                "memory gauges overlap and must not be reported as a summed total",
            ));
        }

        validate_peak(
            descriptor.temporary_current_bytes,
            descriptor.temporary_peak_bytes,
            "temporary",
        )?;
        validate_peak(
            descriptor.mlx_active_bytes,
            descriptor.mlx_peak_bytes,
            "MLX",
        )?;

        if let Some(pressure) = descriptor.system_pressure.as_deref() {
            validate_text(
                pressure,
                "system pressure",
                ErrorCategory::InvalidEvidence,
                "invalid_memory_gauge",
            )?;
        }

        Ok(Self { descriptor })
    }

    pub fn descriptor(&self) -> &MemoryGaugeDescriptor {
        &self.descriptor
    }

    pub fn model_file_bytes(&self) -> Option<u64> {
        self.descriptor.model_file_bytes
    }

    pub fn mapped_virtual_bytes(&self) -> Option<u64> {
        self.descriptor.mapped_virtual_bytes
    }

    pub fn mapped_resident_bytes(&self) -> Option<u64> {
        self.descriptor.mapped_resident_bytes
    }

    pub fn owned_compressed_bytes(&self) -> Option<u64> {
        self.descriptor.owned_compressed_bytes
    }

    pub fn decoded_array_bytes(&self) -> Option<u64> {
        self.descriptor.decoded_array_bytes
    }

    pub fn temporary_current_bytes(&self) -> Option<u64> {
        self.descriptor.temporary_current_bytes
    }

    pub fn temporary_peak_bytes(&self) -> Option<u64> {
        self.descriptor.temporary_peak_bytes
    }

    pub fn mlx_active_bytes(&self) -> Option<u64> {
        self.descriptor.mlx_active_bytes
    }

    pub fn mlx_cache_bytes(&self) -> Option<u64> {
        self.descriptor.mlx_cache_bytes
    }

    pub fn mlx_peak_bytes(&self) -> Option<u64> {
        self.descriptor.mlx_peak_bytes
    }

    pub fn process_footprint_bytes(&self) -> Option<u64> {
        self.descriptor.process_footprint_bytes
    }

    pub fn system_pressure(&self) -> Option<&str> {
        self.descriptor.system_pressure.as_deref()
    }
}

/// Whether the evidence was produced from an immutable clean tree.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GitDirtyState {
    Clean,
    Dirty,
    Unknown,
}

/// Actual result of executing a validation command.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ActualStatus {
    Passed,
    Failed,
    Blocked,
    NotRun,
}

/// Durable evidence lifecycle. Verification creates a new immutable value.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EvidenceStatus {
    Planned,
    ExecutedPassed,
    Verified,
    Blocked,
    ExecutedFailed,
    Superseded,
}

/// Exact depth at which a compatibility claim was exercised.
///
/// These levels are deliberately non-ordered: evidence at one level never
/// implies evidence at another level.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum CompatibilityEvidenceLevel {
    ScalarFixture,
    EvaluatedMlxTensorFixture,
    SyntheticRoutedMoe,
    BoundedRealModelSlice,
    GiantModelExecution,
    ProductionServing,
}

const COMPATIBILITY_EVIDENCE_LEVELS: [CompatibilityEvidenceLevel; 6] = [
    CompatibilityEvidenceLevel::ScalarFixture,
    CompatibilityEvidenceLevel::EvaluatedMlxTensorFixture,
    CompatibilityEvidenceLevel::SyntheticRoutedMoe,
    CompatibilityEvidenceLevel::BoundedRealModelSlice,
    CompatibilityEvidenceLevel::GiantModelExecution,
    CompatibilityEvidenceLevel::ProductionServing,
];

/// Caller-provided fields for one validation execution.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ValidationDescriptor {
    pub case_id: String,
    pub claim_scope: String,
    pub commit: String,
    pub git_dirty_state: GitDirtyState,
    pub evidence_level: Option<CompatibilityEvidenceLevel>,
    pub command: String,
    pub oracle_id: Option<String>,
    pub actual_status: ActualStatus,
    pub actual_values_or_bounded_summary: Option<String>,
    pub memory_gauges: Option<MemoryGaugeDescriptor>,
    pub warnings: Vec<String>,
    pub exclusions: Vec<String>,
    pub artifact_paths: Vec<String>,
}

/// An immutable executed validation result.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ValidationCase {
    descriptor: ValidationDescriptor,
    evidence_status: EvidenceStatus,
    memory_gauges: Option<MemoryGauges>,
}

impl ValidationCase {
    pub fn try_new(descriptor: ValidationDescriptor) -> Result<Self, ContractError> {
        validate_text(
            &descriptor.case_id,
            "case_id",
            ErrorCategory::InvalidEvidence,
            "invalid_validation_identity",
        )?;
        validate_text(
            &descriptor.claim_scope,
            "claim_scope",
            ErrorCategory::InvalidEvidence,
            "invalid_validation_scope",
        )?;
        validate_commit(&descriptor.commit, ErrorCategory::InvalidEvidence)?;

        if descriptor.git_dirty_state != GitDirtyState::Clean {
            return Err(error(
                ErrorCategory::InvalidEvidence,
                "nonimmutable_validation",
                "validation evidence requires a clean immutable commit",
            ));
        }

        validate_text(
            &descriptor.command,
            "command",
            ErrorCategory::InvalidEvidence,
            "invalid_validation_command",
        )?;

        let oracle_id = descriptor.oracle_id.as_deref().ok_or_else(|| {
            error(
                ErrorCategory::InvalidEvidence,
                "missing_validation_oracle",
                "validation evidence requires an independent oracle identity",
            )
        })?;
        validate_text(
            oracle_id,
            "oracle_id",
            ErrorCategory::InvalidEvidence,
            "missing_validation_oracle",
        )?;

        let actual_summary = descriptor
            .actual_values_or_bounded_summary
            .as_deref()
            .ok_or_else(|| {
                error(
                    ErrorCategory::InvalidEvidence,
                    "missing_actual_result",
                    "validation evidence requires actual values or a bounded result summary",
                )
            })?;
        validate_text(
            actual_summary,
            "actual_values_or_bounded_summary",
            ErrorCategory::InvalidEvidence,
            "missing_actual_result",
        )?;

        let memory_gauges = descriptor
            .memory_gauges
            .clone()
            .map(MemoryGauges::try_new)
            .transpose()?;

        validate_optional_unique_list(
            &descriptor.warnings,
            "warnings",
            ErrorCategory::InvalidEvidence,
            "invalid_validation_list",
        )?;
        validate_optional_unique_list(
            &descriptor.exclusions,
            "exclusions",
            ErrorCategory::InvalidEvidence,
            "invalid_validation_list",
        )?;
        validate_artifact_paths(&descriptor.artifact_paths)?;

        let evidence_status = match descriptor.actual_status {
            ActualStatus::Passed => EvidenceStatus::ExecutedPassed,
            ActualStatus::Failed => EvidenceStatus::ExecutedFailed,
            ActualStatus::Blocked => EvidenceStatus::Blocked,
            ActualStatus::NotRun => {
                return Err(error(
                    ErrorCategory::InvalidEvidence,
                    "missing_actual_result",
                    "a not-run case is not executed validation evidence",
                ));
            }
        };

        Ok(Self {
            descriptor,
            evidence_status,
            memory_gauges,
        })
    }

    /// Promote a passing executed record without mutating or erasing it.
    pub fn verify(&self) -> Result<Self, ContractError> {
        if self.descriptor.actual_status != ActualStatus::Passed
            || self.evidence_status != EvidenceStatus::ExecutedPassed
        {
            return Err(error(
                ErrorCategory::InvalidStateTransition,
                "invalid_evidence_transition",
                "only executed passing evidence can become verified",
            ));
        }

        let mut verified = self.clone();
        verified.evidence_status = EvidenceStatus::Verified;
        Ok(verified)
    }

    pub fn descriptor(&self) -> &ValidationDescriptor {
        &self.descriptor
    }

    pub fn case_id(&self) -> &str {
        &self.descriptor.case_id
    }

    pub fn claim_scope(&self) -> &str {
        &self.descriptor.claim_scope
    }

    pub fn commit(&self) -> &str {
        &self.descriptor.commit
    }

    pub fn git_dirty_state(&self) -> GitDirtyState {
        self.descriptor.git_dirty_state
    }

    pub fn evidence_level(&self) -> Option<CompatibilityEvidenceLevel> {
        self.descriptor.evidence_level
    }

    pub fn command(&self) -> &str {
        &self.descriptor.command
    }

    pub fn oracle_id(&self) -> Option<&str> {
        self.descriptor.oracle_id.as_deref()
    }

    pub fn actual_status(&self) -> ActualStatus {
        self.descriptor.actual_status
    }

    pub fn actual_values_or_bounded_summary(&self) -> &str {
        self.descriptor
            .actual_values_or_bounded_summary
            .as_deref()
            .expect("validated validation cases contain an actual result summary")
    }

    pub fn memory_gauges(&self) -> Option<&MemoryGauges> {
        self.memory_gauges.as_ref()
    }

    pub fn evidence_status(&self) -> EvidenceStatus {
        self.evidence_status
    }

    pub fn warnings(&self) -> &[String] {
        &self.descriptor.warnings
    }

    pub fn exclusions(&self) -> &[String] {
        &self.descriptor.exclusions
    }

    pub fn artifact_paths(&self) -> &[String] {
        &self.descriptor.artifact_paths
    }
}

/// Publication state for one exact compatibility evidence level.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CompatibilityStatus {
    Planned,
    Verified,
    Unsupported,
    Blocked,
}

/// Caller-provided state and evidence links for one exact matrix cell.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CompatibilityCellDescriptor {
    pub level: CompatibilityEvidenceLevel,
    pub status: CompatibilityStatus,
    pub evidence_case_ids: Vec<String>,
    pub explanation: Option<String>,
}

/// Caller-provided compatibility matrix for one architecture/quantization pair.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CompatibilityMatrixDescriptor {
    pub architecture: String,
    pub quantization: String,
    pub cells: Vec<CompatibilityCellDescriptor>,
}

/// A complete six-cell compatibility matrix with no ordered implication.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CompatibilityMatrix {
    descriptor: CompatibilityMatrixDescriptor,
}

impl CompatibilityMatrix {
    pub fn try_new(
        descriptor: CompatibilityMatrixDescriptor,
        evidence: &[&ValidationCase],
    ) -> Result<Self, ContractError> {
        validate_text(
            &descriptor.architecture,
            "architecture",
            ErrorCategory::InvalidEvidence,
            "invalid_compatibility_identity",
        )?;
        validate_text(
            &descriptor.quantization,
            "quantization",
            ErrorCategory::InvalidEvidence,
            "invalid_compatibility_identity",
        )?;

        if descriptor.cells.len() != COMPATIBILITY_EVIDENCE_LEVELS.len() {
            return Err(error(
                ErrorCategory::InvalidEvidence,
                "incomplete_compatibility_matrix",
                "compatibility matrix requires one explicit cell for every evidence level",
            ));
        }

        let mut seen_levels = HashSet::with_capacity(descriptor.cells.len());
        for cell in &descriptor.cells {
            if !seen_levels.insert(cell.level) {
                return Err(error(
                    ErrorCategory::InvalidEvidence,
                    "duplicate_compatibility_level",
                    "compatibility matrix contains a duplicate evidence level",
                ));
            }

            validate_optional_unique_list(
                &cell.evidence_case_ids,
                "evidence_case_ids",
                ErrorCategory::InvalidEvidence,
                "invalid_compatibility_evidence",
            )?;
            if let Some(explanation) = cell.explanation.as_deref() {
                validate_text(
                    explanation,
                    "compatibility explanation",
                    ErrorCategory::InvalidEvidence,
                    "invalid_compatibility_explanation",
                )?;
            }

            match cell.status {
                CompatibilityStatus::Verified => {
                    require_verified_evidence(
                        &cell.evidence_case_ids,
                        evidence,
                        ErrorCategory::InvalidEvidence,
                        "invalid_compatibility_evidence",
                    )?;
                    require_exact_evidence_level(cell, evidence)?;
                }
                CompatibilityStatus::Planned
                | CompatibilityStatus::Unsupported
                | CompatibilityStatus::Blocked => {
                    if cell.explanation.is_none() {
                        return Err(error(
                            ErrorCategory::InvalidEvidence,
                            "missing_compatibility_explanation",
                            "every nonverified compatibility cell requires an explanation",
                        ));
                    }
                }
            }
        }

        if !COMPATIBILITY_EVIDENCE_LEVELS
            .into_iter()
            .all(|level| seen_levels.contains(&level))
        {
            return Err(error(
                ErrorCategory::InvalidEvidence,
                "incomplete_compatibility_matrix",
                "compatibility matrix is missing a required evidence level",
            ));
        }

        Ok(Self { descriptor })
    }

    pub fn descriptor(&self) -> &CompatibilityMatrixDescriptor {
        &self.descriptor
    }

    pub fn architecture(&self) -> &str {
        &self.descriptor.architecture
    }

    pub fn quantization(&self) -> &str {
        &self.descriptor.quantization
    }

    pub fn cells(&self) -> &[CompatibilityCellDescriptor] {
        &self.descriptor.cells
    }

    pub fn status(&self, level: CompatibilityEvidenceLevel) -> CompatibilityStatus {
        self.cell(level).status
    }

    pub fn is_verified(&self, level: CompatibilityEvidenceLevel) -> bool {
        self.status(level) == CompatibilityStatus::Verified
    }

    pub fn cell(&self, level: CompatibilityEvidenceLevel) -> &CompatibilityCellDescriptor {
        self.descriptor
            .cells
            .iter()
            .find(|cell| cell.level == level)
            .expect("validated compatibility matrices contain every evidence level")
    }
}

/// Claimed maturity of an external model artifact.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ModelSupportStatus {
    Candidate,
    Compatible,
    Verified,
    Unsupported,
    Blocked,
}

/// Caller-provided model identity, inventory, and evidence links.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ModelCompatibilityDescriptor {
    pub model_id: String,
    pub revision: String,
    pub filename: String,
    pub sha256: Option<String>,
    pub size_bytes: Option<u64>,
    pub license: Option<String>,
    pub architecture: String,
    pub tensor_roles: Vec<String>,
    pub execution_depth: String,
    pub status: ModelSupportStatus,
    pub evidence_case_ids: Vec<String>,
}

/// Validated model identity and compatibility claim.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ModelCompatibilityRecord {
    descriptor: ModelCompatibilityDescriptor,
}

impl ModelCompatibilityRecord {
    pub fn try_new(
        descriptor: ModelCompatibilityDescriptor,
        evidence: &[&ValidationCase],
    ) -> Result<Self, ContractError> {
        validate_model_id(&descriptor.model_id)?;
        validate_commit(&descriptor.revision, ErrorCategory::InvalidModel)?;
        validate_filename(&descriptor.filename)?;
        validate_text(
            &descriptor.architecture,
            "architecture",
            ErrorCategory::InvalidModel,
            "invalid_model_architecture",
        )?;
        validate_text(
            &descriptor.execution_depth,
            "execution_depth",
            ErrorCategory::InvalidModel,
            "invalid_model_execution_depth",
        )?;

        if let Some(checksum) = descriptor.sha256.as_deref() {
            if checksum.len() != 64
                || !checksum
                    .bytes()
                    .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
            {
                return Err(error(
                    ErrorCategory::InvalidModel,
                    "invalid_model_checksum",
                    "model SHA-256 must contain exactly 64 lowercase hexadecimal characters",
                ));
            }
        }
        if descriptor.size_bytes == Some(0) {
            return Err(error(
                ErrorCategory::InvalidModel,
                "invalid_model_size",
                "model size must be positive when recorded",
            ));
        }
        if let Some(license) = descriptor.license.as_deref() {
            validate_text(
                license,
                "license",
                ErrorCategory::InvalidModel,
                "invalid_model_license",
            )?;
        }
        validate_optional_unique_list(
            &descriptor.tensor_roles,
            "tensor_roles",
            ErrorCategory::InvalidModel,
            "invalid_model_inventory",
        )?;
        validate_optional_unique_list(
            &descriptor.evidence_case_ids,
            "evidence_case_ids",
            ErrorCategory::InvalidModel,
            "invalid_model_evidence",
        )?;

        if matches!(
            descriptor.status,
            ModelSupportStatus::Compatible | ModelSupportStatus::Verified
        ) {
            require_complete_model_inventory(&descriptor)?;
        }

        if descriptor.status == ModelSupportStatus::Verified {
            require_verified_evidence(
                &descriptor.evidence_case_ids,
                evidence,
                ErrorCategory::InvalidModel,
                "invalid_model_evidence",
            )?;
        }

        Ok(Self { descriptor })
    }

    pub fn descriptor(&self) -> &ModelCompatibilityDescriptor {
        &self.descriptor
    }

    pub fn model_id(&self) -> &str {
        &self.descriptor.model_id
    }

    pub fn revision(&self) -> &str {
        &self.descriptor.revision
    }

    pub fn filename(&self) -> &str {
        &self.descriptor.filename
    }

    pub fn sha256(&self) -> Option<&str> {
        self.descriptor.sha256.as_deref()
    }

    pub fn size_bytes(&self) -> Option<u64> {
        self.descriptor.size_bytes
    }

    pub fn license(&self) -> Option<&str> {
        self.descriptor.license.as_deref()
    }

    pub fn architecture(&self) -> &str {
        &self.descriptor.architecture
    }

    pub fn tensor_roles(&self) -> &[String] {
        &self.descriptor.tensor_roles
    }

    pub fn execution_depth(&self) -> &str {
        &self.descriptor.execution_depth
    }

    pub fn status(&self) -> ModelSupportStatus {
        self.descriptor.status
    }

    pub fn evidence_case_ids(&self) -> &[String] {
        &self.descriptor.evidence_case_ids
    }
}

/// Caller-provided fields for a bounded reproducible benchmark.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BenchmarkDescriptor {
    pub case_id: String,
    pub commit: String,
    pub git_dirty_state: GitDirtyState,
    pub exact_command: String,
    pub backend_id: String,
    pub device_id: String,
    pub input_identity: String,
    pub warmup_count: u64,
    pub samples_ns: Vec<u64>,
    pub statistic: String,
    pub correctness_case_ids: Vec<String>,
}

/// A performance record admitted only after linked correctness verification.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BenchmarkRecord {
    descriptor: BenchmarkDescriptor,
}

impl BenchmarkRecord {
    pub fn try_new(
        descriptor: BenchmarkDescriptor,
        correctness_evidence: &[&ValidationCase],
    ) -> Result<Self, ContractError> {
        validate_text(
            &descriptor.case_id,
            "case_id",
            ErrorCategory::InvalidBenchmark,
            "invalid_benchmark_identity",
        )?;
        validate_commit(&descriptor.commit, ErrorCategory::InvalidBenchmark)?;
        if descriptor.git_dirty_state != GitDirtyState::Clean {
            return Err(error(
                ErrorCategory::InvalidBenchmark,
                "nonimmutable_benchmark",
                "benchmark evidence requires a clean immutable commit",
            ));
        }

        for (value, label, code) in [
            (
                &descriptor.exact_command,
                "exact_command",
                "invalid_benchmark_command",
            ),
            (
                &descriptor.backend_id,
                "backend_id",
                "invalid_benchmark_backend",
            ),
            (
                &descriptor.device_id,
                "device_id",
                "invalid_benchmark_device",
            ),
            (
                &descriptor.input_identity,
                "input_identity",
                "invalid_benchmark_input",
            ),
            (
                &descriptor.statistic,
                "statistic",
                "invalid_benchmark_statistic",
            ),
        ] {
            validate_text(value, label, ErrorCategory::InvalidBenchmark, code)?;
        }

        if descriptor.samples_ns.is_empty()
            || descriptor.samples_ns.len() > MAX_LIST_ITEMS
            || descriptor.samples_ns.contains(&0)
        {
            return Err(error(
                ErrorCategory::InvalidBenchmark,
                "invalid_benchmark_samples",
                "benchmark evidence requires a bounded nonempty list of positive samples",
            ));
        }

        validate_nonempty_unique_list(
            &descriptor.correctness_case_ids,
            "correctness_case_ids",
            ErrorCategory::InvalidBenchmark,
            "invalid_benchmark_correctness",
        )?;
        require_verified_evidence(
            &descriptor.correctness_case_ids,
            correctness_evidence,
            ErrorCategory::InvalidBenchmark,
            "invalid_benchmark_correctness",
        )?;

        Ok(Self { descriptor })
    }

    pub fn descriptor(&self) -> &BenchmarkDescriptor {
        &self.descriptor
    }

    pub fn case_id(&self) -> &str {
        &self.descriptor.case_id
    }

    pub fn commit(&self) -> &str {
        &self.descriptor.commit
    }

    pub fn exact_command(&self) -> &str {
        &self.descriptor.exact_command
    }

    pub fn backend_id(&self) -> &str {
        &self.descriptor.backend_id
    }

    pub fn device_id(&self) -> &str {
        &self.descriptor.device_id
    }

    pub fn input_identity(&self) -> &str {
        &self.descriptor.input_identity
    }

    pub fn warmup_count(&self) -> u64 {
        self.descriptor.warmup_count
    }

    pub fn samples_ns(&self) -> &[u64] {
        &self.descriptor.samples_ns
    }

    pub fn sample_count(&self) -> usize {
        self.descriptor.samples_ns.len()
    }

    pub fn statistic(&self) -> &str {
        &self.descriptor.statistic
    }

    pub fn correctness_case_ids(&self) -> &[String] {
        &self.descriptor.correctness_case_ids
    }
}

fn validate_positive(
    value: u64,
    label: &str,
    category: ErrorCategory,
    code: &'static str,
) -> Result<(), ContractError> {
    if value == 0 {
        Err(error(category, code, format!("{label} must be positive")))
    } else {
        Ok(())
    }
}

fn validate_peak(
    current: Option<u64>,
    peak: Option<u64>,
    label: &str,
) -> Result<(), ContractError> {
    if let (Some(current), Some(peak)) = (current, peak) {
        if peak < current {
            return Err(error(
                ErrorCategory::InvalidEvidence,
                "invalid_memory_peak",
                format!("{label} peak cannot be below its current gauge"),
            ));
        }
    }
    Ok(())
}

fn validate_text(
    value: &str,
    label: &str,
    category: ErrorCategory,
    code: &'static str,
) -> Result<(), ContractError> {
    let char_count = value.chars().count();
    if value.trim().is_empty() || char_count > MAX_FIELD_CHARS || value.contains('\0') {
        return Err(error(
            category,
            code,
            format!("{label} must be nonempty, bounded, and contain no NUL character"),
        ));
    }
    Ok(())
}

fn validate_nonempty_unique_list(
    values: &[String],
    label: &str,
    category: ErrorCategory,
    code: &'static str,
) -> Result<(), ContractError> {
    if values.is_empty() {
        return Err(error(category, code, format!("{label} must not be empty")));
    }
    validate_optional_unique_list(values, label, category, code)
}

fn validate_optional_unique_list(
    values: &[String],
    label: &str,
    category: ErrorCategory,
    code: &'static str,
) -> Result<(), ContractError> {
    if values.len() > MAX_LIST_ITEMS {
        return Err(error(
            category,
            code,
            format!("{label} exceeds the bounded item count"),
        ));
    }

    let mut seen = HashSet::with_capacity(values.len());
    for value in values {
        validate_text(value, label, category, code)?;
        if !seen.insert(value.as_str()) {
            return Err(error(
                category,
                code,
                format!("{label} contains a duplicate value"),
            ));
        }
    }
    Ok(())
}

fn require_case_ids(
    case_ids: &[String],
    evidence_kind: &str,
    category: ErrorCategory,
    code: &'static str,
) -> Result<(), ContractError> {
    if case_ids.is_empty() {
        return Err(error(
            category,
            code,
            format!("{evidence_kind} case IDs are required for this status"),
        ));
    }
    Ok(())
}

fn validate_commit(commit: &str, category: ErrorCategory) -> Result<(), ContractError> {
    if !matches!(commit.len(), 40 | 64) || !commit.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(error(
            category,
            "invalid_commit_identity",
            "commit identity must be a full 40- or 64-character hexadecimal hash",
        ));
    }
    Ok(())
}

fn validate_artifact_paths(paths: &[String]) -> Result<(), ContractError> {
    validate_optional_unique_list(
        paths,
        "artifact_paths",
        ErrorCategory::InvalidEvidence,
        "invalid_artifact_path",
    )?;

    for value in paths {
        let path = Path::new(value);
        if path.is_absolute()
            || path.components().any(|component| {
                matches!(
                    component,
                    Component::ParentDir | Component::RootDir | Component::Prefix(_)
                )
            })
        {
            return Err(error(
                ErrorCategory::InvalidEvidence,
                "invalid_artifact_path",
                "artifact paths must be repository-relative and may not traverse parents",
            ));
        }
    }
    Ok(())
}

fn validate_model_id(model_id: &str) -> Result<(), ContractError> {
    validate_text(
        model_id,
        "model_id",
        ErrorCategory::InvalidModel,
        "invalid_model_identity",
    )?;
    let mut segments = model_id.split('/');
    let namespace = segments.next().unwrap_or_default();
    let name = segments.next().unwrap_or_default();
    if namespace.trim().is_empty() || name.trim().is_empty() || segments.next().is_some() {
        return Err(error(
            ErrorCategory::InvalidModel,
            "invalid_model_identity",
            "model identity must use an exact namespace/name",
        ));
    }
    Ok(())
}

fn validate_filename(filename: &str) -> Result<(), ContractError> {
    validate_text(
        filename,
        "filename",
        ErrorCategory::InvalidModel,
        "invalid_model_filename",
    )?;
    let path = Path::new(filename);
    if path.is_absolute() || path.components().count() != 1 {
        return Err(error(
            ErrorCategory::InvalidModel,
            "invalid_model_filename",
            "model filename must be an exact basename rather than a local path",
        ));
    }
    Ok(())
}

fn require_complete_model_inventory(
    descriptor: &ModelCompatibilityDescriptor,
) -> Result<(), ContractError> {
    if descriptor.sha256.is_none()
        || descriptor.size_bytes.is_none()
        || descriptor.license.is_none()
        || descriptor.tensor_roles.is_empty()
    {
        return Err(error(
            ErrorCategory::InvalidModel,
            "incomplete_model_inventory",
            "compatible or verified models require checksum, size, license, and tensor inventory",
        ));
    }
    Ok(())
}

fn require_verified_evidence(
    required_case_ids: &[String],
    evidence: &[&ValidationCase],
    category: ErrorCategory,
    code: &'static str,
) -> Result<(), ContractError> {
    if required_case_ids.is_empty() {
        return Err(error(
            category,
            code,
            "at least one correctness evidence case is required",
        ));
    }

    let mut supplied_ids = HashSet::with_capacity(evidence.len());
    for record in evidence {
        if !supplied_ids.insert(record.case_id()) {
            return Err(error(
                category,
                code,
                "duplicate evidence records are not admissible",
            ));
        }
    }

    for required in required_case_ids {
        let record = evidence
            .iter()
            .copied()
            .find(|record| record.case_id() == required)
            .ok_or_else(|| {
                error(
                    category,
                    code,
                    "a referenced correctness evidence case was not supplied",
                )
            })?;
        if record.evidence_status() != EvidenceStatus::Verified
            || record.actual_status() != ActualStatus::Passed
        {
            return Err(error(
                category,
                code,
                "all referenced correctness evidence must be executed, passed, and verified",
            ));
        }
    }

    Ok(())
}

fn require_exact_evidence_level(
    cell: &CompatibilityCellDescriptor,
    evidence: &[&ValidationCase],
) -> Result<(), ContractError> {
    for required in &cell.evidence_case_ids {
        let record = evidence
            .iter()
            .copied()
            .find(|record| record.case_id() == required)
            .ok_or_else(|| {
                error(
                    ErrorCategory::InvalidEvidence,
                    "invalid_compatibility_evidence",
                    "a referenced compatibility evidence case was not supplied",
                )
            })?;
        if record.evidence_level() != Some(cell.level) {
            return Err(error(
                ErrorCategory::InvalidEvidence,
                "compatibility_evidence_level_mismatch",
                "compatibility evidence must match the exact matrix level it verifies",
            ));
        }
    }

    Ok(())
}

fn error(category: ErrorCategory, code: &'static str, message: impl AsRef<str>) -> ContractError {
    ContractError::new(category, code, message)
}
