#!/usr/bin/env python3
"""CI-safe semantic checks for the complete real layer-3 record."""

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

RECORD = ROOT / "docs/research/glm52/raw/f016-layer3-iq3-0001.json"
EXPERT_IDS = [15, 177, 233, 41, 166, 26, 10, 152]
MID_SHA = "7a19b425ae8bdf0009c84daa61c80fb054bffdf5fa0f3f2291d5af87cc7832aa"


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


class Glm52LayerIq3RecordTests(unittest.TestCase):
    def test_reference_route_cache_and_exact_mode_contract(self) -> None:
        record = _load()
        self.assertEqual(record["actual_status"], "passed")
        self.assertFalse(record["source_dirty"])
        self.assertEqual(record["machine"]["chip"], "Apple M1 Ultra")
        boundary = record["boundary"]
        self.assertEqual(boundary["layer"], 3)
        self.assertEqual(boundary["position"], 0)
        self.assertEqual(boundary["attention_mid_f32_sha256"], MID_SHA)
        self.assertEqual(boundary["selected_expert_ids"], EXPERT_IDS)
        self.assertTrue(boundary["includes_attention"])
        self.assertTrue(boundary["includes_moe"])
        self.assertTrue(boundary["includes_residual_updates"])

        reference = record["architecture_reference"]
        self.assertIn("attention", reference["independence_limitation"])
        self.assertTrue(reference["deterministic"])
        self.assertEqual(len(set(reference["output_f32_sha256"])), 1)
        self.assertEqual(reference["route_expert_ids"], [EXPERT_IDS, EXPERT_IDS])
        comparison = record["reference_comparison"]
        self.assertTrue(comparison["passed"])
        self.assertEqual(comparison["mismatch_count"], 0)
        self.assertGreaterEqual(comparison["cosine_similarity"], 0.999)
        self.assertTrue(record["mode_bit_comparison"]["exact_f32_bits"])
        self.assertEqual(record["mode_bit_comparison"]["mismatch_count"], 0)
        self.assertTrue(record["exact_output_hash_across_modes"])
        self.assertTrue(all(record["deterministic_outputs"].values()))

        first = record["process_first_vector"]
        self.assertEqual(first["decoded_cache_hits"], 0)
        self.assertEqual(first["decoded_cache_misses"], 27)
        self.assertEqual(first["resident_entries_end"], 3)
        self.assertEqual(first["mid_f32_sha256"], MID_SHA)
        self.assertEqual(first["route"]["expert_ids"], EXPERT_IDS)

        for mode, expected_reads in (
            ("scalar_reference", 81920),
            ("numpy_vectorized", 24),
        ):
            samples = record["samples"][mode]
            self.assertEqual(len(samples), 10)
            for sample in samples:
                self.assertEqual(sample["storage_read_count"], expected_reads)
                self.assertEqual(sample["storage_bytes_read"], 90_439_680)
                self.assertEqual(sample["decoded_cache_hits"], 3)
                self.assertEqual(sample["decoded_cache_misses"], 24)
                self.assertEqual(sample["resident_entries_end"], 3)
                self.assertEqual(sample["mlx_matvec_count"], 27)
                self.assertEqual(sample["transient_releases"], 24)
                self.assertEqual(sample["mid_f32_sha256"], MID_SHA)
                self.assertEqual(sample["route"]["expert_ids"], EXPERT_IDS)
                self.assertEqual(
                    set(sample["quantization_metrics"]),
                    {"IQ2_XXS", "IQ3_XXS", "Q5_K", "Q6_K"},
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
            "attention_seconds",
            "moe_seconds",
            "storage_read_seconds",
            "dequant_seconds",
            "contiguous_buffer_seconds",
            "mlx_matrix_build_eval_seconds",
            "mlx_matvec_seconds",
            "boundary_overhead_seconds",
            "total_seconds",
        )
        for mode in ("scalar_reference", "numpy_vectorized"):
            samples = record["samples"][mode]
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
