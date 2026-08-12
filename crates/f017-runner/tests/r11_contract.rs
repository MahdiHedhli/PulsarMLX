use f017_runner::json::parse_json_no_duplicates;
use f017_runner::numerical_classification::{
    validate_classification_applicability, GreedyApplicability, GreedyIdentityEvidence,
    NumericalClassification,
};
use serde_json::Value;
use std::fs;
use std::path::Path;

#[test]
fn r11_contract_freezes_applicable_greedy_identity_before_candidate_execution() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let bytes =
        fs::read(root.join(
            "specs/017-rust-native-inference-runtime/contracts/production-r11-tier-b-v1.json",
        ))
        .unwrap();
    let contract: Value = parse_json_no_duplicates(&bytes).unwrap();
    assert_eq!(
        contract["contract_version"],
        "f017-production-r11-tier-b-v1"
    );
    assert_eq!(
        contract["status"],
        "frozen_before_production_candidate_execution"
    );
    assert_eq!(contract["required_repeats"], 10);
    assert_eq!(contract["greedy_applicability"], "applicable");
    assert_eq!(
        contract["classification"]["pass"],
        "numerically_qualified_greedy_identical"
    );
    assert_eq!(
        contract["classification"]["top_k_or_argmax_divergence"],
        "numerically_failed"
    );
    assert_eq!(
        contract["logit_contract"]["threshold_fit_to_observed_candidate"],
        false
    );
}

#[test]
fn r11_greedy_classification_fails_closed() {
    let exact = GreedyIdentityEvidence {
        top_k_ids_exact: true,
        argmax_exact: true,
    };
    assert!(validate_classification_applicability(
        NumericalClassification::NumericallyQualifiedGreedyIdentical,
        GreedyApplicability::Applicable,
        Some(&exact),
    )
    .is_ok());

    let changed = GreedyIdentityEvidence {
        top_k_ids_exact: false,
        argmax_exact: false,
    };
    assert!(validate_classification_applicability(
        NumericalClassification::NumericallyFailed,
        GreedyApplicability::Applicable,
        Some(&changed),
    )
    .is_ok());
    assert!(validate_classification_applicability(
        NumericalClassification::NumericallyQualifiedGreedyNotApplicable,
        GreedyApplicability::Applicable,
        Some(&changed),
    )
    .is_err());
}
