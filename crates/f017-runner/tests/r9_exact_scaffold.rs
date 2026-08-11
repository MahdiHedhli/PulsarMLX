use f017_runner::json::{parse_json_no_duplicates, sha256_bytes, sha256_file};
use f017_runner::layer_qualification::{
    dsa_select_stable, run_r9_exact, R9Inputs, R9Matrices, R9_SCAFFOLD_VERSION,
};
use serde::Deserialize;
use std::fs;
use std::path::Path;

#[derive(Deserialize)]
struct Oracle {
    schema: String,
    fixture_version: String,
    source_commit: String,
    generator_path: String,
    generator_sha256: String,
    independence: Independence,
    architecture: Architecture,
    matrices: Matrices,
    inputs: Inputs,
    expected: Expected,
    selection: Selection,
    dsa_indexer_fixture: Dsa,
    numerical_contract: Contract,
    checkpoint_accessed: bool,
}

#[derive(Deserialize)]
struct Independence {
    classification: String,
    uses_rust_candidate: bool,
    uses_rust_reference_functions: bool,
    uses_mlx: bool,
    uses_checkpoint: bool,
}

#[derive(Deserialize)]
struct Architecture {
    family: String,
    dsa_mode: String,
    full_indexer_active_for_p1: bool,
    query_position: usize,
    visible_positions: usize,
}

#[derive(Deserialize)]
struct Matrix {
    quantization: String,
    shape: [usize; 2],
    packed_hex: String,
    packed_sha256: String,
    decoded_f32_sha256: String,
}

#[derive(Deserialize)]
struct Matrices {
    attn_q_a: Matrix,
    attn_q_b: Matrix,
    attn_kv_a_mqa: Matrix,
    attn_k_b: Matrix,
    attn_v_b: Matrix,
    attn_output: Matrix,
}

#[derive(Deserialize)]
struct F32Record {
    values: Vec<f32>,
    f32_le_hex: String,
    sha256: String,
}

#[derive(Deserialize)]
struct Inputs {
    residual: F32Record,
    attn_norm_scale: F32Record,
    q_norm_scale: F32Record,
    kv_norm_scale: F32Record,
    prior_cache_latents: F32Record,
    prior_cache_ropes: F32Record,
    q_rope_cosine: F32Record,
    q_rope_sine: F32Record,
    rms_epsilon: f32,
    attention_scale: f32,
}

#[derive(Deserialize)]
struct Expected {
    x_norm: F32Record,
    q_rank: F32Record,
    q_rank_norm: F32Record,
    q_flat: F32Record,
    q_nope: F32Record,
    q_rope: F32Record,
    kv_raw: F32Record,
    kv_norm: F32Record,
    current_k_rope: F32Record,
    qk_low: F32Record,
    rotated_keys: F32Record,
    attention_scores: F32Record,
    attention_probabilities: F32Record,
    latent_sum: F32Record,
    value: F32Record,
    projected: F32Record,
    output: F32Record,
}

#[derive(Deserialize)]
struct Selection {
    mode: String,
    selected_positions: Vec<usize>,
}

#[derive(Deserialize)]
struct Dsa {
    scores: F32Record,
    visible_mask: Vec<bool>,
    top_k: usize,
    tie_break: String,
    selected_positions: Vec<usize>,
    state_before: DsaState,
    appended_position: usize,
    state_after: DsaState,
}

#[derive(Deserialize)]
struct DsaState {
    visible: usize,
    last_position: usize,
}

#[derive(Deserialize)]
struct Contract {
    exact_scaffold: String,
    production: String,
    signed_zero: String,
    deterministic_repeats: usize,
}

