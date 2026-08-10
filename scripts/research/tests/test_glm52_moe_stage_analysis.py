#!/usr/bin/env python3
"""CI-safe checks for the generated bounded MoE stage analysis."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/research/analyze_glm52_moe_profile.py"
RECORD = ROOT / "docs/research/glm52/raw/post-f016-moe-stage-analysis-0001.json"
TABLE = ROOT / "docs/research/glm52/tables/post-f016-moe-stage-analysis-0001.md"
sys.path.insert(0, str(ROOT / "scripts/research"))
from glm52_telemetry import assert_public_safe  # noqa: E402


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


class Glm52MoeStageAnalysisTests(unittest.TestCase):
    def test_analysis_is_deterministic_bounded_and_public_safe(self) -> None:
        record = json.loads(RECORD.read_text(), object_pairs_hook=_unique)
        self.assertEqual(record["actual_status"], "passed")
        self.assertEqual([layer["layer"] for layer in record["layers"]], [3, 8, 40, 78])
        self.assertEqual(len(record["top_20_routed_experts"]), 20)
        self.assertEqual(len(record["top_20_matrix_projections"]), 20)
        self.assertEqual(record["decision"]["dominant_stage"], "scalar-reference dequantization for unsupported expert quantizations")
        self.assertEqual(record["decision"]["first_measured_candidates"][0], "Q2_K")
        self.assertFalse(record["decision"]["feature_018_kernel_selected"])
        self.assertGreater(record["layers"][3]["boundary_total_seconds"]["median_seconds"], 50.0)
        self.assertGreater(record["layers"][1]["boundary_total_seconds"]["median_seconds"], 40.0)
        assert_public_safe(record)
        subprocess.run(
            [sys.executable, str(SCRIPT), "--json-out", str(RECORD), "--table-out", str(TABLE), "--check"],
            cwd=ROOT,
            check=True,
        )


if __name__ == "__main__":
    unittest.main()
