#!/usr/bin/env python3
"""Checkpoint-free tests for the bounded residency harness."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from benchmark_glm52_trunk_residency import _summary_nonnegative  # noqa: E402


class TrunkResidencyHarnessTests(unittest.TestCase):
    def test_summary_accepts_absent_stage_zeros(self) -> None:
        summary = _summary_nonnegative([0.0, 0.0, 0.0])
        self.assertEqual(summary["median_seconds"], 0.0)
        self.assertEqual(summary["coefficient_of_variation"], 0.0)

    def test_summary_rejects_negative_values(self) -> None:
        with self.assertRaises(ValueError):
            _summary_nonnegative([0.0, -1.0])


if __name__ == "__main__":
    unittest.main()
