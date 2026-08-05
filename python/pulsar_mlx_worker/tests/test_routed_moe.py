"""Contract tests for the bounded synthetic routed-MoE worker fixture.

The expected routes, weights, expert outputs, and final output below are fixed
independently.  They are not computed with MLX or derived from worker output.
"""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import platform
import unittest

from pulsar_mlx_worker.moe import (
    RoutedMoeError,
    run_routed_moe_fixture,
    validate_routed_moe_fixture,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = REPOSITORY_ROOT / "fixtures" / "mlx" / "routed-moe-v1.json"
FIXTURE_ID = "synthetic-routed-moe-v1"

INDEPENDENT_EXPERT_IDS = (1, 2, 3, 1)
INDEPENDENT_WEIGHTS = (
    0.5,
    0.5,
    0.7310585786300048,
    0.2689414213699952,
)
INDEPENDENT_SELECTED_OUTPUTS = (3.0, 2.0, 1.0, 2.0, 5.75, 3.5, -0.5, 5.5)
INDEPENDENT_WEIGHTED_OUTPUT = (2.0, 2.0, 4.06911611643753, 4.03788284273999)


class SchedulingTrap:
    """Fail if a malformed fixture reaches any MLX scheduling surface."""

    def __init__(self) -> None:
        self.access_count = 0

    def __getattr__(self, name: str):
        self.access_count += 1
        raise AssertionError(f"MLX was accessed before validation: {name}")


class RoutedMoeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def assert_moe_error(
        self,
        expected_code: str,
        callable_,
        /,
        *args,
        **kwargs,
    ) -> RoutedMoeError:
        with self.assertRaises(RoutedMoeError) as caught:
            callable_(*args, **kwargs)
        self.assertEqual(caught.exception.code, expected_code)
        self.assertLessEqual(len(caught.exception.message), 512)
        return caught.exception

    def assert_rejected_before_scheduling(
        self,
        expected_code: str,
        fixture: dict[str, object],
        **overrides,
    ) -> None:
        trap = SchedulingTrap()
        arguments = {
            "expected_fixture_id": FIXTURE_ID,
            "requested_device": "gpu",
            "allow_fallback": False,
            "mx_module": trap,
            **overrides,
        }
        self.assert_moe_error(
            expected_code,
            run_routed_moe_fixture,
            fixture,
            **arguments,
        )
        self.assertEqual(
            trap.access_count,
            0,
            "malformed routed-MoE input reached MLX before rejection",
        )

    def test_fixture_freezes_independent_routing_and_aggregation_oracles(self) -> None:
        fixture = self.fixture
        self.assertEqual(fixture["fixture_id"], FIXTURE_ID)
        self.assertEqual(
            tuple(
                expert_id
                for row in fixture["routing_oracle"]["selected_expert_ids"]
                for expert_id in row
            ),
            INDEPENDENT_EXPERT_IDS,
        )
        self.assertEqual(
            tuple(
                weight
                for row in fixture["routing_oracle"]["normalized_weights"]
                for weight in row
            ),
            INDEPENDENT_WEIGHTS,
        )
        self.assertEqual(
            tuple(
                value
                for token in fixture["expert_output_oracle"]["selected_outputs"]
                for expert in token
                for value in expert
            ),
            INDEPENDENT_SELECTED_OUTPUTS,
        )
        self.assertEqual(
            tuple(
                value
                for row in fixture["expert_output_oracle"]["weighted_output"]
                for value in row
            ),
            INDEPENDENT_WEIGHTED_OUTPUT,
        )

    def test_descriptor_admits_repeated_experts_across_tokens(self) -> None:
        descriptor = validate_routed_moe_fixture(
            self.fixture,
            expected_fixture_id=FIXTURE_ID,
        )

        self.assertEqual(descriptor.fixture_id, FIXTURE_ID)
        self.assertEqual(descriptor.token_count, 2)
        self.assertEqual(descriptor.hidden_size, 2)
        self.assertEqual(descriptor.expert_count, 4)
        self.assertEqual(descriptor.top_k, 2)
        self.assertEqual(descriptor.selected_expert_ids, INDEPENDENT_EXPERT_IDS)
        self.assertEqual(descriptor.selected_expert_ids.count(1), 2)
        self.assertEqual(descriptor.unique_expert_ids, (1, 2, 3))

    def test_non_finite_scores_are_rejected_before_scheduling(self) -> None:
        for label, value in (
            ("nan", math.nan),
            ("positive infinity", math.inf),
            ("negative infinity", -math.inf),
        ):
            with self.subTest(label=label):
                malformed = deepcopy(self.fixture)
                malformed["inputs"]["router_scores"][0][3] = value
                self.assert_rejected_before_scheduling(
                    "malformed_request",
                    malformed,
                )

    def test_top_k_and_router_shape_bounds_precede_scheduling(self) -> None:
        zero_top_k = deepcopy(self.fixture)
        zero_top_k["tensor_contract"]["top_k"] = 0
        self.assert_rejected_before_scheduling("invalid_shape", zero_top_k)

        too_many = deepcopy(self.fixture)
        too_many["tensor_contract"]["top_k"] = 5
        self.assert_rejected_before_scheduling("invalid_shape", too_many)

        no_experts = deepcopy(self.fixture)
        no_experts["tensor_contract"]["expert_count"] = 0
        self.assert_rejected_before_scheduling("invalid_shape", no_experts)

        missing_score = deepcopy(self.fixture)
        missing_score["inputs"]["router_scores"][1].pop()
        self.assert_rejected_before_scheduling("invalid_shape", missing_score)

        extra_score_row = deepcopy(self.fixture)
        extra_score_row["inputs"]["router_scores"].append([0.0, 0.0, 0.0, 0.0])
        self.assert_rejected_before_scheduling("invalid_shape", extra_score_row)

    def test_malformed_expert_and_oracle_payloads_precede_scheduling(self) -> None:
        short_matrix = deepcopy(self.fixture)
        short_matrix["experts"][2]["matrix"].pop()
        self.assert_rejected_before_scheduling("invalid_shape", short_matrix)

        out_of_range_expert = deepcopy(self.fixture)
        out_of_range_expert["routing_oracle"]["selected_expert_ids"][0][0] = 4
        self.assert_rejected_before_scheduling(
            "malformed_request",
            out_of_range_expert,
        )

        unnormalized_weights = deepcopy(self.fixture)
        unnormalized_weights["routing_oracle"]["normalized_weights"][0] = [0.4, 0.4]
        self.assert_rejected_before_scheduling(
            "malformed_request",
            unnormalized_weights,
        )

        non_finite_output = deepcopy(self.fixture)
        non_finite_output["expert_output_oracle"]["weighted_output"][1][0] = math.inf
        self.assert_rejected_before_scheduling(
            "malformed_request",
            non_finite_output,
        )

    def test_explicit_gpu_and_no_fallback_are_required_before_scheduling(self) -> None:
        self.assert_rejected_before_scheduling(
            "device_unavailable",
            deepcopy(self.fixture),
            requested_device="cpu",
        )
        self.assert_rejected_before_scheduling(
            "device_unavailable",
            deepcopy(self.fixture),
            allow_fallback=True,
        )

    @unittest.skipUnless(
        platform.system() == "Darwin" and platform.machine() == "arm64",
        "evaluated routed-MoE fixture execution requires native Apple Silicon",
    )
    def test_evaluated_routes_weights_and_aggregation_match_independent_oracles(
        self,
    ) -> None:
        result = run_routed_moe_fixture(
            self.fixture,
            expected_fixture_id=FIXTURE_ID,
            requested_device="gpu",
            allow_fallback=False,
        )

        self.assertEqual(result.fixture_id, FIXTURE_ID)
        self.assertEqual(result.requested_device, "gpu")
        self.assertEqual(result.selected_device, "gpu")
        self.assertFalse(result.fallback_used)
        self.assertEqual(result.output_shape, (2, 2))
        self.assertTrue(result.evaluated)
        self.assertTrue(result.synchronized)
        self.assertEqual(result.selected_expert_ids, INDEPENDENT_EXPERT_IDS)
        self.assertEqual(result.selected_expert_ids.count(1), 2)

        for actual, expected in zip(
            result.normalized_weights,
            INDEPENDENT_WEIGHTS,
        ):
            self.assertLessEqual(abs(actual - expected), 0.000001)
        for token_offset in range(0, len(result.normalized_weights), 2):
            self.assertLessEqual(
                abs(sum(result.normalized_weights[token_offset : token_offset + 2]) - 1.0),
                0.000001,
            )

        for actual, expected in zip(
            result.selected_outputs,
            INDEPENDENT_SELECTED_OUTPUTS,
        ):
            self.assertLessEqual(abs(actual - expected), 0.00001)
        for actual, expected in zip(result.actual, INDEPENDENT_WEIGHTED_OUTPUT):
            self.assertLessEqual(abs(actual - expected), 0.00001)

        self.assertTrue(result.route_weight_comparison.passed)
        self.assertTrue(result.output_comparison.passed)
        self.assertTrue(result.passed)
        gauges = result.memory_gauges.to_protocol_result()
        self.assertIsNone(gauges["reported_summed_total_bytes"])


if __name__ == "__main__":
    unittest.main()
