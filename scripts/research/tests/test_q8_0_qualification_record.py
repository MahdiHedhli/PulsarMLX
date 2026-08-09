#!/usr/bin/env python3
"""CI-safe semantic validation for the real Q8_0 qualification record."""

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

RECORD = ROOT / "docs/research/glm52/raw/post-f016-q8-0-numpy-qualification-0001.json"
ANALYZER = ROOT / "scripts/research/analyze_glm52_q8_0_numpy.py"
SOURCE = "d24549193e3f9718c34e34b70904a5273af5978c"
CHECKPOINT = "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee"


def _load():
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key: {key}")
            result[key] = value
        return result
    return json.loads(RECORD.read_text(), object_pairs_hook=unique)


class Q80QualificationRecordTests(unittest.TestCase):
    def test_record_contract(self) -> None:
        record = _load()
        self.assertEqual(record["actual_status"], "passed")
        self.assertEqual(record["source_commit"], SOURCE)
        self.assertFalse(record["source_dirty"])
        self.assertEqual(record["checkpoint"]["checkpoint_set_sha256"], CHECKPOINT)
        self.assertEqual(record["machine"]["chip"], "Apple M1 Ultra")
        self.assertEqual([case["layer"] for case in record["cases"]], [3, 20, 40, 60])
        self.assertEqual(len({case["shard"] for case in record["cases"]}), 4)
        for case in record["cases"]:
            self.assertEqual(case["quantization"], "Q8_0")
            self.assertEqual(case["shape_rows_cols"], [16384, 2048])
            self.assertEqual(case["storage_read_count"], 1)
            self.assertTrue(case["exact_f32_bits"])
            self.assertEqual(case["mismatch_count"], 0)
            self.assertTrue(case["deterministic_repeat"])
            self.assertTrue(case["signed_zero_exact"])
        for mode in ("scalar_reference", "numpy_vectorized"):
            section = record["benchmark"][mode]
            self.assertEqual(section["summary"], _summary(section["samples_seconds"]))
        self.assertGreater(record["benchmark"]["median_decode_speedup"], 50)
        self.assertEqual(record["resource_before"]["level"], "normal")
        self.assertEqual(record["resource_after"]["level"], "normal")
        self.assertIn("per-head 3D Q8_0 acceleration", record["unsupported_interpretations"])
        subprocess.run(["git", "cat-file", "-e", f"{SOURCE}^{{commit}}"], cwd=ROOT, check=True)
        assert_public_safe(record)

    def test_generated_table_is_current(self) -> None:
        subprocess.run([sys.executable, str(ANALYZER), "--check"], cwd=ROOT, check=True)


if __name__ == "__main__":
    unittest.main()
