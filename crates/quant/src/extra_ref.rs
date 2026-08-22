//! Strict portable decoders for the four sparse GLM-5.2 formats not used by
//! the representative layer-3 package. The complete 1,809-tensor execution
//! plan requires them and deliberately provides no fallback.

use std::fmt;

const QK_K: usize = 256;
const Q2_K_BYTES: usize = 84;
const Q3_K_BYTES: usize = 110;
const IQ2_S_BYTES: usize = 82;
const IQ4_XS_BYTES: usize = 136;
const KVALUES_IQ4NL: [i8; 16] = [
    -127, -104, -83, -65, -49, -35, -22, -10, 1, 13, 25, 38, 53, 69, 89, 113,
];

include!(concat!(env!("OUT_DIR"), "/f017_iq2s_grid.rs"));

#[derive(Debug, Clone, Eq, PartialEq)]
pub enum ExtraQuantError {
    Shape,
    EncodedLength { expected: usize, actual: usize },
    DestinationLength { expected: usize, actual: usize },
    NonFinite { block: usize },
}

impl fmt::Display for ExtraQuantError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{self:?}")
    }
}
impl std::error::Error for ExtraQuantError {}

fn validate<'a>(
    encoded: &'a [u8],
    rows: usize,
    columns: usize,
    block_bytes: usize,
    out: &mut [f32],
) -> Result<std::slice::ChunksExact<'a, u8>, ExtraQuantError> {
    if rows == 0 || columns == 0 || columns % QK_K != 0 {
        return Err(ExtraQuantError::Shape);
    }
    let expected = rows
        .checked_mul(columns / QK_K)
        .and_then(|v| v.checked_mul(block_bytes))
        .ok_or(ExtraQuantError::Shape)?;
    if encoded.len() != expected {
        return Err(ExtraQuantError::EncodedLength {
            expected,
            actual: encoded.len(),
        });
    }
    let values = rows.checked_mul(columns).ok_or(ExtraQuantError::Shape)?;
    if out.len() != values {
        return Err(ExtraQuantError::DestinationLength {
            expected: values,
            actual: out.len(),
        });
    }
    Ok(encoded.chunks_exact(block_bytes))
}

fn f16(bytes: &[u8]) -> f32 {
    crate::f16_to_f32(u16::from_le_bytes([bytes[0], bytes[1]]))
}

pub fn decode_q2_k_matrix(
    encoded: &[u8],
    rows: usize,
    columns: usize,
    out: &mut [f32],
) -> Result<(), ExtraQuantError> {
    let blocks = validate(encoded, rows, columns, Q2_K_BYTES, out)?;
    for (bi, block) in blocks.enumerate() {
        let (scales, qs) = (&block[..16], &block[16..80]);
        let (d, dmin) = (f16(&block[80..82]), f16(&block[82..84]));
        let base = bi * QK_K;
        for nn in 0..2 {
            for j in 0..32 {
                let byte = qs[32 * nn + j];
                for s in 0..4 {
                    let index = 128 * nn + 32 * s + j;
                    let scale = scales[index / 16];
                    out[base + index] =
                        d * f32::from(scale & 15) * f32::from((byte >> (2 * s)) & 3)
                            - dmin * f32::from(scale >> 4);
                }
            }
        }
        if out[base..base + QK_K].iter().any(|v| !v.is_finite()) {
            return Err(ExtraQuantError::NonFinite { block: bi });
        }
    }
    Ok(())
}

fn q3_scales(bytes: &[u8]) -> [i8; 16] {
    let mut out = [0_i8; 16];
    for j in 0..16 {
        let lo = if j < 8 {
            bytes[j] & 15
        } else {
            bytes[j - 8] >> 4
        };
        let hi = (bytes[8 + j % 4] >> (2 * (j / 4))) & 3;
        out[j] = (lo | (hi << 4)) as i8 - 32;
    }
    out
}

