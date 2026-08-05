//! Contract tests for deterministic backend-neutral routed-MoE planning.
//!
//! Expected routes, weights, and outputs are fixed independently from the
//! implementation under test. They match the generated synthetic fixture in
//! `fixtures/mlx/routed-moe-v1.json` without reading that file at test time.

use backend::RoutingPlan;

const ROUTER_SCORES: [f64; 8] = [1.0, 3.0, 3.0, -1.0, 2.0, 3.0, 1.0, 4.0];
const EXPECTED_EXPERT_IDS: [u64; 4] = [1, 2, 3, 1];
const EXPECTED_WEIGHTS: [f64; 4] = [0.5, 0.5, 0.731_058_578_630_004_8, 0.268_941_421_369_995_2];
const SELECTED_EXPERT_OUTPUTS: [f64; 8] = [3.0, 2.0, 1.0, 2.0, 5.75, 3.5, -0.5, 5.5];
const EXPECTED_WEIGHTED_OUTPUT: [f64; 4] = [2.0, 2.0, 4.069_116_116_437_53, 4.037_882_842_739_99];

fn fixture_plan() -> RoutingPlan {
    RoutingPlan::try_softmax(&ROUTER_SCORES, 2, 4, 2)
        .expect("the bounded synthetic routing fixture is valid")
}

fn assert_close(actual: f64, expected: f64, tolerance: f64) {
    let error = (actual - expected).abs();
    assert!(
        error <= tolerance,
        "expected {expected}, got {actual}, absolute error {error} exceeded {tolerance}"
    );
}

#[test]
fn non_finite_router_scores_are_rejected() {
    for (label, non_finite) in [
        ("nan", f64::NAN),
        ("positive infinity", f64::INFINITY),
        ("negative infinity", f64::NEG_INFINITY),
    ] {
        let mut scores = ROUTER_SCORES;
        scores[3] = non_finite;
        let error = RoutingPlan::try_softmax(&scores, 2, 4, 2)
            .expect_err("non-finite routing scores must fail before planning");
        assert_eq!(error.code(), "non_finite_router_score", "case: {label}");
    }
}

#[test]
fn token_expert_and_top_k_bounds_are_checked() {
    let cases = [
        (0, 4, 2, "invalid_token_count"),
        (2, 0, 1, "invalid_expert_count"),
        (2, 4, 0, "invalid_top_k"),
        (2, 4, 5, "invalid_top_k"),
    ];

    for (token_count, expert_count, top_k, expected_code) in cases {
        let error = RoutingPlan::try_softmax(&ROUTER_SCORES, token_count, expert_count, top_k)
            .expect_err("invalid routing bounds must be rejected");
        assert_eq!(error.code(), expected_code);
    }
}

#[test]
fn score_cardinality_and_shape_product_are_checked() {
    let short = RoutingPlan::try_softmax(&ROUTER_SCORES[..7], 2, 4, 2)
        .expect_err("a short score matrix must be rejected");
    assert_eq!(short.code(), "routing_score_cardinality_mismatch");

    let extra = RoutingPlan::try_softmax(&[0.0; 9], 2, 4, 2)
        .expect_err("an overlong score matrix must be rejected");
    assert_eq!(extra.code(), "routing_score_cardinality_mismatch");

    let overflow = RoutingPlan::try_softmax(&[], u64::MAX, 2, 1)
        .expect_err("the score shape product must use checked arithmetic");
    assert_eq!(overflow.code(), "routing_score_count_overflow");
}

#[test]
fn routes_sort_by_score_descending_then_expert_id_ascending() {
    let plan = fixture_plan();

    assert_eq!(plan.token_count(), 2);
    assert_eq!(plan.expert_count(), 4);
    assert_eq!(plan.top_k(), 2);
    assert_eq!(plan.selected_expert_ids(), EXPECTED_EXPERT_IDS);

    let all_tied = RoutingPlan::try_softmax(&[7.0, 7.0, 7.0, 7.0], 1, 4, 3)
        .expect("finite exact ties are valid");
    assert_eq!(all_tied.selected_expert_ids(), [0, 1, 2]);
}

#[test]
fn repeated_experts_across_tokens_remain_valid_and_fetches_are_deduplicated() {
    let plan = fixture_plan();

    assert_eq!(plan.selected_expert_ids(), [1, 2, 3, 1]);
    assert_eq!(
        plan.selected_expert_ids()
            .iter()
            .filter(|&&expert_id| expert_id == 1)
            .count(),
        2
    );
    assert_eq!(plan.unique_expert_ids(), [1, 2, 3]);
}

#[test]
fn selected_softmax_weights_are_finite_positive_and_normalized_per_token() {
    let plan = fixture_plan();
    assert_eq!(plan.normalized_weights().len(), EXPECTED_WEIGHTS.len());

    for (&actual, &expected) in plan
        .normalized_weights()
        .iter()
        .zip(EXPECTED_WEIGHTS.iter())
    {
        assert!(actual.is_finite());
        assert!(actual > 0.0);
        assert_close(actual, expected, 1.0e-6);
    }
    for token_weights in plan.normalized_weights().chunks_exact(2) {
        assert_close(token_weights.iter().sum(), 1.0, 1.0e-6);
    }
}

#[test]
fn scalar_weighted_aggregation_matches_the_independent_oracle() {
    let actual = fixture_plan()
        .aggregate_selected_outputs(&SELECTED_EXPERT_OUTPUTS, 2)
        .expect("the exact token/slot/output payload is valid");

    assert_eq!(actual.len(), EXPECTED_WEIGHTED_OUTPUT.len());
    for (&actual, &expected) in actual.iter().zip(EXPECTED_WEIGHTED_OUTPUT.iter()) {
        assert_close(actual, expected, 1.0e-5);
    }
}

#[test]
fn aggregation_rejects_malformed_or_non_finite_selected_outputs() {
    let plan = fixture_plan();

    let zero_width = plan
        .aggregate_selected_outputs(&SELECTED_EXPERT_OUTPUTS, 0)
        .expect_err("a zero output width is invalid");
    assert_eq!(zero_width.code(), "invalid_routed_output_width");

    let short = plan
        .aggregate_selected_outputs(&SELECTED_EXPERT_OUTPUTS[..7], 2)
        .expect_err("a partial selected-expert payload is invalid");
    assert_eq!(short.code(), "routed_output_cardinality_mismatch");

    let mut non_finite = SELECTED_EXPERT_OUTPUTS;
    non_finite[4] = f64::NAN;
    let error = plan
        .aggregate_selected_outputs(&non_finite, 2)
        .expect_err("non-finite expert output must not enter accumulation");
    assert_eq!(error.code(), "non_finite_expert_output");
}
