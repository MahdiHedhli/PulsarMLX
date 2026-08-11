use f017_runner::json::{parse_json_no_duplicates, sha256_bytes, sha256_file};
use f017_runner::layer_qualification::{
    run_r10_exact, ExpertMatrices, R10Inputs, R10Matrices, R10Output, R10_SCAFFOLD_VERSION,
};
use serde_json::Value;
use std::fs;
use std::path::Path;

#[test]
fn r10_exact_scaffold_matches_independent_complete_layer() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let path = root.join(
        "specs/017-rust-native-inference-runtime/fixtures/f017-r10-complete-layer-oracle-v1.json",
    );
    let bytes = fs::read(&path).unwrap();
    let oracle: Value = parse_json_no_duplicates(&bytes).unwrap();
    validate_identity(&root, &oracle);
    let (matrices, inputs) = load_inputs(&oracle);
    let first = run_r10_exact(&matrices, &inputs).unwrap();
    for _ in 0..100 {
        assert_eq!(run_r10_exact(&matrices, &inputs).unwrap(), first);
    }
    assert_expected(&oracle, &first);
    assert_eq!(R10_SCAFFOLD_VERSION, "f017-r10-complete-layer-exact-v1");
}

#[test]
fn r10_fails_closed_when_selected_expert_identity_is_changed() {
    let oracle = load_oracle();
    let (mut matrices, inputs) = load_inputs(&oracle);
    matrices.routed[0].expert_id += 1;
    assert!(run_r10_exact(&matrices, &inputs).is_err());
}

fn load_oracle() -> Value {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let bytes = fs::read(root.join(
        "specs/017-rust-native-inference-runtime/fixtures/f017-r10-complete-layer-oracle-v1.json",
    ))
    .unwrap();
    parse_json_no_duplicates(&bytes).unwrap()
}

fn validate_identity(root: &Path, oracle: &Value) {
    assert_eq!(oracle["schema"], "pulsarmlx.f017.r10-complete-layer-oracle");
    assert_eq!(oracle["fixture_version"], "f017-r10-complete-layer-q8-0-v1");
    assert_eq!(oracle["architecture"]["family"], "glm-dsa");
    assert_eq!(
        oracle["promotion_status"],
        "fixture_frozen_before_candidate_execution"
    );
    assert_eq!(oracle["checkpoint_accessed"], false);
    assert_eq!(oracle["independence"]["uses_rust_candidate"], false);
    assert_eq!(oracle["independence"]["uses_mlx"], false);
    assert_eq!(
        sha256_file(&root.join(oracle["generator_path"].as_str().unwrap())).unwrap(),
        oracle["generator_sha256"]
    );
}

fn load_inputs(oracle: &Value) -> (R10Matrices, R10Inputs) {
    let selected = usize_values(&oracle["expected"]["selected_ids"]);
    let routed = oracle["inputs"]["routed_experts"]
        .as_array()
        .unwrap()
        .iter()
        .map(|expert| {
            let matrices = expert["matrices"].as_array().unwrap();
            ExpertMatrices {
                expert_id: expert["expert_id"].as_u64().unwrap() as usize,
                gate: matrix(&matrices[0]),
                up: matrix(&matrices[1]),
                down: matrix(&matrices[2]),
            }
        })
        .collect::<Vec<_>>();
    assert_eq!(
        routed
            .iter()
            .map(|expert| expert.expert_id)
            .collect::<Vec<_>>(),
        selected
    );
    let shared = oracle["inputs"]["shared_expert"]["matrices"]
        .as_array()
        .unwrap();
    (
        R10Matrices {
            router: matrix(&oracle["inputs"]["router"]),
            routed,
            shared: ExpertMatrices {
                expert_id: usize::MAX,
                gate: matrix(&shared[0]),
                up: matrix(&shared[1]),
                down: matrix(&shared[2]),
            },
        },
        R10Inputs {
            attention_residual: f32_record(&oracle["inputs"]["attention_residual"]),
            post_attention_norm_scale: f32_record(&oracle["inputs"]["post_attention_norm_scale"]),
            router_bias: f64_record(&oracle["inputs"]["router_bias"]),
            rms_epsilon: oracle["inputs"]["rms_epsilon"].as_f64().unwrap() as f32,
            top_k: oracle["architecture"]["selected_expert_count"]
                .as_u64()
                .unwrap() as usize,
            expert_weight_scale: oracle["architecture"]["expert_weight_scale"]
                .as_f64()
                .unwrap(),
        },
    )
}

