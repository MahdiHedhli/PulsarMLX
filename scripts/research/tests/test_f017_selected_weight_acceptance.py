from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import random
import unittest

from scripts.research import f017_routing_contract_v31 as v31
from scripts.research import f017_selected_weight_acceptance as weights


IDS = tuple(range(8))


def probability_box(center: float, radius: float) -> tuple[dict[int, float], dict[int, v31.Interval]]:
    nominal = {expert_id: center for expert_id in IDS}
    intervals = {
        expert_id: v31.Interval(center - radius, center + radius)
        for expert_id in IDS
    }
    return nominal, intervals


class SelectedWeightAcceptanceTests(unittest.TestCase):
    def test_zero_width_box_is_qualified_with_engineering_headroom(self) -> None:
        nominal, intervals = probability_box(0.25, 0.0)
        result = weights.qualify_probability_box(IDS, nominal, intervals, selected_set_invariant=True)
        self.assertTrue(result.mathematically_qualified)
        self.assertTrue(result.engineering_h2)
        self.assertTrue(result.joint_normalization_valid)

    def test_narrow_valid_box_and_nominal_boundary(self) -> None:
        nominal, intervals = probability_box(0.25, 1.0e-8)
        result = weights.qualify_probability_box(IDS, nominal, intervals, selected_set_invariant=True)
        self.assertTrue(result.mathematically_qualified)
        direct = weights.qualify_weight_enclosures(
            IDS,
            {expert_id: 0.3125 for expert_id in IDS},
            {expert_id: v31.Interval(0.3125, 0.3125 + 1.0e-6) for expert_id in IDS},
            nominal_probability_sum=2.0,
            probability_sum_interval=v31.Interval(2.0, 2.0),
            selected_set_invariant=True,
        )
        self.assertTrue(direct.mathematically_qualified)

    def test_contains_nominal_but_exceeds_mathematical_budget(self) -> None:
        direct = weights.qualify_weight_enclosures(
            IDS,
            {expert_id: 0.3125 for expert_id in IDS},
            {
                expert_id: v31.Interval(0.3125 - (2.0e-5 if expert_id == 3 else 1.0e-7), 0.3125 + 1.0e-7)
                for expert_id in IDS
            },
            nominal_probability_sum=2.0,
            probability_sum_interval=v31.Interval(2.0, 2.0),
            selected_set_invariant=True,
        )
        self.assertFalse(direct.mathematically_qualified)
        self.assertEqual(direct.failed_mathematical_ids, (3,))

    def test_near_zero_uses_absolute_not_fitted_relative_rule(self) -> None:
        nominal = {expert_id: 0.2 for expert_id in IDS}
        nominal[0] = 1.0e-12
        intervals = {expert_id: v31.Interval(value, value) for expert_id, value in nominal.items()}
        intervals[0] = v31.Interval(0.5e-12, 1.5e-12)
        result = weights.qualify_probability_box(IDS, nominal, intervals, selected_set_invariant=True)
        self.assertTrue(result.mathematically_qualified)
        self.assertGreater(result.by_expert_id[0].relative_radius, 0.0)

    def test_denominator_floor_active_and_inactive_are_modeled(self) -> None:
        active_nominal, active_intervals = probability_box(1.0e-7, 1.0e-12)
        active = weights.qualify_probability_box(IDS, active_nominal, active_intervals, selected_set_invariant=True)
        self.assertEqual(active.denominator_floor_status, "ACTIVE_FOR_ENTIRE_BOX")
        self.assertLess(active.joint_weight_sum_interval.upper, weights.ROUTING_WEIGHT_SCALE)

        inactive_nominal, inactive_intervals = probability_box(0.2, 1.0e-8)
        inactive = weights.qualify_probability_box(IDS, inactive_nominal, inactive_intervals, selected_set_invariant=True)
        self.assertEqual(inactive.denominator_floor_status, "INACTIVE_FOR_ENTIRE_BOX")
        self.assertTrue(inactive.joint_weight_sum_interval.contains(weights.ROUTING_WEIGHT_SCALE))

    def test_floor_transition_is_supported_conservatively(self) -> None:
        center = weights.DENOMINATOR_FLOOR / 8.0
        nominal, intervals = probability_box(center, center * 0.05)
        result = weights.qualify_probability_box(IDS, nominal, intervals, selected_set_invariant=True)
        self.assertEqual(result.denominator_floor_status, "TRANSITION_WITHIN_BOX")
        self.assertTrue(result.joint_normalization_valid)

    def test_joint_sum_uses_common_denominator_not_independent_weight_extrema(self) -> None:
        nominal, intervals = probability_box(0.2, 1.0e-4)
        result = weights.qualify_probability_box(IDS, nominal, intervals, selected_set_invariant=True)
        independent_width = math.fsum(
            item.interval.upper - item.interval.lower for item in result.by_expert_id.values()
        )
        joint_width = result.joint_weight_sum_interval.upper - result.joint_weight_sum_interval.lower
        self.assertLess(joint_width, independent_width)

    def test_aggregate_conservation_can_hold_while_per_id_budget_fails(self) -> None:
        nominal, intervals = probability_box(0.2, 1.0e-3)
        result = weights.qualify_probability_box(IDS, nominal, intervals, selected_set_invariant=True)
        self.assertTrue(result.joint_normalization_valid)
        self.assertFalse(result.mathematically_qualified)

    def test_mathematical_pass_can_fail_engineering_h2(self) -> None:
        result = weights.qualify_weight_enclosures(
            IDS,
            {expert_id: 0.3125 for expert_id in IDS},
            {
                expert_id: v31.Interval(0.3125 - (7.0e-6 if expert_id == 4 else 1.0e-7), 0.3125 + 1.0e-7)
                for expert_id in IDS
            },
            nominal_probability_sum=2.0,
            probability_sum_interval=v31.Interval(2.0, 2.0),
            selected_set_invariant=True,
        )
        self.assertTrue(result.mathematically_qualified)
        self.assertFalse(result.engineering_h2)
        self.assertEqual(result.failed_engineering_ids, (4,))

    def test_invalid_domain_duplicate_ids_and_missing_set_proof_fail_closed(self) -> None:
        nominal, intervals = probability_box(0.2, 0.0)
        with self.assertRaises(weights.WeightQualificationError):
            weights.qualify_probability_box((*IDS[:-1], IDS[-2]), nominal, intervals, selected_set_invariant=True)
        with self.assertRaises(weights.WeightQualificationError):
            weights.qualify_probability_box(IDS, nominal, intervals, selected_set_invariant=False)
        intervals[0] = v31.Interval(-1.0e-6, 0.2)
        with self.assertRaises(weights.WeightQualificationError):
            weights.qualify_probability_box(IDS, nominal, intervals, selected_set_invariant=True)

    def test_nan_inf_and_zero_weight_domains_fail_closed(self) -> None:
        nominal, intervals = probability_box(0.2, 0.0)
        for invalid in (math.nan, math.inf, -math.inf):
            bad = dict(nominal)
            bad[0] = invalid
            with self.assertRaises((weights.WeightQualificationError, v31.TheoremDomainError)):
                weights.qualify_probability_box(IDS, bad, intervals, selected_set_invariant=True)
        direct_intervals = {expert_id: v31.Interval(0.3, 0.33) for expert_id in IDS}
        direct_intervals[0] = v31.Interval(0.0, 0.33)
        with self.assertRaises(weights.WeightQualificationError):
            weights.qualify_weight_enclosures(
                IDS,
                {expert_id: 0.3125 for expert_id in IDS},
                direct_intervals,
                nominal_probability_sum=2.0,
                probability_sum_interval=v31.Interval(2.0, 2.0),
                selected_set_invariant=True,
            )

    def test_inward_interval_mutation_fails_containment(self) -> None:
        nominal = {expert_id: 0.3125 for expert_id in IDS}
        intervals = {expert_id: v31.Interval(0.3125, 0.3125) for expert_id in IDS}
        intervals[2] = v31.Interval(math.nextafter(0.3125, math.inf), 0.33)
        with self.assertRaises(weights.WeightQualificationError):
            weights.qualify_weight_enclosures(
                IDS,
                nominal,
                intervals,
                nominal_probability_sum=2.0,
                probability_sum_interval=v31.Interval(2.0, 2.0),
                selected_set_invariant=True,
            )

    def test_radius_is_rounded_outward_beyond_naive_round_to_nearest(self) -> None:
        nominal = 0.3125
        interval = v31.Interval(nominal - 1.0e-7, nominal + 2.0e-7)
        naive = max(nominal - interval.lower, interval.upper - nominal)
        result = weights.qualify_weight_enclosures(
            IDS,
            {expert_id: nominal for expert_id in IDS},
            {
                expert_id: interval if expert_id == 5 else v31.Interval(nominal, nominal)
                for expert_id in IDS
            },
            nominal_probability_sum=2.0,
            probability_sum_interval=v31.Interval(2.0, 2.0),
            selected_set_invariant=True,
        )
        self.assertGreater(result.by_expert_id[5].outward_absolute_radius, naive)

    def test_sampled_probability_boxes_are_contained(self) -> None:
        rng = random.Random(1705)
        for _ in range(30):
            nominal = {expert_id: rng.uniform(0.02, 0.8) for expert_id in IDS}
            intervals = {
                expert_id: v31.Interval(max(1.0e-12, value - 1.0e-5), min(1.0, value + 1.0e-5))
                for expert_id, value in nominal.items()
            }
            result = weights.qualify_probability_box(IDS, nominal, intervals, selected_set_invariant=True)
            for _sample in range(30):
                probabilities = {
                    expert_id: rng.uniform(interval.lower, interval.upper)
                    for expert_id, interval in intervals.items()
                }
                denominator = max(math.fsum(probabilities.values()), weights.DENOMINATOR_FLOOR)
                for expert_id in IDS:
                    actual = weights.ROUTING_WEIGHT_SCALE * probabilities[expert_id] / denominator
                    self.assertTrue(result.by_expert_id[expert_id].interval.contains(actual))
                # The contract's joint conservation statement is the exact
                # common-denominator model expression, not an implementation's
                # independently rounded sum of eight materialized weights.
                actual_sum = weights.ROUTING_WEIGHT_SCALE * math.fsum(probabilities.values()) / denominator
                self.assertTrue(result.joint_weight_sum_interval.contains(actual_sum))

    def test_deterministic_replay(self) -> None:
        nominal, intervals = probability_box(0.2, 1.0e-8)
        first = weights.qualify_probability_box(IDS, nominal, intervals, selected_set_invariant=True)
        second = weights.qualify_probability_box(IDS, nominal, intervals, selected_set_invariant=True)
        first_bytes = weights.canonical_json_bytes(weights.result_to_dict(first))
        second_bytes = weights.canonical_json_bytes(weights.result_to_dict(second))
        self.assertEqual(first_bytes, second_bytes)
        self.assertEqual(hashlib.sha256(first_bytes).hexdigest(), hashlib.sha256(second_bytes).hexdigest())

    def test_result_serialization_is_id_keyed_and_complete(self) -> None:
        nominal, intervals = probability_box(0.2, 1.0e-8)
        result = weights.qualify_probability_box(IDS, nominal, intervals, selected_set_invariant=True)
        payload = weights.result_to_dict(result)
        self.assertEqual(list(payload["by_expert_id"]), [str(expert_id) for expert_id in IDS])
        self.assertEqual(len(json.loads(weights.canonical_json_bytes(payload))), len(payload))


if __name__ == "__main__":
    unittest.main()
