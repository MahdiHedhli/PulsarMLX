from __future__ import annotations

import math
import random
import unittest

from scripts.research import f017_complete_layer_aggregate_acceptance_v2 as v2
from scripts.research import f017_routing_contract_v31 as v31


class CompleteLayerAggregateV2Tests(unittest.TestCase):
    def evaluate(self, residual, shared, routed, radius=1e-6, shared_intervals=None):
        return v2.qualify_complete_layer(
            residual,
            shared,
            routed,
            [v31.Interval(-radius, radius) for _ in residual],
            shared_intervals=shared_intervals,
        )

    def test_final_threshold_family_is_exact(self):
        self.assertEqual(v2.MAX_ABSOLUTE_BUDGET, 0.0625)
        self.assertEqual(v2.RMSE_BUDGET, 0.03125)
        self.assertEqual(v2.COSINE_MINIMUM, 0.999)
        self.assertNotEqual(v2.COSINE_MINIMUM, 0.9999)

    def test_zero_perturbation_is_exact_and_deterministic(self):
        first = self.evaluate([2.0, -3.0], [1.0, 1.0], [0.5, 0.5], 0.0)
        second = self.evaluate([2.0, -3.0], [1.0, 1.0], [0.5, 0.5], 0.0)
        self.assertEqual(first, second)
        self.assertEqual(first.max_absolute_bound, 0.0)
        self.assertEqual(first.cosine_lower_bound, 1.0)

    def test_residual_dominated_vector(self):
        result = self.evaluate([100.0, -100.0], [0.1, 0.1], [0.1, -0.1], 1e-3)
        self.assertGreater(result.cosine_lower_bound, 0.999)

    def test_small_residual_and_zero_nominal_fail_closed(self):
        self.assertFalse(self.evaluate([1e-9], [0.0], [0.0], 1e-3).mathematically_qualified)
        self.assertIsNone(self.evaluate([0.0], [0.0], [0.0], 1e-3).cosine_lower_bound)

    def test_zero_and_large_shared_expert(self):
        zero = self.evaluate([1.0, 2.0], [0.0, 0.0], [0.2, -0.2], 1e-4)
        large = self.evaluate([1.0, 2.0], [1000.0, -1000.0], [0.2, -0.2], 1e-4)
        self.assertGreaterEqual(large.cosine_lower_bound, zero.cosine_lower_bound)

    def test_mixed_sign_and_exact_addition_order(self):
        result = self.evaluate([-2.0, 3.0], [5.0, -7.0], [-1.0, 2.0], 0.0)
        self.assertEqual(result.nominal, (2.0, -2.0))

    def test_parallel_orthogonal_and_antiparallel_are_contained(self):
        result = self.evaluate([10.0, 0.0], [0.0, 0.0], [0.0, 0.0], 0.1)
        for delta in ((0.1, 0.0), (0.0, 0.1), (-0.1, 0.0)):
            for value, interval in zip(delta, result.perturbations, strict=True):
                self.assertTrue(interval.contains(value))

    def test_cosine_around_final_threshold(self):
        passing = self.evaluate([10.0, 0.0], [0.0, 0.0], [0.0, 0.0], 0.3)
        failing = self.evaluate([1.0, 0.0], [0.0, 0.0], [0.0, 0.0], 0.1)
        self.assertGreater(passing.cosine_lower_bound, 0.999)
        self.assertLess(failing.cosine_lower_bound, 0.999)

    def test_max_absolute_boundary(self):
        below = self.evaluate([100.0], [0.0], [0.0], 0.0624)
        above = self.evaluate([100.0], [0.0], [0.0], 0.0626)
        self.assertLessEqual(below.max_absolute_bound, v2.MAX_ABSOLUTE_BUDGET)
        self.assertGreater(above.max_absolute_bound, v2.MAX_ABSOLUTE_BUDGET)

    def test_rmse_boundary(self):
        below = self.evaluate([100.0, 100.0], [0.0, 0.0], [0.0, 0.0], 0.0311)
        above = self.evaluate([100.0, 100.0], [0.0, 0.0], [0.0, 0.0], 0.0314)
        self.assertLessEqual(below.rmse_bound, v2.RMSE_BUDGET)
        self.assertGreater(above.rmse_bound, v2.RMSE_BUDGET)

    def test_final_f32_cast_boundary_is_enclosed(self):
        result = self.evaluate([0.1], [0.2], [0.3], 1e-7)
        for delta in (-1e-7, 0.0, 1e-7):
            actual = v2.f32(v2.f32(0.1) + ((0.3 + delta) + v2.f32(0.2))) - result.nominal[0]
            self.assertTrue(result.perturbations[0].contains(actual))

    def test_epsilon_approaching_nominal_norm_fails_closed(self):
        result = self.evaluate([1.0], [0.0], [0.0], 1.0)
        self.assertIsNone(result.cosine_lower_bound)
        self.assertFalse(result.mathematically_qualified)

    def test_outward_rounding_is_wider_than_naive(self):
        result = self.evaluate([1.0], [0.0], [0.0], 1e-7)
        self.assertGreater(result.max_absolute_bound, 1e-7)

    def test_residual_double_count_and_wrong_surface_mutations(self):
        correct = self.evaluate([2.0], [3.0], [4.0], 0.0)
        doubled = self.evaluate([4.0], [3.0], [4.0], 0.0)
        routed_only = self.evaluate([0.0], [0.0], [4.0], 0.0)
        self.assertNotEqual(correct.nominal, doubled.nominal)
        self.assertNotEqual(correct.nominal, routed_only.nominal)

    def test_exact_shared_point_and_bounded_shared_are_distinct(self):
        exact = self.evaluate([10.0], [1.0], [0.0], 0.01)
        bounded = self.evaluate(
            [10.0], [1.0], [0.0], 0.01,
            shared_intervals=[v31.Interval(0.9, 1.1)],
        )
        self.assertEqual(exact.shared_uncertainty_mode, "EXACT_CLASS_POINT_DELTA_S_ZERO")
        self.assertEqual(bounded.shared_uncertainty_mode, "BOUNDED_SHARED_INTERVALS_INCLUDED")
        self.assertGreater(bounded.max_absolute_bound, exact.max_absolute_bound)

    def test_geometric_bound_contains_random_samples(self):
        result = self.evaluate([3.0, 4.0], [0.0, 0.0], [0.0, 0.0], 0.01)
        rng = random.Random(17)
        for _ in range(1000):
            delta = [rng.uniform(-0.01, 0.01) for _ in range(2)]
            a = result.nominal
            b = [a[i] + delta[i] for i in range(2)]
            cosine = sum(a[i] * b[i] for i in range(2)) / math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
            self.assertGreaterEqual(cosine, result.cosine_lower_bound)

    def test_invalid_domains_fail_closed(self):
        with self.assertRaises(v2.CompleteLayerTheoremError):
            v2.qualify_complete_layer([1.0], [], [0.0], [v31.Interval(0.0, 0.0)])
        with self.assertRaises(v2.CompleteLayerTheoremError):
            self.evaluate([math.nan], [0.0], [0.0])
        with self.assertRaises(v2.CompleteLayerTheoremError):
            self.evaluate([1.0], [0.0], [0.0], shared_intervals=[v31.Interval(1.0, 2.0)])

    def test_property_containment(self):
        rng = random.Random(1202)
        for _ in range(200):
            residual = [rng.uniform(-10, 10) for _ in range(4)]
            shared = [rng.uniform(-3, 3) for _ in range(4)]
            routed = [rng.uniform(-2, 2) for _ in range(4)]
            radius = rng.uniform(0, 1e-3)
            result = self.evaluate(residual, shared, routed, radius)
            for _ in range(8):
                for index in range(4):
                    delta = rng.uniform(-radius, radius)
                    actual = v2.f32(v2.f32(residual[index]) + ((routed[index] + delta) + v2.f32(shared[index]))) - result.nominal[index]
                    self.assertTrue(result.perturbations[index].contains(actual))


if __name__ == "__main__":
    unittest.main()
