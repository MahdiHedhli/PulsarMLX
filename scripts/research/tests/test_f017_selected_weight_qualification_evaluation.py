from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import unittest

from scripts.research import f017_selected_weight_qualification_evaluation as evaluation


ROOT = Path(__file__).resolve().parents[3]
ROUTE_EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-dprefix-route-ambiguity-v31-evaluation-v1.json"


class SelectedWeightQualificationEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.route = evaluation.load_json(ROUTE_EVIDENCE)

    def test_banked_eight_are_evaluated_by_expert_id(self) -> None:
        result = evaluation.evaluate(self.route)
        self.assertEqual(result["selected_expert_ids"], [250, 10, 237, 73, 62, 177, 218, 28])
        self.assertEqual(set(result["qualification"]["by_expert_id"]), {str(i) for i in result["selected_expert_ids"]})
        self.assertEqual(result["membership"]["mathematical_pass_count"], 1984)

    def test_rho_is_frozen_outward_radius(self) -> None:
        result = evaluation.evaluate(self.route)
        for record in result["qualification"]["by_expert_id"].values():
            nominal = record["nominal_weight"]
            interval = record["interval"]
            expected = math.nextafter(
                max(nominal - interval["lower"], interval["upper"] - nominal),
                math.inf,
            )
            self.assertEqual(record["outward_absolute_radius"], expected)
            self.assertEqual(record["mathematical_threshold"], 1.0e-5)
            self.assertEqual(record["engineering_h2_threshold"], 5.0e-6)

    def test_joint_normalization_and_disposition_are_derived(self) -> None:
        result = evaluation.evaluate(self.route)
        self.assertTrue(result["qualification"]["joint_normalization_valid"])
        self.assertEqual(result["qualification"]["denominator_floor_status"], "INACTIVE_FOR_ENTIRE_BOX")
        self.assertEqual(
            result["final_route_disposition"],
            "ROUTE NOT PROVEN INVARIANT",
        )

    def test_deterministic_replay(self) -> None:
        first = evaluation.canonical_json_bytes(evaluation.evaluate(self.route))
        second = evaluation.canonical_json_bytes(evaluation.evaluate(self.route))
        self.assertEqual(first, second)
        self.assertEqual(hashlib.sha256(first).hexdigest(), hashlib.sha256(second).hexdigest())

    def test_membership_or_selected_set_mutation_fails_closed(self) -> None:
        bad = copy.deepcopy(self.route)
        bad["evaluation"]["membership"]["mathematical_pass_count"] = 1983
        with self.assertRaises(evaluation.ProductionWeightEvaluationError):
            evaluation.evaluate(bad)
        bad = copy.deepcopy(self.route)
        bad["evaluation"]["exact_route"]["selected_top8"][0] = 249
        with self.assertRaises(evaluation.ProductionWeightEvaluationError):
            evaluation.evaluate(bad)

    def test_frozen_input_identity_and_duplicate_json_fail_closed(self) -> None:
        bad = copy.deepcopy(self.route)
        bad["authority"]["DPREFIX_EXACT_1_sha256"] = "0" * 64
        with self.assertRaises(evaluation.ProductionWeightEvaluationError):
            evaluation.evaluate(bad)
        with self.assertRaises(evaluation.ProductionWeightEvaluationError):
            json.loads('{"a":1,"a":2}', object_pairs_hook=evaluation.reject_duplicates)

    def test_evaluation_preserves_zero_access_and_ledger(self) -> None:
        result = evaluation.evaluate(self.route)
        self.assertEqual(
            result["isolation"],
            {
                "checkpoint_reads": 0,
                "shard_opens": 0,
                "candidate_or_model_dispatches": 0,
                "real_payload_ledger_before": 139,
                "real_payload_ledger_after": 139,
                "ledger_mutated": False,
            },
        )


if __name__ == "__main__":
    unittest.main()
