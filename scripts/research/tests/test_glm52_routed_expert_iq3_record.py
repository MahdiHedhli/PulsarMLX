#!/usr/bin/env python3
"""CI-safe semantic checks for the real routed-expert benchmark record."""

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

RECORD = ROOT / "docs/research/glm52/raw/f016-routed-expert-iq3-0001.json"


def _load() -> dict:
    def reject_duplicate(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key: {key}")
            result[key] = value
        return result

    return json.loads(RECORD.read_text(), object_pairs_hook=reject_duplicate)


def _percentile(values: list[float], percentage: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentage / 100.0
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


class Glm52RoutedExpertIq3RecordTests(unittest.TestCase):
    def test_oracle_route_mixed_quant_and_read_contract(self) -> None:
        record = _load()
        self.assertEqual(record["actual_status"], "passed")
        self.assertFalse(record["source_dirty"])
        self.assertEqual(record["machine"]["chip"], "Apple M1 Ultra")
        boundary = record["boundary"]
        self.assertEqual(boundary["layer"], 3)
        self.assertEqual(boundary["expert"], 15)
        self.assertEqual(
            boundary["selected_expert_ids"], [15, 177, 10, 233, 166, 41, 152, 26]
        )
        self.assertEqual(
            [tensor["quantization"] for tensor in boundary["tensors"]],
            ["IQ2_XXS", "IQ2_XXS", "IQ3_XXS"],
        )
        oracle = record["cpu_oracle"]
        self.assertFalse(oracle["imports_mlx"])
        self.assertTrue(oracle["deterministic"])
        self.assertEqual(len(oracle["output_f32_sha256"]), 2)
        self.assertEqual(len(set(oracle["output_f32_sha256"])), 1)
        comparison = record["oracle_comparison"]
        self.assertEqual(comparison["absolute_tolerance"], 5e-3)
        self.assertEqual(comparison["relative_tolerance"], 5e-3)
        self.assertTrue(comparison["passed"])
        self.assertEqual(comparison["mismatch_count"], 0)
        self.assertTrue(record["mode_bit_comparison"]["exact_f32_bits"])
        self.assertEqual(record["mode_bit_comparison"]["mismatch_count"], 0)
        self.assertTrue(record["exact_output_hash_across_modes"])
        self.assertTrue(all(record["deterministic_outputs"].values()))
        self.assertEqual(record["process_first_vector"]["storage_read_count"], 3)
        for sample in record["samples"]["numpy_vectorized"]:
            self.assertEqual(sample["storage_read_count"], 3)
            self.assertEqual(sample["storage_bytes_read"], 11_304_960)
        for sample in record["samples"]["scalar_reference"]:
            self.assertEqual(sample["storage_read_count"], 10240)
            self.assertEqual(sample["storage_bytes_read"], 11_304_960)
        for mode, samples in record["samples"].items():
            for sample in samples:
                metrics = sample["quantization_metrics"]
                self.assertEqual(set(metrics), {"IQ2_XXS", "IQ3_XXS"})
                self.assertEqual(
                    sum(metric["storage_read_count"] for metric in metrics.values()),
                    sample["storage_read_count"],
                )
                self.assertEqual(
                    sum(metric["storage_bytes_read"] for metric in metrics.values()),
                    sample["storage_bytes_read"],
                )
        subprocess.run(
            ["git", "cat-file", "-e", f"{record['source_commit']}^{{commit}}"],
            cwd=ROOT,
            check=True,
        )
        assert_public_safe(record)

    def test_raw_samples_reproduce_all_declared_summaries(self) -> None:
        record = _load()
        fields = (
            "storage_read_seconds",
            "dequant_seconds",
            "contiguous_buffer_seconds",
            "mlx_matrix_build_eval_seconds",
            "mlx_matvec_seconds",
            "unattributed_activation_scale_cleanup_seconds",
            "total_seconds",
        )
        for mode in ("scalar_reference", "numpy_vectorized"):
            samples = record["samples"][mode]
            self.assertEqual(len(samples), 10)
            for field in fields:
                values = [float(sample[field]) for sample in samples]
                mean = sum(values) / len(values)
                deviation = math.sqrt(
                    sum((value - mean) ** 2 for value in values)
                    / (len(values) - 1)
                )
                expected = {
                    "sample_count": len(values),
                    "median_seconds": _percentile(values, 50),
                    "mean_seconds": mean,
                    "standard_deviation_seconds": deviation,
                    "minimum_seconds": min(values),
                    "maximum_seconds": max(values),
                    "p5_seconds": _percentile(values, 5),
                    "p25_seconds": _percentile(values, 25),
                    "p75_seconds": _percentile(values, 75),
                    "p95_seconds": _percentile(values, 95),
                    "coefficient_of_variation": deviation / mean,
                }
                declared = record["summaries"][mode][field]
                for key, value in expected.items():
                    if isinstance(value, float):
                        self.assertAlmostEqual(declared[key], value, places=12)
                    else:
                        self.assertEqual(declared[key], value)


if __name__ == "__main__":
    unittest.main()
