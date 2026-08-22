#!/usr/bin/env python3
"""Run the real bounded-P1 producer with only the inert tensor-math source.

The executable is launched in ten fresh processes.  This script never accepts
or resolves a checkpoint path and rejects an output root that already exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path


COUNTERS = {
    "callback_count",
    "managed_created",
    "managed_destroyed",
    "derived_created",
    "derived_destroyed",
    "default_cpu_stream_created",
    "default_cpu_stream_freed",
    "default_gpu_stream_created",
    "default_gpu_stream_freed",
    "owned_stream_created",
    "owned_stream_freed",
    "native_default_cpu_stream_freed",
    "native_default_gpu_stream_freed",
    "native_owned_stream_freed",
    "native_live_stream_handles",
    "native_duplicate_free_attempts",
    "native_origin_mismatches",
    "context_active",
    "registrations",
    "teardowns",
    "in_flight_work",
    "stale_native_ready_generations",
}

RECEIPT_KEYS = {
    "schema",
    "event_class",
    "authorization_id",
    "attempt_id",
    "domain_declaration_sha256",
    "final_review_sha256",
    "human_approval_sha256",
    "contract_sha256",
    "executor_sha256",
    "git_head",
    "historical_master_ledger_sha256",
    "d0_sha256",
    "d1_sha256",
    "d2_sha256",
    "d3_5_result_sha256",
    "d3_5_acceptance_sha256",
    "synthetic_full_graph_result_sha256",
    "checkpoint_manifest_sha256",
    "checkpoint_catalog_sha256",
    "checkpoint_set_sha256",
    "runtime",
    "accounting_before",
    "accounting_after",
    "prompt_token",
    "result_token",
    "generated_token_count",
    "native_event_delta",
    "historical_master_before",
    "historical_master_after",
    "historical_master_delta",
    "mandatory_stop_observed",
    "execution_result",
    "terminal_state",
    "started_at_unix_ns",
    "completed_at_unix_ns",
}

RUNTIME_KEYS = {
    "mlx_version",
    "mlx_c_version",
    "architecture",
    "machine_brand",
    "stream_origin",
    "native_handle_owned",
    "deallocation_responsibility",
}

TERMINAL_KEYS = {
    "schema",
    "state",
    "authorization_id",
    "attempt_id",
    "owner_pid",
    "ownership_nonce",
    "receipt_count",
    "receipt_sha256",
    "terminalized_at_unix_ns",
    "retry_permitted",
}

SUMMARY_KEYS = {
    "schema",
    "fixture_sha256",
    "authorization_id",
    "attempt_id",
    "prompt_token",
    "expected_token",
    "result_token",
    "generated_token_count",
    "mandatory_stop_observed",
    "terminal_state",
    "historical_master_delta",
    "original_checkpoint_reads",
    "full_real_checkpoint_inference_executed",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_exact(path: Path) -> dict[str, object]:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key} in {path}")
            result[key] = value
        return result

    value = json.loads(path.read_text(), object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError(f"expected object in {path}")
    return value


def exact_keys(value: dict[str, object], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(
            f"{label} key census mismatch: missing={sorted(expected - set(value))} "
            f"extra={sorted(set(value) - expected)}"
        )


def validate_accounting_liveness(before: dict[str, int], after: dict[str, int]) -> None:
    deltas = {name: after[name] - before[name] for name in COUNTERS}
    if any(value < 0 for value in deltas.values()):
        raise ValueError("accounting counter regressed")
    required_positive = {
        "callback_count",
        "managed_created",
        "managed_destroyed",
        "owned_stream_created",
        "owned_stream_freed",
        "native_owned_stream_freed",
        "registrations",
        "teardowns",
    }
    if any(deltas[name] <= 0 for name in required_positive) or not any(deltas.values()):
        raise ValueError("accounting snapshot lacks required live lifecycle deltas")
    if deltas["managed_created"] != deltas["managed_destroyed"] \
            or deltas["callback_count"] != deltas["managed_destroyed"] \
            or deltas["owned_stream_created"] != deltas["owned_stream_freed"] \
            or deltas["owned_stream_freed"] != deltas["native_owned_stream_freed"] \
            or deltas["registrations"] != deltas["teardowns"]:
        raise ValueError("accounting liveness deltas do not reconcile")


def validate_run(
    state: Path, summary_path: Path, fixture_sha: str, authority: dict[str, object]
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    summary = parse_exact(summary_path)
    exact_keys(summary, SUMMARY_KEYS, "summary")
    attempt = state / str(authority["attempt_id"])
    receipt_path = attempt / "execution-receipt.json"
    terminal_path = attempt / "terminal.json"
    receipt = parse_exact(receipt_path)
    terminal = parse_exact(terminal_path)
    exact_keys(receipt, RECEIPT_KEYS, "receipt")
    exact_keys(terminal, TERMINAL_KEYS, "terminal")
    exact_keys(receipt["runtime"], RUNTIME_KEYS, "runtime")
    exact_keys(receipt["accounting_before"], COUNTERS, "accounting_before")
    exact_keys(receipt["accounting_after"], COUNTERS, "accounting_after")
    for snapshot in (receipt["accounting_before"], receipt["accounting_after"]):
        if any(type(value) is not int or value < 0 for value in snapshot.values()):
            raise ValueError("counter type/value rejected")
    validate_accounting_liveness(
        receipt["accounting_before"], receipt["accounting_after"]
    )
    required_receipt = {
        "schema": "pulsarmlx.f017.native-bounded-p1-execution-receipt/2.0.0",
        "event_class": "NATIVE_P1_INERT_MATH_BOUNDARY_REHEARSAL",
        "authorization_id": authority["authorization_id"],
        "attempt_id": authority["attempt_id"],
        "prompt_token": 9703,
        "result_token": 21615,
        "generated_token_count": 1,
        "native_event_delta": 0,
        "historical_master_before": 175,
        "historical_master_after": 175,
        "historical_master_delta": 0,
        "mandatory_stop_observed": True,
        "execution_result": "EXPECTED_TOKEN_MATCH",
        "terminal_state": "COMPLETE_MANDATORY_STOP",
    }
    for key, expected in required_receipt.items():
        if receipt[key] != expected:
            raise ValueError(f"receipt {key} mismatch")
    for key in (
        "domain_declaration_sha256",
        "final_review_sha256",
        "human_approval_sha256",
        "contract_sha256",
        "executor_sha256",
        "git_head",
        "historical_master_ledger_sha256",
        "d0_sha256",
        "d1_sha256",
        "d2_sha256",
        "d3_5_result_sha256",
        "d3_5_acceptance_sha256",
        "synthetic_full_graph_result_sha256",
        "checkpoint_manifest_sha256",
        "checkpoint_catalog_sha256",
        "checkpoint_set_sha256",
    ):
        if receipt[key] != authority[key]:
            raise ValueError(f"receipt authority mismatch: {key}")
    if receipt["started_at_unix_ns"] > receipt["completed_at_unix_ns"]:
        raise ValueError("receipt timestamp order")
    if terminal["state"] != "COMPLETE_MANDATORY_STOP" or terminal["receipt_count"] != 1:
        raise ValueError("terminal state/census")
    if terminal["receipt_sha256"] != sha256(receipt_path) or terminal["retry_permitted"]:
        raise ValueError("terminal receipt/retry mismatch")
    if summary["fixture_sha256"] != fixture_sha:
        raise ValueError("summary fixture mismatch")
    if any(
        (
            summary["prompt_token"] != 9703,
            summary["expected_token"] != 21615,
            summary["result_token"] != 21615,
            summary["generated_token_count"] != 1,
            not summary["mandatory_stop_observed"],
            summary["terminal_state"] != "COMPLETE_MANDATORY_STOP",
            summary["historical_master_delta"] != 0,
            summary["original_checkpoint_reads"] != 0,
            summary["full_real_checkpoint_inference_executed"] is not False,
        )
    ):
        raise ValueError("summary semantic mismatch")
    return summary, receipt, terminal


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--authority", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)
    parser.add_argument("--execution-code-head", required=True)
    parser.add_argument("--fresh-processes", type=int, default=10)
    args = parser.parse_args()
    if args.fresh_processes != 10:
        raise SystemExit("fresh-process count is frozen at 10")
    if any("checkpoint" in str(path).lower() for path in (args.fixture, args.authority)):
        raise SystemExit("synthetic inputs may not name checkpoint paths")
    for path in (args.binary, args.fixture, args.authority):
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"unsafe or absent input {path}")
    if args.output_root.exists() or args.evidence_output.exists():
        raise SystemExit("qualification outputs must be absent")
    args.output_root.mkdir(mode=0o700, parents=True)
    authority = parse_exact(args.authority)
    fixture_sha = sha256(args.fixture)
    if sha256(args.binary) != authority["executor_sha256"]:
        raise SystemExit("synthetic executor SHA does not match inert authority")
    runs: list[dict[str, object]] = []
    summary_bytes: list[bytes] = []
    for ordinal in range(1, 11):
        run_root = args.output_root / f"run-{ordinal:02d}-state"
        summary_path = args.output_root / f"run-{ordinal:02d}-summary.json"
        environment = dict(os.environ)
        environment["PULSARMLX_MODEL_GGUF"] = ""
        subprocess.run(
            [
                str(args.binary.resolve()),
                str(args.fixture.resolve()),
                str(args.authority.resolve()),
                str(run_root.resolve()),
                str(summary_path.resolve()),
            ],
            check=True,
            env=environment,
        )
        summary, receipt, terminal = validate_run(
            run_root, summary_path, fixture_sha, authority
        )
        summary_bytes.append(summary_path.read_bytes())
        attempt = run_root / str(authority["attempt_id"])
        runs.append(
            {
                "ordinal": ordinal,
                "fresh_process": True,
                "summary_path": str(summary_path),
                "summary_sha256": sha256(summary_path),
                "receipt_path": str(attempt / "execution-receipt.json"),
                "receipt_sha256": sha256(attempt / "execution-receipt.json"),
                "receipt_schema": receipt["schema"],
                "terminal_path": str(attempt / "terminal.json"),
                "terminal_sha256": sha256(attempt / "terminal.json"),
                "terminal_state": terminal["state"],
                "result_token": summary["result_token"],
            }
        )
    if len(set(summary_bytes)) != 1:
        raise SystemExit("fresh-process summaries are not byte-identical")
    evidence = {
        "schema": "pulsarmlx.f017.native-full-model-synthetic-qualification-evidence/2.0.0",
        "result": "PASS",
        "execution_code_head": args.execution_code_head,
        "binary": {"path": str(args.binary), "sha256": sha256(args.binary)},
        "fixture": {"path": str(args.fixture), "sha256": fixture_sha},
        "inert_authority": {"path": str(args.authority), "sha256": sha256(args.authority)},
        "fresh_processes": 10,
        "same_production_control_path": True,
        "mocked_boundary": "TENSOR_MATH_ONLY",
        "receipt_schema": "pulsarmlx.f017.native-bounded-p1-execution-receipt/2.0.0",
        "summary_byte_identity": "EXACT_10_OF_10",
        "prompt_token": 9703,
        "result_token": 21615,
        "historical_master_before": 175,
        "historical_master_after": 175,
        "historical_master_delta": 0,
        "original_checkpoint_reads": 0,
        "full_model_real_checkpoint_inference_executed": False,
        "real_m1_ultra_p1_executed": False,
        "live_p1_authorization_created": False,
        "runs": runs,
    }
    args.evidence_output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    encoded = (json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n").encode()
    descriptor = os.open(args.evidence_output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    with os.fdopen(descriptor, "wb") as output:
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())
    print(f"PASS evidence_sha256={sha256(args.evidence_output)}")


if __name__ == "__main__":
    main()
