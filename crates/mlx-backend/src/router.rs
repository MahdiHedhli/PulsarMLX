//! Bounded, model-neutral contracts for the Feature 002 router boundary.
//!
//! This module admits an already-observed complete F32 router range and
//! validates bounded output/evidence values.  It does not discover, acquire,
//! or execute an external checkpoint.

use backend::{ContractError, ErrorCategory};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::fs::File;
use std::io::{self, ErrorKind};
use std::mem::size_of;
#[cfg(unix)]
use std::os::unix::fs::FileExt;

pub const ROUTER_CONTRACT_ID: &str = "qwen3moe-layer0-router-parity-v1";
pub const ROUTER_TENSOR_NAME: &str = "blk.0.ffn_gate_inp.weight";
pub const ROUTER_HIDDEN_WIDTH: usize = 2_048;
pub const ROUTER_EXPERT_COUNT: usize = 128;
pub const ROUTER_TOP_K: usize = 8;
pub const ROUTER_TENSOR_ELEMENTS: u64 = 262_144;
pub const ROUTER_TENSOR_BYTES: u64 = 1_048_576;
pub const ROUTER_MAX_ROWS: usize = 2;

const ROUTER_SEMANTIC_ROLE: &str = "layer_0_router_projection";
const ROUTER_GGUF_TYPE: &str = "F32";
const ROUTER_QUANTIZATION: &str = "none_f32";
const ROUTER_BYTE_ORDER: &str = "little";
const ROUTER_ORIENTATION: &str = "expert_major_rows_input_columns";
const WEIGHT_SUM_TOLERANCE: f64 = 1.0e-6;
const PROBABILITY_ABSOLUTE_TOLERANCE: f64 = 1.0e-6;
const PROBABILITY_RELATIVE_TOLERANCE: f64 = 1.0e-6;
const MAX_CASE_ID_CHARS: usize = 128;

/// Exact caller-observed identity for a complete router tensor range.
#[derive(Debug, Clone, PartialEq)]
pub struct RouterTensorDescriptor {
    pub name: String,
    pub semantic_role: String,
    pub occurrence_count: u64,
    pub gguf_dimensions_fastest_axis_first: Vec<u64>,
    pub reader_shape: Vec<u64>,
    pub execution_shape: Vec<u64>,
    pub gguf_type: String,
    pub quantization: String,
    pub logical_elements: u64,
    pub absolute_data_offset: u64,
    pub encoded_length: u64,
    pub encoded_sha256: String,
    pub byte_order: String,
    pub orientation: String,
    pub expert_count: u64,
    pub top_k: u64,
    pub weight_scale: f32,
    pub bias_present: bool,
    pub correction_bias_present: bool,
}

/// A structurally admitted tensor range. External artifact identity remains a
/// separate pre-execution gate.
#[derive(Debug, Clone, PartialEq)]
pub struct AdmittedRouterTensor {
    descriptor: RouterTensorDescriptor,
    model_file_bytes: u64,
    exclusive_end_offset: u64,
}

impl AdmittedRouterTensor {
    pub fn name(&self) -> &str {
        &self.descriptor.name
    }

    pub fn semantic_role(&self) -> &str {
        &self.descriptor.semantic_role
    }

    pub fn gguf_dimensions(&self) -> &[u64] {
        &self.descriptor.gguf_dimensions_fastest_axis_first
    }

    pub fn reader_shape(&self) -> &[u64] {
        &self.descriptor.reader_shape
    }

    pub fn execution_shape(&self) -> &[u64] {
        &self.descriptor.execution_shape
    }

    pub fn gguf_type(&self) -> &str {
        &self.descriptor.gguf_type
    }

    pub fn quantization(&self) -> &str {
        &self.descriptor.quantization
    }

    pub fn logical_elements(&self) -> u64 {
        self.descriptor.logical_elements
    }

    pub fn absolute_data_offset(&self) -> u64 {
        self.descriptor.absolute_data_offset
    }

    pub fn encoded_length(&self) -> u64 {
        self.descriptor.encoded_length
    }

    pub fn model_file_bytes(&self) -> u64 {
        self.model_file_bytes
    }

    pub fn exclusive_end_offset(&self) -> u64 {
        self.exclusive_end_offset
    }

    pub fn encoded_sha256(&self) -> &str {
        &self.descriptor.encoded_sha256
    }

    pub fn expert_count(&self) -> u64 {
        self.descriptor.expert_count
    }

    pub fn top_k(&self) -> u64 {
        self.descriptor.top_k
    }

    pub fn weight_scale(&self) -> f32 {
        self.descriptor.weight_scale
    }

    pub fn bias_present(&self) -> bool {
        self.descriptor.bias_present
    }

    pub fn correction_bias_present(&self) -> bool {
        self.descriptor.correction_bias_present
    }
}

