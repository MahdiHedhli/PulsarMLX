use f017_runner::json::{parse_json_no_duplicates, sha256_bytes};
use f017_runner::qualification::{exact_matvec_f32, exact_swiglu_f32, EXACT_SCAFFOLD_VERSION};
use serde::Deserialize;
use std::fs;
use std::path::Path;

#[derive(Deserialize)]
struct Oracle {
    schema: String,
    boundaries: Boundaries,
}

#[derive(Deserialize)]
struct Boundaries {
    complete_expert: CompleteExpert,
}

#[derive(Deserialize)]
struct CompleteExpert {
    classification: String,
    fixture_version: String,
    dimensions: [usize; 2],
    dtype: String,
    quantization: String,
    inputs: ExpertInputs,
    expected: ExpertExpected,
    numerical_contract: NumericalContract,
}

#[derive(Deserialize)]
struct ExpertInputs {
    activation: Vec<f32>,
    activation_sha256: String,
    gate_packed_hex: String,
    gate_packed_sha256: String,
    up_packed_hex: String,
    up_packed_sha256: String,
    down_packed_hex: String,
    down_packed_sha256: String,
}

#[derive(Deserialize)]
struct ExpertExpected {
    gate_output_sha256: String,
    up_output_sha256: String,
    hidden_sha256: String,
    output: Vec<f32>,
    output_sha256: String,
}

#[derive(Deserialize)]
struct NumericalContract {
    kind: String,
    atol: f64,
    rtol: f64,
}

#[test]
fn gate_up_down_and_complete_expert_are_exact_and_repeatable() {
    assert_eq!(EXACT_SCAFFOLD_VERSION, "f017-exact-f32-sequential-v1");
    let oracle_path = Path::new(env!("CARGO_MANIFEST_DIR")).join(
        "../../specs/017-rust-native-inference-runtime/fixtures/f017-independent-oracle-v1.json",
    );
    let bytes = fs::read(oracle_path).unwrap();
    let oracle: Oracle = parse_json_no_duplicates(&bytes).unwrap();
    let expert = oracle.boundaries.complete_expert;
    assert_eq!(oracle.schema, "glm52-f017-independent-oracle-v1");
    assert_eq!(expert.classification, "INDEPENDENT");
    assert_eq!(expert.fixture_version, "glm52-runtime-expert-q8-0-v2");
    assert_eq!(expert.dimensions, [32, 32]);
    assert_eq!(expert.dtype, "f32");
    assert_eq!(expert.quantization, "Q8_0");
    assert_eq!(expert.numerical_contract.kind, "exact_f32_bits");
    assert_eq!(expert.numerical_contract.atol, 0.0);
    assert_eq!(expert.numerical_contract.rtol, 0.0);
    require_hash(
        &f32_bytes(&expert.inputs.activation),
        &expert.inputs.activation_sha256,
    );

    let matrices = [
        decode_matrix(
            &expert.inputs.gate_packed_hex,
            &expert.inputs.gate_packed_sha256,
        ),
        decode_matrix(
            &expert.inputs.up_packed_hex,
            &expert.inputs.up_packed_sha256,
        ),
        decode_matrix(
            &expert.inputs.down_packed_hex,
            &expert.inputs.down_packed_sha256,
        ),
    ];

    for _ in 0..10 {
        let mut gate = vec![0.0_f32; 32];
        let mut up = vec![0.0_f32; 32];
        let mut hidden = vec![0.0_f32; 32];
        let mut output = vec![0.0_f32; 32];
        exact_matvec_f32(&matrices[0], 32, 32, &expert.inputs.activation, &mut gate).unwrap();
        exact_matvec_f32(&matrices[1], 32, 32, &expert.inputs.activation, &mut up).unwrap();
        require_hash(&f32_bytes(&gate), &expert.expected.gate_output_sha256);
        require_hash(&f32_bytes(&up), &expert.expected.up_output_sha256);

        exact_swiglu_f32(&gate, &up, &mut hidden).unwrap();
        require_hash(&f32_bytes(&hidden), &expert.expected.hidden_sha256);
        exact_matvec_f32(&matrices[2], 32, 32, &hidden, &mut output).unwrap();
        require_hash(&f32_bytes(&output), &expert.expected.output_sha256);
        assert_eq!(
            output
                .iter()
                .map(|value| value.to_bits())
                .collect::<Vec<_>>(),
            expert
                .expected
                .output
                .iter()
                .map(|value| value.to_bits())
                .collect::<Vec<_>>()
        );
    }
}

fn decode_matrix(encoded_hex: &str, expected_packed_hash: &str) -> Vec<f32> {
    let packed = decode_hex(encoded_hex);
    require_hash(&packed, expected_packed_hash);
    let mut decoded = vec![0.0_f32; 32 * 32];
    quant::decode_q8_0_matrix(&packed, 32, 32, &mut decoded).unwrap();
    decoded
}

fn decode_hex(encoded: &str) -> Vec<u8> {
    encoded
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
        .collect()
}

fn f32_bytes(values: &[f32]) -> Vec<u8> {
    values
        .iter()
        .flat_map(|value| value.to_le_bytes())
        .collect()
}

fn require_hash(bytes: &[u8], expected: &str) {
    assert_eq!(sha256_bytes(bytes), expected);
}
