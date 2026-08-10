use crate::cpu_dot_tables::{IQ2XXS_GRID, IQ3XXS_GRID};

pub const IQ2_XXS_BLOCK_BYTES: usize = 66;
pub const IQ3_XXS_BLOCK_BYTES: usize = 98;
pub const IQ_XXS_VALUES_PER_BLOCK: usize = 256;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum IQXXSError {
    ZeroRowWidth,
    RowWidthNotDivisible,
    ArithmeticOverflow,
    EncodedLengthMismatch,
    DestinationLengthMismatch,
    NonFiniteScale,
    NonFiniteResult,
}

fn layout(
    encoded_len: usize,
    rows: usize,
    row_width: usize,
    block_bytes: usize,
    destination_len: usize,
) -> Result<(usize, usize), IQXXSError> {
    if row_width == 0 {
        return Err(IQXXSError::ZeroRowWidth);
    }
    if !row_width.is_multiple_of(IQ_XXS_VALUES_PER_BLOCK) {
        return Err(IQXXSError::RowWidthNotDivisible);
    }
    let blocks_per_row = row_width / IQ_XXS_VALUES_PER_BLOCK;
    let expected_encoded = rows
        .checked_mul(blocks_per_row)
        .and_then(|blocks| blocks.checked_mul(block_bytes))
        .ok_or(IQXXSError::ArithmeticOverflow)?;
    let expected_destination = rows
        .checked_mul(row_width)
        .ok_or(IQXXSError::ArithmeticOverflow)?;
    if encoded_len != expected_encoded {
        return Err(IQXXSError::EncodedLengthMismatch);
    }
    if destination_len != expected_destination {
        return Err(IQXXSError::DestinationLengthMismatch);
    }
    Ok((blocks_per_row, expected_destination))
}

#[inline]
fn sign_mask(s7: u32) -> u32 {
    s7 | (((s7.count_ones() & 1) as u32) << 7)
}

#[inline]
fn signed_grid_byte(byte: u8) -> f32 {
    (byte as i8) as f32
}

fn decode_iq2_block(block: &[u8], output: &mut [f32]) -> Result<(), IQXXSError> {
    let d = crate::f16_to_f32(u16::from_le_bytes([block[0], block[1]]));
    if !d.is_finite() {
        return Err(IQXXSError::NonFiniteScale);
    }
    for group in 0..8 {
        let base = 2 + group * 8;
        let aux0 = u32::from_le_bytes(block[base..base + 4].try_into().unwrap());
        let aux1 = u32::from_le_bytes(block[base + 4..base + 8].try_into().unwrap());
        let block_scale = 0.125_f32 * d * (2 * (aux1 >> 28) + 1) as f32;
        for k in 0..4 {
            let grid = IQ2XXS_GRID[((aux0 >> (8 * k)) & 0xff) as usize].to_le_bytes();
            let signs = sign_mask((aux1 >> (7 * k)) & 127);
            for i in 0..8 {
                let value = block_scale
                    * signed_grid_byte(grid[i])
                    * if signs & (1 << i) != 0 { -1.0 } else { 1.0 };
                if !value.is_finite() {
                    return Err(IQXXSError::NonFiniteResult);
                }
                output[group * 32 + k * 8 + i] = value;
            }
        }
    }
    Ok(())
}

pub fn decode_iq2_xxs_matrix(
    encoded: &[u8],
    rows: usize,
    row_width: usize,
    destination: &mut [f32],
) -> Result<(), IQXXSError> {
    let (blocks_per_row, output_len) = layout(
        encoded.len(),
        rows,
        row_width,
        IQ2_XXS_BLOCK_BYTES,
        destination.len(),
    )?;
    let mut decoded = vec![0.0_f32; output_len];
    for row in 0..rows {
        for block in 0..blocks_per_row {
            let block_index = row * blocks_per_row + block;
            let start = block_index * IQ2_XXS_BLOCK_BYTES;
            let output_start = row * row_width + block * IQ_XXS_VALUES_PER_BLOCK;
            decode_iq2_block(
                &encoded[start..start + IQ2_XXS_BLOCK_BYTES],
                &mut decoded[output_start..output_start + IQ_XXS_VALUES_PER_BLOCK],
            )?;
        }
    }
    destination.copy_from_slice(&decoded);
    Ok(())
}

fn decode_iq3_block(block: &[u8], output: &mut [f32]) -> Result<(), IQXXSError> {
    let d = crate::f16_to_f32(u16::from_le_bytes([block[0], block[1]]));
    if !d.is_finite() {
        return Err(IQXXSError::NonFiniteScale);
    }
    for group in 0..8 {
        let aux_start = 66 + group * 4;
        let aux = u32::from_le_bytes(block[aux_start..aux_start + 4].try_into().unwrap());
        let block_scale = d * (0.5 + (aux >> 28) as f32) * 0.5;
        for pair in 0..4 {
            let signs = sign_mask((aux >> (7 * pair)) & 127);
            let first = IQ3XXS_GRID[block[2 + group * 8 + pair * 2] as usize].to_le_bytes();
            let second = IQ3XXS_GRID[block[3 + group * 8 + pair * 2] as usize].to_le_bytes();
            let output_start = group * 32 + pair * 8;
            for i in 0..4 {
                let first_value = block_scale
                    * signed_grid_byte(first[i])
                    * if signs & (1 << i) != 0 { -1.0 } else { 1.0 };
                let second_value = block_scale
                    * signed_grid_byte(second[i])
                    * if signs & (1 << (4 + i)) != 0 {
                        -1.0
                    } else {
                        1.0
                    };
                if !first_value.is_finite() || !second_value.is_finite() {
                    return Err(IQXXSError::NonFiniteResult);
                }
                output[output_start + i] = first_value;
                output[output_start + 4 + i] = second_value;
            }
        }
    }
    Ok(())
}

pub fn decode_iq3_xxs_matrix(
    encoded: &[u8],
    rows: usize,
    row_width: usize,
    destination: &mut [f32],
) -> Result<(), IQXXSError> {
    let (blocks_per_row, output_len) = layout(
        encoded.len(),
        rows,
        row_width,
        IQ3_XXS_BLOCK_BYTES,
        destination.len(),
    )?;
    let mut decoded = vec![0.0_f32; output_len];
    for row in 0..rows {
        for block in 0..blocks_per_row {
            let block_index = row * blocks_per_row + block;
            let start = block_index * IQ3_XXS_BLOCK_BYTES;
            let output_start = row * row_width + block * IQ_XXS_VALUES_PER_BLOCK;
            decode_iq3_block(
                &encoded[start..start + IQ3_XXS_BLOCK_BYTES],
                &mut decoded[output_start..output_start + IQ_XXS_VALUES_PER_BLOCK],
            )?;
        }
    }
    destination.copy_from_slice(&decoded);
    Ok(())
}