/// Admit only the exact complete version-1 F32 router contract.
pub fn admit_router_tensor(
    descriptor: &RouterTensorDescriptor,
    model_file_bytes: u64,
) -> Result<AdmittedRouterTensor, ContractError> {
    if descriptor.name != ROUTER_TENSOR_NAME
        || descriptor.semantic_role != ROUTER_SEMANTIC_ROLE
        || descriptor.occurrence_count != 1
    {
        return Err(router_tensor_error(
            "model_tensor_mismatch",
            "router tensor identity or occurrence count differs from contract v1",
        ));
    }
    if descriptor.gguf_dimensions_fastest_axis_first != [2_048, 128]
        || descriptor.reader_shape != [128, 2_048]
        || descriptor.execution_shape != [128, 2_048]
        || descriptor.logical_elements != ROUTER_TENSOR_ELEMENTS
    {
        return Err(router_tensor_error(
            "model_tensor_mismatch",
            "router tensor dimensions or element count differ from contract v1",
        ));
    }
    if descriptor.gguf_type != ROUTER_GGUF_TYPE {
        return Err(ContractError::new(
            ErrorCategory::InvalidQuantization,
            "unsupported_tensor_quantization",
            "router contract v1 admits only a complete F32 tensor",
        ));
    }
    if descriptor.quantization != ROUTER_QUANTIZATION
        || descriptor.byte_order != ROUTER_BYTE_ORDER
        || descriptor.orientation != ROUTER_ORIENTATION
    {
        return Err(ContractError::new(
            ErrorCategory::InvalidTensor,
            "invalid_layout",
            "router storage encoding or orientation differs from contract v1",
        ));
    }
    if descriptor.encoded_length != ROUTER_TENSOR_BYTES {
        return Err(router_tensor_error(
            "model_tensor_mismatch",
            "router tensor encoded byte length differs from complete F32 contract",
        ));
    }
    let exclusive_end_offset = descriptor
        .absolute_data_offset
        .checked_add(descriptor.encoded_length)
        .ok_or_else(|| {
            ContractError::new(
                ErrorCategory::ArithmeticOverflow,
                "invalid_tensor_range",
                "router tensor range overflows the artifact address space",
            )
        })?;
    if descriptor.absolute_data_offset >= model_file_bytes
        || exclusive_end_offset > model_file_bytes
    {
        return Err(ContractError::new(
            ErrorCategory::InvalidTensor,
            "invalid_tensor_range",
            "router tensor range is outside the immutable artifact",
        ));
    }
    if !is_lower_hex_sha256(&descriptor.encoded_sha256) {
        return Err(router_tensor_error(
            "model_checksum_mismatch",
            "router tensor range hash is not a canonical SHA-256 identity",
        ));
    }
    if descriptor.expert_count != ROUTER_EXPERT_COUNT as u64
        || descriptor.top_k != ROUTER_TOP_K as u64
        || descriptor.weight_scale.to_bits() != 1.0_f32.to_bits()
        || descriptor.bias_present
        || descriptor.correction_bias_present
    {
        return Err(router_tensor_error(
            "model_tensor_mismatch",
            "router expert count, top-k, scale, or bias metadata differs from contract v1",
        ));
    }

    Ok(AdmittedRouterTensor {
        descriptor: descriptor.clone(),
        model_file_bytes,
        exclusive_end_offset,
    })
}

/// Positional-read one exact bounded range without changing a file cursor.
///
/// Interrupted reads are retried, partial reads advance, and zero progress or
/// early EOF fails closed. The caller must separately verify file identity
/// before and after this operation.
#[cfg(unix)]
pub fn read_exact_range_at(
    file: &File,
    offset: u64,
    length: usize,
) -> Result<Vec<u8>, ContractError> {
    positional_read_exact(offset, length, |position, buffer| {
        file.read_at(buffer, position)
    })
}

/// Read, hash-bind, and decode the exact range carried by an admitted router.
///
/// The open file's current length must still match the length observed during
/// admission. Callers that also possess a frozen whole-artifact identity must
/// recheck that identity before and after execution.
#[cfg(unix)]
pub fn read_admitted_router_tensor_f32(
    file: &File,
    admitted: &AdmittedRouterTensor,
) -> Result<Vec<f32>, ContractError> {
    let metadata = file.metadata().map_err(|_| {
        router_tensor_error(
            "model_read_failed",
            "admitted router artifact metadata could not be rechecked",
        )
    })?;
    if !metadata.is_file() || metadata.len() != admitted.model_file_bytes {
        return Err(router_tensor_error(
            "model_size_mismatch",
            "admitted router artifact length changed before positional read",
        ));
    }
    let length = usize::try_from(admitted.descriptor.encoded_length).map_err(|_| {
        ContractError::new(
            ErrorCategory::ArithmeticOverflow,
            "invalid_tensor_range",
            "admitted router tensor length is not representable",
        )
    })?;
    let bytes = read_exact_range_at(file, admitted.descriptor.absolute_data_offset, length)?;
    if format!("{:x}", Sha256::digest(&bytes)) != admitted.descriptor.encoded_sha256 {
        return Err(router_tensor_error(
            "model_checksum_mismatch",
            "admitted router tensor bytes differ from the frozen range identity",
        ));
    }
    if bytes.len() != ROUTER_TENSOR_BYTES as usize || bytes.len() % size_of::<f32>() != 0 {
        return Err(invalid_byte_count(
            "admitted router tensor did not yield the exact complete F32 byte count",
        ));
    }

    let mut values = Vec::with_capacity(ROUTER_TENSOR_ELEMENTS as usize);
    for encoded in bytes.chunks_exact(size_of::<f32>()) {
        let value = f32::from_le_bytes(
            encoded
                .try_into()
                .expect("chunks_exact yields one complete float32 value"),
        );
        if !value.is_finite() {
            return Err(ContractError::new(
                ErrorCategory::InvalidTensor,
                "invalid_dtype",
                "admitted router tensor contains a non-finite float32 value",
            ));
        }
        values.push(value);
    }
    if values.len() != ROUTER_TENSOR_ELEMENTS as usize {
        return Err(invalid_byte_count(
            "admitted router tensor decoded element count differs from contract v1",
        ));
    }
    Ok(values)
}

