#!/usr/bin/env python3
"""CI-safe validation for the bounded real trunk-residency record."""

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

RECORD = ROOT / "docs/research/glm52/raw/post-f016-trunk-q6-residency-0001.json"
TABLE = ROOT / "docs/research/glm52/tables/post-f016-trunk-q6-residency-0001.md"
ANALYZER = ROOT / "scripts/research/analyze_glm52_trunk_residency.py"
SOURCE = "bb6c9994"


class Glm52TrunkResidencyRecordTests(unittest.TestCase):
    def test_record_contract_and_generated_table(self) -> None:
        record = json.loads(RECORD.read_text(), object_pairs_hook=_unique)
        self.assertEqual(record["actual_status"], "passed")
        self.assertTrue(record["source_commit"].startswith(SOURCE))
        self.assertFalse(record["source_dirty"])
        self.assertTrue(record["comparison"]["exact_output_hash_across_all_candidates"])
        self.assertEqual([value["candidate"] for value in record["candidates"]], [
            "transient", "compressed_resident", "decoded_hot", "hybrid_compressed_decoded_hot"
        ])
        for candidate in record["candidates"]:
            self.assertEqual(len(candidate["samples"]), 10)
            self.assertEqual(len(candidate["deterministic_output_sha256"]), 1)
            self.assertEqual(candidate["pressure_after_setup"]["level"], "normal")
            self.assertEqual(candidate["pressure_after_teardown"]["level"], "normal")
            for field, summary in candidate["summaries"].items():
                self.assertEqual(summary, _summary_nonnegative([float(sample[field]) for sample in candidate["samples"]]))
        budgets = record["logical_full_trunk_budgets"]
        self.assertEqual(budgets["m1_ultra_capacity_bytes"], 128 * 1024**3)
        self.assertEqual(budgets["conservative_safety_reserve_bytes"], 24 * 1024**3)
        self.assertEqual([value["admission"] for value in budgets["options"] if value["option"] in {"B", "C", "F"}], [
            "unsafe_exceeds_24_gib_reserve",
            "unsafe_exceeds_24_gib_reserve",
            "unsafe_exceeds_24_gib_reserve",
        ])
        subprocess.run(["git", "cat-file", "-e", f"{record['source_commit']}^{{commit}}"], cwd=ROOT, check=True)
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
