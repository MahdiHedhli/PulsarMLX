#!/usr/bin/env python3
"""CI-safe semantic validation for the retained complete layer-8 attempt."""

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

SOURCE_RECORD = ROOT / "docs/research/glm52/raw/post-f016-trunk-complete-layer8-q6-attempt-0001.json"
AUDIT = ROOT / "docs/research/glm52/raw/post-f016-trunk-complete-layer8-q6-audit-0001.json"
TABLE = ROOT / "docs/research/glm52/tables/post-f016-trunk-complete-layer8-q6-0001.md"
ANALYZER = ROOT / "scripts/research/analyze_glm52_trunk_layer.py"
SOURCE_COMMIT = "7abcce2a3448c63df1226a2594734db630c42d9a"


class Glm52TrunkLayerRecordTests(unittest.TestCase):
    def test_rejected_attempt_and_corrected_audit(self) -> None:
        record = json.loads(SOURCE_RECORD.read_text(), object_pairs_hook=_unique)
        audit = json.loads(AUDIT.read_text(), object_pairs_hook=_unique)
        self.assertEqual(record["actual_status"], "failed")
        self.assertEqual(record["source_commit"], SOURCE_COMMIT)
        self.assertFalse(record["source_dirty"])
        self.assertTrue(record["comparison"]["exact_f32_bits"])
        self.assertEqual(audit["actual_status"], "passed")
        self.assertFalse(audit["gate_correction"]["measurement_rerun_required"])
        for mode, samples in record["samples"].items():
            self.assertEqual(len(samples), 10)
            for field, summary in record["summaries"][mode].items():
                self.assertEqual(summary, _summary([sample[field] for sample in samples]))
            self.assertTrue(all(sample["shared_cache_hits"] == 3 for sample in samples))
            self.assertTrue(all(sample["shared_cache_misses"] == 24 for sample in samples))
            self.assertTrue(all(sample["resident_entries_end"] == 3 for sample in samples))
            self.assertTrue(all(sample["resource_after"]["level"] == "normal" for sample in samples))
        subprocess.run(["git", "cat-file", "-e", f"{SOURCE_COMMIT}^{{commit}}"], cwd=ROOT, check=True)
        assert_public_safe(record)
        assert_public_safe(audit)
        subprocess.run([sys.executable, str(ANALYZER), "--source", str(SOURCE_RECORD), "--audit", str(AUDIT), "--table", str(TABLE), "--check"], cwd=ROOT, check=True)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


if __name__ == "__main__":
    unittest.main()
