use sha2::{Digest, Sha256};

pub const IQ2_XXS_BLOCK_WEIGHTS: usize = 256;
pub const IQ2_XXS_BLOCK_BYTES: usize = 66;
pub const IQ2_XXS_GRID_BYTES: usize = 256 * 8;
pub const IQ2_XXS_SIGN_BYTES: usize = 128;

/// Validated packed-IQ2_XXS matrix-vector request.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Iq2XxsGemvSpec {
    rows: usize,
    columns: usize,
    packed_row_bytes: usize,
    packed_matrix_bytes: usize,
}

impl Iq2XxsGemvSpec {
    pub fn new(
        rows: usize,
        columns: usize,
        packed_len: usize,
        activation_len: usize,
    ) -> Result<Self, String> {
        if rows == 0 || columns == 0 {
            return Err("IQ2_XXS rows and columns must be positive".into());
        }
        if columns % IQ2_XXS_BLOCK_WEIGHTS != 0 {
            return Err("IQ2_XXS columns must be divisible by 256".into());
        }
        if activation_len != columns {
            return Err(format!(
                "IQ2_XXS activation length mismatch: {activation_len} != {columns}"
            ));
        }
        let packed_row_bytes = (columns / IQ2_XXS_BLOCK_WEIGHTS)
            .checked_mul(IQ2_XXS_BLOCK_BYTES)
            .ok_or_else(|| "IQ2_XXS packed row size overflow".to_owned())?;
        let packed_matrix_bytes = rows
            .checked_mul(packed_row_bytes)
            .ok_or_else(|| "IQ2_XXS packed matrix size overflow".to_owned())?;
        if packed_len != packed_matrix_bytes {
            return Err(format!(
                "IQ2_XXS packed length mismatch: {packed_len} != {packed_matrix_bytes}"
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

pub fn iq2_xxs_grid_bytes() -> Vec<u8> {
    quant::cpu_dot_tables::IQ2XXS_GRID
        .iter()
        .flat_map(|value| value.to_le_bytes())
        .collect()
}

pub fn iq2_xxs_sign_bytes() -> [u8; IQ2_XXS_SIGN_BYTES] {
    std::array::from_fn(|index| {
        let seven = index as u8;
        seven | (((seven.count_ones() & 1) as u8) << 7)
    })
}

pub fn iq2_xxs_lookup_sha256() -> (String, String) {
    fn hash(bytes: &[u8]) -> String {
        Sha256::digest(bytes)
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect()
    }
    (hash(&iq2_xxs_grid_bytes()), hash(&iq2_xxs_sign_bytes()))
}

/// Exact-decoder CPU reference for the packed matrix-vector boundary.
///
/// Full f32 materialization is intentionally restricted to this oracle. The
/// direct Metal candidate records zero materialized weight bytes.
pub fn iq2_xxs_gemv_reference(
    packed: &[u8],
    spec: Iq2XxsGemvSpec,
    activation: &[f32],
) -> Result<Vec<f32>, String> {
    if packed.len() != spec.packed_matrix_bytes() || activation.len() != spec.columns() {
        return Err("IQ2_XXS reference input length changed after validation".into());
    }
    if !activation.iter().all(|value| value.is_finite()) {
        return Err("IQ2_XXS activation must be finite".into());
    }
    let decoded_len = spec
        .rows()
        .checked_mul(spec.columns())
        .ok_or_else(|| "IQ2_XXS reference destination overflow".to_owned())?;
    let mut decoded = vec![0.0_f32; decoded_len];
    quant::decode_iq2_xxs_matrix(packed, spec.rows(), spec.columns(), &mut decoded)
        .map_err(|error| format!("IQ2_XXS reference decode failed: {error:?}"))?;
    let mut output = Vec::with_capacity(spec.rows());
    for row in decoded.chunks_exact(spec.columns()) {
        let mut sum = 0.0_f32;
        for (&weight, &value) in row.iter().zip(activation) {
            sum += weight * value;
        }
        if !sum.is_finite() {
            return Err("IQ2_XXS reference produced a non-finite result".into());
        }
        output.push(sum);
    }
    Ok(output)
}

/// Deterministic packed matrix used by checkpoint-free native tests.
pub fn synthetic_iq2_xxs_matrix(rows: usize, columns: usize) -> Result<Vec<u8>, String> {
    let row_bytes = (columns / IQ2_XXS_BLOCK_WEIGHTS)
        .checked_mul(IQ2_XXS_BLOCK_BYTES)
        .ok_or_else(|| "synthetic IQ2_XXS row overflow".to_owned())?;
    let len = rows
        .checked_mul(row_bytes)
        .ok_or_else(|| "synthetic IQ2_XXS matrix overflow".to_owned())?;
    let spec = Iq2XxsGemvSpec::new(rows, columns, len, columns)?;
    let mut packed = vec![0_u8; spec.packed_matrix_bytes()];
    for (block_index, block) in packed.chunks_exact_mut(IQ2_XXS_BLOCK_BYTES).enumerate() {
        block[..2].copy_from_slice(&0x3c00_u16.to_le_bytes());
        for group in 0..8 {
            let base = 2 + group * 8;
            for lane in 0..4 {
                block[base + lane] = ((block_index + group + lane) % 256) as u8;
            }
            let aux1 = (((block_index + group) % 16) as u32) << 28
                | 0x01
                | (0x02 << 7)
                | (0x04 << 14)
                | (0x08 << 21);
            block[base + 4..base + 8].copy_from_slice(&aux1.to_le_bytes());
        }
    }
    Ok(packed)
}
