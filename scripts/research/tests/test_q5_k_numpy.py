#!/usr/bin/env python3
"""Exact-bit and malformed-input tests for the NumPy Q5_K decoder."""

from __future__ import annotations

import random
import struct
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from ggml_kquants import (  # noqa: E402
    Q5_K_BLOCK,
    dequantize_blocks_q5_k_numpy,
    dequantize_matrix_q5_k_numpy,
    dequantize_row_q5_k,
)


def _block(rng: random.Random, d: float, dmin: float) -> bytes:
    return (
        struct.pack("<ee", d, dmin)
        + bytes(rng.randrange(256) for _ in range(12 + 32 + 128))
    )


class Q5KNumpyTests(unittest.TestCase):
    def test_randomized_blocks_match_scalar_f32_bits_and_repeat(self) -> None:
        rng = random.Random(0x5137)
        encoded = b"".join(
            _block(rng, rng.uniform(-2, 2), rng.uniform(-2, 2))
            for _ in range(97)
        )
        scalar = np.asarray(dequantize_row_q5_k(encoded), dtype=np.float32)
        vector = dequantize_blocks_q5_k_numpy(encoded)
        repeated = dequantize_blocks_q5_k_numpy(encoded)
        self.assertTrue(np.array_equal(scalar.view(np.uint32), vector.view(np.uint32)))
        self.assertTrue(np.array_equal(vector.view(np.uint32), repeated.view(np.uint32)))
        self.assertTrue(vector.flags.c_contiguous)

    def test_signed_zero_bits_match_scalar(self) -> None:
        rng = random.Random(5)
        encoded = _block(rng, -0.0, 0.0) + _block(rng, 0.0, -0.0)
        scalar = np.asarray(dequantize_row_q5_k(encoded), dtype=np.float32)
        vector = dequantize_blocks_q5_k_numpy(encoded)
        self.assertTrue(np.array_equal(scalar.view(np.uint32), vector.view(np.uint32)))
        self.assertGreater(np.count_nonzero(vector.view(np.uint32) == 0x80000000), 0)

    def test_matrix_shape_and_row_order(self) -> None:
        rng = random.Random(52)
        rows, cols = 3, 512
        encoded = b"".join(_block(rng, 0.5, -0.25) for _ in range(rows * 2))
        matrix = dequantize_matrix_q5_k_numpy(encoded, rows, cols)
        self.assertEqual(matrix.shape, (rows, cols))
        for row in range(rows):
            start = row * 2 * Q5_K_BLOCK
            raw = encoded[start : start + 2 * Q5_K_BLOCK]
            scalar = np.asarray(dequantize_row_q5_k(raw, cols), dtype=np.float32)
            self.assertTrue(
                np.array_equal(scalar.view(np.uint32), matrix[row].view(np.uint32))
            )

    def test_malformed_inputs_fail_closed(self) -> None:
        rng = random.Random(1)
        block = _block(rng, 1.0, 0.5)
        for encoded in (b"", block[:-1], block + b"\0"):
            with self.assertRaises(ValueError):
                dequantize_blocks_q5_k_numpy(encoded)
        with self.assertRaises(ValueError):
            dequantize_matrix_q5_k_numpy(block, 0, 256)
        with self.assertRaises(ValueError):
            dequantize_matrix_q5_k_numpy(block, 1, 255)
        with self.assertRaises(ValueError):
            dequantize_matrix_q5_k_numpy(block[:-1], 1, 256)

    def test_nonfinite_scales_fail_closed(self) -> None:
        rng = random.Random(2)
        block = bytearray(_block(rng, 1.0, 0.5))
        block[0:2] = struct.pack("<e", float("nan"))
        with self.assertRaises(ValueError):
            dequantize_blocks_q5_k_numpy(bytes(block))


if __name__ == "__main__":
    unittest.main()
