//! R3 -- the production decoder.
//!
//! Single precision throughout, and word-parallel rather than bit-serial: at
//! the admitted widths (4 and 8 bits) `32 % bits == 0`, so a code never
//! straddles a word and unpacking is a shift and a mask. That is exactly why
//! [`crate::spec::Bits`] admits only those two widths; the reference in
//! `crate::reference`, which implements the general bit-serial layout, is the
//! thing that checks this one.
//!
//! The arithmetic is deliberately written as a multiply and then an add, not
//! as a fused multiply-add. The frozen numerics contract's exact invariant
//! `R3 == round_to_f32(R1)` depends on there being exactly one rounding in the
//! addition, and `f32::mul_add` would remove it. Nothing here calls `mul_add`.

use crate::error::{AffineError, Result};
use crate::spec::{Bits, QuantSpec};

/// How the stored scales and biases are spelled.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ScaleDtype {
    F16,
    Bf16,
    F32,
}

impl ScaleDtype {
    pub fn size_bytes(self) -> usize {
        match self {
            Self::F16 | Self::Bf16 => 2,
            Self::F32 => 4,
        }
    }

    /// The Safetensors spelling, so a catalog dtype maps straight onto this.
    pub fn from_catalog(dtype: safetensors_catalog::Dtype) -> Option<Self> {
        match dtype {
            safetensors_catalog::Dtype::F16 => Some(Self::F16),
            safetensors_catalog::Dtype::Bf16 => Some(Self::Bf16),
            safetensors_catalog::Dtype::F32 => Some(Self::F32),
            _ => None,
        }
    }

    /// `true` when every value of this format is exactly representable in
    /// binary32 with at most 11 significand bits, which is the premise of the
    /// contract's exact invariant.
    pub fn is_half(self) -> bool {
        matches!(self, Self::F16 | Self::Bf16)
    }

    /// Convert one stored element, given as its raw little-endian bytes, to
    /// `f32`. Exact for all three formats.
    pub fn read(self, bytes: &[u8]) -> f32 {
        match self {
            Self::F16 => {
                let bits = u16::from_le_bytes([bytes[0], bytes[1]]);
                half_to_f32(bits)
            }
            Self::Bf16 => {
                let bits = u16::from_le_bytes([bytes[0], bytes[1]]);
                f32::from_bits(u32::from(bits) << 16)
            }
            Self::F32 => {
                f32::from_bits(u32::from_le_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]))
            }
        }
    }
}

/// IEEE-754 binary16 to binary32. Exact.
pub fn half_to_f32(bits: u16) -> f32 {
    let sign = u32::from(bits & 0x8000) << 16;
    let exponent = u32::from((bits >> 10) & 0x1F);
    let mantissa = u32::from(bits & 0x03FF);
    if exponent == 0x1F {
        return f32::from_bits(sign | 0x7F80_0000 | (mantissa << 13));
    }
    if exponent == 0 {
        if mantissa == 0 {
            return f32::from_bits(sign);
        }
        // A binary16 subnormal is `mantissa * 2^-24`. Shift until bit 10 is
        // set: after `shifts` shifts the value is `1.f * 2^(-14 - shifts)`,
        // so the binary32 biased exponent is `127 - 14 - shifts`.
        let mut mantissa = mantissa;
        let mut shifts = 0u32;
        while mantissa & 0x0400 == 0 {
            mantissa <<= 1;
            shifts += 1;
        }
        let mantissa = mantissa & 0x03FF;
        let biased = 113 - shifts;
        return f32::from_bits(sign | (biased << 23) | (mantissa << 13));
    }
    let biased = exponent + 127 - 15;
    f32::from_bits(sign | (biased << 23) | (mantissa << 13))
}

/// Geometry shared by the decoder entry points.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RowGeometry {
    pub rows: usize,
    pub columns: usize,
    pub packed_columns: usize,
    pub groups: usize,
}

