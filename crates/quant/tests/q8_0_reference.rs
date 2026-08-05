use quant::{decode_q8_0_row, matvec_q8_0, Q8_0Error};

const BLOCK_ELEMENTS: usize = 32;
const BLOCK_BYTES: usize = 34;

fn block(scale_bits: u16, quants: [i8; BLOCK_ELEMENTS]) -> [u8; BLOCK_BYTES] {
    let mut encoded = [0_u8; BLOCK_BYTES];
    encoded[..2].copy_from_slice(&scale_bits.to_le_bytes());
    for (destination, quant) in encoded[2..].iter_mut().zip(quants) {
        *destination = quant as u8;
    }
    encoded
}

fn sparse_quants(entries: &[(usize, i8)]) -> [i8; BLOCK_ELEMENTS] {
    let mut quants = [0_i8; BLOCK_ELEMENTS];
    for &(index, value) in entries {
        quants[index] = value;
    }
    quants
}

#[test]
fn decodes_zero_scale_and_all_zero_quants_exactly() {
    let encoded = block(0x0000, [0; BLOCK_ELEMENTS]);
    let mut decoded = [7.0_f32; BLOCK_ELEMENTS];

    decode_q8_0_row(&encoded, BLOCK_ELEMENTS, &mut decoded).unwrap();

    assert_eq!(decoded, [0.0; BLOCK_ELEMENTS]);
}

#[test]
fn decodes_signed_values_and_extrema_from_a_hand_built_block() {
    // 0x3800 is binary16 0.5. The signed-byte interpretation must preserve
    // -128 rather than treating it as 128.
    let quants = sparse_quants(&[(0, -128), (1, -3), (2, 0), (3, 5), (31, 127)]);
    let encoded = block(0x3800, quants);
    let mut decoded = [0.0_f32; BLOCK_ELEMENTS];

    decode_q8_0_row(&encoded, BLOCK_ELEMENTS, &mut decoded).unwrap();

    let mut expected = [0.0_f32; BLOCK_ELEMENTS];
    expected[0] = -64.0;
    expected[1] = -1.5;
    expected[2] = 0.0;
    expected[3] = 2.5;
    expected[31] = 63.5;
    assert_eq!(decoded, expected);
}

#[test]
fn accepts_a_finite_negative_binary16_scale() {
    // 0xb400 is binary16 -0.25. GGUF stores the scale as ordinary binary16;
    // the strict v1 contract rejects non-finite scales, not finite negatives.
    let encoded = block(
        0xb400,
        sparse_quants(&[(0, -128), (1, -4), (2, 4), (31, 127)]),
    );
    let mut decoded = [0.0_f32; BLOCK_ELEMENTS];

    decode_q8_0_row(&encoded, BLOCK_ELEMENTS, &mut decoded).unwrap();

    assert_eq!(decoded[0], 32.0);
    assert_eq!(decoded[1], 1.0);
    assert_eq!(decoded[2], -1.0);
    assert_eq!(decoded[31], -31.75);
}

#[test]
fn applies_each_blocks_own_scale_and_index_range() {
    // 0x3800 is 0.5 and 0x4000 is 2.0. Distinct constant blocks expose both
    // stale-scale reuse and quant-index reset bugs.
    let mut encoded = Vec::new();
    encoded.extend_from_slice(&block(0x3800, [1; BLOCK_ELEMENTS]));
    encoded.extend_from_slice(&block(0x4000, [-1; BLOCK_ELEMENTS]));
    let mut decoded = [0.0_f32; 2 * BLOCK_ELEMENTS];

    decode_q8_0_row(&encoded, 2 * BLOCK_ELEMENTS, &mut decoded).unwrap();

    assert_eq!(&decoded[..BLOCK_ELEMENTS], &[0.5; BLOCK_ELEMENTS]);
    assert_eq!(&decoded[BLOCK_ELEMENTS..], &[-2.0; BLOCK_ELEMENTS]);
}

