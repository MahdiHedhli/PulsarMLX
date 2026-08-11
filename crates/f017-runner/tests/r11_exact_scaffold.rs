use f017_runner::final_output_qualification::{
    run_r11_exact, stable_top_k, R11Inputs, R11Output, R11_SCAFFOLD_VERSION,
};
use f017_runner::json::{parse_json_no_duplicates, sha256_bytes, sha256_file};
use serde_json::Value;
use std::fs;
use std::path::Path;

#[test]
fn r11_exact_scaffold_matches_independent_q4_k_final_output() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let bytes = fs::read(root.join(
        "specs/017-rust-native-inference-runtime/fixtures/f017-r11-final-output-oracle-v1.json",
    ))
    .unwrap();
    let oracle: Value = parse_json_no_duplicates(&bytes).unwrap();
    validate_identity(&root, &oracle);
    let inputs = load_inputs(&oracle);
    let first = run_r11_exact(&inputs).unwrap();
    for _ in 0..100 {
        assert_eq!(run_r11_exact(&inputs).unwrap(), first);
    }
    assert_expected(&oracle, &first);
    assert_eq!(R11_SCAFFOLD_VERSION, "f017-r11-final-output-exact-v1");
}

#[test]
fn r11_stable_top_k_matches_all_frozen_near_tie_cases() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let bytes = fs::read(root.join(
        "specs/017-rust-native-inference-runtime/fixtures/f017-r11-final-output-oracle-v1.json",
    ))
    .unwrap();
    let oracle: Value = parse_json_no_duplicates(&bytes).unwrap();
    for case in oracle["top_k_stress_cases"].as_array().unwrap() {
        let logits = f32_record(&case["logits"]);
        let top_k = case["top_k"].as_u64().unwrap() as usize;
        let actual = stable_top_k(&logits, top_k).unwrap();
        assert_eq!(
            actual,
            usize_values(&case["expected_top_k_ids"]),
            "{}",
            case["name"]
        );
        assert_eq!(
            actual[0],
            case["expected_argmax"].as_u64().unwrap() as usize,
            "{}",
            case["name"]
        );
    }
}

fn validate_identity(root: &Path, oracle: &Value) {
    assert_eq!(oracle["schema"], "pulsarmlx.f017.r11-final-output-oracle");
    assert_eq!(oracle["fixture_version"], "f017-r11-final-output-q4-k-v1");
    assert_eq!(oracle["inputs"]["output_head"]["quantization"], "Q4_K");
    assert_eq!(oracle["checkpoint_accessed"], false);
    assert_eq!(oracle["independence"]["uses_rust_candidate"], false);
    assert_eq!(oracle["independence"]["uses_mlx"], false);
    assert_eq!(
        sha256_file(&root.join(oracle["generator_path"].as_str().unwrap())).unwrap(),
        oracle["generator_sha256"]
    );
}

fn load_inputs(oracle: &Value) -> R11Inputs {
    let head = &oracle["inputs"]["output_head"];
    let packed = decode_hex(head["packed_hex"].as_str().unwrap());
    assert_eq!(sha256_bytes(&packed), head["packed_sha256"]);
    let shape = usize_values(&head["shape"]);
    R11Inputs {
        final_hidden: f32_record(&oracle["inputs"]["final_hidden"]),
        output_norm_scale: f32_record(&oracle["inputs"]["output_norm_scale"]),
        rms_epsilon: oracle["inputs"]["rms_epsilon"].as_f64().unwrap() as f32,
        output_head_packed: packed,
        output_rows: shape[0],
        output_columns: shape[1],
        top_k: oracle["architecture"]["top_k"].as_u64().unwrap() as usize,
    }
}

fn assert_expected(oracle: &Value, output: &R11Output) {
    assert_f32(
        "final normalized",
        &output.normalized,
        &f32_record(&oracle["expected"]["final_normalized"]),
    );
    assert_eq!(
        sha256_bytes(&f32_bytes(&output.decoded_output_head)),
        oracle["inputs"]["output_head"]["decoded_f32_sha256"]
    );
    assert_f32(
        "logits",
        &output.logits,
        &f32_record(&oracle["expected"]["logits"]),
    );
    assert_eq!(
        sha256_bytes(&f32_bytes(&output.logits)),
        oracle["expected"]["logits_sha256"]
    );
    assert_eq!(
        output.top_k_ids,
        usize_values(&oracle["expected"]["top_k_ids"])
    );
    assert_f32(
        "top k scores",
        &output.top_k_scores,
        &f32_record(&oracle["expected"]["top_k_scores"]),
    );
    assert_eq!(
        output.argmax,
        oracle["expected"]["argmax"].as_u64().unwrap() as usize
    );
}

fn f32_record(value: &Value) -> Vec<f32> {
    decode_hex(value["f32_le_hex"].as_str().unwrap())
        .chunks_exact(4)
        .map(|bytes| f32::from_le_bytes(bytes.try_into().unwrap()))
        .collect()
}

fn usize_values(value: &Value) -> Vec<usize> {
    value
        .as_array()
        .unwrap()
        .iter()
        .map(|value| value.as_u64().unwrap() as usize)
        .collect()
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

fn assert_f32(name: &str, actual: &[f32], expected: &[f32]) {
    assert_eq!(
        actual
            .iter()
            .map(|value| value.to_bits())
            .collect::<Vec<_>>(),
        expected
            .iter()
            .map(|value| value.to_bits())
            .collect::<Vec<_>>(),
        "{name}"
    );
}
