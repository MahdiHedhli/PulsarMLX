use f017_runner::json::parse_json_no_duplicates;
use serde_json::Value;
use std::fs;
use std::path::Path;

#[test]
fn r10_contract_is_frozen_before_candidate_and_fail_closed() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let bytes =
        fs::read(root.join(
            "specs/017-rust-native-inference-runtime/contracts/production-r10-tier-b-v1.json",
        ))
        .unwrap();
    let contract: Value = parse_json_no_duplicates(&bytes).unwrap();
    assert_eq!(
        contract["contract_version"],
        "f017-production-r10-tier-b-v1"
    );
    assert_eq!(contract["status"], "frozen_before_production_r10_execution");
    assert_eq!(contract["required_repeats"], 10);
    assert_eq!(contract["router"]["selected_ids"], "exact");
    assert_eq!(
        contract["router"]["routing_weight_max_absolute_error"],
        0.00001
    );
    assert_eq!(
        contract["intermediate"]["max_absolute_error"],
        2_f64.powi(-6)
    );
    assert_eq!(contract["intermediate"]["rmse"], 2_f64.powi(-7));
    assert_eq!(contract["final"]["max_absolute_error"], 2_f64.powi(-4));
    assert_eq!(contract["final"]["rmse"], 2_f64.powi(-5));
    assert_eq!(
        contract["exact_requirements"]["unexpected_fallback_count"],
        0
    );
    assert_eq!(contract["exact_requirements"]["backend_error_count"], 0);
    assert_eq!(
        contract["exact_requirements"]["explicit_reference_dispatch_count"],
        0
    );
    assert_eq!(
        contract["review_status"],
        "pending_adversarial_numerical_review"
    );
}
