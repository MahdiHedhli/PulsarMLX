use quant::{decode_q6_k_matrix, Q6KError, Q6_K_BLOCK_BYTES};

const ELEMENTS: usize = 256;

fn pack_block(quants: &[i8; ELEMENTS], scale_bits: u16, scales: &[i8; 16]) -> [u8; Q6_K_BLOCK_BYTES] {
    let mut block = [0_u8; Q6_K_BLOCK_BYTES];
    let mut ql = [0_u8; 128];
    let mut qh = [0_u8; 64];
    for n in 0..2 {
        for l in 0..32 {
            let base = 128 * n;
            let values = [
                quants[base + l],
                quants[base + 32 + l],
                quants[base + 64 + l],
                quants[base + 96 + l],
            ];
            let packed = values.map(|value| (value + 32) as u8);
            ql[64 * n + l] = (packed[0] & 0x0f) | ((packed[2] & 0x0f) << 4);
            ql[64 * n + 32 + l] = (packed[1] & 0x0f) | ((packed[3] & 0x0f) << 4);
            qh[32 * n + l] = (packed[0] >> 4)
                | ((packed[1] >> 4) << 2)
                | ((packed[2] >> 4) << 4)
                | ((packed[3] >> 4) << 6);
        }
    }
    block[0..128].copy_from_slice(&ql);
    block[128..192].copy_from_slice(&qh);
    block[192..208].copy_from_slice(&scales.map(|scale| scale as u8));
    block[208..210].copy_from_slice(&scale_bits.to_le_bytes());
    block
}

#[test]
fn matrix_decode_matches_independent_logical_q6_k_reference_bits() {
    let quants = std::array::from_fn(|index| (index as i8 & 63) - 32);
    let scales = std::array::from_fn(|index| if index % 2 == 0 { 1 } else { -2 });
    let block = pack_block(&quants, 0x3800, &scales);
    let mut decoded = [f32::NAN; ELEMENTS];
    decode_q6_k_matrix(&block, 1, ELEMENTS, &mut decoded).unwrap();

    let expected: Vec<f32> = quants
        .iter()
        .enumerate()
        .map(|(index, &quantized)| 0.5 * scales[index / 16] as f32 * quantized as f32)
        .collect();
    let actual_bits: Vec<u32> = decoded.iter().map(|value| value.to_bits()).collect();
    let expected_bits: Vec<u32> = expected.iter().map(|value| value.to_bits()).collect();
    assert_eq!(actual_bits, expected_bits);
}

#[test]
fn matrix_decode_rejects_truncation_without_partial_output() {
    let quants = [0_i8; ELEMENTS];
    let scales = [1_i8; 16];
    let block = pack_block(&quants, 0x3c00, &scales);
    let mut decoded = [17.0_f32; ELEMENTS];
    let error = decode_q6_k_matrix(&block[..Q6_K_BLOCK_BYTES - 1], 1, ELEMENTS, &mut decoded)
        .unwrap_err();
    assert_eq!(
        error,
        Q6KError::EncodedLengthMismatch {
            expected: Q6_K_BLOCK_BYTES,
            actual: Q6_K_BLOCK_BYTES - 1,
        }
    );
    assert_eq!(decoded, [17.0; ELEMENTS]);
}

#[test]
fn matrix_decode_rejects_nonfinite_scale_without_partial_output() {
    let quants = [1_i8; ELEMENTS];
    let scales = [1_i8; 16];
    let block = pack_block(&quants, 0x7c00, &scales);
    let mut decoded = [19.0_f32; ELEMENTS];
    assert_eq!(
        decode_q6_k_matrix(&block, 1, ELEMENTS, &mut decoded),
        Err(Q6KError::NonFiniteScale { block_index: 0 })
    );
    assert_eq!(decoded, [19.0; ELEMENTS]);
}

#[test]
fn matrix_decode_rejects_invalid_shape_and_output_size() {
    let quants = [0_i8; ELEMENTS];
    let scales = [1_i8; 16];
    let block = pack_block(&quants, 0x3c00, &scales);
    let mut decoded = [0.0_f32; ELEMENTS];
    assert_eq!(
        decode_q6_k_matrix(&block, 1, ELEMENTS - 1, &mut decoded).unwrap_err(),
        Q6KError::RowWidthNotDivisible {
            row_width: ELEMENTS - 1
        }
    );
    assert_eq!(
        decode_q6_k_matrix(&block, 1, ELEMENTS, &mut decoded[..ELEMENTS - 1]).unwrap_err(),
        Q6KError::DestinationLengthMismatch {
            expected: ELEMENTS,
            actual: ELEMENTS - 1,
        }
    );
}
