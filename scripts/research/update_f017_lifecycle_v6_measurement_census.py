#!/usr/bin/env python3
"""Apply the reviewed cycle-02 measurement-census correction to model V6."""
from __future__ import annotations

from f017_lifecycle_semantics_v6 import MODEL_PATH, canonical_json_bytes, load_json

REMOVE = {"scripts/research/f017_numerical_capability_structural_check_v1.py"}
ADD = {
    "scripts/research/f017_lifecycle_artifact_v6.py",
    "scripts/research/f017_corrected_oracle_compare_v6.py",
    "scripts/research/generate_f017_corrected_oracle_inert_v6.py",
    "scripts/research/generate_f017_corrected_oracle_scientific_access_v6.py",
    "scripts/research/qualify_f017_corrected_oracle_target_adapters_v6.py",
    "scripts/research/qualify_f017_lifecycle_v6.py",
    "scripts/research/rehearse_f017_corrected_oracle_event04_v6.py",
    "scripts/research/generate_f017_numerical_capability_authorities_v1.py",
    "scripts/research/qualify_f017_numerical_capability_policy_v1.py",
    "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-active-generation-v1.json",
    "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-primary-capability-v6.json",
    "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-secondary-capability-v6.json",
    "specs/017-rust-native-inference-runtime/fixtures/f017-corrected-full-checkpoint-oracle-inert-authorization-v6.json",
    "specs/017-rust-native-inference-runtime/templates/f017-corrected-oracle-event-04-operator-go-template-v1.json",
    "scripts/research/test_f017_lifecycle_semantics_v6.py",
    "scripts/research/test_f017_lifecycle_v6_implementation.py",
    "scripts/research/update_f017_lifecycle_v6_measurement_census.py",
    "scripts/research/extract_f017_corrected_oracle_target_sources_v6.py",
    "scripts/research/retire_f017_corrected_oracle_legacy_surfaces_v6.py",
    "scripts/research/validate_f017_historical_corrected_oracle_authorities_v6.py",
    "scripts/research/generate_f017_lifecycle_v5_authorities.py",
    "scripts/research/validate_f017_lifecycle_semantic_authority_v5.py",
    "scripts/research/generate_f017_corrected_oracle_lifecycle_v4_specs.py",
    "scripts/research/validate_f017_corrected_oracle_lifecycle_v4.py",
}


def _failure_transition(identifier: str, source: str, destination: str, outcome: str) -> dict:
    return {
        "actor": "EVIDENCE_WRITER",
        "artifacts_created": ["evidence_failure"],
        "destination": destination,
        "failure_outcome": "EVIDENCE_BANKING_FAILURE",
        "id": identifier,
        "identities_introduced": ["evidence_failure_id", "evidence_failure_sha256"],
        "ledger_effects": {},
        "operation": f"BANK_{outcome}",
        "path_effects": [],
        "preconditions": [f"{outcome}_DETECTED"],
        "prohibited_side_effects": ["UNMODELED_STATE_ADVANCE", "CHECKPOINT_ACCESS_BEYOND_DURABLE_PREFIX"],
        "source": source,
    }


