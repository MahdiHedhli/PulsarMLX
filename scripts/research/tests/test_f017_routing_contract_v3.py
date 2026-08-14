from __future__ import annotations

import itertools
import json
import math
import struct
import unittest
from decimal import Decimal, localcontext
from pathlib import Path

import numpy as np

from scripts.research import f017_routing_contract_v3 as v3


ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "docs/architecture/reviews/evidence/f017-v2-antecedent-recovery-result-v1.json"
ROUTE = ROOT / "docs/architecture/reviews/evidence/f017-m1-f0-layer3-route-v1.json"


def route_pairs() -> tuple[v3.RoutingPair, ...]:
    value = json.loads(ROUTE.read_text())
    return v3.atomic_pairs(value["top8_ids"], value["routing_weights"])


def simple_pairs() -> tuple[v3.RoutingPair, ...]:
    return v3.atomic_pairs(list(range(8)), [0.1 + index * 0.01 for index in range(8)])


class RoutingSemanticTraceTests(unittest.TestCase):
    def test_trace_classifies_rank_as_numerically_observable_not_model_semantic(self) -> None:
        trace = v3.build_source_trace(ROOT)
        v3.validate_source_trace(ROOT, trace)
        self.assertEqual(
            trace["classification"],
            "ORDER_IS_NUMERICALLY_OBSERVABLE_NOT_MODEL_SEMANTIC",
        )
        self.assertEqual(trace["unresolved_rank_dependence"], [])
        self.assertFalse(trace["runtime_semantics_changed"])

    def test_source_identities_are_complete_sha256(self) -> None:
        sources = v3.source_identities(ROOT)
        self.assertEqual(len(sources), 6)
        self.assertTrue(all(len(item["sha256"]) == 64 for item in sources))


class AtomicRoutingPairTests(unittest.TestCase):
    def test_joint_permutations_are_mathematically_equivalent(self) -> None:
        pairs = simple_pairs()
        outputs = {
            item.expert_id: (item.expert_id - 3.5, (-1.0) ** item.expert_id)
            for item in pairs
        }
        expected = v3.mathematical_moe_sum(pairs, outputs)
        for order in (
            tuple(reversed(pairs)),
            tuple(sorted(pairs, key=lambda item: (item.expert_id * 5) % 7)),
            tuple(pairs[index] for index in (3, 1, 7, 0, 6, 2, 5, 4)),
        ):
            self.assertEqual(v3.mathematical_moe_sum(order, outputs), expected)

    def test_independent_weight_permutation_is_not_equivalent(self) -> None:
        pairs = simple_pairs()
        outputs = {item.expert_id: (float(item.expert_id + 1),) for item in pairs}
        wrong = v3.atomic_pairs(
            [item.expert_id for item in pairs],
            [item.routing_weight for item in reversed(pairs)],
        )
        self.assertNotEqual(
            v3.mathematical_moe_sum(pairs, outputs),
            v3.mathematical_moe_sum(wrong, outputs),
        )

    def test_id_sorted_atomic_serialization_is_permutation_invariant(self) -> None:
        pairs = simple_pairs()
        permuted = tuple(reversed(pairs))
        self.assertEqual(v3.canonical_semantic_bytes(pairs), v3.canonical_semantic_bytes(permuted))
        self.assertEqual(v3.canonical_semantic_sha256(pairs), v3.canonical_semantic_sha256(permuted))
        self.assertNotEqual(v3.rank_diagnostic_bytes(pairs), v3.rank_diagnostic_bytes(permuted))
        self.assertEqual(len(v3.canonical_semantic_bytes(pairs)), 8 * (2 + 8))

    def test_serialization_keeps_id_and_weight_atomic(self) -> None:
        pairs = simple_pairs()
        payload = v3.canonical_semantic_bytes(tuple(reversed(pairs)))
        decoded = [struct.unpack_from("<Hd", payload, offset) for offset in range(0, len(payload), 10)]
        self.assertEqual([item[0] for item in decoded], list(range(8)))
        self.assertEqual([item[1] for item in decoded], [item.routing_weight for item in pairs])

    def test_duplicate_missing_nonfinite_and_signed_zero_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            v3.atomic_pairs([0, 0, 1, 2, 3, 4, 5, 6], [0.1] * 8)
        with self.assertRaises(ValueError):
            v3.atomic_pairs(list(range(7)), [0.1] * 7)
        with self.assertRaises(ValueError):
            v3.atomic_pairs(list(range(8)), [0.1] * 7 + [math.inf])
        with self.assertRaises(ValueError):
            v3.atomic_pairs(list(range(8)), [0.1] * 7 + [-0.0])


class WeightQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.oracle = route_pairs()
        retained = ROOT / "docs/architecture/reviews/evidence/f017-routing-v3-fixture1-retrospective-v1.json"
        private = ROOT / "target/f017-v2-antecedent-recovery-event-1/recovery-package/antecedents"
        if private.is_dir():
            probability = v3.individual_probability_intervals(ROOT)
            cls.weights = v3.normalized_weight_intervals(probability, cls.oracle)
            if retained.is_file():
                banked = json.loads(retained.read_text())["per_expert_weight_contract"]["by_expert_id"]
                if {str(key): value for key, value in sorted(cls.weights.items())} != banked:
                    raise AssertionError("banked and private-derived weight contracts differ")
        else:
            if not retained.is_file():
                raise AssertionError("public retained ID-keyed v3 weight contract is missing")
            cls.weights = {
                int(key): value
                for key, value in json.loads(retained.read_text())[
                    "per_expert_weight_contract"
                ]["by_expert_id"].items()
            }

    def test_retained_antecedents_produce_all_eight_id_keyed_intervals(self) -> None:
        self.assertEqual(set(self.weights), {item.expert_id for item in self.oracle})
        for expert_id, value in self.weights.items():
            self.assertLess(value["routing_weight_low"], value["oracle_routing_weight"])
            self.assertLess(value["oracle_routing_weight"], value["routing_weight_high"])
            self.assertGreater(value["positivity_safety_factor"], 1.0)
            self.assertTrue(value["oracle_self_consistent"])
            self.assertEqual(value["inherited_r10_candidate_atol"], 1.0e-5)

    def test_same_pairs_different_rank_semantically_pass(self) -> None:
        candidate = tuple(reversed(self.oracle))
        intervals = {
            expert_id: (value["routing_weight_low"], value["routing_weight_high"])
            for expert_id, value in self.weights.items()
        }
        result = v3.qualify_candidate_pairs(self.oracle, candidate, intervals)
        self.assertTrue(result["semantic_pass"])
        self.assertTrue(result["engineering_headroom_pass"])
        self.assertFalse(result["rank_equal"])
        self.assertTrue(result["semantic_hash_equal"])

    def test_same_ids_misassociated_weights_fail(self) -> None:
        candidate = v3.atomic_pairs(
            [item.expert_id for item in self.oracle],
            [item.routing_weight for item in reversed(self.oracle)],
        )
        intervals = {
            expert_id: (value["routing_weight_low"], value["routing_weight_high"])
            for expert_id, value in self.weights.items()
        }
        result = v3.qualify_candidate_pairs(self.oracle, candidate, intervals)
        self.assertFalse(result["semantic_pass"])
        self.assertTrue(result["failed_weight_experts"])

    def test_one_weight_outside_bound_fails(self) -> None:
        intervals = {
            expert_id: (value["routing_weight_low"], value["routing_weight_high"])
            for expert_id, value in self.weights.items()
        }
        target = self.oracle[3]
        candidate = list(self.oracle)
        candidate[3] = v3.RoutingPair(target.expert_id, intervals[target.expert_id][1] + 1.0e-6)
        result = v3.qualify_candidate_pairs(self.oracle, candidate, intervals)
        self.assertFalse(result["semantic_pass"])
        self.assertEqual(result["failed_weight_experts"], [target.expert_id])

    def test_inherited_r10_cap_rejects_value_inside_wider_propagated_interval(self) -> None:
        intervals = {
            expert_id: (value["routing_weight_low"], value["routing_weight_high"])
            for expert_id, value in self.weights.items()
        }
        target = self.oracle[0]
        candidate = list(self.oracle)
        candidate[0] = v3.RoutingPair(target.expert_id, target.routing_weight + 2.0e-5)
        self.assertLess(candidate[0].routing_weight, intervals[target.expert_id][1])
        result = v3.qualify_candidate_pairs(self.oracle, candidate, intervals)
        self.assertFalse(result["semantic_pass"])
        self.assertEqual(result["failed_weight_experts"], [target.expert_id])

    def test_mathematical_pass_can_lack_engineering_headroom(self) -> None:
        intervals = {
            expert_id: (value["routing_weight_low"], value["routing_weight_high"])
            for expert_id, value in self.weights.items()
        }
        target = self.oracle[0]
        candidate = list(self.oracle)
        candidate[0] = v3.RoutingPair(
            target.expert_id,
            target.routing_weight - 7.5e-6,
        )
        result = v3.qualify_candidate_pairs(self.oracle, candidate, intervals)
        self.assertTrue(result["semantic_pass"])
        self.assertFalse(result["engineering_headroom_pass"])
        self.assertEqual(result["failed_engineering_weight_experts"], [target.expert_id])

    def test_one_expert_replaced_fails(self) -> None:
        intervals = {
            expert_id: (value["routing_weight_low"], value["routing_weight_high"])
            for expert_id, value in self.weights.items()
        }
        candidate = list(self.oracle)
        candidate[-1] = v3.RoutingPair(98, candidate[-1].routing_weight)
        with self.assertRaises(ValueError):
            v3.qualify_candidate_pairs(self.oracle, candidate, intervals)


