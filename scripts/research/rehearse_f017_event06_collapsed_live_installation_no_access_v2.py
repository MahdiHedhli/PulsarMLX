#!/usr/bin/env python3
"""Production-shaped no-access rehearsal for the Sequence 14 public path."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from f017_event06_sequence14_fixture_v1 import build_sequence14_qualification
from rehearse_f017_event06_bridge_no_access_v1 import rehearse as rehearse_bridge


def rehearse() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="f017-seq14-rehearsal-") as directory:
        package = build_sequence14_qualification(Path(directory))
        counters = dict(package["state"].snapshot())
        gate = package["gate"]
    bridge = rehearse_bridge()
    forbidden = {
        name: counters[name]
        for name in (
            "sanitized_human_decisions_from_live_go",
            "collapsed_live_go_tokens",
            "canonical_live_reservations",
            "live_checkpoint_root_resolutions",
            "live_installation_commit_calls",
            "live_authorities_or_capabilities",
            "package_starts",
            "original_checkpoint_shard_opens",
            "original_checkpoint_identity_hash_reads",
            "original_checkpoint_payload_reads",
            "original_checkpoint_mmaps_or_tensor_reads",
            "numerical_operations",
            "event06_identities_instantiated",
            "event06_identities_consumed",
            "authorization_delta",
            "package_delta",
            "primary_delta",
            "secondary_delta",
            "p1_actions",
        )
    }
    if any(forbidden.values()):
        raise AssertionError(f"live no-access counter changed: {forbidden}")
    if gate.get("result") != "PASS" or gate.get("package_started") is not False:
        raise AssertionError("package-start gate posture")
    if bridge["result"] != "PASS":
        raise AssertionError("existing bridge no-access proof")
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence14-production-shaped-no-access-rehearsal/1.0.0",
        "future_public_path_through_package_start_eligibility": "PASS",
        "existing_bridge_no_access_proof": "PASS",
        "gate_result": "PASS",
        "gate_package_started": False,
        "observed_production_boundary_counters": forbidden,
        "event_04_retry": False,
        "event_05_retry_or_resume": False,
        "prior_event_06_retry_or_resume": False,
        "p1_actions": 0,
        "historical_master_ledger": 175,
        "original_checkpoint_access": "NONE",
        "event_06_executed": False,
        "result": "PASS",
    }


if __name__ == "__main__":
    print(json.dumps(rehearse(), sort_keys=True, separators=(",", ":")))
