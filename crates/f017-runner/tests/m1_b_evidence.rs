use f017_runner::evidence::{Evidence, ResultClassification, TensorMapStatus};
use f017_runner::json::{parse_json_no_duplicates, sha256_bytes};

const EXPECTED_SOURCE_SHA: &str = "b29202171a279cd3bb2ac2cf4dc6b3be7486019e";
const EXPECTED_EVIDENCE_SHA256: &str =
    "9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770";
const EXPECTED_CHECKPOINT_SET_SHA256: &str =
    "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee";
const EXPECTED_CATALOG_SHA256: &str =
    "0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0";

#[test]
fn banked_m1_b_evidence_passes_the_frozen_identity_and_isolation_gate() {
    let bytes = include_bytes!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../docs/architecture/reviews/evidence/f017-m1-b-checkpoint-identity-v1.json"
    ));
    assert_eq!(sha256_bytes(bytes), EXPECTED_EVIDENCE_SHA256);
    let evidence: Evidence = parse_json_no_duplicates(bytes).expect("duplicate-safe M1-B JSON");
    evidence.validate().expect("M1-B evidence schema");
    evidence
        .validate_success_ready()
        .expect("M1-B frozen PASS criteria");

    assert_eq!(evidence.identity.source_sha, EXPECTED_SOURCE_SHA);
    assert_eq!(evidence.identity.environment_kind, "production_reviewed");
    assert_eq!(evidence.admission.telemetry_source, "measured_host");
    assert!(evidence.identity.checkpoint.accessed);
    assert_eq!(
        evidence
            .identity
            .checkpoint
            .checkpoint_set_sha256
            .as_deref(),
        Some(EXPECTED_CHECKPOINT_SET_SHA256)
    );
    assert_eq!(
        evidence.identity.checkpoint.catalog_sha256.as_deref(),
        Some(EXPECTED_CATALOG_SHA256)
    );
    assert_eq!(evidence.identity.checkpoint.shards.len(), 6);
    assert_eq!(evidence.identity.checkpoint.tensor_count, Some(1_809));
    assert_eq!(
        evidence.identity.checkpoint.tensor_map.status,
        TensorMapStatus::Validated
    );
    assert_eq!(
        evidence
            .identity
            .checkpoint
            .tensor_map
            .validated_tensor_count,
        Some(1_809)
    );

    assert_eq!(evidence.input.mode, "checkpoint_identity");
    assert!(evidence.execution.layers.is_empty());
    assert!(evidence.execution.generated_token.is_none());
    assert_eq!(evidence.execution.dispatch.native, 0);
    assert_eq!(evidence.execution.dispatch.direct, 0);
    assert_eq!(evidence.execution.dispatch.qualification_scaffold, 0);
    assert_eq!(evidence.execution.dispatch.explicit_reference, 0);
    assert_eq!(evidence.execution.dispatch.fallback, 0);
    assert_eq!(evidence.execution.dispatch.errors, 0);
    assert_eq!(evidence.residency.compressed, 0);
    assert_eq!(evidence.residency.decoded_hot, 0);
    assert_eq!(evidence.residency.native_ready_hot, 0);
    assert_eq!(evidence.residency.transient, 0);
    assert!(evidence.lifecycle.reconciled);
    assert_eq!(evidence.result.classification, ResultClassification::Pass);
}
