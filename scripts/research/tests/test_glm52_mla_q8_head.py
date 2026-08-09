#!/usr/bin/env python3
"""Native exactness and read-contract tests for experimental Q8 head slabs."""

from __future__ import annotations

import importlib.util
import struct
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from glm52_dense_primitives import (  # noqa: E402
    capture_dense_metrics,
    dense_read_mode,
    require_mlx_backend,
)
from glm52_mla import _matvec_3d_q8  # noqa: E402
from glm52_tensor_store import TensorLoc  # noqa: E402


class FakeStore:
    def __init__(self, loc, encoded, truncate=False):
        self.tensors = {loc.name: loc}
        self.encoded = encoded
        self.truncate = truncate
        self.calls = []

    def pread(self, name, relative, size):
        self.calls.append((name, relative, size))
        result = self.encoded[relative : relative + size]
        if self.truncate and size == len(self.encoded):
            return result[:-1]
        return result


@unittest.skipIf(importlib.util.find_spec("mlx") is None, "native MLX required")
class Q8HeadSlabTests(unittest.TestCase):
    def setUp(self) -> None:
        self.encoded = b"".join(
            struct.pack("<e", scale) + struct.pack("<32b", *range(-16, 16))
            for scale in (0.5, -0.25)
        )
        self.loc = TensorLoc(
            name="head.weight",
            file=Path("fixture.gguf"),
            offset=0,
            n_bytes=len(self.encoded),
            type_id=8,
            type_name="Q8_0",
            dims=[32, 2, 1],
        )
        self.activation = [float(index) / 32 for index in range(32)]

    def _run(self, mode):
        store = FakeStore(self.loc, self.encoded)
        with require_mlx_backend(), dense_read_mode(mode), capture_dense_metrics() as capture:
            output = _matvec_3d_q8(store, self.loc.name, 0, self.activation, out_dim_key="fixture")
        self.assertEqual(len(capture.operations), 1)
        return np.asarray(output, dtype=np.float32), capture.operations[0], store.calls

    def test_row_bulk_scalar_and_numpy_outputs_are_exact(self) -> None:
        row, row_metrics, row_calls = self._run("whole_matrix_numpy_q5_q8")
        bulk, bulk_metrics, bulk_calls = self._run("whole_matrix_numpy_q5_q8_head_bulk_scalar")
        vector, vector_metrics, vector_calls = self._run("whole_matrix_numpy_q5_q8_head_numpy")
        self.assertTrue(np.array_equal(row.view(np.uint32), bulk.view(np.uint32)))
        self.assertTrue(np.array_equal(row.view(np.uint32), vector.view(np.uint32)))
        self.assertEqual(row_metrics.storage_read_count, 2)
        self.assertEqual(bulk_metrics.storage_read_count, 1)
        self.assertEqual(vector_metrics.storage_read_count, 1)
        self.assertEqual(row_metrics.decoder_mode, "scalar_reference")
        self.assertEqual(bulk_metrics.decoder_mode, "scalar_reference")
        self.assertEqual(vector_metrics.decoder_mode, "numpy_vectorized_q8_0")
        self.assertEqual(len(row_calls), 2)
        self.assertEqual(bulk_calls, [(self.loc.name, 0, len(self.encoded))])
        self.assertEqual(vector_calls, [(self.loc.name, 0, len(self.encoded))])

    def test_truncated_bulk_head_fails_closed(self) -> None:
        store = FakeStore(self.loc, self.encoded, truncate=True)
        with self.assertRaisesRegex(OSError, "truncated head slab"):
            with require_mlx_backend(), dense_read_mode("whole_matrix_numpy_q5_q8_head_bulk_scalar"):
                _matvec_3d_q8(store, self.loc.name, 0, self.activation, out_dim_key="fixture")


if __name__ == "__main__":
    unittest.main()
