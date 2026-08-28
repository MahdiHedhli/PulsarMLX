#!/usr/bin/env python3
"""Failure/outcome qualification for the Event 06 numerical bridge."""
from __future__ import annotations

import json
from pathlib import Path

from qualify_f017_event06_numerical_bridge_v1 import qualify

ROOT = Path(__file__).resolve().parents[2]


def qualify_failures() -> dict:
    mutation = qualify()
    lifecycle = json.loads((ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-event06-v12-to-v11-bridge-lifecycle-v3.json").read_text())
    outcomes = lifecycle["outcomes"]
    modeled = sum(len(item["failures"]) for item in outcomes)
    exact = all(item.get("durable_prefix") and item.get("next") and item.get("leases") for item in outcomes)
    result = {"schema":"pulsarmlx.f017.event06-v12-to-v11-bridge-failure-qualification/1.0.0",
        "modeled_failure_classes":modeled,"lifecycle_phases":len(outcomes),
        "substantive_mutation_cases":mutation["mutation_cases_rejected"],
        "unexpected_passes":mutation["unexpected_passes"],"phase_specific_outcomes":"PASS" if exact else "FAIL",
        "generic_fallback":"PROHIBITED","retries":0,"resume":False,"original_checkpoint_access":0,
        "numerical_operations":0,"event06_ids_consumed":0,"event06_executed":False}
    result["result"] = "PASS" if exact and result["unexpected_passes"] == 0 else "FAIL"
    return result


if __name__ == "__main__":
    print(json.dumps(qualify_failures(), sort_keys=True, separators=(",",":")))
