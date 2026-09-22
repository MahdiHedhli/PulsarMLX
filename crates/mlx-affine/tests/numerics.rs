//! R3 against R1, under the frozen contract in
//! `specs/020-mlx-safetensors-affine/contracts/numerics-v1.json`.
//!
//! Two sources of cases: the golden fixture -- the adopted nine-case baseline
//! plus the extended cases that close its multi-group, group-128, 8-bit and
//! F32-metadata gaps -- and seeded randomized rows, which cover geometries no
//! fixture happens to contain.
//!
//! Checks C-CODES, C-DEQUANT-HALF and C-DEQUANT-SINGLE of the contract are
//! asserted by name so that a reader can follow one to the other.

use std::path::PathBuf;

use mlx_affine::decode::{dequantize_rows, unpack_codes, ScaleDtype};
use mlx_affine::reference::{
    dequantize_rows_half, dequantize_rows_single, half_to_f64, round_to_f32,
    unpack_codes_reference, MetadataFormat,
};
use mlx_affine::spec::{Bits, GroupSize, Mode, QuantSpec};
use serde_json::Value;

fn repository(relative: &str) -> PathBuf {
    [env!("CARGO_MANIFEST_DIR"), "../..", relative]
        .iter()
        .collect()
}

fn golden() -> Value {
    let path = repository("fixtures/safetensors/golden-affine-dequant-v1/golden.json");
    let text = std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{}: {e}", path.display()));
    serde_json::from_str(&text).unwrap()
}

fn integers(value: &Value, key: &str) -> Vec<u64> {
    value[key]
        .as_array()
        .unwrap()
        .iter()
        .map(|entry| entry.as_u64().unwrap())
        .collect()
}

fn spec(bits: u32, group: u32) -> QuantSpec {
    QuantSpec::new(
        Bits::from_u32(bits).unwrap(),
        GroupSize::from_u32(group).unwrap(),
        Mode::Affine,
    )
}

/// An `f32` bit pattern to the `f64` it denotes, exactly.
fn f32_bits_to_f64(bits: u32) -> f64 {
    f64::from(f32::from_bits(bits))
}

// --- the golden fixture ---------------------------------------------------

#[test]
fn r1_reproduces_every_golden_case_exactly() {
    let fixture = golden();
    let mut checked = 0usize;
    for block in ["adopted", "extended"] {
        for (name, case) in fixture[block].as_object().unwrap() {
            let words: Vec<u32> = integers(case, "words")
                .into_iter()
                .map(|w| w as u32)
                .collect();
            let scales: Vec<u32> = integers(case, "scales")
                .into_iter()
                .map(|w| w as u32)
                .collect();
            let biases: Vec<u32> = integers(case, "biases")
                .into_iter()
                .map(|w| w as u32)
                .collect();
            let expected = integers(case, "dequant");
            let rows = case["rows"].as_u64().unwrap() as usize;
            let cols = case["cols"].as_u64().unwrap() as usize;
            let bits = case["bits"].as_u64().unwrap() as u32;
            let group = case["group"].as_u64().unwrap() as u32;

            let mut out = vec![0f64; rows * cols];
            dequantize_rows_single(&words, &scales, &biases, bits, group, rows, cols, &mut out)
                .unwrap_or_else(|e| panic!("{block}/{name}: {e}"));
            for (index, value) in out.iter().enumerate() {
                let got = (*value as f32).to_bits() as u64;
                assert_eq!(
                    got, expected[index],
                    "{block}/{name}[{index}]: R1 does not reproduce the stored value"
                );
            }
            checked += 1;
        }
    }
    // Seven adopted quantized cases and eight extended ones.
    assert_eq!(checked, 15);
}

