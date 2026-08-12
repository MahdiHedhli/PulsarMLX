#!/usr/bin/env python3
"""Generate the checkpoint-free F017 M1-D projection qualification package.

This generator is independent of the Rust runner.  It creates a real-shaped
Q8_0 matrix, a deterministic activation, the sequential-column f32 oracle,
and candidate-independent Tier-B bounds.  It never opens a model checkpoint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import struct
import sys
from pathlib import Path

import numpy as np

ROWS = 576
COLUMNS = 6144
BLOCK = 32
BLOCK_BYTES = 34
SEED = 17017004
SCHEMA = "pulsarmlx.f017.m1d-projection-oracle"
SCHEMA_VERSION = "1.0.0"
GENERATOR_VERSION = "f017-m1d-independent-numpy-v1"
SCAFFOLD_VERSION = "f017-m1d-q8-0-sequential-f32-v1"
DECODER_VERSION = "f017-q8-0-decoder-v1"
TIER_B_VERSION = "f017-production-m1d-projection-tier-b-v1"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def f32_bytes(values: np.ndarray) -> bytes:
    return np.asarray(values, dtype="<f4").tobytes(order="C")


def activation() -> np.ndarray:
    rng = np.random.Generator(np.random.PCG64(SEED))
    values = rng.standard_normal(COLUMNS).astype(np.float32)
    values *= np.float32(1.75)
    values[:12] = np.array(
        [0.0, -0.0, 2**-20, -(2**-20), 32.0, -31.5, 0.125, -0.25,
         7.75, -8.5, 1.0, -1.0], dtype=np.float32
    )
    return values


def packed_matrix() -> bytes:
    blocks = ROWS * (COLUMNS // BLOCK)
    row = np.arange(blocks, dtype=np.uint32) // (COLUMNS // BLOCK)
    block = np.arange(blocks, dtype=np.uint32) % (COLUMNS // BLOCK)
    scales = (np.float32(0.00390625) *
              (np.float32(1.0) + ((row * 17 + block * 13) % 29).astype(np.float32) / np.float32(32.0)))
    scales_f16 = scales.astype("<f2")
    lanes = np.arange(BLOCK, dtype=np.int32)[None, :]
    indices = np.arange(blocks, dtype=np.int64)[:, None]
    q = (((indices * 73 + lanes * 41 + SEED) % 255) - 127).astype(np.int8)
    q[(indices[:, 0] % 19) == 0, 0] = 0
    out = np.empty((blocks, BLOCK_BYTES), dtype=np.uint8)
    out[:, :2] = scales_f16.view(np.uint8).reshape(-1, 2)
    out[:, 2:] = q.view(np.uint8)
    return out.tobytes(order="C")


def decode_q8(packed: bytes) -> np.ndarray:
    blocks = np.frombuffer(packed, dtype=np.uint8).reshape(-1, BLOCK_BYTES)
    scales = blocks[:, :2].copy().reshape(-1).view("<f2").astype(np.float32)
    q = blocks[:, 2:].view(np.int8).astype(np.float32)
    decoded = (q * scales[:, None]).reshape(ROWS, COLUMNS)
    return decoded.astype(np.float32, copy=False)


def sequential_matvec(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    output = np.empty(ROWS, dtype=np.float32)
    for r in range(ROWS):
        total = np.float32(0.0)
        for c in range(COLUMNS):
            product = np.float32(matrix[r, c] * vector[c])
            total = np.float32(total + product)
        output[r] = total
    return output


def tier_b(matrix: np.ndarray, vector: np.ndarray, expected: np.ndarray) -> dict:
    u = 2.0 ** -24
    k = 2 * COLUMNS
    gamma = (k * u) / (1.0 - k * u)
    factor = 2.0 * gamma
    floor = 4.0 * COLUMNS * (2.0 ** -149)
    l1 = np.sum(np.abs(matrix.astype(np.float64) * vector.astype(np.float64)[None, :]), axis=1)
    bounds = factor * l1 + floor
    rmse = math.sqrt(float(np.mean(bounds * bounds)))
    expected_norm = float(np.linalg.norm(expected.astype(np.float64)))
    bounds_norm = float(np.linalg.norm(bounds))
    cosine = ((expected_norm - bounds_norm) / (expected_norm + bounds_norm)
              if expected_norm > bounds_norm else None)
    return {
        "formula": "B_i = 2*gamma_(2n)*sum_j(abs(w_ij*x_j)) + 4*n*2^-149",
        "unit_roundoff": u,
        "dot_width": COLUMNS,
        "operation_count": k,
        "gamma": gamma,
        "bound_factor": factor,
        "subnormal_floor": floor,
        "row_bounds_sha256": sha256(np.asarray(bounds, dtype="<f8").tobytes()),
        "global_max_abs_bound": float(np.max(bounds)),
        "rmse_bound": rmse,
        "cosine_minimum": cosine,
        "threshold_fit_to_observed_candidate": False,
    }


def stress_cases() -> list[dict]:
    tiny = np.float32(np.nextafter(np.float32(0), np.float32(1)))
    return [
        {"name": "cancellation", "activation": [1.0, -1.0] * 16},
        {"name": "high_dynamic_range", "activation": [2.0**20, 2.0**-20] * 16},
        {"name": "near_zero", "activation": [2.0**-20, -(2.0**-20)] * 16},
        {"name": "subnormal", "activation": [float(tiny), float(-tiny)] * 16},
        {"name": "signed_zero", "activation": [0.0, -0.0] * 16},
        {"name": "near_overflow_finite", "activation": [2.0**60, -(2.0**60)] * 16},
    ]


def build() -> tuple[dict, bytes]:
    act = activation()
    packed = packed_matrix()
    decoded = decode_q8(packed)
    output = sequential_matvec(decoded, act)
    if not np.isfinite(output).all():
        raise RuntimeError("independent oracle produced a non-finite output")
    document = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "generator": {
            "version": GENERATOR_VERSION,
            "source_sha256": sha256(Path(__file__).read_bytes()),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "seed": SEED,
            "prng": "numpy.PCG64",
        },
        "boundary": {
            "contract_version": "f017-m1d-projection-boundary-v1",
            "tensor": "blk.0.attn_kv_a_mqa.weight",
            "layer": 0,
            "role": "mla_kv_latent_projection",
            "quantization": "Q8_0",
            "matrix_rows": ROWS,
            "matrix_columns": COLUMNS,
            "gguf_shape": [COLUMNS, ROWS],
            "packed_row_bytes": (COLUMNS // BLOCK) * BLOCK_BYTES,
            "packed_length": len(packed),
            "output_shape": [ROWS],
        },
        "activation": {
            "dtype": "f32_le",
            "shape": [COLUMNS],
            "element_count": COLUMNS,
            "bytes_hex": f32_bytes(act).hex(),
            "sha256": sha256(f32_bytes(act)),
            "finite": True,
        },
        "synthetic_matrix": {
            "generator": "row_block_lane_affine_mod255-v1",
            "packed_sha256": sha256(packed),
            "decoded_f32_sha256": sha256(f32_bytes(decoded)),
        },
        "oracle": {
            "generated_before_candidate": True,
            "scaffold_version": SCAFFOLD_VERSION,
            "decoder_contract_version": DECODER_VERSION,
            "output_f32_hex": f32_bytes(output).hex(),
            "output_sha256": sha256(f32_bytes(output)),
        },
        "tier_b": {"contract_version": TIER_B_VERSION, **tier_b(decoded, act, output)},
        "policies": {
            "signed_zero": "exact",
            "nan_inf": "forbidden",
            "deterministic_repeat_minimum": 10,
            "greedy_applicability": "not_applicable",
            "success_classification": "numerically_qualified_greedy_not_applicable",
        },
        "stress_cases": stress_cases(),
        "checkpoint_accessed": False,
    }
    return document, packed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--packed-output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    document, packed = build()
    encoded = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    if args.check:
        if args.output.read_bytes() != encoded or args.packed_output.read_bytes() != packed:
            raise SystemExit("M1-D oracle artifacts differ from deterministic regeneration")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(encoded)
        args.packed_output.write_bytes(packed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
