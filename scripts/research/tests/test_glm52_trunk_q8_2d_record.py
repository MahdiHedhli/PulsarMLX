#!/usr/bin/env python3
"""CI-safe validation for the real 2-D Q8_0 dense integration record."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))
from glm52_telemetry import assert_public_safe  # noqa: E402
from qualify_iq2_xxs_numpy import _summary  # noqa: E402

RECORD = ROOT / "docs/research/glm52/raw/post-f016-trunk-q8-2d-integration-0001.json"
ANALYZER = ROOT / "scripts/research/analyze_glm52_trunk_q8_2d.py"
SOURCE = "15a358de4a48387e9c0d9d1b1da1d781be1a3c08"
BASELINE = "whole_matrix_numpy_q5"
CANDIDATE = "whole_matrix_numpy_q5_q8"


class Glm52TrunkQ82DRecordTests(unittest.TestCase):
    def test_record_contract_summaries_and_table(self) -> None:
        record = json.loads(RECORD.read_text(), object_pairs_hook=lambda pairs: _unique(pairs))
        self.assertEqual(record["actual_status"], "passed")
        self.assertEqual(record["source_commit"], SOURCE)
        self.assertFalse(record["source_dirty"])
        self.assertEqual(record["matrix"]["identity"]["quantization"], "Q8_0")
        self.assertTrue(record["matrix"]["comparison"]["exact_f32_bits"])
        self.assertTrue(record["representative_mla_layer"]["comparison"]["exact_f32_bits"])
        self.assertEqual(record["representative_mla_layer"]["captured_operation_contract"], {"operation_count": 4, "other_scalar_count": 0, "q5_vectorized_count": 2, "q8_vectorized_count": 2})
        for boundary in (record["matrix"], record["representative_mla_layer"]):
            for mode in (BASELINE, CANDIDATE):
                self.assertEqual(len(boundary["samples"][mode]), 10)
                for field, summary in boundary["summaries"][mode].items():
                    values = [sample[field] for sample in boundary["samples"][mode]]
                    self.assertEqual(summary, _summary(values))
        for sample in record["matrix"]["samples"][CANDIDATE]:
            self.assertEqual(sample["decoder_mode"], "numpy_vectorized_q8_0")
            self.assertEqual(sample["storage_read_count"], 1)
        self.assertEqual(record["resource_before"]["level"], "normal")
        self.assertEqual(record["resource_after"]["level"], "normal")
        self.assertIn("per-head 3D Q8_0 vectorization", record["unsupported_interpretations"])
        subprocess.run(["git", "cat-file", "-e", f"{SOURCE}^{{commit}}"], cwd=ROOT, check=True)
        assert_public_safe(record)
        subprocess.run([sys.executable, str(ANALYZER), "--check"], cwd=ROOT, check=True)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


if __name__ == "__main__":
    unittest.main()
