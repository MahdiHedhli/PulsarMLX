//! The bridge's refusals, evaluated on the host in the contract's frozen
//! order before any MLX-C numerical call (contract `refusals`, `domains`).
//!
//! The first failing check's id is returned. Each guard reads only what the
//! earlier guards have already proven well formed: value guards run after
//! R-META (and, for quantized matmul, after R-XDTYPE and R-XSHAPE), so they
//! never see inconsistent metadata, and the magnitude, row-sum, envelope and
//! element guards run after R-NONFINITE and R-SUBNORMAL, so they only see zero
//! or normal values. Every comparison is exact integer arithmetic on the
//! 2^-55 lattice that D-NUM and D-DQ guarantee.

use crate::dtype::{
    abs_units, classify, decode, lambda_units, max_finite_units, rn_units, Class, Dtype,
    FloatFormat, UNIT_EXP,
};
use crate::fixture::HostTensor;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum RefusalId {
    Device,
    Transpose,
    Bits,
    Group,
    WDtype,
    EmptyDim,
    Meta,
    XDtype,
    XShape,
    Geometry,
    NonFinite,
    Subnormal,
    DomainXRange,
    DomainMetaRange,
    DomainRowSum,
    DomainWMax,
    DqRange,
    DqNormal,
}

impl RefusalId {
    pub fn as_str(self) -> &'static str {
        match self {
            RefusalId::Device => "R-DEVICE",
            RefusalId::Transpose => "R-TRANSPOSE",
            RefusalId::Bits => "R-BITS",
            RefusalId::Group => "R-GROUP",
            RefusalId::WDtype => "R-WDTYPE",
            RefusalId::EmptyDim => "R-EMPTY-DIM",
            RefusalId::Meta => "R-META",
            RefusalId::XDtype => "R-XDTYPE",
            RefusalId::XShape => "R-XSHAPE",
            RefusalId::Geometry => "R-GEOMETRY",
            RefusalId::NonFinite => "R-NONFINITE",
            RefusalId::Subnormal => "R-SUBNORMAL",
            RefusalId::DomainXRange => "R-DOMAIN-X-RANGE",
            RefusalId::DomainMetaRange => "R-DOMAIN-META-RANGE",
            RefusalId::DomainRowSum => "R-DOMAIN-ROWSUM",
            RefusalId::DomainWMax => "R-DOMAIN-WMAX",
            RefusalId::DqRange => "R-DQ-RANGE",
            RefusalId::DqNormal => "R-DQ-NORMAL",
        }
    }
}

impl std::fmt::Display for RefusalId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.as_str())
    }
}

/// D-GEOM caps (contract domains.D-GEOM.constraints).
pub const K_MAX: usize = 16384;
pub const N_MAX: usize = 16384;
pub const M_MAX: usize = 4096;
pub const N_ALIGN: usize = 64;
/// D-NUM magnitude window exponents (every nonzero |x|, |s|, |b| in [2^-32, 2^32]).
pub const E_LO: i32 = -32;
pub const E_HI: i32 = 32;

/// What the bridge knows about its execution context (R-DEVICE inputs).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DeviceFacts {
    pub context_device_gpu: bool,
    pub metal_available: bool,
    pub stream_device_gpu: bool,
    pub default_device_gpu: bool,
}

impl DeviceFacts {
    pub const GPU: DeviceFacts = DeviceFacts {
        context_device_gpu: true,
        metal_available: true,
        stream_device_gpu: true,
        default_device_gpu: true,
    };
    fn ok(&self) -> bool {
        self.context_device_gpu
            && self.metal_available
            && self.stream_device_gpu
            && self.default_device_gpu
    }
}

/// Admitted quantized-matmul geometry.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct QmmGeometry {
    pub m_eff: usize,
    pub n: usize,
    pub k: usize,
    pub bits: u32,
    pub group_size: u32,
    pub meta: FloatFormat,
}

/// Admitted dequantize geometry.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DqGeometry {
    pub rows: usize,
    pub k: usize,
    pub bits: u32,
    pub group_size: u32,
    pub meta: FloatFormat,
}

