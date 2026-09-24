//! Hand-computed cases for the Slice 2B binary64 R1 (`reference_qmm`).
//!
//! Every expected value below was worked out by hand from `w = s*q + b`,
//! `y = sum_k w_k * x_k` and `Phi = sum_k (|s|*q + |b|) * |x_k|`; the packed
//! words are written out literally where they are short, and otherwise built
//! by the small bit-setting packer below, which shares nothing with the file
//! under test.

use mlx_affine::reference_qmm::{
    dq_reference, qmm_reference, widen_bf16_bits, widen_f16_bits, widen_f32_bits, QmmMetadata,
    QmmReferenceError,
};

const F32_ONE: u32 = 0x3F80_0000;
const F32_MINUS_ONE: u32 = 0xBF80_0000;
const F32_HALF: u32 = 0x3F00_0000;
const F32_MINUS_QUARTER: u32 = 0xBE80_0000;
const F32_MINUS_HALF: u32 = 0xBF00_0000;
const F32_TWO_POW_32: u32 = 0x4F80_0000;
const F32_TWO_POW_MINUS_32: u32 = 0x2F80_0000;
const F32_MINUS_TWO_POW_32: u32 = 0xCF80_0000;
const F32_NEG_ZERO: u32 = 0x8000_0000;

const F16_ONE: u16 = 0x3C00;
const F16_TWO: u16 = 0x4000;
const F16_HALF: u16 = 0x3800;
const F16_MINUS_ONE: u16 = 0xBC00;
const F16_NEG_ZERO: u16 = 0x8000;

const BF16_ONE: u16 = 0x3F80;
const BF16_QUARTER: u16 = 0x3E80;
const BF16_MINUS_TWO: u16 = 0xC000;
const BF16_MINUS_HALF: u16 = 0xBF00;

/// Set code `j` at bits `[j*bits, j*bits + bits)` of a row stream, one bit at a time.
fn pack_row(codes: &[u32], bits: u32) -> Vec<u32> {
    let total_bits = codes.len() * bits as usize;
    assert_eq!(total_bits % 32, 0);
    let mut words = vec![0u32; total_bits / 32];
    for (j, code) in codes.iter().enumerate() {
        assert!(*code < (1 << bits));
        for bit in 0..bits as usize {
            if (code >> bit) & 1 == 1 {
                let position = j * bits as usize + bit;
                words[position / 32] |= 1 << (position % 32);
            }
        }
    }
    words
}

#[test]
fn four_bit_group_32_f16_literal_words() {
    // Codes 0..15 twice: word 0x76543210 holds codes 0..7, 0xFEDCBA98 codes 8..15.
    let w = [0x7654_3210, 0xFEDC_BA98, 0x7654_3210, 0xFEDC_BA98];
    let meta = QmmMetadata::F16 {
        scales: &[F16_HALF],
        biases: &[F16_MINUS_ONE],
    };
    let x = [F32_ONE; 32];
    let r = qmm_reference(&x, &w, meta, 1, 1, 32, 4, 32).unwrap();
    // sum q = 2 * 120 = 240; y = 0.5 * 240 - 32 = 88; Phi = 120 + 32 = 152.
    assert_eq!(r.y, vec![88.0]);
    assert_eq!(r.phi, vec![152.0]);
    assert_eq!((r.m, r.n), (1, 1));

    let d = dq_reference(&w, meta, 1, 32, 4, 32).unwrap();
    for j in 0..32 {
        let q = (j % 16) as f64;
        assert_eq!(d.p[j], 0.5 * q);
        assert_eq!(d.w[j], 0.5 * q - 1.0);
    }
}

