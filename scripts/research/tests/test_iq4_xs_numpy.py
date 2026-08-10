#!/usr/bin/env python3
"""Exact-bit and malformed-input tests for NumPy IQ4_XS decoding."""

from __future__ import annotations

import random
import struct
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))
from iq4_xs_dequant import (  # noqa: E402
    dequantize_blocks_iq4_xs_numpy,
    dequantize_matrix_iq4_xs_numpy,
    dequantize_row_iq4_xs,
)


def _block(rng: random.Random, d: float) -> bytes:
    return struct.pack("<e", d) + bytes(rng.randrange(256) for _ in range(134))


class IQ4XSNumPyTests(unittest.TestCase):
    def test_randomized_blocks_match_scalar_f32_bits(self) -> None:
        rng = random.Random(0x4415)
        encoded = b"".join(_block(rng, rng.uniform(-3, 3)) for _ in range(89))
        scalar = np.asarray(dequantize_row_iq4_xs(encoded), dtype=np.float32)
        vector = dequantize_blocks_iq4_xs_numpy(encoded)
        repeated = dequantize_blocks_iq4_xs_numpy(encoded)
        self.assertTrue(np.array_equal(scalar.view(np.uint32), vector.view(np.uint32)))
        self.assertTrue(np.array_equal(vector.view(np.uint32), repeated.view(np.uint32)))

    def test_signed_zero_and_row_order(self) -> None:
        rng = random.Random(23)
        encoded = _block(rng, -0.0) + _block(rng, 0.0)
        scalar = np.asarray(dequantize_row_iq4_xs(encoded), dtype=np.float32)
        matrix = dequantize_matrix_iq4_xs_numpy(encoded, 2, 256)
        self.assertTrue(np.array_equal(scalar.view(np.uint32), matrix.reshape(-1).view(np.uint32)))
        self.assertEqual(
            np.count_nonzero(scalar.view(np.uint32) == 0x80000000),
            np.count_nonzero(matrix.view(np.uint32) == 0x80000000),
        )

    def test_malformed_inputs_fail_closed(self) -> None:
        rng = random.Random(1)
        block = _block(rng, 1.0)
        for encoded in (b"", block[:-1], block + b"\0"):
            with self.assertRaises(ValueError):
                dequantize_blocks_iq4_xs_numpy(encoded)
        with self.assertRaises(ValueError):
            dequantize_matrix_iq4_xs_numpy(block, 0, 256)
        with self.assertRaises(ValueError):
            dequantize_matrix_iq4_xs_numpy(block, 1, 255)
        with self.assertRaises(ValueError):
            dequantize_matrix_iq4_xs_numpy(block[:-1], 1, 256)

    def test_nonfinite_scale_fails_closed(self) -> None:
        rng = random.Random(2)
        block = bytearray(_block(rng, 1.0))
        block[:2] = struct.pack("<e", float("nan"))
        with self.assertRaises(ValueError):
            dequantize_blocks_iq4_xs_numpy(bytes(block))


if __name__ == "__main__":
    unittest.main()