fn any_zero_dim(t: &HostTensor) -> bool {
    t.shape.contains(&0)
}

/// R-META (rank-2 weight already established by R-WDTYPE): returns
/// (metadata format, rows, groups).
fn check_meta(
    w: &HostTensor,
    s: &HostTensor,
    b: &HostTensor,
    bits: u32,
    gs: u32,
) -> Result<(FloatFormat, usize), RefusalId> {
    let meta = match s.dtype.float() {
        Some(f) => f,
        None => return Err(RefusalId::Meta),
    };
    if b.dtype != s.dtype || s.shape != b.shape || s.shape.len() != 2 {
        return Err(RefusalId::Meta);
    }
    let rows = w.shape[0];
    let packed = w.shape[1];
    if s.shape[0] != rows {
        return Err(RefusalId::Meta);
    }
    let groups = s.shape[1];
    // packed*32 == groups*group_size*bits, in u128 so nothing wraps.
    if (packed as u128) * 32 != (groups as u128) * (gs as u128) * (bits as u128) {
        return Err(RefusalId::Meta);
    }
    Ok((meta, groups))
}

fn classes(f: FloatFormat, t: &HostTensor) -> impl Iterator<Item = Class> + '_ {
    (0..t.elements()).map(move |i| classify(f, t.bits(i)))
}

fn nonfinite(f: FloatFormat, t: &HostTensor) -> bool {
    classes(f, t).any(|c| matches!(c, Class::Infinite | Class::Nan))
}

fn subnormal(f: FloatFormat, t: &HostTensor) -> bool {
    classes(f, t).any(|c| c == Class::Subnormal)
}

/// A NORMAL value with magnitude outside [2^E_LO, 2^E_HI].
fn out_of_range(f: FloatFormat, t: &HostTensor) -> bool {
    (0..t.elements()).any(|i| {
        let bits = t.bits(i);
        if classify(f, bits) != Class::Normal {
            return false;
        }
        let x = decode(f, bits).expect("normal is finite");
        // |x| = mant * 2^exp with mant normalised to p bits: floor(log2|x|) = exp + p - 1.
        let top = x.exp + (63 - x.mant.leading_zeros() as i32);
        let exact_pow2 = x.mant.is_power_of_two();
        !(E_LO..=E_HI).contains(&top) || (top == E_HI && !exact_pow2)
    })
}

fn units(f: FloatFormat, bits: u32) -> u128 {
    // Only called on zero/normal values inside [2^-32, 2^32] (or F16 normals,
    // which are multiples of 2^-24): always an integer number of 2^-55 units.
    abs_units(f, bits).expect("admitted value on the 2^-55 lattice")
}

/// Extract code `j` of `row` from an LSB-first packed row (bits in {4, 8}).
pub fn code_at(words: &[u32], packed_cols: usize, bits: u32, row: usize, j: usize) -> u32 {
    let bit = j * bits as usize;
    let word = words[row * packed_cols + bit / 32];
    (word >> (bit % 32)) & ((1u32 << bits) - 1)
}

fn check_device(device: &DeviceFacts) -> Result<(), RefusalId> {
    if device.ok() {
        Ok(())
    } else {
        Err(RefusalId::Device)
    }
}

