import importlib.util
import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "scripts/research/bank_f017_v2_antecedent_recovery.py"
SPEC = importlib.util.spec_from_file_location("f017_v2_recovery_banker", SOURCE)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class V2RecoveryBankerTests(unittest.TestCase):
    def test_true_minimum_and_membership_order_are_separate(self):
        selected = MODULE.EXPECTED_ROUTE
        unselected = [item for item in range(256) if item not in selected]
        membership = [
            {"relation": "membership", "selected": i, "challenger": j,
             "margin": 3.0, "B_pair": 1.0, "safety_factor": 3.0}
            for i in selected for j in unselected
        ]
        membership[-1] = {"relation": "membership", "selected": 177,
                          "challenger": unselected[-1], "margin": 1.25,
                          "B_pair": 1.0, "safety_factor": 1.25}
        ordered = [
            {"relation": "ordered_selected", "selected": i, "challenger": j,
             "margin": 3.0, "B_pair": 1.0, "safety_factor": 3.0}
            for i, j in zip(selected, selected[1:])
        ]
        ordered[-1] = {"relation": "ordered_selected", "selected": 233,
                       "challenger": 177, "margin": 0.25,
                       "B_pair": 1.0, "safety_factor": 0.25}
        summary = MODULE.summarize_surface({
            "selected_ids_ordered": selected,
            "unselected_ids": unselected,
            "selected_unselected_pair_bounds": membership,
            "adjacent_selected_pair_bounds": ordered,
        })
        self.assertTrue(summary["membership_stable"])
        self.assertFalse(summary["membership_engineering_headroom"])
        self.assertFalse(summary["ordered_selected_stable"])
        self.assertFalse(summary["exact_ordered_top8_mathematically_stable"])
        self.assertEqual(summary["minimum_mathematical_safety_factor"], 0.25)
        self.assertEqual(summary["minimum_engineering_safety_factor"], 0.125)

    def test_nonfinite_and_incomplete_surfaces_fail_closed(self):
        with self.assertRaises(ValueError):
            MODULE.summarize_surface({
                "selected_ids_ordered": MODULE.EXPECTED_ROUTE,
                "unselected_ids": [],
                "selected_unselected_pair_bounds": [],
                "adjacent_selected_pair_bounds": [],
            })

    def test_banked_public_evidence_is_complete_and_ledger_is_append_only(self):
        evidence = ROOT / "docs/architecture/reviews/evidence"
        result_raw = (evidence / "f017-v2-antecedent-recovery-result-v1.json").read_bytes()
        result = json.loads(result_raw)
        review = json.loads((evidence / "f017-v2-antecedent-recovery-review-v1.json").read_text())
        private = json.loads((evidence / "f017-v2-antecedent-recovery-private-manifest-v1.json").read_text())
        ledger = json.loads((evidence / "f017-real-payload-access-ledger-v1.json").read_text())
        authorization_raw = (evidence / "f017-v2-antecedent-recovery-authorization-v1.json").read_bytes()

        self.assertEqual(hashlib.sha256(result_raw).hexdigest(), "f9422287cb98322d1412a6dd2397bb0f4a0d6538778aa587dddff7c5154acf2a")
        self.assertEqual(hashlib.sha256(authorization_raw).hexdigest(), "46c1f8e0ef0ee38aee5565ccf3f389a29266beba1bcca32a41848bacde6ab906")
        self.assertTrue(result["identity_reproduction"]["accepted_computation_reproduced_exactly"])
        self.assertEqual(len(result["antecedent_retention"]["pairwise_surface"]["selected_unselected_pair_bounds"]), 1984)
        self.assertEqual(len(result["antecedent_retention"]["pairwise_surface"]["adjacent_selected_pair_bounds"]), 7)
        self.assertTrue(review["pairwise_summary"]["membership_stable"])
        self.assertFalse(review["pairwise_summary"]["ordered_selected_stable"])
        self.assertEqual(review["pairwise_summary"]["minimum_mathematical_safety_factor"], 0.22551544432236478)
        self.assertTrue(review["immutable_raw_summary_audit"]["membership_subclassification_corrected"])
        self.assertEqual(private["artifact_count"], 8)
        self.assertFalse(private["machine_local_paths_published"])
        self.assertTrue(all(not Path(item["symbolic_name"]).is_absolute() for item in private["artifacts"]))
        self.assertEqual(ledger["cumulative_tensor_payloads"], 57)
        self.assertEqual(sum(item["tensor_payload_count"] for item in ledger["events"]), 57)
        self.assertEqual(ledger["events"][-1]["attempt"], "analytical-antecedent-recovery-1")
        self.assertFalse(ledger["events"][-1]["consumed_attempt"])


if __name__ == "__main__":
    unittest.main()
