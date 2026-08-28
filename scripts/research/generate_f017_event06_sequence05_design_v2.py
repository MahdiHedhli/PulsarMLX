#!/usr/bin/env python3
"""Generate the repaired Event-06 Sequence-5 design authority."""
from __future__ import annotations

import argparse
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes
from generate_f017_event06_sequence05_design_v1 import ROOT, CONTRACT_DIR, EVIDENCE_DIR

READINESS = CONTRACT_DIR / "f017-corrected-oracle-event06-readiness-consumer-interface-v3.json"
INSTALL = CONTRACT_DIR / "f017-corrected-oracle-event06-live-installation-interface-v2.json"
GO_CAPABILITY = CONTRACT_DIR / "f017-corrected-oracle-event06-future-go-capability-v1.json"
MANIFEST = CONTRACT_DIR / "f017-corrected-oracle-event06-readiness-authority-manifest-v1.json"
FINDINGS = CONTRACT_DIR / "f017-event06-sequence4-finding-disposition-v1.json"
PROVENANCE = CONTRACT_DIR / "f017-independent-review-transport-provenance-v1.json"

ROLE_NAMES = [
    "implementation_measurement", "scientific_access_contract", "checkpoint_identity_authority",
    "numerical_contract", "result_authority", "bridge_declaration", "readiness_interface",
    "live_installation_interface", "future_go_capability", "canonical_readiness_qualification",
    "installation_preparation_qualification", "failure_qualification", "no_access_rehearsal",
    "full_corpus_validation", "full_native_evidence", "challenge_result",
    "challenge_provenance", "opus_result", "sequence4_finding_disposition",
]
PATH_FIELDS = [item for role in ROLE_NAMES for item in (f"{role}_path", f"{role}_sha256")]
STRING_FIELDS = [
    "schema", "declaration", "supersedes_path", "supersedes_sha256",
    "active_corrected_oracle_generation", "numerical_authority", "bridge_digest",
    "p1_attempt_2_authority_or_execution", "gemini_verdict", "opus_verdict",
    "independent_challenge_provenance", "exact_next_safe_action",
]
BOOL_FIELDS = [
    "historical_readiness_accepted", "current_executable_readiness", "event_04_retry",
    "event_05_retry", "sequence_4_event_06_retry_or_resume", "event_06_executed",
    "live_event_06_authorization_created", "live_v12_installation_created",
    "event_06_package_started", "original_checkpoint_root_resolved",
    "ready_for_fresh_corrected_full_checkpoint_oracle_event_06_go",
    "ready_to_prepare_p1_attempt_2_authorization",
]
COUNT_FIELDS = [
    "full_native_run", "required_native_skips", "blocking_findings",
    "non_blocking_required_findings", "unresolved_claims", "unresolved_findings",
    "primary_real_oracle_event06_executions", "secondary_real_oracle_event06_executions",
    "original_checkpoint_shard_opens", "original_checkpoint_identity_hash_reads",
    "original_checkpoint_payload_reads", "original_checkpoint_mmaps_or_tensor_reads",
    "event06_identities_consumed", "historical_master_ledger",
]
GIT_FIELDS = ["implementation_head", "implementation_tree"]
REQUIRED = STRING_FIELDS + BOOL_FIELDS + COUNT_FIELDS + GIT_FIELDS + PATH_FIELDS

EXACT = {
    "declaration": "F017_CORRECTED_ORACLE_EVENT06_EXECUTION_READINESS: ACCEPTED",
    "active_corrected_oracle_generation": "V12", "numerical_authority": "V4",
    "historical_readiness_accepted": True, "current_executable_readiness": True,
    "p1_attempt_2_authority_or_execution": "NONE",
    "gemini_verdict": "NO_UNRESOLVED_MATERIAL_CHALLENGE",
    "opus_verdict": "ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_06_EXECUTION_AUTHORIZATION_PREPARATION",
    "independent_challenge_provenance": "PASS",
    "event_04_retry": False, "event_05_retry": False,
    "sequence_4_event_06_retry_or_resume": False, "event_06_executed": False,
    "live_event_06_authorization_created": False, "live_v12_installation_created": False,
    "event_06_package_started": False, "primary_real_oracle_event06_executions": 0,
    "secondary_real_oracle_event06_executions": 0, "original_checkpoint_root_resolved": False,
    "original_checkpoint_shard_opens": 0, "original_checkpoint_identity_hash_reads": 0,
    "original_checkpoint_payload_reads": 0, "original_checkpoint_mmaps_or_tensor_reads": 0,
    "event06_identities_consumed": 0, "required_native_skips": 0, "blocking_findings": 0,
    "non_blocking_required_findings": 0, "unresolved_claims": 0, "unresolved_findings": 0,
    "historical_master_ledger": 175,
    "ready_for_fresh_corrected_full_checkpoint_oracle_event_06_go": True,
    "ready_to_prepare_p1_attempt_2_authorization": False,
    "exact_next_safe_action": "RETURN_TO_F017_PLANNER_AND_REQUEST_NEW_HUMAN_EVENT06_GO",
}


