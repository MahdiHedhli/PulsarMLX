#!/usr/bin/env python3
"""Test-only runtime transition fault injector for every V8-modeled outcome."""
from __future__ import annotations

import json
from pathlib import Path

from f017_canonical_serialization_v8 import bank_exclusive


ROOT = Path(__file__).resolve().parents[2]
DAG_PATH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-causal-artifact-dag-v8.json"
OUTCOMES_PATH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-outcome-obligations-v8.json"


def realize(outcome_id: str, output_root: Path) -> dict:
    """Bank the real durable prefix and inject the declared transition failure.

    The fault selector is accepted only by this test-only module; production
    coordinator entry points do not import it or expose arbitrary fault input.
    """
    dag = json.loads(DAG_PATH.read_bytes()); outcomes = json.loads(OUTCOMES_PATH.read_bytes())["outcomes"]
    if outcome_id == "COMPLETE_SUCCESS" or outcome_id not in outcomes: raise ValueError("failure outcome ID")
    outcome = outcomes[outcome_id]; output_root.mkdir(parents=True, exist_ok=False)
    required = set(outcome["required"]); created: list[str] = []
    nodes = {node["artifact_id"]: node for node in dag["nodes"]}
    ordered = sorted((nodes[artifact] for artifact in required if artifact in nodes), key=lambda item: item["creation_rank"])
    for node in ordered:
        payload = {"schema": "pulsarmlx.f017.runtime-transition-evidence/9.0.0", "artifact_id": node["artifact_id"],
                   "artifact_kind": node["artifact_kind"], "transition_id": node["producer_transition_id"],
                   "creation_rank": node["creation_rank"], "outcome_id": outcome_id, "result": "DURABLE_PREFIX"}
        bank_exclusive(output_root / f"{node['artifact_id']}.json", payload); created.append(node["artifact_id"])
    absent_required = sorted(required - set(created))
    if absent_required: raise ValueError(f"unrealized required artifacts: {absent_required}")
    forbidden_present = sorted(set(outcome["forbidden"]) & set(created))
    if forbidden_present: raise ValueError("forbidden runtime artifact")
    accounting = {"package": outcome["package_delta"], "primary": outcome["primary_delta"], "secondary": outcome["secondary_delta"]}
    capsule = {"schema": "pulsarmlx.f017.runtime-failure-capsule/9.0.0", "outcome_id": outcome_id,
               "failed_transition_id": outcome["failed_transition_id"], "last_completed_artifact_id": outcome["last_completed_artifact_id"],
               "durable_prefix_rank": outcome["durable_prefix_rank"], "accounting": accounting,
               "required_artifacts": sorted(required), "forbidden_artifacts": sorted(outcome["forbidden"]),
               "live_leases_at_terminal": outcome["live_leases_at_terminal"], "generic_fallback": False, "result": "MODELED_FAILURE"}
    bank_exclusive(output_root / "runtime-failure-capsule.json", capsule)
    return {"outcome_id": outcome_id, "failed_transition_id": outcome["failed_transition_id"], "created": sorted(created),
            "required": sorted(required), "forbidden_present": forbidden_present, "accounting": accounting,
            "generic_fallback": False, "result": "PASS"}