#[test]
fn r9_exact_scaffold_matches_every_independent_oracle_boundary() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let fixture_path = root
        .join("specs/017-rust-native-inference-runtime/fixtures/f017-r9-mla-dsa-oracle-v1.json");
    let bytes = fs::read(&fixture_path).unwrap();
    let oracle: Oracle = parse_json_no_duplicates(&bytes).unwrap();
    validate_identity(&root, &oracle);
    let matrices = R9Matrices {
        q_a: decode_matrix(&oracle.matrices.attn_q_a),
        q_b: decode_matrix(&oracle.matrices.attn_q_b),
        kv_a: decode_matrix(&oracle.matrices.attn_kv_a_mqa),
        k_b: decode_matrix(&oracle.matrices.attn_k_b),
        v_b: decode_matrix(&oracle.matrices.attn_v_b),
        output: decode_matrix(&oracle.matrices.attn_output),
    };
    let inputs = R9Inputs {
        residual: decode_record(&oracle.inputs.residual),
        attn_norm_scale: decode_record(&oracle.inputs.attn_norm_scale),
        q_norm_scale: decode_record(&oracle.inputs.q_norm_scale),
        kv_norm_scale: decode_record(&oracle.inputs.kv_norm_scale),
        prior_cache_latents: decode_record(&oracle.inputs.prior_cache_latents),
        prior_cache_ropes: decode_record(&oracle.inputs.prior_cache_ropes),
        q_rope_cosine: decode_record(&oracle.inputs.q_rope_cosine),
        q_rope_sine: decode_record(&oracle.inputs.q_rope_sine),
        rms_epsilon: oracle.inputs.rms_epsilon,
        attention_scale: oracle.inputs.attention_scale,
        query_position: oracle.architecture.query_position,
        visible_positions: oracle.architecture.visible_positions,
    };
    let first = run_r9_exact(&matrices, &inputs).unwrap();
    for _ in 0..100 {
        assert_eq!(run_r9_exact(&matrices, &inputs).unwrap(), first);
    }
    for (name, actual, expected) in [
        ("x_norm", &first.x_norm, &oracle.expected.x_norm),
        ("q_rank", &first.q_rank, &oracle.expected.q_rank),
        (
            "q_rank_norm",
            &first.q_rank_norm,
            &oracle.expected.q_rank_norm,
        ),
        ("q_flat", &first.q_flat, &oracle.expected.q_flat),
        ("q_nope", &first.q_nope, &oracle.expected.q_nope),
        ("q_rope", &first.q_rope, &oracle.expected.q_rope),
        ("kv_raw", &first.kv_raw, &oracle.expected.kv_raw),
        ("kv_norm", &first.kv_norm, &oracle.expected.kv_norm),
        (
            "current_k_rope",
            &first.current_k_rope,
            &oracle.expected.current_k_rope,
        ),
        ("qk_low", &first.qk_low, &oracle.expected.qk_low),
        (
            "rotated_keys",
            &first.rotated_keys,
            &oracle.expected.rotated_keys,
        ),
        (
            "attention_scores",
            &first.attention_scores,
            &oracle.expected.attention_scores,
        ),
        (
            "attention_probabilities",
            &first.attention_probabilities,
            &oracle.expected.attention_probabilities,
        ),
        ("latent_sum", &first.latent_sum, &oracle.expected.latent_sum),
        ("value", &first.value, &oracle.expected.value),
        ("projected", &first.projected, &oracle.expected.projected),
        ("output", &first.output, &oracle.expected.output),
    ] {
        assert_bits(name, actual, &decode_record(expected));
    }
    assert_eq!(
        first.selected_positions,
        oracle.selection.selected_positions
    );
    assert_eq!(oracle.selection.mode, "range_fill");
    assert_eq!(R9_SCAFFOLD_VERSION, "f017-r9-mla-dsa-exact-v1");
}

#[test]
fn r9_dsa_indexer_selection_mask_ties_and_state_are_exact() {
    let oracle = load_oracle();
    let selected = dsa_select_stable(
        &decode_record(&oracle.dsa_indexer_fixture.scores),
        &oracle.dsa_indexer_fixture.visible_mask,
        oracle.dsa_indexer_fixture.top_k,
    )
    .unwrap();
    assert_eq!(selected, oracle.dsa_indexer_fixture.selected_positions);
    assert_eq!(oracle.dsa_indexer_fixture.tie_break, "lower_position");
    assert_eq!(
        oracle.dsa_indexer_fixture.state_before.visible + 1,
        oracle.dsa_indexer_fixture.state_after.visible
    );
    assert_eq!(
        oracle.dsa_indexer_fixture.appended_position,
        oracle.dsa_indexer_fixture.state_after.last_position
    );
    assert_eq!(
        oracle.dsa_indexer_fixture.state_before.last_position + 1,
        oracle.dsa_indexer_fixture.appended_position
    );
    assert!(!selected.contains(&5));
    assert!(!selected.contains(&9));
}

