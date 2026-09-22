//! R1 -- an independent reference implementation of the MLX affine
//! representation, in binary64.
//!
//! # Independence
//!
//! This module is written from the written format specification alone and
//! shares nothing with the production decoder in `crate::decode`: not a type,
//! not a helper, not a constant. It has **no `use` statements at all** and
//! names neither `crate::` nor `super::`; `tests/independence.rs` reads this
//! file and asserts exactly that, so the claim is checked rather than
//! promised. Its types are the minimum the format needs -- `&[u32]` for the
//! packed stream, `&[u16]` for stored half-precision metadata bit patterns,
//! `&[u32]` for stored binary32 bit patterns, `&mut [f64]` for the result.
//!
//! It also admits every bit width the format defines, including 2, 3, 5 and 6,
//! which `crate::spec::Bits` refuses. That is deliberate: the reference must
//! be able to check a case the production path declines to decode, and the
//! bit-serial extraction below handles codes that straddle a word boundary by
//! construction rather than by a special case.
//!
//! # The specification it implements
//!
//! *  Packing. "is packed in an unsigned 32-bit integer from the lower to
//!    upper bits. For instance, for 4-bit quantization we fit 8 elements in an
//!    unsigned 32 bit integer where the 1st element occupies the 4 least
//!    significant bits, the 2nd bits 4-7 etc." (MLX `python/src/ops.cpp`
//!    docstring; quoted in the F020 Phase 0 inventory W2 section 4, which also
//!    cites the extraction in `mlx/ops.cpp:5001-5010`.) Code `j` of a row
//!    therefore occupies bits `[j*bits, j*bits + bits)` of that row's
//!    contiguous little-endian `u32` bit stream.
//!
//! *  Grouping. A group is `group_size` consecutive elements along the last
//!    axis; `scales` and `biases` have the weight's shape with the last axis
//!    replaced by `in_features / group_size` (`mlx/ops.cpp:107-113`).
//!
//! *  Dequantization. `w_i = scale_g * q_i + bias_g` with `g = i / group_size`
//!    (`mlx/ops.cpp:5028-5029`). The scale may be negative and the bias may be
//!    a group edge rather than the minimum, because the implemented encoder is
//!    not the documented one (`mlx/ops.cpp:4764-4778`); a decoder is unaffected
//!    as long as it does not assume a positive scale, and this one does not.
//!
//! All arithmetic below is `f64`.

/// How stored metadata is spelled on disk.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MetadataFormat {
    /// IEEE-754 binary16.
    Half,
    /// bfloat16, the leading 16 bits of binary32.
    BrainHalf,
    /// IEEE-754 binary32.
    Single,
}

/// Why a reference call was refused.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ReferenceError {
    BitWidth(u32),
    GroupSize(u32),
    Geometry(&'static str),
    Truncated,
    /// An index computation left the range of `usize`. `extract_code` is
    /// public, so its index is caller-supplied and must be checked: at 4 bits
    /// an index of `2^62` wraps on a 64-bit release build and silently returns
    /// the first code instead of refusing.
    IndexOverflow,
}

impl core::fmt::Display for ReferenceError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::BitWidth(bits) => write!(f, "bit width {bits} is outside 1..=8"),
            Self::GroupSize(size) => write!(f, "group size {size} is not 32, 64 or 128"),
            Self::Geometry(detail) => write!(f, "geometry: {detail}"),
            Self::Truncated => f.write_str("a bit position lies beyond the packed stream"),
            Self::IndexOverflow => f.write_str("an index computation overflowed"),
        }
    }
}

impl std::error::Error for ReferenceError {}

/// Widen a bfloat16 bit pattern to binary64. Exact: bfloat16 is the leading
/// 16 bits of binary32, so the widening is a shift and a reinterpretation.
pub fn brain_half_to_f64(bits: u16) -> f64 {
    f64::from(f32::from_bits((bits as u32) << 16))
}

