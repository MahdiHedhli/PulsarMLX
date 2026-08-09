#!/usr/bin/env python3
"""Exact-bit and malformed-input tests for NumPy Q8_0 decoding."""

from __future__ import annotations

import random
import struct
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from glm52_dense_primitives import _decode_q8_0_row  # noqa: E402
from q8_0_dequant import (  # noqa: E402
    BLOCK_BYTES,
    dequantize_blocks_q8_0_numpy,
    dequantize_matrix_q8_0_numpy,
)


def _block(rng: random.Random, scale: float) -> bytes:
    return struct.pack("<e", scale) + bytes(rng.randrange(256) for _ in range(32))


class Q80NumpyTests(unittest.TestCase):
    def test_randomized_blocks_match_scalar_f32_bits(self) -> None:
        rng = random.Random(0x80)
        encoded = b"".join(_block(rng, rng.uniform(-4, 4)) for _ in range(131))
        scalar = np.asarray(_decode_q8_0_row(encoded, 131 * 32), dtype=np.float32)
        vector = dequantize_blocks_q8_0_numpy(encoded)
        repeated = dequantize_blocks_q8_0_numpy(encoded)
        self.assertTrue(np.array_equal(scalar.view(np.uint32), vector.view(np.uint32)))
        self.assertTrue(np.array_equal(vector.view(np.uint32), repeated.view(np.uint32)))
        self.assertTrue(vector.flags.c_contiguous)

    def test_signed_zero_and_matrix_row_order(self) -> None:
        rng = random.Random(8)
        encoded = _block(rng, -0.0) + _block(rng, 0.0)
        scalar = np.asarray(_decode_q8_0_row(encoded, 64), dtype=np.float32)
        matrix = dequantize_matrix_q8_0_numpy(encoded, 2, 32)
        self.assertTrue(np.array_equal(scalar.view(np.uint32), matrix.reshape(-1).view(np.uint32)))
        self.assertGreater(np.count_nonzero(matrix.view(np.uint32) == 0x80000000), 0)

    def test_malformed_inputs_fail_closed(self) -> None:
        rng = random.Random(1)
        block = _block(rng, 1.0)
        for encoded in (b"", block[:-1], block + b"\0"):
            with self.assertRaises(ValueError):
                dequantize_blocks_q8_0_numpy(encoded)
        with self.assertRaises(ValueError):
            dequantize_matrix_q8_0_numpy(block, 0, 32)
        with self.assertRaises(ValueError):
            dequantize_matrix_q8_0_numpy(block, 1, 31)
        with self.assertRaises(ValueError):
            dequantize_matrix_q8_0_numpy(block[:-1], 1, 32)

    def test_nonfinite_scale_fails_closed(self) -> None:
        rng = random.Random(2)
        block = bytearray(_block(rng, 1.0))
        block[:2] = struct.pack("<e", float("inf"))
        with self.assertRaises(ValueError):
            dequantize_blocks_q8_0_numpy(bytes(block))


if __name__ == "__main__":
    unittest.main()
