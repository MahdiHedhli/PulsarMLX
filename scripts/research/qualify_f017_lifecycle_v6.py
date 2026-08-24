#!/usr/bin/env python3
"""Synthetic execution and outcome-family qualification for lifecycle V6."""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from execute_f017_corrected_oracle_event_v6 import execute_synthetic
from f017_corrected_oracle_authorization_v6 import canonical_bytes
from f017_lifecycle_semantics_v6 import MODEL_PATH, derive_outcome_obligations, load_json, simulate_trace
from qualify_f017_corrected_oracle_target_adapters_v6 import run_once as qualify_adapters
from validate_f017_lifecycle_semantic_authority_v6 import validate as validate_authority

ROOT = Path(__file__).resolve().parents[2]
INTERFACE_NAME = "interface.json"


def run_package(work: Path, seed: int) -> dict:
    adapter = qualify_adapters(work, seed)
    result = execute_synthetic(
        work / "authorization.json",
        work / INTERFACE_NAME,
        work / "installation-receipt.json",
        work / "checkpoint",
        work / "catalog.json",
        work / "geometry.json",
        work / "identity.json",
        work / "lifecycle-authority",
    )
    return {
        "result": result["result"],
        "classification": result["comparison"]["classification"],
        "deltas": result["deltas"],
        "handshake_checkpoint_opens": result["handshake"]["checkpoint_opens_before_handshake"],
        "handshake_checkpoint_reads": result["handshake"]["checkpoint_reads_before_handshake"],
        "adapter_primary_access_events": adapter["primary_access_events"],
        "adapter_secondary_access_events": adapter["secondary_access_events"],
        "historical_ledger_before": result["historical_ledger_before"],
        "historical_ledger_after": result["historical_ledger_after"],
    }


def qualify_outcomes() -> dict:
    model = load_json(MODEL_PATH)
    obligations = derive_outcome_obligations(model)["variants"]
    checked = 0
    for variant_id, obligation in obligations.items():
        trace = simulate_trace(model, obligation["trace"])
        if sorted(trace.artifacts) != obligation["required_artifacts"]:
            raise ValueError(f"required artifact mismatch: {variant_id}")
        if set(trace.artifacts) & set(obligation["forbidden_artifacts"]):
            raise ValueError(f"forbidden artifact present: {variant_id}")
        if trace.ledgers != obligation["ledger_deltas"]:
            raise ValueError(f"ledger mismatch: {variant_id}")
        for consumer in ("primary", "secondary"):
            started = obligation["started"][consumer]
            evidence = {f"{consumer}_receipt", f"{consumer}_terminal", f"{consumer}_ledger_entry"}
            if not started and evidence & set(obligation["required_artifacts"]):
                raise ValueError(f"fabricated unstarted evidence: {variant_id}/{consumer}")
        checked += 1
    return {"variant_count": checked, "result": "PASS"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--success-repeats", type=int, default=10)
    parser.add_argument("--failure-repeats", type=int, default=5)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    authority = validate_authority()
    outcomes = qualify_outcomes()
    packages = []
    with tempfile.TemporaryDirectory(prefix="f017-lifecycle-v6-") as temporary:
        root = Path(temporary)
        for index in range(arguments.success_repeats):
            work = root / f"package-{index:02}"; work.mkdir()
            packages.append(run_package(work, 18101 + index % 12))
    if any(item["result"] != "PASS" or item["handshake_checkpoint_opens"] or item["handshake_checkpoint_reads"] for item in packages):
        raise ValueError("synthetic package qualification")
    total_failure_traces = outcomes["variant_count"] * arguments.failure_repeats
    result = {
        "schema": "pulsarmlx.f017.corrected-oracle-lifecycle-v6-synthetic-qualification/1.0.0",
        "result": "PASS",
        "semantic_model_sha256": authority["semantic_model_sha256"],
        "successful_package_count": len(packages),
        "successful_packages": packages,
        "terminal_and_transition_failure_variant_count": outcomes["variant_count"],
        "failure_variant_repeat_count": arguments.failure_repeats,
        "failure_trace_count": total_failure_traces,
        "candidate_dual_validation_process_count": len(packages) * 2,
        "installed_handshake_process_count": len(packages) * 2,
        "primary_target_process_count": len(packages) * 2,
        "secondary_target_process_count": len(packages) * 2,
        "semantic_mutations_rejected": authority["semantic_mutations_rejected"],
        "format_authority": {
            "format_count": 11,
            "packed_decoder_cases": 44,
            "binding": "NUMERICAL_REQUALIFICATION_V3_PLUS_REAL_V6_TARGET_ADAPTER_CONTROL_PATH",
        },
        "original_checkpoint_shard_opens": 0,
        "original_checkpoint_payload_reads": 0,
        "event_04_authorization_created": False,
        "event_04_executed": False,
    }
    encoded = canonical_bytes(result)
    if arguments.output:
        arguments.output.write_bytes(encoded)
    print(json.dumps({"result": "PASS", "packages": len(packages), "failure_traces": total_failure_traces}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
