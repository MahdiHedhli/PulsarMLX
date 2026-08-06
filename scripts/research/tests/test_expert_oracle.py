#!/usr/bin/env python3
import importlib.util
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from expert_oracle import (  # noqa: E402
    EXPERT_GATE_UP_BYTES,
    GATE_UP_ROW_BYTES,
    compare_vectors,
    expert_byte_range,
    _silu,
    _swiglu,
)


class ExpertOracleTests(unittest.TestCase):
    def test_layout_constants(self) -> None:
        self.assertEqual(GATE_UP_ROW_BYTES, 2176)
        self.assertEqual(EXPERT_GATE_UP_BYTES, 1_671_168)
        off, n = expert_byte_range("blk.0.ffn_gate_exps.weight", 114)
        self.assertEqual(n, 1_671_168)
        self.assertEqual(off, 901_175_808 + 114 * 1_671_168)

    def test_silu_and_swiglu(self) -> None:
        self.assertTrue(math.isclose(_silu(0.0), 0.0, abs_tol=1e-12))
        self.assertGreater(_silu(1.0), 0.0)
        out = _swiglu([1.0, -1.0], [2.0, 3.0])
        self.assertEqual(len(out), 2)

    def test_compare_pass(self) -> None:
        c = compare_vectors([1.0, 2.0], [1.0, 2.0], 5e-4, 5e-4)
        self.assertTrue(c["passed"])

    def test_does_not_import_mlx(self) -> None:
        self.assertNotIn("mlx", sys.modules)


if __name__ == "__main__":
    unittest.main()
