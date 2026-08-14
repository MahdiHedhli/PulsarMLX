from __future__ import annotations

import importlib.util
import json
import math
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def load():
    path = ROOT / "scripts/research/f017_route_stability_v2.py"
    spec = importlib.util.spec_from_file_location("f017_route_stability_v2", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves the defining module through sys.modules.
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


V2 = load()


def load_v2_estimator():
    path = ROOT / "scripts/research/estimate_f017_m1f0_qualification_rate_v2.py"
    spec = importlib.util.spec_from_file_location("f017_route_stability_v2_estimator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ESTIMATOR = load_v2_estimator()


def load_fixture_research():
    path = ROOT / "scripts/research/generate_f017_m1f0_representative_fixture.py"
    spec = importlib.util.spec_from_file_location("f017_representative_fixture", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FIXTURES = load_fixture_research()


def load_scalar():
    path = ROOT / "scripts/research/f017_route_stability_v2_scalar.py"
    spec = importlib.util.spec_from_file_location("f017_route_stability_v2_scalar", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCALAR = load_scalar()


def case(logit_i=0.2, logit_j=-0.1, row_i=(1.0, -0.5), row_j=(0.8, -0.3)):
    return V2.PairwiseInputs(
        logit_i=logit_i,
        logit_j=logit_j,
        row_i=row_i,
        row_j=row_j,
        lambda_bound=1e-3,
        residual_bounds=(2e-3, 3e-3),
        reduction_i=1e-4,
        reduction_j=1.2e-4,
        import_i=1e-6,
        import_j=2e-6,
    )


class RouteStabilityV2Tests(unittest.TestCase):
    def test_contract_is_candidate_and_preserves_v1(self):
        contract = json.loads((ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-m1f-route-stability-v2-candidate.json").read_text())
        self.assertEqual(contract["status"], "DRAFT_PENDING_INDEPENDENT_ADVERSARIAL_REVIEW")
        self.assertEqual(contract["v1_compatibility"]["v1_sha256"], "da05364470f7fc5fbdc930441be1ea269af01b6a87173df34e467bcc0b0df9d7")
        self.assertEqual(contract["classification"]["M1F_admission_requires"], "ENGINEERING_HEADROOM")

    def test_primary_and_independent_scalar_implementations_match(self):
        value = case()
        self.assertEqual(V2.pairwise_bound_primary(value)["B_pair"], V2.pairwise_bound_scalar(value))
        self.assertEqual(V2.pairwise_bound_primary(value)["B_pair"], SCALAR.calculate(value.__dict__))

    def test_bound_covers_extreme_corners_and_shared_radial_error(self):
        for value in (
            case(),
            case(logit_i=12.0, logit_j=11.9),
            case(logit_i=-12.0, logit_j=-11.9),
            case(logit_i=0.0, logit_j=math.nextafter(0.0, 1.0)),
            case(row_i=(1.0, 1.0), row_j=(1.0, 1.0)),
            case(row_i=(1.0, -1.0), row_j=(-1.0, 1.0)),
        ):
            bound = V2.pairwise_bound_primary(value)["B_pair"]
            for lam in (-value.lambda_bound, value.lambda_bound):
                for signs in ((-1.0, -1.0), (-1.0, 1.0), (1.0, -1.0), (1.0, 1.0)):
                    residual = [sign * magnitude for sign, magnitude in zip(signs, value.residual_bounds, strict=True)]
                    actual = V2.exact_pair_delta(
                        value, lam, residual,
                        value.reduction_i + value.import_i,
                        -(value.reduction_j + value.import_j),
                    )
                    self.assertLessEqual(actual, bound)

    def test_local_sigmoid_interval_handles_maximum_and_saturation(self):
        near_zero = V2.derivative_interval(-0.1, 0.1)
        saturated = V2.derivative_interval(10.0, 12.0)
        self.assertGreaterEqual(near_zero[1], 0.25)
        self.assertLess(saturated[1], 0.001)
        self.assertLessEqual(saturated[0], saturated[1])

    def test_non_finite_and_shape_errors_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "non-finite"):
            V2.pairwise_bound_primary(case(logit_i=math.nan))
        with self.assertRaisesRegex(ValueError, "shape"):
            V2.pairwise_bound_primary(V2.PairwiseInputs(0.0, 0.0, (1.0,), (1.0, 2.0), 0.0, (0.0,), 0.0, 0.0))

    def test_full_set_checks_all_unselected_not_only_rank_nine(self):
        scores = [1.0, 0.9, 0.89, 0.1]
        selected = [0, 1]
        bounds = {(i, j): 0.01 for i in selected for j in (2, 3)}
        self.assertTrue(V2.full_set_stable(scores, selected, bounds)[0])
        # Rank 3 is the highest unselected, but a row-specific loose bound on
        # rank 4 still invalidates a proof that only inspects the cutoff pair.
        bounds[(1, 3)] = 0.9
        stable, pair, _ = V2.full_set_stable(scores, selected, bounds)
        self.assertFalse(stable)
        self.assertEqual(pair, (1, 3))

    def test_high_precision_sigmoid_contains_binary64_value(self):
        for item in (-20.0, -1.0, 0.0, 1.0, 20.0):
            high = V2.high_precision_sigmoid(item)
            self.assertLessEqual(abs(float(high) - V2.sigmoid(item)), 2e-16)

    def test_randomized_stress_has_no_under_bound(self):
        result = V2.stress(sample_count=5_000, seed=12345)
        self.assertEqual(result["under_bound_count"], 0)
        self.assertEqual(result["independent_implementation_mismatches"], 0)

    def test_v2_estimator_is_bound_to_ladder_and_fails_closed_without_antecedents(self):
        result = ESTIMATOR.simulate(ROOT, sample_count=2_048, seed=4567)
        self.assertEqual(result["v2_contract_sha256"], "fd300f061307442c56af9ca3183f7485544ecb11752755074a330bb7b5f5f68c")
        self.assertEqual(result["methodology"], "PAIRWISE_ANTECEDENTS_UNAVAILABLE_FALLBACK_V1")
        self.assertEqual(result["ladder_sha256"], "59c55a26d12ff9e0fdbe488608c4cb7ffb1a2082d322dec85ee5ef37719c3ed2")
        self.assertFalse(result["real_ladder_execution_authorized"])

    def test_representative_fixture_research_is_deterministic_and_checkpoint_free(self):
        first = FIXTURES.describe()
        second = FIXTURES.describe()
        self.assertEqual(first, second)
        self.assertEqual(first["checkpoint_access"], 0)
        self.assertEqual(first["status"], "RESEARCH_ONLY_NOT_SELECTED_NOT_AUTHORIZED")
        for family in first["families"].values():
            self.assertEqual(family["shape"], [6144])
            self.assertAlmostEqual(family["rms"], 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