class AccumulationPolicyTests(unittest.TestCase):
    def test_rank_and_id_order_can_differ_bitwise_but_stay_bounded(self) -> None:
        pairs = simple_pairs()
        outputs = {
            0: (6.888437030500963, 5.159088058806049),
            1: (-1.5885683833831, -4.821664994140733),
            2: (0.22549442737217085, -1.9013172509917133),
            3: (5.675971780695452, -3.933745478421451),
            4: (-0.4680609169528829, 1.6676407891006235),
            5: (8.162257703906704, 0.09373711634780513),
            6: (-4.363243112005923, 5.116084083144479),
            7: (2.3673799335066334, -4.989873172751189),
        }
        result = v3.qualify_accumulation_orders(
            tuple(reversed(pairs)), outputs, [3, 1, 7, 0, 6, 2, 5, 4]
        )
        self.assertTrue(result["mathematical_equivalence"])
        self.assertFalse(result["bitwise_equivalence"])
        self.assertTrue(result["covered_by_r10_intermediate_tier_b"])
        self.assertFalse(result["runtime_change"])

    def test_every_permutation_of_four_active_terms_is_bounded(self) -> None:
        terms = {
            index: (v3.f32(value),)
            for index, value in enumerate((1e20, 1.0, -1e20, 0.5, 0.0, -0.0, 1e-30, -1e-30))
        }
        reference = v3.accumulate_f32(tuple(range(8)), terms)[0]
        bound = v3.accumulation_order_bound(terms)[0]
        for prefix in itertools.permutations(range(4)):
            order = prefix + (4, 5, 6, 7)
            self.assertLessEqual(abs(reference - v3.accumulate_f32(order, terms)[0]), bound)

    def test_high_precision_exact_sum_is_enclosed_for_every_order(self) -> None:
        values = (1e20, 1.0, -1e20, 0.5, 1e-30, -1e-30, 3.0, -2.0)
        terms = {index: (v3.f32(value),) for index, value in enumerate(values)}
        with localcontext() as context:
            context.prec = 100
            exact = sum((Decimal.from_float(item[0]) for item in terms.values()), Decimal(0))
        single_order_bound = v3.accumulation_order_bound(terms)[0] / 2.0
        for order in (tuple(range(8)), tuple(reversed(range(8))), (3, 1, 7, 0, 6, 2, 5, 4)):
            actual = Decimal.from_float(v3.accumulate_f32(order, terms)[0])
            self.assertLessEqual(float(abs(actual - exact)), single_order_bound)

    def test_randomized_accumulation_stress_has_no_under_bounds(self) -> None:
        result = v3.accumulation_stress(2_000, seed=170_189_004)
        self.assertEqual(result["under_bound_count"], 0)
        self.assertLessEqual(result["maximum_observed_actual_to_bound_ratio"], 1.0)

    def test_asynchronous_completion_does_not_control_declared_reduction_order(self) -> None:
        pairs = simple_pairs()
        terms = {item.expert_id: (float(item.expert_id + 1),) for item in pairs}
        completion = [7, 2, 0, 6, 4, 1, 5, 3]
        declared = sorted(completion)
        self.assertEqual(
            v3.accumulate_f32(declared, terms),
            v3.accumulate_f32(sorted(p.expert_id for p in pairs), terms),
        )
        self.assertNotEqual(completion, declared)

    def test_nonfinite_atomic_term_fails(self) -> None:
        pairs = simple_pairs()
        outputs = {item.expert_id: (1.0,) for item in pairs}
        outputs[7] = (math.nan,)
        with self.assertRaises(ValueError):
            v3.f32_atomic_terms(pairs, outputs)


class HistoricalImmutabilityTests(unittest.TestCase):
    def test_raw_v2_recovery_remains_immutable(self) -> None:
        self.assertEqual(v3.sha256_path(RAW), v3.RAW_RECOVERY_SHA256)

    def test_v2_contract_and_route_are_bound_but_not_rewritten(self) -> None:
        self.assertEqual(
            v3.sha256_path(ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-m1f-route-stability-v2.json"),
            v3.V2_CONTRACT_SHA256,
        )
        self.assertEqual(v3.sha256_path(ROUTE), v3.ROUTE_SHA256)

    def test_ledger_constant_is_57(self) -> None:
        self.assertEqual(v3.LEDGER, 57)


if __name__ == "__main__":
    unittest.main()
