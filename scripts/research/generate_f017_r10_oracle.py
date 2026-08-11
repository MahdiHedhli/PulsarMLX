#!/usr/bin/env python3
"""Generate the independent checkpoint-free Feature 017 R10 layer oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Iterable

import numpy as np


SCHEMA = "pulsarmlx.f017.r10-complete-layer-oracle"
SCHEMA_VERSION = "1.0.0"
FIXTURE_VERSION = "f017-r10-complete-layer-q8-0-v1"
GENERATOR_PATH = "scripts/research/generate_f017_r10_oracle.py"
WIDTH = 32
ROUTER_EXPERTS = 12
TOP_K = 8
RMS_EPS = np.float32(1.0e-5)
WEIGHT_SCALE = 2.5


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _f32(value: float | np.float32) -> np.float32:
    return np.float32(value)


def _f32_bytes(values: Iterable[float]) -> bytes:
    return b"".join(struct.pack("<f", float(_f32(value))) for value in values)


def _f64_bytes(values: Iterable[float]) -> bytes:
    return b"".join(struct.pack("<d", float(value)) for value in values)


def _record_f32(values: Iterable[float]) -> dict[str, object]:
    materialized = [_f32(value) for value in values]
    payload = _f32_bytes(materialized)
    return {"values": [float(value) for value in materialized], "f32_le_hex": payload.hex(), "sha256": _sha256(payload)}


def _record_f64(values: Iterable[float]) -> dict[str, object]:
    materialized = [float(value) for value in values]
    payload = _f64_bytes(materialized)
    return {"values": materialized, "f64_le_hex": payload.hex(), "sha256": _sha256(payload)}


def _q8_matrix(name: str, rows: int, salt: int) -> tuple[dict[str, object], list[np.float32]]:
    packed = bytearray()
    decoded: list[np.float32] = []
    for row in range(rows):
        scale = _f32((1 + (row + salt) % 4) / 128.0)
        packed.extend(struct.pack("<e", float(scale)))
        for column in range(WIDTH):
            quant = ((row * 11 + column * 7 + salt * 3) % 17) - 8
            packed.extend(struct.pack("b", quant))
            decoded.append(_f32(scale * _f32(quant)))
    payload = bytes(packed)
    return ({
        "name": name,
        "quantization": "Q8_0",
        "shape": [rows, WIDTH],
        "packed_hex": payload.hex(),
        "packed_sha256": _sha256(payload),
        "decoded_f32_sha256": _sha256(_f32_bytes(decoded)),
    }, decoded)


def _matvec(matrix: list[np.float32], rows: int, vector: list[np.float32]) -> list[np.float32]:
    output: list[np.float32] = []
    for row in range(rows):
        total = _f32(0.0)
        for column in range(WIDTH):
            total = _f32(total + _f32(matrix[row * WIDTH + column] * vector[column]))
        output.append(total)
    return output


def _rms_norm(values: list[np.float32], scale: list[np.float32]) -> list[np.float32]:
    total = _f32(0.0)
    for value in values:
        total = _f32(total + _f32(value * value))
    mean = _f32(total / _f32(len(values)))
    inverse = _f32(_f32(1.0) / np.sqrt(_f32(mean + RMS_EPS), dtype=np.float32))
    return [_f32(_f32(value * inverse) * weight) for value, weight in zip(values, scale, strict=True)]


def _expert(matrices: list[list[np.float32]], activation: list[np.float32]) -> dict[str, list[np.float32]]:
    gate = _matvec(matrices[0], WIDTH, activation)
    up = _matvec(matrices[1], WIDTH, activation)
    hidden: list[np.float32] = []
    for gate_value, up_value in zip(gate, up, strict=True):
        denominator = _f32(_f32(1.0) + np.exp(_f32(-gate_value), dtype=np.float32))
        hidden.append(_f32(_f32(gate_value / denominator) * up_value))
    down = _matvec(matrices[2], WIDTH, hidden)
    return {"gate": gate, "up": up, "hidden": hidden, "down": down}


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        factor = math.exp(-value)
        return 1.0 / (1.0 + factor)
    factor = math.exp(value)
    return factor / (1.0 + factor)


def build_oracle(source_commit: str, generator_sha256: str, r9_path: Path) -> dict[str, object]:
    r9_bytes = r9_path.read_bytes()
    r9 = json.loads(r9_bytes)
    attention_residual = [
        _f32(value)
        for value in struct.iter_unpack("<f", bytes.fromhex(r9["expected"]["output"]["f32_le_hex"]))
        for value in value
    ]
    norm_scale = [_f32(0.8125 + (index % 7) / 32.0) for index in range(WIDTH)]
    normalized = _rms_norm(attention_residual, norm_scale)
    router_record, router_matrix = _q8_matrix("ffn_gate_inp", ROUTER_EXPERTS, 31)
    router_logits = _matvec(router_matrix, ROUTER_EXPERTS, normalized)
    router_bias = [((index * 5) % 11 - 5) / 32.0 for index in range(ROUTER_EXPERTS)]
    probabilities = [_sigmoid(float(value)) for value in router_logits]
    scores = [probabilities[index] + router_bias[index] for index in range(ROUTER_EXPERTS)]
    selected_ids = sorted(range(ROUTER_EXPERTS), key=lambda index: (-scores[index], index))[:TOP_K]
    denominator = math.fsum(probabilities[index] for index in selected_ids)
    weights = [probabilities[index] / max(denominator, 6.103515625e-5) * WEIGHT_SCALE for index in selected_ids]

    expert_inputs: list[dict[str, object]] = []
    expert_expected: list[dict[str, object]] = []
    expert_outputs: list[list[np.float32]] = []
    for route, expert_id in enumerate(selected_ids):
        records = []
        decoded = []
        for role, salt in (("gate", 101), ("up", 151), ("down", 211)):
            record, matrix = _q8_matrix(f"routed.{expert_id}.{role}", WIDTH, salt + expert_id * 7)
            records.append(record)
            decoded.append(matrix)
        result = _expert(decoded, normalized)
        expert_inputs.append({"expert_id": expert_id, "route": route, "matrices": records})
        expert_expected.append({name: _record_f32(values) for name, values in result.items()})
        expert_outputs.append(result["down"])

    shared_records = []
    shared_decoded = []
    for role, salt in (("gate", 307), ("up", 359), ("down", 401)):
        record, matrix = _q8_matrix(f"shared.{role}", WIDTH, salt)
        shared_records.append(record)
        shared_decoded.append(matrix)
    shared_expected_values = _expert(shared_decoded, normalized)
    shared_output = shared_expected_values["down"]
    routed_aggregate = [
        math.fsum(weights[route] * float(expert_outputs[route][column]) for route in range(TOP_K))
        for column in range(WIDTH)
    ]
    combined = [routed_aggregate[column] + float(shared_output[column]) for column in range(WIDTH)]
    output = [_f32(float(attention_residual[column]) + combined[column]) for column in range(WIDTH)]
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "fixture_version": FIXTURE_VERSION,
        "source_commit": source_commit,
        "generator_path": GENERATOR_PATH,
        "generator_sha256": generator_sha256,
        "r9_fixture_sha256": _sha256(r9_bytes),
        "independence": {
            "classification": "INDEPENDENT",
            "uses_rust_candidate": False,
            "uses_rust_reference_functions": False,
            "uses_mlx": False,
            "uses_checkpoint": False,
        },
        "architecture": {
            "family": "glm-dsa",
            "layer_kind": "moe_top8_plus_shared",
            "composition": ["R9 attention residual", "post-attention RMSNorm", "sigmoid+bias top-8 router", "8 routed experts", "1 shared expert", "residual add"],
            "hidden_width": WIDTH,
            "router_expert_count": ROUTER_EXPERTS,
            "selected_expert_count": TOP_K,
            "shared_expert_count": 1,
            "expert_weight_scale": WEIGHT_SCALE,
        },
        "inputs": {
            "attention_residual": _record_f32(attention_residual),
            "post_attention_norm_scale": _record_f32(norm_scale),
            "router": router_record,
            "router_bias": _record_f64(router_bias),
            "routed_experts": expert_inputs,
            "shared_expert": {"matrices": shared_records},
            "rms_epsilon": float(RMS_EPS),
        },
        "expected": {
            "normalized": _record_f32(normalized),
            "router_logits": _record_f32(router_logits),
            "router_probabilities": _record_f64(probabilities),
            "router_scores": _record_f64(scores),
            "selected_ids": selected_ids,
            "selected_ids_sha256": _sha256(b"".join(struct.pack("<Q", value) for value in selected_ids)),
            "routing_weights": _record_f64(weights),
            "routed_experts": expert_expected,
            "shared_expert": {name: _record_f32(values) for name, values in shared_expected_values.items()},
            "routed_aggregate": _record_f64(routed_aggregate),
            "combined_moe": _record_f64(combined),
            "output": _record_f32(output),
        },
        "numerical_contract": {
            "exact_scaffold": "exact f32 projections/activation/output and exact f64 router/aggregation",
            "production": "pending_frozen_r10_tier_b_contract",
            "routing_ids": "exact",
            "deterministic_repeats": 10,
        },
        "promotion_status": "fixture_frozen_before_candidate_execution",
        "review_status": "pending_adversarial_numerical_review",
        "checkpoint_accessed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--r9-fixture", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    generator_sha = _sha256(Path(__file__).read_bytes())
    args.out.write_text(json.dumps(build_oracle(args.source_commit, generator_sha, args.r9_fixture), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