def _write(target: Path, value: object, check: bool) -> None:
    raw = canonical_bytes(value)
    if check:
        if not target.is_file() or target.read_bytes() != raw:
            raise SystemExit(f"generated artifact drift: {target.relative_to(ROOT)}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)


def readiness() -> dict:
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-event06-readiness-consumer-interface/2.1.0",
        "declaration_schema": "pulsarmlx.f017.corrected-oracle-event06-execution-readiness-final-declaration/12.2.0",
        "required_fields": REQUIRED, "field_count": len(REQUIRED),
        "exact_types": {
            "boolean": BOOL_FIELDS, "git_object": GIT_FIELDS,
            "nonnegative_integer": COUNT_FIELDS,
            "repository_path": [field for field in PATH_FIELDS if field.endswith("_path")] + ["supersedes_path"],
            "sha256": [field for field in PATH_FIELDS if field.endswith("_sha256")] + ["supersedes_sha256", "bridge_digest"],
            "string": [field for field in STRING_FIELDS if field not in {"supersedes_path", "supersedes_sha256", "bridge_digest"}],
        },
        "exact_predicates": EXACT, "exact_predicates_exhaustive_for_acceptance": True,
        "unknown_keys_permitted": False, "aliases_permitted": False,
        "coercions_permitted": False, "canonical_bytes_required": True,
        "historical_declarations_permitted_as_current": False,
        "historical_source_binding_policy": {
            "fields": ["supersedes_path", "supersedes_sha256"],
            "sha_verified": True, "manifest_membership_required": False,
            "reason": "predecessor layer-3 declaration cannot be a layer-2 current-authority dependency",
        },
        "manifest_contract": str(MANIFEST.relative_to(ROOT)),
    }


