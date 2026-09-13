use backend::{CancellationToken, GenerationRequest, MAX_NEW_TOKENS, MAX_PROMPT_TOKENS};
use mlx_backend::{
    deterministic_top_k, parse_qwen3moe_synthetic_fixture, run_qwen3moe_synthetic_generation,
    run_qwen3moe_synthetic_generation_with_cancel_after_step, validate_qwen3moe_synthetic_fixture,
    Qwen3MoeSyntheticFixture, QWEN3MOE_FULL_GRAPH_CONTRACT_ID,
};
use serde_json::Value;

const FIXTURE: &str = include_str!("../../../fixtures/mlx/qwen3moe-ffn-generation-v1.json");

fn fixture() -> Qwen3MoeSyntheticFixture {
    parse_qwen3moe_synthetic_fixture(FIXTURE.as_bytes()).expect("fixture parses")
}

fn request(fixture: &Qwen3MoeSyntheticFixture) -> GenerationRequest {
    GenerationRequest::try_new(
        fixture.prompt_token_ids.clone(),
        fixture.max_new_tokens,
        Some(fixture.eos_token_id),
    )
    .expect("fixture request is bounded")
}

fn assert_close(actual: f32, expected: f32) {
    assert!(
        (actual - expected).abs() <= 2.0e-5,
        "actual={actual} expected={expected}"
    );
}

#[test]
fn fixture_is_strict_model_free_and_oracle_backed() {
    let fixture = fixture();
    assert_eq!(
        fixture.schema,
        "pulsarmlx.fixture.qwen3moe-ffn-generation-v1"
    );
    assert_eq!(fixture.schema_version, 1);
    assert_eq!(fixture.fixture_id, "qwen3moe-ffn-generation-v1");
    assert!(fixture.model_free);
    assert!(!fixture.uses_checkpoint_payload_bytes);
    assert_eq!(fixture.contract_id, QWEN3MOE_FULL_GRAPH_CONTRACT_ID);
    assert_eq!(fixture.execution_dimensions.dtype, "f32");
    assert_eq!(fixture.operation_order.len(), 10);
    assert_eq!(fixture.oracle.steps.len(), fixture.steps.len());
    assert!(fixture.oracle.independently_generated);
    assert_eq!(
        fixture.oracle.generator,
        "standalone_f32_scalar_reference_v1"
    );
    validate_qwen3moe_synthetic_fixture(&fixture).expect("fixture contract is valid");
}

#[test]
fn computed_ffn_logits_match_independent_oracle_and_drive_greedy() {
    let fixture = fixture();
    let result =
        run_qwen3moe_synthetic_generation(&fixture, &request(&fixture), &CancellationToken::new())
            .expect("synthetic Qwen FFN generation succeeds");

    assert!(result.evaluated);
    assert!(!result.fallback_used);
    assert_eq!(result.generated_token_ids(), [7, 9, 0]);
    assert_eq!(result.full_token_ids(), [1, 2, 7, 9, 0]);
    assert_eq!(result.termination_reason().as_str(), "eos_token");
    assert_eq!(result.steps.len(), 3);
    for (actual, expected) in result.steps.iter().zip(fixture.oracle.steps.iter()) {
        assert_eq!(actual.selected_expert_ids, expected.selected_expert_ids);
        for (a, e) in actual
            .normalized_selected_probabilities
            .iter()
            .zip(expected.normalized_selected_probabilities.iter())
        {
            assert_close(*a, *e);
        }
        for (a, e) in actual.residual.iter().zip(expected.residual.iter()) {
            assert_close(*a, *e);
        }
        for (a, e) in actual.logits.iter().zip(expected.logits.iter()) {
            assert_close(*a, *e);
        }
    }
}