#[test]
fn scalar_matvec_uses_row_major_blocks_and_f32_logical_order() {
    // Two 64-element rows with four non-zero weights each. Products are
    // exactly representable, fixing the v1 accumulation rule to f32 in
    // increasing logical-element order without depending on the decoder.
    let mut encoded = Vec::new();
    encoded.extend_from_slice(&block(0x3800, sparse_quants(&[(0, 2), (31, -4)])));
    encoded.extend_from_slice(&block(0x4000, sparse_quants(&[(0, 3), (31, -1)])));
    encoded.extend_from_slice(&block(0xbc00, sparse_quants(&[(0, 2), (31, -4)])));
    encoded.extend_from_slice(&block(0x3400, sparse_quants(&[(0, 8), (31, -8)])));

    let mut activation = [0.0_f32; 2 * BLOCK_ELEMENTS];
    activation[0] = 3.0;
    activation[31] = 5.0;
    activation[32] = -2.0;
    activation[63] = 7.0;
    let mut destination = [99.0_f32; 2];

    matvec_q8_0(
        &encoded,
        2,
        2 * BLOCK_ELEMENTS,
        &activation,
        &mut destination,
    )
    .unwrap();

    // row 0: (1*3) + (-2*5) + (6*-2) + (-2*7) = -33
    // row 1: (-2*3) + (4*5) + (2*-2) + (-2*7) = -4
    assert_eq!(destination, [-33.0, -4.0]);
}

#[test]
fn decode_rejects_zero_or_non_block_divisible_width_before_writing() {
    for row_width in [0, BLOCK_ELEMENTS - 1, BLOCK_ELEMENTS + 1] {
        let encoded = block(0x3c00, [1; BLOCK_ELEMENTS]);
        let mut destination = [17.0_f32; BLOCK_ELEMENTS];

        let error = decode_q8_0_row(&encoded, row_width, &mut destination).unwrap_err();

        if row_width == 0 {
            assert_eq!(error, Q8_0Error::ZeroRowWidth);
        } else {
            assert_eq!(error, Q8_0Error::RowWidthNotDivisible { row_width });
        }
        assert_eq!(destination, [17.0; BLOCK_ELEMENTS]);
    }
}

#[test]
fn decode_requires_the_exact_encoded_byte_count() {
    for actual in [BLOCK_BYTES - 1, BLOCK_BYTES + 1] {
        let encoded = vec![0_u8; actual];
        let mut destination = [23.0_f32; BLOCK_ELEMENTS];

        let error = decode_q8_0_row(&encoded, BLOCK_ELEMENTS, &mut destination).unwrap_err();

        assert_eq!(
            error,
            Q8_0Error::EncodedLengthMismatch {
                expected: BLOCK_BYTES,
                actual,
            }
        );
        assert_eq!(destination, [23.0; BLOCK_ELEMENTS]);
    }
}

#[test]
fn matvec_requires_the_exact_encoded_byte_count() {
    let expected = 2 * BLOCK_BYTES;
    let activation = [0.0_f32; BLOCK_ELEMENTS];
    for actual in [expected - 1, expected + 1] {
        let encoded = vec![0_u8; actual];
        let mut destination = [29.0_f32; 2];

        let error =
            matvec_q8_0(&encoded, 2, BLOCK_ELEMENTS, &activation, &mut destination).unwrap_err();

        assert_eq!(error, Q8_0Error::EncodedLengthMismatch { expected, actual });
        assert_eq!(destination, [29.0; 2]);
    }
}

#[test]
fn checked_block_and_matrix_arithmetic_rejects_overflow() {
    let largest_divisible_width = usize::MAX - (usize::MAX % BLOCK_ELEMENTS);
    let mut decode_destination = [];
    assert_eq!(
        decode_q8_0_row(&[], largest_divisible_width, &mut decode_destination).unwrap_err(),
        Q8_0Error::ArithmeticOverflow
    );

    // rows * width still fits here, but rows * encoded-row-bytes does not.
    let rows = usize::MAX / 33;
    let mut matvec_destination = [];
    assert_eq!(
        matvec_q8_0(&[], rows, BLOCK_ELEMENTS, &[], &mut matvec_destination).unwrap_err(),
        Q8_0Error::ArithmeticOverflow
    );
}

