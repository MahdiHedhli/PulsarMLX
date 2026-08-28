#!/usr/bin/env python3
"""Generate the cycle-3 repaired Event-06 Sequence-5 design authority."""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes
import generate_f017_event06_sequence05_design_v2 as v2

ROOT = v2.ROOT
CONTRACT_DIR = v2.CONTRACT_DIR
EVIDENCE_DIR = v2.EVIDENCE_DIR
READINESS = CONTRACT_DIR / "f017-corrected-oracle-event06-readiness-consumer-interface-v4.json"
INSTALL = CONTRACT_DIR / "f017-corrected-oracle-event06-live-installation-interface-v3.json"
MANIFEST = CONTRACT_DIR / "f017-corrected-oracle-event06-readiness-authority-manifest-v2.json"
PROVENANCE = CONTRACT_DIR / "f017-independent-review-transport-provenance-v2.json"
QUALIFICATION = CONTRACT_DIR / "f017-event06-sequence05-qualification-role-requirements-v1.json"

DEPENDENCY_ROLES = [
    "implementation_measurement", "scientific_access_contract", "checkpoint_identity_authority",
    "numerical_contract", "result_authority", "bridge_declaration", "readiness_interface",
    "live_installation_interface", "future_go_capability", "review_transport_provenance_contract",
    "qualification_role_requirements", "canonical_readiness_qualification",
    "installation_preparation_qualification", "failure_qualification", "no_access_rehearsal",
    "full_corpus_validation", "full_native_evidence", "challenge_result",
    "challenge_provenance", "opus_result", "sequence4_finding_disposition",
]
DECLARATION_PATH_ROLES = ["authority_manifest"] + DEPENDENCY_ROLES
PATH_FIELDS = [item for role in DECLARATION_PATH_ROLES for item in (f"{role}_path", f"{role}_sha256")]
REQUIRED = v2.STRING_FIELDS + v2.BOOL_FIELDS + v2.COUNT_FIELDS + v2.GIT_FIELDS + PATH_FIELDS
EXACT = deepcopy(v2.EXACT)
EXACT["schema"] = "pulsarmlx.f017.corrected-oracle-event06-execution-readiness-final-declaration/12.2.0"


def _write(target: Path, value: object, check: bool) -> None:
    raw = canonical_bytes(value)
    if check:
        if not target.is_file() or target.read_bytes() != raw:
            raise SystemExit(f"generated artifact drift: {target.relative_to(ROOT)}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)


def readiness() -> dict:
    value = deepcopy(v2.readiness())
    value.update({
        "schema": "pulsarmlx.f017.corrected-oracle-event06-readiness-consumer-interface/2.2.0",
        "required_fields": REQUIRED, "field_count": len(REQUIRED),
        "exact_predicates": EXACT,
        "manifest_contract": str(MANIFEST.relative_to(ROOT)),
        "review_transport_provenance_contract": str(PROVENANCE.relative_to(ROOT)),
        "qualification_role_requirements": str(QUALIFICATION.relative_to(ROOT)),
        "unresolved_claims_scope": "final successor claim ledger rows only; rejected historical cycles remain append-only history",
        "unresolved_findings_scope": "final Sequence-4 disposition rows plus current review findings",
    })
    value["exact_types"] = {
        "boolean": v2.BOOL_FIELDS, "git_object": v2.GIT_FIELDS,
        "nonnegative_integer": v2.COUNT_FIELDS,
        "repository_path": [field for field in PATH_FIELDS if field.endswith("_path")] + ["supersedes_path"],
        "sha256": [field for field in PATH_FIELDS if field.endswith("_sha256")] + ["supersedes_sha256", "bridge_digest"],
        "string": [field for field in v2.STRING_FIELDS if field not in {"supersedes_path", "supersedes_sha256", "bridge_digest"}],
    }
    return value


def manifest() -> dict:
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest-contract/1.1.0",
        "manifest_schema": "pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest/1.1.0",
        "required_keys": ["schema", "implementation_head", "implementation_tree", "binding_count", "bindings", "role_count", "roles", "result"],
        "bindings_type": "closed repository-relative-path-to-sha256 mapping",
        "roles_type": "closed role-to-{path,sha256} mapping",
        "required_roles": DEPENDENCY_ROLES, "role_count": len(DEPENDENCY_ROLES),
        "role_count_equals_roles_length": True, "binding_count_equals_bindings_length": True,
        "each_role_path_sha_must_equal_binding_entry": True,
        "binding_count_equals_role_count": True, "unknown_roles_permitted": False,
        "manifest_may_bind_itself": False, "manifest_may_bind_final_declaration": False,
        "final_declaration_requires_authority_manifest_path_and_sha256": True,
        "final_declaration_binds_manifest": True,
        "historical_supersedes_is_verified_outside_current_manifest": True,
        "terminal_index_may_bind_manifest_and_declaration": True,
        "terminal_index_is_readiness_input": False,
    }


