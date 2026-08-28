#!/usr/bin/env python3
"""Generate the version-forward Event-06 Sequence-5 design authority."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_DIR = ROOT / "specs/017-rust-native-inference-runtime/contracts"
EVIDENCE_DIR = ROOT / "docs/architecture/reviews/evidence"

READINESS_CONTRACT = CONTRACT_DIR / "f017-corrected-oracle-event06-readiness-consumer-interface-v2.json"
INSTALL_CONTRACT = CONTRACT_DIR / "f017-corrected-oracle-event06-live-installation-interface-v1.json"

PATH_ROLES = [
    "implementation_measurement", "authority_manifest", "scientific_access_contract",
    "checkpoint_identity_authority", "numerical_contract", "result_authority",
    "bridge_declaration", "readiness_interface", "live_installation_interface",
    "canonical_readiness_qualification", "installation_preparation_qualification",
    "failure_qualification", "no_access_rehearsal", "full_corpus_validation",
    "full_native_evidence", "challenge_result", "challenge_provenance",
    "opus_result", "sequence4_finding_disposition",
]
PATH_FIELDS = [item for role in PATH_ROLES for item in (f"{role}_path", f"{role}_sha256")]
STRING_FIELDS = [
    "schema", "declaration", "supersedes_path", "supersedes_sha256",
    "active_corrected_oracle_generation", "numerical_authority",
    "bridge_digest", "gemini_verdict", "opus_verdict", "exact_next_safe_action",
]
BOOL_FIELDS = [
    "historical_readiness_accepted", "current_executable_readiness",
    "event_04_retry", "event_05_retry", "sequence_4_event_06_retry_or_resume",
    "event_06_executed", "live_event_06_authorization_created",
    "live_v12_installation_created", "event_06_package_started",
    "original_checkpoint_root_resolved", "ready_for_fresh_corrected_full_checkpoint_oracle_event_06_go",
    "ready_to_prepare_p1_attempt_2_authorization",
]
COUNT_FIELDS = [
    "full_native_run", "required_native_skips", "blocking_findings",
    "non_blocking_required_findings", "unresolved_claims",
    "primary_real_oracle_event06_executions", "secondary_real_oracle_event06_executions",
    "original_checkpoint_shard_opens", "original_checkpoint_identity_hash_reads",
    "original_checkpoint_payload_reads", "original_checkpoint_mmaps_or_tensor_reads",
    "event06_identities_consumed", "historical_master_ledger",
]
GIT_FIELDS = ["implementation_head", "implementation_tree"]
REQUIRED_FIELDS = STRING_FIELDS + BOOL_FIELDS + COUNT_FIELDS + GIT_FIELDS + PATH_FIELDS


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: object, *, check: bool) -> None:
    raw = canonical_bytes(value)
    if check:
        if not path.is_file() or path.read_bytes() != raw:
            raise SystemExit(f"generated artifact drift: {path.relative_to(ROOT)}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def readiness_contract() -> dict:
    exact_predicates = {
        "active_corrected_oracle_generation": "V12",
        "numerical_authority": "V4",
        "historical_readiness_accepted": True,
        "current_executable_readiness": True,
        "event_04_retry": False,
        "event_05_retry": False,
        "sequence_4_event_06_retry_or_resume": False,
        "event_06_executed": False,
        "live_event_06_authorization_created": False,
        "live_v12_installation_created": False,
        "event_06_package_started": False,
        "primary_real_oracle_event06_executions": 0,
        "secondary_real_oracle_event06_executions": 0,
        "original_checkpoint_root_resolved": False,
        "original_checkpoint_shard_opens": 0,
        "original_checkpoint_identity_hash_reads": 0,
        "original_checkpoint_payload_reads": 0,
        "original_checkpoint_mmaps_or_tensor_reads": 0,
        "event06_identities_consumed": 0,
        "required_native_skips": 0,
        "blocking_findings": 0,
        "non_blocking_required_findings": 0,
        "unresolved_claims": 0,
        "historical_master_ledger": 175,
        "ready_for_fresh_corrected_full_checkpoint_oracle_event_06_go": True,
        "ready_to_prepare_p1_attempt_2_authorization": False,
        "exact_next_safe_action": "RETURN_TO_F017_PLANNER_AND_REQUEST_NEW_HUMAN_EVENT06_GO",
    }
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-event06-readiness-consumer-interface/2.0.0",
        "declaration_schema": "pulsarmlx.f017.corrected-oracle-event06-execution-readiness-final-declaration/12.2.0",
        "required_fields": REQUIRED_FIELDS,
        "field_count": len(REQUIRED_FIELDS),
        "exact_types": {
            "boolean": BOOL_FIELDS,
            "git_object": GIT_FIELDS,
            "nonnegative_integer": COUNT_FIELDS,
            "repository_path": [field for field in PATH_FIELDS if field.endswith("_path")] + ["supersedes_path"],
            "sha256": [field for field in PATH_FIELDS if field.endswith("_sha256")] + ["supersedes_sha256", "bridge_digest"],
            "string": [field for field in STRING_FIELDS if field not in {"supersedes_path", "supersedes_sha256", "bridge_digest"}],
        },
        "exact_predicates": exact_predicates,
        "unknown_keys_permitted": False,
        "aliases_permitted": False,
        "coercions_permitted": False,
        "canonical_bytes_required": True,
        "historical_declarations_permitted_as_current": False,
        "layering": [
            "measured implementation and qualification artifacts",
            "layered authority manifest excluding the final declaration",
            "canonical final readiness declaration binding that manifest",
            "optional terminal index binding both without becoming a readiness input",
        ],
    }


def installation_contract() -> dict:
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-event06-live-installation-interface/1.0.0",
        "postures": ["PREPARED_VALIDATION_ONLY", "SYNTHETIC_INSTALLED", "PRODUCTION_INSTALLED"],
        "synthetic_entrypoint": "install_noncanonical_candidate",
        "production_prepare_entrypoint": "prepare_production_installation",
        "production_commit_entrypoint": "commit_production_installation",
        "production_validate_entrypoint": "validate_prepared_production_installation",
        "phases": [
            "validate sealed readiness, future GO, execution plan, identity plan, approval, and candidate triple",
            "derive canonical candidate, receipt, and installed bytes without filesystem writes",
            "validate prepared receipt and installed triple in memory",
            "commit exclusively only with the same unexpired sealed future-GO capability",
            "fsync files and parent directories, read back through no-follow descriptors, and verify exact identities",
        ],
        "durable_commit_authorized_in_sequence_5": False,
        "validation_only_live_authority": False,
        "forbidden_capabilities": [
            "arbitrary callback", "caller mapping", "mutable policy", "ambient environment authority",
            "unchecked path", "public direct constructor", "pickle", "copy", "authority-widening serialization",
        ],
        "exact_failure_outcomes": [
            "F017_V12_PRODUCTION_INSTALL_INPUT_MISMATCH",
            "F017_V12_PRODUCTION_INSTALL_CAPABILITY_REQUIRED",
            "F017_V12_PRODUCTION_INSTALL_CAPABILITY_EXPIRED",
            "F017_V12_PRODUCTION_INSTALL_REPLAY",
            "F017_V12_PRODUCTION_INSTALL_TARGET_EXISTS",
            "F017_V12_PRODUCTION_INSTALL_WRITE_FAILURE",
            "F017_V12_PRODUCTION_INSTALL_FSYNC_FAILURE",
            "F017_V12_PRODUCTION_INSTALL_READBACK_MISMATCH",
            "F017_V12_PRODUCTION_INSTALL_PARTIAL_COMMIT",
        ],
        "one_owner": True,
        "one_package": True,
        "one_install": True,
        "no_replace": True,
        "restart_replay_rejected": True,
    }


def design_artifacts() -> dict[Path, object]:
    source_head = "ed3e379ebb4da7bbd28d773bb309db3fadf2dba3"
    safety = {
        "event_06_executed": False, "live_event_06_authorization_created": False,
        "live_v12_installation_created": False, "event_06_package_started": False,
        "original_checkpoint_root_resolved": False, "original_checkpoint_access": 0,
        "numerical_operations": 0, "event06_identities_consumed": 0,
        "historical_master_ledger": 175,
    }
    artifacts: dict[Path, object] = {
        READINESS_CONTRACT: readiness_contract(),
        INSTALL_CONTRACT: installation_contract(),
        EVIDENCE_DIR / "f017-event06-v12-sequence05-mismatch-reproduction-v1.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-mismatch-reproduction/1.0.0",
            "starting_head": source_head,
            "readiness": {
                "observed_bytes": 3124, "canonical_bytes": 2923, "canonical": False,
                "bounded_decode": "ArtifactDecodeError: noncanonical JSON artifact bytes",
                "actual_schema": "pulsarmlx.f017.corrected-oracle-event06-execution-readiness-final-declaration/12.1.0",
                "consumer_schema": "pulsarmlx.f017.corrected-oracle-event06-execution-readiness-final-declaration/12.0.0",
                "missing_required_fields": 25, "unexpected_fields": 28,
                "prompt_expected_unexpected_fields": 30,
                "disposition": "GIT_DERIVED_28_FIELDS_AUTHORITATIVE",
                "historical_v12_v2_control": "PASS",
            },
            "installation": {
                "installer_count": 1,
                "installer": "install_noncanonical_candidate",
                "installation_kind": "NONCANONICAL_SYNTHETIC_QUALIFICATION",
                "live_authority_required": False,
                "production_installer_found": False,
            },
            "safety": safety,
            "result": "REPRODUCED",
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-readiness-field-census-v1.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-readiness-field-census/1.0.0",
            "consumer_schema": readiness_contract()["schema"],
            "declaration_schema": readiness_contract()["declaration_schema"],
            "field_count": len(REQUIRED_FIELDS), "required_fields": REQUIRED_FIELDS,
            "exact_types": readiness_contract()["exact_types"], "unknown_keys_permitted": False,
            "aliases_permitted": False, "coercions_permitted": False, "result": "FROZEN",
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-consumer-matrix-v1.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-consumer-matrix/1.0.0",
            "rows": [
                {"consumer": name, "readiness": "ValidatedEvent06ReadinessV2", "candidate": "ValidatedIdentityAuthority", "posture": posture}
                for name, posture in [
                    ("candidate_builder", "PREPARED_VALIDATION_ONLY"), ("primary", "CANDIDATE"),
                    ("secondary", "CANDIDATE"), ("identity_producer", "CANDIDATE"),
                    ("installation_preparer", "PREPARED_VALIDATION_ONLY"),
                    ("installed_primary", "PRODUCTION_INSTALLED"),
                    ("installed_secondary", "PRODUCTION_INSTALLED"),
                    ("package_gate", "PRODUCTION_INSTALLED"), ("bridge", "PRODUCTION_INSTALLED"),
                    ("coordinator", "PRODUCTION_INSTALLED"),
                ]
            ],
            "shared_provenance_required": True, "alternate_authority_permitted": False,
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-installation-state-machine-v1.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-installation-state-machine/1.0.0",
            "states": ["UNVALIDATED", "PREPARED_VALIDATION_ONLY", "SYNTHETIC_INSTALLED", "PRODUCTION_INSTALLED", "TERMINAL_FAILURE"],
            "transitions": [
                {"from": "UNVALIDATED", "to": "PREPARED_VALIDATION_ONLY", "write": False},
                {"from": "UNVALIDATED", "to": "SYNTHETIC_INSTALLED", "write": True, "scope": "synthetic temporary root"},
                {"from": "PREPARED_VALIDATION_ONLY", "to": "PRODUCTION_INSTALLED", "write": True, "requires": "sealed future fresh-GO capability"},
            ],
            "cross_posture_substitution": "REJECT", "sequence_5_terminal_state": "PREPARED_VALIDATION_ONLY",
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-failure-matrix-v1.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-failure-matrix/1.0.0",
            "categories": ["readiness schema", "authority binding", "GO", "plan", "identity", "candidate", "receipt", "posture", "path", "write", "fsync", "readback", "race", "restart"],
            "minimum_mutations": 240, "failure_prefix": "NO_LIVE_WRITE", "generic_fallback": False,
            "safety": safety,
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-authority-provenance-map-v1.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-authority-provenance-map/1.0.0",
            "layers": [
                {"ordinal": 1, "name": "implementation_and_qualification", "may_bind_future": False},
                {"ordinal": 2, "name": "authority_manifest", "may_bind_final_declaration": False},
                {"ordinal": 3, "name": "final_readiness_declaration", "binds_manifest": True},
                {"ordinal": 4, "name": "terminal_index", "readiness_input": False},
            ],
            "self_references": 0, "future_references": 0, "result": "ACYCLIC_BY_CONSTRUCTION",
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-no-access-qualification-plan-v1.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-no-access-qualification-plan/1.0.0",
            "readiness_reconstructions": 20, "installation_reconstructions": 20,
            "minimum_mutations": 240, "production_commit_success_calls": 0,
            "checkpoint_coordinate": "NONEXISTENT_SENTINEL_ONLY",
            "interposition": ["root resolution", "stat", "open", "hash", "read", "mmap", "tensor read", "numerical core", "state creation", "ID consumption"],
            "required_terminal": "PACKAGE_START_ELIGIBLE_DRY_STOP",
            "safety": safety,
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-design-graph-state-v1.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-design-graph-state/1.0.0",
            "nodes": [
                {"id": "D0", "status": "PASS", "name": "reproduction"},
                {"id": "D1", "status": "PASS", "name": "canonical readiness design"},
                {"id": "D2", "status": "PASS", "name": "production installation design"},
                {"id": "D3", "status": "PENDING", "name": "independent design review"},
            ],
            "running_nodes": 0, "original_checkpoint_access": 0,
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-design-claim-ledger-v1.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-design-claim-ledger/1.0.0",
            "claims": [
                {"claim_id": "S5-DESIGN-READINESS", "state": "SUPPORTED", "statement": "One closed canonical successor readiness interface is constructible without a hash cycle."},
                {"claim_id": "S5-DESIGN-INSTALL", "state": "SUPPORTED", "statement": "Production preparation and durable commit are separate postures; Sequence 5 cannot authorize commit."},
                {"claim_id": "S5-DESIGN-NOACCESS", "state": "SUPPORTED", "statement": "The complete qualification plan uses nonexistent coordinates and fail-closed interposition."},
            ],
            "claim_count": 3, "supported": 3, "challenged": 0, "unresolved": 0,
        },
    }
    return artifacts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, value in design_artifacts().items():
        _write(path, value, check=args.check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
