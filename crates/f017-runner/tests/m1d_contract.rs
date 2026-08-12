use f017_runner::json::{parse_json_no_duplicates, sha256_bytes};
use f017_runner::numerical_classification::{
    validate_classification_applicability, GreedyApplicability, NumericalClassification,
};
use f017_runner::qualification::{
    exact_matvec_f32, qualify_m1d_projection_tier_b, M1D_EXACT_SCAFFOLD_VERSION,
    M1D_TIER_B_CONTRACT_VERSION,
};
use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../specs/017-rust-native-inference-runtime/fixtures")
}

fn decode_hex(value: &str) -> Vec<u8> {
    (0..value.len())
        .step_by(2)
        .map(|index| u8::from_str_radix(&value[index..index + 2], 16).unwrap())
        .collect()
}

fn f32_values(bytes: &[u8]) -> Vec<f32> {
    bytes
        .chunks_exact(4)
        .map(|chunk| f32::from_le_bytes(chunk.try_into().unwrap()))
        .collect()
}

fn f32_bytes(values: &[f32]) -> Vec<u8> {
    values
        .iter()
        .flat_map(|value| value.to_le_bytes())
        .collect()
}

#[test]
fn real_shaped_q8_decoder_and_exact_scaffold_are_golden_identical() {
    let bytes = fs::read(root().join("f017-m1d-projection-oracle-v1.json")).unwrap();
    let oracle: Value = parse_json_no_duplicates(&bytes).unwrap();
    let packed = fs::read(root().join("f017-m1d-projection-q8-0-v1.bin")).unwrap();
    assert_eq!(
        sha256_bytes(&packed),
        oracle["synthetic_matrix"]["packed_sha256"]
    );
    let mut decoded = vec![0.0_f32; 576 * 6144];
    quant::decode_q8_0_matrix(&packed, 576, 6144, &mut decoded).unwrap();
    assert_eq!(
        sha256_bytes(&f32_bytes(&decoded)),
        oracle["synthetic_matrix"]["decoded_f32_sha256"]
    );
    let activation = f32_values(&decode_hex(
        oracle["activation"]["bytes_hex"].as_str().unwrap(),
    ));
    let expected_bytes = decode_hex(oracle["oracle"]["output_f32_hex"].as_str().unwrap());
    let expected = f32_values(&expected_bytes);
    let mut output = vec![0.0_f32; 576];
    for _ in 0..10 {
        exact_matvec_f32(&decoded, 576, 6144, &activation, &mut output).unwrap();
        assert_eq!(f32_bytes(&output), expected_bytes);
    }
    let qualified =
        qualify_m1d_projection_tier_b(&decoded, 576, 6144, &activation, &expected, &output)
            .unwrap();
    assert!(qualified.passes);
    assert_eq!(qualified.contract_version, M1D_TIER_B_CONTRACT_VERSION);
    assert_eq!(
        oracle["oracle"]["scaffold_version"],
        M1D_EXACT_SCAFFOLD_VERSION
    );
}

#[test]
fn tier_b_is_operand_derived_and_rejects_contract_violations() {
    let matrix = (0..64)
        .map(|index| {
            if index % 2 == 0 {
                2.0_f32.powi(20)
            } else {
                -2.0_f32.powi(20)
            }
        })
        .collect::<Vec<_>>();
    let activation = (0..32)
        .map(|index| {
            if index % 2 == 0 {
                2.0_f32.powi(-20)
            } else {
                -2.0_f32.powi(-20)
            }
        })
        .collect::<Vec<_>>();
    let mut expected = vec![0.0_f32; 2];
    exact_matvec_f32(&matrix, 2, 32, &activation, &mut expected).unwrap();
    let exact =
        qualify_m1d_projection_tier_b(&matrix, 2, 32, &activation, &expected, &expected).unwrap();
    assert!(exact.passes);
    let mut bad = expected.clone();
    bad[0] += 1_000_000.0;
    assert!(
        !qualify_m1d_projection_tier_b(&matrix, 2, 32, &activation, &expected, &bad,)
            .unwrap()
            .passes
    );
    assert!(validate_classification_applicability(
        NumericalClassification::NumericallyQualifiedGreedyNotApplicable,
        GreedyApplicability::NotApplicable,
        None,
    )
    .is_ok());
    assert!(validate_classification_applicability(
        NumericalClassification::NumericallyQualifiedGreedyIdentical,
        GreedyApplicability::NotApplicable,
        None,
    )
    .is_err());
}

#[test]
fn q8_decoder_rejects_malformed_input_without_partial_write() {
    let packed = fs::read(root().join("f017-m1d-projection-q8-0-v1.bin")).unwrap();
    let mut output = vec![123.0_f32; 576 * 6144];
    assert!(
        quant::decode_q8_0_matrix(&packed[..packed.len() - 1], 576, 6144, &mut output).is_err()
    );
    assert!(output
        .iter()
        .all(|value| value.to_bits() == 123.0_f32.to_bits()));
}
