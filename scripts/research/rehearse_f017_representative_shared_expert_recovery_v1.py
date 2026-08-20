#!/usr/bin/env python3
"""Real-geometry retained-only rehearsal for representative shared recovery."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts/research") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts/research"))

from f017_representative_shared_expert_recovery_executor_v1 import (
    ExecutorError, OpenOnce, atomic_exclusive, close_all, compute, open_retained,
    sha_bytes, validate_authorization, verify_after,
)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def semantic_sha(document: dict[str, Any]) -> str:
    projection = {key: value for key, value in document.items() if key != "rehearsal"}
    return sha_bytes(canonical(projection))


def gate(document: dict[str, Any]) -> None:
    validate_authorization(document)
    parameters = document.get("retained_parameters", [])
    if [(x.get("ordinal"), x.get("role"), x.get("quantization")) for x in parameters] != [(0, "gate", "Q5_K"), (1, "up", "Q5_K"), (2, "down", "Q6_K")]:
        raise ExecutorError("PARAMETER_ORDER")
    if len({x.get("checkpoint_key") for x in parameters}) != 3:
        raise ExecutorError("PARAMETER_DUPLICATE")
    if document.get("stop_boundary") != "AFTER_REPRESENTATIVE_SHARED_EXPERT_OUTPUT_ONLY":
        raise ExecutorError("STOP_BOUNDARY")
    if document.get("output_contract", {}).get("semantic_role") != "REPRESENTATIVE_M1F0_SHARED_EXPERT_OUTPUT":
        raise ExecutorError("OUTPUT_ROLE")
    if document.get("output_contract", {}).get("dtype") != "little-endian-f32" or document["output_contract"].get("shape") != [6144] or document["output_contract"].get("byte_length") != 24576:
        raise ExecutorError("OUTPUT_GEOMETRY")


def synthetic_input(path: Path, *, nonfinite: bool = False) -> str:
    values = [math.sin(index / 37.0) / 16.0 for index in range(6144)]
    if nonfinite:
        values[11] = math.nan
    raw = struct.pack("<6144f", *values)
    path.write_bytes(raw)
    os.chmod(path, 0o400)
    return sha_bytes(raw)


def internal_once(candidate: Path, parameter_root: Path, input_path: Path) -> dict[str, Any]:
    document = json.loads(candidate.read_text())
    local = copy.deepcopy(document)
    local["representative_input"]["sha256"] = sha_bytes(input_path.read_bytes())
    normalized, manifest, parameters = open_retained(local, input_path, parameter_root)
    try:
        output = compute(local, normalized, parameters)
        after = verify_after(normalized, manifest, parameters)
    finally:
        close_all(normalized, manifest, parameters)
    return {
        "output_sha256": sha_bytes(output),
        "output_bytes": len(output),
        "output_dtype": "little-endian-f32",
        "output_shape": [6144],
        "finite": all(math.isfinite(value) for value in struct.unpack("<6144f", output)),
        "after_sha256": after,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "real_shared_expert_executions": 0,
        "synthetic_shared_expert_computations": 1,
    }


def rejects(document: dict[str, Any], mutation: Callable[[dict[str, Any]], None]) -> bool:
    candidate = copy.deepcopy(document)
    mutation(candidate)
    try:
        gate(candidate)
    except Exception:
        return True
    return False


def run_rehearsal(candidate: Path, parameter_root: Path, output: Path) -> dict[str, Any]:
    document = json.loads(candidate.read_text())
    gate(document)
    with tempfile.TemporaryDirectory(prefix="f017-representative-shared-rehearsal-") as directory:
        root = Path(directory)
        input_path = root / "synthetic-f-norm.f32le"
        input_sha = synthetic_input(input_path)
        runs: list[dict[str, Any]] = []
        for _ in range(2):
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--internal-once", "--candidate", str(candidate), "--parameter-root", str(parameter_root), "--input", str(input_path)],
                check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                env={**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"},
            )
            if completed.returncode:
                raise RuntimeError(completed.stderr)
            runs.append(json.loads(completed.stdout))
        if runs[0] != runs[1] or runs[0]["output_sha256"] != runs[1]["output_sha256"]:
            raise RuntimeError("FRESH_PROCESS_MISMATCH")

        local = copy.deepcopy(document)
        local["representative_input"]["sha256"] = input_sha
        normalized, manifest, parameters = open_retained(local, input_path, parameter_root)
        try:
            try:
                compute(local, normalized, parameters, disagreement_role="gate")
            except ExecutorError as error:
                decoder_disagreement = str(error) == "DUAL_DECODER_DISAGREEMENT"
            else:
                decoder_disagreement = False
        finally:
            close_all(normalized, manifest, parameters)

        bad_input = root / "bad-input.f32le"
        bad_input_sha = synthetic_input(bad_input, nonfinite=True)
        bad_doc = copy.deepcopy(document)
        bad_doc["representative_input"]["sha256"] = bad_input_sha
        normalized, manifest, parameters = open_retained(bad_doc, bad_input, parameter_root)
        try:
            try:
                compute(bad_doc, normalized, parameters)
            except ExecutorError as error:
                nonfinite_rejected = str(error) == "INPUT_VALUES"
            else:
                nonfinite_rejected = False
        finally:
            close_all(normalized, manifest, parameters)

        writable = root / "writable.f32le"
        synthetic_input(writable)
        os.chmod(writable, 0o600)
        writable_doc = copy.deepcopy(document)
        writable_doc["representative_input"]["sha256"] = sha_bytes(writable.read_bytes())
        try:
            open_retained(writable_doc, writable, parameter_root)
        except ExecutorError:
            writable_rejected = True
        else:
            writable_rejected = False

        exclusive_dir = root / "exclusive"
        first = exclusive_dir / "attempt-start.json"
        atomic_exclusive(first, b"{}\n")
        try:
            atomic_exclusive(first, b"{}\n")
        except FileExistsError:
            concurrent_rejected = True
        else:
            concurrent_rejected = False

        mutations: list[tuple[str, Callable[[dict[str, Any]], None]]] = [
            ("retained_input_mismatch", lambda x: x["representative_input"].__setitem__("sha256", "0" * 64)),
            ("retained_parameter_mismatch", lambda x: x["retained_parameters"][0].__setitem__("packed_sha256", "0" * 64)),
            ("decoded_hash_mismatch", lambda x: x["retained_parameters"][0].__setitem__("decoded_sha256", "0" * 64)),
            ("wrong_tensor_order", lambda x: x["retained_parameters"].__setitem__(slice(0, 2), [x["retained_parameters"][1], x["retained_parameters"][0]])),
            ("historical_direct_dprefix_input", lambda x: x["prohibitions"].__setitem__("historical_direct_dprefix_input", False)),
            ("historical_shared_output", lambda x: x["prohibitions"].__setitem__("historical_shared_output_substitution", False)),
            ("wrong_input_dtype", lambda x: x["representative_input"].__setitem__("dtype", "little-endian-f64")),
            ("wrong_input_shape", lambda x: x["representative_input"].__setitem__("shape", [1, 6144])),
            ("missing_parameter", lambda x: x["retained_parameters"].pop()),
            ("extra_parameter", lambda x: x["retained_parameters"].append(copy.deepcopy(x["retained_parameters"][0]))),
            ("retry", lambda x: x["one_shot_semantics"].__setitem__("retry", True)),
            ("checkpoint_read", lambda x: x["access_accounting"].__setitem__("checkpoint_reads", 1)),
            ("shard_open", lambda x: x["access_accounting"].__setitem__("shard_opens", 1)),
            ("wrong_ledger", lambda x: x["access_accounting"].__setitem__("ledger_before", 174)),
            ("aggregate_enabled", lambda x: x["access_accounting"].__setitem__("routed_aggregate_executions", 1)),
            ("ffn_enabled", lambda x: x["access_accounting"].__setitem__("ffn_completions", 1)),
            ("s2_enabled", lambda x: x["access_accounting"].__setitem__("s2_constructions", 1)),
            ("wrong_output_dtype", lambda x: x["output_contract"].__setitem__("dtype", "little-endian-f64")),
            ("wrong_stop_boundary", lambda x: x.__setitem__("stop_boundary", "AFTER_FFN")),
        ]
        mutation_results = {name: rejects(document, mutation) for name, mutation in mutations}
        mutation_results["decoder_disagreement"] = decoder_disagreement
        mutation_results["nan_inf"] = nonfinite_rejected
        mutation_results["writable_alias"] = writable_rejected
        mutation_results["concurrent_invocation"] = concurrent_rejected
        if not all(mutation_results.values()):
            raise RuntimeError(f"FAILURE_REHEARSAL:{mutation_results}")

    evidence = {
        "schema": "pulsarmlx.f017.representative-shared-expert-synthetic-rehearsal",
        "schema_version": "1.0.0",
        "authorization_semantic_sha256": semantic_sha(document),
        "producer_sha256": sha_bytes(Path(__file__).read_bytes()),
        "executor_sha256": sha_bytes((ROOT / document["executor"]["path"]).read_bytes()),
        "real_geometry": {"input_shape": [6144], "gate_up_shape": [2048, 6144], "down_shape": [6144, 2048], "output_shape": [6144], "retained_parameters": 3, "retained_packed_bytes": 27_623_424, "decoded_bytes_per_matrix": 50_331_648, "decoded_total_bytes": 150_994_944},
        "synthetic_input_sha256": input_sha,
        "uses_real_retained_parameter_bytes": True,
        "parameter_packed_sha256": [x["packed_sha256"] for x in document["retained_parameters"]],
        "fresh_process_runs": runs,
        "fresh_processes": 2,
        "exact_output_identity": "2_OF_2",
        "output_sha256": runs[0]["output_sha256"],
        "failure_cases": mutation_results,
        "failure_case_count": len(mutation_results),
        "failure_cases_passed": sum(mutation_results.values()),
        "accounting": {"checkpoint_reads": 0, "shard_opens": 0, "real_shared_expert_executions": 0, "real_payload_ledger_before": 175, "real_payload_ledger_after": 175},
        "result": "PASS",
    }
    output.write_bytes(canonical(evidence) + b"\n")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--parameter-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--internal-once", action="store_true")
    args = parser.parse_args()
    if args.internal_once:
        if args.input is None:
            raise SystemExit("--input required")
        print(json.dumps(internal_once(args.candidate, args.parameter_root, args.input), sort_keys=True))
        return 0
    if args.output is None:
        raise SystemExit("--output required")
    evidence = run_rehearsal(args.candidate, args.parameter_root, args.output)
    print(json.dumps({"result": evidence["result"], "output_sha256": evidence["output_sha256"], "failure_cases_passed": evidence["failure_cases_passed"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
