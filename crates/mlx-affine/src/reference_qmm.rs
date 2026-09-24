//! R1 for F020 Slice 2B -- an independent binary64 reference for the two
//! native primitives the slice qualifies: OP-QMM (`y = x . W^T`, the
//! `transpose = true` quantized matmul) and OP-DQ (affine dequantization).
//!
//! # Independence
//!
//! This file is self-contained. It has **no `use` statements**, names neither
//! `crate::` nor `super::`, shares no type or helper with the production R3
//! path of this crate or with the Slice 1 reference module, and calls no
//! native library. `tests/reference_qmm_static.rs` reads this file and asserts
//! that, so the claim is checked rather than promised. The Slice 1 dequant
//! reference is deliberately **not** reused here: the Slice 2B contract does not
//! designate it as the OP-DQ R1, and G-DQ-RUST names its own operation order,
//! which this file implements directly.
//!
//! Its inputs are the stored bit patterns exactly as a fixture file or a
//! Safetensors payload holds them: `&[u32]` for the packed weight and for
//! binary32 values, `&[u16]` for binary16 and bfloat16 metadata. Every input
//! value is widened to binary64 exactly (every finite binary16, bfloat16 and
//! binary32 value is a binary64 value); a NaN or an infinity is refused.
//!
//! # The format
//!
//! *  Packing: code `j` of a weight row occupies bits `[j*bits, j*bits + bits)`
//!    of that row's contiguous little-endian `u32` stream, least significant
//!    bit first. The extraction below is bit-serial, so it has no special case
//!    for a code that crosses a word boundary.
//! *  Groups: `group_size` consecutive elements along K share one scale and one
//!    bias; scales and biases are `[rows, K / group_size]`, row-major.
//! *  Affine value: `w = s*q + b`.
//!
//! # Operation order (contract `acceptance_implementation`)
//!
//! Every operation below is one binary64 round-to-nearest-even operation
//! (`fl`). Rust never contracts `a*b + c` into a fused multiply-add, so the
//! order written is the order executed.
//!
//! *  OP-DQ (G-DQ-RUST): `P_hat = fl(s*q)`, which is `s*q` exactly (`s` has at
//!    most 24 significant bits, `q` at most 8), and `w_hat = fl(P_hat + b)`.
//! *  OP-QMM (G-QMM-RUST): `w_k = fl(fl(s*q) + b)`;
//!    `y1 = ((0 + fl(w_0*x_0)) + fl(w_1*x_1)) + ...`, a sequential binary64
//!    sum over `k` ascending; and
//!    `Phi_hat = sum_k fl(fl(fl(|s|*q) + |b|) * |x_k|)`, sequential over `k`
//!    ascending in the same way.
//!
//! The acceptance padding of G-QMM-RUST and G-DQ-RUST rests on these orders:
//! `|y1 - y*| <= gamma64_{K+1} * Phi`, `|Phi_hat - Phi| <= gamma64_{K+2} * Phi`
//! and `|w_hat - w| <= 2^-53 * |w|`. The first and the last are the R1
//! self-checks N-R1-SELF and N-R1-SELF-DQ; they are decided by exact rational
//! comparison against the exact Python R1
//! (`scripts/research/mlx_affine_qmm_reference_v1.py`), never here.
//!
//! # Interface
//!
//! ```text
//! qmm_reference(x_bits: &[u32], w_packed: &[u32], meta: QmmMetadata<'_>,
//!               m: usize, n: usize, k: usize, bits: u32, group_size: usize)
//!     -> Result<QmmReference, QmmReferenceError>
//!   x_bits    [m, k] binary32 bit patterns, row-major (m = M_eff: every
//!             leading dimension of x multiplied together)
//!   w_packed  [n, k*bits/32] packed codes, row-major (the stored [out, in])
//!   meta      scales and biases, [n, k/group_size] each, in one stored dtype
//!   result    y[m*n] and phi[m*n], row-major [m, n]: y[i*n + j] is y1 and
//!             phi[i*n + j] is Phi_hat for x row i and weight row j
//!
//! dq_reference(w_packed: &[u32], meta: QmmMetadata<'_>,
//!              rows: usize, k: usize, bits: u32, group_size: usize)
//!     -> Result<DqReference, QmmReferenceError>
//!   result    p[rows*k] (P_hat) and w[rows*k] (w_hat), row-major [rows, k]
//! ```
//!
//! Geometry is checked (every dimension >= 1, `1 <= bits <= 8`,
//! `k % group_size == 0`, whole packed words per row, every slice length
//! exact). The bridge's numerical domain is **not** re-checked: R1 is defined
//! for every finite input, and binary64 neither overflows nor underflows on
//! finite binary32 and binary16 operands at these sizes.

