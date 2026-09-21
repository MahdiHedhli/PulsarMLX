#!/usr/bin/env python3
"""Generate the cycle-4 closed Event-06 Sequence-5 design authority."""
from __future__ import annotations

import argparse
from copy import deepcopy

from f017_canonical_serialization_v10 import canonical_bytes
import generate_f017_event06_sequence05_design_v3 as v3

ROOT = v3.ROOT
CONTRACT_DIR = v3.CONTRACT_DIR
EVIDENCE_DIR = v3.EVIDENCE_DIR
READINESS = CONTRACT_DIR / "f017-corrected-oracle-event06-readiness-consumer-interface-v5.json"
INSTALL = CONTRACT_DIR / "f017-corrected-oracle-event06-live-installation-interface-v4.json"
MANIFEST = CONTRACT_DIR / "f017-corrected-oracle-event06-readiness-authority-manifest-v3.json"
PROVENANCE = CONTRACT_DIR / "f017-independent-review-transport-provenance-v3.json"
QUALIFICATION = CONTRACT_DIR / "f017-event06-sequence05-qualification-role-requirements-v2.json"


def _write(target, value, check: bool) -> None:
    raw = canonical_bytes(value)
    if check:
        if not target.is_file() or target.read_bytes() != raw:
            raise SystemExit(f"generated artifact drift: {target.relative_to(ROOT)}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)


def readiness() -> dict:
    value = deepcopy(v3.readiness())
    value.update({
        "schema": "pulsarmlx.f017.corrected-oracle-event06-readiness-consumer-interface/2.3.0",
        "manifest_contract": str(MANIFEST.relative_to(ROOT)),
        "review_transport_provenance_contract": str(PROVENANCE.relative_to(ROOT)),
        "qualification_role_requirements": str(QUALIFICATION.relative_to(ROOT)),
        "challenge_reproducibility_policy": "current reviewed commit plus mechanical finding-disposition reproduction required",
    })
    return value


def manifest() -> dict:
    value = deepcopy(v3.manifest())
    value["schema"] = "pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest-contract/1.2.0"
    value["manifest_schema"] = "pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest/1.2.0"
    value["role_count"] = len(v3.DEPENDENCY_ROLES)
    value["required_roles"] = v3.DEPENDENCY_ROLES
    value["instance_validation_algorithm"] = [
        "require exact key census", "require exact role census and role_count",
        "require each role path/sha pair to equal one bindings entry",
        "require binding_count equals role_count equals mapping lengths",
        "resolve every path without symlink/traversal and verify SHA",
        "reject self/final-declaration/future dependency",
    ]
    return value


def installation() -> dict:
    value = deepcopy(v3.installation())
    value["schema"] = "pulsarmlx.f017.corrected-oracle-event06-live-installation-interface/1.3.0"
    value["phase_order"] = ["UNVALIDATED", "CANDIDATE", "PREPARED_VALIDATION_ONLY", "PRODUCTION_INSTALLED"]
    value["state_machine_contract"] = "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-installation-state-machine-v3.json"
    value["qualification_role_requirements"] = str(QUALIFICATION.relative_to(ROOT))
    return value


def provenance() -> dict:
    value = deepcopy(v3.provenance())
    value["schema"] = "pulsarmlx.f017.independent-review-transport-provenance-contract/1.2.0"
    value["accepted_independent_attestation_sources"] = {
        "AGY_JSON_ENVELOPE_CONVERSATION_ID_STATUS_DURATION_USAGE": ["conversation_id", "status=SUCCESS", "duration_seconds", "turn count"],
        "CLAUDE_JSON_ENVELOPE_SESSION_ID_CANONICAL_MODEL_STATUS_USAGE": ["session_id", "canonical model", "terminal_reason=completed", "permission_denials=0"],
    }
    value["attestation_must_be_outside_reviewer_wording"] = True
    value["instance_must_be_canonical"] = True
    return value


def qualification() -> dict:
    roles = {
        "implementation_measurement": {"required": {"result": "PASS"}, "cross_bindings": ["implementation_head", "implementation_tree"]},
        "scientific_access_contract": {"required": {"active_generation": "V12"}},
        "checkpoint_identity_authority": {"required": {"generation": "V12"}},
        "numerical_contract": {"required": {"numerical_authority": "V4"}},
        "result_authority": {"required": {"generation": "V11"}},
        "bridge_declaration": {"required": {"result": "ACCEPTED"}, "cross_bindings": ["bridge_digest"]},
        "readiness_interface": {"required": {"schema": readiness()["schema"], "canonical_bytes_required": True}},
        "live_installation_interface": {"required": {"schema": installation()["schema"], "durable_commit_authorized_in_sequence_5": False}},
        "future_go_capability": {"required": {"sequence_5_factory_available": False, "attempts": 1, "retries": 0, "resume": False}},
        "review_transport_provenance_contract": {"required": {"schema": provenance()["schema"], "self_report_alone_sufficient": False}},
        "qualification_role_requirements": {"required": {"schema": "pulsarmlx.f017.event06-sequence05-qualification-role-requirements/1.1.0", "role_scope": "all manifest dependency roles"}},
        "canonical_readiness_qualification": {"required": {"result": "PASS", "reconstructions": 20, "unique_sha_count": 1, "event_06_executed": False, "checkpoint_access": 0}},
        "installation_preparation_qualification": {"required": {"result": "PASS", "reconstructions": 20, "unique_identity_set_count": 1, "production_commit_success_calls": 0, "live_installations": 0}},
        "failure_qualification": {"required": {"result": "PASS", "mutation_floor": 320, "unexpected_passes": 0, "event_06_executed": False, "checkpoint_access": 0}},
        "no_access_rehearsal": {"required": {"result": "PASS", "terminal": "PACKAGE_START_ELIGIBLE_DRY_STOP", "checkpoint_access": 0, "numerical_operations": 0, "package_starts": 0}},
        "full_corpus_validation": {"required": {"result": "PASS", "unexplained_failures": 0, "ignored_failure_keys": 0, "external_coordinates_supported": True, "supersession_supported": True, "historical_failures_enumerated": True}},
        "full_native_evidence": {"required": {"result": "PASS", "required_native_skips": 0}, "field_equals": {"run_id": "full_native_run"}},
        "challenge_result": {"required": {"blocking_findings": 0, "required_findings": 0, "unresolved_claims": 0, "reviewed_commit_exact": True, "reproduction_result": "PASS"}, "field_equals": {"verdict": "gemini_verdict"}},
        "challenge_provenance": {"contract": str(PROVENANCE.relative_to(ROOT)), "required": {"result": "PASS", "exit_status": 0}},
        "opus_result": {"required": {"blocking_findings": 0, "required_findings": 0, "unresolved_claims": 0, "reviewed_commit_exact": True}, "field_equals": {"global_verdict": "opus_verdict"}},
        "sequence4_finding_disposition": {"contract": str(v3.v2.FINDINGS.relative_to(ROOT)), "required": {"resolved": 8, "conceded": 0, "unresolved": 0, "false_verification_disposition": "SUPERSEDED_BY_REPRODUCIBLE_CURRENT_CHALLENGE"}},
    }
    return {
        "schema": "pulsarmlx.f017.event06-sequence05-qualification-role-requirements/1.1.0",
        "role_scope": "all manifest dependency roles", "roles": roles,
        "role_count": len(roles), "role_count_equals_manifest_dependency_role_count": True,
        "unknown_roles_permitted": False, "all_requirements_mechanically_validated": False,
        "validation_required_before_acceptance": True,
    }


def artifacts() -> dict:
    safety = {"checkpoint_root_resolved": False, "checkpoint_access": 0, "numerical_operations": 0, "live_installations": 0, "package_starts": 0, "ids_consumed": 0}
    state_transitions = [
        {"from": "UNVALIDATED", "to": "CANDIDATE", "write": False},
        {"from": "CANDIDATE", "to": "PREPARED_VALIDATION_ONLY", "write": False},
        {"from": "CANDIDATE", "to": "SYNTHETIC_INSTALLED", "write": True, "scope": "synthetic temporary root"},
        {"from": "PREPARED_VALIDATION_ONLY", "to": "PRODUCTION_INSTALLED", "write": True, "requires": "same unexpired sealed future-GO capability"},
    ]
    for state in ["UNVALIDATED", "CANDIDATE", "PREPARED_VALIDATION_ONLY", "SYNTHETIC_INSTALLED", "PRODUCTION_INSTALLED"]:
        state_transitions.append({"from": state, "to": "TERMINAL_FAILURE", "write": False, "preserves_durable_prefix": True})
    base_failure = v3.artifacts()[EVIDENCE_DIR / "f017-event06-v12-sequence05-failure-matrix-v3.json"]
    derivation = {"readiness_deletions": len(v3.REQUIRED), "readiness_types": len(v3.REQUIRED), "acceptance_predicates": len(v3.EXACT), "alternate_encoding_alias_binding_floor": 18, "installation_and_race_floor": 100}
    computed_total = sum(derivation.values())
    return {
        READINESS: readiness(), INSTALL: installation(), MANIFEST: manifest(), PROVENANCE: provenance(), QUALIFICATION: qualification(),
        EVIDENCE_DIR / "f017-event06-v12-sequence05-installation-state-machine-v3.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-installation-state-machine/1.2.0",
            "states": ["UNVALIDATED", "CANDIDATE", "PREPARED_VALIDATION_ONLY", "SYNTHETIC_INSTALLED", "PRODUCTION_INSTALLED", "TERMINAL_FAILURE"],
            "transitions": state_transitions, "failure_outcome_count": len(v3.v2.installation()["exact_failure_outcomes"]),
            "cross_posture_substitution": "REJECT", "sequence_5_terminal_state": "PREPARED_VALIDATION_ONLY",
            "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-installation-state-machine-v2.json",
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-failure-matrix-v4.json": {
            **{key: value for key, value in base_failure.items() if key not in {"schema", "derivation", "minimum_mutations", "supersedes"}},
            "schema": "pulsarmlx.f017.event06-v12-sequence05-failure-matrix/1.3.0",
            "derivation": {**derivation, "total": computed_total}, "minimum_mutations": computed_total,
            "alternate_encoding_alias_binding_cases": ["noncanonical whitespace", "duplicate key", "unknown alias", "type coercion", "path substitution", "SHA substitution"],
            "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-failure-matrix-v3.json",
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-review-correction-index-v1.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-review-correction-index/1.0.0",
            "rows": [
                {"artifact": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-agy-design-cycle-02-provenance-v1.json", "finding": "NONCANONICAL_HISTORICAL_REVIEW_RECEIPT", "disposition": "PRESERVED_FAILURE_EVIDENCE_NOT_CURRENT_AUTHORITY"},
                {"artifact": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-agy-design-cycle-02-exact-response.md", "finding": "FALSE_ZERO_FINDING_ACCEPT", "disposition": "SUPERSEDED_BY_REPRODUCIBLE_CURRENT_CHALLENGE"},
            ],
            "row_count": 2, "ignored_failure_keys": 0, "historical_failures_enumerated": True,
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-no-access-qualification-plan-v4.json": {
            **{key: value for key, value in v3.artifacts()[EVIDENCE_DIR / "f017-event06-v12-sequence05-no-access-qualification-plan-v3.json"].items() if key not in {"schema", "real_consumer_functions", "supersedes"}},
            "schema": "pulsarmlx.f017.event06-v12-sequence05-no-access-qualification-plan/1.3.0",
            "existing_consumer_functions": ["build_identity_candidate_from_readiness", "validate_candidate_triple", "_validate_producer", "bank_candidate", "install_noncanonical_candidate", "validate_installed_triple"],
            "planned_successor_functions": ["validate_event06_readiness_declaration_v2", "prepare_production_installation", "validate_prepared_production_installation", "validate_prepared_package_start_eligibility", "derive_bridge_execution_plan", "validate_result_authority"],
            "wrapper_consumers": ["f017_corrected_oracle_primary_wrapper_v12.validate_identity_authority", "f017_corrected_oracle_secondary_wrapper_v12.validate_identity_authority"],
            "safety": safety,
            "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-no-access-qualification-plan-v3.json",
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-design-graph-state-v4.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-design-graph-state/1.3.0",
            "nodes": [{"id": "D0", "status": "PASS"}, {"id": "D1", "status": "REPAIR_REQUIRED"}, {"id": "D2", "status": "REPAIR_REQUIRED"}, {"id": "D3", "status": "REPAIR_REQUIRED"}],
            "running_nodes": 0, "opus_cycle": 3, "current_cycle_blocking_findings": 0,
            "current_cycle_required_findings": 5, "current_cycle_unresolved_claims": 2,
            "historical_rejected_cycles": 3, "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-design-graph-state-v3.json",
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-design-claim-ledger-v4.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-design-claim-ledger/1.3.0",
            "claims": [{"claim_id": item, "state": "CHALLENGED"} for item in ["S5-DESIGN-READINESS", "S5-DESIGN-INSTALL", "S5-DESIGN-NOACCESS"]],
            "claim_count": 3, "supported": 0, "challenged": 3, "unresolved": 0,
            "counter_scope": "current successor rows only", "historical_rejected_cycles": 3,
            "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-design-claim-ledger-v3.json",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for target, value in artifacts().items():
        _write(target, value, args.check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