def installation() -> dict:
    posture_map = {
        "CANDIDATE": {"authority_posture": "CANDIDATE", "authority_scope": ["SYNTHETIC", "PRODUCTION"], "live_authority": "ABSENT"},
        "PREPARED_VALIDATION_ONLY": {"authority_posture": "INSTALLED_BYTES_UNCOMMITTED", "authority_scope": "PRODUCTION", "live_authority": False},
        "SYNTHETIC_INSTALLED": {"authority_posture": "INSTALLED", "authority_scope": "SYNTHETIC", "live_authority": False},
        "PRODUCTION_INSTALLED": {"authority_posture": "INSTALLED", "authority_scope": "PRODUCTION", "live_authority": True},
    }
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-event06-live-installation-interface/1.1.0",
        "posture_mapping": posture_map,
        "synthetic_entrypoint": "install_noncanonical_candidate",
        "production_prepare_entrypoint": "prepare_production_installation",
        "production_validate_entrypoint": "validate_prepared_production_installation",
        "production_dry_package_gate": "validate_prepared_package_start_eligibility",
        "production_commit_entrypoint": "commit_production_installation",
        "future_go_capability_contract": str(GO_CAPABILITY.relative_to(ROOT)),
        "phase_order": ["SEALED_INPUTS", "CANDIDATE_VALIDATED", "PREPARED_VALIDATION_ONLY", "PRODUCTION_INSTALLED"],
        "durable_commit_authorized_in_sequence_5": False,
        "sequence_5_terminal_posture": "PREPARED_VALIDATION_ONLY",
        "dry_gate_accepts_only": "PREPARED_VALIDATION_ONLY",
        "runtime_producer_accepts_only": "PRODUCTION_INSTALLED_AFTER_PACKAGE_DURABLE_START",
        "synthetic_runtime_qualification_accepts_only": "SYNTHETIC_INSTALLED",
        "cross_posture_substitution": "REJECT",
        "forbidden_capabilities": ["arbitrary callback", "caller mapping", "mutable policy", "ambient environment authority", "unchecked path", "public direct constructor", "pickle", "copy", "authority-widening serialization"],
        "exact_failure_outcomes": {
            "input": "F017_V12_PRODUCTION_INSTALL_INPUT_MISMATCH",
            "readiness": "F017_V12_PRODUCTION_INSTALL_READINESS_MISMATCH",
            "go": "F017_V12_PRODUCTION_INSTALL_GO_MISMATCH",
            "plan": "F017_V12_PRODUCTION_INSTALL_PLAN_MISMATCH",
            "identity": "F017_V12_PRODUCTION_INSTALL_IDENTITY_MISMATCH",
            "candidate": "F017_V12_PRODUCTION_INSTALL_CANDIDATE_MISMATCH",
            "receipt": "F017_V12_PRODUCTION_INSTALL_RECEIPT_MISMATCH",
            "posture": "F017_V12_PRODUCTION_INSTALL_POSTURE_MISMATCH",
            "capability": "F017_V12_PRODUCTION_INSTALL_CAPABILITY_REQUIRED",
            "capability_expired": "F017_V12_PRODUCTION_INSTALL_CAPABILITY_EXPIRED",
            "replay": "F017_V12_PRODUCTION_INSTALL_REPLAY",
            "target": "F017_V12_PRODUCTION_INSTALL_TARGET_EXISTS",
            "write": "F017_V12_PRODUCTION_INSTALL_WRITE_FAILURE",
            "fsync": "F017_V12_PRODUCTION_INSTALL_FSYNC_FAILURE",
            "readback": "F017_V12_PRODUCTION_INSTALL_READBACK_MISMATCH",
            "partial": "F017_V12_PRODUCTION_INSTALL_PARTIAL_COMMIT",
        },
        "one_owner": True, "one_package": True, "one_install": True,
        "no_replace": True, "restart_replay_rejected": True,
    }


def go_capability() -> dict:
    fields = ["schema", "human_go_sha256", "operator_approval_sha256", "execution_plan_sha256", "event_identity_plan_sha256", "authorization_id", "package_attempt_id", "issued_at_unix_ns", "expires_at_unix_ns", "nonce_sha256", "scope", "attempts", "retries", "resume"]
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-event06-future-go-capability/1.0.0",
        "required_fields": fields, "unknown_keys_permitted": False,
        "sealing_authority": "repository-owned factory after exact fresh human GO validation",
        "same_capability_rule": "prepare and commit require object identity plus canonical digest equality",
        "expiry_rule": "issued_at_unix_ns < now < expires_at_unix_ns at prepare and commit",
        "freshness_rule": "nonce, human GO, approval, plan, identities, and package are unused and pairwise bound",
        "scope": "ONE_EVENT06_V12_PRODUCTION_INSTALL",
        "attempts": 1, "retries": 0, "resume": False,
        "public_constructor": False, "copy": False, "pickle": False,
        "sequence_5_factory_available": False,
    }


def manifest() -> dict:
    layers = {role: 1 for role in ROLE_NAMES if role != "authority_manifest"}
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest-contract/1.0.0",
        "manifest_schema": "pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest/1.0.0",
        "required_keys": ["schema", "implementation_head", "implementation_tree", "binding_count", "bindings", "roles", "result"],
        "bindings_type": "repository-relative-path-to-sha256 closed mapping",
        "roles": layers, "binding_count_equals_bindings_length": True,
        "required_roles": sorted(layers), "unknown_roles_permitted": False,
        "manifest_may_bind_itself": False, "manifest_may_bind_final_declaration": False,
        "final_declaration_binds_manifest": True,
        "terminal_index_may_bind_manifest_and_declaration": True,
        "terminal_index_is_readiness_input": False,
    }


