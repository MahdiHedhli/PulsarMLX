#!/usr/bin/env python3
"""Exact-bit tests for the opt-in NumPy IQ2_XXS decoder."""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

try:
    import numpy as np
except ModuleNotFoundError:
    np = None  # type: ignore[assignment]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from iq2_xxs_dequant import (  # noqa: E402
    BLOCK_BYTES,
    QK_K,
    dequantize_blocks_iq2_xxs_numpy,
    dequantize_matrix_iq2_xxs_numpy,
    dequantize_row_iq2_xxs,
)
from qualify_iq2_xxs_numpy import _summary  # noqa: E402


def scalar_f32_bits(encoded: bytes) -> np.ndarray:
    scalar = np.asarray(dequantize_row_iq2_xxs(encoded), dtype=np.float32)
    return scalar.view(np.uint32)


@unittest.skipIf(np is None, "NumPy is installed by the lockfile-backed CI tier")
class NumpyIq2XxsDecoderTests(unittest.TestCase):
    def test_timing_summary_uses_sample_deviation_without_module_shadowing(self) -> None:
        summary = _summary([1.0, 2.0, 3.0])
        self.assertEqual(summary["sample_count"], 3)
        self.assertEqual(summary["mean_seconds"], 2.0)
        self.assertEqual(summary["standard_deviation_seconds"], 1.0)
        self.assertEqual(summary["coefficient_of_variation"], 0.5)

    def assert_exact_bits(self, encoded: bytes) -> np.ndarray:
        expected = scalar_f32_bits(encoded)
        actual = dequantize_blocks_iq2_xxs_numpy(encoded)
        self.assertEqual(actual.dtype, np.dtype(np.float32))
        self.assertTrue(actual.flags.c_contiguous)
        np.testing.assert_array_equal(actual.view(np.uint32), expected)
        return actual.view(np.uint32)

    def test_randomized_finite_blocks_match_scalar_f32_bits(self) -> None:
        rng = np.random.default_rng(0x50554C534152)
        blocks = []
        for _ in range(257):
            scale = np.float16(rng.uniform(-4.0, 4.0))
            payload = rng.integers(0, 256, size=64, dtype=np.uint8).tobytes()
            blocks.append(scale.tobytes() + payload)
        self.assert_exact_bits(b"".join(blocks))

    def test_signed_zero_matches_scalar_exactly(self) -> None:
        payload = bytearray(64)
        struct.pack_into("<I", payload, 4, 1)
        bits = self.assert_exact_bits(struct.pack("<e", -0.0) + payload)
        self.assertIn(np.uint32(0), bits)
        self.assertIn(np.uint32(0x80000000), bits)

    def test_matrix_shape_contiguity_and_determinism(self) -> None:
        rng = np.random.default_rng(42)
        encoded = b"".join(
            np.float16(index + 0.25).tobytes()
            + rng.integers(0, 256, size=64, dtype=np.uint8).tobytes()
            for index in range(6)
        )
        first = dequantize_matrix_iq2_xxs_numpy(encoded, rows=2, cols=3 * QK_K)
        second = dequantize_matrix_iq2_xxs_numpy(encoded, rows=2, cols=3 * QK_K)
        self.assertEqual(first.shape, (2, 3 * QK_K))
        self.assertTrue(first.flags.c_contiguous)
        np.testing.assert_array_equal(first.view(np.uint32), second.view(np.uint32))
        np.testing.assert_array_equal(first.reshape(-1).view(np.uint32), scalar_f32_bits(encoded))

    def test_malformed_truncated_overlong_and_nonfinite_fail_closed(self) -> None:
        valid = struct.pack("<e", 1.0) + bytes(64)
        for malformed in (b"", valid[:-1], valid + b"\x00"):
            with self.subTest(length=len(malformed)):
                with self.assertRaises(ValueError):
                    dequantize_blocks_iq2_xxs_numpy(malformed)
        with self.assertRaises(ValueError):
            dequantize_matrix_iq2_xxs_numpy(valid, rows=1, cols=2 * QK_K)
        with self.assertRaises(ValueError):
            dequantize_matrix_iq2_xxs_numpy(valid + valid, rows=1, cols=QK_K)
        for value in (float("inf"), float("-inf"), float("nan")):
            with self.subTest(scale=value):
                with self.assertRaises(ValueError):
                    dequantize_blocks_iq2_xxs_numpy(
                        struct.pack("<e", value) + bytes(64)
                    )


if __name__ == "__main__":
    unittest.main()