#[test]
fn r3_matches_r1_exactly_on_every_admitted_golden_case() {
    let fixture = golden();
    let mut admitted = 0usize;
    let mut refused = 0usize;
    for block in ["adopted", "extended"] {
        for (name, case) in fixture[block].as_object().unwrap() {
            let bits = case["bits"].as_u64().unwrap() as u32;
            let group = case["group"].as_u64().unwrap() as u32;
            let Ok(bits_enum) = Bits::from_u32(bits) else {
                // 2, 3 and 6 bits: the production decoder refuses them by
                // design, and the reference still decodes them. That is the
                // fail-closed behaviour, demonstrated rather than asserted in
                // prose.
                refused += 1;
                continue;
            };
            let spec = QuantSpec::new(bits_enum, GroupSize::from_u32(group).unwrap(), Mode::Affine);
            let words: Vec<u32> = integers(case, "words")
                .into_iter()
                .map(|w| w as u32)
                .collect();
            let scale_bits: Vec<u32> = integers(case, "scales")
                .into_iter()
                .map(|w| w as u32)
                .collect();
            let bias_bits: Vec<u32> = integers(case, "biases")
                .into_iter()
                .map(|w| w as u32)
                .collect();
            let rows = case["rows"].as_u64().unwrap() as usize;
            let cols = case["cols"].as_u64().unwrap() as usize;
            let dtype = case["metadata_dtype"].as_str().unwrap();

            // C-CODES: the unpacked codes agree exactly.
            let mut r3_codes = vec![0u8; rows * cols];
            unpack_codes(&words, bits_enum, &mut r3_codes).unwrap();
            let mut r1_codes = vec![0u32; rows * cols];
            unpack_codes_reference(&words, bits, rows, cols, &mut r1_codes).unwrap();
            for (index, code) in r1_codes.iter().enumerate() {
                assert_eq!(
                    u32::from(r3_codes[index]),
                    *code,
                    "C-CODES {block}/{name}[{index}]"
                );
            }

            // R1 in binary64 from the stored bit patterns.
            let mut r1 = vec![0f64; rows * cols];
            dequantize_rows_single(
                &words,
                &scale_bits,
                &bias_bits,
                bits,
                group,
                rows,
                cols,
                &mut r1,
            )
            .unwrap();

            // R3 from the bytes a shard would hold, in the declared dtype.
            let (scale_dtype, scale_bytes, bias_bytes) =
                stored_metadata(dtype, &scale_bits, &bias_bits);
            let mut r3 = vec![0f32; rows * cols];
            dequantize_rows(
                "test",
                &words,
                &scale_bytes,
                &bias_bytes,
                scale_dtype,
                spec,
                rows,
                &mut r3,
            )
            .unwrap();

            for (index, value) in r1.iter().enumerate() {
                assert!(
                    value.is_finite(),
                    "{block}/{name}[{index}]: R1 is not finite"
                );
                if scale_dtype.is_half() {
                    // C-DEQUANT-HALF: exact.
                    assert_eq!(
                        r3[index].to_bits(),
                        (*value as f32).to_bits(),
                        "C-DEQUANT-HALF {block}/{name}[{index}]: R3 {} vs round_to_f32(R1) {}",
                        r3[index],
                        round_to_f32(*value)
                    );
                } else {
                    // C-DEQUANT-SINGLE: the derived two-rounding bound.
                    let row = index / cols;
                    let group = row * (cols / group as usize) + (index % cols) / group as usize;
                    let product = f32_bits_to_f64(scale_bits[group]) * f64::from(r1_codes[index]);
                    assert_within_single_bound(
                        r3[index],
                        *value,
                        product,
                        &format!("C-DEQUANT-SINGLE {block}/{name}[{index}]"),
                    );
                }
            }
            admitted += 1;
        }
    }
    assert_eq!(
        refused, 3,
        "2-, 3- and 6-bit cases must be refused by the decoder"
    );
    assert_eq!(admitted, 12);
}

/// Re-encode binary32 bit patterns as the bytes a shard would store for the
/// declared metadata dtype. For BF16 and F16 the values are exact in that
/// format by construction, which the fixture's own checker asserts.
fn stored_metadata(dtype: &str, scales: &[u32], biases: &[u32]) -> (ScaleDtype, Vec<u8>, Vec<u8>) {
    match dtype {
        "F32" => (
            ScaleDtype::F32,
            scales.iter().flat_map(|b| b.to_le_bytes()).collect(),
            biases.iter().flat_map(|b| b.to_le_bytes()).collect(),
        ),
        "BF16" => (
            ScaleDtype::Bf16,
            scales
                .iter()
                .flat_map(|b| (((*b) >> 16) as u16).to_le_bytes())
                .collect(),
            biases
                .iter()
                .flat_map(|b| (((*b) >> 16) as u16).to_le_bytes())
                .collect(),
        ),
        "F16" => (
            ScaleDtype::F16,
            scales
                .iter()
                .flat_map(|b| f32_to_f16_bits(f32::from_bits(*b)).to_le_bytes())
                .collect(),
            biases
                .iter()
                .flat_map(|b| f32_to_f16_bits(f32::from_bits(*b)).to_le_bytes())
                .collect(),
        ),
        other => panic!("unknown metadata dtype {other}"),
    }
}