def finding_contract() -> dict:
    ids = [
        "B-CYCLE02-CHALLENGE-FALSE-VERIFICATION", "B-CLAIM-LEDGER-CONTRADICTION",
        "B-SUPPORT-LEDGER-COUNTERS", "B-CYCLE01-ARBITRATION-UNAUDITABLE",
        "U-EXTERNAL-PARENT-RESPONSE-NOT-SNAPSHOTTED", "U-CI-RUN-IDENTIFIERS",
        "U-EVIDENCE-CI-DIFF-SCOPED", "U-CHALLENGE-TRANSPORT-PROVENANCE",
    ]
    return {
        "schema": "pulsarmlx.f017.event06-sequence4-finding-disposition-contract/1.0.0",
        "required_finding_ids": ids, "finding_count": 8,
        "allowed_dispositions": ["RESOLVED", "CONCEDED", "UNRESOLVED"],
        "resolved_requires_exact_support": True, "conceded_counts_as_resolved": False,
        "row_counter_scope": "successor rows only", "cumulative_counters_separate": True,
        "acceptance": {"resolved": 8, "conceded": 0, "unresolved": 0},
    }


def provenance() -> dict:
    return {
        "schema": "pulsarmlx.f017.independent-review-transport-provenance-contract/1.0.0",
        "required_fields": ["schema", "tool", "tool_version", "transport", "command", "requested_model", "provider_reported_model", "provider_session_metadata", "started_at_utc", "completed_at_utc", "exit_status", "request_path", "request_sha256", "response_path", "response_sha256", "normalized_result_path", "normalized_result_sha256", "reviewed_commit", "credentials_serialized", "result"],
        "provider_metadata_unavailable_policy": "UNRESOLVED",
        "self_report_alone_sufficient": False,
        "credentials_serialized": False,
    }