fn assert_expected(oracle: &Value, output: &R10Output) {
    assert_f32(
        "normalized",
        &output.normalized,
        &f32_record(&oracle["expected"]["normalized"]),
    );
    assert_f32(
        "router_logits",
        &output.router_logits,
        &f32_record(&oracle["expected"]["router_logits"]),
    );
    assert_f64(
        "router_probabilities",
        &output.router_probabilities,
        &f64_record(&oracle["expected"]["router_probabilities"]),
    );
    assert_f64(
        "router_scores",
        &output.router_scores,
        &f64_record(&oracle["expected"]["router_scores"]),
    );
    assert_eq!(
        output.selected_ids,
        usize_values(&oracle["expected"]["selected_ids"])
    );
    assert_f64(
        "routing_weights",
        &output.routing_weights,
        &f64_record(&oracle["expected"]["routing_weights"]),
    );
    for (index, expert) in output.routed_experts.iter().enumerate() {
        let expected = &oracle["expected"]["routed_experts"][index];
        assert_f32("expert gate", &expert.gate, &f32_record(&expected["gate"]));
        assert_f32("expert up", &expert.up, &f32_record(&expected["up"]));
        assert_f32(
            "expert hidden",
            &expert.hidden,
            &f32_record(&expected["hidden"]),
        );
        assert_f32("expert down", &expert.down, &f32_record(&expected["down"]));
    }
    let shared = &oracle["expected"]["shared_expert"];
    assert_f32(
        "shared gate",
        &output.shared_expert.gate,
        &f32_record(&shared["gate"]),
    );
    assert_f32(
        "shared up",
        &output.shared_expert.up,
        &f32_record(&shared["up"]),
    );
    assert_f32(
        "shared hidden",
        &output.shared_expert.hidden,
        &f32_record(&shared["hidden"]),
    );
    assert_f32(
        "shared down",
        &output.shared_expert.down,
        &f32_record(&shared["down"]),
    );
    assert_f64(
        "routed aggregate",
        &output.routed_aggregate,
        &f64_record(&oracle["expected"]["routed_aggregate"]),
    );
    assert_f64(
        "combined moe",
        &output.combined_moe,
        &f64_record(&oracle["expected"]["combined_moe"]),
    );
    assert_f32(
        "output",
        &output.output,
        &f32_record(&oracle["expected"]["output"]),
    );
}

fn matrix(value: &Value) -> Vec<f32> {
    let packed = decode_hex(value["packed_hex"].as_str().unwrap());
    assert_eq!(sha256_bytes(&packed), value["packed_sha256"]);
    let shape = usize_values(&value["shape"]);
    let mut output = vec![0.0; shape[0] * shape[1]];
    quant::decode_q8_0_matrix(&packed, shape[0], shape[1], &mut output).unwrap();
    assert_eq!(
        sha256_bytes(&f32_bytes(&output)),
        value["decoded_f32_sha256"]
    );
    output
}

fn f32_record(value: &Value) -> Vec<f32> {
    decode_hex(value["f32_le_hex"].as_str().unwrap())
        .chunks_exact(4)
        .map(|bytes| f32::from_le_bytes(bytes.try_into().unwrap()))
        .collect()
}
fn f64_record(value: &Value) -> Vec<f64> {
    decode_hex(value["f64_le_hex"].as_str().unwrap())
        .chunks_exact(8)
        .map(|bytes| f64::from_le_bytes(bytes.try_into().unwrap()))
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
fn assert_f32(name: &str, actual: &[f32], expected: &[f32]) {
    assert_eq!(
        actual.iter().map(|v| v.to_bits()).collect::<Vec<_>>(),
        expected.iter().map(|v| v.to_bits()).collect::<Vec<_>>(),
        "{name}"
    );
}
fn assert_f64(name: &str, actual: &[f64], expected: &[f64]) {
    assert_eq!(
        actual.iter().map(|v| v.to_bits()).collect::<Vec<_>>(),
        expected.iter().map(|v| v.to_bits()).collect::<Vec<_>>(),
        "{name}"
    );
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