/// Testable core for an exact positional range read.
pub fn positional_read_exact<F>(
    offset: u64,
    length: usize,
    mut read_at: F,
) -> Result<Vec<u8>, ContractError>
where
    F: FnMut(u64, &mut [u8]) -> io::Result<usize>,
{
    if length == 0 {
        return Err(invalid_byte_count("router tensor reads must be nonempty"));
    }
    let length_u64 = u64::try_from(length).map_err(|_| {
        ContractError::new(
            ErrorCategory::ArithmeticOverflow,
            "invalid_tensor_range",
            "router tensor read length is not representable",
        )
    })?;
    offset.checked_add(length_u64).ok_or_else(|| {
        ContractError::new(
            ErrorCategory::ArithmeticOverflow,
            "invalid_tensor_range",
            "router tensor read range overflows",
        )
    })?;

    let mut bytes = vec![0_u8; length];
    let mut consumed = 0_usize;
    while consumed < length {
        let position = offset
            .checked_add(u64::try_from(consumed).map_err(|_| {
                ContractError::new(
                    ErrorCategory::ArithmeticOverflow,
                    "invalid_tensor_range",
                    "router tensor read position is not representable",
                )
            })?)
            .ok_or_else(|| {
                ContractError::new(
                    ErrorCategory::ArithmeticOverflow,
                    "invalid_tensor_range",
                    "router tensor read position overflows",
                )
            })?;
        match read_at(position, &mut bytes[consumed..]) {
            Ok(0) => {
                return Err(invalid_byte_count(
                    "router tensor positional read ended before the exact range was complete",
                ));
            }
            Ok(read) if read <= length - consumed => consumed += read,
            Ok(_) => {
                return Err(invalid_byte_count(
                    "router tensor positional reader returned an impossible byte count",
                ));
            }
            Err(error) if error.kind() == ErrorKind::Interrupted => continue,
            Err(_) => {
                return Err(invalid_byte_count(
                    "router tensor positional read failed before completion",
                ));
            }
        }
    }
    Ok(bytes)
}

/// Canonical SHA-256 over finite IEEE-754 float32 little-endian values.
pub fn canonical_f32le_sha256(values: &[f32]) -> Result<String, ContractError> {
    if values.iter().any(|value| !value.is_finite()) {
        return Err(ContractError::new(
            ErrorCategory::InvalidComparison,
            "invalid_dtype",
            "canonical router output hashing rejects non-finite float32 values",
        ));
    }
    let mut digest = Sha256::new();
    for value in values {
        digest.update(value.to_le_bytes());
    }
    Ok(format!("{:x}", digest.finalize()))
}

/// Complete bounded router output for one generated or admitted case.
#[derive(Debug, Clone, PartialEq)]
pub struct RouterOutput {
    case_id: String,
    row_count: usize,
    logits_shape: [usize; 2],
    full_probabilities_shape: [usize; 2],
    logits: Vec<f32>,
    full_probabilities: Vec<f32>,
    selected_expert_ids: Vec<Vec<u64>>,
    selected_probabilities: Vec<Vec<f32>>,
    normalized_weights: Vec<Vec<f32>>,
    logits_f32le_sha256: String,
    full_probabilities_f32le_sha256: String,
    selected_probabilities_f32le_sha256: String,
    normalized_weights_f32le_sha256: String,
}

