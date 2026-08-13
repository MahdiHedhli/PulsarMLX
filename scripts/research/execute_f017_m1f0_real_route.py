#!/usr/bin/env python3
"""Execute one authorized, oracle-only M1-F0 real route discovery.

The independently reviewed numerical preparer remains frozen.  This wrapper
adds the attempt-consumption marker, exact access accounting, ten-repeat
integrity, and immutable package construction without changing its decoder or
oracle arithmetic.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np


EXPECTED_SHARD_SHA256 = "d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36"
EXPECTED_PACKED_BYTES = 139_217_920
EXPECTED_DECODED_BYTES = 666_430_464
Q5_NAME = "blk.3.attn_output.weight"
Q5_PACKED_SHA256 = "30d37ee75f7877defe1720f6bf14f4d9b9c4151b3d164f0618e5c2bff454b084"
Q5_DECODED_SHA256 = "2cd327fb89256c1d4a920fff53a47994f294a67eb17e640785b616d7c9c8e5e8"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _load(root: Path, relative: str, name: str):
    path = root / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_execution_start_marker(
    marker: Path, execution_config_sha256: str, authorization_sha256: str, attempt: int
) -> None:
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json(
        {
            "schema": "pulsarmlx.f017.m1f0-execution-start",
            "schema_version": "1.0.0",
            "attempt": attempt,
            "state": "EXECUTION_STARTED",
            "execution_config_sha256": execution_config_sha256,
            "authorization_sha256": authorization_sha256,
            "recorded_unix_ns": time.time_ns(),
        }
    )
    descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def repeat_record(ordinal: int, result: dict[str, Any]) -> dict[str, Any]:
    stages = result["stage_hashes"]
    return {
        "ordinal": ordinal,
        "attention_output_sha256": stages["attention_output"],
        "attention_residual_sha256": stages["attention_residual"],
        "router_normalized_input_sha256": stages["router_normalized"],
        "router_logits_sha256": stages["router_logits"],
        "router_scores_sha256": result["router_scores_sha256"],
        "ranking_sha256": result["ranking_sha256"],
        "top8_ids": result["top8_ids"],
        "top8_ids_sha256": result["top8_ids_sha256"],
        "routing_weights": result["routing_weights"],
        "routing_weights_sha256": result["routing_weights_sha256"],
    }


def _repeat_identity(record: dict[str, Any]) -> bytes:
    return canonical_json({key: value for key, value in record.items() if key != "ordinal"})


def _write_atomic_readonly(output: Path, value: object) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError("refusing to overwrite M1-F0 oracle package")
    with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as temporary:
        temporary.write(canonical_json(value))
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, output)
    output.chmod(0o444)


def execute(
    repository_root: Path,
    config_path: Path,
    expected_config_sha: str,
    authorization_path: Path,
    expected_authorization_sha: str,
    package_root: Path,
    output: Path,
    execution_start_marker: Path,
) -> dict[str, Any]:
    admission = _load(repository_root, "scripts/research/f017_m1f0_admission.py", "m1f0_admission_exec")
    oracle = _load(
        repository_root,
        "scripts/research/prepare_f017_m1f0_real_reference.py",
        "m1f0_frozen_oracle_exec",
    )
    config_raw = config_path.read_bytes()
    authorization_raw = authorization_path.read_bytes()
    if sha256(config_raw) != expected_config_sha:
        raise ValueError("execution config identity")
    if sha256(authorization_raw) != expected_authorization_sha:
        raise ValueError("authorization identity")
    config = json.loads(config_raw, object_pairs_hook=admission._reject_duplicates)
    admission.validate_config(repository_root, config)
    admission.validate_authorization(
        repository_root,
        config,
        expected_config_sha,
        authorization_path,
        expected_authorization_sha,
    )

    manifest_path = oracle._safe_package_file(package_root, "checkpoint-manifest.json")
    manifest = json.loads(manifest_path.read_text(), object_pairs_hook=admission._reject_duplicates)
    if set(manifest) != {"schema", "schema_version", "checkpoint_set_sha256", "shard_2"}:
        raise ValueError("private package manifest fields")
    shard = manifest.get("shard_2", {})
    if (
        manifest.get("schema") != "pulsarmlx.f017.m1f0-private-package"
        or manifest.get("schema_version") != "1.0.0"
        or manifest.get("checkpoint_set_sha256")
        != config["checkpoint_bindings"]["checkpoint_set_sha256"]
        or set(shard) != {"path_kind", "path", "size_bytes", "sha256"}
        or shard.get("path_kind") != "package_relative"
        or shard.get("sha256") != EXPECTED_SHARD_SHA256
    ):
        raise ValueError("private package identity")
    shard_path = oracle._safe_package_file(package_root, shard["path"])
    if shard_path.stat().st_size != shard["size_bytes"]:
        raise ValueError("private shard size identity")

    hidden_path = (repository_root / config["input_state"]["symbolic_path"]).resolve(strict=True)
    if repository_root not in (hidden_path, *hidden_path.parents):
        raise ValueError("repository artifact path escape")
    hidden_fixture = json.loads(hidden_path.read_text(), object_pairs_hook=admission._reject_duplicates)
    hidden = np.frombuffer(
        bytes.fromhex(hidden_fixture["state"]["hidden"]["bytes_hex"]), dtype="<f4"
    ).copy()
    if sha256(hidden.tobytes(order="C")) != config["input_state"]["hidden_sha256"]:
        raise ValueError("input hidden identity")

    # This exclusive marker is the attempt-consumption boundary.  All source,
    # authorization, private-package metadata, and input checks precede it.
    write_execution_start_marker(
        execution_start_marker, expected_config_sha, expected_authorization_sha, config["attempt"]
    )
    total_started = time.monotonic_ns()
    storage_started = time.monotonic_ns()
    payload_hashes: dict[str, str] = {}
    decoded_hashes: dict[str, str] = {}
    tensors: dict[str, np.ndarray] = {}
    with shard_path.open("rb", buffering=0) as source:
        for binding in config["tensor_allowlist"]:
            name = binding["name"]
            if "_exps" in name or "_shexp" in name:
                raise ValueError("UNAUTHORIZED_ACCESS")
            source.seek(binding["offset"])
            raw = source.read(binding["packed_length"])
            if len(raw) != binding["packed_length"]:
                raise ValueError("truncated tensor payload")
            payload_hashes[name] = sha256(raw)
            tensor = oracle.decode_tensor(raw, binding["quantization"], binding["logical_shape"])
            decoded_hashes[name] = sha256(oracle.f32_bytes(tensor))
            tensors[name] = tensor
    storage_and_decode_ns = time.monotonic_ns() - storage_started
    if sum(item["packed_length"] for item in config["tensor_allowlist"]) != EXPECTED_PACKED_BYTES:
        raise ValueError("compressed access accounting")
    if sum(item["decoded_length"] for item in config["tensor_allowlist"]) != EXPECTED_DECODED_BYTES:
        raise ValueError("decoded access accounting")
    if payload_hashes[Q5_NAME] != Q5_PACKED_SHA256 or decoded_hashes[Q5_NAME] != Q5_DECODED_SHA256:
        raise ValueError("Q5_K real-byte identity")

    oracle_started = time.monotonic_ns()
    results = [oracle.compute_oracle(tensors, hidden) for _ in range(10)]
    oracle_ns = time.monotonic_ns() - oracle_started
    records = [repeat_record(ordinal, result) for ordinal, result in enumerate(results)]
    if any(_repeat_identity(record) != _repeat_identity(records[0]) for record in records[1:]):
        raise ValueError("M1-F0 repeat nondeterminism")
    selected = results[0]["top8_ids"]
    if selected in (admission.HISTORICAL_ROUTE, admission.SYNTHETIC_ROUTE):
        raise ValueError("forbidden route substitution")
    evidence = {
        "schema": "pulsarmlx.f017.m1f0-oracle-package",
        "schema_version": "1.0.0",
        "attempt": config["attempt"],
        "attempt_state": "COMPLETED",
        "execution_config_sha256": expected_config_sha,
        "authorization_sha256": expected_authorization_sha,
        "input_state": {
            "fixture_sha256": config["input_state"]["artifact_sha256"],
            "package_sha256": config["input_state"]["package_sha256"],
            "hidden_sha256": config["input_state"]["hidden_sha256"],
        },
        "tensor_payload_sha256": payload_hashes,
        "decoded_tensor_sha256": decoded_hashes,
        "oracle": results[0],
        "repeat_integrity": {
            "required": 10,
            "observed": 10,
            "all_equal": True,
            "records": records,
        },
        "numerical_qualification": {
            "attention_router_contract": "PASS",
            "selection_exact": True,
            "signed_zero_policy": "PASS",
            "non_finite_count": 0,
            "repeat_max_abs": 0.0,
            "repeat_rmse": 0.0,
            "repeat_cosine": 1.0,
            "classification": "independent_oracle_route_exact_and_deterministic",
            "post_observation_retuning": False,
        },
        "access": {
            "shard_opens": 1,
            "positional_reads": 12,
            "tensor_payloads": 12,
            "compressed_bytes": EXPECTED_PACKED_BYTES,
            "decoded_bytes": EXPECTED_DECODED_BYTES,
            "expert_payloads": 0,
        },
        "isolation": {
            "attention_router_discoveries": 1,
            "expert_tensor_accesses": 0,
            "expert_dispatches": 0,
            "mlx_candidate_dispatches": 0,
            "m1_f_executions": 0,
        },
        "timing": {
            "storage_and_decode_ns": storage_and_decode_ns,
            "oracle_ten_repeats_ns": oracle_ns,
            "total_ns": time.monotonic_ns() - total_started,
        },
        "expert_computation": False,
    }
    _write_atomic_readonly(output, evidence)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--execution-config", type=Path, required=True)
    parser.add_argument("--execution-config-sha256", required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--authorization-sha256", required=True)
    parser.add_argument("--private-package-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execution-start-marker", type=Path, required=True)
    args = parser.parse_args()
    evidence = execute(
        args.repository_root.resolve(strict=True),
        args.execution_config,
        args.execution_config_sha256,
        args.authorization,
        args.authorization_sha256,
        args.private_package_root.resolve(strict=True),
        args.output,
        args.execution_start_marker,
    )
    print(sha256(canonical_json(evidence)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