#[test]
fn r9_scaffold_rejects_malformed_inputs_without_candidate_dispatch() {
    let oracle = load_oracle();
    let matrices = R9Matrices {
        q_a: decode_matrix(&oracle.matrices.attn_q_a),
        q_b: decode_matrix(&oracle.matrices.attn_q_b),
        kv_a: decode_matrix(&oracle.matrices.attn_kv_a_mqa),
        k_b: decode_matrix(&oracle.matrices.attn_k_b),
        v_b: decode_matrix(&oracle.matrices.attn_v_b),
        output: decode_matrix(&oracle.matrices.attn_output),
    };
    let mut inputs = R9Inputs {
        residual: decode_record(&oracle.inputs.residual),
        attn_norm_scale: decode_record(&oracle.inputs.attn_norm_scale),
        q_norm_scale: decode_record(&oracle.inputs.q_norm_scale),
        kv_norm_scale: decode_record(&oracle.inputs.kv_norm_scale),
        prior_cache_latents: decode_record(&oracle.inputs.prior_cache_latents),
        prior_cache_ropes: decode_record(&oracle.inputs.prior_cache_ropes),
        q_rope_cosine: decode_record(&oracle.inputs.q_rope_cosine),
        q_rope_sine: decode_record(&oracle.inputs.q_rope_sine),
        rms_epsilon: oracle.inputs.rms_epsilon,
        attention_scale: oracle.inputs.attention_scale,
        query_position: oracle.architecture.query_position,
        visible_positions: oracle.architecture.visible_positions,
    };
    inputs.prior_cache_latents.pop();
    assert!(run_r9_exact(&matrices, &inputs).is_err());
}

fn load_oracle() -> Oracle {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let bytes =
        fs::read(root.join(
            "specs/017-rust-native-inference-runtime/fixtures/f017-r9-mla-dsa-oracle-v1.json",
        ))
        .unwrap();
    parse_json_no_duplicates(&bytes).unwrap()
}

fn validate_identity(root: &Path, oracle: &Oracle) {
    assert_eq!(oracle.schema, "pulsarmlx.f017.r9-mla-dsa-oracle");
    assert_eq!(oracle.fixture_version, "f017-r9-mla-dsa-q8-0-v1");
    assert_eq!(oracle.source_commit.len(), 40);
    assert_eq!(oracle.independence.classification, "INDEPENDENT");
    assert!(!oracle.independence.uses_rust_candidate);
    assert!(!oracle.independence.uses_rust_reference_functions);
    assert!(!oracle.independence.uses_mlx);
    assert!(!oracle.independence.uses_checkpoint);
    assert!(!oracle.checkpoint_accessed);
    assert_eq!(oracle.architecture.family, "glm-dsa");
    assert_eq!(oracle.architecture.dsa_mode, "range_fill");
    assert!(!oracle.architecture.full_indexer_active_for_p1);
    assert_eq!(
        oracle.numerical_contract.exact_scaffold,
        "exact_f32_bits_at_every_recorded_boundary"
    );
    assert_eq!(
        oracle.numerical_contract.production,
        "pending_frozen_r9_tier_b_contract"
    );
    assert_eq!(oracle.numerical_contract.signed_zero, "exact");
    assert_eq!(oracle.numerical_contract.deterministic_repeats, 10);
    assert_eq!(
        sha256_file(&root.join(&oracle.generator_path)).unwrap(),
        oracle.generator_sha256
    );
}

fn decode_matrix(matrix: &Matrix) -> Vec<f32> {
    assert_eq!(matrix.quantization, "Q8_0");
    let packed = decode_hex(&matrix.packed_hex);
    assert_eq!(sha256_bytes(&packed), matrix.packed_sha256);
    let mut output = vec![0.0_f32; matrix.shape[0] * matrix.shape[1]];
    quant::decode_q8_0_matrix(&packed, matrix.shape[0], matrix.shape[1], &mut output).unwrap();
    assert_eq!(sha256_bytes(&f32_bytes(&output)), matrix.decoded_f32_sha256);
    output
}

fn decode_record(record: &F32Record) -> Vec<f32> {
    let bytes = decode_hex(&record.f32_le_hex);
    assert_eq!(sha256_bytes(&bytes), record.sha256);
    let values = bytes
        .chunks_exact(4)
        .map(|bytes| f32::from_le_bytes(bytes.try_into().unwrap()))
        .collect::<Vec<_>>();
    assert_bits("record decimal mirror", &values, &record.values);
    values
}

fn assert_bits(name: &str, actual: &[f32], expected: &[f32]) {
    assert_eq!(actual.len(), expected.len(), "{name} length");
    for (index, (&actual, &expected)) in actual.iter().zip(expected).enumerate() {
        assert_eq!(actual.to_bits(), expected.to_bits(), "{name}[{index}]");
    }
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
