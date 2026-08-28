#!/usr/bin/env python3
"""Failure/outcome qualification for the Event 06 numerical bridge."""
from __future__ import annotations

import json
from pathlib import Path

from qualify_f017_event06_numerical_bridge_v1 import qualify
from qualify_f017_event06_bridge_call_path_v2 import qualify_call_path

ROOT = Path(__file__).resolve().parents[2]


def qualify_failures() -> dict:
    mutation = qualify()
    call_path = qualify_call_path()
    lifecycle = json.loads((ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-event06-v12-to-v11-bridge-lifecycle-v4.json").read_text())
    inherited = json.loads((ROOT / lifecycle["outcomes_inherited_unchanged_from"]).read_text())
    outcomes = inherited["outcomes"]
    release_paths = lifecycle["implemented_release_paths"]
    modeled_failures = [failure for outcome in outcomes for failure in outcome["failures"]]
    exact_outcomes = all(
        type(outcome) is dict
        and set(outcome) == {"phase", "failures", "durable_prefix", "leases", "next"}
        and type(outcome["failures"]) is list and outcome["failures"]
        and outcome["durable_prefix"] and outcome["leases"] and outcome["next"]
        and "GENERIC" not in outcome["next"]
        for outcome in outcomes
    )
    modeled = len(modeled_failures)
    exact = (len(outcomes) == 9 and len(set(modeled_failures)) == modeled
             and exact_outcomes and len(release_paths) == 5
             and lifecycle["generic_fallback"] == "PROHIBITED"
             and lifecycle["retry"] is False and lifecycle["resume"] is False)
    result = {"schema":"pulsarmlx.f017.event06-v12-to-v11-bridge-failure-qualification/1.0.0",
        "modeled_failure_classes":modeled,"lifecycle_outcomes":len(outcomes),
        "unique_failure_outcomes":len(set(modeled_failures)),
        "lifecycle_release_paths":len(release_paths),
        "substantive_mutation_cases":mutation["mutation_cases_rejected"],
        "unexpected_passes":mutation["unexpected_passes"],"phase_specific_outcomes":"PASS" if exact else "FAIL",
        "implemented_failure_release_paths":call_path["failure_release_paths"],
        "success_release_passes":call_path["success_release_passes"],
        "comparison_release_accounting_chain":call_path["comparison_release_accounting_chain"],
        "generic_fallback":"PROHIBITED","retries":0,"resume":False,"original_checkpoint_access":0,
        "numerical_operations":0,"event06_ids_consumed":0,"event06_executed":False}
    result["result"] = "PASS" if (exact and result["unexpected_passes"] == 0
        and result["implemented_failure_release_paths"] == 4
        and result["success_release_passes"] == 1) else "FAIL"
    return result


if __name__ == "__main__":
    print(json.dumps(qualify_failures(), sort_keys=True, separators=(",",":")))