/// Widen an IEEE-754 binary16 bit pattern to binary64. Exact: every binary16
/// value is a binary64 value. Decoded by hand so that this file depends on
/// nothing, not even a conversion intrinsic.
pub fn half_to_f64(bits: u16) -> f64 {
    let sign = if bits & 0x8000 != 0 { -1.0f64 } else { 1.0f64 };
    let exponent = ((bits >> 10) & 0x1F) as i32;
    let mantissa = (bits & 0x03FF) as u64;
    if exponent == 0x1F {
        return if mantissa == 0 {
            sign * f64::INFINITY
        } else {
            f64::NAN
        };
    }
    if exponent == 0 {
        // Subnormal: value = mantissa * 2^-24.
        let scaled = mantissa as f64;
        return sign * scaled * (2.0f64).powi(-24);
    }
    let significand = 1.0f64 + (mantissa as f64) / 1024.0;
    sign * significand * (2.0f64).powi(exponent - 15)
}

/// Widen an IEEE-754 binary32 bit pattern to binary64. Exact.
pub fn single_to_f64(bits: u32) -> f64 {
    f64::from(f32::from_bits(bits))
}

/// Round a binary64 to the nearest binary32 and widen it back, so that an
/// exact-invariant comparison can be written in one precision.
pub fn round_to_f32(value: f64) -> f64 {
    f64::from(value as f32)
}

/// Extract code `index` from a contiguous little-endian `u32` bit stream.
///
/// Bit-serial on purpose: bit `k` of the stream is bit `k % 32` of word
/// `k / 32`, so a code that crosses a word boundary needs no special case.
pub fn extract_code(words: &[u32], bits: u32, index: usize) -> Result<u32, ReferenceError> {
    if bits == 0 || bits > 8 {
        return Err(ReferenceError::BitWidth(bits));
    }
    let mut value: u32 = 0;
    // Checked: `index * bits + offset` is computed from a caller-supplied
    // index and wraps rather than refuses if left alone.
    let base = index
        .checked_mul(bits as usize)
        .ok_or(ReferenceError::IndexOverflow)?;
    for offset in 0..bits {
        let position = base
            .checked_add(offset as usize)
            .ok_or(ReferenceError::IndexOverflow)?;
        let word = position / 32;
        if word >= words.len() {
            return Err(ReferenceError::Truncated);
        }
        let bit = (words[word] >> (position % 32)) & 1;
        value |= bit << offset;
    }
    Ok(value)
}

fn check_geometry(
    bits: u32,
    group_size: u32,
    rows: usize,
    columns: usize,
    words: usize,
    metadata: usize,
) -> Result<(usize, usize), ReferenceError> {
    if bits == 0 || bits > 8 {
        return Err(ReferenceError::BitWidth(bits));
    }
    if group_size != 32 && group_size != 64 && group_size != 128 {
        return Err(ReferenceError::GroupSize(group_size));
    }
    if columns == 0 || !columns.is_multiple_of(group_size as usize) {
        return Err(ReferenceError::Geometry(
            "columns are not a whole number of groups",
        ));
    }
    if !(columns * (bits as usize)).is_multiple_of(32) {
        return Err(ReferenceError::Geometry(
            "a row is not a whole number of packed words",
        ));
    }
    let packed_columns = columns * (bits as usize) / 32;
    let groups = columns / (group_size as usize);
    // The MLX shape invariant, restated: packed_columns * 32 / bits == groups * group_size.
    if packed_columns * 32 != groups * (group_size as usize) * (bits as usize) {
        return Err(ReferenceError::Geometry(
            "the MLX shape invariant does not hold",
        ));
    }
    if words != rows * packed_columns {
        return Err(ReferenceError::Geometry(
            "packed stream length does not match the geometry",
        ));
    }
    if metadata != rows * groups {
        return Err(ReferenceError::Geometry(
            "metadata length does not match the geometry",
        ));
    }
    Ok((packed_columns, groups))
}

