//! Checkpoint-free Feature 017 R11 final-output qualification boundary.
//!
//! The real GLM-5.2 output head is Q4_K.  This module keeps the packed Q4_K
//! decoder, exact f32 scaffold, production matvec injection, and stable
//! output-token ordering together so fixture mode cannot quietly replace the
//! output path with a Q8_0 projection.

use crate::layer_qualification::exact_rms_norm_f32;
use crate::qualification::{exact_matvec_f32, QualificationError};

pub const R11_SCAFFOLD_VERSION: &str = "f017-r11-final-output-exact-v1";
pub const Q4_K_ELEMENTS_PER_BLOCK: usize = 256;
pub const Q4_K_BYTES_PER_BLOCK: usize = 144;

#[derive(Debug, Clone, PartialEq)]
pub struct R11Inputs {
    pub final_hidden: Vec<f32>,
    pub output_norm_scale: Vec<f32>,
    pub rms_epsilon: f32,
    pub output_head_packed: Vec<u8>,
    pub output_rows: usize,
    pub output_columns: usize,
    pub top_k: usize,
}

#[derive(Debug, Clone, PartialEq)]
pub struct R11Output {
    pub normalized: Vec<f32>,
    pub decoded_output_head: Vec<f32>,
    pub logits: Vec<f32>,
    pub top_k_ids: Vec<usize>,
    pub top_k_scores: Vec<f32>,
    pub argmax: usize,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum R11Error {
    InvalidShape(&'static str),
    EncodedLength,
    Decode,
    Matvec(QualificationError),
    CandidateMatvec(&'static str),
    NonFiniteLogit,
}

impl std::fmt::Display for R11Error {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidShape(field) => write!(formatter, "invalid R11 shape: {field}"),
            Self::EncodedLength => write!(formatter, "invalid Q4_K encoded length"),
            Self::Decode => write!(formatter, "Q4_K decode produced an invalid output"),
            Self::Matvec(error) => write!(formatter, "R11 exact matvec failed: {error}"),
            Self::CandidateMatvec(role) => write!(formatter, "R11 candidate matvec failed: {role}"),
            Self::NonFiniteLogit => write!(formatter, "R11 logits must be finite"),
        }
    }
}

impl std::error::Error for R11Error {}

impl From<QualificationError> for R11Error {
    fn from(error: QualificationError) -> Self {
        Self::Matvec(error)
    }
}

pub fn decode_q4_k_matrix(
    packed: &[u8],
    rows: usize,
    columns: usize,
) -> Result<Vec<f32>, R11Error> {
    if rows == 0 || columns == 0 || columns % Q4_K_ELEMENTS_PER_BLOCK != 0 {
        return Err(R11Error::InvalidShape("q4_k_matrix"));
    }
    let blocks_per_row = columns / Q4_K_ELEMENTS_PER_BLOCK;
    let bytes_per_row = blocks_per_row
        .checked_mul(Q4_K_BYTES_PER_BLOCK)
        .ok_or(R11Error::InvalidShape("q4_k_row_bytes"))?;
    let expected_bytes = rows
        .checked_mul(bytes_per_row)
        .ok_or(R11Error::InvalidShape("q4_k_matrix_bytes"))?;
    if packed.len() != expected_bytes {
        return Err(R11Error::EncodedLength);
    }
    let output_len = rows
        .checked_mul(columns)
        .ok_or(R11Error::InvalidShape("q4_k_output"))?;
    let mut decoded = Vec::with_capacity(output_len);
    for row in packed.chunks_exact(bytes_per_row) {
        let values = quant::cpu_dot::dequant_q4_k(row, columns);
        if values.len() != columns || values.iter().any(|value| !value.is_finite()) {
            return Err(R11Error::Decode);
        }
        decoded.extend(values);
    }
    if decoded.len() != output_len {
        return Err(R11Error::Decode);
    }
    Ok(decoded)
}

pub fn run_r11_exact(inputs: &R11Inputs) -> Result<R11Output, R11Error> {
    run_r11_with_matvec(inputs, |matrix, rows, columns, vector, role| {
        let mut output = vec![0.0_f32; rows];
        exact_matvec_f32(matrix, rows, columns, vector, &mut output)
            .map_err(|_| R11Error::CandidateMatvec(role))?;
        Ok(output)
    })
}

pub fn run_r11_with_matvec<F>(inputs: &R11Inputs, matvec: F) -> Result<R11Output, R11Error>
where
    F: FnMut(&[f32], usize, usize, &[f32], &'static str) -> Result<Vec<f32>, R11Error>,
{
    validate_inputs(inputs)?;
    let decoded_output_head = decode_q4_k_matrix(
        &inputs.output_head_packed,
        inputs.output_rows,
        inputs.output_columns,
    )?;
    run_r11_with_decoded_matvec(inputs, decoded_output_head, matvec)
}

pub fn run_r11_with_decoded_matvec<F>(
    inputs: &R11Inputs,
    decoded_output_head: Vec<f32>,
    mut matvec: F,
) -> Result<R11Output, R11Error>
where
    F: FnMut(&[f32], usize, usize, &[f32], &'static str) -> Result<Vec<f32>, R11Error>,
{
    validate_inputs(inputs)?;
    let expected_elements = inputs
        .output_rows
        .checked_mul(inputs.output_columns)
        .ok_or(R11Error::InvalidShape("q4_k_output"))?;
    if decoded_output_head.len() != expected_elements
        || decoded_output_head.iter().any(|value| !value.is_finite())
    {
        return Err(R11Error::Decode);
    }
    let normalized = exact_rms_norm_f32(
        &inputs.final_hidden,
        &inputs.output_norm_scale,
        inputs.rms_epsilon,
    )
    .map_err(|_| R11Error::InvalidShape("final_rms_norm"))?;
    let logits = matvec(
        &decoded_output_head,
        inputs.output_rows,
        inputs.output_columns,
        &normalized,
        "output_head",
    )?;
    if logits.len() != inputs.output_rows || logits.iter().any(|value| !value.is_finite()) {
        return Err(R11Error::NonFiniteLogit);
    }
    let top_k_ids = stable_top_k(&logits, inputs.top_k)?;
    let top_k_scores = top_k_ids.iter().map(|&index| logits[index]).collect();
    Ok(R11Output {
        normalized,
        decoded_output_head,
        logits,
        argmax: top_k_ids[0],
        top_k_ids,
        top_k_scores,
    })
}

fn validate_inputs(inputs: &R11Inputs) -> Result<(), R11Error> {
    if inputs.final_hidden.is_empty()
        || inputs.final_hidden.len() != inputs.output_norm_scale.len()
        || inputs.output_columns != inputs.final_hidden.len()
        || inputs.top_k == 0
        || inputs.top_k > inputs.output_rows
        || !inputs.rms_epsilon.is_finite()
        || inputs.rms_epsilon <= 0.0
    {
        return Err(R11Error::InvalidShape("R11 inputs"));
    }
    Ok(())
}

pub fn stable_top_k(logits: &[f32], count: usize) -> Result<Vec<usize>, R11Error> {
    if count == 0 || count > logits.len() || logits.iter().any(|value| !value.is_finite()) {
        return Err(R11Error::NonFiniteLogit);
    }
    let mut indices = (0..logits.len()).collect::<Vec<_>>();
    indices.sort_by(|&left, &right| {
        logits[right]
            .total_cmp(&logits[left])
            .then_with(|| left.cmp(&right))
    });
    indices.truncate(count);
    Ok(indices)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stable_top_k_is_descending_and_lower_index_stable_on_ties() {
        assert_eq!(stable_top_k(&[3.0, 4.0, 4.0, -1.0], 3).unwrap(), [1, 2, 0]);
    }

    #[test]
    fn q4_k_decoder_rejects_truncated_rows_without_partial_result() {
        assert_eq!(
            decode_q4_k_matrix(&[0; Q4_K_BYTES_PER_BLOCK - 1], 1, Q4_K_ELEMENTS_PER_BLOCK),
            Err(R11Error::EncodedLength)
        );
        assert_eq!(
            decode_q4_k_matrix(&[0; Q4_K_BYTES_PER_BLOCK], 1, 32),
            Err(R11Error::InvalidShape("q4_k_matrix"))
        );
    }
}
