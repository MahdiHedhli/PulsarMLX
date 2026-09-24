//! Storage dtypes and exact, bit-level host arithmetic on binary16, bfloat16
//! and binary32 patterns.
//!
//! Nothing here uses hardware half-precision conversion: every function works
//! on integer bit patterns, so the host side of N-CAST-WIDEN and of the
//! refusal guards is exact by construction and independent of the compiler's
//! float semantics.

/// A tensor's stored element type, as spelled in the fixture manifest.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Dtype {
    U32,
    F16,
    BF16,
    F32,
}

impl Dtype {
    pub fn parse(name: &str) -> Option<Dtype> {
        match name {
            "U32" => Some(Dtype::U32),
            "F16" => Some(Dtype::F16),
            "BF16" => Some(Dtype::BF16),
            "F32" => Some(Dtype::F32),
            _ => None,
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Dtype::U32 => "U32",
            Dtype::F16 => "F16",
            Dtype::BF16 => "BF16",
            Dtype::F32 => "F32",
        }
    }

    pub fn size(self) -> usize {
        match self {
            Dtype::U32 | Dtype::F32 => 4,
            Dtype::F16 | Dtype::BF16 => 2,
        }
    }

    /// The floating format of a floating dtype.
    pub fn float(self) -> Option<FloatFormat> {
        match self {
            Dtype::U32 => None,
            Dtype::F16 => Some(FloatFormat::F16),
            Dtype::BF16 => Some(FloatFormat::BF16),
            Dtype::F32 => Some(FloatFormat::F32),
        }
    }
}

/// The three floating formats of the contract.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum FloatFormat {
    F16,
    BF16,
    F32,
}

/// (total bits, precision p including the hidden bit, emin, emax).
pub fn params(f: FloatFormat) -> (u32, u32, i32, i32) {
    match f {
        FloatFormat::F32 => (32, 24, -126, 127),
        FloatFormat::F16 => (16, 11, -14, 15),
        FloatFormat::BF16 => (16, 8, -126, 127),
    }
}