impl RowGeometry {
    /// Derive the geometry from the packed stream and the requested rows.
    pub fn derive(spec: QuantSpec, rows: usize, columns: usize) -> Result<Self> {
        let group_size = spec.group_size.get() as usize;
        if rows == 0 || columns == 0 {
            return Err(AffineError::GeometryMismatch {
                detail: "rows and columns must both be positive".to_string(),
            });
        }
        if !columns.is_multiple_of(group_size) {
            return Err(AffineError::GeometryMismatch {
                detail: format!("{columns} columns are not a whole number of {group_size}-groups"),
            });
        }
        let codes_per_word = spec.bits.codes_per_word() as usize;
        if !columns.is_multiple_of(codes_per_word) {
            return Err(AffineError::GeometryMismatch {
                detail: format!("{columns} columns are not a whole number of packed words"),
            });
        }
        Ok(Self {
            rows,
            columns,
            packed_columns: columns / codes_per_word,
            groups: columns / group_size,
        })
    }
}

/// Unpack every code of a packed stream, one byte per code.
///
/// `out.len()` fixes the number of codes; `packed` must hold exactly
/// `out.len() / codes_per_word` words.
pub fn unpack_codes(packed: &[u32], bits: Bits, out: &mut [u8]) -> Result<()> {
    let per_word = bits.codes_per_word() as usize;
    if !out.len().is_multiple_of(per_word) {
        return Err(AffineError::GeometryMismatch {
            detail: format!("{} codes are not a whole number of packed words", out.len()),
        });
    }
    if packed.len() != out.len() / per_word {
        return Err(AffineError::GeometryMismatch {
            detail: format!(
                "{} packed words cannot hold {} codes at {} bits",
                packed.len(),
                out.len(),
                bits.get()
            ),
        });
    }
    let width = bits.get();
    let mask = bits.max_code();
    for (index, slot) in out.iter_mut().enumerate() {
        let word = packed[index / per_word];
        let shift = ((index % per_word) as u32) * width;
        *slot = ((word >> shift) & mask) as u8;
    }
    Ok(())
}

/// Dequantize `rows` rows into `out`, in row-major order.
///
/// `scales` and `biases` are the raw little-endian bytes of the stored
/// metadata in `scale_dtype`, in row-major `[rows, columns / group_size]`
/// order. `out.len()` fixes `columns`.
#[allow(clippy::too_many_arguments)]
pub fn dequantize_rows(
    module: &str,
    packed: &[u32],
    scales: &[u8],
    biases: &[u8],
    scale_dtype: ScaleDtype,
    spec: QuantSpec,
    rows: usize,
    out: &mut [f32],
) -> Result<()> {
    if rows == 0 {
        return Err(AffineError::GeometryMismatch {
            detail: "rows must be positive".to_string(),
        });
    }
    if !out.len().is_multiple_of(rows) {
        return Err(AffineError::GeometryMismatch {
            detail: format!("{} outputs do not divide into {rows} rows", out.len()),
        });
    }
    let geometry = RowGeometry::derive(spec, rows, out.len() / rows)?;
    if packed.len() != rows * geometry.packed_columns {
        return Err(AffineError::GeometryMismatch {
            detail: format!(
                "{} packed words, the geometry needs {}",
                packed.len(),
                rows * geometry.packed_columns
            ),
        });
    }
    let element = scale_dtype.size_bytes();
    let needed = rows * geometry.groups * element;
    if scales.len() != needed || biases.len() != needed {
        return Err(AffineError::GeometryMismatch {
            detail: format!(
                "{} scale bytes and {} bias bytes, the geometry needs {needed} of each",
                scales.len(),
                biases.len()
            ),
        });
    }

    let width = spec.bits.get();
    let mask = spec.bits.max_code();
    let per_word = spec.bits.codes_per_word() as usize;
    let group_size = spec.group_size.get() as usize;

    for row in 0..rows {
        let row_words = &packed[row * geometry.packed_columns..(row + 1) * geometry.packed_columns];
        for column in 0..geometry.columns {
            let word = row_words[column / per_word];
            let shift = ((column % per_word) as u32) * width;
            let code = (word >> shift) & mask;
            let group = row * geometry.groups + column / group_size;
            let at = group * element;
            let scale = scale_dtype.read(&scales[at..at + element]);
            let bias = scale_dtype.read(&biases[at..at + element]);
            // One multiply, one add, no fusion. See the module comment.
            let product = scale * (code as f32);
            let value = product + bias;
            // The qualified domain. A finite triple can still have an infinite
            // binary32 product -- scale = max finite bf16, code = 2 -- while
            // its binary64 value is finite. Returning an infinity there is an
            // answer outside the domain the contract qualifies, so it is a
            // refusal. Both the product and the result are checked, because
            // the product is where the overflow happens and the result is
            // where a NaN from an infinite operand would appear.
            if !product.is_finite() || !value.is_finite() {
                return Err(AffineError::NonFiniteValue {
                    module: module.to_string(),
                    row,
                    index: column,
                });
            }
            out[row * geometry.columns + column] = value;
        }
    }
    Ok(())
}

