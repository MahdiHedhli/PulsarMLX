from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "scripts/research/f017_post_v3_estimator.py"
SPEC = importlib.util.spec_from_file_location("f017_post_v3_estimator", PATH)
assert SPEC is not None and SPEC.loader is not None
EST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EST)


class PostV3EstimatorTests(unittest.TestCase):
    def test_retained_inputs_are_identity_bound_and_complete(self) -> None:
        values = EST.retained_inputs(ROOT)
        self.assertEqual(np.asarray(values["probabilities"]).shape, (256,))
        self.assertEqual(np.asarray(values["bias"]).shape, (256,))
        self.assertLessEqual(float(values["ratio_max"]), 1.0)
        self.assertLess(float(values["ratio_min"]), float(values["ratio_median"]))

    def test_full_membership_surface_not_only_rank_boundary(self) -> None:
        scores = np.zeros((1, 256), dtype=np.float64)
        scores[0, :8] = np.arange(16.0, 8.0, -1.0)
        scores[0, 8:] = -1000.0
        # Expert 255 is far below the cutoff, but an enormous independent
        # bound makes it the weakest full-set proof. A rank-8/rank-9-only
        # estimator would miss this deliberately adversarial case.
        bounds = np.ones(256, dtype=np.float64)
        bounds[255] = 1.0e9
        safety = EST._surface_safety(scores, bounds)
        self.assertLess(float(safety[0]), 1.0e-5)

    def test_three_way_planning_rule(self) -> None:
        self.assertAlmostEqual(EST.p_any(0.0), 0.0)
        self.assertAlmostEqual(EST.p_any(1.0), 1.0)
        low, high = EST.wilson(0, 1_000_000)
        self.assertEqual(low, 0.0)
        self.assertLess(high, 4.0e-6)

    def test_small_simulation_is_deterministic_and_zero_read(self) -> None:
        first = EST.simulate(ROOT, family="frozen_random_normal", sample_count=128, seed=91)
        second = EST.simulate(ROOT, family="frozen_random_normal", sample_count=128, seed=91)
        self.assertEqual(first, second)
        self.assertEqual(first["checkpoint_access"], 0)
        self.assertFalse(first["frozen_ladder_executed"])
        self.assertEqual(first["real_payload_ledger"], 57)
        self.assertIn(first["planning_decision"]["disposition"], {
            "EXISTING_FROZEN_LADDER_VIABLE",
            "EXISTING_FROZEN_LADDER_NOT_VIABLE",
            "ESTIMATOR_INCONCLUSIVE",
        })

    def test_correlated_surrogate_is_planning_only(self) -> None:
        result = EST.simulate(ROOT, family="correlated_low_rank", sample_count=64, seed=92)
        self.assertIn("surrogate", result["family_model"])
        self.assertIn("NOT_ESTIMABLE", result["complete_semantic_set_plus_weight_rate"])
        self.assertFalse(result["real_access_authorized"])


if __name__ == "__main__":
    unittest.main()
