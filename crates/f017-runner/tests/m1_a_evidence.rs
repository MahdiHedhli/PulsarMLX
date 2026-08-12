use f017_runner::evidence::{Evidence, ResultClassification};
use f017_runner::json::{parse_json_no_duplicates, sha256_bytes};

const EXPECTED_SOURCE_SHA: &str = "42506d75b6b10d6fe3c1d804175f5dc5c9c69f45";
const EXPECTED_EVIDENCE_SHA256: &str =
    "aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805";

#[test]
fn banked_m1_a_evidence_passes_the_frozen_gate() {
    let bytes = include_bytes!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../docs/architecture/reviews/evidence/f017-m1-a-adapter-preflight-v1.json"
    ));
    assert_eq!(sha256_bytes(bytes), EXPECTED_EVIDENCE_SHA256);
    let evidence: Evidence = parse_json_no_duplicates(bytes).expect("duplicate-safe M1-A JSON");
    evidence.validate().expect("M1-A evidence schema");
    evidence
        .validate_success_ready()
        .expect("M1-A frozen PASS criteria");

    assert_eq!(evidence.identity.source_sha, EXPECTED_SOURCE_SHA);
    assert_eq!(evidence.identity.environment_kind, "production_reviewed");
    assert!(!evidence.identity.checkpoint.accessed);
    assert!(evidence.execution.layers.is_empty());
    assert_eq!(evidence.execution.storage.read_bytes, 0);
    assert_eq!(evidence.execution.storage.read_count, 0);
    assert_eq!(evidence.execution.dispatch.native, 1);
    assert_eq!(evidence.execution.dispatch.direct, 0);
    assert_eq!(evidence.execution.dispatch.qualification_scaffold, 0);
    assert_eq!(evidence.execution.dispatch.explicit_reference, 0);
    assert_eq!(evidence.execution.dispatch.fallback, 0);
    assert_eq!(evidence.execution.dispatch.errors, 0);
    assert_eq!(evidence.result.classification, ResultClassification::Pass);
}