/// The full frozen order for OP-QMM. `transpose` is only ever false through
/// the test-only entry point.
#[allow(clippy::too_many_arguments)]
pub fn check_qmm(
    device: &DeviceFacts,
    transpose: bool,
    x: &HostTensor,
    w: &HostTensor,
    s: &HostTensor,
    b: &HostTensor,
    bits: u32,
    gs: u32,
) -> Result<QmmGeometry, RefusalId> {
    check_device(device)?;
    if !transpose {
        return Err(RefusalId::Transpose);
    }
    if bits != 4 && bits != 8 {
        return Err(RefusalId::Bits);
    }
    if gs != 32 && gs != 64 && gs != 128 {
        return Err(RefusalId::Group);
    }
    if w.dtype != Dtype::U32 || w.shape.len() != 2 {
        return Err(RefusalId::WDtype);
    }
    if [x, w, s, b].iter().any(|t| any_zero_dim(t)) {
        return Err(RefusalId::EmptyDim);
    }
    let (meta, groups) = check_meta(w, s, b, bits, gs)?;
    if x.dtype != Dtype::F32 {
        return Err(RefusalId::XDtype);
    }
    let k = groups * gs as usize;
    if !(1..=3).contains(&x.shape.len()) || *x.shape.last().unwrap() != k {
        return Err(RefusalId::XShape);
    }
    let n = w.shape[0];
    let m_eff: usize = x.shape[..x.shape.len() - 1].iter().product();
    if k > K_MAX
        || n > N_MAX
        || m_eff > M_MAX
        || !n.is_multiple_of(N_ALIGN)
        || !k.is_multiple_of(gs as usize)
    {
        return Err(RefusalId::Geometry);
    }
    let x32 = FloatFormat::F32;
    if nonfinite(x32, x) || nonfinite(meta, s) || nonfinite(meta, b) {
        return Err(RefusalId::NonFinite);
    }
    if subnormal(x32, x) || subnormal(meta, s) || subnormal(meta, b) {
        return Err(RefusalId::Subnormal);
    }
    if out_of_range(x32, x) {
        return Err(RefusalId::DomainXRange);
    }
    if out_of_range(meta, s) || out_of_range(meta, b) {
        return Err(RefusalId::DomainMetaRange);
    }
    // R-DOMAIN-ROWSUM: sum_k |x[m,k]| <= 2^40, exactly (units of 2^-55; each
    // |x| < 2^88 units and K <= 2^14, so the sum stays below 2^102).
    let rowsum_max: u128 = 1u128 << (40 - UNIT_EXP);
    for m in 0..m_eff {
        let mut sum: u128 = 0;
        for kk in 0..k {
            sum += units(x32, x.bits(m * k + kk));
        }
        if sum > rowsum_max {
            return Err(RefusalId::DomainRowSum);
        }
    }
    // R-DOMAIN-WMAX: |s|*255 + |b| <= 2^36 for every group.
    let wmax: u128 = 1u128 << (36 - UNIT_EXP);
    for g in 0..s.elements() {
        let v = units(meta, s.bits(g)) * 255 + units(meta, b.bits(g));
        if v > wmax {
            return Err(RefusalId::DomainWMax);
        }
    }
    Ok(QmmGeometry {
        m_eff,
        n,
        k,
        bits,
        group_size: gs,
        meta,
    })
}

