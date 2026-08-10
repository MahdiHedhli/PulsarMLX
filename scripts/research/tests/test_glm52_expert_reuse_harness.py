#!/usr/bin/env python3
"""Checkpoint-free tests for the routed-expert reuse harness."""

from __future__ import annotations
import math, unittest

from scripts.research.benchmark_glm52_expert_reuse import CANDIDATES, EXPERT, LAYER, _summary


class ExpertReuseHarnessTests(unittest.TestCase):
    def test_frozen_candidate_and_route_contract(self):
        self.assertEqual(CANDIDATES, ("transient", "decoded_host_rebuild", "mlx_ready_reuse"))
        self.assertEqual((LAYER, EXPERT), (64, 183))

    def test_summary_rejects_invalid_samples(self):
        self.assertEqual(_summary([1.0, 2.0, 3.0])["median_seconds"], 2.0)
        for values in ([], [-1.0], [math.nan]):
            with self.assertRaises(ValueError):
                _summary(values)


if __name__ == "__main__":
    unittest.main()
