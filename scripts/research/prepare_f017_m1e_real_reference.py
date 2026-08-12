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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--up", type=Path, required=True)
    parser.add_argument("--down", type=Path, required=True)
    parser.add_argument("--activation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    activation_doc = json.loads(args.activation.read_text())
    activation = np.frombuffer(bytes.fromhex(activation_doc["activation"]["bytes_hex"]), dtype="<f4").copy()
    digest = exclusive_finalize(args.output, prepare(args.gate.read_bytes(), args.up.read_bytes(), args.down.read_bytes(), activation))
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
