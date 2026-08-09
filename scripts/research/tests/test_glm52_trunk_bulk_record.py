#!/usr/bin/env python3
"""CI-safe semantic checks for the Phase-A real trunk bulk-read record."""

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

RECORD = ROOT / "docs/research/glm52/raw/post-f016-trunk-bulk-read-0001.json"
ANALYZER = ROOT / "scripts/research/analyze_glm52_trunk_bulk.py"
EXPECTED_SOURCE = "bf697033b2288f92f8659f0e8e2b10b04b3e17f6"
EXPECTED_CHECKPOINT = "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee"
EXPECTED_MATRICES = {
    "blk.3.attn_output.weight": ("Q5_K", [6144, 16384], 69_206_016),
    "blk.3.attn_q_b.weight": ("Q8_0", [16384, 2048], 35_651_584),
    "blk.8.attn_output.weight": ("Q6_K", [6144, 16384], 82_575_360),
}
SUMMARY_FIELDS = (
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


def _percentile(values: list[float], percentage: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentage / 100.0
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _assert_summary(test: unittest.TestCase, samples: list[dict], declared: dict, field: str) -> None:
    values = [float(sample[field]) for sample in samples]
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
            test.assertAlmostEqual(declared[field][key], value, places=12)
        else:
            test.assertEqual(declared[field][key], value)


class Glm52TrunkBulkRecordTests(unittest.TestCase):
    def test_identity_exactness_requests_resources_and_scope(self) -> None:
        record = _load()
        self.assertEqual(record["schema"], "pulsarmlx.research.glm52-trunk-bulk-read")
        self.assertEqual(record["schema_version"], "1.0.0")
        self.assertEqual(record["actual_status"], "passed")
        self.assertEqual(record["source_commit"], EXPECTED_SOURCE)
        self.assertFalse(record["source_dirty"])
        self.assertEqual(record["checkpoint"]["checkpoint_set_sha256"], EXPECTED_CHECKPOINT)
        self.assertEqual(record["checkpoint"]["file_count"], 6)
        self.assertEqual(record["checkpoint"]["total_bytes"], 238_458_632_928)
        self.assertEqual(record["protocol"]["warmups_per_mode"], 3)
        self.assertEqual(record["protocol"]["measured_samples_per_mode"], 10)
        self.assertEqual(record["protocol"]["decoder"], "same scalar row decoder in the same row order")

        matrices = {item["identity"]["tensor"]: item for item in record["matrices"]}
        self.assertEqual(set(matrices), set(EXPECTED_MATRICES))
        for tensor, (quant, shape, encoded_bytes) in EXPECTED_MATRICES.items():
            matrix = matrices[tensor]
            identity = matrix["identity"]
            self.assertEqual(identity["quantization"], quant)
            self.assertEqual(identity["shape_rows_cols"], shape)
            self.assertEqual(identity["encoded_bytes"], encoded_bytes)
            self.assertTrue(matrix["comparison"]["exact_f32_bits"])
            self.assertEqual(matrix["comparison"]["mismatch_count"], 0)
            self.assertTrue(matrix["comparison"]["same_hash_across_modes"])
            self.assertTrue(matrix["read_contract"]["encoded_bytes_unchanged"])
            self.assertEqual(matrix["read_contract"]["row_reference"], shape[0])
            self.assertEqual(matrix["read_contract"]["whole_matrix_scalar"], 1)
            for mode, expected_reads in (("row_reference", shape[0]), ("whole_matrix_scalar", 1)):
                samples = matrix["samples"][mode]
                self.assertEqual(len(samples), 10)
                self.assertEqual(len({sample["output_f32_sha256"] for sample in samples}), 1)
                for sample in samples:
                    self.assertEqual(sample["storage_read_count"], expected_reads)
                    self.assertEqual(sample["encoded_bytes"], encoded_bytes)
                    self.assertEqual(sample["resource_before"]["level"], "normal")
                    self.assertEqual(sample["resource_after"]["level"], "normal")

        mla = record["representative_mla_layer"]
        self.assertEqual(mla["layer"], 8)
        self.assertTrue(mla["comparison"]["exact_f32_bits"])
        self.assertEqual(mla["comparison"]["mismatch_count"], 0)
        self.assertEqual(mla["dense_2d_read_counts"]["row_reference"], [25_152])
        self.assertEqual(mla["dense_2d_read_counts"]["whole_matrix_scalar"], [4])
        for mode in ("row_reference", "whole_matrix_scalar"):
            self.assertEqual(len(mla["samples"][mode]), 10)
            for sample in mla["samples"][mode]:
                self.assertEqual(sample["resource_before"]["level"], "normal")
                self.assertEqual(sample["resource_after"]["level"], "normal")

        self.assertIn("full-stack or token-generation speedup", record["unsupported_interpretations"])
        self.assertIn("direct quantized Metal evidence", record["unsupported_interpretations"])
        self.assertEqual(record["resource_before"]["level"], "normal")
        self.assertEqual(record["resource_after"]["level"], "normal")
        subprocess.run(
            ["git", "cat-file", "-e", f"{record['source_commit']}^{{commit}}"],
            cwd=ROOT,
            check=True,
        )
        assert_public_safe(record)

    def test_raw_samples_reproduce_declared_summaries_and_table(self) -> None:
        record = _load()
        for matrix in record["matrices"]:
            for mode in ("row_reference", "whole_matrix_scalar"):
                for field in SUMMARY_FIELDS:
                    _assert_summary(
                        self,
                        matrix["samples"][mode],
                        matrix["summaries"][mode],
                        field,
                    )
        mla = record["representative_mla_layer"]
        for mode in ("row_reference", "whole_matrix_scalar"):
            for field in SUMMARY_FIELDS + ("uninstrumented_residual_seconds",):
                _assert_summary(self, mla["samples"][mode], mla["summaries"][mode], field)
        subprocess.run([sys.executable, str(ANALYZER), "--check"], cwd=ROOT, check=True)


if __name__ == "__main__":
    unittest.main()
