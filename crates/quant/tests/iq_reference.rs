use quant::cpu_dot_tables::{IQ2XXS_GRID, IQ3XXS_GRID};
use quant::{
    decode_iq2_xxs_matrix, decode_iq3_xxs_matrix, IQXXSError, IQ2_XXS_BLOCK_BYTES,
    IQ3_XXS_BLOCK_BYTES,
};

const VALUES: usize = 256;

fn set_f16_one(block: &mut [u8]) {
    block[..2].copy_from_slice(&0x3c00_u16.to_le_bytes());
}

fn pack_iq2_block() -> [u8; IQ2_XXS_BLOCK_BYTES] {
    let mut block = [0_u8; IQ2_XXS_BLOCK_BYTES];
    set_f16_one(&mut block);
    for group in 0..8 {
        let base = 2 + group * 8;
        let aux0 = (group as u32)
            | (((group + 1) as u32) << 8)
            | (((group + 2) as u32) << 16)
            | (((group + 3) as u32) << 24);
        let aux1 = (1_u32 << 28) | 0x01 | (0x02 << 7) | (0x04 << 14) | (0x08 << 21);
        block[base..base + 4].copy_from_slice(&aux0.to_le_bytes());
        block[base + 4..base + 8].copy_from_slice(&aux1.to_le_bytes());
    }
    block
}

fn pack_iq3_block() -> [u8; IQ3_XXS_BLOCK_BYTES] {
    let mut block = [0_u8; IQ3_XXS_BLOCK_BYTES];
    set_f16_one(&mut block);
    for group in 0..8 {
        for pair in 0..4 {
            block[2 + group * 8 + pair * 2] = (group + pair) as u8;
            block[3 + group * 8 + pair * 2] = (group + pair + 1) as u8;
        }
        let aux = (2_u32 << 28) | 0x01 | (0x02 << 7) | (0x04 << 14) | (0x08 << 21);
        let base = 66 + group * 4;
        block[base..base + 4].copy_from_slice(&aux.to_le_bytes());
    }
    block
}

fn sign_mask(s7: u32) -> u32 {
    s7 | (((s7.count_ones() & 1) as u32) << 7)
}

fn expected_iq2(block: &[u8; IQ2_XXS_BLOCK_BYTES]) -> [f32; VALUES] {
    let mut expected = [0.0_f32; VALUES];
    let d = quant::f16_to_f32(u16::from_le_bytes([block[0], block[1]]));
    for group in 0..8 {
        let base = 2 + group * 8;
        let aux0 = u32::from_le_bytes(block[base..base + 4].try_into().unwrap());
        let aux1 = u32::from_le_bytes(block[base + 4..base + 8].try_into().unwrap());
        let scale = 0.125_f32 * d * (2 * (aux1 >> 28) + 1) as f32;
        for pair in 0..4 {
            let grid = IQ2XXS_GRID[((aux0 >> (8 * pair)) & 0xff) as usize].to_le_bytes();
            let signs = sign_mask((aux1 >> (7 * pair)) & 127);
            for i in 0..8 {
                let index = group * 32 + pair * 8 + i;
                expected[index] =
                    scale * (grid[i] as i8) as f32 * if signs & (1 << i) != 0 { -1.0 } else { 1.0 };
            }
        }
    }
    expected
}

fn expected_iq3(block: &[u8; IQ3_XXS_BLOCK_BYTES]) -> [f32; VALUES] {
    let mut expected = [0.0_f32; VALUES];
    let d = quant::f16_to_f32(u16::from_le_bytes([block[0], block[1]]));
    for group in 0..8 {
        let aux_start = 66 + group * 4;
        let aux = u32::from_le_bytes(block[aux_start..aux_start + 4].try_into().unwrap());
        let scale = d * (0.5 + (aux >> 28) as f32) * 0.5;
        for pair in 0..4 {
            let signs = sign_mask((aux >> (7 * pair)) & 127);
            let first = IQ3XXS_GRID[block[2 + group * 8 + pair * 2] as usize].to_le_bytes();
            let second = IQ3XXS_GRID[block[3 + group * 8 + pair * 2] as usize].to_le_bytes();
            for i in 0..4 {
                let index = group * 32 + pair * 8;
                expected[index + i] = scale
                    * (first[i] as i8) as f32
                    * if signs & (1 << i) != 0 { -1.0 } else { 1.0 };
                expected[index + 4 + i] = scale
                    * (second[i] as i8) as f32
                    * if signs & (1 << (4 + i)) != 0 {
                        -1.0
                    } else {
                        1.0
                    };
            }
        }
    }
    expected
}

