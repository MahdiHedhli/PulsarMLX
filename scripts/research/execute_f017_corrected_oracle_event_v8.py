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
    bank_runtime_artifact(evidence_root / "package-durable-start.json", "package_durable_start", {"package_attempt_id": candidate["package_attempt_id"], "delta": 1})
    leases = None
    try:
        leases, identity = produce(candidate)
        descriptors = copy.deepcopy(identity["descriptor_identities"])
        if malformed == "MODE_65536":
            descriptors[0]["mode"] = 65536
        elif malformed == "NON_DICT":
            descriptors[0] = None
        elif malformed == "UNHASHABLE_LEASE":
            descriptors[0]["lease_id"] = []
        validate_descriptors(descriptors, [item["size_bytes"] for item in candidate["shards"][1:]])
        bank_runtime_artifact(evidence_root / "checkpoint-identity.json", "checkpoint_identity_receipt", identity)
        bank_runtime_artifact(evidence_root / "primary-continuity.json", "primary_descriptor_continuity_report", {"descriptor_count": 5, "ordinals": [2, 3, 4, 5, 6], "descriptor_identities": descriptors, "path_reopen_count": 0})
        primary = execute_primary(candidate, descriptors, leases.inherited_fds())
        bank_runtime_artifact(evidence_root / "primary-terminal.json", "primary_terminal", {"result": "COMPLETE", "layers_completed": primary["layers_completed"], "output_sha256": hashlib.sha256(json.dumps(primary, sort_keys=True, separators=(",", ":")).encode()).hexdigest()})
        bank_runtime_artifact(evidence_root / "secondary-continuity.json", "secondary_descriptor_continuity_report", {"descriptor_count": 5, "ordinals": [2, 3, 4, 5, 6], "descriptor_identities": descriptors, "path_reopen_count": 0})
        secondary = execute_secondary(candidate, descriptors, leases.inherited_fds())
        bank_runtime_artifact(evidence_root / "secondary-terminal.json", "secondary_terminal", {"result": "COMPLETE", "layers_completed": secondary["layers_completed"], "output_sha256": hashlib.sha256(json.dumps(secondary, sort_keys=True, separators=(",", ":")).encode()).hexdigest()})
        comparison = compare(primary, secondary)
        bank_runtime_artifact(evidence_root / "comparison-terminal.json", "comparison_terminal", comparison)
        release = leases.release()
        bank_runtime_artifact(evidence_root / "descriptor-release.json", "descriptor_release_terminal", release)
        accounting = deltas(package_started=True, primary_started=True, secondary_started=True)
        bank_runtime_artifact(evidence_root / "package-terminal.json", "package_terminal", {"result": "COMPLETE", "classification": comparison["classification"], "accounting": accounting, "mandatory_stop": True})
        docs = design.load_documents()
        projection = evidence_root / "causal-projection"
        projection.mkdir()
        constructed = construct_outcome("COMPLETE_SUCCESS", projection, docs["artifact_dag"], docs["artifact_schemas"], docs["outcomes"])
        return {"result": "PASS", "candidate_sha256": handshake["candidate_sha256"], "identity": identity, "primary": primary, "secondary": secondary, "comparison": comparison, "release": release, "accounting": accounting, "causal_projection": constructed, "original_checkpoint_access": 0}
    except ValueError as exc:
        release = {"attempted_closures": 0, "successful_closures": 0, "duplicate_closures": 0, "unknown_leases": 0, "live_leases_after_release": 0, "lease_ids": []}
        if leases is not None and not leases.closed:
            release = leases.release()
        bank_runtime_artifact(evidence_root / "failure-terminal.json", "failure_terminal_capsule", {"classification": "DESCRIPTOR_LEASE_ACTIVATION_FAILURE", "controlled_failure_class": "ValueError", "message": str(exc), "release": release, "mandatory_stop": True})
        return {"result": "CONTROLLED_FAILURE", "failure_class": "ValueError", "message": str(exc), "release": release, "accounting": deltas(package_started=True, primary_started=False, secondary_started=False), "original_checkpoint_access": 0}