#[test]
fn four_bit_two_groups_f16_selects_the_group_by_column() {
    // Every code 1. Group 0: s = 1, b = 0 -> w = 1. Group 1: s = 2, b = 1 -> w = 3.
    let w = [0x1111_1111u32; 8];
    let meta = QmmMetadata::F16 {
        scales: &[F16_ONE, F16_TWO],
        biases: &[0x0000, F16_ONE],
    };
    let x = [F32_ONE; 64];
    let r = qmm_reference(&x, &w, meta, 1, 1, 64, 4, 32).unwrap();
    assert_eq!(r.y, vec![32.0 + 96.0]);
    assert_eq!(r.phi, vec![128.0]);
    let d = dq_reference(&w, meta, 1, 64, 4, 32).unwrap();
    assert!(d.w[..32].iter().all(|v| *v == 1.0));
    assert!(d.w[32..].iter().all(|v| *v == 3.0));
}

#[test]
fn eight_bit_group_64_bf16_two_by_two() {
    // Row 0: every code 255, s = 0.25, b = -2 -> w = 61.75, |s|q + |b| = 65.75.
    // Row 1: code j, s = -0.5, b = 1 -> w = 1 - j/2, |s|q + |b| = 1 + j/2.
    let mut w = vec![0xFFFF_FFFFu32; 16];
    for word in 0..16u32 {
        let base = 4 * word;
        w.push(base | ((base + 1) << 8) | ((base + 2) << 16) | ((base + 3) << 24));
    }
    assert_eq!(w[16], 0x0302_0100);
    let meta = QmmMetadata::Bf16 {
        scales: &[BF16_QUARTER, BF16_MINUS_HALF],
        biases: &[BF16_MINUS_TWO, BF16_ONE],
    };
    // x row 0 = 1, x row 1 = -0.5.
    let mut x = vec![F32_ONE; 64];
    x.extend(std::iter::repeat_n(F32_MINUS_HALF, 64));
    let r = qmm_reference(&x, &w, meta, 2, 2, 64, 8, 64).unwrap();
    // sum_j j = 2016.
    assert_eq!(r.y, vec![3952.0, -944.0, -1976.0, 472.0]);
    assert_eq!(r.phi, vec![4208.0, 1072.0, 2104.0, 536.0]);

    let d = dq_reference(&w, meta, 2, 64, 8, 64).unwrap();
    assert!(d.w[..64].iter().all(|v| *v == 61.75));
    assert!(d.p[..64].iter().all(|v| *v == 63.75));
    for j in 0..64 {
        assert_eq!(d.w[64 + j], 1.0 - 0.5 * j as f64);
        assert_eq!(d.p[64 + j], -0.5 * j as f64);
    }
}

#[test]
fn four_bit_group_128_f32_cancels_to_exact_zero() {
    // Every code 15, s = 0.5, b = -0.25 -> w = 7.25; x alternates +1, -1.
    let w = [0xFFFF_FFFFu32; 16];
    let meta = QmmMetadata::F32 {
        scales: &[F32_HALF],
        biases: &[F32_MINUS_QUARTER],
    };
    let x: Vec<u32> = (0..128)
        .map(|t| if t % 2 == 0 { F32_ONE } else { F32_MINUS_ONE })
        .collect();
    let r = qmm_reference(&x, &w, meta, 1, 1, 128, 4, 128).unwrap();
    assert_eq!(r.y, vec![0.0]);
    assert_eq!(r.phi, vec![128.0 * 7.75]);
}

#[test]
fn sequential_order_is_k_ascending() {
    // w = (1, 1, 1, 0, ...) (s = 1, b = 0, codes 1,1,1,0...); x = (2^32, 2^-32, -2^32, 0...).
    // Exact y* = 2^-32. Sequentially, 2^32 + 2^-32 rounds to 2^32 (the addend is far
    // below half an ulp, 2^-21), and adding -2^32 leaves exactly 0. Any other order
    // that pairs the two large terms first would give 2^-32.
    let w = [0x0000_0111u32, 0, 0, 0];
    let meta = QmmMetadata::F32 {
        scales: &[F32_ONE],
        biases: &[0],
    };
    let mut x = vec![0u32; 32];
    x[0] = F32_TWO_POW_32;
    x[1] = F32_TWO_POW_MINUS_32;
    x[2] = F32_MINUS_TWO_POW_32;
    let r = qmm_reference(&x, &w, meta, 1, 1, 32, 4, 32).unwrap();
    assert_eq!(r.y, vec![0.0]);
    // Phi_hat: 2^32 + 2^-32 -> 2^32, + 2^32 = 2^33 (exact Phi = 2^33 + 2^-32).
    assert_eq!(r.phi, vec![2f64.powi(33)]);
    // The N-R1-SELF bound gamma64_{K+1} * Phi covers the 2^-32 error by a wide margin.
    let k_plus_1 = 33.0;
    assert!(2f64.powi(-32) <= k_plus_1 * 2f64.powi(-53) * 2f64.powi(33));
}

