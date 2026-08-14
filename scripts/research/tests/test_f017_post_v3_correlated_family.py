from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "scripts/research/generate_f017_m1f0_post_v3_correlated_family.py"
SPEC = importlib.util.spec_from_file_location("f017_post_v3_correlated_family", PATH)
assert SPEC is not None and SPEC.loader is not None
GEN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GEN)


class PostV3CorrelatedFamilyTests(unittest.TestCase):
    def test_seed_order_is_frozen(self) -> None:
        self.assertEqual(GEN.SEEDS, tuple(range(17_017_201, 17_017_209)))

    def test_generation_is_deterministic_norm_calibrated_and_correlated(self) -> None:
        first = GEN.hidden_state(GEN.SEEDS[0])
        second = GEN.hidden_state(GEN.SEEDS[0])
        np.testing.assert_array_equal(first, second)
        self.assertAlmostEqual(float(np.sqrt(np.mean(first.astype(np.float64) ** 2))), 1.125, places=5)
        self.assertGreater(float(np.corrcoef(first[:-1], first[1:])[0, 1]), 0.5)

    def test_seed_expansion_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            GEN.hidden_state(GEN.SEEDS[-1] + 1)

    def test_manifest_precommits_selection_stopping_and_banking(self) -> None:
        fixtures = [GEN.document(seed) for seed in GEN.SEEDS]
        value = GEN.manifest(ROOT, fixtures)
        self.assertEqual(value["selection_rule"], "first qualifying fixture in precommitted ordinal order")
        self.assertIn("every precommitted fixture", value["execution_stopping_rule"])
        self.assertEqual(value["best_of_n_selection"], "FORBIDDEN")
        self.assertFalse(value["real_execution_authorized"])
        self.assertEqual(value["checkpoint_access"], 0)


if __name__ == "__main__":
    unittest.main()