/// Round-to-nearest-even binary32 to binary16. Used only to lay out fixture
/// metadata as a shard would store it; values reaching it are exact in f16.
fn f32_to_f16_bits(value: f32) -> u16 {
    let bits = value.to_bits();
    let sign = ((bits >> 16) & 0x8000) as u16;
    let exponent = ((bits >> 23) & 0xFF) as i32;
    let mantissa = bits & 0x007F_FFFF;
    if exponent == 0xFF {
        return sign | 0x7C00 | if mantissa != 0 { 0x0200 } else { 0 };
    }
    let unbiased = exponent - 127;
    if unbiased > 15 {
        return sign | 0x7C00;
    }
    if unbiased >= -14 {
        let half_exponent = ((unbiased + 15) as u16) << 10;
        let half_mantissa = (mantissa >> 13) as u16;
        assert_eq!(
            mantissa & 0x1FFF,
            0,
            "value {value} is not exact in binary16"
        );
        return sign | half_exponent | half_mantissa;
    }
    if unbiased >= -24 {
        let significand = mantissa | 0x0080_0000;
        let shift = (-unbiased - 14) as u32;
        assert_eq!(
            significand & ((1 << (13 + shift)) - 1),
            0,
            "value {value} is not exact in binary16"
        );
        return sign | ((significand >> (13 + shift)) as u16);
    }
    assert_eq!(
        bits & 0x7FFF_FFFF,
        0,
        "value {value} is not exact in binary16"
    );
    sign
}

/// C-DEQUANT-SINGLE's bound: half a binary32 ulp at the magnitude of the
/// product, plus half a binary32 ulp at the magnitude of the result, plus the
/// second-order term. The product term is the one that matters: when the bias
/// nearly cancels the product, the result is far smaller than the product and
/// a bound stated in ulps of the result would not hold.
fn assert_within_single_bound(candidate: f32, reference: f64, product: f64, label: &str) {
    let difference = (f64::from(candidate) - reference).abs();
    let unit = 2f64.powi(-24);
    let bound = unit * (product.abs() + reference.abs()) * (1.0 + unit);
    assert!(
        difference <= bound,
        "{label}: |{candidate} - {reference}| = {difference} exceeds the contract bound {bound} \
         (product {product})"
    );
}

// --- randomized rows ------------------------------------------------------

/// A deterministic 64-bit LCG, so the randomized qualification is reproducible
/// from the seed alone and depends on no external crate.
struct Lcg(u64);

impl Lcg {
    fn next(&mut self) -> u64 {
        self.0 = self
            .0
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        self.0
    }

    fn below(&mut self, bound: u32) -> u32 {
        (self.next() >> 33) as u32 % bound
    }
}

/// A bf16 value with a modest exponent, so no product or sum leaves the
/// binary32 normal range -- the precondition the contract states for
/// C-DEQUANT-HALF.
fn bounded_bf16(rng: &mut Lcg) -> u16 {
    let sign = (rng.next() & 1) as u32;
    // Exponents 118..=132 span roughly 2^-9 to 2^5.
    let exponent = 118 + rng.below(15);
    let mantissa = rng.below(128);
    (((sign << 31) | (exponent << 23) | (mantissa << 16)) >> 16) as u16
}

