#!/usr/bin/env python3
"""Generate independent public-safe Feature 017 Tier-B matvec stresses.

This generator does not import Rust, MLX, FFI, checkpoint data, or candidate
outputs. NumPy is used only to make every scalar arithmetic boundary f32.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Callable

import numpy as np


SCHEMA = "pulsarmlx.f017.tier-b-stress-oracle"
SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "f017-production-expert-tier-b-v1"
GENERATOR_PATH = "scripts/research/generate_f017_tierb_stress.py"
WIDTH = 32
U = 2.0**-24
ETA = 2.0**-149
GAMMA_64 = (64.0 * U) / (1.0 - 64.0 * U)
BOUND_FACTOR = 2.0 * GAMMA_64


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _f32_bytes(values: list[np.float32]) -> bytes:
    return b"".join(struct.pack("<f", float(value)) for value in values)


def _f32(value: float) -> np.float32:
    return np.float32(value)


def _exact_matvec(
    matrix: list[np.float32], vector: list[np.float32], rows: int
) -> list[np.float32]:
    output: list[np.float32] = []
    for row in range(rows):
        total = _f32(0.0)
        for column in range(WIDTH):
            product = _f32(matrix[row * WIDTH + column] * vector[column])
            total = _f32(total + product)
        output.append(total)
    return output


def _row_budgets(
    matrix: list[np.float32], vector: list[np.float32], rows: int
) -> tuple[list[float], list[float]]:
    l1_products = []
    budgets = []
    for row in range(rows):
        l1 = math.fsum(
            abs(float(matrix[row * WIDTH + column]) * float(vector[column]))
            for column in range(WIDTH)
        )
        l1_products.append(l1)
        budgets.append(BOUND_FACTOR * l1 + 4.0 * WIDTH * ETA)
    return l1_products, budgets


def _case(
    name: str,
    purpose: str,
    rows: int,
    matrix_fn: Callable[[int, int], float],
    vector_fn: Callable[[int], float],
    *,
    behavioral_selection: bool = False,
) -> dict[str, object]:
    matrix = [_f32(matrix_fn(row, column)) for row in range(rows) for column in range(WIDTH)]
    vector = [_f32(vector_fn(column)) for column in range(WIDTH)]
    output = _exact_matvec(matrix, vector, rows)
    l1_products, bounds = _row_budgets(matrix, vector, rows)
    expected_argmax = max(range(rows), key=lambda index: (float(output[index]), -index))
    return {
        "name": name,
        "purpose": purpose,
        "shape": [rows, WIDTH],
        "matrix": [float(value) for value in matrix],
        "matrix_sha256": _sha256(_f32_bytes(matrix)),
        "vector": [float(value) for value in vector],
        "vector_sha256": _sha256(_f32_bytes(vector)),
        "expected": [float(value) for value in output],
        "expected_sha256": _sha256(_f32_bytes(output)),
        "l1_products": l1_products,
        "absolute_bounds": bounds,
        "rmse_bound": math.sqrt(math.fsum(bound * bound for bound in bounds) / rows),
        "behavioral_selection": behavioral_selection,
        "expected_argmax_lowest_index_tie_break": expected_argmax,
    }


def build_oracle(source_commit: str, generator_sha256: str) -> dict[str, object]:
    cases = [
        _case(
            "one_row_positive",
            "smallest supported output shape and monotone positive products",
            1,
            lambda _r, c: (c + 1) * 0.125,
            lambda c: 0.5 + (c % 7) * 0.125,
        ),
        _case(
            "alternating_signs",
            "alternating signs with row-dependent cancellation",
            4,
            lambda r, c: (-1.0 if (r + c) % 2 else 1.0) * (1 + (3 * r + c) % 11),
            lambda c: 0.25 + (c % 5) * 0.125,
        ),
        _case(
            "cancellation_sensitive",
            "large cancelling partial sums separated by small residual terms",
            4,
            lambda r, c: (
                (2.0**20 if c % 4 == 0 else -2.0**20 if c % 4 == 2 else (r + 1) * (c + 1) * 0.25)
            ),
            lambda _c: 1.0,
        ),
        _case(
            "large_dynamic_range",
            "products spanning powers of two with mixed signs",
            8,
            lambda r, c: (-1.0 if (r * 5 + c) % 3 == 0 else 1.0) * 2.0 ** ((c % 21) - 10),
            lambda c: 2.0 ** (10 - (c % 17)),
        ),
        _case(
            "small_residual_after_large_partials",
            "small f32 residual retained after repeated large partial sums",
            4,
            lambda r, c: (
                65536.0
                if c % 4 == 0
                else -65536.0
                if c % 4 == 2
                else (r + 1) * (1.0 if c % 4 == 1 else -0.5)
            ),
            lambda _c: 1.0,
        ),
        _case(
            "denormal_adjacent",
            "normal and subnormal-adjacent products without non-finite values",
            4,
            lambda r, c: (-1.0 if c % 2 else 1.0) * (2.0 ** (-120 + r)) * (1 + c % 3),
            lambda c: 0.5 + (c % 4) * 0.25,
        ),
        _case(
            "large_magnitude",
            "large finite outputs and a large absolute forward-error budget",
            8,
            lambda r, c: (-1.0 if (r + c) % 7 == 0 else 1.0) * (2.0**20) * (1 + (r + c) % 5),
            lambda c: (2.0**8) * (1 + c % 3),
        ),
        _case(
            "full_shape_sign_changes",
            "complete 32x32 shape with deterministic row and column sign changes",
            32,
            lambda r, c: (-1.0 if (r * 13 + c * 7) % 5 < 2 else 1.0) * ((r * 17 + c * 11) % 31 + 1) / 8.0,
            lambda c: (-1.0 if c % 3 == 0 else 1.0) * (0.5 + (c % 9) / 16.0),
        ),
        _case(
            "near_tie_rows",
            "two close outputs exercise explicit behavioral classification",
            2,
            lambda r, c: (1.0 + c / 64.0) if r == 0 or c < 31 else (1.0 + c / 64.0 + 2.0**-20),
            lambda c: 1.0 / 32.0 if c < 31 else 1.0,
            behavioral_selection=True,
        ),
    ]
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
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
        "arithmetic": {
            "dtype": "f32",
            "column_order": "strict_increasing",
            "multiply_add": "separately_rounded",
            "fast_math": False,
            "dot_width": WIDTH,
            "bound_factor": BOUND_FACTOR,
        },
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    generator_sha256 = _sha256(Path(__file__).read_bytes())
    payload = build_oracle(args.source_commit, generator_sha256)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
