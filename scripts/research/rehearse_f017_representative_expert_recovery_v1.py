#!/usr/bin/env python3
"""Real-geometry synthetic rehearsal for representative expert recovery."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Callable

import numpy as np

from f017_representative_expert_recovery_executor_v1 import (
    OpenOnce, SELECTED_IDS, canonical, compute_outputs, sha_bytes,
)


def sparse_zero(path: Path, length: int) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.ftruncate(descriptor, length)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    path.chmod(0o400)
    digest = hashlib.sha256()
    block = b"\0" * (1024 * 1024)
    remaining = length
    while remaining:
        part = block[:min(len(block), remaining)]
        digest.update(part)
        remaining -= len(part)
    return digest.hexdigest()


def gate(document: dict[str, Any]) -> None:
    ids = document.get("selected_expert_ids")
    if ids != list(SELECTED_IDS) or len(set(ids or [])) != 8:
        raise ValueError("EXPERT_ORDER")
    pairs = document.get("route_pairs", [])
    if [(x.get("expert_id"), x.get("routing_weight")) for x in pairs] != [
        (expert, weight) for expert, weight in zip(document["selected_expert_ids"], document["routing_weights"], strict=True)
    ]:
        raise ValueError("ID_WEIGHT_PAIR")
    inventory = document.get("retained_payload_inventory", [])
    if len(inventory) != 24 or [x.get("ordinal") for x in inventory] != list(range(24)):
        raise ValueError("INVENTORY")
    if [(x.get("expert_id"), x.get("role")) for x in inventory] != [
        (expert, role) for expert in SELECTED_IDS for role in ("gate", "up", "down")
    ]:
        raise ValueError("INVENTORY_ORDER")
    if document.get("representative_expert_input", {}).get("sha256") != "687a692a452e30860c34055942061f4ff368ec0e1c815439c71e457a444fe62c":
        raise ValueError("INPUT_SHA")
    accounting = document.get("access_accounting", {})
    if accounting.get("new_checkpoint_payload_reads") != 0 or accounting.get("shard_opens") != 0:
        raise ValueError("CHECKPOINT_CAPABILITY")
    if accounting.get("starting_real_payload_ledger") != 175 or accounting.get("successful_terminal_ledger") != 175:
        raise ValueError("LEDGER")
    if any(document.get("failure_semantics", {}).get(key) is not False for key in ("retry", "resume", "second_attempt")):
        raise ValueError("RETRY")
    if not all(document.get("prohibitions", {}).get(key) is True for key in (
        "checkpoint_access", "shard_open", "historical_direct_dprefix_input",
        "historical_direct_dprefix_outputs", "routed_aggregate", "shared_expert", "ffn_completion",
    )):
        raise ValueError("PROHIBITIONS")


def internal_once(candidate: Path, fixture_root: Path) -> dict[str, Any]:
    document = json.loads(candidate.read_text())
    normalized_path = fixture_root / "input.f32le"
    normalized_sha = sha_bytes(normalized_path.read_bytes())
    normalized = OpenOnce(normalized_path, normalized_sha, 24576, "SYNTHETIC_INPUT")
    packed: list[OpenOnce] = []
    try:
        for item in document["retained_payload_inventory"]:
            path = fixture_root / "packed" / f"{item['ordinal']:02d}.bin"
            packed.append(OpenOnce(path, sha_bytes(path.read_bytes()), item["packed_bytes"], f"SYNTHETIC_{item['ordinal']:02d}"))
        outputs = compute_outputs(document, normalized, packed, synthetic=True)
        after = normalized.verify_after()
        for handle in packed:
            handle.verify_after()
    finally:
        normalized.close()
        for handle in packed:
            handle.close()
    return {
        "output_sha256_by_expert": {str(k): sha_bytes(v) for k, v in outputs.items()},
        "input_after_sha256": after,
        "checkpoint_reads": 0, "shard_opens": 0, "real_expert_executions": 0,
        "synthetic_expert_computations": 8,
    }


def expect_reject(document: dict[str, Any], mutate: Callable[[dict[str, Any]], None]) -> bool:
    candidate = copy.deepcopy(document)
    mutate(candidate)
    try:
        gate(candidate)
    except Exception:
        return True
    return False


def rehearsal(candidate: Path, output: Path) -> dict[str, Any]:
    document = json.loads(candidate.read_text())
    gate(document)
    with tempfile.TemporaryDirectory(prefix="f017-representative-expert-rehearsal-") as directory:
        root = Path(directory)
        input_sha = sparse_zero(root / "input.f32le", 24576)
        packed_sha = {}
        for item in document["retained_payload_inventory"]:
            packed_sha[str(item["ordinal"])] = sparse_zero(root / "packed" / f"{item['ordinal']:02d}.bin", item["packed_bytes"])
        runs = []
        for _ in range(2):
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--internal-once", "--candidate", str(candidate), "--fixture-root", str(root)],
                check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                env={**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"},
            )
            if completed.returncode:
                raise RuntimeError(completed.stderr)
            runs.append(json.loads(completed.stdout))
        if runs[0] != runs[1]:
            raise RuntimeError("FRESH_PROCESS_MISMATCH")
        mutations: list[tuple[str, Callable[[dict[str, Any]], None]]] = [
            ("swapped_62_73", lambda x: x["selected_expert_ids"].__setitem__(3, 73)),
            ("weight_reassignment", lambda x: x["route_pairs"][0].__setitem__("routing_weight", x["routing_weights"][1])),
            ("duplicate_expert", lambda x: x["selected_expert_ids"].__setitem__(7, 250)),
            ("omitted_expert", lambda x: x["selected_expert_ids"].pop()),
            ("extra_expert", lambda x: x["selected_expert_ids"].append(1)),
            ("historical_route", lambda x: x.__setitem__("selected_expert_ids", [250,10,237,73,62,177,218,28])),
            ("wrong_input", lambda x: x["representative_expert_input"].__setitem__("sha256", "0"*64)),
            ("reordered_payload", lambda x: x["retained_payload_inventory"].__setitem__(0, x["retained_payload_inventory"][1])),
            ("extra_payload", lambda x: x["retained_payload_inventory"].append(copy.deepcopy(x["retained_payload_inventory"][0]))),
            ("checkpoint_read", lambda x: x["access_accounting"].__setitem__("new_checkpoint_payload_reads", 1)),
            ("shard_open", lambda x: x["access_accounting"].__setitem__("shard_opens", 1)),
            ("wrong_start_ledger", lambda x: x["access_accounting"].__setitem__("starting_real_payload_ledger", 174)),
            ("wrong_success_ledger", lambda x: x["access_accounting"].__setitem__("successful_terminal_ledger", 176)),
            ("retry", lambda x: x["failure_semantics"].__setitem__("retry", True)),
            ("resume", lambda x: x["failure_semantics"].__setitem__("resume", True)),
            ("second_attempt", lambda x: x["failure_semantics"].__setitem__("second_attempt", True)),
            ("direct_output_reuse", lambda x: x["prohibitions"].__setitem__("historical_direct_dprefix_outputs", False)),
            ("aggregate", lambda x: x["prohibitions"].__setitem__("routed_aggregate", False)),
            ("shared", lambda x: x["prohibitions"].__setitem__("shared_expert", False)),
            ("ffn_completion", lambda x: x["prohibitions"].__setitem__("ffn_completion", False)),
        ]
        failures = {name: expect_reject(document, mutation) for name, mutation in mutations}
        if not all(failures.values()):
            raise RuntimeError("FAILURE_REHEARSAL")
        evidence = {
            "schema": "pulsarmlx.f017.representative-expert-recovery-synthetic-rehearsal",
            "schema_version": "1.0.0",
            "candidate_semantic_sha256": document["candidate_semantic_sha256"],
            "producer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "real_geometry": {
                "expert_count": 8, "retained_payload_count": 24,
                "retained_packed_bytes": 90_439_680,
                "decoded_bytes_per_matrix": 50_331_648,
                "peak_three_matrix_decoded_bytes": 150_994_944,
                "input_shape": [6144], "gate_up_shape": [2048,6144], "down_shape": [6144,2048],
                "output_shapes": [[6144]] * 8,
            },
            "synthetic_input_sha256": input_sha,
            "synthetic_packed_sha256_by_ordinal": packed_sha,
            "fresh_process_runs": 2,
            "fresh_process_exact_output_identity": True,
            "success_output_sha256_by_expert": runs[0]["output_sha256_by_expert"],
            "failure_paths": failures,
            "failure_paths_passed": sum(failures.values()),
            "failure_paths_required": len(failures),
            "checkpoint_reads": 0, "shard_opens": 0, "real_ledger_delta": 0,
            "real_expert_executions": 0,
        }
    output.write_bytes(canonical(evidence) + b"\n")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fixture-root", type=Path)
    parser.add_argument("--internal-once", action="store_true")
    args = parser.parse_args()
    if args.internal_once:
        print(canonical(internal_once(args.candidate, args.fixture_root)).decode())
    else:
        if args.output is None:
            raise ValueError("OUTPUT_REQUIRED")
        value = rehearsal(args.candidate, args.output)
        print(hashlib.sha256(args.output.read_bytes()).hexdigest(), value["failure_paths_passed"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
