use sha2::{Digest, Sha256};

pub const IQ3_XXS_BLOCK_WEIGHTS: usize = 256;
pub const IQ3_XXS_BLOCK_BYTES: usize = 98;
pub const IQ3_XXS_GRID_BYTES: usize = 256 * 4;
pub const IQ3_XXS_SIGN_BYTES: usize = 128;

/// Validated packed-IQ3_XXS routed-down matrix-vector request.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Iq3XxsGemvSpec {
    rows: usize,
    columns: usize,
    packed_row_bytes: usize,
    packed_matrix_bytes: usize,
}

impl Iq3XxsGemvSpec {
    pub fn new(
        rows: usize,
        columns: usize,
        packed_len: usize,
        activation_len: usize,
    ) -> Result<Self, String> {
        if rows == 0 || columns == 0 {
            return Err("IQ3_XXS rows and columns must be positive".into());
        }
        if !columns.is_multiple_of(IQ3_XXS_BLOCK_WEIGHTS) {
            return Err("IQ3_XXS columns must be divisible by 256".into());
        }
        if activation_len != columns {
            return Err(format!(
                "IQ3_XXS activation length mismatch: {activation_len} != {columns}"
            ));
        }
        let packed_row_bytes = (columns / IQ3_XXS_BLOCK_WEIGHTS)
            .checked_mul(IQ3_XXS_BLOCK_BYTES)
            .ok_or_else(|| "IQ3_XXS packed row size overflow".to_owned())?;
        let packed_matrix_bytes = rows
            .checked_mul(packed_row_bytes)
            .ok_or_else(|| "IQ3_XXS packed matrix size overflow".to_owned())?;
        if packed_len != packed_matrix_bytes {
            return Err(format!(
                "IQ3_XXS packed length mismatch: {packed_len} != {packed_matrix_bytes}"
            ));
        }
        Ok(Self {
            rows,
            columns,
            packed_row_bytes,
            packed_matrix_bytes,
        })
    }

    pub fn rows(self) -> usize {
        self.rows
    }

    pub fn columns(self) -> usize {
        self.columns
    }

    pub fn packed_row_bytes(self) -> usize {
        self.packed_row_bytes
    }

    pub fn packed_matrix_bytes(self) -> usize {
        self.packed_matrix_bytes
    }

    pub fn complete_f32_weight_materialized_bytes(self) -> usize {
        0
    }
}

pub fn iq3_xxs_grid_bytes() -> Vec<u8> {
    quant::cpu_dot_tables::IQ3XXS_GRID
        .iter()
        .flat_map(|value| value.to_le_bytes())
        .collect()
}

pub fn iq3_xxs_sign_bytes() -> [u8; IQ3_XXS_SIGN_BYTES] {
    std::array::from_fn(|index| {
        let seven = index as u8;
        seven | (((seven.count_ones() & 1) as u8) << 7)
    })
}

pub fn iq3_xxs_lookup_sha256() -> (String, String) {
    fn hash(bytes: &[u8]) -> String {
        Sha256::digest(bytes)
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect()
    }
    (hash(&iq3_xxs_grid_bytes()), hash(&iq3_xxs_sign_bytes()))
}