/// Dequantize `rows` rows of `columns` elements from half-precision metadata.
///
/// `scale_bits` and `bias_bits` are the stored 16-bit patterns in row-major
/// `[rows, columns / group_size]` order. `out` receives `rows * columns`
/// binary64 values in row-major order.
#[allow(clippy::too_many_arguments)]
pub fn dequantize_rows_half(
    words: &[u32],
    scale_bits: &[u16],
    bias_bits: &[u16],
    format: MetadataFormat,
    bits: u32,
    group_size: u32,
    rows: usize,
    columns: usize,
    out: &mut [f64],
) -> Result<(), ReferenceError> {
    if scale_bits.len() != bias_bits.len() {
        return Err(ReferenceError::Geometry(
            "scales and biases differ in length",
        ));
    }
    let (packed_columns, groups) = check_geometry(
        bits,
        group_size,
        rows,
        columns,
        words.len(),
        scale_bits.len(),
    )?;
    if out.len() != rows * columns {
        return Err(ReferenceError::Geometry(
            "output length does not match the geometry",
        ));
    }
    let widen: fn(u16) -> f64 = match format {
        MetadataFormat::Half => half_to_f64,
        MetadataFormat::BrainHalf => brain_half_to_f64,
        MetadataFormat::Single => {
            return Err(ReferenceError::Geometry(
                "binary32 metadata needs dequantize_rows_single",
            ))
        }
    };
    for row in 0..rows {
        let row_words = &words[row * packed_columns..(row + 1) * packed_columns];
        for column in 0..columns {
            let code = extract_code(row_words, bits, column)?;
            let group = row * groups + column / (group_size as usize);
            let scale = widen(scale_bits[group]);
            let bias = widen(bias_bits[group]);
            out[row * columns + column] = scale * f64::from(code) + bias;
        }
    }
    Ok(())
}

/// [`dequantize_rows_half`] for binary32 metadata.
#[allow(clippy::too_many_arguments)]
pub fn dequantize_rows_single(
    words: &[u32],
    scale_bits: &[u32],
    bias_bits: &[u32],
    bits: u32,
    group_size: u32,
    rows: usize,
    columns: usize,
    out: &mut [f64],
) -> Result<(), ReferenceError> {
    if scale_bits.len() != bias_bits.len() {
        return Err(ReferenceError::Geometry(
            "scales and biases differ in length",
        ));
    }
    let (packed_columns, groups) = check_geometry(
        bits,
        group_size,
        rows,
        columns,
        words.len(),
        scale_bits.len(),
    )?;
    if out.len() != rows * columns {
        return Err(ReferenceError::Geometry(
            "output length does not match the geometry",
        ));
    }
    for row in 0..rows {
        let row_words = &words[row * packed_columns..(row + 1) * packed_columns];
        for column in 0..columns {
            let code = extract_code(row_words, bits, column)?;
            let group = row * groups + column / (group_size as usize);
            let scale = single_to_f64(scale_bits[group]);
            let bias = single_to_f64(bias_bits[group]);
            out[row * columns + column] = scale * f64::from(code) + bias;
        }
    }
    Ok(())
}

/// Every code of `rows * columns` elements, in row-major order.
pub fn unpack_codes_reference(
    words: &[u32],
    bits: u32,
    rows: usize,
    columns: usize,
    out: &mut [u32],
) -> Result<(), ReferenceError> {
    if bits == 0 || bits > 8 {
        return Err(ReferenceError::BitWidth(bits));
    }
    if !(columns * (bits as usize)).is_multiple_of(32) {
        return Err(ReferenceError::Geometry(
            "a row is not a whole number of packed words",
        ));
    }
    let packed_columns = columns * (bits as usize) / 32;
    if words.len() != rows * packed_columns {
        return Err(ReferenceError::Geometry(
            "packed stream length does not match the geometry",
        ));
    }
    if out.len() != rows * columns {
        return Err(ReferenceError::Geometry(
            "output length does not match the geometry",
        ));
    }
    for row in 0..rows {
        let row_words = &words[row * packed_columns..(row + 1) * packed_columns];
        for column in 0..columns {
            out[row * columns + column] = extract_code(row_words, bits, column)?;
        }
    }
    Ok(())
}