#[test]
fn r3_matches_r1_exactly_over_seeded_random_rows() {
    let mut rng = Lcg(0x5AFE_7E45_0020_0001);
    let mut cases = 0usize;
    let mut elements = 0usize;
    for bits in [4u32, 8] {
        for group in [32u32, 64, 128] {
            for groups_per_row in [1usize, 2, 4] {
                let spec = spec(bits, group);
                let rows = 1 + (rng.below(4) as usize);
                let columns = (group as usize) * groups_per_row;
                let per_word = spec.bits.codes_per_word() as usize;
                let packed_columns = columns / per_word;

                let words: Vec<u32> = (0..rows * packed_columns)
                    .map(|_| rng.next() as u32)
                    .collect();
                let metadata = rows * groups_per_row;
                let scale_bits: Vec<u16> = (0..metadata).map(|_| bounded_bf16(&mut rng)).collect();
                let bias_bits: Vec<u16> = (0..metadata).map(|_| bounded_bf16(&mut rng)).collect();

                let mut r1 = vec![0f64; rows * columns];
                dequantize_rows_half(
                    &words,
                    &scale_bits,
                    &bias_bits,
                    MetadataFormat::BrainHalf,
                    bits,
                    group,
                    rows,
                    columns,
                    &mut r1,
                )
                .unwrap();

                let scale_bytes: Vec<u8> =
                    scale_bits.iter().flat_map(|b| b.to_le_bytes()).collect();
                let bias_bytes: Vec<u8> = bias_bits.iter().flat_map(|b| b.to_le_bytes()).collect();
                let mut r3 = vec![0f32; rows * columns];
                dequantize_rows(
                    "test",
                    &words,
                    &scale_bytes,
                    &bias_bytes,
                    ScaleDtype::Bf16,
                    spec,
                    rows,
                    &mut r3,
                )
                .unwrap();

                let mut r3_codes = vec![0u8; rows * columns];
                unpack_codes(&words, spec.bits, &mut r3_codes).unwrap();
                let mut r1_codes = vec![0u32; rows * columns];
                unpack_codes_reference(&words, bits, rows, columns, &mut r1_codes).unwrap();

                for index in 0..rows * columns {
                    assert_eq!(u32::from(r3_codes[index]), r1_codes[index], "C-CODES");
                    assert!(r1[index].is_finite());
                    assert!(
                        r3[index] == 0.0 || r3[index].abs() >= f64::from(f32::MIN_POSITIVE) as f32,
                        "precondition: a subnormal result would void the exactness argument"
                    );
                    assert_eq!(
                        r3[index].to_bits(),
                        (r1[index] as f32).to_bits(),
                        "C-DEQUANT-HALF at bits={bits} group={group} groups_per_row={groups_per_row} index={index}"
                    );
                }
                cases += 1;
                elements += rows * columns;
            }
        }
    }
    assert_eq!(cases, 18);
    assert!(elements > 5000, "{elements} elements is too thin a sample");
}

#[test]
fn the_two_half_widenings_agree_on_every_bit_pattern() {
    // R1 decodes binary16 by hand in binary64, R3 by bit surgery in binary32.
    // They were written separately; over all 65,536 patterns they must agree.
    for raw in 0u32..=0xFFFF {
        let bits = raw as u16;
        let reference = half_to_f64(bits);
        let production = mlx_affine::decode::half_to_f32(bits);
        if reference.is_nan() {
            assert!(production.is_nan(), "{bits:#06x}");
            continue;
        }
        assert_eq!(
            f64::from(production),
            reference,
            "{bits:#06x}: R3 {production} vs R1 {reference}"
        );
    }
}

#[test]
fn the_exactness_argument_is_stated_where_it_can_be_checked() {
    // The contract's C-DEQUANT-HALF justification rests on: a bf16 or f16
    // significand fits in 11 bits, a code fits in 8, so their product fits in
    // 19 and is exact in binary32. Assert the two premises rather than trust
    // the prose.
    assert_eq!(Bits::Eight.max_code(), 255);
    assert_eq!(Bits::Four.max_code(), 15);
    assert_eq!(u32::BITS - Bits::Eight.max_code().leading_zeros(), 8);
    // Every bf16 value is a binary32 value with 16 zero low bits.
    for raw in [0x3F80u16, 0xBF80, 0x0001, 0x7F7F] {
        let widened = f32::from_bits(u32::from(raw) << 16);
        assert_eq!(widened.to_bits() & 0xFFFF, 0);
    }
}

// --- the qualified numerical domain (Round 2, Astra finding 5) ------------

