"""Hand-derived CPU controls for the Studio018 evidence-only reconstruction."""
from fractions import Fraction as F
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio018_routing as diag


class CustodyControls(unittest.TestCase):
    def test_read_bound_requires_original_file_and_digest(self):
        sha = 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            item = root / 'evidence'
            item.write_bytes(b'abc')
            (root / 'alias').symlink_to(item)
            with diag.directory(root) as fd:
                self.assertEqual(diag.read_bound(fd, 'evidence', 3, sha), b'abc')
                with self.assertRaises(ValueError):
                    diag.read_bound(fd, 'evidence', 2, sha)
                with self.assertRaises(OSError):
                    diag.read_bound(fd, 'alias', 3, sha)
                item.write_bytes(b'abd')
                with self.assertRaises(ValueError):
                    diag.read_bound(fd, 'evidence', 3, sha)


class CorrectedScoreControls(unittest.TestCase):
    def test_negative_scores_use_absolute_radius(self):
        result = diag.route([-2.0, -1.0], 1)
        self.assertEqual(list(result['ranked_ids']), [1, 0])
        self.assertEqual((result['selected_boundary'], result['unselected_boundary']), (1, 0))
        self.assertEqual(result['observed_gap'], 1)
        # Radii at -1 and -2 are 44 and 48 millionths, respectively.
        self.assertEqual(result['conservative_gap'], F(249977, 250000))
        self.assertIs(result['eligible'], True)

    def test_signed_zero_tie_has_deterministic_ids_but_no_stable_cut(self):
        result = diag.route([-0.0, 0.0, -1.0], 1)
        self.assertEqual(list(result['ranked_ids']), [0, 1, 2])
        self.assertEqual(result['observed_gap'], 0)
        self.assertEqual(result['conservative_gap'], -F(1, 12500))
        self.assertIs(result['eligible'], False)

    def test_membership_accepts_permutation_and_rejects_wrong_expert(self):
        route = diag.route([0.0, 2.0, 4.0, -3.0], 2)
        expected = route['selected_ids']
        self.assertEqual(list(expected), [2, 1])
        diag.compare_membership([1, 2], expected, 4)
        for selected in ([1, 3], [1, 1], [-1, 2], [2, 4], [2], [True, 2]):
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                diag.compare_membership(selected, expected, 4)

    def test_nonfinite_scores_and_invalid_cut_rejected(self):
        for bad in (math.nan, math.inf, -math.inf):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                diag.route([0.0, bad], 1)
        for k in (0, 2):
            with self.subTest(k=k), self.assertRaises(ValueError):
                diag.route([0.0, 1.0], k)

    def test_upstream_adjacent_bf16_activation_changes_route(self):
        # Three-component input [x, 1, 1/256], fixed rows [1,-1,-1] and [0,0,0].
        # The two dot products compare +/-1/256 with zero. The score gap exceeds
        # 0.0009 on either side, larger than the sum of both local radii.
        def corrected(x):
            dot = x - 1.0 - 1.0 / 256
            return [diag.f32(1 / (1 + math.exp(-dot))), 0.5]

        earlier = diag.route(corrected(1.0), 1)
        matched = diag.route(corrected(1.0), 1)
        adjacent = diag.route(corrected(129 / 128), 1)
        self.assertEqual(list(earlier['selected_ids']), [1])
        self.assertEqual(matched, earlier)
        self.assertEqual(list(adjacent['selected_ids']), [0])
        for result in (earlier, adjacent):
            self.assertGreater(result['observed_gap'], F(9, 10000))
            self.assertIs(result['eligible'], True)


class IntervalControls(unittest.TestCase):
    def test_strict_touch_and_neighbors(self):
        radius = lambda _: F(1, 4)
        # The two intervals touch at 1/4; separated or overlapped by 1/64 either side.
        for center, expected, eligible in ((F(31, 64), -F(1, 64), False),
                                            (F(1, 2), F(0), False),
                                            (F(33, 64), F(1, 64), True)):
            with self.subTest(center=center):
                left, right, gap = diag.interval_gap([center], [F(0)], radius)
                self.assertEqual((left, right, gap), (0, 0, expected))
                self.assertIs(gap > 0, eligible)

    def test_interval_extrema_may_differ_from_center_cut(self):
        def radius(center):
            return F(2) if center in (0, 3) else F(0)

        # Selected lows [1,2] and unselected highs [1,2] force indices (0,1);
        # subtracting the two center-boundary intervals alone would instead give +1.
        self.assertEqual(diag.interval_gap([F(3), F(2)], [F(1), F(0)], radius),
                         (0, 1, F(-1)))


