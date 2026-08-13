#!/usr/bin/env python3
"""Independent bounded M1-E oracle preparer.

This module intentionally imports only the independent NumPy decoders. It
does not import Rust, MLX, FFI, ctypes/cffi, or candidate output. The real
entrypoint is used only by a separately authorized attempt; checkpoint-free
tests exercise the same functions with synthetic packed matrices.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import time
from pathlib import Path

import numpy as np

from iq2_xxs_dequant import dequantize_matrix_iq2_xxs_numpy
from iq3_xxs_dequant import dequantize_matrix_iq3_xxs_numpy

U = 2.0 ** -24
ETA = 2.0 ** -149
SILU_DERIVATIVE_BOUND = 1.1


def f32_bytes(values: np.ndarray) -> bytes:
    return np.asarray(values, dtype="<f4").tobytes(order="C")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strict_matvec(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    rows, columns = matrix.shape
    if vector.shape != (columns,):
        raise ValueError("matvec shape mismatch")
    total = np.zeros(rows, dtype=np.float32)
    for column in range(columns):
        product = np.multiply(matrix[:, column], vector[column], dtype=np.float32)
        total = np.add(total, product, dtype=np.float32)
    return total


def strict_swiglu(gate: np.ndarray, up: np.ndarray) -> np.ndarray:
    negative = np.negative(gate, dtype=np.float32)
    exponential = np.exp(negative, dtype=np.float32)
    denominator = np.add(np.float32(1.0), exponential, dtype=np.float32)
    silu = np.divide(gate, denominator, dtype=np.float32)
    return np.multiply(silu, up, dtype=np.float32)


def gamma(operations: int) -> float:
    return (operations * U) / (1.0 - operations * U)


def matvec_bounds(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    n = matrix.shape[1]
    l1 = np.sum(np.abs(matrix.astype(np.float64) * vector.astype(np.float64)), axis=1)
    return 2.0 * gamma(2 * n) * l1 + 4.0 * n * ETA


def composed_bounds(
    gate_matrix: np.ndarray,
    up_matrix: np.ndarray,
    down_matrix: np.ndarray,
    activation: np.ndarray,
    gate: np.ndarray,
    up: np.ndarray,
    hidden: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    gate_bound = matvec_bounds(gate_matrix, activation)
    up_bound = matvec_bounds(up_matrix, activation)
    silu = hidden.astype(np.float64) / np.where(up != 0.0, up.astype(np.float64), 1.0)
    preceding = (
        np.abs(up.astype(np.float64)) * SILU_DERIVATIVE_BOUND * gate_bound
        + np.abs(silu) * up_bound
        + SILU_DERIVATIVE_BOUND * gate_bound * up_bound
    )
    hidden_bound = preceding + 4.0 * U * (np.abs(hidden.astype(np.float64)) + preceding) + 4.0 * ETA
    down_reduction = matvec_bounds(down_matrix, hidden)
    propagation_l1 = np.sum(np.abs(down_matrix.astype(np.float64)) * hidden_bound, axis=1)
    final_bound = down_reduction + propagation_l1 * (1.0 + gamma(2 * hidden.size)) + 4.0 * hidden.size * ETA
    return gate_bound, up_bound, hidden_bound, final_bound


def prepare(gate_packed: bytes, up_packed: bytes, down_packed: bytes, activation: np.ndarray) -> dict[str, object]:
    started = time.time_ns()
    gate_decode_started = time.perf_counter_ns()
    gate_matrix = dequantize_matrix_iq2_xxs_numpy(gate_packed, 2048, 6144)
    gate_decode_seconds = (time.perf_counter_ns() - gate_decode_started) / 1e9
    up_decode_started = time.perf_counter_ns()
    up_matrix = dequantize_matrix_iq2_xxs_numpy(up_packed, 2048, 6144)
    up_decode_seconds = (time.perf_counter_ns() - up_decode_started) / 1e9
    down_decode_started = time.perf_counter_ns()
    down_matrix = dequantize_matrix_iq3_xxs_numpy(down_packed, 6144, 2048)
    down_decode_seconds = (time.perf_counter_ns() - down_decode_started) / 1e9
    gate_started = time.perf_counter_ns()
    gate = strict_matvec(gate_matrix, activation)
    gate_seconds = (time.perf_counter_ns() - gate_started) / 1e9
    up_started = time.perf_counter_ns()
    up = strict_matvec(up_matrix, activation)
    up_seconds = (time.perf_counter_ns() - up_started) / 1e9
    activation_started = time.perf_counter_ns()
    hidden = strict_swiglu(gate, up)
    activation_seconds = (time.perf_counter_ns() - activation_started) / 1e9
    down_started = time.perf_counter_ns()
    output = strict_matvec(down_matrix, hidden)
    down_seconds = (time.perf_counter_ns() - down_started) / 1e9
    bounds = composed_bounds(gate_matrix, up_matrix, down_matrix, activation, gate, up, hidden)
    completed = time.time_ns()
    stages = {"gate": gate, "up": up, "activated_hidden": hidden, "final_output": output}
    return {
        "schema": "pulsarmlx.f017.m1e-oracle-package",
        "schema_version": "1.0.0",
        "generator": {"implementation": "independent_python_numpy", "source_sha256": "TO_BE_BOUND_BY_EXECUTION_CONFIG"},
        "matrices": {
            "gate": {"packed_sha256": sha(gate_packed), "decoded_sha256": sha(f32_bytes(gate_matrix))},
            "up": {"packed_sha256": sha(up_packed), "decoded_sha256": sha(f32_bytes(up_matrix))},
            "down": {"packed_sha256": sha(down_packed), "decoded_sha256": sha(f32_bytes(down_matrix))},
        },
        "activation": {"sha256": sha(f32_bytes(activation)), "bytes_hex": f32_bytes(activation).hex(), "element_count": 6144},
        "stages": {name: {"sha256": sha(f32_bytes(value)), "bytes_hex": f32_bytes(value).hex()} for name, value in stages.items()},
        "bounds": {
            name: {"sha256": sha(np.asarray(value, dtype="<f8").tobytes()), "f64_hex": np.asarray(value, dtype="<f8").tobytes().hex()}
            for name, value in zip(("gate", "up", "activated_hidden", "final_output"), bounds)
        },
        "derived_global": {
            "max_absolute_bound": float(np.max(bounds[-1])),
            "rmse_bound": float(np.sqrt(np.mean(np.square(bounds[-1])))),
            "cosine_minimum": float(max(0.0, (np.linalg.norm(output.astype(np.float64)) - np.linalg.norm(bounds[-1])) / (np.linalg.norm(output.astype(np.float64)) + np.linalg.norm(bounds[-1])))) if np.linalg.norm(output.astype(np.float64)) > np.linalg.norm(bounds[-1]) else None,
        },
        "timings": {
            "decoder_gate_seconds": gate_decode_seconds,
            "decoder_up_seconds": up_decode_seconds,
            "decoder_down_seconds": down_decode_seconds,
            "oracle_gate_seconds": gate_seconds,
            "oracle_up_seconds": up_seconds,
            "oracle_activation_seconds": activation_seconds,
            "oracle_down_seconds": down_seconds,
        },
        "finalization": {
            "preparation_started_at": str(started),
            "oracle_completed_at": str(completed),
            "completion_marker": "m1e_oracle_finalized_sequence_0",
            "immutable_after_finalization": True,
        },
    }


def exclusive_finalize(path: Path, document: dict[str, object]) -> str:
    raw = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    try:
        os.write(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    path.chmod(stat.S_IRUSR)
    return sha(raw)


def exclusive_bytes(path: Path, payload: bytes) -> str:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    path.chmod(stat.S_IRUSR)
    return sha(payload)


def no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_exact_at(descriptor: int, offset: int, length: int) -> bytes:
    chunks: list[bytes] = []
    observed = 0
    while observed < length:
        chunk = os.pread(descriptor, length - observed, offset + observed)
        if not chunk:
            raise ValueError("short bounded checkpoint read")
        chunks.append(chunk)
        observed += len(chunk)
    return b"".join(chunks)


def prepare_from_config(config_path: Path, expected_sha256: str) -> str:
    raw = config_path.read_bytes()
    if sha(raw) != expected_sha256:
        raise ValueError("immutable M1-E execution config hash mismatch")
    config = json.loads(raw, object_pairs_hook=no_duplicates)
    if config.get("schema") != "pulsarmlx.f017.m1e-execution-config" or config.get("attempt") != 1:
        raise ValueError("M1-E execution config identity mismatch")
    root = Path(config["repository_root"]["path"]).resolve(strict=True)
    package_root = Path(config["package_root"]["path"]).resolve(strict=True)
    local = config["local_artifacts"]
    shard = Path(local["target_shard"]["path"])
    if shard.is_symlink() or not shard.is_file():
        raise ValueError("bound target shard is not a regular non-symlink file")
    source_binding = config["repository_artifacts"]["real_reference_preparer"]
    source_path = root / source_binding["symbolic_path"]
    if source_path.resolve(strict=True) != Path(__file__).resolve(strict=True) or sha(source_path.read_bytes()) != source_binding["content_sha256"]:
        raise ValueError("real-reference preparer source binding mismatch")
    activation_binding = config["activation_fixture"]
    activation_path = root / activation_binding["symbolic_path"]
    if sha(activation_path.read_bytes()) != activation_binding["content_sha256"]:
        raise ValueError("activation artifact hash mismatch")
    activation_doc = json.loads(activation_path.read_text(), object_pairs_hook=no_duplicates)
    activation = np.frombuffer(bytes.fromhex(activation_doc["activation"]["bytes_hex"]), dtype="<f4").copy()
    if sha(f32_bytes(activation)) != config["activation_payload_sha256"]:
        raise ValueError("activation payload hash mismatch")

    packed: dict[str, bytes] = {}
    descriptor = os.open(shard, os.O_RDONLY)
    try:
        for tensor in config["tensors"]:
            role = tensor["role"]
            if role in packed or role not in {"gate", "up", "down"} or tensor["allowed_read_count"] != 1:
                raise ValueError("one-expert tensor access set mismatch")
            packed[role] = read_exact_at(descriptor, tensor["offset"], tensor["packed_length"])
    finally:
        os.close(descriptor)
    if set(packed) != {"gate", "up", "down"}:
        raise ValueError("exactly three expert payloads are required")
    payload_references: dict[str, dict[str, object]] = {}
    for role in ("gate", "up", "down"):
        name = f"m1e-{role}-packed-v1.bin"
        digest = exclusive_bytes(package_root / name, packed[role])
        payload_references[role] = {
            "path_kind": "package_relative",
            "symbolic_path": name,
            "content_sha256": digest,
            "logical_role": f"{role}_packed_payload",
            "package_artifact_id": f"m1e-attempt-1-{role}-packed-v1",
        }

    oracle = prepare(packed["gate"], packed["up"], packed["down"], activation)
    oracle["generator"]["source_sha256"] = source_binding["content_sha256"]
    oracle_path = Path(local["oracle_output"])
    oracle_sha = exclusive_finalize(oracle_path, oracle)
    tensor_documents = []
    for tensor in config["tensors"]:
        tensor_documents.append({
            "role": tensor["role"], "name": tensor["name"], "shard_ordinal": tensor["shard_ordinal"],
            "offset": tensor["offset"], "packed_length": tensor["packed_length"],
            "quantization": tensor["quantization"], "matrix_shape": tensor["logical_matrix_shape"],
            "packed_sha256": payload_references[tensor["role"]]["content_sha256"],
            "payload": payload_references[tensor["role"]],
        })
    package = {
        "schema": "pulsarmlx.f017.m1e-package", "schema_version": "1.0.0",
        "package_kind": "production_reviewed" if config["runner"]["mode"] == "real_expert" else "checkpoint_free_fixture",
        "checkpoint_set_sha256": config["checkpoint_bindings"]["checkpoint_set_sha256"],
        "catalog_sha256": config["checkpoint_bindings"]["catalog_sha256"],
        "tensor_map_sha256": config["checkpoint_bindings"]["tensor_map_sha256"],
        "source_checkpoint_read_count": 3, "tensors": tensor_documents,
        "oracle": {"path_kind":"package_relative","symbolic_path":oracle_path.name,"content_sha256":oracle_sha,"logical_role":"independent_oracle","package_artifact_id":"m1e-attempt-1-real-oracle-v1"},
        "one_attempt": True,
    }
    return exclusive_finalize(Path(local["package_output"]), package)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", type=Path)
    parser.add_argument("--up", type=Path)
    parser.add_argument("--down", type=Path)
    parser.add_argument("--activation", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execution-config", type=Path)
    parser.add_argument("--execution-config-sha256")
    args = parser.parse_args()
    if args.execution_config is not None or args.execution_config_sha256 is not None:
        if args.execution_config is None or args.execution_config_sha256 is None or any(
            value is not None for value in (args.gate, args.up, args.down, args.activation, args.output)
        ):
            parser.error("config-only preparation requires exactly config path and hash")
        print(prepare_from_config(args.execution_config, args.execution_config_sha256))
        return 0
    if any(value is None for value in (args.gate, args.up, args.down, args.activation, args.output)):
        parser.error("legacy fixture preparation requires gate/up/down/activation/output")
    activation_doc = json.loads(args.activation.read_text())
    activation = np.frombuffer(bytes.fromhex(activation_doc["activation"]["bytes_hex"]), dtype="<f4").copy()
    digest = exclusive_finalize(args.output, prepare(args.gate.read_bytes(), args.up.read_bytes(), args.down.read_bytes(), activation))
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
