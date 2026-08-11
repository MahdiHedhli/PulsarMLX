#!/usr/bin/env python3
"""Generate the independent checkpoint-free Feature 017 R8 oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Iterable

import numpy as np


SCHEMA = "pulsarmlx.f017.r8-top8-shared-oracle"
CONTRACT_VERSION = "f017-production-expert-tier-b-v1"
GENERATOR_PATH = "scripts/research/generate_f017_r8_oracle.py"
WIDTH = 32
U = 2.0**-24
ETA = 2.0**-149
BOUND_FACTOR = 2.0 * ((64.0 * U) / (1.0 - 64.0 * U))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _f32_bytes(values: Iterable[float]) -> bytes:
    return b"".join(struct.pack("<f", float(np.float32(value))) for value in values)


def _f64_bytes(values: Iterable[float]) -> bytes:
    return b"".join(struct.pack("<d", float(value)) for value in values)


def _f32(value: float) -> np.float32:
    return np.float32(value)


def _decode_q8_matrix(encoded: bytes) -> list[np.float32]:
    if len(encoded) != WIDTH * 34:
        raise ValueError("R8 requires one complete 32x32 Q8_0 matrix")
    output: list[np.float32] = []
    for row in range(WIDTH):
        start = row * 34
        scale = _f32(struct.unpack("<e", encoded[start : start + 2])[0])
        for column in range(WIDTH):
            quant = struct.unpack("b", encoded[start + 2 + column : start + 3 + column])[0]
            output.append(_f32(scale * _f32(quant)))
    return output


def _matvec(matrix: list[np.float32], vector: list[np.float32]) -> list[np.float32]:
    output: list[np.float32] = []
    for row in range(WIDTH):
        total = _f32(0.0)
        for column in range(WIDTH):
            product = _f32(matrix[row * WIDTH + column] * vector[column])
            total = _f32(total + product)
        output.append(total)
    return output


def _expert(
    matrices: list[list[np.float32]], activation: list[np.float32]
) -> tuple[list[np.float32], list[float]]:
    gate = _matvec(matrices[0], activation)
    up = _matvec(matrices[1], activation)
    hidden: list[np.float32] = []
    for gate_value, up_value in zip(gate, up):
        denominator = _f32(_f32(1.0) + np.exp(_f32(-gate_value), dtype=np.float32))
        silu = _f32(gate_value / denominator)
        hidden.append(_f32(silu * up_value))
    output = _matvec(matrices[2], hidden)
    bounds = []
    for row in range(WIDTH):
        l1 = math.fsum(
            abs(float(matrices[2][row * WIDTH + column]) * float(hidden[column]))
            for column in range(WIDTH)
        )
        bounds.append(BOUND_FACTOR * l1 + 4.0 * WIDTH * ETA)
    return output, bounds


def _activation(base: list[float], expert_id: int) -> list[np.float32]:
    return [
        _f32(
            float(base[column]) * (1.0 + expert_id / 32.0)
            + (((column + expert_id) % 3) - 1) * 0.03125
        )
        for column in range(WIDTH)
    ]


def build_oracle(
    source_commit: str,
    generator_sha256: str,
    r7_fixture_path: Path,
) -> dict[str, object]:
    r7_bytes = r7_fixture_path.read_bytes()
    r7 = json.loads(r7_bytes)
    expert = r7["boundaries"]["complete_expert"]
    if expert["fixture_version"] != "glm52-runtime-expert-q8-0-v2":
        raise ValueError("unexpected R7 expert fixture")
    inputs = expert["inputs"]
    matrices = [
        _decode_q8_matrix(bytes.fromhex(inputs[f"{role}_packed_hex"]))
        for role in ("gate", "up", "down")
    ]
    activations = [_activation(inputs["activation"], expert_id) for expert_id in range(9)]
    outputs_and_bounds = [_expert(matrices, activation) for activation in activations]
    outputs = [item[0] for item in outputs_and_bounds]
    bounds = [item[1] for item in outputs_and_bounds]

    scores = [float(expert_id) for expert_id in range(8)]
    selected_ids = list(reversed(range(8)))
    maximum = max(scores)
    exponentials = [math.exp(scores[expert_id] - maximum) for expert_id in selected_ids]
    denominator = math.fsum(exponentials)
    weights = [value / denominator for value in exponentials]
    residual = [(-1.0 if column % 2 else 1.0) * (column + 1) / 64.0 for column in range(WIDTH)]
    aggregate = [
        math.fsum(
            weights[route] * float(outputs[expert_id][column])
            for route, expert_id in enumerate(selected_ids)
        )
        for column in range(WIDTH)
    ]
    shared = outputs[8]
    final = [aggregate[column] + float(shared[column]) + residual[column] for column in range(WIDTH)]
    aggregate_bounds = [
        math.fsum(
            weights[route] * bounds[expert_id][column]
            for route, expert_id in enumerate(selected_ids)
        )
        + bounds[8][column]
        for column in range(WIDTH)
    ]

    return {
        "schema": SCHEMA,
        "schema_version": "1.0.0",
        "fixture_version": "f017-r8-top8-shared-q8-0-v1",
        "source_commit": source_commit,
        "generator_path": GENERATOR_PATH,
        "generator_sha256": generator_sha256,
        "r7_oracle_fixture_sha256": _sha256(r7_bytes),
        "contract_version": CONTRACT_VERSION,
        "independence": {
            "classification": "INDEPENDENT",
            "uses_rust_candidate": False,
            "uses_rust_reference_functions": False,
            "uses_mlx": False,
            "uses_checkpoint": False,
        },
        "shape": [1, 8, WIDTH],
        "quantization": "Q8_0",
        "scores": scores,
        "scores_sha256": _f64_hash(scores),
        "selected_ids": selected_ids,
        "weights": weights,
        "weights_sha256": _f64_hash(weights),
        "activations": [[float(value) for value in activation] for activation in activations],
        "activation_sha256": [_sha256(_f32_bytes(value)) for value in activations],
        "expert_outputs": [[float(value) for value in output] for output in outputs[:8]],
        "expert_output_sha256": [_sha256(_f32_bytes(value)) for value in outputs[:8]],
        "shared_output": [float(value) for value in shared],
        "shared_output_sha256": _sha256(_f32_bytes(shared)),
        "per_expert_absolute_bounds": bounds,
        "residual": residual,
        "residual_sha256": _f64_hash(residual),
        "aggregate": aggregate,
        "aggregate_sha256": _f64_hash(aggregate),
        "aggregate_absolute_bounds": aggregate_bounds,
        "final_output": final,
        "final_output_sha256": _f64_hash(final),
        "behavioral_contract": {
            "router_ids": "exact",
            "router_weights_atol": 1.0e-12,
            "tie_break": "lowest_expert_id",
            "greedy_applicability": "router_top8",
        },
    }


def _f64_hash(values: Iterable[float]) -> str:
    return _sha256(_f64_bytes(values))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--r7-fixture", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    generator_sha256 = _sha256(Path(__file__).read_bytes())
    oracle = build_oracle(args.source_commit, generator_sha256, args.r7_fixture)
    args.out.write_text(json.dumps(oracle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