def installation() -> dict:
    value = deepcopy(v2.installation())
    value["schema"] = "pulsarmlx.f017.corrected-oracle-event06-live-installation-interface/1.2.0"
    value["state_machine_contract"] = "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-installation-state-machine-v2.json"
    value["qualification_role_requirements"] = str(QUALIFICATION.relative_to(ROOT))
    return value


def provenance() -> dict:
    return {
        "schema": "pulsarmlx.f017.independent-review-transport-provenance-contract/1.1.0",
        "instance_schema": "pulsarmlx.f017.independent-review-transport-provenance/1.0.0",
        "required_fields": ["schema", "tool", "tool_version", "transport", "command", "requested_model", "provider_reported_model", "provider_session_metadata", "independent_attestation_source", "started_at_utc", "completed_at_utc", "exit_status", "request_path", "request_sha256", "response_path", "response_sha256", "normalized_result_path", "normalized_result_sha256", "reviewed_commit", "credentials_serialized", "result"],
        "challenge_provenance_role_must_conform": True,
        "provider_metadata_unavailable_policy": "UNRESOLVED",
        "self_report_alone_sufficient": False,
        "independent_attestation_source_required": True,
        "credentials_serialized": False,
    }


def qualification() -> dict:
    return {
        "schema": "pulsarmlx.f017.event06-sequence05-qualification-role-requirements/1.0.0",
        "roles": {
            "canonical_readiness_qualification": {"required": {"result": "PASS", "reconstructions": 20, "unique_sha_count": 1, "event_06_executed": False, "checkpoint_access": 0}},
            "installation_preparation_qualification": {"required": {"result": "PASS", "reconstructions": 20, "unique_identity_set_count": 1, "production_commit_success_calls": 0, "live_installations": 0}},
            "failure_qualification": {"required": {"result": "PASS", "mutation_floor": 320, "unexpected_passes": 0, "event_06_executed": False, "checkpoint_access": 0}},
            "no_access_rehearsal": {"required": {"result": "PASS", "terminal": "PACKAGE_START_ELIGIBLE_DRY_STOP", "checkpoint_access": 0, "numerical_operations": 0, "package_starts": 0}},
            "full_corpus_validation": {"required": {"result": "PASS", "unexplained_failures": 0, "ignored_failure_keys": 0, "external_coordinates_supported": True, "supersession_supported": True}},
            "full_native_evidence": {"required": {"result": "PASS", "required_native_skips": 0}},
            "challenge_result": {"required": {"blocking_findings": 0, "required_findings": 0, "unresolved_claims": 0}},
            "challenge_provenance": {"contract": str(PROVENANCE.relative_to(ROOT)), "required": {"result": "PASS", "exit_status": 0}},
            "opus_result": {"required": {"blocking_findings": 0, "required_findings": 0, "unresolved_claims": 0}},
            "sequence4_finding_disposition": {"contract": str(v2.FINDINGS.relative_to(ROOT)), "required": {"resolved": 8, "conceded": 0, "unresolved": 0}},
        },
        "unknown_roles_permitted": False,
        "all_requirements_mechanically_validated": True,
    }


