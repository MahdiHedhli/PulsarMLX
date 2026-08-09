#!/usr/bin/env python3
"""CI-safe semantic checks for the committed real matrix boundary record."""

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

RECORD = ROOT / "docs/research/glm52/raw/f016-matrix-boundary-0001.json"


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


class Glm52MatrixBoundaryRecordTests(unittest.TestCase):
    def test_one_read_mlx_gpu_exact_output_contract(self) -> None:
        record = _load()
        self.assertEqual(record["actual_status"], "passed")
        self.assertFalse(record["source_dirty"])
        self.assertEqual(record["machine"]["chip"], "Apple M1 Ultra")
        self.assertEqual(record["machine"]["architecture"], "arm64")
        self.assertEqual(record["matrix"]["quantization"], "IQ2_XXS")
        self.assertEqual(record["matrix"]["shape"], [2048, 6144])
        self.assertEqual(record["matrix"]["expert"], 15)
        self.assertIn(
            "gpu",
            record["backend_identities"]["numpy_vectorized"]["device"].lower(),
        )
        self.assertEqual(record["process_first_vector"]["storage_read_count"], 1)
        self.assertEqual(
            record["process_first_vector"]["storage_bytes_read"], 3_244_032
        )
        self.assertEqual(record["comparison"]["mismatch_count"], 0)
        self.assertTrue(record["comparison"]["exact_f32_bits"])
        self.assertTrue(record["exact_output_hash_across_modes"])
        self.assertTrue(all(record["deterministic_outputs"].values()))
        for sample in record["samples"]["numpy_vectorized"]:
            self.assertEqual(sample["storage_read_count"], 1)
            self.assertEqual(sample["storage_bytes_read"], 3_244_032)
        for sample in record["samples"]["scalar_reference"]:
            self.assertEqual(sample["storage_read_count"], 2048)
        subprocess.run(
            ["git", "cat-file", "-e", f"{record['source_commit']}^{{commit}}"],
            cwd=ROOT,
            check=True,
        )
        assert_public_safe(record)

    def test_raw_samples_reproduce_component_summaries(self) -> None:
        record = _load()
        fields = (
            "storage_read_seconds",
            "dequant_seconds",
            "contiguous_buffer_seconds",
            "mlx_matrix_build_eval_seconds",
            "mlx_matvec_seconds",
            "total_seconds",
            "cleanup_seconds",
            "total_with_cleanup_seconds",
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
