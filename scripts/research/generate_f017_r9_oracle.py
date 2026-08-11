#!/usr/bin/env python3
"""Generate the independent checkpoint-free Feature 017 R9 MLA/DSA oracle.

The generator deliberately has no Rust, FFI, MLX, or checkpoint dependency.
It mirrors the frozen one-token GLM-5.2 MLA ordering with reduced dimensions:
RMSNorm, q/kv low-rank projections, nope/rope split, compact latent state,
range-fill DSA selection, attention, output projection, and residual add.
An independent synthetic indexer record covers stable top-k, masking, and state
update without claiming that the long-context real-checkpoint indexer has run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import struct
from importlib.metadata import version
from pathlib import Path
from typing import Iterable

import numpy as np


SCHEMA = "pulsarmlx.f017.r9-mla-dsa-oracle"
SCHEMA_VERSION = "1.0.0"
FIXTURE_VERSION = "f017-r9-mla-dsa-q8-0-v1"
GENERATOR_PATH = "scripts/research/generate_f017_r9_oracle.py"
SEED = 17019
WIDTH = 32
Q_NOPE = 32
Q_ROPE = 32
QK = Q_NOPE + Q_ROPE
KV_LORA = 32
VALUE = 32
RMS_EPS = np.float32(1.0e-5)
ATTENTION_SCALE = np.float32(1.0 / math.sqrt(QK))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _f32(value: float | np.float32) -> np.float32:
    return np.float32(value)


def _f32_bytes(values: Iterable[float]) -> bytes:
    return b"".join(struct.pack("<f", float(_f32(value))) for value in values)


def _f32_record(values: Iterable[float]) -> dict[str, object]:
    materialized = [_f32(value) for value in values]
    payload = _f32_bytes(materialized)
    return {
        "values": [float(value) for value in materialized],
        "f32_le_hex": payload.hex(),
        "sha256": _sha256(payload),
    }


def _u64_bytes(values: Iterable[int]) -> bytes:
    return b"".join(struct.pack("<Q", int(value)) for value in values)


def _q8_matrix(name: str, rows: int, salt: int) -> tuple[dict[str, object], list[np.float32]]:
    packed = bytearray()
    decoded: list[np.float32] = []
    for row in range(rows):
        scale = _f32((1 + (row + salt) % 4) / 64.0)
        packed.extend(struct.pack("<e", float(scale)))
        for column in range(WIDTH):
            quant = ((row * 7 + column * 11 + salt * 5) % 17) - 8
            packed.extend(struct.pack("b", quant))
            decoded.append(_f32(scale * _f32(quant)))
    payload = bytes(packed)
    return (
        {
            "name": name,
            "role": name,
            "quantization": "Q8_0",
            "shape": [rows, WIDTH],
            "packed_hex": payload.hex(),
            "packed_sha256": _sha256(payload),
            "decoded_f32_sha256": _sha256(_f32_bytes(decoded)),
        },
        decoded,
    )


def _matvec(matrix: list[np.float32], rows: int, vector: list[np.float32]) -> list[np.float32]:
    output: list[np.float32] = []
    for row in range(rows):
        total = _f32(0.0)
        for column in range(WIDTH):
            product = _f32(matrix[row * WIDTH + column] * vector[column])
            total = _f32(total + product)
        output.append(total)
    return output


def _rms_norm(values: list[np.float32], scale: list[np.float32]) -> list[np.float32]:
    total = _f32(0.0)
    for value in values:
        total = _f32(total + _f32(value * value))
    mean = _f32(total / _f32(len(values)))
    inverse = _f32(_f32(1.0) / np.sqrt(_f32(mean + RMS_EPS), dtype=np.float32))
    return [_f32(_f32(value * inverse) * weight) for value, weight in zip(values, scale, strict=True)]


def _rope_constants(position: int) -> tuple[list[np.float32], list[np.float32]]:
    cosine: list[np.float32] = []
    sine: list[np.float32] = []
    for pair in range(Q_ROPE // 2):
        index = pair * 2
        theta = float(position) * (1_000_000.0 ** (-float(index) / float(Q_ROPE)))
        cosine.append(_f32(math.cos(theta)))
        sine.append(_f32(math.sin(theta)))
    return cosine, sine


def _rotate(values: list[np.float32], cosine: list[np.float32], sine: list[np.float32]) -> list[np.float32]:
    output = list(values)
    for pair in range(Q_ROPE // 2):
        left = values[2 * pair]
        right = values[2 * pair + 1]
        output[2 * pair] = _f32(_f32(left * cosine[pair]) - _f32(right * sine[pair]))
        output[2 * pair + 1] = _f32(_f32(left * sine[pair]) + _f32(right * cosine[pair]))
    return output


def _dot(left: list[np.float32], right: list[np.float32]) -> np.float32:
    total = _f32(0.0)
    for left_value, right_value in zip(left, right, strict=True):
        total = _f32(total + _f32(left_value * right_value))
    return total


def _softmax(values: list[np.float32]) -> list[np.float32]:
    maximum = max(values)
    exponentials = [np.exp(_f32(value - maximum), dtype=np.float32) for value in values]
    denominator = _f32(0.0)
    for value in exponentials:
        denominator = _f32(denominator + value)
    return [_f32(value / denominator) for value in exponentials]


def _stable_dsa_select(scores: list[np.float32], visible: list[bool], top_k: int) -> list[int]:
    eligible = [index for index, is_visible in enumerate(visible) if is_visible]
    eligible.sort(key=lambda index: (-float(scores[index]), index))
    return eligible[:top_k]


def build_oracle(source_commit: str, generator_sha256: str) -> dict[str, object]:
    matrices: dict[str, dict[str, object]] = {}
    decoded: dict[str, list[np.float32]] = {}
    for name, rows, salt in (
        ("attn_q_a", WIDTH, 1),
        ("attn_q_b", QK, 2),
        ("attn_kv_a_mqa", KV_LORA + Q_ROPE, 3),
        ("attn_k_b", KV_LORA, 4),
        ("attn_v_b", VALUE, 5),
        ("attn_output", WIDTH, 6),
    ):
        record, values = _q8_matrix(name, rows, salt)
        matrices[name] = record
        decoded[name] = values

    residual = [_f32((((index * 13) % 23) - 11) / 8.0) for index in range(WIDTH)]
    attn_norm = [_f32(0.75 + (index % 7) / 16.0) for index in range(WIDTH)]
    q_norm_scale = [_f32(0.875 + (index % 5) / 32.0) for index in range(WIDTH)]
    kv_norm_scale = [_f32(0.8125 + (index % 3) / 16.0) for index in range(KV_LORA)]
    x_norm = _rms_norm(residual, attn_norm)
    q_rank = _matvec(decoded["attn_q_a"], WIDTH, x_norm)
    q_rank_norm = _rms_norm(q_rank, q_norm_scale)
    q_flat = _matvec(decoded["attn_q_b"], QK, q_rank_norm)
    q_nope = q_flat[:Q_NOPE]
    q_rope_raw = q_flat[Q_NOPE:]
    q_cosine, q_sine = _rope_constants(2)
    q_rope = _rotate(q_rope_raw, q_cosine, q_sine)

    kv_raw = _matvec(decoded["attn_kv_a_mqa"], KV_LORA + Q_ROPE, x_norm)
    kv_norm = _rms_norm(kv_raw[:KV_LORA], kv_norm_scale)
    current_k_rope = kv_raw[KV_LORA:]
    prior_latents = [
        [_f32((((row + 2) * (column + 3)) % 19 - 9) / 16.0) for column in range(KV_LORA)]
        for row in range(2)
    ]
    prior_ropes = [
        [_f32((((row + 5) * (column + 1)) % 17 - 8) / 32.0) for column in range(Q_ROPE)]
        for row in range(2)
    ]
    cache_latents = prior_latents + [kv_norm]
    cache_ropes = prior_ropes + [current_k_rope]
    selected = [0, 1, 2]
    qk_low = _matvec(decoded["attn_k_b"], KV_LORA, q_nope)
    scores: list[np.float32] = []
    rotated_keys: list[list[np.float32]] = []
    for position in selected:
        key_cosine, key_sine = _rope_constants(position)
        rotated = _rotate(cache_ropes[position], key_cosine, key_sine)
        rotated_keys.append(rotated)
        latent_score = _dot(qk_low, cache_latents[position])
        rope_score = _dot(q_rope, rotated)
        scores.append(_f32(_f32(latent_score + rope_score) * ATTENTION_SCALE))
    probabilities = _softmax(scores)
    latent_sum = [_f32(0.0) for _ in range(KV_LORA)]
    for weight, position in zip(probabilities, selected, strict=True):
        for column in range(KV_LORA):
            latent_sum[column] = _f32(
                latent_sum[column] + _f32(weight * cache_latents[position][column])
            )
    value = _matvec(decoded["attn_v_b"], VALUE, latent_sum)
    projected = _matvec(decoded["attn_output"], WIDTH, value)
    output = [_f32(left + right) for left, right in zip(residual, projected, strict=True)]

    dsa_scores = [_f32(value) for value in (0.5, 1.0, 1.0, -2.0, 3.0, 3.0, 0.25, 4.0, 4.0, -1.0, 2.0, 4.0)]
    dsa_visible = [True, True, True, True, True, False, True, True, True, False, True, True]
    dsa_selected = _stable_dsa_select(dsa_scores, dsa_visible, 4)

    expected_values = {
        "x_norm": x_norm,
        "q_rank": q_rank,
        "q_rank_norm": q_rank_norm,
        "q_flat": q_flat,
        "q_nope": q_nope,
        "q_rope": q_rope,
        "kv_raw": kv_raw,
        "kv_norm": kv_norm,
        "current_k_rope": current_k_rope,
        "qk_low": qk_low,
        "rotated_keys": [value for row in rotated_keys for value in row],
        "attention_scores": scores,
        "attention_probabilities": probabilities,
        "latent_sum": latent_sum,
        "value": value,
        "projected": projected,
        "output": output,
    }
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "fixture_version": FIXTURE_VERSION,
        "source_commit": source_commit,
        "generator_path": GENERATOR_PATH,
        "generator_sha256": generator_sha256,
        "deterministic_seed": SEED,
        "environment": {
            "python": platform.python_version(),
            "numpy": version("numpy"),
        },
        "independence": {
            "classification": "INDEPENDENT",
            "uses_rust_candidate": False,
            "uses_rust_reference_functions": False,
            "uses_mlx": False,
            "uses_checkpoint": False,
        },
        "architecture": {
            "family": "glm-dsa",
            "boundary": "one-token reduced-dimension MLA",
            "hidden_width": WIDTH,
            "head_count": 1,
            "q_lora_rank": WIDTH,
            "qk_nope": Q_NOPE,
            "qk_rope": Q_ROPE,
            "kv_lora_rank": KV_LORA,
            "value_width": VALUE,
            "query_position": 2,
            "visible_positions": 3,
            "real_indexer_top_k": 2048,
            "dsa_mode": "range_fill",
            "full_indexer_active_for_p1": False,
            "full_indexer_reason": "visible positions for P1 are below indexer top-k",
        },
        "matrices": matrices,
        "inputs": {
            "residual": _f32_record(residual),
            "attn_norm_scale": _f32_record(attn_norm),
            "q_norm_scale": _f32_record(q_norm_scale),
            "kv_norm_scale": _f32_record(kv_norm_scale),
            "prior_cache_latents": _f32_record(value for row in prior_latents for value in row),
            "prior_cache_ropes": _f32_record(value for row in prior_ropes for value in row),
            "q_rope_cosine": _f32_record(q_cosine),
            "q_rope_sine": _f32_record(q_sine),
            "rms_epsilon": float(RMS_EPS),
            "attention_scale": float(ATTENTION_SCALE),
        },
        "expected": {name: _f32_record(values) for name, values in expected_values.items()},
        "selection": {
            "mode": "range_fill",
            "selected_positions": selected,
            "selected_positions_sha256": _sha256(_u64_bytes(selected)),
        },
        "dsa_indexer_fixture": {
            "scores": _f32_record(dsa_scores),
            "visible_mask": dsa_visible,
            "top_k": 4,
            "tie_break": "lower_position",
            "selected_positions": dsa_selected,
            "selected_positions_sha256": _sha256(_u64_bytes(dsa_selected)),
            "state_before": {"visible": 11, "last_position": 10},
            "appended_position": 11,
            "state_after": {"visible": 12, "last_position": 11},
        },
        "numerical_contract": {
            "exact_scaffold": "exact_f32_bits_at_every_recorded_boundary",
            "production": "pending_frozen_r9_tier_b_contract",
            "signed_zero": "exact",
            "deterministic_repeats": 10,
        },
        "promotion_status": "fixture_frozen_before_candidate_execution",
        "review_status": "pending_adversarial_numerical_review",
        "checkpoint_accessed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    generator_sha256 = _sha256(Path(__file__).read_bytes())
    oracle = build_oracle(args.source_commit, generator_sha256)
    args.out.write_text(json.dumps(oracle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
