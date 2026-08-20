#!/usr/bin/env python3
"""Generate checkpoint-free real-geometry FFN composition rehearsal evidence."""

from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EXECUTOR = ROOT / "scripts/research/f017_representative_ffn_composition_executor_v1.py"


def canonical(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_read_only(path: Path, raw: bytes) -> None:
    path.write_bytes(raw)
    os.chmod(path, 0o400)


def make_input(root: Path, name: str, raw: bytes, role: str, dtype: str, shape: list[int]) -> dict[str, Any]:
    artifact = root / name
    write_read_only(artifact, raw)
    entry = {
        "symbolic_path": name,
        "sha256": sha(raw),
        "semantic_role": role,
        "dtype": dtype,
        "shape": shape,
        "byte_length": len(raw),
    }
    manifest_document = {
        "schema": "pulsarmlx.f017.representative-ffn-composition-synthetic-private-manifest",
        "schema_version": "1.0.0",
        "artifacts": [entry],
    }
    manifest_raw = canonical(manifest_document)
    manifest_name = name + ".manifest.json"
    write_read_only(root / manifest_name, manifest_raw)
    return {
        "manifest": {
            "relative_path": manifest_name,
            "sha256": sha(manifest_raw),
            "byte_length": len(manifest_raw),
        },
        "artifact": dict(entry, relative_path=entry.pop("symbolic_path")),
    }


def exact_oracle(routed_raw: bytes, shared_raw: bytes) -> bytes:
    routed = struct.unpack("<6144d", routed_raw)
    shared = struct.unpack("<6144f", shared_raw)
    output = bytearray(49152)
    for index, (routed_value, shared_value) in enumerate(zip(routed, shared, strict=True)):
        exact_sum = Fraction.from_float(routed_value) + Fraction.from_float(float(shared_value))
        struct.pack_into("<d", output, index * 8, float(exact_sum))
    return bytes(output)


def generate(output: Path) -> dict[str, Any]:
    routed_values = [((index * 17) % 257 - 128) * (2.0 ** -19) for index in range(6144)]
    shared_values = [((index * 29) % 127 - 63) * (2.0 ** -13) for index in range(6144)]
    # Include directed rounding-sensitive coordinates without using real bytes.
    routed_values[:6] = [1.0, -1.0, 2.0 ** -1022, -(2.0 ** -1022), 2.0 ** 52, -(2.0 ** 52)]
    shared_values[:6] = [2.0 ** -24, -(2.0 ** -24), 2.0 ** -126, -(2.0 ** -126), 1.0, -1.0]
    routed_raw = struct.pack("<6144d", *routed_values)
    shared_raw = struct.pack("<6144f", *shared_values)
    oracle_raw = exact_oracle(routed_raw, shared_raw)
    environment = os.environ.copy()
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        environment[name] = "1"

    with tempfile.TemporaryDirectory(prefix="f017-ffn-composition-rehearsal-") as temporary_name:
        temporary = Path(temporary_name)
        routed_root = temporary / "routed"
        shared_root = temporary / "shared"
        routed_root.mkdir()
        shared_root.mkdir()
        routed = make_input(routed_root, "synthetic-routed.f64le", routed_raw, "SYNTHETIC_ROUTED", "little-endian-f64", [6144])
        shared = make_input(shared_root, "synthetic-shared.f32le", shared_raw, "SYNTHETIC_SHARED", "little-endian-f32", [6144])
        config = temporary / "config.json"
        config.write_bytes(canonical({
            "schema": "pulsarmlx.f017.representative-ffn-composition-synthetic-input",
            "schema_version": "1.0.0",
            "inputs": {"routed": routed, "shared": shared},
        }))
        packets: list[dict[str, Any]] = []
        output_shas: list[str] = []
        for run in range(2):
            target = temporary / f"output-{run}.f64le"
            completed = subprocess.run([
                sys.executable,
                str(EXECUTOR),
                "--synthetic-rehearsal",
                "--synthetic-config", str(config),
                "--routed-root", str(routed_root),
                "--shared-root", str(shared_root),
                "--output", str(target),
            ], check=True, capture_output=True, text=True, env=environment)
            packet = json.loads(completed.stdout)
            packets.append(packet)
            output_shas.append(hashlib.sha256(target.read_bytes()).hexdigest())
        oracle_sha = sha(oracle_raw)
        if output_shas != [oracle_sha, oracle_sha]:
            raise RuntimeError("INDEPENDENT_ORACLE_MISMATCH")

    document = {
        "schema": "pulsarmlx.f017.representative-ffn-composition-synthetic-rehearsal",
        "schema_version": "1.0.0",
        "result": "PASS",
        "producer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "executor_sha256": hashlib.sha256(EXECUTOR.read_bytes()).hexdigest(),
        "real_geometry": {"routed": "f64[6144]", "shared": "f32[6144]", "output": "f64[6144]"},
        "fresh_processes": 2,
        "exact_identity": True,
        "independent_exact_rational_oracle": True,
        "output_sha256": oracle_sha,
        "real_routed_bytes_used": False,
        "real_shared_bytes_used": False,
        "real_ffn_completions": 0,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "expert_executions": 0,
        "shared_expert_executions": 0,
        "s2_constructions": 0,
        "runtime_packets": packets,
        "required_failure_classes_covered_by_committed_tests": [
            "wrong_routed_sha",
            "wrong_shared_sha",
            "production_serial_f32_substitution",
            "wrong_promotion_or_casting",
            "wrong_addition_order",
            "nan_or_inf",
            "wrong_dtype_or_shape",
            "historical_shared_output",
            "historical_aggregate",
            "checkpoint_fallback",
            "retry_or_duplicate_execution",
            "s2_execution_attempt"
        ],
    }
    output.write_bytes(json.dumps(document, indent=2).encode() + b"\n")
    return document


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    result = generate(arguments.output)
    print(json.dumps({
        "result": result["result"],
        "fresh_processes": result["fresh_processes"],
        "output_sha256": result["output_sha256"],
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "real_ffn_completions": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