def artifacts() -> dict[Path, object]:
    safety = {"checkpoint_root_resolved": False, "checkpoint_access": 0, "numerical_operations": 0, "live_installations": 0, "package_starts": 0, "ids_consumed": 0}
    return {
        READINESS: readiness(), INSTALL: installation(), GO_CAPABILITY: go_capability(),
        MANIFEST: manifest(), FINDINGS: finding_contract(), PROVENANCE: provenance(),
        EVIDENCE_DIR / "f017-event06-v12-sequence05-readiness-field-census-v2.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-readiness-field-census/1.1.0",
            "consumer_schema": readiness()["schema"], "declaration_schema": readiness()["declaration_schema"],
            "field_count": len(REQUIRED), "required_fields": REQUIRED, "exact_types": readiness()["exact_types"],
            "exact_predicates": EXACT, "exact_predicate_count": len(EXACT),
            "exact_predicates_exhaustive_for_acceptance": True, "unknown_keys_permitted": False,
            "aliases_permitted": False, "coercions_permitted": False, "result": "REPAIRED",
            "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-readiness-field-census-v1.json",
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-consumer-matrix-v2.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-consumer-matrix/1.1.0",
            "rows": [
                {"consumer": "candidate_builder", "allowed": ["CANDIDATE"]},
                {"consumer": "primary_candidate_validator", "allowed": ["CANDIDATE"]},
                {"consumer": "secondary_candidate_validator", "allowed": ["CANDIDATE"]},
                {"consumer": "identity_candidate_validator", "allowed": ["CANDIDATE"]},
                {"consumer": "installation_preparer", "allowed": ["CANDIDATE"], "produces": "PREPARED_VALIDATION_ONLY"},
                {"consumer": "prepared_installed_validator", "allowed": ["PREPARED_VALIDATION_ONLY"]},
                {"consumer": "synthetic_installed_validator", "allowed": ["SYNTHETIC_INSTALLED"]},
                {"consumer": "production_installed_validator", "allowed": ["PRODUCTION_INSTALLED"]},
                {"consumer": "dry_package_gate", "allowed": ["PREPARED_VALIDATION_ONLY"], "side_effects": 0},
                {"consumer": "runtime_package_gate", "allowed": ["PRODUCTION_INSTALLED"]},
                {"consumer": "identity_runtime_producer", "allowed": ["PRODUCTION_INSTALLED"], "requires_package_durable_start": True},
                {"consumer": "bridge", "allowed": ["PREPARED_VALIDATION_ONLY", "PRODUCTION_INSTALLED"]},
                {"consumer": "coordinator_dry", "allowed": ["PREPARED_VALIDATION_ONLY"]},
                {"consumer": "coordinator_live", "allowed": ["PRODUCTION_INSTALLED"]},
            ],
            "posture_mapping": installation()["posture_mapping"],
            "alternate_authority_permitted": False, "result": "REPAIRED",
            "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-consumer-matrix-v1.json",
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-authority-provenance-map-v2.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-authority-provenance-map/1.1.0",
            "manifest_contract": str(MANIFEST.relative_to(ROOT)),
            "role_layers": manifest()["roles"], "layer_order": ["dependencies", "manifest", "final declaration", "terminal index"],
            "supersedes_manifest_membership_required": False,
            "self_references": 0, "future_references": 0, "result": "REPAIRED_ACYCLIC_BY_CONSTRUCTION",
            "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-authority-provenance-map-v1.json",
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-failure-matrix-v2.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-failure-matrix/1.1.0",
            "category_outcomes": installation()["exact_failure_outcomes"],
            "readiness_outcomes": {"canonical": "F017_EVENT06_READINESS_NONCANONICAL", "schema": "F017_EVENT06_READINESS_SCHEMA", "field": "F017_EVENT06_READINESS_FIELD", "type": "F017_EVENT06_READINESS_TYPE", "predicate": "F017_EVENT06_READINESS_PREDICATE", "binding": "F017_EVENT06_READINESS_BINDING"},
            "minimum_mutations": 320,
            "derivation": {"readiness_deletions": len(REQUIRED), "readiness_types": len(REQUIRED), "acceptance_predicates": len(EXACT), "installation_and_race_floor": 100},
            "generic_fallback": False, "failure_prefix": "EXACT_OUTCOME_PER_CATEGORY", "safety": safety,
            "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-failure-matrix-v1.json",
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-no-access-qualification-plan-v2.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-no-access-qualification-plan/1.1.0",
            "real_consumer_functions": ["validate_event06_readiness_declaration_v2", "build_identity_candidate_from_readiness", "validate_candidate_triple", "prepare_production_installation", "validate_prepared_production_installation", "validate_prepared_package_start_eligibility", "derive_bridge_execution_plan", "primary consumer signature", "secondary consumer signature", "result consumer signature"],
            "interposed_primitives": ["Path.resolve for checkpoint coordinates", "Path.stat", "os.open", "os.pread", "mmap.mmap", "checkpoint hash stream", "tensor source", "numerical execute", "bank_exclusive live root", "ID consumption"],
            "spy_policy": {"binds_real_consumer_signatures": True, "bypasses_consumer_signatures": False, "fails_if_prohibited_capability_reached": True, "synthetic_temporary_roots_only": True, "original_checkpoint_name_or_root_discovery": "PROHIBITED"},
            "checkpoint_coordinate": "NONEXISTENT_SENTINEL_ONLY", "readiness_reconstructions": 20,
            "installation_reconstructions": 20, "minimum_mutations": 320,
            "production_commit_success_calls": 0, "required_terminal": "PACKAGE_START_ELIGIBLE_DRY_STOP",
            "safety": safety, "result": "REPAIRED",
            "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-no-access-qualification-plan-v1.json",
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-design-graph-state-v2.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-design-graph-state/1.1.0",
            "nodes": [{"id": "D0", "status": "PASS"}, {"id": "D1", "status": "REPAIR_REQUIRED"}, {"id": "D2", "status": "REPAIR_REQUIRED"}, {"id": "D3", "status": "REPAIR_REQUIRED"}],
            "running_nodes": 0, "opus_cycle": 1, "blocking_findings": 6, "required_findings": 5,
            "unresolved_claims": 3, "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-design-graph-state-v1.json",
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-design-claim-ledger-v2.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-design-claim-ledger/1.1.0",
            "claims": [
                {"claim_id": "S5-DESIGN-READINESS", "state": "CHALLENGED"},
                {"claim_id": "S5-DESIGN-INSTALL", "state": "CHALLENGED"},
                {"claim_id": "S5-DESIGN-NOACCESS", "state": "CHALLENGED"},
            ],
            "claim_count": 3, "supported": 0, "challenged": 3, "unresolved": 0,
            "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-design-claim-ledger-v1.json",
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
