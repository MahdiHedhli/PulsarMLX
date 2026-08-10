#!/usr/bin/env python3
"""CI-safe checks for the post-trunk P1 MoE attribution."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/research/analyze_glm52_moe_p1.py"
RECORD = ROOT / "docs/research/glm52/raw/post-f016-p1-moe-attribution-0001.json"
TABLE = ROOT / "docs/research/glm52/tables/post-f016-p1-moe-attribution-0001.md"
sys.path.insert(0, str(ROOT / "scripts/research"))
from glm52_telemetry import assert_public_safe  # noqa: E402


class Glm52MoeP1AttributionTests(unittest.TestCase):
    def test_attribution_is_bounded_deterministic_and_public_safe(self) -> None:
        record = json.loads(RECORD.read_text(), object_pairs_hook=_unique)
        self.assertEqual(record["actual_status"], "passed")
        self.assertEqual(len(record["stacks"]["warm"]["all_layers"]), 79)
        self.assertEqual(len(record["top_20_routed_expert_sets_by_attributed_seconds"]), 20)
        self.assertFalse(record["individual_expert_hotspot_status"]["available"])
        split = record["warm_routed_shared_decomposition"]
        self.assertEqual(split["routed_matrix_loads_per_moe_layer"], 24)
        self.assertEqual(split["shared_matrix_hits_per_moe_layer"], 3)
        self.assertEqual(split["shared_decode_read_build_seconds"], 0.0)
        self.assertFalse(split["shared_vs_routed_matvec_split_available"])
        self.assertGreater(split["expert_cache_attributed_total_seconds"], 0.0)
        self.assertTrue(all(len(row["routed_expert_ids"]) == 8 for row in record["top_20_routed_expert_sets_by_attributed_seconds"]))
        self.assertIn("not an individual expert ranking", record["individual_expert_hotspot_status"]["safe_interpretation"])
        assert_public_safe(record)
        subprocess.run(
            [sys.executable, str(SCRIPT), "--json-out", str(RECORD), "--table-out", str(TABLE), "--check"],
            cwd=ROOT,
            check=True,
        )


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


if __name__ == "__main__":
    unittest.main()