/// Stored scales and biases of one quantized tensor, as bit patterns, both in
/// the same stored dtype (the type makes a mixed pair unrepresentable).
#[derive(Debug, Clone, Copy)]
pub enum QmmMetadata<'a> {
    /// IEEE 754 binary16.
    F16 {
        scales: &'a [u16],
        biases: &'a [u16],
    },
    /// bfloat16, the leading 16 bits of a binary32.
    Bf16 {
        scales: &'a [u16],
        biases: &'a [u16],
    },
    /// IEEE 754 binary32.
    F32 {
        scales: &'a [u32],
        biases: &'a [u32],
    },
}

/// Why the reference declined an input.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum QmmReferenceError {
    /// A bit width outside `1..=8`.
    Bits(u32),
    /// A shape or a slice length that does not describe the stated geometry.
    Shape(&'static str),
    /// A NaN or an infinity in the named tensor, at a flat element index.
    NonFinite { tensor: &'static str, index: usize },
    /// A size computation left the range of `usize`.
    Overflow,
}

impl core::fmt::Display for QmmReferenceError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::Bits(bits) => write!(f, "bit width {bits} is outside 1..=8"),
            Self::Shape(detail) => write!(f, "shape: {detail}"),
            Self::NonFinite { tensor, index } => {
                write!(f, "{tensor}[{index}] is not finite")
            }
            Self::Overflow => f.write_str("a size computation overflowed"),
        }
    }
}

impl std::error::Error for QmmReferenceError {}

/// The binary64 R1 of one OP-QMM call.
#[derive(Debug, Clone, PartialEq)]
pub struct QmmReference {
    /// Rows of x (`M_eff`).
    pub m: usize,
    /// Rows of W (`N`).
    pub n: usize,
    /// `y1`, row-major `[m, n]`.
    pub y: Vec<f64>,
    /// `Phi_hat`, row-major `[m, n]`.
    pub phi: Vec<f64>,
}

/// The binary64 R1 of one OP-DQ call.
#[derive(Debug, Clone, PartialEq)]
pub struct DqReference {
    /// Weight rows.
    pub rows: usize,
    /// Logical columns (`K`).
    pub k: usize,
    /// `P_hat = s*q` (exact), row-major `[rows, k]`.
    pub p: Vec<f64>,
    /// `w_hat = fl(P_hat + b)`, row-major `[rows, k]`.
    pub w: Vec<f64>,
}

/// Widen a binary16 bit pattern to binary64 exactly; `None` for NaN or an
/// infinity. The binary64 bit pattern is assembled directly for normal values
/// and subnormals are `fraction * 2^-24`, a product by a power of two that is
/// exact in binary64. Both signed zeros are preserved.
pub fn widen_f16_bits(pattern: u16) -> Option<f64> {
    let negative = pattern & 0x8000 != 0;
    let exponent = u64::from((pattern >> 10) & 0x1F);
    let fraction = u64::from(pattern & 0x03FF);
    let magnitude = if exponent == 0x1F {
        return None;
    } else if exponent == 0 {
        // 2^-24 as a binary64 bit pattern: biased exponent 1023 - 24.
        (fraction as f64) * f64::from_bits((1023 - 24) << 52)
    } else {
        // Rebias 15 -> 1023 and move the 10 fraction bits to the top of 52.
        f64::from_bits(((exponent + 1023 - 15) << 52) | (fraction << 42))
    };
    Some(if negative { -magnitude } else { magnitude })
}

