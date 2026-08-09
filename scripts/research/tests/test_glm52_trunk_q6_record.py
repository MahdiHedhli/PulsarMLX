#!/usr/bin/env python3
"""CI-safe validation for the real Q6_K dense-integration record."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))
from analyze_glm52_trunk_q6 import _candidate_counts  # noqa: E402
from glm52_telemetry import assert_public_safe  # noqa: E402
from qualify_iq2_xxs_numpy import _summary  # noqa: E402

RECORD = ROOT / "docs/research/glm52/raw/post-f016-trunk-q6-integration-0001.json"
TABLE = ROOT / "docs/research/glm52/tables/post-f016-trunk-q6-integration-0001.md"
ANALYZER = ROOT / "scripts/research/analyze_glm52_trunk_q6.py"
SOURCE = "42c38d3ef61a251fc9823bdca0c35afdcdc171c8"
BASELINE = "whole_matrix_numpy_q5_q8_head_numpy"
CANDIDATE = "whole_matrix_numpy_q5_q8_q6_head_numpy"


class Glm52TrunkQ6RecordTests(unittest.TestCase):
    def test_record_contract_summaries_and_table(self) -> None:
        record = json.loads(RECORD.read_text(), object_pairs_hook=_unique)
        self.assertEqual(record["actual_status"], "passed")
        self.assertEqual(record["source_commit"], SOURCE)
        self.assertFalse(record["source_dirty"])
        self.assertEqual(record["matrix"]["identity"]["quantization"], "Q6_K")
        self.assertTrue(record["matrix"]["comparison"]["exact_f32_bits"])
        self.assertTrue(record["representative_mla_layer"]["comparison"]["exact_f32_bits"])
        self.assertEqual(record["representative_mla_layer"]["layer"], 8)
        self.assertEqual(_candidate_counts(record), {
            "operation_count": 132,
            "q5_vectorized_count": 0,
            "q8_vectorized_count": 130,
            "q6_vectorized_count": 2,
            "other_scalar_count": 0,
        })
        for boundary in (record["matrix"], record["representative_mla_layer"]):
            for mode in (BASELINE, CANDIDATE):
                self.assertEqual(len(boundary["samples"][mode]), 10)
                for field, summary in boundary["summaries"][mode].items():
                    self.assertEqual(summary, _summary([sample[field] for sample in boundary["samples"][mode]]))
        for sample in record["matrix"]["samples"][CANDIDATE]:
            self.assertEqual(sample["decoder_mode"], "numpy_vectorized_q6_k")
            self.assertEqual(sample["storage_read_count"], 1)
        for sample in record["representative_mla_layer"]["samples"][CANDIDATE]:
            modes = [op["decoder_mode"] for op in sample["dense_2d"]["operations"]]
            self.assertEqual(modes.count("numpy_vectorized_q6_k"), 2)
            self.assertEqual(modes.count("numpy_vectorized_q8_0"), 130)
            self.assertNotIn("scalar_reference", modes)
        self.assertEqual(record["resource_before"]["level"], "normal")
        self.assertEqual(record["resource_after"]["level"], "normal")
        subprocess.run(["git", "cat-file", "-e", f"{SOURCE}^{{commit}}"], cwd=ROOT, check=True)
        assert_public_safe(record)
        subprocess.run([sys.executable, str(ANALYZER), "--source", str(RECORD), "--table", str(TABLE), "--check"], cwd=ROOT, check=True)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


if __name__ == "__main__":
    unittest.main()
