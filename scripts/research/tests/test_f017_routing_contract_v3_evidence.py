from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from scripts.research import f017_routing_contract_v3 as v3
from scripts.research import generate_f017_routing_v3_evidence as evidence


ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / evidence.CONTRACT
RETROSPECTIVE = (
    ROOT
    / "docs/architecture/reviews/evidence/f017-routing-v3-fixture1-retrospective-v1.json"
)


class FrozenContractTests(unittest.TestCase):
    def test_contract_is_the_pre_observation_identity(self) -> None:
        self.assertEqual(v3.sha256_path(CONTRACT), evidence.CONTRACT_SHA256)
        contract = v3.parse_json_no_duplicates(CONTRACT)
        self.assertFalse(
            contract["freeze"]["fixture_1_values_used_to_choose_coefficients_or_thresholds"]
        )
        self.assertEqual(contract["freeze"]["engineering_headroom"], 2.0)
        self.assertEqual(
            contract["rank_diagnostics"]["rank_mismatch_alone"],
            "DIAGNOSTIC_NOT_SEMANTIC_FAILURE",
        )

    def test_retrospective_is_deterministically_regenerated(self) -> None:
        result = v3.parse_json_no_duplicates(RETROSPECTIVE)
        private = ROOT / "target/f017-v2-antecedent-recovery-event-1/recovery-package/antecedents"
        if private.is_dir():
            self.assertEqual(
                RETROSPECTIVE.read_bytes(),
                v3.canonical_json_bytes(evidence.retrospective(ROOT)),
            )
        else:
            self.assertEqual(result["accepted_raw_v2_recovery_sha256"], v3.RAW_RECOVERY_SHA256)
            self.assertEqual(result["pre_observation_freeze"]["contract_sha256"], evidence.CONTRACT_SHA256)
        self.assertEqual(
            result["fixture_1_disposition"],
            "SEMANTICALLY_VALID_BUT_INSUFFICIENT_HEADROOM",
        )
        self.assertTrue(result["membership"]["mathematically_stable"])
        self.assertFalse(result["membership"]["engineering_headroom"])
        self.assertFalse(result["rank_diagnostics"]["historical_v2_route_order_stable"])
        self.assertFalse(result["retrospective_v3"]["m1f_candidate_execution_qualified"])

    def test_historical_contracts_and_ledger_are_unchanged(self) -> None:
        result = v3.parse_json_no_duplicates(RETROSPECTIVE)
        self.assertTrue(result["historical_v1_status_unchanged"])
        self.assertTrue(result["historical_v2_status_unchanged"])
        self.assertEqual(result["real_payload_ledger"], 57)
        self.assertEqual(result["checkpoint_access"], 0)


class FalsePassAttackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        route = json.loads(
            (ROOT / "docs/architecture/reviews/evidence/f017-m1-f0-layer3-route-v1.json").read_text()
        )
        cls.oracle = v3.atomic_pairs(route["top8_ids"], route["routing_weights"])
        retained = v3.parse_json_no_duplicates(RETROSPECTIVE)
        cls.weights = {
            int(key): value
            for key, value in retained["per_expert_weight_contract"]["by_expert_id"].items()
        }
        cls.intervals = {
            expert_id: (value["routing_weight_low"], value["routing_weight_high"])
            for expert_id, value in cls.weights.items()
        }

    def test_set_sorting_cannot_hide_duplicate_or_missing_pairs(self) -> None:
        with self.assertRaises(ValueError):
            v3.atomic_pairs(
                [item.expert_id for item in self.oracle[:-1]] + [self.oracle[0].expert_id],
                [item.routing_weight for item in self.oracle],
            )

    def test_canonical_serialization_does_not_hide_runtime_order_policy(self) -> None:
        permuted = tuple(reversed(self.oracle))
        result = v3.qualify_candidate_pairs(self.oracle, permuted, self.intervals)
        self.assertTrue(result["semantic_pass"])
        self.assertFalse(result["rank_equal"])
        self.assertNotEqual(
            v3.rank_diagnostic_bytes(self.oracle), v3.rank_diagnostic_bytes(permuted)
        )

    def test_individual_weight_pass_does_not_override_layer_sum_failure(self) -> None:
        pair_result = v3.qualify_candidate_pairs(self.oracle, self.oracle, self.intervals)
        self.assertTrue(pair_result["semantic_pass"])
        outputs = {
            item.expert_id: ((-1.0) ** index * (2.0**20 + index),)
            for index, item in enumerate(self.oracle)
        }
        accumulation = v3.qualify_accumulation_orders(
            self.oracle,
            outputs,
            sorted(item.expert_id for item in self.oracle),
        )
        self.assertFalse(accumulation["covered_by_r10_intermediate_tier_b"])
        contract = v3.parse_json_no_duplicates(CONTRACT)
        self.assertIn(
            "complete-layer numerical contract passes",
            contract["qualification"]["mathematical_pass"],
        )

    def test_nonfinite_and_signed_zero_weight_fail(self) -> None:
        ids = [item.expert_id for item in self.oracle]
        weights = [item.routing_weight for item in self.oracle]
        for invalid in (math.nan, math.inf, -math.inf, -0.0, 0.0):
            with self.assertRaises(ValueError):
                v3.atomic_pairs(ids, weights[:-1] + [invalid])

    def test_exact_and_near_ties_use_lower_id(self) -> None:
        scores = {9: 1.0, 3: 1.0, 5: math.nextafter(1.0, -math.inf)}
        ranking = sorted(scores, key=lambda expert_id: (-scores[expert_id], expert_id))
        self.assertEqual(ranking, [3, 9, 5])

    def test_different_accumulation_policy_requires_disclosure_and_bound(self) -> None:
        contract = v3.parse_json_no_duplicates(CONTRACT)
        required = contract["accumulation"]["required_checks"]
        self.assertIn("candidate runtime reports its actual reduction order", required)
        self.assertEqual(
            contract["accumulation"]["different_runtime_policy_without_bound_evidence"],
            "REJECT",
        )


class PlanningEvidenceTests(unittest.TestCase):
    def test_dense_prefix_is_honestly_multi_layer(self) -> None:
        value = evidence.dense_prefix(ROOT)
        self.assertEqual(value["metadata"]["glm-dsa.leading_dense_block_count"], 3)
        self.assertTrue(value["not_a_single_layer_fixture_operation"])
        self.assertEqual(value["estimated_scope"]["conceptual_layers_executed"], 3)
        self.assertEqual(value["status"], "CHARACTERIZED_NOT_IMPLEMENTED_NOT_AUTHORIZED")

    def test_representative_target_retains_stress_split(self) -> None:
        value = evidence.representative_target()
        self.assertTrue(value["target"]["separate_adversarial_stress_fixture"])
        self.assertEqual(value["status"], "PLANNING_ONLY_NOT_AUTHORIZED")


if __name__ == "__main__":
    unittest.main()
