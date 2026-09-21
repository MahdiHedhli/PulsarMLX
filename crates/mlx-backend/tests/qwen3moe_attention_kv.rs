use backend::CancellationToken;
use mlx_backend::{
    parse_qwen3moe_attention_kv_fixture, run_qwen3moe_attention_kv,
    validate_qwen3moe_attention_kv_fixture, Qwen3MoeAttentionKvFixture, Qwen3MoeAttentionRuntime,
};
use serde_json::Value;

const FIXTURE: &str = include_str!("../../../fixtures/mlx/qwen3moe-attention-kv-v1.json");

fn fixture() -> Qwen3MoeAttentionKvFixture {
    parse_qwen3moe_attention_kv_fixture(FIXTURE.as_bytes()).expect("attention fixture parses")
}

fn assert_close(actual: &[f32], expected: &[f32], tolerance: f32) {
    assert_eq!(actual.len(), expected.len());
    for (actual, expected) in actual.iter().zip(expected) {
        assert!(
            (actual - expected).abs() <= tolerance,
            "actual={actual} expected={expected}"
        );
    }
}

fn assert_matrix_close(actual: &[Vec<f32>], expected: &[Vec<f32>], tolerance: f32) {
    assert_eq!(actual.len(), expected.len());
    for (actual, expected) in actual.iter().zip(expected) {
        assert_close(actual, expected, tolerance);
    }
}

#[test]
fn attention_fixture_matches_oracle_and_commits_transactional_cache() {
    let fixture = fixture();
    assert_eq!(fixture.schema, "pulsarmlx.fixture.qwen3moe-attention-kv-v1");
    assert_eq!(fixture.schema_version, 1);
    assert_eq!(fixture.fixture_id, "qwen3moe-attention-kv-v1");
    assert!(fixture.model_free);
    assert!(!fixture.uses_checkpoint_payload_bytes);
    assert_eq!(fixture.execution_dimensions.dtype, "f32");
    assert_eq!(fixture.target_dimensions.query_heads, 32);
    assert_eq!(fixture.target_dimensions.kv_heads, 4);
    assert_eq!(fixture.target_dimensions.head_dimension, 128);

    let result = run_qwen3moe_attention_kv(&fixture, &CancellationToken::new())
        .expect("synthetic attention execution succeeds");
    assert!(result.evaluated);
    assert!(!result.fallback_used);
    assert_eq!(result.steps.len(), fixture.steps.len());
    assert_eq!(result.cache.positions.len(), fixture.steps.len());
    for (actual, expected) in result.steps.iter().zip(fixture.oracle.steps.iter()) {
        assert_eq!(actual.position, expected.position);
        assert_close(
            &actual.residual,
            &expected.residual,
            fixture.oracle.tolerance,
        );
    }
}

#[test]
fn every_attention_stage_matches_the_independent_oracle() {
    let fixture = fixture();
    let result = run_qwen3moe_attention_kv(&fixture, &CancellationToken::new()).unwrap();
    for (actual, expected) in result.steps.iter().zip(&fixture.oracle.steps) {
        let tolerance = fixture.oracle.tolerance;
        assert_close(
            &actual.normalized_input,
            &expected.normalized_input,
            tolerance,
        );
        assert_close(
            &actual.query_projected,
            &expected.query_projected,
            tolerance,
        );
        assert_close(&actual.key_projected, &expected.key_projected, tolerance);
        assert_close(
            &actual.value_projected,
            &expected.value_projected,
            tolerance,
        );
        assert_close(
            &actual.query_normalized,
            &expected.query_normalized,
            tolerance,
        );
        assert_close(&actual.key_normalized, &expected.key_normalized, tolerance);
        assert_close(&actual.query_rotated, &expected.query_rotated, tolerance);
        assert_close(&actual.key_rotated, &expected.key_rotated, tolerance);
        assert_matrix_close(
            &actual.attention_scores,
            &expected.attention_scores,
            tolerance,
        );
        assert_matrix_close(
            &actual.attention_probabilities,
            &expected.attention_probabilities,
            tolerance,
        );
        assert_close(
            &actual.attention_output,
            &expected.attention_output,
            tolerance,
        );
        assert_close(
            &actual.projected_output,
            &expected.projected_output,
            tolerance,
        );
        assert_close(&actual.residual, &expected.residual, tolerance);
    }
}

