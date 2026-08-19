#!/usr/bin/env python3
"""Materialize the representative post-attention expert input without checkpoint access.

The accepted route-value recovery producer already recomputes the complete
attention-to-router path from retained authority.  This adapter observes the
``router_normalized`` local produced by that exact function; it does not
replace or reimplement any numerical operation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

import numpy as np

import f017_representative_m1f0_recover_route_values_from_retention_v1 as recovery
import prepare_f017_m1f0_real_reference as oracle


EXPECTED_SHA256 = "687a692a452e30860c34055942061f4ff368ec0e1c815439c71e457a444fe62c"
EXPECTED_BYTES = 24_576


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_read_only(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.new")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(payload)
        while view:
            count = os.write(descriptor, view)
            if count <= 0:
                raise OSError("SHORT_WRITE")
            view = view[count:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(temporary, 0o400)
    os.replace(temporary, path)
    fsync_dir(path.parent)


def materialize(args: argparse.Namespace) -> dict[str, Any]:
    captured: dict[str, np.ndarray] = {}
    target_code = oracle.compose_oracle.__code__

    def local_tracer(frame: Any, event: str, arg: Any) -> Any:
        if event == "return":
            value = frame.f_locals.get("router_normalized")
            if not isinstance(value, np.ndarray):
                raise RuntimeError("ROUTER_NORMALIZED_NOT_OBSERVED")
            captured["router_normalized"] = np.array(value, dtype=np.float32, copy=True)
        return local_tracer

    def tracer(frame: Any, event: str, arg: Any) -> Any:
        if event == "call" and frame.f_code is target_code:
            return local_tracer
        return None

    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        route = recovery.recover(
            args.execution_evidence,
            args.candidate,
            args.retention_root,
            {
                "canonical_s0": args.canonical_s0,
                "ffn_norm": args.ffn_norm,
                "router_matrix": args.router_matrix,
                "correction_bias": args.correction_bias,
            },
        )
    finally:
        sys.settrace(previous)
    value = captured.get("router_normalized")
    if value is None:
        raise RuntimeError("ROUTER_NORMALIZED_CAPTURE_MISSING")
    payload = np.ascontiguousarray(value, dtype="<f4").tobytes()
    if value.shape != (6144,) or len(payload) != EXPECTED_BYTES or sha_bytes(payload) != EXPECTED_SHA256:
        raise RuntimeError("ROUTER_NORMALIZED_IDENTITY")
    if not np.isfinite(value).all():
        raise RuntimeError("ROUTER_NORMALIZED_NONFINITE")
    output = args.output_root / "router_normalized.f32le"
    manifest = args.output_root / "manifest.json"
    if output.exists() or manifest.exists():
        raise RuntimeError("OUTPUT_AUTHORITY_ALREADY_EXISTS")
    atomic_read_only(output, payload)
    output_stat = output.lstat()
    if not stat.S_ISREG(output_stat.st_mode) or stat.S_ISLNK(output_stat.st_mode):
        raise RuntimeError("OUTPUT_OBJECT_TYPE")
    if output_stat.st_nlink != 1 or output_stat.st_mode & 0o222:
        raise RuntimeError("OUTPUT_IMMUTABILITY")
    manifest_value = {
        "schema": "pulsarmlx.f017.representative-expert-input-private-manifest",
        "schema_version": "1.0.0",
        "artifact": {
            "symbolic_name": "representative-m1f0/router_normalized.f32le",
            "sha256": EXPECTED_SHA256,
            "dtype": "little-endian-f32",
            "shape": [6144],
            "byte_length": EXPECTED_BYTES,
            "semantic_role": "CANONICAL_REPRESENTATIVE_POST_ATTENTION_FFN_NORMALIZED_EXPERT_INPUT",
            "regular_file": True,
            "non_symlink": True,
            "read_only": True,
            "hard_link_count": 1,
        },
        "derivation": {
            "source": "ACCEPTED_RETAINED_ONLY_REPRESENTATIVE_M1F0_ORACLE",
            "route_recovery_producer_sha256": recovery.sha_file(Path(recovery.__file__).resolve()),
            "accepted_oracle_sha256": recovery.sha_file(Path(oracle.__file__).resolve()),
            "execution_evidence_sha256": route["execution_evidence_sha256"],
            "representative_route_sha256": route["representative_route_sha256"],
            "checkpoint_rereads": 0,
            "shard_opens": 0,
            "expert_executions": 0,
        },
    }
    atomic_read_only(manifest, canonical(manifest_value) + b"\n")
    return {
        "router_normalized_sha256": EXPECTED_SHA256,
        "private_manifest_sha256": sha_bytes(manifest.read_bytes()),
        "byte_length": EXPECTED_BYTES,
        "checkpoint_rereads": 0,
        "shard_opens": 0,
        "expert_executions": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-evidence", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--retention-root", type=Path, required=True)
    parser.add_argument("--canonical-s0", type=Path, required=True)
    parser.add_argument("--ffn-norm", type=Path, required=True)
    parser.add_argument("--router-matrix", type=Path, required=True)
    parser.add_argument("--correction-bias", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(canonical(materialize(args)).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