impl RouterOutput {
    #[allow(clippy::too_many_arguments)]
    pub fn try_new(
        case_id: impl Into<String>,
        row_count: usize,
        logits: Vec<f32>,
        full_probabilities: Vec<f32>,
        selected_expert_ids: Vec<Vec<u64>>,
        selected_probabilities: Vec<Vec<f32>>,
        normalized_weights: Vec<Vec<f32>>,
    ) -> Result<Self, ContractError> {
        let case_id = case_id.into();
        validate_case_id(&case_id)?;
        if !(1..=ROUTER_MAX_ROWS).contains(&row_count) {
            return Err(invalid_shape(
                "router output row count exceeds the bounded contract",
            ));
        }
        let complete_count = row_count.checked_mul(ROUTER_EXPERT_COUNT).ok_or_else(|| {
            ContractError::new(
                ErrorCategory::ArithmeticOverflow,
                "invalid_shape",
                "router output element count overflows",
            )
        })?;
        if logits.len() != complete_count || full_probabilities.len() != complete_count {
            return Err(invalid_shape(
                "router output must retain all 128 logits and probabilities per row",
            ));
        }
        if selected_expert_ids.len() != row_count
            || selected_probabilities.len() != row_count
            || normalized_weights.len() != row_count
        {
            return Err(invalid_shape(
                "router selected-output row count differs from the complete output",
            ));
        }
        ensure_finite(&logits, "router logits contain a non-finite value")?;
        ensure_finite(
            &full_probabilities,
            "router probabilities contain a non-finite value",
        )?;

        for row_index in 0..row_count {
            let ids = &selected_expert_ids[row_index];
            let selected = &selected_probabilities[row_index];
            let normalized = &normalized_weights[row_index];
            if ids.len() != ROUTER_TOP_K
                || selected.len() != ROUTER_TOP_K
                || normalized.len() != ROUTER_TOP_K
            {
                return Err(invalid_shape(
                    "router selected outputs must contain exactly eight values per row",
                ));
            }
            let unique: BTreeSet<u64> = ids.iter().copied().collect();
            if unique.len() != ROUTER_TOP_K
                || ids
                    .iter()
                    .any(|expert_id| *expert_id >= ROUTER_EXPERT_COUNT as u64)
            {
                return Err(ContractError::new(
                    ErrorCategory::InvalidSelection,
                    "comparison_failed",
                    "router selected expert IDs are duplicated or out of range",
                ));
            }
            ensure_finite(selected, "selected router probabilities are non-finite")?;
            ensure_finite(normalized, "normalized router weights are non-finite")?;
            let logits_row =
                &logits[row_index * ROUTER_EXPERT_COUNT..(row_index + 1) * ROUTER_EXPERT_COUNT];
            let probability_row = &full_probabilities
                [row_index * ROUTER_EXPERT_COUNT..(row_index + 1) * ROUTER_EXPERT_COUNT];
            validate_complete_softmax(logits_row, probability_row)?;

            let mut expected_ids = (0..ROUTER_EXPERT_COUNT).collect::<Vec<_>>();
            expected_ids.sort_by(|left, right| {
                probability_row[*right]
                    .total_cmp(&probability_row[*left])
                    .then_with(|| left.cmp(right))
            });
            expected_ids.truncate(ROUTER_TOP_K);
            if ids
                .iter()
                .copied()
                .ne(expected_ids.iter().map(|expert_id| *expert_id as u64))
            {
                return Err(ContractError::new(
                    ErrorCategory::InvalidSelection,
                    "comparison_failed",
                    "router selected expert IDs do not match deterministic complete-softmax order",
                ));
            }
            for (rank, expert_id) in ids.iter().enumerate() {
                let expert_index = usize::try_from(*expert_id).map_err(|_| {
                    invalid_shape("router expert ID is not representable on this host")
                })?;
                if selected[rank].to_bits() != probability_row[expert_index].to_bits() {
                    return Err(ContractError::new(
                        ErrorCategory::InvalidComparison,
                        "comparison_failed",
                        "selected router probability does not match the complete softmax output",
                    ));
                }
            }
            if selected.iter().any(|value| *value < 0.0)
                || normalized.iter().any(|value| *value < 0.0)
            {
                return Err(ContractError::new(
                    ErrorCategory::InvalidComparison,
                    "comparison_failed",
                    "router probabilities and weights must be nonnegative",
                ));
            }
            let selected_sum = selected.iter().copied().map(f64::from).sum::<f64>();
            let normalized_sum = normalized.iter().copied().map(f64::from).sum::<f64>();
            if !selected_sum.is_finite()
                || selected_sum <= 0.0
                || !normalized_sum.is_finite()
                || (normalized_sum - 1.0).abs() > WEIGHT_SUM_TOLERANCE
            {
                return Err(ContractError::new(
                    ErrorCategory::InvalidComparison,
                    "comparison_failed",
                    "router selected sum or normalized weight sum is invalid",
                ));
            }
            for (selected_value, normalized_value) in selected.iter().zip(normalized) {
                let expected = f64::from(*selected_value) / selected_sum;
                if (f64::from(*normalized_value) - expected).abs() > WEIGHT_SUM_TOLERANCE {
                    return Err(ContractError::new(
                        ErrorCategory::InvalidComparison,
                        "comparison_failed",
                        "normalized router weight does not match selected-probability renormalization",
                    ));
                }
            }
        }

        let selected_flat = selected_probabilities
            .iter()
            .flatten()
            .copied()
            .collect::<Vec<_>>();
        let normalized_flat = normalized_weights
            .iter()
            .flatten()
            .copied()
            .collect::<Vec<_>>();
        let logits_f32le_sha256 = canonical_f32le_sha256(&logits)?;
        let full_probabilities_f32le_sha256 = canonical_f32le_sha256(&full_probabilities)?;
        let selected_probabilities_f32le_sha256 = canonical_f32le_sha256(&selected_flat)?;
        let normalized_weights_f32le_sha256 = canonical_f32le_sha256(&normalized_flat)?;

        Ok(Self {
            case_id,
            row_count,
            logits_shape: [row_count, ROUTER_EXPERT_COUNT],
            full_probabilities_shape: [row_count, ROUTER_EXPERT_COUNT],
            logits,
            full_probabilities,
            selected_expert_ids,
            selected_probabilities,
            normalized_weights,
            logits_f32le_sha256,
            full_probabilities_f32le_sha256,
            selected_probabilities_f32le_sha256,
            normalized_weights_f32le_sha256,
        })
    }