#[test]
fn gqa_uses_one_kv_head_for_two_query_heads_and_masks_future_positions() {
    let fixture = fixture();
    let result = run_qwen3moe_attention_kv(&fixture, &CancellationToken::new()).unwrap();
    assert_eq!(result.cache.keys[0].len(), 4);
    assert_eq!(result.cache.values[0].len(), 4);
    assert_eq!(result.steps[2].attention_scores.len(), 2);
    assert_eq!(result.steps[2].attention_scores[0].len(), 3);
    assert_eq!(result.steps[2].attention_scores[1].len(), 3);
    assert_eq!(result.steps[0].attention_probabilities[0].len(), 1);
    assert_eq!(result.steps[1].attention_probabilities[0].len(), 2);
    assert_eq!(result.steps[2].attention_output.len(), 8);
    for probabilities in &result.steps[2].attention_probabilities {
        assert!((probabilities.iter().sum::<f32>() - 1.0).abs() <= fixture.oracle.tolerance);
    }
}

#[test]
fn cache_positions_are_contiguous_and_reset_discards_all_state() {
    let fixture = fixture();
    let mut runtime = Qwen3MoeAttentionRuntime::try_new(&fixture).unwrap();
    runtime
        .run_fixture(&fixture, &CancellationToken::new())
        .unwrap();
    assert_eq!(runtime.position(), 3);
    assert_eq!(runtime.cache_snapshot().positions, [0, 1, 2]);

    let before = runtime.cache_snapshot();
    let error = runtime
        .process_step(
            &fixture,
            0,
            0,
            &fixture.steps[0].input,
            &CancellationToken::new(),
        )
        .unwrap_err();
    assert_eq!(error.code(), "position_mismatch");
    assert_eq!(runtime.cache_snapshot(), before);

    runtime.reset();
    assert_eq!(runtime.position(), 0);
    assert_eq!(runtime.cache_len(), 0);
    runtime
        .run_fixture(&fixture, &CancellationToken::new())
        .expect("reset runtime accepts a fresh causal sequence");
    assert_eq!(runtime.cache_snapshot().positions, [0, 1, 2]);
}

#[test]
fn cancellation_and_oracle_failure_roll_back_the_entire_kv_batch() {
    let base_fixture = fixture();
    let mut runtime = Qwen3MoeAttentionRuntime::try_new(&base_fixture).unwrap();
    let error = runtime
        .run_fixture_with_cancel_after_step(&base_fixture, &CancellationToken::new(), Some(1))
        .unwrap_err();
    assert_eq!(error.code(), "cancelled");
    assert_eq!(runtime.cache_len(), 0);

    let mut mismatch = fixture();
    mismatch.oracle.steps[1].residual[0] += 0.5;
    let error = runtime
        .run_fixture(&mismatch, &CancellationToken::new())
        .unwrap_err();
    assert_eq!(error.code(), "oracle_mismatch");
    assert_eq!(runtime.cache_len(), 0);
}

#[test]
fn malformed_shape_non_finite_and_payload_fields_fail_closed() {
    let mut shape: Value = serde_json::from_str(FIXTURE).unwrap();
    shape["execution_dimensions"]["query_heads"] = Value::from(3);
    let error =
        parse_qwen3moe_attention_kv_fixture(&serde_json::to_vec(&shape).unwrap()).unwrap_err();
    assert_eq!(error.code(), "tensor_shape_mismatch");

    let mut payload: Value = serde_json::from_str(FIXTURE).unwrap();
    payload["payload_bytes"] = Value::String("forbidden".to_owned());
    let error =
        parse_qwen3moe_attention_kv_fixture(&serde_json::to_vec(&payload).unwrap()).unwrap_err();
    assert_eq!(error.code(), "fixture_parse_error");

    let mut non_finite = fixture();
    non_finite.tensors.query_weight[0][0] = f32::NAN;
    let error = validate_qwen3moe_attention_kv_fixture(&non_finite).unwrap_err();
    assert_eq!(error.code(), "tensor_values_invalid");
}

#[test]
fn qkv_projection_rows_must_match_hidden_width() {
    for matrix_name in ["query_weight", "key_weight", "value_weight"] {
        for overlong in [false, true] {
            let mut malformed = fixture();
            let matrix = match matrix_name {
                "query_weight" => &mut malformed.tensors.query_weight,
                "key_weight" => &mut malformed.tensors.key_weight,
                "value_weight" => &mut malformed.tensors.value_weight,
                _ => unreachable!("matrix name is fixed by the test table"),
            };
            if overlong {
                matrix[0].push(0.0);
            } else {
                matrix[0].pop();
            }

            let error = validate_qwen3moe_attention_kv_fixture(&malformed).unwrap_err();
            assert_eq!(
                error.code(),
                "tensor_shape_mismatch",
                "{matrix_name} overlong={overlong}"
            );
        }
    }
}