/// Astra's concrete case: a finite BF16 triple whose binary64 value is finite
/// and whose binary32 product is not.
#[test]
fn a_finite_triple_whose_binary32_product_overflows_is_refused() {
    let max_bf16: u16 = 0x7F7F; // the largest finite bfloat16
    let scale = f32::from_bits(u32::from(max_bf16) << 16);
    assert!(scale.is_finite());
    assert!((scale * 2.0).is_infinite(), "the premise of this test");

    // One row of 32 columns at 8 bits, group 32: every code is 2, the scale is
    // the largest finite bf16 and the bias is its negation. R1 in binary64
    // says 3.3895e38, which is finite and perfectly representable in binary32.
    let words = vec![0x0202_0202u32; 8];
    let scales = max_bf16.to_le_bytes().to_vec();
    let biases = (max_bf16 | 0x8000).to_le_bytes().to_vec();

    let mut r1 = vec![0f64; 32];
    dequantize_rows_single(
        &words,
        &[scale.to_bits()],
        &[(-scale).to_bits()],
        8,
        32,
        1,
        32,
        &mut r1,
    )
    .unwrap();
    assert!(r1[0].is_finite(), "R1 stays finite: {}", r1[0]);
    assert_eq!(
        r1[0],
        f64::from(scale),
        "R1's value is representable in binary32"
    );

    // R3 refuses rather than returning the infinity its product would produce.
    let mut r3 = vec![0f32; 32];
    match dequantize_rows(
        "overflow",
        &words,
        &scales,
        &biases,
        ScaleDtype::Bf16,
        spec(8, 32),
        1,
        &mut r3,
    ) {
        Err(mlx_affine::AffineError::NonFiniteValue { module, row, index }) => {
            assert_eq!(module, "overflow");
            assert_eq!(row, 0);
            assert_eq!(index, 0);
        }
        other => panic!("unexpected {other:?}"),
    }
}

#[test]
fn the_reference_asserts_the_same_domain_as_the_candidate() {
    // An infinite stored scale is outside the domain for both arms, so both
    // refuse rather than one of them producing a number.
    let words = vec![0x1111_1111u32; 8];
    let infinite = f32::INFINITY.to_bits();
    let mut r1 = vec![0f64; 64];
    assert!(matches!(
        dequantize_rows_single(&words, &[infinite], &[0], 4, 64, 1, 64, &mut r1),
        Err(mlx_affine::reference::ReferenceError::NonFinite { row: 0, index: 0 })
    ));

    let mut r3 = vec![0f32; 64];
    let scales = f32::INFINITY.to_bits().to_le_bytes().to_vec();
    let biases = 0f32.to_bits().to_le_bytes().to_vec();
    assert!(matches!(
        dequantize_rows(
            "infinite",
            &words,
            &scales,
            &biases,
            ScaleDtype::F32,
            spec(4, 64),
            1,
            &mut r3
        ),
        Err(mlx_affine::AffineError::NonFiniteValue { .. })
    ));
}

#[test]
fn every_golden_intermediate_is_inside_the_qualified_domain() {
    // Round 1 said the preconditions were asserted on every fixture. They were
    // not: the golden test checked R1's finiteness and the randomized test
    // checked R3's final magnitude, but no test checked every product. This
    // one does, elementwise, for both arms.
    let fixture = golden();
    let mut products = 0usize;
    for block in ["adopted", "extended"] {
        for (name, case) in fixture[block].as_object().unwrap() {
            let bits = case["bits"].as_u64().unwrap() as u32;
            let group = case["group"].as_u64().unwrap() as u32;
            let words: Vec<u32> = integers(case, "words")
                .into_iter()
                .map(|w| w as u32)
                .collect();
            let scale_bits: Vec<u32> = integers(case, "scales")
                .into_iter()
                .map(|w| w as u32)
                .collect();
            let rows = case["rows"].as_u64().unwrap() as usize;
            let cols = case["cols"].as_u64().unwrap() as usize;
            let groups = cols / group as usize;
            let packed_columns = cols * bits as usize / 32;
            for row in 0..rows {
                let row_words = &words[row * packed_columns..(row + 1) * packed_columns];
                for column in 0..cols {
                    let code =
                        mlx_affine::reference::extract_code(row_words, bits, column).unwrap();
                    let scale = f32_bits_to_f64(scale_bits[row * groups + column / group as usize]);
                    let product = scale * f64::from(code);
                    assert!(
                        product.is_finite(),
                        "{block}/{name}[{row},{column}]: the product is not finite"
                    );
                    let as_f32 = product as f32;
                    assert!(
                        as_f32.is_finite(),
                        "{block}/{name}[{row},{column}]: the product leaves binary32"
                    );
                    products += 1;
                }
            }
        }
    }
    assert!(products > 2000, "only {products} products were checked");
}
