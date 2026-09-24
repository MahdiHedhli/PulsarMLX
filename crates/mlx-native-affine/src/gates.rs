//! The frozen acceptance algorithms decided in binary64 or by exact bit
//! comparison (contract acceptance_implementation). The exact-rational gates
//! (G-QMM-EXACT, G-DQ-EXACT, G-R1-SELF-QMM, G-R1-SELF-DQ) are decided in
//! `acceptance/exact_gates_v1.py` with `fractions.Fraction`, as the contract
//! words them.
//!
//! Every `fl(.)` of the contract is exactly one binary64 operation below,
//! written as its own expression. Rust never contracts `a * b + c` into a
//! fused multiply-add, so each line is one round-to-nearest-even operation.
//! Constants that are powers of two are exact in binary64.

use crate::dtype::{classify, encode_integer, to_f64, widen_to_f32_bits, Class, FloatFormat};

/// P48 = 1 + 2^-48 and M48 = 1 - 2^-48 (both exact in binary64).
pub const P48: f64 = 1.0 + 1.0 / 281_474_976_710_656.0;
pub const M48: f64 = 1.0 - 1.0 / 281_474_976_710_656.0;
const TWO_M53: f64 = 1.0 / 9_007_199_254_740_992.0;
const TWO_M52: f64 = 1.0 / 4_503_599_627_370_496.0;
const TWO_M24: f64 = 1.0 / 16_777_216.0;

/// u_star_T (contract N-DQ-BOUND): 2^-24 (F32); 2^-11 + 2^-24 + 2^-35
/// (F16); 2^-8 + 2^-24 + 2^-32 (BF16). Each has at most 25 significant bits,
/// so the binary64 sums below are exact.
pub fn u_star(f: FloatFormat) -> f64 {
    match f {
        FloatFormat::F32 => pow2(-24),
        FloatFormat::F16 => pow2(-11) + pow2(-24) + pow2(-35),
        FloatFormat::BF16 => pow2(-8) + pow2(-24) + pow2(-32),
    }
}

/// 2^e for a normal binary64 exponent, built from its bit pattern (exact).
pub fn pow2(e: i32) -> f64 {
    assert!((-1022..=1023).contains(&e));
    f64::from_bits(((e + 1023) as u64) << 52)
}

/// G-DQ-RUST for one element. `out_bits` is the R3 output element in T;
/// `p_hat = fl(s*q)` and `w_hat = fl(p_hat + b)` come from the Rust R1.
/// Returns (pass, d_hi, B_lo).
pub fn g_dq_rust(f: FloatFormat, out_bits: u32, p_hat: f64, w_hat: f64) -> (bool, f64, f64) {
    let out = to_f64(f, out_bits);
    let c2 = u_star(f);
    let one_plus_c2 = 1.0 + c2;
    let c2_times = c2 * one_plus_c2;
    let c1_lo = c2_times * M48;
    // B_lo = fl(fl(fl(c1_lo * |P_hat|) + fl(fl(c2 * |w_hat|) * fl(1 - 2^-52))) * M48)
    let t1 = c1_lo * p_hat.abs();
    let one_minus_52 = 1.0 - TWO_M52;
    let t2a = c2 * w_hat.abs();
    let t2 = t2a * one_minus_52;
    let t3 = t1 + t2;
    let b_lo = t3 * M48;
    // d_hi = fl(fl(fl(|fl(out - w_hat)| * P48) + fl(|w_hat| * 2^-52)) * P48)
    let diff = out - w_hat;
    let d1 = diff.abs() * P48;
    let d2 = w_hat.abs() * TWO_M52;
    let d3 = d1 + d2;
    let d_hi = d3 * P48;
    (d_hi <= b_lo, d_hi, b_lo)
}