#[test]
fn decode_requires_the_exact_destination_size() {
    let encoded = block(0x3c00, [1; BLOCK_ELEMENTS]);
    for actual in [BLOCK_ELEMENTS - 1, BLOCK_ELEMENTS + 1] {
        let mut destination = vec![31.0_f32; actual];

        let error = decode_q8_0_row(&encoded, BLOCK_ELEMENTS, &mut destination).unwrap_err();

        assert_eq!(
            error,
            Q8_0Error::DestinationLengthMismatch {
                expected: BLOCK_ELEMENTS,
                actual,
            }
        );
        assert_eq!(destination, vec![31.0; actual]);
    }
}

#[test]
fn matvec_requires_exact_activation_and_destination_sizes() {
    let encoded = block(0x3c00, [1; BLOCK_ELEMENTS]);

    for actual in [BLOCK_ELEMENTS - 1, BLOCK_ELEMENTS + 1] {
        let activation = vec![0.0_f32; actual];
        let mut destination = [37.0_f32; 1];
        let error =
            matvec_q8_0(&encoded, 1, BLOCK_ELEMENTS, &activation, &mut destination).unwrap_err();
        assert_eq!(
            error,
            Q8_0Error::ActivationLengthMismatch {
                expected: BLOCK_ELEMENTS,
                actual,
            }
        );
        assert_eq!(destination, [37.0]);
    }

    for actual in [1, 3] {
        let encoded = [
            block(0x3c00, [1; BLOCK_ELEMENTS]),
            block(0x3c00, [1; BLOCK_ELEMENTS]),
        ]
        .concat();
        let activation = [0.0_f32; BLOCK_ELEMENTS];
        let mut destination = vec![41.0_f32; actual];
        let error =
            matvec_q8_0(&encoded, 2, BLOCK_ELEMENTS, &activation, &mut destination).unwrap_err();
        assert_eq!(
            error,
            Q8_0Error::DestinationLengthMismatch {
                expected: 2,
                actual,
            }
        );
        assert_eq!(destination, vec![41.0; actual]);
    }
}

#[test]
fn decode_rejects_non_finite_scales_without_partial_output() {
    for scale_bits in [0x7c00_u16, 0xfc00, 0x7e00] {
        let mut encoded = Vec::new();
        encoded.extend_from_slice(&block(0x3c00, [1; BLOCK_ELEMENTS]));
        encoded.extend_from_slice(&block(scale_bits, [0; BLOCK_ELEMENTS]));
        let mut destination = [43.0_f32; 2 * BLOCK_ELEMENTS];

        let error = decode_q8_0_row(&encoded, 2 * BLOCK_ELEMENTS, &mut destination).unwrap_err();

        assert_eq!(error, Q8_0Error::NonFiniteScale { block_index: 1 });
        assert_eq!(destination, [43.0; 2 * BLOCK_ELEMENTS]);
    }
}

#[test]
fn matvec_rejects_non_finite_activations_without_writing() {
    let encoded = block(0x3c00, [1; BLOCK_ELEMENTS]);
    for value in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY] {
        let mut activation = [0.0_f32; BLOCK_ELEMENTS];
        activation[7] = value;
        let mut destination = [47.0_f32; 1];

        let error =
            matvec_q8_0(&encoded, 1, BLOCK_ELEMENTS, &activation, &mut destination).unwrap_err();

        assert_eq!(error, Q8_0Error::NonFiniteActivation { index: 7 });
        assert_eq!(destination, [47.0]);
    }
}

#[test]
fn matvec_rejects_a_non_finite_accumulation_result() {
    // 0x7bff is the largest finite binary16 value (65504). All public inputs
    // are finite, but this product overflows f32 and must not become evidence.
    let encoded = block(0x7bff, sparse_quants(&[(0, 127)]));
    let mut activation = [0.0_f32; BLOCK_ELEMENTS];
    activation[0] = f32::MAX;
    let mut destination = [53.0_f32; 1];

    let error =
        matvec_q8_0(&encoded, 1, BLOCK_ELEMENTS, &activation, &mut destination).unwrap_err();

    assert_eq!(error, Q8_0Error::NonFiniteResult { row: 0 });
    assert_eq!(destination, [53.0]);
}
