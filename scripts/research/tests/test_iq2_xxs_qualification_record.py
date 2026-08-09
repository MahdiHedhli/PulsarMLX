#!/usr/bin/env python3
"""CI-safe semantic checks for the committed real IQ2_XXS qualification."""

from __future__ import annotations

import json
import math
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from glm52_telemetry import assert_public_safe  # noqa: E402

RECORD = (
    ROOT
    / "docs/research/glm52/raw/f016-iq2-xxs-numpy-qualification-0001.json"
)


def _percentile(values: list[float], percentage: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentage / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _load() -> dict:
    def reject_duplicate(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key: {key}")
            result[key] = value
        return result

    return json.loads(RECORD.read_text(), object_pairs_hook=reject_duplicate)


class Iq2XxsQualificationRecordTests(unittest.TestCase):
    def test_real_matrix_exact_bit_and_identity_gates(self) -> None:
        record = _load()
        self.assertEqual(record["actual_status"], "passed")
        self.assertFalse(record["source_dirty"])
        self.assertEqual(record["machine"]["architecture"], "arm64")
        self.assertEqual(record["machine"]["chip"], "Apple M1 Ultra")
        self.assertEqual(record["decoder_modes"], ["scalar_reference", "numpy_vectorized"])
        self.assertFalse(record["scalar_oracle_imports_mlx"])
        self.assertEqual(
            [case["layer"] for case in record["cases"]], [3, 20, 40, 60]
        )
        self.assertEqual(len({case["shard"] for case in record["cases"]}), 4)
        for case in record["cases"]:
            self.assertEqual(case["shape"], [2048, 6144])
            self.assertEqual(case["encoded_bytes"], 3_244_032)
            self.assertEqual(case["decoded_bytes"], 50_331_648)
            self.assertTrue(case["exact_f32_bits"])
            self.assertEqual(case["mismatch_count"], 0)
            self.assertIsNone(case["first_mismatch"])
            self.assertTrue(case["deterministic_repeat"])
            self.assertEqual(len(set(case["deterministic_repeat_sha256"])), 1)
            self.assertTrue(all(row["exact_f32_bits"] for row in case["rows_checked"]))
        subprocess.run(
            ["git", "cat-file", "-e", f"{record['source_commit']}^{{commit}}"],
            cwd=ROOT,
            check=True,
        )
        assert_public_safe(record)

    def test_raw_timing_samples_reproduce_every_summary(self) -> None:
        benchmark = _load()["benchmark"]
        self.assertEqual(benchmark["warmups_per_mode"], 3)
        self.assertEqual(benchmark["samples_per_mode"], 10)
        self.assertTrue(benchmark["exact_and_deterministic_outputs"])
        self.assertEqual(len(set(benchmark["vector_output_hashes"])), 1)
        self.assertEqual(
            benchmark["vector_output_hashes"][0],
            benchmark["scalar_output_hashes"][0],
        )
        summaries = {}
        for mode in ("vector", "scalar"):
            samples = benchmark[f"{mode}_raw_seconds"]
            declared = benchmark[f"{mode}_summary"]
            self.assertEqual(len(samples), 10)
            self.assertTrue(all(math.isfinite(value) and value > 0 for value in samples))
            mean = sum(samples) / len(samples)
            deviation = math.sqrt(
                sum((value - mean) ** 2 for value in samples) / (len(samples) - 1)
            )
            expected = {
                "sample_count": len(samples),
                "median_seconds": _percentile(samples, 50),
                "mean_seconds": mean,
                "standard_deviation_seconds": deviation,
                "minimum_seconds": min(samples),
                "maximum_seconds": max(samples),
                "p5_seconds": _percentile(samples, 5),
                "p25_seconds": _percentile(samples, 25),
                "p75_seconds": _percentile(samples, 75),
                "p95_seconds": _percentile(samples, 95),
                "coefficient_of_variation": deviation / mean,
            }
            for key, value in expected.items():
                if isinstance(value, float):
                    self.assertAlmostEqual(declared[key], value, places=12)
                else:
                    self.assertEqual(declared[key], value)
            summaries[mode] = declared
        weights = benchmark["case"]["weights"]
        self.assertAlmostEqual(
            benchmark["vector_weights_per_second_median"],
            weights / summaries["vector"]["median_seconds"],
        )
        self.assertAlmostEqual(
            benchmark["scalar_weights_per_second_median"],
            weights / summaries["scalar"]["median_seconds"],
        )
        self.assertAlmostEqual(
            benchmark["median_speedup"],
            summaries["scalar"]["median_seconds"]
            / summaries["vector"]["median_seconds"],
        )


if __name__ == "__main__":
    unittest.main()
