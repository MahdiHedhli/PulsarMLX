#!/usr/bin/env python3
"""CI-safe validation for the real Q5_K dense integration record."""

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

RECORD = ROOT / "docs/research/glm52/raw/post-f016-trunk-q5-integration-0001.json"
ANALYZER = ROOT / "scripts/research/analyze_glm52_trunk_q5.py"
EXPECTED_SOURCE = "f6446a07d62118672d6d593d536f834786ad2b54"
EXPECTED_CHECKPOINT = "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee"
FIELDS = (
    "storage_read_seconds",
    "dequant_seconds",
    "contiguous_buffer_seconds",
    "mlx_matrix_build_seconds",
    "mlx_matvec_seconds",
    "total_seconds",
    "cleanup_seconds",
    "total_with_cleanup_seconds",
)


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


def _check_summary(test, samples, summaries, field):
    values = [float(sample[field]) for sample in samples]
    mean = sum(values) / len(values)
    deviation = math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))
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
            test.assertAlmostEqual(summaries[field][key], value, places=12)
        else:
            test.assertEqual(summaries[field][key], value)


class Glm52TrunkQ5RecordTests(unittest.TestCase):
    def test_identity_exactness_decoder_contract_and_resources(self) -> None:
        record = _load()
        self.assertEqual(record["schema"], "pulsarmlx.research.glm52-trunk-q5-integration")
        self.assertEqual(record["schema_version"], "1.0.0")
        self.assertEqual(record["actual_status"], "passed")
        self.assertEqual(record["source_commit"], EXPECTED_SOURCE)
        self.assertFalse(record["source_dirty"])
        self.assertEqual(record["checkpoint"]["checkpoint_set_sha256"], EXPECTED_CHECKPOINT)
        self.assertFalse(record["model_inference_executed"])
        matrix = record["matrix"]
        self.assertEqual(matrix["identity"]["tensor"], "blk.3.attn_output.weight")
        self.assertTrue(matrix["comparison"]["exact_f32_bits"])
        self.assertEqual(matrix["comparison"]["mismatch_count"], 0)
        self.assertTrue(matrix["comparison"]["same_hash_across_modes"])
        for mode, decoder in (("whole_matrix_scalar", "scalar_reference"), ("whole_matrix_numpy_q5", "numpy_vectorized_q5_k")):
            self.assertEqual(len(matrix["samples"][mode]), 10)
            for sample in matrix["samples"][mode]:
                self.assertEqual(sample["storage_read_count"], 1)
                self.assertEqual(sample["decoder_mode"], decoder)
                self.assertEqual(sample["resource_before"]["level"], "normal")
                self.assertEqual(sample["resource_after"]["level"], "normal")
        mla = record["representative_mla_layer"]
        self.assertEqual(mla["layer"], 3)
        self.assertTrue(mla["comparison"]["exact_f32_bits"])
        self.assertEqual(mla["captured_operation_contract"], {"operation_count": 4, "other_scalar_count": 2, "q5_vectorized_count": 2})
        for sample in mla["samples"]["whole_matrix_numpy_q5"]:
            operations = sample["dense_2d"]["operations"]
            self.assertEqual(sum(op["decoder_mode"] == "numpy_vectorized_q5_k" for op in operations), 2)
            self.assertEqual(sum(op["decoder_mode"] == "scalar_reference" for op in operations), 2)
        self.assertEqual(record["resource_before"]["level"], "normal")
        self.assertEqual(record["resource_after"]["level"], "normal")
        self.assertIn("full-stack or token-generation speedup", record["unsupported_interpretations"])
        subprocess.run(["git", "cat-file", "-e", f"{record['source_commit']}^{{commit}}"], cwd=ROOT, check=True)
        assert_public_safe(record)

    def test_raw_samples_reproduce_summaries_and_table(self) -> None:
        record = _load()
        for boundary_name in ("matrix", "representative_mla_layer"):
            boundary = record[boundary_name]
            fields = FIELDS + (("uninstrumented_residual_seconds",) if boundary_name != "matrix" else ())
            for mode in ("whole_matrix_scalar", "whole_matrix_numpy_q5"):
                for field in fields:
                    _check_summary(self, boundary["samples"][mode], boundary["summaries"][mode], field)
        subprocess.run([sys.executable, str(ANALYZER), "--check"], cwd=ROOT, check=True)


if __name__ == "__main__":
    unittest.main()