/// Same-order f32 CPU oracle for one packed IQ3_XXS matrix-vector operation.
///
/// Complete f32 materialization is restricted to this reference and is never
/// part of a successful direct Metal result.
pub fn iq3_xxs_gemv_reference(
    packed: &[u8],
    spec: Iq3XxsGemvSpec,
    activation: &[f32],
) -> Result<Vec<f32>, String> {
    if packed.len() != spec.packed_matrix_bytes() || activation.len() != spec.columns() {
        return Err("IQ3_XXS reference input length changed after validation".into());
    }
    if !activation.iter().all(|value| value.is_finite()) {
        return Err("IQ3_XXS activation must be finite".into());
    }
    let grid = iq3_xxs_grid_bytes();
    let signs = iq3_xxs_sign_bytes();
    let blocks_per_row = spec.columns() / IQ3_XXS_BLOCK_WEIGHTS;
    let mut output = Vec::with_capacity(spec.rows());
    let mut row_values = vec![0.0_f32; spec.columns()];
    for row_index in 0..spec.rows() {
        for block_index in 0..blocks_per_row {
            let block_start =
                row_index * spec.packed_row_bytes() + block_index * IQ3_XXS_BLOCK_BYTES;
            let block = &packed[block_start..block_start + IQ3_XXS_BLOCK_BYTES];
            let d = quant::f16_to_f32(u16::from_le_bytes([block[0], block[1]]));
            if !d.is_finite() {
                return Err("IQ3_XXS reference scale must be finite".into());
            }
            for group in 0..8 {
                let aux_start = 66 + group * 4;
                let aux = u32::from_le_bytes(
                    block[aux_start..aux_start + 4]
                        .try_into()
                        .expect("four-byte IQ3 aux word"),
                );
                let scale = f64::from(d) * (0.5 + f64::from(aux >> 28)) * 0.5;
                for pair in 0..4 {
                    let sign_mask = signs[((aux >> (7 * pair)) & 127) as usize];
                    let first_index = block[2 + group * 8 + pair * 2] as usize;
                    let second_index = block[3 + group * 8 + pair * 2] as usize;
                    for element in 0..4 {
                        let first_sign = if sign_mask & (1 << element) != 0 {
                            -1.0
                        } else {
                            1.0
                        };
                        let second_sign = if sign_mask & (1 << (4 + element)) != 0 {
                            -1.0
                        } else {
                            1.0
                        };
                        let logical = block_index * 256 + group * 32 + pair * 8 + element * 2;
                        row_values[logical] = (scale
                            * f64::from(grid[first_index * 4 + element])
                            * first_sign) as f32;
                        row_values[logical + 1] = (scale
                            * f64::from(grid[second_index * 4 + element])
                            * second_sign) as f32;
                    }
                }
            }
        }
        let mut sum = 0.0_f32;
        for (&weight, &value) in row_values.iter().zip(activation) {
            sum += weight * value;
        }
        if !sum.is_finite() {
            return Err("IQ3_XXS reference produced a non-finite result".into());
        }
        output.push(sum);
    }
    Ok(output)
}

/// Deterministic packed matrix covering scale nibbles, grid indices, and sign
/// patterns for checkpoint-free native qualification.
pub fn synthetic_iq3_xxs_matrix(rows: usize, columns: usize) -> Result<Vec<u8>, String> {
    let row_bytes = (columns / IQ3_XXS_BLOCK_WEIGHTS)
        .checked_mul(IQ3_XXS_BLOCK_BYTES)
        .ok_or_else(|| "synthetic IQ3_XXS row overflow".to_owned())?;
    let len = rows
        .checked_mul(row_bytes)
        .ok_or_else(|| "synthetic IQ3_XXS matrix overflow".to_owned())?;
    let spec = Iq3XxsGemvSpec::new(rows, columns, len, columns)?;
    let mut packed = vec![0_u8; spec.packed_matrix_bytes()];
    for (block_index, block) in packed.chunks_exact_mut(IQ3_XXS_BLOCK_BYTES).enumerate() {
        block[..2].copy_from_slice(&0x3c00_u16.to_le_bytes());
        for (index, byte) in block[2..66].iter_mut().enumerate() {
            *byte = ((block_index * 17 + index * 13) % 256) as u8;
        }
        for group in 0..8 {
            let aux = (((block_index + group) % 16) as u32) << 28
                | 0x01
                | (0x02 << 7)
                | (0x04 << 14)
                | (0x08 << 21);
            let start = 66 + group * 4;
            block[start..start + 4].copy_from_slice(&aux.to_le_bytes());
        }
    }
    Ok(packed)
}
