use quant::{decode_q8_0_matrix, Q8_0Error};

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

#[test]
fn matrix_decode_matches_independent_f32_bit_reference() {
    let mut encoded = Vec::new();
    encoded.extend_from_slice(&block(0x3800, [1; BLOCK_ELEMENTS]));
    encoded.extend_from_slice(&block(0x4000, [-2; BLOCK_ELEMENTS]));

    let mut decoded = [f32::NAN; 2 * BLOCK_ELEMENTS];
    decode_q8_0_matrix(&encoded, 2, BLOCK_ELEMENTS, &mut decoded).unwrap();

    let mut expected = [0.0_f32; 2 * BLOCK_ELEMENTS];
    expected[..BLOCK_ELEMENTS].fill(0.5);
    expected[BLOCK_ELEMENTS..].fill(-4.0);
    let actual_bits: Vec<u32> = decoded.iter().map(|value| value.to_bits()).collect();
    let expected_bits: Vec<u32> = expected.iter().map(|value| value.to_bits()).collect();
    assert_eq!(actual_bits, expected_bits);
}

#[test]
fn matrix_decode_rejects_truncation_without_partial_output() {
    let full = block(0x3c00, [1; BLOCK_ELEMENTS]);
    let mut decoded = [17.0_f32; 2 * BLOCK_ELEMENTS];
    let error = decode_q8_0_matrix(
        &full[..full.len() - 1],
        2,
        BLOCK_ELEMENTS,
        &mut decoded,
    )
    .unwrap_err();
    assert_eq!(
        error,
        Q8_0Error::EncodedLengthMismatch {
            expected: 2 * BLOCK_BYTES,
            actual: BLOCK_BYTES - 1,
        }
    );
    assert_eq!(decoded, [17.0; 2 * BLOCK_ELEMENTS]);
}
