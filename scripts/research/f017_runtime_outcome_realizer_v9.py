#!/usr/bin/env python3
"""Test-only driver that faults actual V9 lifecycle transitions."""
from __future__ import annotations

import json
import os
from pathlib import Path

import execute_f017_corrected_oracle_event_v9 as coordinator
from f017_lifecycle_artifact_v8 import bank_runtime_artifact
from f017_corrected_oracle_event_accounting_v9 import derive
from f017_synthetic_checkpoint_v9 import prepare
from validate_f017_corrected_oracle_access_v9 import install_rehearsal_candidate, render_rehearsal_candidate

ROOT = Path(__file__).resolve().parents[2]
DAG_PATH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-causal-artifact-dag-v8.json"
OUTCOMES_PATH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-outcome-obligations-v8.json"
OUTCOMES = json.loads(OUTCOMES_PATH.read_bytes())["outcomes"]
NODES = {node["artifact_id"]: node for node in json.loads(DAG_PATH.read_bytes())["nodes"]}


def _artifact_id(path: Path, kind: str) -> str | None:
    if kind == "checkpoint_access_event":
        return path.stem.replace("checkpoint-access-event-", "checkpoint_access_event_")
    if kind == "checkpoint_shard_receipt":
        return path.stem.replace("checkpoint-shard-receipt-", "checkpoint_shard_receipt_")
    return kind if kind in NODES else None


def _early_capsule(root: Path, outcome_id: str) -> dict:
    outcome = OUTCOMES[outcome_id]
    artifact_id = next(item for item in outcome["required"] if item.startswith("failure_terminal_capsule__"))
    payload = {"outcome_id": outcome_id, "classification": outcome["outcome_class"],
               "failed_transition_id": outcome["failed_transition_id"],
               "last_completed_transition_id": outcome["last_completed_artifact_id"],
               "accounting": {"authorization": 0, "package": 0, "primary": 0, "secondary": 0,
                              "historical_before": 175, "historical_after": 175},
               "package_terminal_evidence": False, "generic_fallback": False, "mandatory_stop": True}
    bank_runtime_artifact(root / f"{artifact_id}.json", artifact_id, payload)
    return {"result": "CONTROLLED_FAILURE", "generic_fallback": payload["generic_fallback"],
            "outcome_id": outcome_id, "accounting": payload["accounting"]}


def realize(outcome_id: str, output_root: Path) -> dict:
    """Execute real authorizer/coordinator operations and fail after one rank."""
    if outcome_id == "COMPLETE_SUCCESS" or outcome_id not in OUTCOMES:
        raise ValueError("failure outcome ID")
    outcome = OUTCOMES[outcome_id]; target_rank = outcome["durable_prefix_rank"]
    output_root.mkdir(parents=True, exist_ok=False); pre = output_root / "prestate"; pre.mkdir()
    checkpoint, shards, catalog, manifest = prepare(output_root, 18101, f"OUTCOME-{target_rank:03d}", False)
    candidate_path = output_root / "candidate.json"; installed = output_root / "installed" / "authorization.json"
    receipt = output_root / "installation-receipt.json"

    runtime_result: dict
    bank_runtime_artifact(pre / "operator_approval.json", "operator_approval", {"scope": "SYNTHETIC_FAULT_QUALIFICATION", "result": "PASS"})
    if target_rank == 1:
        runtime_result = _early_capsule(pre, outcome_id)
    else:
        rendered = render_rehearsal_candidate(checkpoint, shards, catalog, candidate_path, f"OUTCOME-{target_rank:03d}",
                                               scope="SYNTHETIC_QUALIFICATION", manifest_path=manifest)
        bank_runtime_artifact(pre / "candidate_authorization.json", "candidate_authorization",
                              {"candidate_sha256": rendered["candidate_sha256"], "result": "PASS"})
        if target_rank == 2:
            runtime_result = _early_capsule(pre, outcome_id)
        else:
            bank_runtime_artifact(pre / "primary_candidate_validation.json", "primary_candidate_validation", rendered["primary"])
            if target_rank == 3:
                runtime_result = _early_capsule(pre, outcome_id)
            else:
                bank_runtime_artifact(pre / "secondary_candidate_validation.json", "secondary_candidate_validation", rendered["secondary"])
                if target_rank == 4:
                    runtime_result = _early_capsule(pre, outcome_id)
                elif target_rank == 5:
                    installed.parent.mkdir(parents=True)
                    raw = candidate_path.read_bytes()
                    with installed.open("xb") as sink:
                        sink.write(raw); sink.flush(); os.fsync(sink.fileno())
                    bank_runtime_artifact(pre / "installed_authorization.json", "installed_authorization",
                                          {"installed_sha256": rendered["candidate_sha256"], "result": "PASS"})
                    runtime_result = _early_capsule(pre, outcome_id)
                else:
                    installed_receipt = install_rehearsal_candidate(candidate_path, installed, receipt)
                    bank_runtime_artifact(pre / "installed_authorization.json", "installed_authorization",
                                          {"installed_sha256": rendered["candidate_sha256"], "result": "PASS"})
                    bank_runtime_artifact(pre / "installation_receipt.json", "installation_receipt", installed_receipt)
                    if target_rank == 6:
                        runtime_result = _early_capsule(pre, outcome_id)
                    else:
                        original_bank = coordinator.bank_runtime_artifact
                        injected = False
                        def fault_bank(path: Path, kind: str, payload: dict) -> str:
                            nonlocal injected
                            digest = original_bank(path, kind, payload); artifact_id = _artifact_id(path, kind)
                            if not injected and artifact_id is not None and NODES[artifact_id]["creation_rank"] == target_rank:
                                injected = True
                                raise coordinator.ModeledTransitionFailure(
                                    outcome_id, outcome["failed_transition_id"], artifact_id)
                            return digest
                        coordinator.bank_runtime_artifact = fault_bank
                        try:
                            runtime_result = coordinator.execute_synthetic(installed, receipt, output_root / "runtime")
                        finally:
                            coordinator.bank_runtime_artifact = original_bank
                        if runtime_result.get("outcome_id") != outcome_id or runtime_result.get("generic_fallback") is not False:
                            raise ValueError("runtime did not realize selected modeled failure")

    created: set[str] = set()
    for path in output_root.rglob("*.json"):
        try: value = json.loads(path.read_bytes())
        except (OSError, ValueError): continue
        kind = value.get("artifact_kind") if type(value) is dict else None
        artifact_id = _artifact_id(path, kind) if type(kind) is str else None
        if artifact_id in NODES: created.add(artifact_id)
    required = set(outcome["required"]); forbidden_present = sorted(set(outcome["forbidden"]) & created)
    missing = sorted(required - created)
    if missing or forbidden_present:
        raise ValueError(f"runtime outcome artifact mismatch missing={missing} forbidden={forbidden_present}")
    observed = derive((output_root / "runtime").resolve(strict=False))
    accounting = {key: observed[key] for key in ("package", "primary", "secondary")}
    capsule_source = ("AUTHORIZER_PHASE_DIRECT_TERMINALIZATION" if target_rank <= 6
                      else "COORDINATOR_CAUSAL_BANK_INJECTION")
    return {"outcome_id": outcome_id, "failed_transition_id": outcome["failed_transition_id"], "created": sorted(created),
            "required": sorted(required), "forbidden_present": forbidden_present, "accounting": accounting,
            "capsule_source": capsule_source, "generic_fallback": runtime_result.get("generic_fallback"),
            "terminalization_result": runtime_result.get("result"), "result": "PASS"}