    pub fn case_id(&self) -> &str {
        &self.case_id
    }

    pub fn row_count(&self) -> usize {
        self.row_count
    }

    pub fn logits_shape(&self) -> &[usize; 2] {
        &self.logits_shape
    }

    pub fn full_probabilities_shape(&self) -> &[usize; 2] {
        &self.full_probabilities_shape
    }

    pub fn logits(&self) -> &[f32] {
        &self.logits
    }

    pub fn full_probabilities(&self) -> &[f32] {
        &self.full_probabilities
    }

    pub fn selected_expert_ids(&self) -> &[Vec<u64>] {
        &self.selected_expert_ids
    }

    pub fn selected_probabilities(&self) -> &[Vec<f32>] {
        &self.selected_probabilities
    }

    pub fn normalized_weights(&self) -> &[Vec<f32>] {
        &self.normalized_weights
    }

    pub fn logits_f32le_sha256(&self) -> &str {
        &self.logits_f32le_sha256
    }

    pub fn full_probabilities_f32le_sha256(&self) -> &str {
        &self.full_probabilities_f32le_sha256
    }

    pub fn selected_probabilities_f32le_sha256(&self) -> &str {
        &self.selected_probabilities_f32le_sha256
    }

    pub fn normalized_weights_f32le_sha256(&self) -> &str {
        &self.normalized_weights_f32le_sha256
    }

