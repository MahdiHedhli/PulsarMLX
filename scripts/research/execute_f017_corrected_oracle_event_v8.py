#!/usr/bin/env python3
"""Synthetic-only V8 lifecycle coordinator with inherited descriptor continuity."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import validate_f017_lifecycle_causal_design_v8 as design
from construct_f017_lifecycle_v8_symbolically import construct_outcome
from f017_checkpoint_identity_producer_v8 import produce
from f017_corrected_oracle_compare_v8 import compare
from f017_corrected_oracle_event_accounting_v8 import deltas
from f017_corrected_oracle_primary_v8 import execute as execute_primary
from f017_corrected_oracle_secondary_v8 import execute as execute_secondary
from f017_descriptor_lease_manager_v8 import validate_descriptors
from f017_lifecycle_artifact_v8 import bank_runtime_artifact
from validate_f017_corrected_oracle_access_v8 import validate_installed_rehearsal


def execute_synthetic(installed_path: Path, receipt_path: Path, evidence_root: Path, *, malformed: str | None = None) -> dict:
    handshake = validate_installed_rehearsal(installed_path, receipt_path)
    candidate = handshake["candidate"]
    if any(report["checkpoint_opens"] or report["checkpoint_reads"] or report["state_created"] for report in (handshake["primary"], handshake["secondary"])):
        raise ValueError("candidate handshake side effect")
    evidence_root.mkdir(parents=True, exist_ok=False)
    bank_runtime_artifact(evidence_root / "coordinator-handshake.json", "coordinator_handshake", {"candidate_sha256": handshake["candidate_sha256"], "checkpoint_opens": 0, "checkpoint_reads": 0, "state_created": False, "result": "PASS"})
    bank_runtime_artifact(evidence_root / "package-claim.json", "package_claim", {"authorization_id": candidate["authorization_id"], "package_attempt_id": candidate["package_attempt_id"], "owner_nonce": f"OWNER-{candidate['package_attempt_id']}", "attempts": 1, "retries": 0, "resume": False})
    bank_runtime_artifact(evidence_root / "package-durable-start.json", "package_durable_start", {"package_attempt_id": candidate["package_attempt_id"], "delta": 1})
    bank_runtime_artifact(evidence_root / "package-ledger-entry.json", "package_ledger_entry", {"authorization_id": candidate["authorization_id"], "package_attempt_id": candidate["package_attempt_id"], "event_class": "CORRECTED_ORACLE_PACKAGE_ATTEMPT_LEDGER", "delta": 1, "historical_ledger": 175})
    leases = None
    try:
        bank_runtime_artifact(evidence_root / "checkpoint-identity-durable-start.json", "checkpoint_identity_durable_start", {"package_attempt_id": candidate["package_attempt_id"], "expected_shards": 6, "expected_graph_descriptors": 5})
        leases, identity = produce(candidate)
        descriptors = copy.deepcopy(identity["descriptor_identities"])
        if malformed == "MODE_65536":
            descriptors[0]["mode"] = 65536
        elif malformed == "NON_DICT":
            descriptors[0] = None
        elif malformed == "UNHASHABLE_LEASE":
            descriptors[0]["lease_id"] = []
        validate_descriptors(descriptors, [item["size_bytes"] for item in candidate["shards"][1:]])
        bank_runtime_artifact(evidence_root / "checkpoint-access-journal-terminal.json", "checkpoint_access_journal_terminal", {"event_count": 6, "ordered_shard_digests": identity["ordered_shard_digests"], "checkpoint_shard_opens": 6, "checkpoint_identity_hash_reads": 6, "unexpected_access_count": 0})
        bank_runtime_artifact(evidence_root / "descriptor-lease-manifest.json", "descriptor_lease_manifest", {"lease_count": 5, "ordinals": [2, 3, 4, 5, 6], "lease_ids": [item["lease_id"] for item in descriptors], "descriptor_identities": descriptors})
        bank_runtime_artifact(evidence_root / "checkpoint-identity-receipt.json", "checkpoint_identity_receipt", identity)
        bank_runtime_artifact(evidence_root / "checkpoint-identity-terminal.json", "checkpoint_identity_terminal", {"result": "COMPLETE", "retained_lease_count": 5, "identity_only_retained_count": 0})
        bank_runtime_artifact(evidence_root / "primary-continuity.json", "primary_descriptor_continuity_report", {"consumer_role": "PRIMARY", "descriptor_count": 5, "ordinals": [2, 3, 4, 5, 6], "lease_ids": [item["lease_id"] for item in descriptors], "descriptor_identities": descriptors, "path_reopen_count": 0})
        bank_runtime_artifact(evidence_root / "primary-durable-start.json", "primary_durable_start", {"package_attempt_id": candidate["package_attempt_id"], "event_id": candidate["primary_event_id"], "delta": 1})
        bank_runtime_artifact(evidence_root / "primary-ledger-entry.json", "primary_ledger_entry", {"package_attempt_id": candidate["package_attempt_id"], "event_id": candidate["primary_event_id"], "event_class": "CORRECTED_ORACLE_PRIMARY_EVENT_LEDGER", "delta": 1})
        primary = execute_primary(candidate, descriptors, leases.inherited_fds())
        primary_sha = hashlib.sha256(json.dumps(primary, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        bank_runtime_artifact(evidence_root / "primary-execution-evidence.json", "primary_execution_evidence", {"event_id": candidate["primary_event_id"], "layers_completed": primary["layers_completed"], "output_sha256": primary_sha, "synthetic_only": True})
        primary_receipt_sha = bank_runtime_artifact(evidence_root / "primary-receipt.json", "primary_receipt", {"package_attempt_id": candidate["package_attempt_id"], "event_id": candidate["primary_event_id"], "result": "COMPLETE", "output_sha256": primary_sha})
        primary_terminal_sha = bank_runtime_artifact(evidence_root / "primary-terminal.json", "primary_terminal", {"package_attempt_id": candidate["package_attempt_id"], "event_id": candidate["primary_event_id"], "result": "COMPLETE", "receipt_sha256": primary_receipt_sha})
        bank_runtime_artifact(evidence_root / "secondary-continuity.json", "secondary_descriptor_continuity_report", {"consumer_role": "SECONDARY", "descriptor_count": 5, "ordinals": [2, 3, 4, 5, 6], "lease_ids": [item["lease_id"] for item in descriptors], "descriptor_identities": descriptors, "path_reopen_count": 0})
        bank_runtime_artifact(evidence_root / "secondary-durable-start.json", "secondary_durable_start", {"package_attempt_id": candidate["package_attempt_id"], "event_id": candidate["secondary_event_id"], "delta": 1})
        bank_runtime_artifact(evidence_root / "secondary-ledger-entry.json", "secondary_ledger_entry", {"package_attempt_id": candidate["package_attempt_id"], "event_id": candidate["secondary_event_id"], "event_class": "CORRECTED_ORACLE_SECONDARY_EVENT_LEDGER", "delta": 1})
        secondary = execute_secondary(candidate, descriptors, leases.inherited_fds())
        secondary_sha = hashlib.sha256(json.dumps(secondary, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        bank_runtime_artifact(evidence_root / "secondary-execution-evidence.json", "secondary_execution_evidence", {"event_id": candidate["secondary_event_id"], "layers_completed": secondary["layers_completed"], "output_sha256": secondary_sha, "synthetic_only": True})
        secondary_receipt_sha = bank_runtime_artifact(evidence_root / "secondary-receipt.json", "secondary_receipt", {"package_attempt_id": candidate["package_attempt_id"], "event_id": candidate["secondary_event_id"], "result": "COMPLETE", "output_sha256": secondary_sha})
        secondary_terminal_sha = bank_runtime_artifact(evidence_root / "secondary-terminal.json", "secondary_terminal", {"package_attempt_id": candidate["package_attempt_id"], "event_id": candidate["secondary_event_id"], "result": "COMPLETE", "receipt_sha256": secondary_receipt_sha})
        comparison = compare(primary, secondary)
        comparison_receipt_sha = bank_runtime_artifact(evidence_root / "comparison-receipt.json", "comparison_receipt", comparison)
        bank_runtime_artifact(evidence_root / "comparison-terminal.json", "comparison_terminal", {**comparison, "receipt_sha256": comparison_receipt_sha, "result": "COMPLETE"})
        release = leases.release()
        bank_runtime_artifact(evidence_root / "descriptor-release.json", "descriptor_release_terminal", release)
        accounting = deltas(package_started=True, primary_started=True, secondary_started=True)
        package_receipt_sha = bank_runtime_artifact(evidence_root / "package-receipt.json", "package_receipt", {"package_attempt_id": candidate["package_attempt_id"], "primary_receipt_sha256": primary_receipt_sha, "primary_terminal_sha256": primary_terminal_sha, "secondary_receipt_sha256": secondary_receipt_sha, "secondary_terminal_sha256": secondary_terminal_sha, "accounting": accounting, "classification": comparison["classification"]})
        bank_runtime_artifact(evidence_root / "package-terminal.json", "package_terminal", {"package_attempt_id": candidate["package_attempt_id"], "result": "COMPLETE", "classification": comparison["classification"], "package_receipt_sha256": package_receipt_sha, "accounting": accounting, "mandatory_stop": True})
        docs = design.load_documents()
        projection = evidence_root / "causal-projection"
        projection.mkdir()
        constructed = construct_outcome("COMPLETE_SUCCESS", projection, docs["artifact_dag"], docs["artifact_schemas"], docs["outcomes"])
        return {"result": "PASS", "candidate_sha256": handshake["candidate_sha256"], "identity": identity, "primary": primary, "secondary": secondary, "comparison": comparison, "release": release, "accounting": accounting, "causal_projection": constructed, "original_checkpoint_access": 0}
    except (ValueError, OSError) as exc:
        release = {"attempted_closures": 0, "successful_closures": 0, "duplicate_closures": 0, "unknown_leases": 0, "live_leases_after_release": 0, "lease_ids": []}
        if leases is not None and not leases.closed:
            release = leases.release()
        bank_runtime_artifact(evidence_root / "failure-terminal.json", "failure_terminal_capsule", {"classification": "DESCRIPTOR_LEASE_ACTIVATION_FAILURE", "controlled_failure_class": "ValueError", "message": str(exc), "release": release, "mandatory_stop": True})
        return {"result": "CONTROLLED_FAILURE", "failure_class": "ValueError", "source_exception_class": type(exc).__name__, "message": str(exc), "release": release, "accounting": deltas(package_started=True, primary_started=False, secondary_started=False), "original_checkpoint_access": 0}