pub fn decode_q3_k_matrix(
    encoded: &[u8],
    rows: usize,
    columns: usize,
    out: &mut [f32],
) -> Result<(), ExtraQuantError> {
    let blocks = validate(encoded, rows, columns, Q3_K_BYTES, out)?;
    for (bi, block) in blocks.enumerate() {
        let (hmask, qs) = (&block[..32], &block[32..96]);
        let scales = q3_scales(&block[96..108]);
        let d = f16(&block[108..110]);
        let base = bi * QK_K;
        for nn in 0..2 {
            for j in 0..32 {
                let byte = qs[32 * nn + j];
                for s in 0..4 {
                    let index = 128 * nn + 32 * s + j;
                    let mut q = ((byte >> (2 * s)) & 3) as i8;
                    if hmask[j] & (1 << (4 * nn + s)) == 0 {
                        q -= 4;
                    }
                    out[base + index] = d * f32::from(scales[index / 16]) * f32::from(q);
                }
            }
        }
        if out[base..base + QK_K].iter().any(|v| !v.is_finite()) {
            return Err(ExtraQuantError::NonFinite { block: bi });
        }
    }
    Ok(())
}

pub fn decode_iq2_s_matrix(
    encoded: &[u8],
    rows: usize,
    columns: usize,
    out: &mut [f32],
) -> Result<(), ExtraQuantError> {
    let blocks = validate(encoded, rows, columns, IQ2_S_BYTES, out)?;
    for (bi, block) in blocks.enumerate() {
        let d = f16(&block[..2]);
        let (qs, qh, scales) = (&block[2..66], &block[66..74], &block[74..82]);
        let mut at = bi * QK_K;
        for g in 0..8 {
            for h in 0..2 {
                let nibble = if h == 0 {
                    scales[g] & 15
                } else {
                    scales[g] >> 4
                };
                let scale = 0.125 * d * f32::from(2 * nibble + 1);
                for k in 0..2 {
                    let j = h * 2 + k;
                    let index =
                        usize::from(qs[g * 4 + j]) | ((usize::from(qh[g]) << (8 - 2 * j)) & 0x300);
                    let grid = IQ2S_GRID[index].to_le_bytes();
                    let signs = qs[32 + g * 4 + j];
                    for (bit, magnitude) in grid.iter().enumerate() {
                        out[at] = scale
                            * if signs & (1 << bit) == 0 {
                                f32::from(*magnitude)
                            } else {
                                -f32::from(*magnitude)
                            };
                        at += 1;
                    }
                }
            }
        }
        if out[bi * QK_K..(bi + 1) * QK_K]
            .iter()
            .any(|v| !v.is_finite())
        {
            return Err(ExtraQuantError::NonFinite { block: bi });
        }
    }
    Ok(())
}

pub fn decode_iq4_xs_matrix(
    encoded: &[u8],
    rows: usize,
    columns: usize,
    out: &mut [f32],
) -> Result<(), ExtraQuantError> {
    let blocks = validate(encoded, rows, columns, IQ4_XS_BYTES, out)?;
    for (bi, block) in blocks.enumerate() {
        let d = f16(&block[..2]);
        let scales_h = u16::from_le_bytes([block[2], block[3]]);
        let (scales_l, qs) = (&block[4..8], &block[8..136]);
        let mut at = bi * QK_K;
        for group in 0..8 {
            let low = (scales_l[group / 2] >> (4 * (group & 1))) & 15;
            let high = ((scales_h >> (2 * group)) & 3) as u8;
            let scale = d * f32::from((low | (high << 4)) as i8 - 32);
            for byte in &qs[group * 16..group * 16 + 16] {
                out[at] = scale * f32::from(KVALUES_IQ4NL[usize::from(byte & 15)]);
                at += 1;
                out[at] = scale * f32::from(KVALUES_IQ4NL[usize::from(byte >> 4)]);
                at += 1;
            }
        }
        if out[bi * QK_K..(bi + 1) * QK_K]
            .iter()
            .any(|v| !v.is_finite())
        {
            return Err(ExtraQuantError::NonFinite { block: bi });
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn four_formats_reject_truncation_and_decode_zero_blocks() {
        let cases: [(
            usize,
            fn(&[u8], usize, usize, &mut [f32]) -> Result<(), ExtraQuantError>,
        ); 4] = [
            (Q2_K_BYTES, decode_q2_k_matrix),
            (Q3_K_BYTES, decode_q3_k_matrix),
            (IQ2_S_BYTES, decode_iq2_s_matrix),
            (IQ4_XS_BYTES, decode_iq4_xs_matrix),
        ];
        for (bytes, decoder) in cases {
            let mut out = vec![1.0; QK_K];
            decoder(&vec![0; bytes], 1, QK_K, &mut out).unwrap();
            assert!(out.iter().all(|v| *v == 0.0));
            assert!(decoder(&vec![0; bytes - 1], 1, QK_K, &mut out).is_err());
        }
    }
}
