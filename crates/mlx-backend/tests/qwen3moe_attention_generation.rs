use backend::{generate_greedy, CancellationToken, GenerationRequest};
use mlx_backend::{
    parse_qwen3moe_attention_greedy_fixture, run_qwen3moe_attention_greedy_generation,
    validate_qwen3moe_attention_greedy_fixture, Qwen3MoeAttentionGreedyFixture,
    Qwen3MoeAttentionGreedyRuntime,
};
use serde_json::Value;

const FIXTURE: &str = include_str!("../../../fixtures/mlx/qwen3moe-attention-greedy-v1.json");

fn fixture() -> Qwen3MoeAttentionGreedyFixture {
    parse_qwen3moe_attention_greedy_fixture(FIXTURE.as_bytes())
        .expect("attention-to-greedy fixture parses")
}

fn request(fixture: &Qwen3MoeAttentionGreedyFixture) -> GenerationRequest {
    GenerationRequest::try_new(
        fixture.prompt_token_ids.clone(),
        fixture.max_new_tokens,
        Some(fixture.eos_token_id),
    )
    .expect("fixture request is bounded")
}

#[test]
fn fixture_is_strict_bounded_model_free_and_oracle_backed() {
    assert!(FIXTURE.len() < 1 << 20);
    let fixture = fixture();
    assert_eq!(
        fixture.schema,
        "pulsarmlx.fixture.qwen3moe-attention-greedy-v1"
    );
    assert_eq!(fixture.schema_version, 1);
    assert_eq!(fixture.fixture_id, "qwen3moe-attention-greedy-v1");
    assert!(fixture.model_free);
    assert!(!fixture.uses_checkpoint_payload_bytes);
    assert_eq!(fixture.attention.execution_dimensions.dtype, "f32");
    assert_eq!(fixture.operation_order.len(), 4);
    assert_eq!(fixture.oracle.steps.len(), fixture.attention.steps.len());
    assert!(fixture.oracle.independently_generated);
    assert_eq!(
        fixture.oracle.generator,
        "standalone_f32_scalar_reference_v1"
    );
    validate_qwen3moe_attention_greedy_fixture(&fixture).expect("fixture contract is valid");
}

#[test]
fn computed_attention_residuals_and_logits_drive_backend_greedy() {
    let fixture = fixture();
    let result = run_qwen3moe_attention_greedy_generation(
        &fixture,
        &request(&fixture),
        &CancellationToken::new(),
    )
    .expect("attention-to-greedy generation succeeds");

    assert!(result.evaluated);
    assert!(!result.fallback_used);
    assert_eq!(result.prompt_token_ids(), [1, 2]);
    assert_eq!(result.generated_token_ids(), [7, 9, 0]);
    assert_eq!(result.full_token_ids(), [1, 2, 7, 9, 0]);
    assert_eq!(result.termination_reason().as_str(), "eos_token");
    assert_eq!(result.steps.len(), 3);
    assert_eq!(result.steps[0].position, 0);
    assert_eq!(result.steps[1].position, 1);
    assert_eq!(result.steps[2].position, 2);
    for (actual, expected) in result.steps.iter().zip(fixture.oracle.steps.iter()) {
        assert_eq!(actual.position, expected.position);
        assert_eq!(actual.argmax, expected.argmax);
        assert_eq!(actual.topk.len(), expected.topk.len());
        for (actual, expected) in actual.logits.iter().zip(expected.logits.iter()) {
            assert!((actual - expected).abs() <= fixture.oracle.tolerance);
        }
        for (actual, expected) in actual.residual.iter().zip(expected.residual.iter()) {
            assert!((actual - expected).abs() <= fixture.oracle.tolerance);
        }
    }
}

#[test]
fn deterministic_projection_ties_choose_the_lowest_token_id() {
    let fixture = fixture();
    let result = run_qwen3moe_attention_greedy_generation(
        &fixture,
        &request(&fixture),
        &CancellationToken::new(),
    )
    .unwrap();
    assert_eq!(result.steps[0].argmax, 7);
    assert_eq!(result.steps[0].topk[0].0, 7);
    assert_eq!(result.steps[0].topk[3].0, 42);
    assert_eq!(result.steps[0].topk[0].1, result.steps[0].topk[3].1);
}

#[test]
fn attention_or_projection_mutations_cannot_fall_back_to_fixture_logits() {
    let mut attention = fixture();
    attention.attention.steps[0].input[0] += 0.25;
    let error = run_qwen3moe_attention_greedy_generation(
        &attention,
        &request(&attention),
        &CancellationToken::new(),
    )
    .unwrap_err();
    assert_eq!(error.code(), "oracle_mismatch");

    let mut projection = fixture();
    projection.output_projection.output_projection_weight[0][0] += 0.25;
    let error = run_qwen3moe_attention_greedy_generation(
        &projection,
        &request(&projection),
        &CancellationToken::new(),
    )
    .unwrap_err();
    assert_eq!(error.code(), "oracle_mismatch");
}

#[test]
fn cancellation_before_and_after_logits_does_not_publish_tokens_or_kv() {
    let fixture = fixture();
    let request = request(&fixture);

    let before = CancellationToken::new();
    before.cancel();
    let mut runtime = Qwen3MoeAttentionGreedyRuntime::new(fixture.clone()).unwrap();
    let error = generate_greedy(&mut runtime, &request, &before).unwrap_err();
    assert_eq!(error.code(), "cancelled");
    assert_eq!(runtime.attention_position(), 0);
    assert!(runtime.evidence().is_empty());

    let cancellation = CancellationToken::new();
    let mut runtime = Qwen3MoeAttentionGreedyRuntime::new(fixture)
        .unwrap()
        .with_cancel_after_logits(Some(1));
    let error = generate_greedy(&mut runtime, &request, &cancellation).unwrap_err();
    assert_eq!(error.code(), "cancelled");
    assert_eq!(runtime.attention_position(), 0);
    assert!(runtime.evidence().is_empty());
}

#[test]
fn malformed_operation_shape_non_finite_duplicate_and_unknown_fields_fail_closed() {
    let mut operation = fixture();
    operation.operation_order.swap(0, 1);
    assert!(validate_qwen3moe_attention_greedy_fixture(&operation).is_err());

    let mut shape = fixture();
    shape.output_projection.output_projection_weight[0].pop();
    assert_eq!(
        validate_qwen3moe_attention_greedy_fixture(&shape)
            .unwrap_err()
            .code(),
        "tensor_shape_mismatch"
    );

    let mut non_finite = fixture();
    non_finite.output_projection.output_projection_weight[0][0] = f32::NAN;
    assert_eq!(
        validate_qwen3moe_attention_greedy_fixture(&non_finite)
            .unwrap_err()
            .code(),
        "non_finite_tensor"
    );

    let mut duplicate = fixture();
    duplicate.output_projection.output_token_ids[1] =
        duplicate.output_projection.output_token_ids[0];
    assert_eq!(
        validate_qwen3moe_attention_greedy_fixture(&duplicate)
            .unwrap_err()
            .code(),
        "duplicate_output_token"
    );

    for field in ["payload_bytes", "model_path", "file_descriptor"] {
        let mut value: Value = serde_json::from_str(FIXTURE).unwrap();
        value[field] = Value::String("forbidden".to_owned());
        let error = parse_qwen3moe_attention_greedy_fixture(&serde_json::to_vec(&value).unwrap())
            .unwrap_err();
        assert_eq!(error.code(), "fixture_parse_error", "field={field}");
    }
}