def artifacts() -> dict[Path, object]:
    safety = {"checkpoint_root_resolved": False, "checkpoint_access": 0, "numerical_operations": 0, "live_installations": 0, "package_starts": 0, "ids_consumed": 0}
    return {
        READINESS: readiness(), INSTALL: installation(), MANIFEST: manifest(),
        PROVENANCE: provenance(), QUALIFICATION: qualification(),
        EVIDENCE_DIR / "f017-event06-v12-sequence05-readiness-field-census-v3.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-readiness-field-census/1.2.0",
            "consumer_schema": readiness()["schema"], "declaration_schema": readiness()["declaration_schema"],
            "field_count": len(REQUIRED), "required_fields": REQUIRED, "exact_types": readiness()["exact_types"],
            "exact_predicates": EXACT, "exact_predicate_count": len(EXACT),
            "exact_predicates_exhaustive_for_acceptance": True,
            "authority_manifest_binding_present": True, "schema_predicate_present": True,
            "unknown_keys_permitted": False, "aliases_permitted": False, "coercions_permitted": False,
            "result": "REPAIRED", "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-readiness-field-census-v2.json",
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-installation-state-machine-v2.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-installation-state-machine/1.1.0",
            "states": ["UNVALIDATED", "CANDIDATE", "PREPARED_VALIDATION_ONLY", "SYNTHETIC_INSTALLED", "PRODUCTION_INSTALLED", "TERMINAL_FAILURE"],
            "transitions": [
                {"from": "UNVALIDATED", "to": "CANDIDATE", "write": False},
                {"from": "CANDIDATE", "to": "PREPARED_VALIDATION_ONLY", "write": False},
                {"from": "CANDIDATE", "to": "SYNTHETIC_INSTALLED", "write": True, "scope": "synthetic temporary root"},
                {"from": "PREPARED_VALIDATION_ONLY", "to": "PRODUCTION_INSTALLED", "write": True, "requires": "same unexpired sealed future-GO capability"},
            ],
            "cross_posture_substitution": "REJECT", "sequence_5_terminal_state": "PREPARED_VALIDATION_ONLY",
            "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-installation-state-machine-v1.json",
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-consumer-matrix-v3.json": {
            **{key: value for key, value in v2.artifacts()[EVIDENCE_DIR / "f017-event06-v12-sequence05-consumer-matrix-v2.json"].items() if key != "rows"},
            "schema": "pulsarmlx.f017.event06-v12-sequence05-consumer-matrix/1.2.0",
            "rows": v2.artifacts()[EVIDENCE_DIR / "f017-event06-v12-sequence05-consumer-matrix-v2.json"]["rows"] + [
                {"consumer": "install_noncanonical_candidate", "allowed": ["CANDIDATE"], "produces": "SYNTHETIC_INSTALLED"},
            ],
            "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-consumer-matrix-v2.json",
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-authority-provenance-map-v3.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-authority-provenance-map/1.2.0",
            "manifest_contract": str(MANIFEST.relative_to(ROOT)), "dependency_roles": DEPENDENCY_ROLES,
            "layer_order": ["dependencies", "manifest", "final declaration", "terminal index"],
            "final_declaration_manifest_fields": ["authority_manifest_path", "authority_manifest_sha256"],
            "supersedes_manifest_membership_required": False, "self_references": 0, "future_references": 0,
            "result": "REPAIRED_ACYCLIC_BY_CONSTRUCTION",
            "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-authority-provenance-map-v2.json",
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-failure-matrix-v3.json": {
            **{key: value for key, value in v2.artifacts()[EVIDENCE_DIR / "f017-event06-v12-sequence05-failure-matrix-v2.json"].items() if key not in {"derivation", "minimum_mutations", "schema", "supersedes"}},
            "schema": "pulsarmlx.f017.event06-v12-sequence05-failure-matrix/1.2.0",
            "minimum_mutations": 320,
            "derivation": {"readiness_deletions": len(REQUIRED), "readiness_types": len(REQUIRED), "acceptance_predicates": len(EXACT), "alternate_encoding_alias_binding_floor": 18, "installation_and_race_floor": 100, "total": 320},
            "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-failure-matrix-v2.json",
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-no-access-qualification-plan-v3.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-no-access-qualification-plan/1.2.0",
            "real_consumer_functions": ["validate_event06_readiness_declaration_v2", "build_identity_candidate_from_readiness", "validate_candidate_triple", "_validate_producer", "bank_candidate", "install_noncanonical_candidate", "validate_installed_triple", "prepare_production_installation", "validate_prepared_production_installation", "validate_prepared_package_start_eligibility", "derive_bridge_execution_plan", "validate_primary", "validate_secondary", "validate_result_authority"],
            "interposed_primitives": ["Path.resolve for checkpoint coordinates", "Path.stat", "os.open", "os.pread", "mmap.mmap", "checkpoint hash stream", "tensor source", "numerical execute", "bank_exclusive live root", "ID consumption"],
            "spy_policy": {"binds_real_consumer_signatures": True, "bypasses_consumer_signatures": False, "fails_if_prohibited_capability_reached": True, "synthetic_temporary_roots_only": True, "original_checkpoint_name_or_root_discovery": "PROHIBITED"},
            "checkpoint_coordinate": "NONEXISTENT_SENTINEL_ONLY", "readiness_reconstructions": 20,
            "installation_reconstructions": 20, "minimum_mutations": 320,
            "production_commit_success_calls": 0, "required_terminal": "PACKAGE_START_ELIGIBLE_DRY_STOP",
            "safety": safety, "result": "REPAIRED",
            "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-no-access-qualification-plan-v2.json",
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-design-graph-state-v3.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-design-graph-state/1.2.0",
            "nodes": [{"id": "D0", "status": "PASS"}, {"id": "D1", "status": "REPAIR_REQUIRED"}, {"id": "D2", "status": "REPAIR_REQUIRED"}, {"id": "D3", "status": "REPAIR_REQUIRED"}],
            "running_nodes": 0, "opus_cycle": 2, "current_cycle_blocking_findings": 1,
            "current_cycle_required_findings": 6, "current_cycle_unresolved_claims": 2,
            "historical_rejected_cycles": 2, "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-design-graph-state-v2.json",
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-design-claim-ledger-v3.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-design-claim-ledger/1.2.0",
            "claims": [{"claim_id": item, "state": "CHALLENGED"} for item in ["S5-DESIGN-READINESS", "S5-DESIGN-INSTALL", "S5-DESIGN-NOACCESS"]],
            "claim_count": 3, "supported": 0, "challenged": 3, "unresolved": 0,
            "counter_scope": "current successor rows only", "historical_rejected_cycles": 2,
            "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-design-claim-ledger-v2.json",
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