/// Reinterpret a little-endian byte slice as `u32` words.
pub fn words_from_bytes(bytes: &[u8]) -> Result<Vec<u32>> {
    if !bytes.len().is_multiple_of(4) {
        return Err(AffineError::GeometryMismatch {
            detail: format!("{} bytes are not a whole number of u32 words", bytes.len()),
        });
    }
    Ok(bytes
        .chunks_exact(4)
        .map(|chunk| u32::from_le_bytes([chunk[0], chunk[1], chunk[2], chunk[3]]))
        .collect())
}

#[cfg(test)]
mod tests {
    use super::{dequantize_rows, half_to_f32, unpack_codes, words_from_bytes, ScaleDtype};
    use crate::error::AffineError;
    use crate::spec::{Bits, GroupSize, Mode, QuantSpec};

    fn spec(bits: u32, group: u32) -> QuantSpec {
        QuantSpec::new(
            Bits::from_u32(bits).unwrap(),
            GroupSize::from_u32(group).unwrap(),
            Mode::Affine,
        )
    }

    #[test]
    fn codes_are_least_significant_bits_first() {
        // 0x76543210: code 0 is 0, code 1 is 1, ... code 7 is 7.
        let mut out = [0u8; 8];
        unpack_codes(&[0x7654_3210], Bits::Four, &mut out).unwrap();
        assert_eq!(out, [0, 1, 2, 3, 4, 5, 6, 7]);

        let mut wide = [0u8; 4];
        unpack_codes(&[0xDDCC_BBAA], Bits::Eight, &mut wide).unwrap();
        assert_eq!(wide, [0xAA, 0xBB, 0xCC, 0xDD]);
    }

    #[test]
    fn unpacking_refuses_a_mismatched_stream() {
        let mut out = [0u8; 8];
        assert!(matches!(
            unpack_codes(&[0, 0], Bits::Four, &mut out),
            Err(AffineError::GeometryMismatch { .. })
        ));
        let mut ragged = [0u8; 3];
        assert!(matches!(
            unpack_codes(&[0], Bits::Four, &mut ragged),
            Err(AffineError::GeometryMismatch { .. })
        ));
    }

    #[test]
    fn half_conversions_are_exact() {
        assert_eq!(half_to_f32(0x3C00), 1.0);
        assert_eq!(half_to_f32(0xC000), -2.0);
        assert_eq!(half_to_f32(0x0000), 0.0);
        assert_eq!(half_to_f32(0x8000), -0.0);
        // The smallest binary16 subnormal is 2^-24.
        assert_eq!(half_to_f32(0x0001), 2.0f32.powi(-24));
        assert_eq!(half_to_f32(0x03FF), 1023.0 * 2.0f32.powi(-24));
        assert_eq!(half_to_f32(0x0400), 2.0f32.powi(-14));
        assert!(half_to_f32(0x7C00).is_infinite());
        assert!(half_to_f32(0x7E00).is_nan());

        assert_eq!(ScaleDtype::Bf16.read(&[0x80, 0x3F]), 1.0);
        assert_eq!(ScaleDtype::F16.read(&[0x00, 0x3C]), 1.0);
        assert_eq!(ScaleDtype::F32.read(&[0x00, 0x00, 0x80, 0x3F]), 1.0);
        assert_eq!(ScaleDtype::Bf16.size_bytes(), 2);
        assert_eq!(ScaleDtype::F32.size_bytes(), 4);
        assert!(ScaleDtype::Bf16.is_half());
        assert!(!ScaleDtype::F32.is_half());
    }

