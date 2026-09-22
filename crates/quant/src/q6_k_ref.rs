use std::fmt;

use crate::{f16_to_f32, QK_K};

pub const Q6_K_BLOCK_BYTES: usize = 210;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Q6KError {
    ZeroRowWidth,
    RowWidthNotDivisible { row_width: usize },
    ArithmeticOverflow,
    EncodedLengthMismatch { expected: usize, actual: usize },
    DestinationLengthMismatch { expected: usize, actual: usize },
    NonFiniteScale { block_index: usize },
    NonFiniteResult { block_index: usize, element_index: usize },
}

impl fmt::Display for Q6KError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::ZeroRowWidth => formatter.write_str("Q6_K row width must be non-zero"),
            Self::RowWidthNotDivisible { row_width } => write!(
                formatter,
                "Q6_K row width {row_width} is not divisible by {QK_K}"
            ),
            Self::ArithmeticOverflow => {
                formatter.write_str("Q6_K shape or byte-count arithmetic overflowed")
            }
            Self::EncodedLengthMismatch { expected, actual } => write!(
                formatter,
                "Q6_K encoded length mismatch: expected {expected} bytes, got {actual}"
            ),
            Self::DestinationLengthMismatch { expected, actual } => write!(
                formatter,
                "Q6_K destination length mismatch: expected {expected}, got {actual}"
            ),
            Self::NonFiniteScale { block_index } => {
                write!(formatter, "Q6_K block {block_index} has a non-finite f16 scale")
            }
            Self::NonFiniteResult {
                block_index,
                element_index,
            } => write!(
                formatter,
                "Q6_K block {block_index} element {element_index} decoded to a non-finite value"
            ),
        }
    }
}

impl std::error::Error for Q6KError {}

fn checked_row_layout(row_width: usize) -> Result<usize, Q6KError> {
    if row_width == 0 {
        return Err(Q6KError::ZeroRowWidth);
    }
    if !row_width.is_multiple_of(QK_K) {
        return Err(Q6KError::RowWidthNotDivisible { row_width });
    }
    (row_width / QK_K)
        .checked_mul(Q6_K_BLOCK_BYTES)
        .ok_or(Q6KError::ArithmeticOverflow)
}

fn validate_scales(encoded: &[u8]) -> Result<(), Q6KError> {
    for (block_index, block) in encoded.chunks_exact(Q6_K_BLOCK_BYTES).enumerate() {
        let d = f16_to_f32(u16::from_le_bytes([block[208], block[209]]));
        if !d.is_finite() {
            return Err(Q6KError::NonFiniteScale { block_index });
        }
    }
    Ok(())
}

fn decode_block(
    block: &[u8],
    block_index: usize,
    output: &mut [f32],
) -> Result<(), Q6KError> {
    let ql = &block[0..128];
    let qh = &block[128..192];
    let scales = &block[192..208];
    let d = f16_to_f32(u16::from_le_bytes([block[208], block[209]]));

    for n in 0..2 {
        for l in 0..32 {
            let base = 128 * n;
            let high = qh[32 * n + l];
            let q1 = ((ql[64 * n + l] & 0x0f) | ((high & 0x03) << 4)) as i32 - 32;
            let q2 = ((ql[64 * n + 32 + l] & 0x0f) | (((high >> 2) & 0x03) << 4)) as i32 - 32;
            let q3 = ((ql[64 * n + l] >> 4) | (((high >> 4) & 0x03) << 4)) as i32 - 32;
            let q4 = ((ql[64 * n + 32 + l] >> 4) | (((high >> 6) & 0x03) << 4)) as i32 - 32;
            let values = [
                (base + l, q1),
                (base + 32 + l, q2),
                (base + 64 + l, q3),
                (base + 96 + l, q4),
            ];
            for (index, quantized) in values {
                let value = d * scales[index / 16] as i8 as f32 * quantized as f32;
                if !value.is_finite() {
                    return Err(Q6KError::NonFiniteResult {
                        block_index,
                        element_index: index,
                    });
                }
                output[index] = value;
            }
        }
    }
    Ok(())
}

/// Decode a complete row-major Q6_K matrix into an exact f32 buffer.
///
/// Q6_K uses 210-byte blocks for 256 logical values. All encoded lengths,
/// destination sizes, and block scales are validated before any destination
/// write, and no architecture-specific dot-product path is used.
pub fn decode_q6_k_matrix(
    encoded: &[u8],
    rows: usize,
    row_width: usize,
    destination: &mut [f32],
) -> Result<(), Q6KError> {
    let row_bytes = checked_row_layout(row_width)?;
    let expected_elements = rows
        .checked_mul(row_width)
        .ok_or(Q6KError::ArithmeticOverflow)?;
    let expected_bytes = rows
        .checked_mul(row_bytes)
        .ok_or(Q6KError::ArithmeticOverflow)?;
    if encoded.len() != expected_bytes {
        return Err(Q6KError::EncodedLengthMismatch {
            expected: expected_bytes,
            actual: encoded.len(),
        });
    }
    if destination.len() != expected_elements {
        return Err(Q6KError::DestinationLengthMismatch {
            expected: expected_elements,
            actual: destination.len(),
        });
    }
    validate_scales(encoded)?;

    for (row_index, (encoded_row, output_row)) in encoded
        .chunks_exact(row_bytes)
        .zip(destination.chunks_exact_mut(row_width))
        .enumerate()
    {
        for (block_index, (block, output)) in encoded_row
            .chunks_exact(Q6_K_BLOCK_BYTES)
            .zip(output_row.chunks_exact_mut(QK_K))
            .enumerate()
        {
            decode_block(block, row_index * (row_width / QK_K) + block_index, output)?;
        }
    }
    Ok(())
}
