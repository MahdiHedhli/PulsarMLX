#!/usr/bin/env python3
"""CI-safe validation for the complete Q2_K qualification record."""

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

RECORD = ROOT / "docs/research/glm52/raw/post-f016-q2-k-numpy-qualification-0001.json"
ANALYZER = ROOT / "scripts/research/analyze_glm52_q2_k_numpy.py"
SOURCE = "296e88688b536b7acc964fbf09137aa45b0ca4ac"


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


class Q2KQualificationRecordTests(unittest.TestCase):
    def test_record(self) -> None:
        record = json.loads(RECORD.read_text(), object_pairs_hook=_unique)
        self.assertEqual(record["actual_status"], "passed")
        self.assertEqual(record["source_commit"], SOURCE)
        self.assertFalse(record["source_dirty"])
        self.assertEqual(
            record["checkpoint_format_census"]["q2_k_tensor_names"],
            ["blk.78.ffn_gate_exps.weight", "blk.78.ffn_up_exps.weight"],
        )
        self.assertEqual(len(record["cases"]), 4)
        for case in record["cases"]:
            self.assertEqual(case["quantization"], "Q2_K")
            self.assertTrue(case["exact_f32_bits"])
            self.assertEqual(case["mismatch_count"], 0)
            self.assertTrue(case["deterministic_repeat"])
            self.assertTrue(case["signed_zero_exact"])
        for mode in ("scalar_reference", "numpy_vectorized"):
            section = record["benchmark"][mode]
            self.assertEqual(section["summary"], _summary(section["samples_seconds"]))
        self.assertGreater(record["benchmark"]["median_decode_speedup"], 10.0)
        self.assertEqual(record["resource_before"]["level"], "normal")
        self.assertEqual(record["resource_after"]["level"], "normal")
        subprocess.run(["git", "cat-file", "-e", f"{SOURCE}^{{commit}}"], cwd=ROOT, check=True)
        assert_public_safe(record)
        subprocess.run([sys.executable, str(ANALYZER), "--check"], cwd=ROOT, check=True)


if __name__ == "__main__":
    unittest.main()