#[test]
fn iq2_matrix_decode_matches_exact_f32_reference_bits() {
    let block = pack_iq2_block();
    let mut encoded = Vec::new();
    encoded.extend_from_slice(&block);
    encoded.extend_from_slice(&block);
    let mut first = [f32::NAN; VALUES * 2];
    let mut second = [0.0_f32; VALUES * 2];
    decode_iq2_xxs_matrix(&encoded, 2, VALUES, &mut first).unwrap();
    decode_iq2_xxs_matrix(&encoded, 2, VALUES, &mut second).unwrap();
    assert_eq!(first, second);
    let expected = expected_iq2(&block);
    assert_eq!(
        first[..VALUES]
            .iter()
            .map(|value| value.to_bits())
            .collect::<Vec<_>>(),
        expected
            .iter()
            .map(|value| value.to_bits())
            .collect::<Vec<_>>()
    );
    assert_eq!(&first[..VALUES], &first[VALUES..]);
}

#[test]
fn iq3_matrix_decode_matches_exact_f32_reference_bits() {
    let block = pack_iq3_block();
    let mut first = [f32::NAN; VALUES];
    let mut second = [0.0_f32; VALUES];
    decode_iq3_xxs_matrix(&block, 1, VALUES, &mut first).unwrap();
    decode_iq3_xxs_matrix(&block, 1, VALUES, &mut second).unwrap();
    assert_eq!(first, second);
    let expected = expected_iq3(&block);
    assert_eq!(
        first
            .iter()
            .map(|value| value.to_bits())
            .collect::<Vec<_>>(),
        expected
            .iter()
            .map(|value| value.to_bits())
            .collect::<Vec<_>>()
    );
}

#[test]
fn iq_decoders_reject_truncation_without_partial_output() {
    let iq2 = pack_iq2_block();
    let iq3 = pack_iq3_block();
    let mut out2 = [19.0_f32; VALUES];
    let mut out3 = [23.0_f32; VALUES];
    assert_eq!(
        decode_iq2_xxs_matrix(&iq2[..IQ2_XXS_BLOCK_BYTES - 1], 1, VALUES, &mut out2),
        Err(IQXXSError::EncodedLengthMismatch)
    );
    assert_eq!(
        decode_iq3_xxs_matrix(&iq3[..IQ3_XXS_BLOCK_BYTES - 1], 1, VALUES, &mut out3),
        Err(IQXXSError::EncodedLengthMismatch)
    );
    assert_eq!(out2, [19.0; VALUES]);
    assert_eq!(out3, [23.0; VALUES]);
}

#[test]
fn iq_decoders_reject_nonfinite_scales_without_partial_output() {
    let mut iq2 = pack_iq2_block();
    let mut iq3 = pack_iq3_block();
    iq2[..2].copy_from_slice(&0x7c00_u16.to_le_bytes());
    iq3[..2].copy_from_slice(&0x7e00_u16.to_le_bytes());
    let mut out2 = [29.0_f32; VALUES];
    let mut out3 = [31.0_f32; VALUES];
    assert_eq!(
        decode_iq2_xxs_matrix(&iq2, 1, VALUES, &mut out2),
        Err(IQXXSError::NonFiniteScale)
    );
    assert_eq!(
        decode_iq3_xxs_matrix(&iq3, 1, VALUES, &mut out3),
        Err(IQXXSError::NonFiniteScale)
    );
    assert_eq!(out2, [29.0; VALUES]);
    assert_eq!(out3, [31.0; VALUES]);
}

#[test]
fn iq_decoders_validate_shapes_and_destination_sizes() {
    let iq2 = pack_iq2_block();
    let iq3 = pack_iq3_block();
    let mut out = [0.0_f32; VALUES];
    assert_eq!(
        decode_iq2_xxs_matrix(&iq2, 1, VALUES - 1, &mut out),
        Err(IQXXSError::RowWidthNotDivisible)
    );
    assert_eq!(
        decode_iq3_xxs_matrix(&iq3, 1, VALUES, &mut out[..VALUES - 1]),
        Err(IQXXSError::DestinationLengthMismatch)
    );
}