    pub fn repeat_identity(&self) -> RouterRepeatIdentity {
        RouterRepeatIdentity {
            case_id: self.case_id.clone(),
            row_count: self.row_count,
            logits_f32le_sha256: self.logits_f32le_sha256.clone(),
            full_probabilities_f32le_sha256: self.full_probabilities_f32le_sha256.clone(),
            selected_probabilities_f32le_sha256: self.selected_probabilities_f32le_sha256.clone(),
            normalized_weights_f32le_sha256: self.normalized_weights_f32le_sha256.clone(),
            selected_expert_ids: self.selected_expert_ids.clone(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RouterRepeatIdentity {
    case_id: String,
    row_count: usize,
    logits_f32le_sha256: String,
    full_probabilities_f32le_sha256: String,
    selected_probabilities_f32le_sha256: String,
    normalized_weights_f32le_sha256: String,
    selected_expert_ids: Vec<Vec<u64>>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RouterRepeatSummary {
    repeat_count: usize,
    unique_output_identity_count: usize,
    identical: bool,
}

impl RouterRepeatSummary {
    pub fn repeat_count(&self) -> usize {
        self.repeat_count
    }

    pub fn unique_output_identity_count(&self) -> usize {
        self.unique_output_identity_count
    }

    pub fn identical(&self) -> bool {
        self.identical
    }
}

pub fn validate_repeat_identities(
    identities: &[RouterRepeatIdentity],
) -> Result<RouterRepeatSummary, ContractError> {
    if identities.len() < 10 {
        return Err(ContractError::new(
            ErrorCategory::InvalidComparison,
            "comparison_failed",
            "router repeatability requires at least ten measured identities",
        ));
    }
    let first = identities.first().expect("length checked above");
    let unique_output_identity_count = identities
        .iter()
        .map(|identity| {
            (
                identity.case_id.as_str(),
                identity.row_count,
                identity.logits_f32le_sha256.as_str(),
                identity.full_probabilities_f32le_sha256.as_str(),
                identity.selected_probabilities_f32le_sha256.as_str(),
                identity.normalized_weights_f32le_sha256.as_str(),
                &identity.selected_expert_ids,
            )
        })
        .collect::<BTreeSet<_>>()
        .len();
    if identities.iter().any(|identity| identity != first) {
        return Err(ContractError::new(
            ErrorCategory::InvalidComparison,
            "comparison_failed",
            "router measured repetitions are not bitwise identical",
        ));
    }
    Ok(RouterRepeatSummary {
        repeat_count: identities.len(),
        unique_output_identity_count,
        identical: true,
    })
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct NumericTolerance {
    absolute: f64,
    relative: f64,
}

impl NumericTolerance {
    pub fn absolute(&self) -> f64 {
        self.absolute
    }

    pub fn relative(&self) -> f64 {
        self.relative
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct RouterTolerancePolicy {
    logits: NumericTolerance,
    full_probabilities: NumericTolerance,
    selected_probabilities: NumericTolerance,
    normalized_weights: NumericTolerance,
}

impl RouterTolerancePolicy {
    pub const fn contract_v1() -> Self {
        Self {
            logits: NumericTolerance {
                absolute: 5.0e-4,
                relative: 5.0e-4,
            },
            full_probabilities: NumericTolerance {
                absolute: 1.0e-6,
                relative: 1.0e-6,
            },
            selected_probabilities: NumericTolerance {
                absolute: 1.0e-6,
                relative: 1.0e-6,
            },
            normalized_weights: NumericTolerance {
                absolute: 1.0e-6,
                relative: 1.0e-6,
            },
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct RouterMismatch {
    row_index: usize,
    column_index: usize,
    reference: f32,
    candidate: f32,
}

impl RouterMismatch {
    pub fn row_index(&self) -> usize {
        self.row_index
    }

    pub fn column_index(&self) -> usize {
        self.column_index
    }

    pub fn reference(&self) -> f32 {
        self.reference
    }

    pub fn candidate(&self) -> f32 {
        self.candidate
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct RouterNumericComparison {
    compared_count: usize,
    mismatch_count: usize,
    first_mismatch: Option<RouterMismatch>,
    maximum_absolute_error: f64,
    mean_absolute_error: f64,
    rmse: f64,
    maximum_relative_error: Option<f64>,
    tolerance: NumericTolerance,
}

impl RouterNumericComparison {
    pub fn compared_count(&self) -> usize {
        self.compared_count
    }

    pub fn mismatch_count(&self) -> usize {
        self.mismatch_count
    }

    pub fn first_mismatch(&self) -> Option<&RouterMismatch> {
        self.first_mismatch.as_ref()
    }

    pub fn maximum_absolute_error(&self) -> f64 {
        self.maximum_absolute_error
    }

    pub fn mean_absolute_error(&self) -> f64 {
        self.mean_absolute_error
    }

    pub fn rmse(&self) -> f64 {
        self.rmse
    }

    pub fn maximum_relative_error(&self) -> Option<f64> {
        self.maximum_relative_error
    }

    pub fn tolerance(&self) -> NumericTolerance {
        self.tolerance
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct RouterOutputComparison {
    logits: RouterNumericComparison,
    full_probabilities: RouterNumericComparison,
    selected_probabilities: RouterNumericComparison,
    normalized_weights: RouterNumericComparison,
    id_mismatch_count: usize,
    order_mismatch_count: usize,
    passed: bool,
}

impl RouterOutputComparison {
    pub fn logits(&self) -> &RouterNumericComparison {
        &self.logits
    }

    pub fn full_probabilities(&self) -> &RouterNumericComparison {
        &self.full_probabilities
    }

    pub fn selected_probabilities(&self) -> &RouterNumericComparison {
        &self.selected_probabilities
    }

    pub fn normalized_weights(&self) -> &RouterNumericComparison {
        &self.normalized_weights
    }

    pub fn id_mismatch_count(&self) -> usize {
        self.id_mismatch_count
    }

    pub fn order_mismatch_count(&self) -> usize {
        self.order_mismatch_count
    }

    pub fn passed(&self) -> bool {
        self.passed
    }
}

pub fn compare_router_outputs(
    reference: &RouterOutput,
    candidate: &RouterOutput,
    policy: &RouterTolerancePolicy,
) -> Result<RouterOutputComparison, ContractError> {
    if reference.case_id != candidate.case_id
        || reference.row_count != candidate.row_count
        || reference.logits_shape != candidate.logits_shape
        || reference.full_probabilities_shape != candidate.full_probabilities_shape
    {
        return Err(ContractError::new(
            ErrorCategory::InvalidComparison,
            "comparison_failed",
            "router outputs have incompatible identities or shapes",
        ));
    }

    let logits = compare_numeric(
        &reference.logits,
        &candidate.logits,
        ROUTER_EXPERT_COUNT,
        policy.logits,
    )?;
    let full_probabilities = compare_numeric(
        &reference.full_probabilities,
        &candidate.full_probabilities,
        ROUTER_EXPERT_COUNT,
        policy.full_probabilities,
    )?;
    let reference_selected = flatten_rows(&reference.selected_probabilities);
    let candidate_selected = flatten_rows(&candidate.selected_probabilities);
    let selected_probabilities = compare_numeric(
        &reference_selected,
        &candidate_selected,
        ROUTER_TOP_K,
        policy.selected_probabilities,
    )?;
    let reference_normalized = flatten_rows(&reference.normalized_weights);
    let candidate_normalized = flatten_rows(&candidate.normalized_weights);
    let normalized_weights = compare_numeric(
        &reference_normalized,
        &candidate_normalized,
        ROUTER_TOP_K,
        policy.normalized_weights,
    )?;

    let mut id_mismatch_count = 0_usize;
    let mut order_mismatch_count = 0_usize;
    for (reference_ids, candidate_ids) in reference
        .selected_expert_ids
        .iter()
        .zip(&candidate.selected_expert_ids)
    {
        let reference_set = reference_ids.iter().copied().collect::<BTreeSet<_>>();
        let candidate_set = candidate_ids.iter().copied().collect::<BTreeSet<_>>();
        id_mismatch_count += reference_set.difference(&candidate_set).count();
        order_mismatch_count += reference_ids
            .iter()
            .zip(candidate_ids)
            .filter(|(left, right)| left != right)
            .count();
    }

    let passed = id_mismatch_count == 0
        && order_mismatch_count == 0
        && logits.mismatch_count == 0
        && full_probabilities.mismatch_count == 0
        && selected_probabilities.mismatch_count == 0
        && normalized_weights.mismatch_count == 0;
    Ok(RouterOutputComparison {
        logits,
        full_probabilities,
        selected_probabilities,
        normalized_weights,
        id_mismatch_count,
        order_mismatch_count,
        passed,
    })
}

fn compare_numeric(
    reference: &[f32],
    candidate: &[f32],
    row_width: usize,
    tolerance: NumericTolerance,
) -> Result<RouterNumericComparison, ContractError> {
    if reference.len() != candidate.len() || reference.is_empty() || row_width == 0 {
        return Err(invalid_shape(
            "router numeric comparison inputs have incompatible lengths",
        ));
    }
    ensure_finite(reference, "router reference contains a non-finite value")?;
    ensure_finite(candidate, "router candidate contains a non-finite value")?;

    let mut mismatch_count = 0_usize;
    let mut first_mismatch = None;
    let mut maximum_absolute_error = 0.0_f64;
    let mut absolute_error_sum = 0.0_f64;
    let mut squared_error_sum = 0.0_f64;
    let mut maximum_relative_error = None::<f64>;
    for (index, (reference_value, candidate_value)) in reference.iter().zip(candidate).enumerate() {
        let reference_f64 = f64::from(*reference_value);
        let candidate_f64 = f64::from(*candidate_value);
        let absolute_error = (candidate_f64 - reference_f64).abs();
        let admitted = tolerance.absolute + tolerance.relative * reference_f64.abs();
        if absolute_error > admitted {
            mismatch_count += 1;
            first_mismatch.get_or_insert(RouterMismatch {
                row_index: index / row_width,
                column_index: index % row_width,
                reference: *reference_value,
                candidate: *candidate_value,
            });
        }
        maximum_absolute_error = maximum_absolute_error.max(absolute_error);
        absolute_error_sum += absolute_error;
        squared_error_sum += absolute_error * absolute_error;
        if reference_f64 != 0.0 {
            let relative_error = absolute_error / reference_f64.abs();
            maximum_relative_error =
                Some(maximum_relative_error.unwrap_or(0.0).max(relative_error));
        }
    }
    let compared_count = reference.len();
    let compared_f64 = compared_count as f64;
    Ok(RouterNumericComparison {
        compared_count,
        mismatch_count,
        first_mismatch,
        maximum_absolute_error,
        mean_absolute_error: absolute_error_sum / compared_f64,
        rmse: (squared_error_sum / compared_f64).sqrt(),
        maximum_relative_error,
        tolerance,
    })
}

fn flatten_rows(rows: &[Vec<f32>]) -> Vec<f32> {
    rows.iter().flatten().copied().collect()
}

fn validate_complete_softmax(logits: &[f32], probabilities: &[f32]) -> Result<(), ContractError> {
    if logits.len() != ROUTER_EXPERT_COUNT || probabilities.len() != ROUTER_EXPERT_COUNT {
        return Err(invalid_shape(
            "router softmax inputs must contain all 128 experts",
        ));
    }
    if probabilities.iter().any(|value| *value < 0.0) {
        return Err(ContractError::new(
            ErrorCategory::InvalidComparison,
            "comparison_failed",
            "complete router probabilities must be nonnegative",
        ));
    }

    let maximum = logits
        .iter()
        .copied()
        .map(f64::from)
        .reduce(f64::max)
        .expect("complete router row is nonempty");
    let exponentials = logits
        .iter()
        .map(|value| (f64::from(*value) - maximum).exp())
        .collect::<Vec<_>>();
    let denominator = exponentials.iter().sum::<f64>();
    if !denominator.is_finite() || denominator <= 0.0 {
        return Err(ContractError::new(
            ErrorCategory::InvalidComparison,
            "comparison_failed",
            "router logits do not define a finite complete softmax",
        ));
    }

    let probability_sum = probabilities.iter().copied().map(f64::from).sum::<f64>();
    if !probability_sum.is_finite() || (probability_sum - 1.0).abs() > WEIGHT_SUM_TOLERANCE {
        return Err(ContractError::new(
            ErrorCategory::InvalidComparison,
            "comparison_failed",
            "complete router probabilities do not sum to one",
        ));
    }
    for (candidate, exponential) in probabilities.iter().zip(exponentials) {
        let expected = exponential / denominator;
        let error = (f64::from(*candidate) - expected).abs();
        let admitted =
            PROBABILITY_ABSOLUTE_TOLERANCE + PROBABILITY_RELATIVE_TOLERANCE * expected.abs();
        if error > admitted {
            return Err(ContractError::new(
                ErrorCategory::InvalidComparison,
                "comparison_failed",
                "complete router probabilities are not the full softmax of the logits",
            ));
        }
    }
    Ok(())
}

fn ensure_finite(values: &[f32], message: &'static str) -> Result<(), ContractError> {
    if values.iter().any(|value| !value.is_finite()) {
        return Err(ContractError::new(
            ErrorCategory::InvalidComparison,
            "invalid_dtype",
            message,
        ));
    }
    Ok(())
}

fn validate_case_id(case_id: &str) -> Result<(), ContractError> {
    if case_id.is_empty()
        || case_id.len() > MAX_CASE_ID_CHARS
        || !case_id
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'-')
    {
        return Err(ContractError::new(
            ErrorCategory::InvalidEvidence,
            "unsupported_operation",
            "router case identity is not a bounded stable identifier",
        ));
    }
    Ok(())
}

fn is_lower_hex_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn router_tensor_error(code: &'static str, message: &'static str) -> ContractError {
    ContractError::new(ErrorCategory::InvalidTensor, code, message)
}

fn invalid_shape(message: &'static str) -> ContractError {
    ContractError::new(ErrorCategory::InvalidTensor, "invalid_shape", message)
}

fn invalid_byte_count(message: &'static str) -> ContractError {
    ContractError::new(ErrorCategory::InvalidTensor, "invalid_byte_count", message)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::VecDeque;
    #[cfg(unix)]
    use std::fs::{self, OpenOptions};
    #[cfg(unix)]
    use std::io::Write;
    #[cfg(unix)]
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn positional_read_retries_interruptions_and_joins_partial_reads() {
        let mut events = VecDeque::from([
            Err(io::Error::from(ErrorKind::Interrupted)),
            Ok(vec![1_u8, 2]),
            Ok(vec![3_u8, 4]),
        ]);
        let bytes = positional_read_exact(100, 4, |position, destination| {
            let event = events.pop_front().expect("fixture event remains")?;
            let expected_position = if destination.len() == 4 { 100 } else { 102 };
            assert_eq!(position, expected_position);
            destination[..event.len()].copy_from_slice(&event);
            Ok(event.len())
        })
        .expect("partial exact read succeeds");
        assert_eq!(bytes, [1, 2, 3, 4]);
    }

    #[test]
    fn positional_read_rejects_zero_progress() {
        let error = positional_read_exact(0, 1, |_position, _destination| Ok(0))
            .expect_err("zero progress must fail");
        assert_eq!(error.code(), "invalid_byte_count");
    }

    #[cfg(unix)]
    #[test]
    fn admitted_router_range_is_positionally_read_and_hash_bound() {
        let prefix = vec![0xa5_u8; 32];
        let encoded = vec![0_u8; ROUTER_TENSOR_BYTES as usize];
        let suffix = vec![0x5a_u8; 16];
        let model_file_bytes = (prefix.len() + encoded.len() + suffix.len()) as u64;
        let descriptor = RouterTensorDescriptor {
            name: ROUTER_TENSOR_NAME.to_owned(),
            semantic_role: ROUTER_SEMANTIC_ROLE.to_owned(),
            occurrence_count: 1,
            gguf_dimensions_fastest_axis_first: vec![2_048, 128],
            reader_shape: vec![128, 2_048],
            execution_shape: vec![128, 2_048],
            gguf_type: ROUTER_GGUF_TYPE.to_owned(),
            quantization: ROUTER_QUANTIZATION.to_owned(),
            logical_elements: ROUTER_TENSOR_ELEMENTS,
            absolute_data_offset: prefix.len() as u64,
            encoded_length: ROUTER_TENSOR_BYTES,
            encoded_sha256: format!("{:x}", Sha256::digest(&encoded)),
            byte_order: ROUTER_BYTE_ORDER.to_owned(),
            orientation: ROUTER_ORIENTATION.to_owned(),
            expert_count: ROUTER_EXPERT_COUNT as u64,
            top_k: ROUTER_TOP_K as u64,
            weight_scale: 1.0,
            bias_present: false,
            correction_bias_present: false,
        };
        let admitted = admit_router_tensor(&descriptor, model_file_bytes)
            .expect("complete exact descriptor is admitted");

        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("test clock is after the Unix epoch")
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "pulsarmlx-router-range-{}-{nonce}.bin",
            std::process::id()
        ));
        let mut file = OpenOptions::new()
            .create_new(true)
            .read(true)
            .write(true)
            .open(&path)
            .expect("create isolated router fixture");
        file.write_all(&prefix).expect("write fixture prefix");
        file.write_all(&encoded)
            .expect("write router fixture bytes");
        file.write_all(&suffix).expect("write fixture suffix");
        file.sync_all().expect("synchronize router fixture");

        let values = read_admitted_router_tensor_f32(&file, &admitted)
            .expect("the exact admitted range is read and hash-bound");
        assert_eq!(values.len(), ROUTER_TENSOR_ELEMENTS as usize);
        assert!(values.iter().all(|value| value.to_bits() == 0));
        drop(file);
        fs::remove_file(path).expect("remove isolated router fixture");
    }
}
