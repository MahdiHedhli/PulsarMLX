#!/usr/bin/env python3
"""Synthetic execution and outcome-family qualification for lifecycle V6."""
from __future__ import annotations

import argparse
import hashlib
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
NUMERICAL_REQUALIFICATION = ROOT / "docs/architecture/reviews/evidence/f017-corrected-oracle-numerical-requalification-v3.json"


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
        "process_census": {
            "candidate_validation": adapter["process_census"]["candidate_validation"],
            "installed_validation": result["process_census"]["installed_validation"],
            "primary_target": adapter["process_census"]["primary_target"] + result["process_census"]["primary_target"],
            "secondary_target": adapter["process_census"]["secondary_target"] + result["process_census"]["secondary_target"],
        },
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


def execute_failure_variant(work: Path, variant_id: str, obligation: dict) -> dict:
    """Execute one isolated semantic failure trace and durably bank each step.

    This is deliberately a file-backed execution of the independently validated
    state machine, not a multiplied claim derived from a CLI repetition count.
    The successful package family separately exercises the production V6
    authorizer, consumers, installer, coordinator, receipts, and terminals.
    """
    model = load_json(MODEL_PATH)
    work.mkdir(parents=True, exist_ok=False)
    transition_receipts: list[dict] = []
    for ordinal, transition_id in enumerate(obligation["trace"], 1):
        prefix = obligation["trace"][:ordinal]
        trace = simulate_trace(model, prefix)
        receipt = {
            "schema": "pulsarmlx.f017.corrected-oracle-lifecycle-transition-execution/6.0.0",
            "variant_id": variant_id,
            "transition_id": transition_id,
            "ordinal": ordinal,
            "state_after": trace.state,
            "durable_artifacts": sorted(trace.artifacts),
            "ledger_deltas": trace.ledgers,
            "original_checkpoint_shard_opens": 0,
            "original_checkpoint_payload_reads": 0,
        }
        path = work / f"{ordinal:02d}-{transition_id}.json"
        encoded = canonical_bytes(receipt)
        path.write_bytes(encoded)
        readback = path.read_bytes()
        if readback != encoded or json.loads(readback) != receipt:
            raise ValueError(f"failure trace readback: {variant_id}/{transition_id}")
        transition_receipts.append({
            "transition_id": transition_id,
            "path": path.name,
            "sha256": hashlib.sha256(readback).hexdigest(),
        })
    final = simulate_trace(model, obligation["trace"])
    if sorted(final.artifacts) != obligation["required_artifacts"]:
        raise ValueError(f"executed required artifact mismatch: {variant_id}")
    if final.ledgers != obligation["ledger_deltas"] or final.state != obligation["state_reached"]:
        raise ValueError(f"executed semantic result mismatch: {variant_id}")
    summary = {
        "schema": "pulsarmlx.f017.corrected-oracle-lifecycle-failure-trace-execution/6.0.0",
        "variant_id": variant_id,
        "outcome_class": obligation["outcome_class"],
        "transition_receipts": transition_receipts,
        "state_reached": final.state,
        "terminalized": obligation["terminalized"],
        "required_artifacts": sorted(final.artifacts),
        "forbidden_artifacts_absent": not bool(set(final.artifacts) & set(obligation["forbidden_artifacts"])),
        "ledger_deltas": final.ledgers,
        "original_checkpoint_shard_opens": 0,
        "original_checkpoint_payload_reads": 0,
        "result": "PASS",
    }
    summary_path = work / "summary.json"
    summary_path.write_bytes(canonical_bytes(summary))
    if json.loads(summary_path.read_bytes()) != summary:
        raise ValueError(f"failure summary readback: {variant_id}")
    return {
        "variant_id": variant_id,
        "outcome_class": obligation["outcome_class"],
        "transition_count": len(transition_receipts),
        "summary_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "result": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--success-repeats", type=int, default=10)
    parser.add_argument("--failure-repeats", type=int, default=5)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    authority = validate_authority()
    outcomes = qualify_outcomes()
    packages = []
    failure_executions = []
    with tempfile.TemporaryDirectory(prefix="f017-lifecycle-v6-") as temporary:
        root = Path(temporary)
        for index in range(arguments.success_repeats):
            work = root / f"package-{index:02}"; work.mkdir()
            packages.append(run_package(work, 18101 + index % 12))
        obligations = derive_outcome_obligations(load_json(MODEL_PATH))["variants"]
        failure_variants = {
            name: value for name, value in obligations.items()
            if value["outcome_class"] != "COMPLETE_SUCCESS"
        }
        for repeat in range(arguments.failure_repeats):
            for ordinal, (variant_id, obligation) in enumerate(sorted(failure_variants.items())):
                failure_executions.append(execute_failure_variant(
                    root / "failures" / f"repeat-{repeat:02d}" / f"{ordinal:02d}",
                    variant_id,
                    obligation,
                ))
    if any(item["result"] != "PASS" or item["handshake_checkpoint_opens"] or item["handshake_checkpoint_reads"] for item in packages):
        raise ValueError("synthetic package qualification")
    total_failure_traces = len(failure_executions)
    candidate_processes = sum(item["process_census"]["candidate_validation"] for item in packages)
    installed_processes = sum(item["process_census"]["installed_validation"] for item in packages)
    primary_processes = sum(item["process_census"]["primary_target"] for item in packages)
    secondary_processes = sum(item["process_census"]["secondary_target"] for item in packages)
    numerical_requalification_bytes = NUMERICAL_REQUALIFICATION.read_bytes()
    numerical_requalification = json.loads(numerical_requalification_bytes)
    result = {
        "schema": "pulsarmlx.f017.corrected-oracle-lifecycle-v6-synthetic-qualification/1.0.0",
        "result": "PASS",
        "semantic_model_sha256": authority["semantic_model_sha256"],
        "successful_package_count": len(packages),
        "successful_packages": packages,
        "terminal_and_transition_failure_variant_count": outcomes["variant_count"],
        "failure_variant_repeat_count": arguments.failure_repeats,
        "failure_trace_count": total_failure_traces,
        "failure_trace_executions": failure_executions,
        "candidate_dual_validation_process_count": candidate_processes,
        "installed_handshake_process_count": installed_processes,
        "primary_target_process_count": primary_processes,
        "secondary_target_process_count": secondary_processes,
        "semantic_mutations_rejected": authority["semantic_mutations_rejected"],
        "format_authority": {
            "path": NUMERICAL_REQUALIFICATION.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(numerical_requalification_bytes).hexdigest(),
            "format_count": numerical_requalification["format_count"],
            "packed_decoder_cases": numerical_requalification["packed_decoder_case_count"],
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
