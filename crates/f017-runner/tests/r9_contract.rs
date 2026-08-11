use f017_runner::json::parse_json_no_duplicates;
use serde::Deserialize;
use std::fs;
use std::path::Path;

#[derive(Deserialize)]
struct Contract {
    schema: String,
    contract_version: String,
    status: String,
    exact_scaffold: String,
    per_matvec_contract: String,
    required_repeats: usize,
    intermediate: Bounds,
    #[serde(rename = "final")]
    final_bounds: Bounds,
    exact_requirements: ExactRequirements,
    classification: std::collections::BTreeMap<String, String>,
    greedy_applicability: String,
    retuning_policy: String,
    review_status: String,
}

#[derive(Deserialize)]
struct Bounds {
    max_absolute_error: f64,
    rmse: f64,
    cosine_similarity_minimum: f64,
}

#[derive(Deserialize)]
struct ExactRequirements {
    selected_positions: bool,
    dsa_indexer_selection: bool,
    signed_zero: bool,
    deterministic_candidate_bits: bool,
    unexpected_fallback_count: u64,
    backend_error_count: u64,
    in_flight_after_teardown: u64,
}

#[test]
fn r9_contract_is_frozen_narrow_and_fail_closed() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let bytes = fs::read(
        root.join("specs/017-rust-native-inference-runtime/contracts/production-r9-tier-b-v1.json"),
    )
    .unwrap();
    let value: serde_json::Value = parse_json_no_duplicates(&bytes).unwrap();
    let contract: Contract = serde_json::from_value(value).unwrap();
    assert_eq!(
        contract.schema,
        "pulsarmlx.f017.production-r9-tier-b-contract"
    );
    assert_eq!(contract.contract_version, "f017-production-r9-tier-b-v1");
    assert_eq!(contract.status, "frozen_before_production_r9_execution");
    assert_eq!(contract.exact_scaffold, "f017-r9-mla-dsa-exact-v1");
    assert_eq!(
        contract.per_matvec_contract,
        "f017-production-expert-tier-b-v1"
    );
    assert_eq!(contract.required_repeats, 10);
    assert_eq!(contract.intermediate.max_absolute_error, 2_f64.powi(-8));
    assert_eq!(contract.intermediate.rmse, 2_f64.powi(-9));
    assert!(contract.intermediate.cosine_similarity_minimum >= 0.999999);
    let final_bounds = contract.final_bounds;
    assert_eq!(final_bounds.max_absolute_error, 2_f64.powi(-7));
    assert_eq!(final_bounds.rmse, 2_f64.powi(-8));
    assert!(final_bounds.cosine_similarity_minimum >= 0.99999);
    assert!(contract.exact_requirements.selected_positions);
    assert!(contract.exact_requirements.dsa_indexer_selection);
    assert!(contract.exact_requirements.signed_zero);
    assert!(contract.exact_requirements.deterministic_candidate_bits);
    assert_eq!(contract.exact_requirements.unexpected_fallback_count, 0);
    assert_eq!(contract.exact_requirements.backend_error_count, 0);
    assert_eq!(contract.exact_requirements.in_flight_after_teardown, 0);
    assert_eq!(
        contract.classification["pass"],
        "numerically_qualified_greedy_not_applicable"
    );
    assert_eq!(contract.greedy_applicability, "not_applicable");
    assert!(contract
        .retuning_policy
        .starts_with("never mutate this version"));
    assert_eq!(
        contract.review_status,
        "pending_adversarial_numerical_review"
    );
}