#[test]
fn tie_ordering_is_probability_descending_then_expert_id_ascending() {
    assert_eq!(
        deterministic_top_k(&[0.5, 0.5, 0.5, 0.4], 2).unwrap(),
        [0, 1]
    );
    assert_eq!(
        deterministic_top_k(&[0.5, 0.9, 0.9, 0.4], 2).unwrap(),
        [1, 2]
    );
}

#[test]
fn selected_probabilities_are_renormalized_after_full_softmax() {
    let fixture = fixture();
    let result =
        run_qwen3moe_synthetic_generation(&fixture, &request(&fixture), &CancellationToken::new())
            .unwrap();
    for step in &result.steps {
        let sum: f32 = step.normalized_selected_probabilities.iter().sum();
        assert_close(sum, 1.0);
        let selected_sum: f32 = step.selected_probabilities.iter().sum();
        assert!(selected_sum < 1.0);
    }
}

#[test]
fn unknown_operation_order_is_rejected_before_execution() {
    let mut fixture = fixture();
    fixture.operation_order.swap(0, 1);
    assert!(validate_qwen3moe_synthetic_fixture(&fixture).is_err());
}

#[test]
fn duplicate_experts_wrong_top_k_and_non_finite_values_are_rejected() {
    let mut duplicate = fixture();
    duplicate.oracle.steps[0].selected_expert_ids[1] =
        duplicate.oracle.steps[0].selected_expert_ids[0];
    assert!(validate_qwen3moe_synthetic_fixture(&duplicate).is_err());

    let mut wrong_top_k = fixture();
    wrong_top_k.execution_dimensions.top_k = 1;
    assert!(validate_qwen3moe_synthetic_fixture(&wrong_top_k).is_err());

    let mut non_finite = fixture();
    non_finite.tensors.router_weight[0][0] = f32::NAN;
    assert!(validate_qwen3moe_synthetic_fixture(&non_finite).is_err());
}

#[test]
fn payload_byte_markers_are_rejected_by_deny_unknown_fields() {
    let mut value: Value = serde_json::from_str(FIXTURE).unwrap();
    value["payload_bytes"] = Value::String("forbidden".to_owned());
    let mutated = serde_json::to_vec(&value).unwrap();
    assert!(parse_qwen3moe_synthetic_fixture(&mutated).is_err());
}

#[test]
fn mutation_mismatch_cannot_fall_back_to_fixture_fed_logits() {
    let mut fixture = fixture();
    fixture.steps[0].input[0] += 0.25;
    let error =
        run_qwen3moe_synthetic_generation(&fixture, &request(&fixture), &CancellationToken::new())
            .unwrap_err();
    assert_eq!(error.code(), "oracle_mismatch");
}

#[test]
fn prompt_token_bounds_and_cancellation_are_preserved() {
    assert_eq!(
        GenerationRequest::try_new(Vec::new(), 1, None)
            .unwrap_err()
            .code(),
        "invalid_prompt_length"
    );
    assert_eq!(
        GenerationRequest::try_new(vec![1; MAX_PROMPT_TOKENS + 1], 1, None)
            .unwrap_err()
            .code(),
        "invalid_prompt_length"
    );
    assert_eq!(
        GenerationRequest::try_new(vec![1], 0, None)
            .unwrap_err()
            .code(),
        "invalid_max_new_tokens"
    );
    assert_eq!(
        GenerationRequest::try_new(vec![1], MAX_NEW_TOKENS + 1, None)
            .unwrap_err()
            .code(),
        "invalid_max_new_tokens"
    );

    let fixture = fixture();
    let request = request(&fixture);
    let before = CancellationToken::new();
    before.cancel();
    let error = run_qwen3moe_synthetic_generation(&fixture, &request, &before).unwrap_err();
    assert_eq!(error.code(), "cancelled");

    let during = run_qwen3moe_synthetic_generation_with_cancel_after_step(
        &fixture,
        &request,
        &CancellationToken::new(),
        Some(1),
    )
    .unwrap_err();
    assert_eq!(during.code(), "cancelled");
}
