use std::fmt;

use crate::{f16_to_f32, QK8_0};

const BLOCK_BYTES: usize = 34;

/// Failures reported by the strict portable Q8_0 reference operations.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Q8_0Error {
    ZeroRowWidth,
    RowWidthNotDivisible { row_width: usize },
    ArithmeticOverflow,
    EncodedLengthMismatch { expected: usize, actual: usize },
    ActivationLengthMismatch { expected: usize, actual: usize },
    DestinationLengthMismatch { expected: usize, actual: usize },
    NonFiniteScale { block_index: usize },
    NonFiniteActivation { index: usize },
    NonFiniteResult { row: usize },
}

impl fmt::Display for Q8_0Error {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::ZeroRowWidth => formatter.write_str("Q8_0 row width must be non-zero"),
            Self::RowWidthNotDivisible { row_width } => write!(
                formatter,
                "Q8_0 row width {row_width} is not divisible by {QK8_0}"
            ),
            Self::ArithmeticOverflow => {
                formatter.write_str("Q8_0 shape or byte-count arithmetic overflowed")
            }
            Self::EncodedLengthMismatch { expected, actual } => write!(
                formatter,
                "Q8_0 encoded length mismatch: expected {expected} bytes, got {actual}"
            ),
            Self::ActivationLengthMismatch { expected, actual } => write!(
                formatter,
                "Q8_0 activation length mismatch: expected {expected}, got {actual}"
            ),
            Self::DestinationLengthMismatch { expected, actual } => write!(
                formatter,
                "Q8_0 destination length mismatch: expected {expected}, got {actual}"
            ),
            Self::NonFiniteScale { block_index } => {
                write!(formatter, "Q8_0 block {block_index} has a non-finite scale")
            }
            Self::NonFiniteActivation { index } => {
                write!(formatter, "Q8_0 activation at index {index} is non-finite")
            }
            Self::NonFiniteResult { row } => {
                write!(
                    formatter,
                    "Q8_0 matvec row {row} produced a non-finite result"
                )
            }
        }
    }
}

impl std::error::Error for Q8_0Error {}

#[derive(Clone, Copy)]
struct RowLayout {
    encoded_bytes: usize,
}

fn checked_row_layout(row_width: usize) -> Result<RowLayout, Q8_0Error> {
    if row_width == 0 {
        return Err(Q8_0Error::ZeroRowWidth);
    }
    if !row_width.is_multiple_of(QK8_0) {
        return Err(Q8_0Error::RowWidthNotDivisible { row_width });
    }

    let block_count = row_width / QK8_0;
    let encoded_bytes = block_count
        .checked_mul(BLOCK_BYTES)
        .ok_or(Q8_0Error::ArithmeticOverflow)?;
    Ok(RowLayout { encoded_bytes })
}

fn scale_for_block(block: &[u8], block_index: usize) -> Result<f32, Q8_0Error> {
    let scale = f16_to_f32(u16::from_le_bytes([block[0], block[1]]));
    if !scale.is_finite() {
        return Err(Q8_0Error::NonFiniteScale { block_index });
    }
    Ok(scale)
}

fn validate_scales(encoded: &[u8]) -> Result<(), Q8_0Error> {
    for (block_index, block) in encoded.chunks_exact(BLOCK_BYTES).enumerate() {
        scale_for_block(block, block_index)?;
    }
    Ok(())
}

/// Decode exactly one complete Q8_0 row into `destination`.
///
/// The row has no partial-block tail: `row_width` must be a non-zero multiple
/// of 32 and `encoded` must contain exactly 34 bytes per block. All malformed
/// input is rejected before `destination` is modified.
pub fn decode_q8_0_row(
    encoded: &[u8],
    row_width: usize,
    destination: &mut [f32],
) -> Result<(), Q8_0Error> {
    let layout = checked_row_layout(row_width)?;
    if encoded.len() != layout.encoded_bytes {
        return Err(Q8_0Error::EncodedLengthMismatch {
            expected: layout.encoded_bytes,
            actual: encoded.len(),
        });
    }
    if destination.len() != row_width {
        return Err(Q8_0Error::DestinationLengthMismatch {
            expected: row_width,
            actual: destination.len(),
        });
    }
    validate_scales(encoded)?;

    for (block, output) in encoded
        .chunks_exact(BLOCK_BYTES)
        .zip(destination.chunks_exact_mut(QK8_0))
    {
        // Scale validity was established before any destination write.
        let scale = f16_to_f32(u16::from_le_bytes([block[0], block[1]]));
        for (value, &quantized) in output.iter_mut().zip(&block[2..]) {
            *value = scale * (quantized as i8) as f32;
        }
    }
    Ok(())
}

fn dot_row(encoded_row: &[u8], activation: &[f32]) -> f32 {
    let mut accumulator = 0.0_f32;
    for (block, activation_block) in encoded_row
        .chunks_exact(BLOCK_BYTES)
        .zip(activation.chunks_exact(QK8_0))
    {
        let scale = f16_to_f32(u16::from_le_bytes([block[0], block[1]]));
        for (&quantized, &input) in block[2..].iter().zip(activation_block) {
            let weight = scale * (quantized as i8) as f32;
            accumulator += weight * input;
        }
    }
    accumulator
}

/// Multiply a row-major Q8_0 matrix by one float32 activation vector.
///
/// Each matrix row contains `row_width / 32` consecutive 34-byte blocks. The
/// scalar reference accumulates float32 products in increasing logical-element
/// order. Validation and a complete dry run occur before any output is written.
pub fn matvec_q8_0(
    encoded: &[u8],
    rows: usize,
    row_width: usize,
    activation: &[f32],
    destination: &mut [f32],
) -> Result<(), Q8_0Error> {
    let layout = checked_row_layout(row_width)?;

    rows.checked_mul(row_width)
        .ok_or(Q8_0Error::ArithmeticOverflow)?;
    let encoded_bytes = rows
        .checked_mul(layout.encoded_bytes)
        .ok_or(Q8_0Error::ArithmeticOverflow)?;

    if encoded.len() != encoded_bytes {
        return Err(Q8_0Error::EncodedLengthMismatch {
            expected: encoded_bytes,
            actual: encoded.len(),
        });
    }
    if activation.len() != row_width {
        return Err(Q8_0Error::ActivationLengthMismatch {
            expected: row_width,
            actual: activation.len(),
        });
    }
    if destination.len() != rows {
        return Err(Q8_0Error::DestinationLengthMismatch {
            expected: rows,
            actual: destination.len(),
        });
    }

    validate_scales(encoded)?;
    if let Some(index) = activation.iter().position(|value| !value.is_finite()) {
        return Err(Q8_0Error::NonFiniteActivation { index });
    }

    // First calculate every row without writing so a non-finite later row
    // cannot leave an otherwise valid prefix in the destination.
    for (row, encoded_row) in encoded.chunks_exact(layout.encoded_bytes).enumerate() {
        if !dot_row(encoded_row, activation).is_finite() {
            return Err(Q8_0Error::NonFiniteResult { row });
        }
    }

    for (output, encoded_row) in destination
        .iter_mut()
        .zip(encoded.chunks_exact(layout.encoded_bytes))
    {
        *output = dot_row(encoded_row, activation);
    }
    Ok(())
}
