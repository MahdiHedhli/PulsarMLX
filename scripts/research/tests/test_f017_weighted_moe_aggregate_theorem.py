from __future__ import annotations

import hashlib
import math
import random
import unittest

from scripts.research import f017_routing_contract_v31 as v31
from scripts.research import f017_weighted_moe_aggregate_theorem as aggregate


IDS = tuple(range(8))


def weights_box(radius: float) -> tuple[dict[int, float], dict[int, v31.Interval]]:
    nominal = {expert_id: 0.3125 for expert_id in IDS}
    intervals = {
        expert_id: v31.Interval(0.3125 - radius, 0.3125 + radius)
        for expert_id in IDS
    }
    return nominal, intervals


def outputs(*rows: tuple[float, ...]) -> dict[int, tuple[float, ...]]:
    return {expert_id: rows[expert_id] for expert_id in IDS}


def fixed_output_intervals(
    values: dict[int, tuple[float, ...]],
) -> dict[int, tuple[v31.Interval, ...]]:
    return {
        expert_id: tuple(v31.Interval(value, value) for value in row)
        for expert_id, row in values.items()
    }


class WeightedMoeAggregateTheoremTests(unittest.TestCase):
    def evaluate(
        self,
        nominal_outputs: dict[int, tuple[float, ...]],
        *,
        weight_radius: float = 1.0e-7,
        joint_sum: v31.Interval = v31.Interval(2.5, 2.5),
        output_intervals: dict[int, tuple[v31.Interval, ...]] | None = None,
    ) -> aggregate.AggregateQualification:
        nominal_weights, weight_intervals = weights_box(weight_radius)
        return aggregate.qualify_weighted_aggregate(
            IDS,
            nominal_weights,
            weight_intervals,
            nominal_outputs,
            output_intervals=output_intervals,
            joint_weight_sum_interval=joint_sum,
        )

    def test_zero_weight_uncertainty_is_qualified(self) -> None:
        values = outputs(*((1.0, -2.0, 3.0) for _ in IDS))
        result = self.evaluate(values, weight_radius=0.0)
        self.assertTrue(result.mathematically_qualified)
        self.assertTrue(result.engineering_h2)
        payload = aggregate.result_to_dict(result)
        aggregate.canonical_json_bytes(payload)
        self.assertEqual(payload["aggregate_safety_factor"], "INFINITY")

    def test_zero_expert_outputs_have_zero_scale_bound_but_undefined_cosine(self) -> None:
        values = outputs(*((0.0, 0.0) for _ in IDS))
        result = self.evaluate(values, weight_radius=0.1)
        self.assertLess(result.max_absolute_bound, 1.0e-300)
        self.assertIsNone(result.cosine_lower_bound)
        self.assertFalse(result.mathematically_qualified)

    def test_identical_outputs_use_joint_normalization(self) -> None:
        values = outputs(*((100.0, -50.0) for _ in IDS))
        result = self.evaluate(values, weight_radius=0.01)
        self.assertLess(result.max_absolute_bound, 1.0e-10)
        self.assertLess(
            result.component_bounds[0].centered.width,
            result.component_bounds[0].direct.width,
        )

    def test_equal_weight_normalization_preserving_perturbation_is_contained(self) -> None:
        values = outputs(*((float(i), -float(i)) for i in IDS))
        result = self.evaluate(values, weight_radius=0.01)
        delta = 0.005
        weights = [0.3125 + (delta if i % 2 == 0 else -delta) for i in IDS]
        actual = [
            math.fsum((weights[i] - 0.3125) * values[i][column] for i in IDS)
            for column in range(2)
        ]
        for value, bound in zip(actual, result.component_bounds, strict=True):
            self.assertTrue(bound.enclosure.contains(value))

    def test_positive_mixed_sign_and_cancellation_heavy_outputs(self) -> None:
        fixtures = (
            outputs(*((1.0, 2.0) for _ in IDS)),
            outputs(*(((1.0 if i % 2 else -1.0), float(i - 4)) for i in IDS)),
            outputs(*(((1.0e8 if i % 2 else -1.0e8), 1.0e-8) for i in IDS)),
        )
        for values in fixtures:
            result = self.evaluate(values, weight_radius=1.0e-8)
            self.assertEqual(len(result.component_bounds), 2)
            self.assertTrue(all(bound.enclosure.lower <= bound.enclosure.upper for bound in result.component_bounds))

    def test_one_dominant_expert_and_all_eight_active(self) -> None:
        values = outputs(*(((100.0, 0.0) if i == 3 else (0.01, float(i))) for i in IDS))
        result = self.evaluate(values, weight_radius=1.0e-6)
        self.assertEqual(result.expert_count, 8)
        self.assertGreater(result.max_absolute_bound, 0.0)

    def test_componentwise_worst_case_and_linf_containment(self) -> None:
        values = outputs(*(((i + 1.0), -(i + 1.0), 0.5 * i) for i in IDS))
        result = self.evaluate(values, weight_radius=0.002)
        choices = [0.3105 if i % 2 else 0.3145 for i in IDS]
        for column in range(3):
            actual = math.fsum(
                (choices[i] - 0.3125) * values[i][column] for i in IDS
            )
            self.assertTrue(result.component_bounds[column].enclosure.contains(actual))
            self.assertLessEqual(abs(actual), result.max_absolute_bound)

    def test_centering_materially_tightens_common_mode(self) -> None:
        values = outputs(*(((1000.0 + i * 1.0e-3),) for i in IDS))
        result = self.evaluate(values, weight_radius=0.01)
        component = result.component_bounds[0]
        self.assertLess(component.centered.width * 1000.0, component.direct.width)

    def test_mathematical_pass_and_fail(self) -> None:
        values = outputs(*(((1.0 + 0.01 * i), 2.0 - 0.01 * i) for i in IDS))
        self.assertTrue(self.evaluate(values, weight_radius=1.0e-7).mathematically_qualified)
        self.assertFalse(self.evaluate(values, weight_radius=0.1).mathematically_qualified)

    def test_mathematical_pass_can_fail_engineering_h2(self) -> None:
        values = outputs(*(((101.0 if i == 0 else 100.0), 100.0) for i in IDS))
        result = self.evaluate(
            values,
            weight_radius=0.0015,
            joint_sum=v31.Interval(2.5, 2.5),
        )
        self.assertTrue(result.mathematically_qualified)
        self.assertFalse(result.engineering_h2)

    def test_nominal_and_outward_normalization_enclosures(self) -> None:
        values = outputs(*(((1.0 + i), -1.0) for i in IDS))
        exact = self.evaluate(values, joint_sum=v31.Interval(2.5, 2.5))
        outward = self.evaluate(
            values,
            joint_sum=v31.Interval(2.4999999999999996, 2.5000000000000004),
        )
        self.assertLessEqual(exact.max_absolute_bound, outward.max_absolute_bound)

    def test_joint_weight_and_output_uncertainty_complete_decomposition(self) -> None:
        values = outputs(*(((float(i), -float(i)),) [0] for i in IDS))
        intervals = fixed_output_intervals(values)
        intervals[4] = (
            v31.Interval(values[4][0] - 0.01, values[4][0] + 0.01),
            v31.Interval(values[4][1] - 0.02, values[4][1] + 0.02),
        )
        result = self.evaluate(values, output_intervals=intervals)
        q = {i: 0.3125 + (5.0e-8 if i % 2 else -5.0e-8) for i in IDS}
        sampled = {i: list(values[i]) for i in IDS}
        sampled[4] = [values[4][0] + 0.005, values[4][1] - 0.01]
        for column, component in enumerate(result.component_bounds):
            actual = math.fsum(q[i] * sampled[i][column] for i in IDS) - math.fsum(
                0.3125 * values[i][column] for i in IDS
            )
            self.assertTrue(component.enclosure.contains(actual))

    def test_zero_width_nominal_output_at_interval_boundary(self) -> None:
        values = outputs(*(((float(i),),) [0] for i in IDS))
        intervals = fixed_output_intervals(values)
        result = self.evaluate(values, output_intervals=intervals, weight_radius=0.0)
        self.assertTrue(result.mathematically_qualified)

    def test_invalid_nan_inf_duplicate_and_missing_output_fail_closed(self) -> None:
        values = outputs(*(((float(i),),) [0] for i in IDS))
        with self.assertRaises(aggregate.AggregateTheoremError):
            aggregate.qualify_weighted_aggregate(
                (*IDS[:-1], IDS[-2]), *weights_box(0.0), values,
                joint_weight_sum_interval=v31.Interval(2.5, 2.5),
            )
        for bad in (math.nan, math.inf, -math.inf):
            broken = dict(values)
            broken[0] = (bad,)
            with self.assertRaises(aggregate.AggregateTheoremError):
                self.evaluate(broken)
        missing = dict(values)
        del missing[7]
        with self.assertRaises(aggregate.AggregateTheoremError):
            self.evaluate(missing)

    def test_missing_or_misaligned_output_bounds_fail_closed(self) -> None:
        values = outputs(*(((float(i), float(i + 1)),) [0] for i in IDS))
        intervals = fixed_output_intervals(values)
        del intervals[6]
        with self.assertRaises(aggregate.AggregateTheoremError):
            self.evaluate(values, output_intervals=intervals)
        intervals = fixed_output_intervals(values)
        intervals[6] = intervals[6][:-1]
        with self.assertRaises(aggregate.AggregateTheoremError):
            self.evaluate(values, output_intervals=intervals)

    def test_outward_rounding_expands_naive_bound(self) -> None:
        values = outputs(*(((1.0 + i / 10.0,),) [0] for i in IDS))
        result = self.evaluate(values, weight_radius=1.0e-7)
        reference = (min(values[i][0] for i in IDS) + max(values[i][0] for i in IDS)) / 2.0
        naive = sum(1.0e-7 * abs(values[i][0] - reference) for i in IDS)
        self.assertGreater(result.component_bounds[0].radius, naive)

    def test_mutating_away_centering_guard_loses_containment(self) -> None:
        values = outputs(*(((100.0 + i,),) [0] for i in IDS))
        result = self.evaluate(
            values,
            weight_radius=0.01,
            joint_sum=v31.Interval(2.49, 2.51),
        )
        component = result.component_bounds[0]
        self.assertGreater(component.centered_common_mode_radius, 0.0)
        self.assertGreater(component.radius, component.centered_deviation_radius)

    def test_random_admissible_boxes_are_contained(self) -> None:
        rng = random.Random(1707)
        for _ in range(40):
            dimension = 4
            values = {
                expert_id: tuple(rng.uniform(-3.0, 3.0) for _ in range(dimension))
                for expert_id in IDS
            }
            nominal_weights, weight_intervals = weights_box(1.0e-3)
            result = aggregate.qualify_weighted_aggregate(
                IDS,
                nominal_weights,
                weight_intervals,
                values,
                joint_weight_sum_interval=v31.Interval(2.49, 2.51),
            )
            for _sample in range(20):
                deltas = [rng.uniform(-1.0e-3, 1.0e-3) for _ in IDS]
                correction = sum(deltas) / len(deltas)
                deltas = [delta - correction for delta in deltas]
                for column in range(dimension):
                    actual = math.fsum(deltas[i] * values[i][column] for i in IDS)
                    self.assertTrue(result.component_bounds[column].enclosure.contains(actual))

    def test_result_is_deterministic_and_id_keyed(self) -> None:
        values = outputs(*(((float(i), -float(i)),) [0] for i in IDS))
        first = self.evaluate(values)
        second = self.evaluate(values)
        first_bytes = aggregate.canonical_json_bytes(aggregate.result_to_dict(first))
        second_bytes = aggregate.canonical_json_bytes(aggregate.result_to_dict(second))
        self.assertEqual(first_bytes, second_bytes)
        self.assertEqual(hashlib.sha256(first_bytes).hexdigest(), hashlib.sha256(second_bytes).hexdigest())
        self.assertEqual(first.expert_ids, IDS)

    def test_production_wrapper_requires_set_invariance_and_width_6144(self) -> None:
        nominal_weights, weight_intervals = weights_box(0.0)
        short = outputs(*(((float(i),),) [0] for i in IDS))
        with self.assertRaises(aggregate.AggregateTheoremError):
            aggregate.qualify_f017_production_aggregate(
                IDS,
                nominal_weights,
                weight_intervals,
                short,
                selected_set_invariant=True,
                joint_weight_sum_interval=v31.Interval(2.5, 2.5),
            )
        with self.assertRaises(aggregate.AggregateTheoremError):
            aggregate.qualify_f017_production_aggregate(
                IDS,
                nominal_weights,
                weight_intervals,
                short,
                selected_set_invariant=False,
                joint_weight_sum_interval=v31.Interval(2.5, 2.5),
            )

    def test_production_wrapper_accepts_exact_synthetic_width(self) -> None:
        nominal_weights, weight_intervals = weights_box(0.0)
        values = outputs(*((tuple(1.0 + i * 0.01 for _ in range(6144))) for i in IDS))
        result = aggregate.qualify_f017_production_aggregate(
            IDS,
            nominal_weights,
            weight_intervals,
            values,
            selected_set_invariant=True,
            joint_weight_sum_interval=v31.Interval(2.5, 2.5),
        )
        self.assertEqual(result.dimension, 6144)
        self.assertTrue(result.mathematically_qualified)


if __name__ == "__main__":
    unittest.main()