#[test]
fn signed_zeros_give_zero_and_zero_envelope() {
    // s = -0, b = -0: every w is -0 (q >= 1: -0 * q = -0; -0 + -0 = -0).
    let w = [0x1111_1111u32; 4];
    let meta = QmmMetadata::F16 {
        scales: &[F16_NEG_ZERO],
        biases: &[F16_NEG_ZERO],
    };
    let d = dq_reference(&w, meta, 1, 32, 4, 32).unwrap();
    assert!(d.w.iter().all(|v| *v == 0.0 && v.is_sign_negative()));
    let x = [F32_ONE; 32];
    let r = qmm_reference(&x, &w, meta, 1, 1, 32, 4, 32).unwrap();
    assert_eq!(r.y, vec![0.0]);
    assert_eq!(r.phi, vec![0.0]);

    // A row of x made of +0 and -0 against nonzero weights: y = 0, Phi = 0.
    let meta = QmmMetadata::F16 {
        scales: &[F16_HALF],
        biases: &[F16_MINUS_ONE],
    };
    let x: Vec<u32> = (0..32)
        .map(|t| if t % 2 == 0 { 0 } else { F32_NEG_ZERO })
        .collect();
    let r = qmm_reference(&x, &w, meta, 1, 1, 32, 4, 32).unwrap();
    assert_eq!(r.y, vec![0.0]);
    assert_eq!(r.phi, vec![0.0]);
}

#[test]
fn dequantize_f32_rounds_once_and_keeps_the_exact_product() {
    // s = 1 + 2^-23, q = 255, b = 2^40: P = 255 + 255 * 2^-23 is exact in binary64;
    // w = 2^40 + 255 + 255 * 2^-23, whose last part is below half an ulp (2^-13) of
    // 2^40, so w_hat = 2^40 + 255 after the single rounding of the addition.
    let w = [0xFFFF_FFFFu32; 8];
    let meta = QmmMetadata::F32 {
        scales: &[0x3F80_0001],
        biases: &[0x5380_0000],
    };
    let d = dq_reference(&w, meta, 1, 32, 8, 32).unwrap();
    let p = 255.0 + 255.0 * 2f64.powi(-23);
    assert!(d.p.iter().all(|v| *v == p));
    assert!(d.w.iter().all(|v| *v == 2f64.powi(40) + 255.0));
}

#[test]
fn three_bit_codes_straddle_words() {
    // 32 three-bit codes fill exactly three words; codes 10 and 21 straddle a boundary.
    let codes: Vec<u32> = (0..32).map(|j| j % 8).collect();
    let w = pack_row(&codes, 3);
    assert_eq!(w.len(), 3);
    let meta = QmmMetadata::Bf16 {
        scales: &[BF16_ONE],
        biases: &[0],
    };
    let d = dq_reference(&w, meta, 1, 32, 3, 32).unwrap();
    let expected: Vec<f64> = codes.iter().map(|q| f64::from(*q)).collect();
    assert_eq!(d.w, expected);
}

#[test]
fn packer_agrees_with_literal_words() {
    let codes: Vec<u32> = (0..16).collect();
    assert_eq!(pack_row(&codes, 4), vec![0x7654_3210, 0xFEDC_BA98]);
    let codes: Vec<u32> = vec![0, 1, 2, 3];
    assert_eq!(pack_row(&codes, 8), vec![0x0302_0100]);
}

