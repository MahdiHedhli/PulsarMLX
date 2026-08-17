from __future__ import annotations

import math
import random
import unittest

from scripts.research.f017_routing_contract_v31 import (
    DENOMINATOR_FLOOR,
    Interval,
    RMS_EPSILON,
    TheoremDomainError,
    interval_add,
    interval_div,
    interval_mul,
    pair_safety,
    propagate_rmsnorm,
    propagate_router_logits,
    propagate_scores,
    round_down,
    round_up,
    select_top_k_diagnostic,
    selected_challenger_difference,
    selected_weight_intervals,
    sigmoid,
    sigmoid_interval,
    square_interval,
    summarize_pair_safety,
)


def nominal_rmsnorm(x: list[float], gamma: list[float]) -> list[float]:
    rms = math.sqrt(math.fsum(value * value for value in x) / len(x) + RMS_EPSILON)
    return [weight * value / rms for weight, value in zip(gamma, x, strict=True)]


class RoutingContractV31Tests(unittest.TestCase):
    def test_zero_width_box_is_tight_and_contains_nominal(self) -> None:
        x = [0.5, -1.25, 2.0]
        gamma = [1.0, -0.5, 0.0]
        result = propagate_rmsnorm(x, [0.0] * 3, gamma)
        nominal = nominal_rmsnorm(x, gamma)
        for interval, value in zip(result.gamma_scaled, nominal, strict=True):
            self.assertTrue(interval.contains(value))
            self.assertLessEqual(interval.upper - interval.lower, 1e-14)

    def test_positive_negative_and_crossing_coordinate_boxes(self) -> None:
        result = propagate_rmsnorm([2.0, -2.0, 0.0], [0.25, 0.25, 0.25], [1.0] * 3)
        self.assertGreater(result.coordinates[0].lower, 0.0)
        self.assertLess(result.coordinates[1].upper, 0.0)
        self.assertEqual(result.squared_coordinates[2].lower, 0.0)

    def test_gamma_positive_negative_and_zero(self) -> None:
        result = propagate_rmsnorm([1.0, 1.0, 1.0], [0.1] * 3, [2.0, -2.0, 0.0])
        self.assertGreater(result.gamma_scaled[0].lower, 0.0)
        self.assertLess(result.gamma_scaled[1].upper, 0.0)
        self.assertTrue(result.gamma_scaled[2].contains(0.0))

    def test_rms_denominator_near_minimum_remains_positive(self) -> None:
        result = propagate_rmsnorm([0.0], [0.0], [1.0], epsilon=1e-300)
        self.assertGreater(result.rms.lower, 0.0)

    def test_invalid_rms_domains_fail_closed(self) -> None:
        for epsilon in (0.0, -1.0, math.nan, math.inf):
            with self.subTest(epsilon=epsilon), self.assertRaises(TheoremDomainError):
                propagate_rmsnorm([1.0], [0.0], [1.0], epsilon=epsilon)
        with self.assertRaises(TheoremDomainError):
            propagate_rmsnorm([1.0], [-0.1], [1.0])

    def test_square_interval_crossing_zero(self) -> None:
        squared = square_interval(Interval(-3.0, 2.0))
        self.assertEqual(squared.lower, 0.0)
        self.assertGreaterEqual(squared.upper, 9.0)

    def test_router_rows_support_positive_negative_weights_and_cancellation(self) -> None:
        y = (Interval(0.9, 1.1), Interval(0.9, 1.1))
        rows = ([1e12, -1e12], [-2.0, 3.0])
        logits = propagate_router_logits(
            y,
            rows,
            logit_bias=[0.0, 0.25],
            reduction_guards=[1e-3, 0.0],
            import_guards=[2e-3, 0.0],
            bias_guards=[0.0, 1e-6],
        )
        self.assertTrue(logits[0].contains(0.0))
        self.assertTrue(logits[1].contains(1.25))

    def test_missing_rounding_guards_fail_closed(self) -> None:
        with self.assertRaisesRegex(TheoremDomainError, "explicit"):
            propagate_router_logits(
                [Interval(1.0, 1.0)],
                [[1.0]],
                logit_bias=None,
                reduction_guards=None,
                import_guards=[0.0],
                bias_guards=[0.0],
            )

    def test_router_shape_mismatch_fails_closed(self) -> None:
        with self.assertRaises(TheoremDomainError):
            propagate_router_logits(
                [Interval(1.0, 1.0)],
                [[1.0, 2.0]],
                logit_bias=None,
                reduction_guards=[0.0],
                import_guards=[0.0],
                bias_guards=[0.0],
            )

    def test_sigmoid_extremes_and_near_zero(self) -> None:
        for value in (-1000.0, -1e-12, 0.0, 1e-12, 1000.0):
            interval = sigmoid_interval(Interval(value, value))
            self.assertTrue(interval.contains(sigmoid(value)))
        self.assertEqual(sigmoid(-1000.0), 0.0)
        self.assertEqual(sigmoid(1000.0), 1.0)

    def test_score_bias_is_post_sigmoid_and_outward(self) -> None:
        result = propagate_scores(
            [Interval(0.0, 0.0)],
            [0.125],
            score_bias_guards=[0.0],
        )
        self.assertTrue(result.probabilities[0].contains(0.5))
        self.assertTrue(result.selection_scores[0].contains(0.625))

    def test_selected_challenger_near_tie_is_not_invariant(self) -> None:
        difference = selected_challenger_difference(Interval(0.5, 0.5001), Interval(0.4999, 0.5002))
        self.assertLessEqual(difference.lower, 0.0)

    def test_clearly_invariant_pair(self) -> None:
        result = pair_safety(3, 9, Interval(0.8, 0.81), Interval(0.1, 0.2), 0.805, 0.15)
        self.assertTrue(result.membership_invariant)
        self.assertTrue(result.mathematical_factor_pass)
        self.assertTrue(result.engineering_h2_pass)

    def test_mathematically_unsafe_pair(self) -> None:
        result = pair_safety(3, 9, Interval(0.4, 0.6), Interval(0.5, 0.7), 0.55, 0.54)
        self.assertFalse(result.membership_invariant)
        self.assertFalse(result.mathematical_factor_pass)

    def test_factor_over_one_but_under_engineering_two(self) -> None:
        result = pair_safety(1, 2, Interval(0.55, 0.61), Interval(0.48, 0.51), 0.60, 0.50)
        self.assertTrue(result.membership_invariant)
        self.assertIsNotNone(result.factor)
        self.assertGreaterEqual(result.factor or 0.0, 1.0)
        self.assertLess(result.factor or 0.0, 2.0)
        self.assertFalse(result.engineering_h2_pass)

    def test_pair_summary_reports_worst_and_counts(self) -> None:
        safe = pair_safety(1, 3, Interval(0.8, 0.9), Interval(0.1, 0.2), 0.85, 0.15)
        unsafe = pair_safety(2, 4, Interval(0.4, 0.5), Interval(0.45, 0.55), 0.48, 0.47)
        summary = summarize_pair_safety([safe, unsafe])
        self.assertEqual(summary["worst_pair"], [2, 4])
        self.assertEqual(summary["count_below_1"], 1)

    def test_fixed_selected_set_weight_normalization_is_id_keyed(self) -> None:
        ids = [9, 1, 7, 3, 5, 11, 13, 15]
        probabilities = {expert_id: Interval(0.1, 0.1) for expert_id in ids}
        weights = selected_weight_intervals(ids, probabilities)
        self.assertEqual(set(weights), set(ids))
        for value in weights.values():
            self.assertTrue(value.contains(2.5 / 8.0))

    def test_selected_weight_denominator_stress(self) -> None:
        ids = list(range(8))
        tiny = DENOMINATOR_FLOOR / 100.0
        probabilities = {expert_id: Interval(tiny, tiny * 2) for expert_id in ids}
        weights = selected_weight_intervals(ids, probabilities)
        self.assertTrue(all(value.lower >= 0.0 for value in weights.values()))

    def test_duplicate_selected_expert_id_rejected(self) -> None:
        with self.assertRaises(TheoremDomainError):
            selected_weight_intervals([0, 1, 2, 3, 4, 5, 6, 6], {i: Interval(0.1, 0.2) for i in range(7)})

    def test_nan_and_inf_rejected_everywhere(self) -> None:
        for invalid in (math.nan, math.inf, -math.inf):
            with self.subTest(invalid=invalid), self.assertRaises(TheoremDomainError):
                Interval(invalid, 1.0)
            with self.subTest(invalid=invalid), self.assertRaises(TheoremDomainError):
                sigmoid(invalid)

    def test_outward_rounding_is_strictly_wider_than_nearest(self) -> None:
        nearest = 0.1 + 0.2
        outward = interval_add(Interval(0.1, 0.1), Interval(0.2, 0.2))
        self.assertLess(outward.lower, nearest)
        self.assertGreater(outward.upper, nearest)
        product = interval_mul(Interval(0.1, 0.1), Interval(0.2, 0.2))
        self.assertLess(product.lower, 0.1 * 0.2)
        self.assertGreater(product.upper, 0.1 * 0.2)

    def test_directed_division_expands_nearest(self) -> None:
        nearest = 1.0 / 3.0
        result = interval_div(Interval(1.0, 1.0), Interval(3.0, 3.0))
        self.assertLess(result.lower, nearest)
        self.assertGreater(result.upper, nearest)

    def test_top_k_tie_uses_lower_id_but_order_is_diagnostic(self) -> None:
        scores = [0.1] * 10
        self.assertEqual(select_top_k_diagnostic(scores), tuple(range(8)))

    def test_random_box_samples_are_inside_rmsnorm_enclosure(self) -> None:
        rng = random.Random(170_311)
        for _ in range(80):
            x0 = [rng.uniform(-3.0, 3.0) for _ in range(4)]
            dx = [rng.uniform(0.0, 0.5) for _ in range(4)]
            gamma = [rng.uniform(-2.0, 2.0) for _ in range(4)]
            enclosure = propagate_rmsnorm(x0, dx, gamma)
            for _ in range(30):
                sample = [center + rng.uniform(-radius, radius) for center, radius in zip(x0, dx, strict=True)]
                actual = nominal_rmsnorm(sample, gamma)
                self.assertTrue(
                    all(interval.contains(value) for interval, value in zip(enclosure.gamma_scaled, actual, strict=True))
                )

    def test_random_router_samples_are_inside_logit_and_score_enclosures(self) -> None:
        rng = random.Random(170_312)
        for _ in range(40):
            x0 = [rng.uniform(-1.0, 1.0) for _ in range(3)]
            dx = [rng.uniform(0.0, 0.2) for _ in range(3)]
            gamma = [rng.uniform(-1.5, 1.5) for _ in range(3)]
            rows = [[rng.uniform(-2.0, 2.0) for _ in range(3)] for _ in range(4)]
            bias = [rng.uniform(-0.2, 0.2) for _ in range(4)]
            rms_box = propagate_rmsnorm(x0, dx, gamma)
            logits = propagate_router_logits(
                rms_box.gamma_scaled,
                rows,
                logit_bias=None,
                reduction_guards=[0.0] * 4,
                import_guards=[0.0] * 4,
                bias_guards=[0.0] * 4,
            )
            scores = propagate_scores(logits, bias, score_bias_guards=[0.0] * 4)
            for _ in range(20):
                sample = [center + rng.uniform(-radius, radius) for center, radius in zip(x0, dx, strict=True)]
                normalized = nominal_rmsnorm(sample, gamma)
                actual_logits = [math.fsum(w * y for w, y in zip(row, normalized, strict=True)) for row in rows]
                actual_scores = [sigmoid(value) + item_bias for value, item_bias in zip(actual_logits, bias, strict=True)]
                self.assertTrue(all(interval.contains(value) for interval, value in zip(logits, actual_logits, strict=True)))
                self.assertTrue(
                    all(interval.contains(value) for interval, value in zip(scores.selection_scores, actual_scores, strict=True))
                )

    def test_interval_constructor_and_arithmetic_fail_on_invalid_domains(self) -> None:
        with self.assertRaises(TheoremDomainError):
            Interval(2.0, 1.0)
        with self.assertRaises(TheoremDomainError):
            interval_div(Interval(1.0, 2.0), Interval(-1.0, 1.0))
        self.assertLess(round_down(1.0), 1.0)
        self.assertGreater(round_up(1.0), 1.0)


if __name__ == "__main__":
    unittest.main()