class BiasAndWeightControls(unittest.TestCase):
    def test_same_sigmoids_with_different_fixed_bias_change_membership(self):
        sigmoids = [F(3, 4), F(1, 4)]
        original = [diag.f32(float(p)) for p in sigmoids]
        changed = [diag.f32(float(p + b)) for p, b in zip(sigmoids, [F(-1), F(0)])]
        self.assertEqual(changed, [-0.25, 0.25])
        self.assertEqual(list(diag.route(original, 1)['selected_ids']), [0])
        self.assertEqual(list(diag.route(changed, 1)['selected_ids']), [1])

    def test_subtraction_cancellation_and_fp32_midpoint_add(self):
        # All operands below are exactly binary32. Addition after near cancellation
        # gives one small representable difference, not input-sized absolute error.
        self.assertEqual(diag.f32((0.5 + 2**-24) - 0.5), 2**-24)
        # At 2^23 the upward spacing is 1. The exact half-step rounds to even;
        # one extra exactly representable bit tips that same addition up to 2^23+1.
        bias = float(2**23)
        self.assertEqual(diag.f32(bias + 0.5), bias)
        self.assertEqual(diag.f32(bias + (0.5 + 2**-24)), bias + 1)
        self.assertEqual(diag.f32(bias + 0.25), bias)

    def test_distinct_raw_and_bias_vectors_share_both_observables(self):
        # A common rescaling preserves the selected-sigmoid proportions. A different
        # fixed bias per scenario keeps the entire corrected vector identical.
        cases = (([F(3, 8), F(1, 8), F(1, 16)], [F(1, 8), F(5, 8), F(1, 16)]),
                 ([F(3, 16), F(1, 16), F(1, 32)], [F(5, 16), F(11, 16), F(3, 32)]))
        raw_logits = []
        for sigmoid, bias in cases:
            raw_logits.append([math.log(float(p / (1-p))) for p in sigmoid])
            corrected = [diag.f32(float(p+b)) for p,b in zip(sigmoid, bias)]
            route = diag.route(corrected, 2)
            ids = route['selected_ids']
            self.assertEqual(corrected, [0.5, 0.75, 0.125])
            self.assertEqual(list(ids), [1, 0])
            total = diag.f32(float(sum(sigmoid[i] for i in ids)))
            normalized = [diag.f32(float(sigmoid[i]) / total) for i in ids]
            scaled = [diag.f32(2.5 * q) for q in normalized]
            # Both normalizations and the final scaling are dyadic and exact.
            self.assertEqual(scaled, [5/8, 15/8])
        self.assertNotEqual(raw_logits[0], raw_logits[1])


    def test_inverse_normalized_proportion_has_directed_cell_at_quarter(self):
        # Output 5/8 can arise only from the binary32 normalized value 1/4.
        # Neighbors of 1/4 are 1/4 - 2^-26 and 1/4 + 2^-25, so its inverse
        # division-rounding cell has unequal lower and upper half widths.
        self.assertEqual(diag.selected_proportion_bounds(5/8),
                         (F(1,4) - F(1,2**27), F(1,4) + F(1,2**26)))
        self.assertEqual(diag.selected_proportion_bounds(15/8),
                         (F(3,4) - F(1,2**25), F(3,4) + F(1,2**25)))

    def test_division_then_routed_scaling_differs_from_one_ideal_round(self):
        # Two selected probabilities of 1/4 and 1/2 give D=3/4 exactly.
        # Binary32 division of 1/4 by D rounds up to 11184811 / 2^25.
        denominator = diag.f32(0.25 + 0.5)
        normalized = diag.f32(0.25 / denominator)
        self.assertEqual(normalized, 11184811 / 2**25)
        staged = diag.f32(normalized * 2.5)
        once = diag.f32(float(F(5,6)))
        self.assertEqual(staged, 13981014 / 2**24)
        self.assertEqual(once, 13981013 / 2**24)
        lower, upper = diag.selected_proportion_bounds(staged)
        self.assertEqual((lower, upper), (F(22369621,2**26), F(22369623,2**26)))
        self.assertLess(lower, F(1,3))
        self.assertLess(F(1,3), upper)
        self.assertLess(diag.selected_proportion_bounds(once)[1], F(1,3))


class VocabularyControls(unittest.TestCase):
    def test_power_of_two_has_asymmetric_bf16_neighbors_and_strict_touch(self):
        # The BF16 predecessor of 1 is 255/256; successor is 129/128.
        # The upper neighbor of 127/128 is also 255/256, so the intervals touch.
        result = diag.bf_margin([1.0, 127/128, 0.0])
        self.assertEqual((result['winner'], result['runner_up']), (0, 1))
        self.assertEqual(result['margin'], F(1,128))
        self.assertEqual(result['conservative_gap'], 0)
        self.assertIs(result['eligible'], False)

        negative = diag.bf_margin([-1.0, -131/128])
        self.assertEqual(negative['margin'], F(3,128))
        self.assertEqual(negative['conservative_gap'], F(1,128))
        self.assertIs(negative['eligible'], True)

    def test_zero_neighbors_and_tie_order(self):
        result = diag.bf_margin([-0.0, 0.0])
        self.assertEqual((result['winner'], result['runner_up']), (0, 1))
        self.assertEqual(result['margin'], 0)
        self.assertEqual(result['conservative_gap'], -F(1, 2**132))
        self.assertIs(result['eligible'], False)

    def test_nonfinite_or_non_bf16_carrier_rejected(self):
        for bad in (math.nan, math.inf, -math.inf, 1+2**-16):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                diag.bf_margin([0.0, bad])


if __name__ == '__main__':
    unittest.main()