    #[test]
    fn one_group_decodes_to_scale_times_code_plus_bias() {
        // One row, 32 columns, 4 bits, group 32: scale 0.5, bias -1.0 in bf16.
        let codes: Vec<u8> = (0..32).map(|index| (index % 16) as u8).collect();
        let mut words = vec![0u32; 4];
        for (index, code) in codes.iter().enumerate() {
            words[index / 8] |= u32::from(*code) << ((index % 8) * 4);
        }
        let scale = 0.5f32.to_bits() >> 16;
        let bias = (-1.0f32).to_bits() >> 16;
        let scales = (scale as u16).to_le_bytes().to_vec();
        let biases = (bias as u16).to_le_bytes().to_vec();
        let mut out = vec![0f32; 32];
        dequantize_rows(
            "test",
            &words,
            &scales,
            &biases,
            ScaleDtype::Bf16,
            spec(4, 32),
            1,
            &mut out,
        )
        .unwrap();
        for (index, value) in out.iter().enumerate() {
            assert_eq!(*value, 0.5 * (codes[index] as f32) - 1.0);
        }
    }

    #[test]
    fn a_negative_scale_is_decoded_not_assumed_away() {
        // MLX's encoder writes signed scales; a decoder must carry the sign.
        let words = vec![0x0000_000Fu32; 8];
        let scale = (-0.25f32).to_bits() >> 16;
        let bias = 2.0f32.to_bits() >> 16;
        let scales = (scale as u16).to_le_bytes().to_vec();
        let biases = (bias as u16).to_le_bytes().to_vec();
        let mut out = vec![0f32; 64];
        dequantize_rows(
            "test",
            &words,
            &scales,
            &biases,
            ScaleDtype::Bf16,
            spec(4, 64),
            1,
            &mut out,
        )
        .unwrap();
        assert_eq!(out[0], -0.25 * 15.0 + 2.0);
        assert_eq!(out[1], 2.0);
    }

    #[test]
    fn geometry_mismatches_are_refused() {
        let words = vec![0u32; 8];
        let metadata = vec![0u8; 2];
        let mut out = vec![0f32; 64];
        assert!(matches!(
            dequantize_rows(
                "test",
                &words,
                &metadata,
                &metadata,
                ScaleDtype::Bf16,
                spec(4, 64),
                0,
                &mut out
            ),
            Err(AffineError::GeometryMismatch { .. })
        ));
        let mut ragged = vec![0f32; 63];
        assert!(matches!(
            dequantize_rows(
                "test",
                &words,
                &metadata,
                &metadata,
                ScaleDtype::Bf16,
                spec(4, 64),
                1,
                &mut ragged
            ),
            Err(AffineError::GeometryMismatch { .. })
        ));
        let short = vec![0u32; 7];
        assert!(matches!(
            dequantize_rows(
                "test",
                &short,
                &metadata,
                &metadata,
                ScaleDtype::Bf16,
                spec(4, 64),
                1,
                &mut out
            ),
            Err(AffineError::GeometryMismatch { .. })
        ));
        let wrong = vec![0u8; 4];
        assert!(matches!(
            dequantize_rows(
                "test",
                &words,
                &wrong,
                &metadata,
                ScaleDtype::Bf16,
                spec(4, 64),
                1,
                &mut out
            ),
            Err(AffineError::GeometryMismatch { .. })
        ));
    }

    #[test]
    fn words_come_off_disk_little_endian() {
        assert_eq!(
            words_from_bytes(&[1, 0, 0, 0, 2, 0, 0, 0]).unwrap(),
            vec![1, 2]
        );
        assert!(matches!(
            words_from_bytes(&[1, 2, 3]),
            Err(AffineError::GeometryMismatch { .. })
        ));
    }
}