#[test]
fn widening_is_exact_for_every_half_and_brain_half_pattern() {
    for pattern in 0..=u16::MAX {
        let sign = if pattern & 0x8000 != 0 { -1.0 } else { 1.0 };
        let exponent = i32::from((pattern >> 10) & 0x1F);
        let fraction = f64::from(pattern & 0x3FF);
        let expected = match exponent {
            0x1F => None,
            0 => Some(sign * fraction * 2f64.powi(-24)),
            _ => Some(sign * (1024.0 + fraction) * 2f64.powi(exponent - 25)),
        };
        let got = widen_f16_bits(pattern);
        assert_eq!(got, expected, "f16 {pattern:#06x}");
        if let Some(value) = got {
            assert_eq!(value.is_sign_negative(), pattern & 0x8000 != 0);
        }

        let single = f32::from_bits(u32::from(pattern) << 16);
        let got = widen_bf16_bits(pattern);
        if single.is_finite() {
            assert_eq!(got.map(f64::to_bits), Some(f64::from(single).to_bits()));
        } else {
            assert_eq!(got, None, "bf16 {pattern:#06x}");
        }
    }
    assert_eq!(
        widen_f32_bits(F32_NEG_ZERO).map(f64::to_bits),
        Some((-0.0f64).to_bits())
    );
    assert_eq!(widen_f32_bits(0x7F80_0000), None);
    assert_eq!(widen_f32_bits(0x7FC0_0000), None);
    assert_eq!(widen_f32_bits(0x0000_0001), Some(2f64.powi(-149)));
}

#[test]
fn malformed_inputs_are_refused() {
    let w = [0u32; 4];
    let f16 = QmmMetadata::F16 {
        scales: &[F16_ONE],
        biases: &[0],
    };
    let x = [F32_ONE; 32];
    assert_eq!(
        qmm_reference(&x, &w, f16, 1, 1, 32, 0, 32),
        Err(QmmReferenceError::Bits(0))
    );
    assert_eq!(
        qmm_reference(&x, &w, f16, 1, 1, 32, 9, 32),
        Err(QmmReferenceError::Bits(9))
    );
    assert!(matches!(
        qmm_reference(&x, &w, f16, 1, 1, 32, 4, 64),
        Err(QmmReferenceError::Shape(_))
    ));
    assert!(matches!(
        qmm_reference(&x[..31], &w, f16, 1, 1, 32, 4, 32),
        Err(QmmReferenceError::Shape(_))
    ));
    assert!(matches!(
        qmm_reference(&x, &w[..3], f16, 1, 1, 32, 4, 32),
        Err(QmmReferenceError::Shape(_))
    ));
    assert!(matches!(
        qmm_reference(&[], &w, f16, 0, 1, 32, 4, 32),
        Err(QmmReferenceError::Shape(_))
    ));
    assert!(matches!(
        dq_reference(&[], f16, 0, 32, 4, 32),
        Err(QmmReferenceError::Shape(_))
    ));
    let mut nan_x = x;
    nan_x[5] = 0x7FC0_0000;
    assert_eq!(
        qmm_reference(&nan_x, &w, f16, 1, 1, 32, 4, 32),
        Err(QmmReferenceError::NonFinite {
            tensor: "x",
            index: 5
        })
    );
    let inf_scale = QmmMetadata::Bf16 {
        scales: &[0x7F80],
        biases: &[0],
    };
    assert_eq!(
        dq_reference(&w, inf_scale, 1, 32, 4, 32),
        Err(QmmReferenceError::NonFinite {
            tensor: "scales",
            index: 0
        })
    );
    let short = QmmMetadata::F32 {
        scales: &[F32_ONE],
        biases: &[],
    };
    assert!(matches!(
        dq_reference(&w, short, 1, 32, 4, 32),
        Err(QmmReferenceError::Shape(_))
    ));
}