/// Widen a bfloat16 bit pattern to binary64 exactly; `None` for NaN or an
/// infinity. bfloat16 is the leading half of a binary32.
pub fn widen_bf16_bits(pattern: u16) -> Option<f64> {
    widen_f32_bits(u32::from(pattern) << 16)
}

/// Widen a binary32 bit pattern to binary64 exactly; `None` for NaN or an
/// infinity.
pub fn widen_f32_bits(pattern: u32) -> Option<f64> {
    let value = f64::from(f32::from_bits(pattern));
    if value.is_finite() {
        Some(value)
    } else {
        None
    }
}

/// Code `index` of a row's packed stream, least significant bit first.
///
/// Bit `t` of the stream is bit `t % 32` of word `t / 32`. The caller
/// guarantees `1 <= bits <= 8` and that the stream holds the code.
fn packed_code(row: &[u32], bits: u32, index: usize) -> u32 {
    let start = index * (bits as usize);
    let mut code = 0u32;
    for offset in 0..(bits as usize) {
        let position = start + offset;
        let bit = (row[position / 32] >> (position % 32)) & 1;
        code |= bit << offset;
    }
    code
}

fn product(a: usize, b: usize) -> Result<usize, QmmReferenceError> {
    a.checked_mul(b).ok_or(QmmReferenceError::Overflow)
}

/// The widened, validated metadata and packed geometry shared by both ops.
struct Widened {
    scales: Vec<f64>,
    biases: Vec<f64>,
    packed_columns: usize,
    groups: usize,
}

fn widen_all<T: Copy>(
    values: &[T],
    widen: fn(T) -> Option<f64>,
    tensor: &'static str,
) -> Result<Vec<f64>, QmmReferenceError> {
    let mut out = Vec::with_capacity(values.len());
    for (index, value) in values.iter().enumerate() {
        match widen(*value) {
            Some(wide) => out.push(wide),
            None => return Err(QmmReferenceError::NonFinite { tensor, index }),
        }
    }
    Ok(out)
}

fn prepare(
    w_packed: &[u32],
    meta: QmmMetadata<'_>,
    rows: usize,
    k: usize,
    bits: u32,
    group_size: usize,
) -> Result<Widened, QmmReferenceError> {
    if bits == 0 || bits > 8 {
        return Err(QmmReferenceError::Bits(bits));
    }
    if rows == 0 || k == 0 {
        return Err(QmmReferenceError::Shape("a dimension is zero"));
    }
    if group_size == 0 || !k.is_multiple_of(group_size) {
        return Err(QmmReferenceError::Shape(
            "K is not a whole number of groups",
        ));
    }
    let row_bits = product(k, bits as usize)?;
    if !row_bits.is_multiple_of(32) {
        return Err(QmmReferenceError::Shape(
            "a weight row is not a whole number of packed words",
        ));
    }
    let packed_columns = row_bits / 32;
    let groups = k / group_size;
    if w_packed.len() != product(rows, packed_columns)? {
        return Err(QmmReferenceError::Shape(
            "packed weight length is not rows * K * bits / 32",
        ));
    }
    let metadata_len = product(rows, groups)?;
    let (scales, biases) = match meta {
        QmmMetadata::F16 { scales, biases } => {
            if scales.len() != metadata_len || biases.len() != metadata_len {
                return Err(QmmReferenceError::Shape(
                    "scales or biases length is not rows * K / group_size",
                ));
            }
            (
                widen_all(scales, widen_f16_bits, "scales")?,
                widen_all(biases, widen_f16_bits, "biases")?,
            )
        }
        QmmMetadata::Bf16 { scales, biases } => {
            if scales.len() != metadata_len || biases.len() != metadata_len {
                return Err(QmmReferenceError::Shape(
                    "scales or biases length is not rows * K / group_size",
                ));
            }
            (
                widen_all(scales, widen_bf16_bits, "scales")?,
                widen_all(biases, widen_bf16_bits, "biases")?,
            )
        }
        QmmMetadata::F32 { scales, biases } => {
            if scales.len() != metadata_len || biases.len() != metadata_len {
                return Err(QmmReferenceError::Shape(
                    "scales or biases length is not rows * K / group_size",
                ));
            }
            (
                widen_all(scales, widen_f32_bits, "scales")?,
                widen_all(biases, widen_f32_bits, "biases")?,
            )
        }
    };
    Ok(Widened {
        scales,
        biases,
        packed_columns,
        groups,
    })
}

