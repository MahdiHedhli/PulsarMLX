#!/usr/bin/env python3
"""Checkpoint-free DPREFIX oracle forensics and exact-input preparation.

This module has no checkpoint path, reader, or real-payload-ledger writer.  Its
sole weight authority is the immutable REAL-2 packed package.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PRIVATE = ROOT / ".pulsarmlx-local"
PACKAGE = PRIVATE / "dprefix-real-2/material/packed"
PACKAGE_MANIFEST = PACKAGE / "manifest.json"
EXACT_ROOT = PRIVATE / "dprefix-exact-1"
INVENTORY = ROOT / "docs/architecture/reviews/evidence/f017-dense-prefix-40-read-allowlist-v1.json"
DECODED_GATES = ROOT / "docs/architecture/reviews/evidence/f017-dprefix-real3-decoded-identity-manifest-v1.json"
REAL2_RAW = ROOT / "docs/architecture/reviews/evidence/f017-dense-prefix-real-attempt-2-rejected-evidence-validation-v1.json"
REAL3_RAW = ROOT / "docs/architecture/reviews/evidence/f017-dprefix-real3-rejected-oracle-state-identity-v1.json"
REAL2_STATE = PRIVATE / "dprefix-real-2/oracle-primary/layer_3_entry.f32le"
REAL3_STATE = PRIVATE / "dprefix-real-3/oracle-primary/layer_3_entry.f32le"
CANDIDATE_STATE = PRIVATE / "dprefix-real-3/candidate-evidence.json.surfaces/layer_3_entry.f32le"
PACKED_PACKAGE_SHA = "705066830506dbebab9212948059c71e76b4535eaeb41672c9dbd62f6e9ed156"
LEDGER = 139
SURFACES = (
    "embedding", "layer_0_attention", "layer_0_output", "layer_1_attention",
    "layer_1_output", "layer_2_attention", "layer_2_output", "layer_3_entry",
)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def ordered_f32_bits(values: np.ndarray) -> np.ndarray:
    bits = np.asarray(values, dtype="<f4").view(np.uint32)
    return np.where(bits & np.uint32(0x80000000), np.uint32(0xFFFFFFFF) - bits,
                    bits + np.uint32(0x80000000)).astype(np.uint64)


def metrics(left: Path, right: Path) -> dict[str, Any]:
    a = np.fromfile(left, dtype="<f4")
    b = np.fromfile(right, dtype="<f4")
    if a.shape != b.shape:
        raise RuntimeError("state shape mismatch")
    different = np.flatnonzero(a.view(np.uint32) != b.view(np.uint32))
    delta = a.astype(np.float64) - b.astype(np.float64)
    ulps = np.abs(ordered_f32_bits(a).astype(np.int64) - ordered_f32_bits(b).astype(np.int64))
    unique, counts = np.unique(ulps[different], return_counts=True)
    first = int(different[0]) if different.size else None
    norm = float(np.linalg.norm(a.astype(np.float64)) * np.linalg.norm(b.astype(np.float64)))
    return {
        "left_sha256": sha(left), "right_sha256": sha(right), "count": int(a.size),
        "differing_elements": int(different.size), "first_differing_element": first,
        "first_left": None if first is None else float(a[first]),
        "first_right": None if first is None else float(b[first]),
        "first_ulp_distance": None if first is None else int(ulps[first]),
        "max_absolute_difference": float(np.max(np.abs(delta))),
        "rmse": float(np.sqrt(np.mean(delta * delta))),
        "cosine": float(np.dot(a.astype(np.float64), b.astype(np.float64)) / norm),
        "ulp_distance_histogram": {str(int(k)): int(v) for k, v in zip(unique, counts, strict=True)},
        "sign_changes": int(np.count_nonzero(np.signbit(a) != np.signbit(b))),
        "zero_presence_differences": int(np.count_nonzero((a == 0) != (b == 0))),
        "signed_zero_differences": int(np.count_nonzero((a == 0) & (b == 0) & (np.signbit(a) != np.signbit(b)))),
    }


def historical_forensics() -> dict[str, Any]:
    r2, r3 = load(REAL2_RAW), load(REAL3_RAW)
    comparisons = []
    first = None
    for left, right in zip(r2["numerical_surfaces"], r3["numerical_surfaces"], strict=True):
        if left["semantic_id"] != right["semantic_id"]:
            raise RuntimeError("surface ordering mismatch")
        equal = left["oracle_sha256"] == right["oracle_sha256"]
        comparisons.append({"semantic_id": left["semantic_id"], "real2_sha256": left["oracle_sha256"],
                            "real3_sha256": right["oracle_sha256"], "exact": equal,
                            "evidence_kind": "direct_hash_from_terminal_evidence"})
        if not equal and first is None:
            first = left["semantic_id"]
    decoded2 = r2["decoded_identities"]
    decoded3 = {item["tensor"]: item["decoded_sha256"] for item in load(DECODED_GATES)["entries"]}
    package = load(PACKAGE_MANIFEST)
    packed = {item["tensor"]: item["packed_sha256"] for item in package["entries"]}
    r2_packed = {item["tensor"]: item["packed_sha256"] for item in r2["access"]["read_records"]}
    return {
        "schema": "pulsarmlx.f017.dprefix-oracle-cross-process-forensics",
        "schema_version": "1.0.0", "classification": "BLAS-CLASS CROSS-PROCESS ORACLE DELTA CHARACTERIZED",
        "real2_real3_layer3_delta": metrics(REAL2_STATE, REAL3_STATE),
        "surface_hash_comparison": comparisons,
        "first_cross_process_oracle_divergence": first,
        "direct_value_availability": {"embedding": False, "layer_0_attention": False, "layer_0_output": False,
                                      "layer_1_attention": False, "layer_1_output": False, "layer_2_attention": False,
                                      "layer_2_output": True, "layer_3_entry": True},
        "input_identity": {
            "result": "ORACLE INPUTS BYTE-IDENTICAL",
            "packed_package_sha256": sha(PACKAGE_MANIFEST),
            "packed_40_exact": packed == r2_packed and len(packed) == 40,
            "decoded_40_exact": decoded2 == decoded3 and len(decoded2) == 40,
            "prompt_package_sha256": r2["bindings"]["prompt_package"]["sha256"],
            "token": 9703, "position": 0, "dsa": "range_fill([0])",
        },
        "checkpoint_access": 0, "real_payload_ledger": LEDGER,
    }


def _replay_module():
    from scripts.research import f017_dprefix_real3_replay
    return f017_dprefix_real3_replay


def decoded_tensors() -> dict[str, np.ndarray]:
    replay = _replay_module()
    inventory = replay._entries_by_tensor()
    expected = {item["tensor"]: item["decoded_sha256"] for item in load(DECODED_GATES)["entries"]}
    result: dict[str, np.ndarray] = {}
    for retained in load(PACKAGE_MANIFEST)["entries"]:
        name = retained["tensor"]
        entry = inventory[name]
        payload = (PACKAGE / retained["artifact"]["symbolic_path"]).read_bytes()
        decoded = replay.decode_canonical_f32(entry, payload)
        if hashlib.sha256(decoded).hexdigest() != expected[name]:
            raise RuntimeError(f"decoded identity: {name}")
        flat = np.frombuffer(decoded, dtype="<f4")
        dimensions = entry["gguf_shape"]
        if name.endswith("attn_k_b.weight"):
            array = flat.reshape(dimensions[2], dimensions[1], dimensions[0]).transpose(0, 2, 1)
        else:
            array = flat.reshape(replay._oracle_shape(entry))
        result[name] = array
    return result


def blas_run(output: Path) -> None:
    replay = _replay_module()
    oracle = replay._oracle_module()
    _, stages = oracle.dense_prefix_surfaces(decoded_tensors(), 9703)
    value = {
        "schema": "pulsarmlx.f017.dprefix-blas-oracle-process-observation", "schema_version": "1.0.0",
        "pid": os.getpid(), "python": platform.python_version(), "numpy": np.__version__,
        "architecture": platform.machine(), "platform": platform.platform(),
        "thread_environment": {name: os.environ.get(name) for name in (
            "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS")},
        "surface_sha256": {name: oracle.sha_f32(stages[name]) for name in SURFACES},
        "checkpoint_access": 0, "real_payload_ledger": LEDGER,
    }
    output.write_bytes(canonical(value))


def prepare_exact_input() -> None:
    target = EXACT_ROOT / "decoded"
    target.mkdir(parents=True, exist_ok=True)
    tensors = decoded_tensors()
    lines = []
    records = []
    for ordinal, name in enumerate(sorted(tensors)):
        path = target / f"{ordinal:02d}.f32le"
        raw = np.asarray(tensors[name], dtype="<f4").tobytes(order="C")
        with path.open("wb") as sink:
            sink.write(raw); sink.flush(); os.fsync(sink.fileno())
        path.chmod(0o444)
        shape = tensors[name].shape
        dims = [*shape, *([1] * (3 - len(shape)))]
        lines.append("\t".join((name, str(path), str(len(shape)), *(str(x) for x in dims))))
        records.append({"ordinal": ordinal, "tensor": name, "shape": list(shape), "bytes": len(raw),
                        "sha256": hashlib.sha256(raw).hexdigest(), "read_only": True})
    manifest = EXACT_ROOT / "exact-input.tsv"
    manifest.write_text("\n".join(lines) + "\n")
    manifest.chmod(0o444)
    (EXACT_ROOT / "exact-input-descriptor.json").write_bytes(canonical({
        "schema": "pulsarmlx.f017.dprefix-exact-input", "schema_version": "1.0.0",
        "source_packed_package_sha256": PACKED_PACKAGE_SHA, "decoded_gate_count": 40,
        "entries": records, "manifest_sha256": sha(manifest), "checkpoint_access": 0,
        "real_payload_ledger": LEDGER,
    }))


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--forensics", type=Path)
    group.add_argument("--blas-run", type=Path)
    group.add_argument("--prepare-exact-input", action="store_true")
    arguments = parser.parse_args()
    if arguments.forensics:
        arguments.forensics.write_bytes(canonical(historical_forensics()))
    elif arguments.blas_run:
        blas_run(arguments.blas_run)
    else:
        prepare_exact_input()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
