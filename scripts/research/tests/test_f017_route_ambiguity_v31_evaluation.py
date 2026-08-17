from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

import f017_route_ambiguity_v31_evaluation as evaluation


class RouteAmbiguityV31EvaluationTests(unittest.TestCase):
    def synthetic_inputs(self) -> dict[str, object]:
        width = 4
        center = [0.5, -0.25, 0.75, -1.0]
        real2 = [value + 1e-10 for value in center]
        real3 = [value - 2e-10 for value in center]
        gamma = [1.0, -0.5, 0.75, 1.25]
        rows = []
        for expert_id in range(256):
            scale = (expert_id + 1) * 1e-5
            rows.append([scale, -scale, scale * 0.5, -scale * 0.25])
        correction_bias = [10.0 - expert_id * 0.01 for expert_id in range(256)]
        guards = [1e-12] * 256
        return {
            "center": center,
            "real2": real2,
            "real3": real3,
            "gamma": gamma,
            "router_rows": rows,
            "correction_bias": correction_bias,
            "reduction_guards": guards,
            "import_guards": guards,
        }

    def test_complete_evaluation_has_256_rows_and_1984_pairs(self) -> None:
        result = evaluation.evaluate_vectors(**self.synthetic_inputs())
        self.assertEqual(len(result["exact_route"]["ranking"]), 256)
        self.assertEqual(result["membership"]["evaluated"], 1984)
        self.assertEqual(len(result["membership"]["pairs"]), 1984)
        self.assertEqual(len(result["exact_route"]["selected_top8"]), 8)

    def test_evaluation_is_deterministic(self) -> None:
        inputs = self.synthetic_inputs()
        first = evaluation.canonical_json(evaluation.evaluate_vectors(**inputs))
        second = evaluation.canonical_json(evaluation.evaluate_vectors(**inputs))
        self.assertEqual(first, second)
        self.assertEqual(hashlib.sha256(first).hexdigest(), hashlib.sha256(second).hexdigest())

    def test_box_is_centered_on_exact_and_rounded_outward(self) -> None:
        box = evaluation.build_ambiguity_box(
            [1.0, -2.0],
            [math.nextafter(1.0, math.inf), -2.0],
            [1.0, math.nextafter(-2.0, -math.inf)],
        )
        self.assertEqual(box.center, (1.0, -2.0))
        self.assertGreaterEqual(box.radius[0], math.nextafter(1.0, math.inf) - 1.0)
        self.assertGreaterEqual(box.radius[1], abs(-2.0 - math.nextafter(-2.0, -math.inf)))

    def test_weight_intervals_are_id_keyed_and_not_rank_qualified(self) -> None:
        result = evaluation.evaluate_vectors(**self.synthetic_inputs())
        weights = result["selected_weights"]
        self.assertEqual(weights["qualification"], "REQUIRES_FROZEN_ACCEPTANCE_RULE")
        self.assertTrue(weights["all_exact_weights_contained"])
        self.assertEqual(
            set(map(int, weights["by_expert_id"])),
            set(result["exact_route"]["selected_top8"]),
        )

    def test_duplicate_or_short_router_surface_fails_closed(self) -> None:
        inputs = self.synthetic_inputs()
        inputs["router_rows"] = inputs["router_rows"][:-1]
        with self.assertRaises(evaluation.EvaluationError):
            evaluation.evaluate_vectors(**inputs)

    def test_non_finite_input_fails_closed(self) -> None:
        inputs = self.synthetic_inputs()
        inputs["center"][0] = math.nan
        with self.assertRaises((evaluation.EvaluationError, ValueError)):
            evaluation.evaluate_vectors(**inputs)

    def test_isolation_contract_is_zero_read_and_ledger_immutable(self) -> None:
        self.assertEqual(evaluation.CHECKPOINT_READS, 0)
        self.assertEqual(evaluation.SHARD_OPENS, 0)
        self.assertEqual(evaluation.REAL_PAYLOAD_LEDGER, 139)

    def test_public_result_rejects_machine_local_paths(self) -> None:
        result = evaluation.evaluate_vectors(**self.synthetic_inputs())
        text = evaluation.canonical_json(result).decode("utf-8")
        self.assertNotIn("/Users/", text)
        self.assertNotIn(".pulsarmlx-local", text)

    def test_expected_synthetic_selected_set_is_stable(self) -> None:
        result = evaluation.evaluate_vectors(**self.synthetic_inputs())
        self.assertEqual(result["exact_route"]["selected_top8"], list(range(8)))
        self.assertTrue(result["membership"]["all_membership_invariant"])

    def test_canonical_json_rejects_non_finite_numbers(self) -> None:
        with self.assertRaises(ValueError):
            evaluation.canonical_json({"bad": math.inf})


if __name__ == "__main__":
    unittest.main()
