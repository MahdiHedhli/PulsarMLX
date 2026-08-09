#!/usr/bin/env python3
"""CI-safe validation for the retained cleanup-cadence record."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))
from benchmark_glm52_trunk_residency import _summary_nonnegative  # noqa: E402
from glm52_telemetry import assert_public_safe  # noqa: E402

RECORD = ROOT / "docs/research/glm52/raw/post-f016-trunk-cleanup-0001.json"
TABLE = ROOT / "docs/research/glm52/tables/post-f016-trunk-cleanup-0001.md"
ANALYZER = ROOT / "scripts/research/analyze_glm52_cleanup.py"
SOURCE = "919d575e7b2ec5d5b6cc0a6d5ac04a36d5990ebb"


class Glm52CleanupRecordTests(unittest.TestCase):
    def test_record_contract_and_generated_table(self) -> None:
        record = json.loads(RECORD.read_text(), object_pairs_hook=_unique)
        self.assertEqual(record["actual_status"], "passed")
        self.assertEqual(record["source_commit"], SOURCE)
        self.assertFalse(record["source_dirty"])
        self.assertTrue(record["comparison"]["exact_output_hash_across_cleanup_modes"])
        self.assertEqual(record["protocol"]["batched_cleanup_interval"], 5)
        current = record["current_cleanup_each_operation"]
        batched = record["batched_cleanup"]
        self.assertEqual(len(current["samples"]), 30)
        self.assertEqual(len(batched["samples"]), 30)
        self.assertEqual(len(batched["cleanup_event_samples_seconds"]), 6)
        self.assertEqual(record["cleanup_only"]["summary"], _summary_nonnegative(record["cleanup_only"]["samples_seconds"]))
        for group in (current, batched):
            for field, summary in group["summaries"].items():
                self.assertEqual(summary, _summary_nonnegative([float(sample[field]) for sample in group["samples"]]))
        self.assertEqual(batched["cleanup_event_summary"], _summary_nonnegative(batched["cleanup_event_samples_seconds"]))
        self.assertTrue(all(sample["resource_after"]["level"] == "normal" for sample in current["samples"] + batched["samples"]))
        self.assertEqual(record["resource_after"]["level"], "normal")
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
