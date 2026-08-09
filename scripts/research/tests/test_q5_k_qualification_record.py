#!/usr/bin/env python3
"""CI-safe semantic validation for the real Q5_K qualification record."""

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

RECORD = ROOT / "docs/research/glm52/raw/post-f016-q5-k-numpy-qualification-0001.json"
ANALYZER = ROOT / "scripts/research/analyze_glm52_q5_k_numpy.py"
EXPECTED_SOURCE = "b5ad0059eae9f989c3f24fe7f6208e798fb66a4a"
EXPECTED_CHECKPOINT = "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee"


def _load() -> dict:
    def reject_duplicate(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key: {key}")
            result[key] = value
        return result

    return json.loads(RECORD.read_text(), object_pairs_hook=reject_duplicate)


def _percentile(values: list[float], percent: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


class Q5KQualificationRecordTests(unittest.TestCase):
    def test_real_cases_identity_exactness_and_resources(self) -> None:
        record = _load()
        self.assertEqual(record["schema"], "pulsarmlx.research.glm52-q5-k-numpy-qualification")
        self.assertEqual(record["schema_version"], "1.0.0")
        self.assertEqual(record["actual_status"], "passed")
        self.assertEqual(record["source_commit"], EXPECTED_SOURCE)
        self.assertFalse(record["source_dirty"])
        self.assertEqual(record["checkpoint"]["checkpoint_set_sha256"], EXPECTED_CHECKPOINT)
        self.assertEqual(record["machine"]["chip"], "Apple M1 Ultra")
        self.assertEqual(record["machine"]["architecture"], "arm64")
        self.assertEqual(record["protocol"]["warmups_per_mode"], 3)
        self.assertEqual(record["protocol"]["measured_samples_per_mode"], 10)
        self.assertEqual([case["layer"] for case in record["cases"]], [3, 20, 40, 60])
        self.assertEqual(len({case["shard"] for case in record["cases"]}), 4)
        for case in record["cases"]:
            self.assertEqual(case["quantization"], "Q5_K")
            self.assertEqual(case["shape_rows_cols"], [6144, 16384])
            self.assertEqual(case["encoded_bytes"], 69_206_016)
            self.assertEqual(case["storage_read_count"], 1)
            self.assertTrue(case["exact_f32_bits"])
            self.assertEqual(case["mismatch_count"], 0)
            self.assertIsNone(case["first_mismatch"])
            self.assertTrue(case["deterministic_repeat"])
            self.assertEqual(len(set(case["deterministic_repeat_sha256"])), 1)
            self.assertTrue(case["signed_zero_exact"])
            self.assertEqual(case["signed_zero_count_scalar"], case["signed_zero_count_vector"])
        self.assertGreater(record["benchmark"]["median_decode_speedup"], 20)
        self.assertEqual(record["resource_before"]["level"], "normal")
        self.assertEqual(record["resource_after"]["level"], "normal")
        self.assertIn("full-stack or token-generation speedup", record["unsupported_interpretations"])
        subprocess.run(
            ["git", "cat-file", "-e", f"{record['source_commit']}^{{commit}}"],
            cwd=ROOT,
            check=True,
        )
        assert_public_safe(record)

    def test_raw_samples_reproduce_summaries_and_generated_table(self) -> None:
        record = _load()
        for mode in ("scalar_reference", "numpy_vectorized"):
            section = record["benchmark"][mode]
            values = [float(value) for value in section["samples_seconds"]]
            mean = sum(values) / len(values)
            deviation = math.sqrt(
                sum((value - mean) ** 2 for value in values) / (len(values) - 1)
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
            for key, value in expected.items():
                if isinstance(value, float):
                    self.assertAlmostEqual(section["summary"][key], value, places=12)
                else:
                    self.assertEqual(section["summary"][key], value)
        scalar = record["benchmark"]["scalar_reference"]["summary"]["median_seconds"]
        vector = record["benchmark"]["numpy_vectorized"]["summary"]["median_seconds"]
        self.assertAlmostEqual(record["benchmark"]["median_decode_speedup"], scalar / vector, places=12)
        subprocess.run([sys.executable, str(ANALYZER), "--check"], cwd=ROOT, check=True)


if __name__ == "__main__":
    unittest.main()