/// OP-DQ R1: `P_hat = s*q` (exact) and `w_hat = fl(P_hat + b)` for every
/// element of a `[rows, k]` weight, row-major.
pub fn dq_reference(
    w_packed: &[u32],
    meta: QmmMetadata<'_>,
    rows: usize,
    k: usize,
    bits: u32,
    group_size: usize,
) -> Result<DqReference, QmmReferenceError> {
    let wide = prepare(w_packed, meta, rows, k, bits, group_size)?;
    let total = product(rows, k)?;
    let mut p = Vec::with_capacity(total);
    let mut w = Vec::with_capacity(total);
    for row in 0..rows {
        let stream = &w_packed[row * wide.packed_columns..(row + 1) * wide.packed_columns];
        for column in 0..k {
            let q = f64::from(packed_code(stream, bits, column));
            let group = row * wide.groups + column / group_size;
            let scaled = wide.scales[group] * q;
            p.push(scaled);
            w.push(scaled + wide.biases[group]);
        }
    }
    Ok(DqReference { rows, k, p, w })
}

/// OP-QMM R1: `y1` and `Phi_hat` for `y = x . W^T`, x `[m, k]` binary32,
/// W `[n, k]` packed, output row-major `[m, n]`.
#[allow(clippy::too_many_arguments)]
pub fn qmm_reference(
    x_bits: &[u32],
    w_packed: &[u32],
    meta: QmmMetadata<'_>,
    m: usize,
    n: usize,
    k: usize,
    bits: u32,
    group_size: usize,
) -> Result<QmmReference, QmmReferenceError> {
    let wide = prepare(w_packed, meta, n, k, bits, group_size)?;
    if m == 0 {
        return Err(QmmReferenceError::Shape("a dimension is zero"));
    }
    if x_bits.len() != product(m, k)? {
        return Err(QmmReferenceError::Shape("x length is not M_eff * K"));
    }
    let x = widen_all(x_bits, widen_f32_bits, "x")?;
    let weights = product(n, k)?;
    // w_k = fl(fl(s*q) + b) and a_k = fl(fl(|s|*q) + |b|), once per weight
    // element; s*q and |s|*q are exact.
    let mut w = Vec::with_capacity(weights);
    let mut a = Vec::with_capacity(weights);
    for row in 0..n {
        let stream = &w_packed[row * wide.packed_columns..(row + 1) * wide.packed_columns];
        for column in 0..k {
            let q = f64::from(packed_code(stream, bits, column));
            let group = row * wide.groups + column / group_size;
            let s = wide.scales[group];
            let b = wide.biases[group];
            w.push(s * q + b);
            a.push(s.abs() * q + b.abs());
        }
    }
    let outputs = product(m, n)?;
    let mut y = Vec::with_capacity(outputs);
    let mut phi = Vec::with_capacity(outputs);
    for i in 0..m {
        let x_row = &x[i * k..(i + 1) * k];
        for j in 0..n {
            let w_row = &w[j * k..(j + 1) * k];
            let a_row = &a[j * k..(j + 1) * k];
            let mut sum = 0.0f64;
            let mut envelope = 0.0f64;
            for t in 0..k {
                sum += w_row[t] * x_row[t];
                envelope += a_row[t] * x_row[t].abs();
            }
            y.push(sum);
            phi.push(envelope);
        }
    }
    Ok(QmmReference { m, n, y, phi })
}
