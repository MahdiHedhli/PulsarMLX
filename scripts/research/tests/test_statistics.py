"""Known-vector contract tests for Feature 002 research statistics.

These tests intentionally load ``scripts/research/statistics.py`` by path so
the project module cannot be confused with Python's standard-library module of
the same name.  T005 lands this test contract before T010 supplies the
implementation.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import unittest


STATISTICS_PATH = Path(__file__).resolve().parents[1] / "statistics.py"


def _load_statistics_module():
    if not STATISTICS_PATH.is_file():
        return None

    spec = importlib.util.spec_from_file_location(
        "pulsarmlx_research_statistics", STATISTICS_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load statistics module: {STATISTICS_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


statistics = _load_statistics_module()


class StatisticsContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertIsNotNone(
            statistics,
            "T010 must implement scripts/research/statistics.py",
        )

    def test_known_vector_uses_type_7_and_sample_standard_deviation(self) -> None:
        summary = statistics.summarize_nanoseconds([10, 20, 30, 40, 50])

        self.assertEqual(summary["sample_count"], 5)
        self.assertEqual(summary["minimum_ns"], 10)
        self.assertEqual(summary["maximum_ns"], 50)
        self.assertEqual(summary["mean_ns"], 30.0)
        self.assertAlmostEqual(
            summary["sample_standard_deviation_ns"], math.sqrt(250.0)
        )
        self.assertIsNone(summary["sample_standard_deviation_reason"])
        self.assertEqual(summary["p5_ns"], 12.0)
        self.assertEqual(summary["p25_ns"], 20.0)
        self.assertEqual(summary["median_ns"], 30.0)
        self.assertEqual(summary["p75_ns"], 40.0)
        self.assertEqual(summary["p95_ns"], 48.0)
        self.assertAlmostEqual(
            summary["coefficient_of_variation"], math.sqrt(250.0) / 30.0
        )
        self.assertIsNone(summary["coefficient_of_variation_reason"])

    def test_type_7_interpolates_every_required_nonmedian_percentile(self) -> None:
        summary = statistics.summarize_nanoseconds([1, 2, 3, 4])

        self.assertEqual(summary["p5_ns"], 1.15)
        self.assertEqual(summary["p25_ns"], 1.75)
        self.assertEqual(summary["median_ns"], 2.5)
        self.assertEqual(summary["p75_ns"], 3.25)
        self.assertEqual(summary["p95_ns"], 3.85)

    def test_single_sample_encodes_undefined_statistics_with_reasons(self) -> None:
        summary = statistics.summarize_nanoseconds([7])

        self.assertEqual(summary["sample_count"], 1)
        self.assertEqual(summary["mean_ns"], 7.0)
        self.assertIsNone(summary["sample_standard_deviation_ns"])
        self.assertEqual(
            summary["sample_standard_deviation_reason"],
            "requires_at_least_two_samples",
        )
        self.assertIsNone(summary["coefficient_of_variation"])
        self.assertEqual(
            summary["coefficient_of_variation_reason"],
            "sample_standard_deviation_unavailable",
        )

    def test_coefficient_of_variation_reports_zero_mean_reason(self) -> None:
        value, reason = statistics.coefficient_of_variation(
            mean=0.0,
            sample_standard_deviation=1.0,
        )

        self.assertIsNone(value)
        self.assertEqual(reason, "zero_mean")

    def test_coefficient_of_variation_reports_missing_deviation_reason(self) -> None:
        value, reason = statistics.coefficient_of_variation(
            mean=7.0,
            sample_standard_deviation=None,
        )

        self.assertIsNone(value)
        self.assertEqual(reason, "sample_standard_deviation_unavailable")

    def test_nanosecond_samples_must_be_positive_plain_integers(self) -> None:
        for invalid_samples in (
            [],
            [0],
            [-1],
            [1.0],
            [True],
            [1, 2, 0],
        ):
            with self.subTest(samples=invalid_samples):
                with self.assertRaises((TypeError, ValueError)):
                    statistics.summarize_nanoseconds(invalid_samples)

        summary = statistics.summarize_nanoseconds([1, 2**63])
        self.assertEqual(summary["minimum_ns"], 1)
        self.assertEqual(summary["maximum_ns"], 2**63)

    def test_grouping_never_pools_incompatible_observations(self) -> None:
        base = {
            "observation_id": "obs-0",
            "case_id": "single-row",
            "condition": "warm",
            "instrumentation_mode": "minimally_instrumented",
            "source_commit": "a" * 40,
            "batch_id": "batch-0",
            "duration_ns": 101,
        }
        observations = [base, {**base, "observation_id": "obs-1"}]
        for index, (field, value) in enumerate(
            (
                ("case_id", "two-row"),
                ("condition", "first_read_new_process_os_cache_uncontrolled"),
                ("instrumentation_mode", "stage_instrumented"),
                ("source_commit", "b" * 40),
                ("batch_id", "batch-1"),
            ),
            start=2,
        ):
            observations.append(
                {
                    **base,
                    "observation_id": f"obs-{index}",
                    field: value,
                }
            )

        groups = statistics.group_raw_observations(observations)

        self.assertEqual(len(groups), 6)
        self.assertEqual(
            sorted(len(group) for group in groups.values()),
            [1, 1, 1, 1, 1, 2],
        )

    def test_grouping_rejects_missing_compatibility_fields(self) -> None:
        complete = {
            "observation_id": "obs-0",
            "case_id": "single-row",
            "condition": "warm",
            "instrumentation_mode": "minimally_instrumented",
            "source_commit": "a" * 40,
            "batch_id": "batch-0",
            "duration_ns": 101,
        }

        for field in (
            "case_id",
            "condition",
            "instrumentation_mode",
            "source_commit",
            "batch_id",
        ):
            incomplete = {
                key: value for key, value in complete.items() if key != field
            }
            with self.subTest(field=field):
                with self.assertRaisesRegex((KeyError, ValueError), field):
                    statistics.group_raw_observations([incomplete])


if __name__ == "__main__":
    unittest.main()
