from __future__ import annotations

import importlib.util
import math
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "scripts/research/bank_f017_post_v3_fixture_descriptors.py"
SPEC = importlib.util.spec_from_file_location("f017_post_v3_fixture_descriptors", PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FixtureDescriptorTests(unittest.TestCase):
    def test_complete_frozen_order_without_route_labels(self) -> None:
        result = MODULE.build(ROOT)
        self.assertEqual(result["seed_order"], list(range(17_017_007, 17_017_015)))
        self.assertEqual(len(result["fixtures"]), 8)
        self.assertTrue(all(item["predicted_family_membership"] for item in result["fixtures"]))
        self.assertFalse(result["actual_route_labels_generated"])
        forbidden = {"top8_ids", "router_scores", "ranking", "routing_weights"}
        self.assertTrue(all(forbidden.isdisjoint(item) for item in result["fixtures"]))
        self.assertEqual(result["checkpoint_access"], 0)

    def test_lag1_correlation_is_fixed_order_and_blas_independent(self) -> None:
        values = np.asarray([1.0, -2.0, 4.0, -8.0, 16.0], dtype=np.float64)
        observed = MODULE.deterministic_lag1_correlation(values)
        left = tuple(float(value) for value in values[:-1])
        right = tuple(float(value) for value in values[1:])
        left_mean = math.fsum(left) / len(left)
        right_mean = math.fsum(right) / len(right)
        expected = math.fsum(
            (x - left_mean) * (y - right_mean) for x, y in zip(left, right)
        ) / math.sqrt(
            math.fsum((x - left_mean) ** 2 for x in left)
            * math.fsum((y - right_mean) ** 2 for y in right)
        )
        self.assertEqual(observed, expected)


if __name__ == "__main__":
    unittest.main()
