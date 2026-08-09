#!/usr/bin/env python3
"""Checkpoint-free tests for experimental whole-matrix scalar reads."""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from glm52_dense_primitives import _load_scalar_dense_matrix  # noqa: E402
from glm52_tensor_store import TensorLoc  # noqa: E402


class FakeStore:
    def __init__(self, loc: TensorLoc, encoded: bytes, *, truncate_bulk: bool = False) -> None:
        self.tensors = {loc.name: loc}
        self.encoded = encoded
        self.truncate_bulk = truncate_bulk
        self.calls: list[tuple[str, int, int]] = []

    def pread(self, name: str, rel: int, size: int) -> bytes:
        self.calls.append((name, rel, size))
        result = self.encoded[rel : rel + size]
        if self.truncate_bulk and rel == 0 and size == len(self.encoded):
            return result[:-1]
        return result


def f32_bits(values: list[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


class DenseBulkReadTests(unittest.TestCase):
    def test_q8_scalar_decoder_bits_match_with_one_complete_read(self) -> None:
        cols = 32
        rows = 3
        encoded_rows = []
        for scale, offset in ((1.0, -16), (-0.5, 4), (0.0, -8)):
            encoded_rows.append(
                struct.pack("<e", scale)
                + struct.pack("<32b", *(offset + index for index in range(32)))
            )
        encoded = b"".join(encoded_rows)
        loc = TensorLoc(
            name="fixture.weight",
            file=Path("fixture.gguf"),
            offset=0,
            n_bytes=len(encoded),
            type_id=8,
            type_name="Q8_0",
            dims=[cols, rows],
        )
        row_store = FakeStore(loc, encoded)
        bulk_store = FakeStore(loc, encoded)
        reference, reference_metrics = _load_scalar_dense_matrix(
            row_store, loc, cols, rows, "row_reference"
        )
        actual, actual_metrics = _load_scalar_dense_matrix(
            bulk_store, loc, cols, rows, "whole_matrix_scalar"
        )
        self.assertEqual(f32_bits(actual), f32_bits(reference))
        self.assertEqual(reference_metrics.storage_read_count, rows)
        self.assertEqual(actual_metrics.storage_read_count, 1)
        self.assertEqual(reference_metrics.encoded_bytes, len(encoded))
        self.assertEqual(actual_metrics.encoded_bytes, len(encoded))
        self.assertEqual(len(row_store.calls), rows)
        self.assertEqual(bulk_store.calls, [(loc.name, 0, len(encoded))])

    def test_f32_preserves_signed_zero_and_row_order(self) -> None:
        values = [0.0, -0.0, 1.25, -2.5, -3.0, 4.0, -0.0, 0.0]
        encoded = struct.pack("<8f", *values)
        loc = TensorLoc(
            name="f32.weight",
            file=Path("fixture.gguf"),
            offset=0,
            n_bytes=len(encoded),
            type_id=0,
            type_name="F32",
            dims=[4, 2],
        )
        reference, _ = _load_scalar_dense_matrix(
            FakeStore(loc, encoded), loc, 4, 2, "row_reference"
        )
        actual, _ = _load_scalar_dense_matrix(
            FakeStore(loc, encoded), loc, 4, 2, "whole_matrix_scalar"
        )
        self.assertEqual(f32_bits(actual), f32_bits(reference))
        self.assertEqual(f32_bits(actual), encoded)

    def test_truncated_complete_buffer_fails_closed(self) -> None:
        encoded = struct.pack("<8f", *range(8))
        loc = TensorLoc(
            name="truncated.weight",
            file=Path("fixture.gguf"),
            offset=0,
            n_bytes=len(encoded),
            type_id=0,
            type_name="F32",
            dims=[4, 2],
        )
        with self.assertRaisesRegex(OSError, "truncated complete matrix"):
            _load_scalar_dense_matrix(
                FakeStore(loc, encoded, truncate_bulk=True),
                loc,
                4,
                2,
                "whole_matrix_scalar",
            )

    def test_size_mismatch_and_unknown_mode_fail_before_reads(self) -> None:
        encoded = struct.pack("<8f", *range(8))
        loc = TensorLoc(
            name="bad-size.weight",
            file=Path("fixture.gguf"),
            offset=0,
            n_bytes=len(encoded) - 1,
            type_id=0,
            type_name="F32",
            dims=[4, 2],
        )
        store = FakeStore(loc, encoded)
        with self.assertRaisesRegex(ValueError, "encoded matrix size mismatch"):
            _load_scalar_dense_matrix(store, loc, 4, 2, "whole_matrix_scalar")
        self.assertEqual(store.calls, [])
        with self.assertRaisesRegex(ValueError, "unsupported dense read mode"):
            _load_scalar_dense_matrix(store, loc, 4, 2, "vectorized")
        self.assertEqual(store.calls, [])


if __name__ == "__main__":
    unittest.main()
