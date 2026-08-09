#!/usr/bin/env python3
"""CI-safe validation for the Q8_0 head-slab NumPy integration record."""

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

RECORD = ROOT / "docs/research/glm52/raw/post-f016-q8-head-numpy-integration-0001.json"
TABLE = ROOT / "docs/research/glm52/tables/post-f016-q8-head-numpy-integration-0001.md"
ANALYZER = ROOT / "scripts/research/analyze_glm52_q8_head.py"
SOURCE = "a6f233822dade6096209a165d5085c4234063960"


class Q8HeadNumpyRecordTests(unittest.TestCase):
    def test_record_contract_summaries_and_table(self) -> None:
        record = json.loads(RECORD.read_text(), object_pairs_hook=_unique)
        baseline, candidate = record["protocol"]["modes"]
        self.assertEqual(record["actual_status"], "passed")
        self.assertEqual(record["source_commit"], SOURCE)
        self.assertFalse(record["source_dirty"])
        self.assertTrue(record["head_boundary"]["comparison"]["exact_f32_bits"])
        self.assertTrue(record["representative_mla_layer"]["comparison"]["exact_f32_bits"])
        for boundary in (record["head_boundary"], record["representative_mla_layer"]):
            for mode in (baseline, candidate):
                self.assertEqual(len(boundary["samples"][mode]), 10)
                for field, summary in boundary["summaries"][mode].items():
                    self.assertEqual(summary, _summary([sample[field] for sample in boundary["samples"][mode]]))
        mla = record["representative_mla_layer"]
        self.assertEqual(mla["samples"][baseline][0]["head_storage_read_count"], 128)
        self.assertEqual(mla["samples"][candidate][0]["head_storage_read_count"], 128)
        self.assertEqual(mla["samples"][baseline][0]["head_decoder_modes"], ["scalar_reference"])
        self.assertEqual(mla["samples"][candidate][0]["head_decoder_modes"], ["numpy_vectorized_q8_0"])
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