impl FloatFormat {
    pub fn name(self) -> &'static str {
        match self {
            FloatFormat::F16 => "F16",
            FloatFormat::BF16 => "BF16",
            FloatFormat::F32 => "F32",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Class {
    Zero,
    Normal,
    Subnormal,
    Infinite,
    Nan,
}

fn fields(f: FloatFormat, bits: u32) -> (bool, u32, u32) {
    let (width, p, _, _) = params(f);
    let ebits = width - p;
    let sign = (bits >> (width - 1)) & 1 == 1;
    let e = (bits >> (p - 1)) & ((1 << ebits) - 1);
    let frac = bits & ((1 << (p - 1)) - 1);
    (sign, e, frac)
}

pub fn classify(f: FloatFormat, bits: u32) -> Class {
    let (width, p, _, _) = params(f);
    let emax_field = (1u32 << (width - p)) - 1;
    let (_, e, frac) = fields(f, bits);
    if e == emax_field {
        if frac == 0 {
            Class::Infinite
        } else {
            Class::Nan
        }
    } else if e == 0 {
        if frac == 0 {
            Class::Zero
        } else {
            Class::Subnormal
        }
    } else {
        Class::Normal
    }
}

/// An exact finite value `(-1)^negative * mant * 2^exp`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Exact {
    pub negative: bool,
    pub mant: u64,
    pub exp: i32,
}

/// Exact decode of a finite pattern; `None` for infinities and NaNs.
pub fn decode(f: FloatFormat, bits: u32) -> Option<Exact> {
    let (width, p, _, _) = params(f);
    let bias = (1i32 << (width - p - 1)) - 1;
    let (negative, e, frac) = fields(f, bits);
    match classify(f, bits) {
        Class::Infinite | Class::Nan => None,
        Class::Zero | Class::Subnormal => Some(Exact {
            negative,
            mant: frac as u64,
            exp: 1 - bias - (p as i32 - 1),
        }),
        Class::Normal => Some(Exact {
            negative,
            mant: (frac | (1 << (p - 1))) as u64,
            exp: e as i32 - bias - (p as i32 - 1),
        }),
    }
}

/// The exact binary64 value of a pattern (every binary16, bfloat16 and
/// binary32 value is exactly representable in binary64).
pub fn to_f64(f: FloatFormat, bits: u32) -> f64 {
    match f {
        FloatFormat::F32 => f32::from_bits(bits) as f64,
        _ => f32::from_bits(widen_to_f32_bits(f, bits)) as f64,
    }
}

/// The host widening to binary32, bit for bit, for every pattern.
///
/// Zero and normal patterns map to the exactly equal binary32 value with the
/// same sign (the gated domain of N-CAST-WIDEN). Subnormal binary16 patterns
/// are normalised exactly; infinities keep their sign; NaNs keep sign and
/// payload shifted into the binary32 fraction. Only the zero/normal part is
/// gated; the rest is recorded.
pub fn widen_to_f32_bits(f: FloatFormat, bits: u32) -> u32 {
    match f {
        FloatFormat::F32 => bits,
        FloatFormat::BF16 => (bits & 0xFFFF) << 16,
        FloatFormat::F16 => {
            let h = bits & 0xFFFF;
            let sign = (h >> 15) << 31;
            let e = (h >> 10) & 0x1F;
            let frac = h & 0x3FF;
            if e == 0x1F {
                sign | 0x7F80_0000 | (frac << 13)
            } else if e == 0 {
                if frac == 0 {
                    sign
                } else {
                    // value = frac * 2^-24; normalise.
                    let lead = 31 - frac.leading_zeros(); // position of the top bit, 0..=9
                    let exp = lead as i32 - 24; // unbiased exponent of the value
                    let m = (frac << (23 - lead)) & 0x7F_FFFF;
                    sign | (((exp + 127) as u32) << 23) | m
                }
            } else {
                sign | ((e + 127 - 15) << 23) | (frac << 13)
            }
        }
    }
}

/// The encoding in `f` of the non-negative integer `q` (q < 2^p), code 0 as
/// +0. Used by G-DQ-CODES.
pub fn encode_integer(f: FloatFormat, q: u32) -> u32 {
    let (width, p, _, _) = params(f);
    if q == 0 {
        return 0;
    }
    assert!(q < (1 << p), "integer {q} not exact in {}", f.name());
    let bias = (1u32 << (width - p - 1)) - 1;
    let e = 31 - q.leading_zeros();
    let frac = (q ^ (1 << e)) << (p - 1 - e);
    ((e + bias) << (p - 1)) | frac
}

/// Units of 2^-55: every zero or normal value admitted by D-NUM / D-DQ is an
/// integer multiple of 2^-55 (contract D-NUM.consequences.lattices).
pub const UNIT_EXP: i32 = -55;

/// |value| in units of 2^-55, if it is an integer number of units that fits.
pub fn abs_units(f: FloatFormat, bits: u32) -> Option<u128> {
    let x = decode(f, bits)?;
    let shift = x.exp - UNIT_EXP;
    if x.mant == 0 {
        return Some(0);
    }
    if shift < 0 {
        return None;
    }
    let width = 64 - x.mant.leading_zeros() as i32;
    if width + shift > 127 {
        return None;
    }
    Some((x.mant as u128) << shift)
}

/// Largest finite value of `f` in units of 2^-55, if it fits in a u128.
pub fn max_finite_units(f: FloatFormat) -> Option<u128> {
    let (_, p, _, emax) = params(f);
    let mant: u128 = (1u128 << p) - 1;
    let shift = emax - (p as i32 - 1) - UNIT_EXP;
    if shift < 0 || shift as u32 + p > 127 {
        return None;
    }
    Some(mant << shift)
}

/// Round-to-nearest-even of a non-negative value given in units of 2^-55
/// into format `f` (with gradual underflow at emin). Returns `None` when the
/// rounded value overflows to infinity.
pub fn rn_units(f: FloatFormat, units: u128) -> Option<u128> {
    if units == 0 {
        return Some(0);
    }
    let (_, p, emin, _) = params(f);
    let top = 127 - units.leading_zeros() as i32; // floor(log2(units))
    let e = top + UNIT_EXP; // floor(log2(value))
    let e_eff = e.max(emin);
    let quantum_exp = e_eff - (p as i32 - 1); // real exponent of the ulp
    let shift = quantum_exp - UNIT_EXP;
    let rounded = if shift <= 0 {
        units
    } else {
        // shift <= 72 - 7 + 56 < 128 for every format here (units < 2^128
        // gives e <= 72; p >= 8).
        let shift = shift as u32;
        assert!(shift < 128);
        let base = units >> shift;
        let low = units & ((1u128 << shift) - 1);
        let half = 1u128 << (shift - 1);
        let up = low > half || (low == half && base & 1 == 1);
        (base + up as u128) << shift
    };
    match max_finite_units(f) {
        Some(max) if rounded > max => None,
        _ => Some(rounded),
    }
}

/// lambda_f (smallest positive normal) in units of 2^-55, or `None` when it
/// is below one unit (then every nonzero lattice value is >= lambda_f).
pub fn lambda_units(f: FloatFormat) -> Option<u128> {
    let (_, _, emin, _) = params(f);
    let shift = emin - UNIT_EXP;
    if shift < 0 {
        None
    } else {
        Some(1u128 << shift)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn f16_widening_matches_exact_decode_for_every_finite_pattern() {
        for h in 0u32..=0xFFFF {
            let w = widen_to_f32_bits(FloatFormat::F16, h);
            match classify(FloatFormat::F16, h) {
                Class::Nan => {
                    assert_eq!(classify(FloatFormat::F32, w), Class::Nan);
                    assert_eq!(w >> 31, h >> 15);
                }
                Class::Infinite => {
                    assert_eq!(classify(FloatFormat::F32, w), Class::Infinite);
                    assert_eq!(w >> 31, h >> 15);
                }
                _ => {
                    let a = decode(FloatFormat::F16, h).unwrap();
                    let b = decode(FloatFormat::F32, w).unwrap();
                    assert_eq!(a.negative, b.negative, "{h:#06x}");
                    // same exact value: compare mant*2^exp
                    let va = (a.mant as f64) * (a.exp as f64).exp2();
                    let vb = (b.mant as f64) * (b.exp as f64).exp2();
                    assert_eq!(va, vb, "{h:#06x}");
                    assert_ne!(classify(FloatFormat::F32, w), Class::Subnormal);
                }
            }
        }
    }

    #[test]
    fn bf16_widening_is_the_leading_half() {
        for h in [0u32, 0x8000, 0x3F80, 0x7F80, 0xFF80, 0x7FC1, 0x0001] {
            assert_eq!(widen_to_f32_bits(FloatFormat::BF16, h), h << 16);
        }
    }

    #[test]
    fn integer_encodings() {
        for q in 0..=255u32 {
            for f in [FloatFormat::F16, FloatFormat::BF16, FloatFormat::F32] {
                let b = encode_integer(f, q);
                assert_eq!(to_f64(f, b), q as f64);
                if q == 0 {
                    assert_eq!(b, 0);
                }
            }
        }
        assert_eq!(encode_integer(FloatFormat::F16, 1), 0x3C00);
        assert_eq!(encode_integer(FloatFormat::BF16, 1), 0x3F80);
        assert_eq!(encode_integer(FloatFormat::F32, 255), 0x437F_0000);
    }

    #[test]
    fn rounding_to_nearest_even() {
        let one = 1u128 << 55;
        // 1 + 2^-11 is a tie in F16 (p = 11): rounds to even (1).
        assert_eq!(rn_units(FloatFormat::F16, one + (one >> 11)), Some(one));
        // 1 + 3*2^-11 rounds up to 1 + 2^-9.
        assert_eq!(
            rn_units(FloatFormat::F16, one + 3 * (one >> 11)),
            Some(one + (one >> 9))
        );
        // 65520 overflows F16.
        assert_eq!(rn_units(FloatFormat::F16, 65520 * one), None);
        assert_eq!(rn_units(FloatFormat::F16, 65504 * one), Some(65504 * one));
        assert_eq!(max_finite_units(FloatFormat::F16), Some(65504 * one));
        assert_eq!(max_finite_units(FloatFormat::F32), None);
        assert_eq!(lambda_units(FloatFormat::F16), Some(one >> 14));
        assert_eq!(lambda_units(FloatFormat::BF16), None);
    }
}
