#!/usr/bin/env python3
"""Generate the independent checkpoint-free Feature 017 R11 oracle.

The bounded output head deliberately uses one full Q4_K block per vocabulary
row.  Q4_K is the real GLM-5.2 ``output.weight`` format, while the small
public-safe dimensions avoid committing checkpoint bytes or materializing the
real 154,880 by 6,144 head.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Iterable

import numpy as np


SCHEMA = "pulsarmlx.f017.r11-final-output-oracle"
SCHEMA_VERSION = "1.0.0"
FIXTURE_VERSION = "f017-r11-final-output-q4-k-v1"
GENERATOR_PATH = "scripts/research/generate_f017_r11_oracle.py"
WIDTH = 256
VOCAB = 16
TOP_K = 8
RMS_EPS = np.float32(1.0e-5)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _f32(value: float | np.float32) -> np.float32:
    return np.float32(value)


def _f32_bytes(values: Iterable[float]) -> bytes:
    return b"".join(struct.pack("<f", float(_f32(value))) for value in values)


def _record_f32(values: Iterable[float]) -> dict[str, object]:
    materialized = [_f32(value) for value in values]
    payload = _f32_bytes(materialized)
    return {
        "values": [float(value) for value in materialized],
        "f32_le_hex": payload.hex(),
        "sha256": _sha256(payload),
    }


def _scale_min(block: bytes, index: int) -> tuple[int, int]:
    scales = block[4:16]
    if index < 4:
        return scales[index] & 63, scales[index + 4] & 63
    return (
        (scales[index + 4] & 0x0F) | ((scales[index - 4] >> 6) << 4),
        (scales[index + 4] >> 4) | ((scales[index] >> 6) << 4),
    )


def _decode_q4_k_row(encoded: bytes) -> list[np.float32]:
    if len(encoded) != 144:
        raise ValueError("Q4_K row must contain one 144-byte block")
    scale = _f32(struct.unpack("<e", encoded[:2])[0])
    minimum = _f32(struct.unpack("<e", encoded[2:4])[0])
    quants = encoded[16:144]
    output: list[np.float32] = []
    for group in range(4):
        scale_low, minimum_low = _scale_min(encoded, 2 * group)
        scale_high, minimum_high = _scale_min(encoded, 2 * group + 1)
        for lane in range(32):
            byte = quants[32 * group + lane]
            output.append(_f32(_f32(scale * _f32(scale_low)) * _f32(byte & 0x0F) - _f32(minimum * _f32(minimum_low))))
        for lane in range(32):
            byte = quants[32 * group + lane]
            output.append(_f32(_f32(scale * _f32(scale_high)) * _f32(byte >> 4) - _f32(minimum * _f32(minimum_high))))
    return output


def _q4_k_matrix(rows: int) -> tuple[dict[str, object], list[np.float32]]:
    packed = bytearray()
    decoded: list[np.float32] = []
    for row in range(rows):
        block = bytearray()
        block.extend(struct.pack("<e", 0.0625 + (row % 3) * 0.015625))
        block.extend(struct.pack("<e", 0.03125 + (row % 2) * 0.015625))
        # Eight 6-bit scale/min pairs.  The upper four retain zero high bits,
        # which keeps the packing independently auditable while exercising all
        # four Q4_K nibble groups.
        block.extend(bytes([1, 2, 3, 4, 0, 1, 2, 3, 0x21, 0x32, 0x43, 0x54]))
        for group in range(4):
            for lane in range(32):
                low = (row * 3 + group * 5 + lane * 7) % 16
                high = (row * 11 + group * 2 + lane * 3 + 1) % 16
                block.append(low | (high << 4))
        assert len(block) == 144
        packed.extend(block)
        decoded.extend(_decode_q4_k_row(bytes(block)))
    payload = bytes(packed)
    return (
        {
            "name": "output.weight",
            "quantization": "Q4_K",
            "shape": [rows, WIDTH],
            "block_elements": 256,
            "block_bytes": 144,
            "packed_hex": payload.hex(),
            "packed_sha256": _sha256(payload),
            "decoded_f32_sha256": _sha256(_f32_bytes(decoded)),
        },
        decoded,
    )


def _rms_norm(values: list[np.float32], scale: list[np.float32]) -> list[np.float32]:
    total = _f32(0.0)
    for value in values:
        total = _f32(total + _f32(value * value))
    mean = _f32(total / _f32(len(values)))
    inverse = _f32(_f32(1.0) / np.sqrt(_f32(mean + RMS_EPS), dtype=np.float32))
    return [_f32(_f32(value * inverse) * weight) for value, weight in zip(values, scale, strict=True)]


def _matvec(matrix: list[np.float32], rows: int, vector: list[np.float32]) -> list[np.float32]:
    output: list[np.float32] = []
    for row in range(rows):
        total = _f32(0.0)
        for column in range(WIDTH):
            total = _f32(total + _f32(matrix[row * WIDTH + column] * vector[column]))
        output.append(total)
    return output


def _stable_top_k(logits: list[np.float32], count: int) -> tuple[list[int], list[np.float32]]:
    ids = sorted(range(len(logits)), key=lambda index: (-float(logits[index]), index))[:count]
    return ids, [logits[index] for index in ids]


def _stress_case(name: str, logits: list[np.float32], top_k: int) -> dict[str, object]:
    ids, scores = _stable_top_k(logits, top_k)
    return {
        "name": name,
        "logits": _record_f32(logits),
        "top_k": top_k,
        "expected_top_k_ids": ids,
        "expected_top_k_scores": _record_f32(scores),
        "expected_argmax": ids[0],
    }


def _top_k_stress_cases() -> list[dict[str, object]]:
    one = _f32(1.0)
    one_up = np.nextafter(one, _f32(math.inf), dtype=np.float32)
    one_down = np.nextafter(one, _f32(-math.inf), dtype=np.float32)
    negative_one_up = np.nextafter(_f32(-1.0), _f32(math.inf), dtype=np.float32)
    tiny = np.nextafter(_f32(0.0), _f32(math.inf), dtype=np.float32)
    return [
        _stress_case("exact_tie_lower_index", [_f32(2.0), _f32(2.0), _f32(1.0), _f32(-1.0)], 3),
        _stress_case("positive_one_ulp", [one, one_up, one_down, _f32(0.0)], 3),
        _stress_case("negative_one_ulp", [_f32(-1.0), negative_one_up, _f32(-2.0)], 2),
        _stress_case("large_finite", [_f32(2.0**100), _f32(-(2.0**100)), _f32(2.0**99)], 2),
        _stress_case("near_zero", [_f32(-0.0), _f32(0.0), tiny, _f32(-tiny)], 4),
        _stress_case("repeated_equal", [_f32(3.0), _f32(3.0), _f32(3.0), _f32(3.0)], 4),
        _stress_case("margin_below_tier_b_scale", [one, one_down, _f32(0.0)], 2),
    ]


def build_oracle(source_commit: str, generator_sha256: str) -> dict[str, object]:
    hidden = [_f32(((index * 13 + 7) % 31 - 15) / 16.0) for index in range(WIDTH)]
    norm_scale = [_f32(0.75 + (index % 9) / 32.0) for index in range(WIDTH)]
    matrix_record, matrix = _q4_k_matrix(VOCAB)
    normalized = _rms_norm(hidden, norm_scale)
    logits = _matvec(matrix, VOCAB, normalized)
    top_k_ids, top_k_scores = _stable_top_k(logits, TOP_K)
    top1_top2_margin = _f32(logits[top_k_ids[0]] - logits[top_k_ids[1]])
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "fixture_version": FIXTURE_VERSION,
        "source_commit": source_commit,
        "generator_path": GENERATOR_PATH,
        "generator_sha256": generator_sha256,
        "independence": {
            "classification": "INDEPENDENT",
            "uses_rust_candidate": False,
            "uses_rust_reference_functions": False,
            "uses_mlx": False,
            "uses_checkpoint": False,
        },
        "architecture": {
            "family": "glm-dsa",
            "boundary": "final_rms_norm_output_head_logits_top_k",
            "hidden_width": WIDTH,
            "vocabulary_size": VOCAB,
            "top_k": TOP_K,
            "real_output_weight_quantization": "Q4_K",
        },
        "inputs": {
            "final_hidden": _record_f32(hidden),
            "output_norm_scale": _record_f32(norm_scale),
            "rms_epsilon": float(RMS_EPS),
            "output_head": matrix_record,
        },
        "expected": {
            "final_normalized": _record_f32(normalized),
            "logits": _record_f32(logits),
            "logits_sha256": _sha256(_f32_bytes(logits)),
            "top_k_ids": top_k_ids,
            "top_k_scores": _record_f32(top_k_scores),
            "argmax": top_k_ids[0],
            "top1_top2_margin": float(top1_top2_margin),
        },
        "top_k_stress_cases": _top_k_stress_cases(),
        "numerical_contract": {
            "exact_scaffold": "exact f32 final RMSNorm, Q4_K decode, sequential output matvec, stable top-k",
            "production": "f017-production-r11-tier-b-v1",
            "greedy_applicability": "applicable",
            "top_k_and_argmax": "exact",
            "tie_break": "descending_total_order_then_lower_index",
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
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generator_sha = _sha256(Path(__file__).read_bytes())
    rendered = json.dumps(build_oracle(args.source_commit, generator_sha), indent=2, sort_keys=True) + "\n"
    if args.check:
        if args.out.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"{args.out}: deterministic regeneration differs")
    else:
        args.out.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