/// G-QMM-RUST for one output element. `y3` is the R3 float32 output;
/// `y1` and `phi_hat` come from the Rust R1; `k` is K and `n` the case's
/// gamma exponent. Returns (pass, d_hi, B_lo).
pub fn g_qmm_rust(y3: f32, y1: f64, phi_hat: f64, k: usize, n: usize) -> (bool, f64, f64) {
    let y3 = y3 as f64;
    // G64a = fl(fl((2K+4)*2^-53) / fl(1 - (2K+4)*2^-53))
    let a = (2 * k + 4) as f64;
    let a_u = a * TWO_M53;
    let a_den = 1.0 - a_u;
    let g64a = a_u / a_den;
    // Phi_lo = fl(fl(Phi_hat * fl(1 - G64a)) * M48); Phi_hi = fl(fl(Phi_hat * fl(1 + G64a)) * P48)
    let one_minus_g = 1.0 - g64a;
    let phi_lo_a = phi_hat * one_minus_g;
    let phi_lo = phi_lo_a * M48;
    let one_plus_g = 1.0 + g64a;
    let phi_hi_a = phi_hat * one_plus_g;
    let phi_hi = phi_hi_a * P48;
    // g = fl(fl(n*2^-24) / fl(1 - n*2^-24)); B_lo = fl(fl(fl(g * M48) * Phi_lo) * M48)
    let nn = n as f64;
    let n_u = nn * TWO_M24;
    let n_den = 1.0 - n_u;
    let g = n_u / n_den;
    let g_lo = g * M48;
    let b_lo_a = g_lo * phi_lo;
    let b_lo = b_lo_a * M48;
    // G64b = fl(fl((K+1)*2^-53) / fl(1 - (K+1)*2^-53)); e_R1_hi = fl(fl(G64b * Phi_hi) * P48)
    let kb = (k + 1) as f64;
    let kb_u = kb * TWO_M53;
    let kb_den = 1.0 - kb_u;
    let g64b = kb_u / kb_den;
    let e_a = g64b * phi_hi;
    let e_r1_hi = e_a * P48;
    // d_hi = fl(fl(fl(|fl(y3 - y1)| * P48) + e_R1_hi) * P48)
    let diff = y3 - y1;
    let d1 = diff.abs() * P48;
    let d2 = d1 + e_r1_hi;
    let d_hi = d2 * P48;
    (d_hi <= b_lo, d_hi, b_lo)
}

/// G-DQ-CODES: every output element bit-identical to the T encoding of its
/// code (code 0 -> +0). Returns the number of mismatching elements.
pub fn g_dq_codes(f: FloatFormat, codes: &[u32], out_bits: &[u32]) -> usize {
    assert_eq!(codes.len(), out_bits.len());
    codes
        .iter()
        .zip(out_bits)
        .filter(|(&q, &o)| encode_integer(f, q) != o)
        .count()
}

/// G-CAST outcome over an exhaustive 65536-pattern cast.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct CastOutcome {
    pub gated_patterns: usize,
    pub gated_mismatches: usize,
    pub recorded_subnormal: usize,
    pub recorded_subnormal_bit_equal: usize,
    pub recorded_subnormal_flushed_to_signed_zero: usize,
    pub recorded_infinite: usize,
    pub recorded_infinite_bit_equal: usize,
    pub recorded_nan: usize,
    pub recorded_nan_bit_equal: usize,
    pub recorded_nan_is_nan: usize,
}

/// N-CAST-WIDEN: bit equality with the host widening on zero/normal finite
/// patterns (gated); subnormal, infinity and NaN patterns recorded only.
pub fn g_cast(f: FloatFormat, inputs: &[u16], outputs: &[u32]) -> CastOutcome {
    assert_eq!(inputs.len(), outputs.len());
    let mut o = CastOutcome::default();
    for (&h, &got) in inputs.iter().zip(outputs) {
        let want = widen_to_f32_bits(f, h as u32);
        match classify(f, h as u32) {
            Class::Zero | Class::Normal => {
                o.gated_patterns += 1;
                if got != want {
                    o.gated_mismatches += 1;
                }
            }
            Class::Subnormal => {
                o.recorded_subnormal += 1;
                if got == want {
                    o.recorded_subnormal_bit_equal += 1;
                }
                if got & 0x7FFF_FFFF == 0 && (got >> 31) == ((h as u32 >> 15) & 1) {
                    o.recorded_subnormal_flushed_to_signed_zero += 1;
                }
            }
            Class::Infinite => {
                o.recorded_infinite += 1;
                if got == want {
                    o.recorded_infinite_bit_equal += 1;
                }
            }
            Class::Nan => {
                o.recorded_nan += 1;
                if got == want {
                    o.recorded_nan_bit_equal += 1;
                }
                if classify(FloatFormat::F32, got) == Class::Nan {
                    o.recorded_nan_is_nan += 1;
                }
            }
        }
    }
    o
}