/// The full frozen order for OP-DQ.
pub fn check_dq(
    device: &DeviceFacts,
    w: &HostTensor,
    s: &HostTensor,
    b: &HostTensor,
    bits: u32,
    gs: u32,
) -> Result<DqGeometry, RefusalId> {
    check_device(device)?;
    if bits != 4 && bits != 8 {
        return Err(RefusalId::Bits);
    }
    if gs != 32 && gs != 64 && gs != 128 {
        return Err(RefusalId::Group);
    }
    if w.dtype != Dtype::U32 || w.shape.len() != 2 {
        return Err(RefusalId::WDtype);
    }
    if [w, s, b].iter().any(|t| any_zero_dim(t)) {
        return Err(RefusalId::EmptyDim);
    }
    let (meta, groups) = check_meta(w, s, b, bits, gs)?;
    let k = groups * gs as usize;
    let rows = w.shape[0];
    if k > K_MAX || rows > N_MAX || !k.is_multiple_of(gs as usize) {
        return Err(RefusalId::Geometry);
    }
    if nonfinite(meta, s) || nonfinite(meta, b) {
        return Err(RefusalId::NonFinite);
    }
    if subnormal(meta, s) || subnormal(meta, b) {
        return Err(RefusalId::Subnormal);
    }
    if out_of_range(meta, s) || out_of_range(meta, b) {
        return Err(RefusalId::DomainMetaRange);
    }
    let words = w.words_u32();
    let packed = w.shape[1];
    let per_row_groups = groups;
    // R-DQ-RANGE: |s|*q + |b| <= 0.5*max_T for every element (exact).
    let half_max = max_finite_units(meta).map(|m| m / 2); // max_T is even in units
    for r in 0..rows {
        for j in 0..k {
            let g = r * per_row_groups + j / gs as usize;
            let q = code_at(&words, packed, bits, r, j) as u128;
            let v = units(meta, s.bits(g)) * q + units(meta, b.bits(g));
            if let Some(h) = half_max {
                if v > h {
                    return Err(RefusalId::DqRange);
                }
            }
        }
    }
    // R-DQ-NORMAL: exact P + b and RN_T(P) + b each zero or >= lambda_T.
    let lambda = lambda_units(meta);
    for r in 0..rows {
        for j in 0..k {
            let g = r * per_row_groups + j / gs as usize;
            let q = code_at(&words, packed, bits, r, j) as u128;
            let sv = decode(meta, s.bits(g)).unwrap();
            let bv = decode(meta, b.bits(g)).unwrap();
            let p_abs = units(meta, s.bits(g)) * q;
            let p_neg = sv.negative && p_abs != 0;
            let b_abs = units(meta, b.bits(g));
            let b_neg = bv.negative && b_abs != 0;
            let rn_p = rn_units(meta, p_abs).expect("R-DQ-RANGE bounds P below max_T");
            for p in [p_abs, rn_p] {
                let sum = signed_add(p_neg, p, b_neg, b_abs);
                if let Some(l) = lambda {
                    if sum != 0 && sum < l {
                        return Err(RefusalId::DqNormal);
                    }
                }
            }
        }
    }
    Ok(DqGeometry {
        rows,
        k,
        bits,
        group_size: gs,
        meta,
    })
}

/// |(-1)^an * a + (-1)^bn * b| for unsigned magnitudes.
fn signed_add(an: bool, a: u128, bn: bool, b: u128) -> u128 {
    if an == bn {
        a + b
    } else {
        a.abs_diff(b)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn t(name: &str, dtype: Dtype, shape: &[usize], words: &[u32]) -> HostTensor {
        let mut bytes = Vec::new();
        for &w in words {
            match dtype.size() {
                4 => bytes.extend_from_slice(&w.to_le_bytes()),
                _ => bytes.extend_from_slice(&(w as u16).to_le_bytes()),
            }
        }
        HostTensor {
            name: name.into(),
            dtype,
            shape: shape.to_vec(),
            bytes,
        }
    }

    #[test]
    fn range_boundaries_are_inclusive() {
        let f = FloatFormat::F32;
        let at = |bits: u32| out_of_range(f, &t("x", Dtype::F32, &[1], &[bits]));
        assert!(!at(0x2F80_0000)); // 2^-32
        assert!(at(0x2F7F_FFFF)); // just below 2^-32
        assert!(!at(0x4F80_0000)); // 2^32
        assert!(at(0x4F80_0001)); // just above 2^32
        assert!(!at(0x0000_0000));
        assert!(!at(0x8000_0000));
        assert!(!at(0xCF80_0000)); // -2^32
    }

    #[test]
    fn transpose_false_is_refused_after_device() {
        let x = t("x", Dtype::F32, &[1, 64], &[0; 64]);
        let w = t("w", Dtype::U32, &[64, 8], &[0; 512]);
        let s = t("s", Dtype::BF16, &[64, 1], &[0x3F80; 64]);
        let b = t("b", Dtype::BF16, &[64, 1], &[0; 64]);
        assert_eq!(
            check_qmm(&DeviceFacts::GPU, false, &x, &w, &s, &b, 4, 64),
            Err(RefusalId::Transpose)
        );
        let cpu = DeviceFacts {
            context_device_gpu: false,
            ..DeviceFacts::GPU
        };
        assert_eq!(
            check_qmm(&cpu, false, &x, &w, &s, &b, 4, 64),
            Err(RefusalId::Device)
        );
        assert!(check_qmm(&DeviceFacts::GPU, true, &x, &w, &s, &b, 4, 64).is_ok());
    }
}