def main() -> int:
    model = load_json(MODEL_PATH)
    entries = set(model["measurement_authority"]["required_entries"])
    entries.difference_update(REMOVE)
    entries.update(ADD)
    model["measurement_authority"]["required_entries"] = sorted(entries)
    document = model["authorization_document"]
    document["pinned_values"]["authority_scope"] = "PRODUCTION"
    document["pinned_values"].update({
        "package_accounting_class": "CORRECTED_ORACLE_PACKAGE_ATTEMPT_LEDGER",
        "primary_accounting_class": "CORRECTED_ORACLE_PRIMARY_EVENT_LEDGER",
        "secondary_accounting_class": "CORRECTED_ORACLE_SECONDARY_EVENT_LEDGER",
    })
    document["live_id_forbidden_markers"] = ["INERT", "FIXTURE", "TEST", "SYNTHETIC", "REHEARSAL"]
    model["serialization"]["finite_float_encoding"] = "IEEE754_BINARY64_HEX_STRING_LOWERCASE"
    model["artifact_bank_order_semantics"] = "DECLARED_LIST_ORDER_IS_DURABLE_ORDER_LATER_BINDS_ALL_EARLIER_SIBLING_SHAS"
    model["artifact_path_descriptors"]["evidence_failure"]["leaf_identity"] = "evidence_failure_id"
    model["ledger_targets"]["HISTORICAL_REAL_PAYLOAD_LEDGER"]["authority_commit"] = "96503db702e95c7a08746924a208304819139803"

    authorization_identities = {
        key for key in document["top_level_keys"]
        if key not in {"schema", "package", "primary", "secondary", "context", "limits", "shards", "state", "live"}
    }
    authorization_identities.update(f"package_{key}" for key in document["package_keys"])
    for consumer in ("primary", "secondary"):
        authorization_identities.update(f"{consumer}_{key}" for key in document["consumer_keys"])
    authorization_identities.update(document["context_keys"])
    authorization_identities.update(document["limits_keys"])
    authorization_identities.update({"authorization_schema", "authorization_state", "authorization_live"})

    transitions = model["transitions"]
    by_id = {transition["id"]: transition for transition in transitions}
    by_id["T01_APPROVE"]["identities_introduced"] = sorted(authorization_identities | {"operator_approval_sha256"})
    for transition in transitions:
        if transition["artifacts_created"] == ["evidence_failure"]:
            transition["identities_introduced"] = ["evidence_failure_id", "evidence_failure_sha256"]
    additions = [
        _failure_transition("F02_PREFLIGHT_FAILURE", "OPERATOR_APPROVED", "PRE_MINT_TERMINAL_FAILURE", "PREFLIGHT_FAILURE"),
        _failure_transition("F03_CANDIDATE_RENDER_FAILURE", "PREFLIGHT_PASS", "PRE_MINT_TERMINAL_FAILURE", "CANDIDATE_RENDER_FAILURE"),
        _failure_transition("F04_PRIMARY_CANDIDATE_VALIDATION_FAILURE", "CANDIDATE_RENDERED", "PRE_MINT_TERMINAL_FAILURE", "PRIMARY_CANDIDATE_VALIDATION_FAILURE"),
        _failure_transition("F05_SECONDARY_CANDIDATE_VALIDATION_FAILURE", "PRIMARY_CANDIDATE_VALIDATED", "PRE_MINT_TERMINAL_FAILURE", "SECONDARY_CANDIDATE_VALIDATION_FAILURE"),
        _failure_transition("F07_INSTALLATION_READBACK_FAILURE", "AUTHORIZATION_INSTALLED", "INSTALLATION_TERMINAL_FAILURE", "INSTALLATION_READBACK_FAILURE"),
        _failure_transition("F09_COORDINATOR_HANDSHAKE_FAILURE", "INSTALLED_AUTHORIZATION_REVALIDATED", "HANDSHAKE_TERMINAL_FAILURE", "COORDINATOR_HANDSHAKE_FAILURE"),
        _failure_transition("F11_PACKAGE_DURABLE_START_FAILURE", "PACKAGE_CLAIMED", "PACKAGE_PRE_START_TERMINAL_FAILURE", "PACKAGE_DURABLE_START_FAILURE"),
    ]
    existing = set(by_id)
    transitions.extend(item for item in additions if item["id"] not in existing)
    model["failure_routes"] = {
        "T01_APPROVE": "F00_PRE_MINT_FAILURE",
        "T02_PREFLIGHT": "F02_PREFLIGHT_FAILURE",
        "T03_RENDER_CANDIDATE": "F03_CANDIDATE_RENDER_FAILURE",
        "T04_PRIMARY_VALIDATE_CANDIDATE": "F04_PRIMARY_CANDIDATE_VALIDATION_FAILURE",
        "T05_SECONDARY_VALIDATE_CANDIDATE": "F05_SECONDARY_CANDIDATE_VALIDATION_FAILURE",
        "T06_INSTALL_AUTHORIZATION": "F06_INSTALLATION_FAILURE",
        "T07_BANK_INSTALL_RECEIPT": "F07_INSTALLATION_READBACK_FAILURE",
        "T08_REVALIDATE_INSTALLED": "F08_HANDSHAKE_FAILURE",
        "T09_HANDSHAKE": "F09_COORDINATOR_HANDSHAKE_FAILURE",
        "T10_CLAIM_PACKAGE": "F10_PACKAGE_PRE_START_FAILURE",
        "T11_START_PACKAGE": "F11_PACKAGE_DURABLE_START_FAILURE",
        "T12_START_PRIMARY": "T17_CLOSE_PRE_PRIMARY_FAILURE",
        "T14_START_SECONDARY": "T17_CLOSE_SECONDARY_PRE_START_FAILURE",
        "T16_COMPARE_SUCCESS": "T16F_COMPARE_FAILURE",
    }
    MODEL_PATH.write_bytes(canonical_json_bytes(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