/// N-QMM-ZERO for one x row: returns the number of outputs of that row that
/// are not +0 or -0 (only meaningful when every x in the row is +/-0).
pub fn qmm_zero_violations(row_outputs: &[f32]) -> usize {
    row_outputs
        .iter()
        .filter(|y| y.to_bits() & 0x7FFF_FFFF != 0)
        .count()
}

/// True when every element of an F32 x row is +0 or -0.
pub fn is_zero_row(x_bits: &[u32]) -> bool {
    x_bits.iter().all(|&b| b & 0x7FFF_FFFF == 0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn padding_constants_are_exact() {
        assert_eq!(P48 - 1.0, pow2(-48));
        assert_eq!(1.0 - M48, pow2(-48));
        assert_eq!(TWO_M53, pow2(-53));
        assert_eq!(TWO_M52, pow2(-52));
        assert_eq!(TWO_M24, pow2(-24));
        // u_star values are exact sums.
        let f16 = u_star(FloatFormat::F16);
        assert_eq!(f16 - pow2(-11) - pow2(-24), pow2(-35));
        let bf16 = u_star(FloatFormat::BF16);
        assert_eq!(bf16 - pow2(-8) - pow2(-24), pow2(-32));
    }

    #[test]
    fn qmm_rust_gate_accepts_an_exact_result_and_rejects_a_bound_violation() {
        // K = 64, n = 21 (qmv_quad), Phi = 1, y1 exact.
        let (pass, _, b_lo) = g_qmm_rust(0.5, 0.5, 1.0, 64, 21);
        assert!(pass);
        let u = pow2(-24);
        let gamma = 21.0 * u / (1.0 - 21.0 * u);
        assert!(b_lo < gamma && b_lo > gamma * 0.999_999);
        // A distance of 21u (< gamma_21) passes; 22u (> gamma_21) fails.
        let at = |d: f64| g_qmm_rust((0.5 + d) as f32, 0.5, 1.0, 64, 21).0;
        assert!(at(21.0 * u));
        assert!(!at(22.0 * u));
        // NaN never passes.
        assert!(!g_qmm_rust(f32::NAN, 0.5, 1.0, 64, 21).0);
        // Phi = 0: only an exact zero passes.
        assert!(g_qmm_rust(-0.0, 0.0, 0.0, 64, 21).0);
        assert!(!g_qmm_rust(f32::from_bits(1), 0.0, 0.0, 64, 21).0);
    }

    #[test]
    fn dq_rust_gate() {
        // F32: P = 3, b = 0.5, w = 3.5 exactly representable -> distance 0.
        let out = 3.5f32.to_bits();
        assert!(g_dq_rust(FloatFormat::F32, out, 3.0, 3.5).0);
        // One F32 ulp off at 3.5 (2^-22) exceeds u*(|P|+|w|)... 2^-24*6.5 < 2^-22? 6.5*2^-24 = 1.625*2^-22 > 2^-22, so passes.
        let out = f32::from_bits(3.5f32.to_bits() + 1).to_bits();
        assert!(g_dq_rust(FloatFormat::F32, out, 3.0, 3.5).0);
        // Two ulps (2^-21 = 2*2^-22 > 1.625*2^-22) fails.
        let out = f32::from_bits(3.5f32.to_bits() + 2).to_bits();
        assert!(!g_dq_rust(FloatFormat::F32, out, 3.0, 3.5).0);
    }

    #[test]
    fn cast_outcome_counts() {
        let inputs: Vec<u16> = (0..=0xFFFFu32).map(|v| v as u16).collect();
        let outputs: Vec<u32> = inputs
            .iter()
            .map(|&h| widen_to_f32_bits(FloatFormat::F16, h as u32))
            .collect();
        let o = g_cast(FloatFormat::F16, &inputs, &outputs);
        assert_eq!(o.gated_mismatches, 0);
        assert_eq!(o.gated_patterns, 65536 - 2 * 1023 - 2 - 2 * 1023);
        assert_eq!(o.recorded_subnormal, 2 * 1023);
        assert_eq!(o.recorded_infinite, 2);
        assert_eq!(o.recorded_nan, 2 * 1023);
    }
}
