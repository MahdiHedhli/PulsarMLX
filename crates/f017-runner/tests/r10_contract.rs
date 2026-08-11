use f017_runner::json::parse_json_no_duplicates;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::fs;
use std::path::Path;

#[test]
fn r10_contract_is_frozen_before_candidate_and_fail_closed() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let v1_bytes =
        fs::read(root.join(
            "specs/017-rust-native-inference-runtime/contracts/production-r10-tier-b-v1.json",
        ))
        .unwrap();
    assert_eq!(
        format!("{:x}", Sha256::digest(&v1_bytes)),
        "dc11769af639a207c1528ae6756a315f585a04438d5e5f5115883e0323ebd81f"
    );
    let v1: Value = parse_json_no_duplicates(&v1_bytes).unwrap();
    assert_eq!(v1["contract_version"], "f017-production-r10-tier-b-v1");
    assert_eq!(
        v1["classification"]["routing_divergence"],
        "numerically_qualified_greedy_divergent"
    );

    let bytes =
        fs::read(root.join(
            "specs/017-rust-native-inference-runtime/contracts/production-r10-tier-b-v2.json",
        ))
        .unwrap();
    let contract: Value = parse_json_no_duplicates(&bytes).unwrap();
    assert_eq!(
        contract["contract_version"],
        "f017-production-r10-tier-b-v2"
    );
    assert_eq!(
        contract["status"],
        "reviewed_semantic_tightening_of_frozen_v1"
    );
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
    assert_eq!(contract["intermediate"], v1["intermediate"]);
    assert_eq!(contract["final"]["max_absolute_error"], 2_f64.powi(-4));
    assert_eq!(contract["final"]["rmse"], 2_f64.powi(-5));
    assert_eq!(contract["final"], v1["final"]);
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
        contract["classification"]["pass"],
        "numerically_qualified_greedy_not_applicable"
    );
    assert_eq!(contract["greedy_applicability"], "not_applicable");
    assert_eq!(
        contract["classification"]["routing_divergence"],
        "numerically_failed"
    );
    assert_eq!(
        contract["versioning"]["supersedes"],
        "f017-production-r10-tier-b-v1"
    );
    assert_eq!(contract["versioning"]["thresholds_unchanged"], true);
    assert_eq!(
        contract["review_status"],
        "accepted_after_contract_version_cleanup"
    );
}
