#!/usr/bin/env python3
"""CI-safe validation for routed-expert residency economics."""

from __future__ import annotations
import json, subprocess, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/research/analyze_glm52_routed_residency.py"
RECORD = ROOT / "docs/research/glm52/raw/post-f016-routed-residency-economics-0001.json"
sys.path.insert(0, str(ROOT / "scripts/research"))
from glm52_telemetry import assert_public_safe  # noqa: E402


class RoutedResidencyTests(unittest.TestCase):
    def test_committed_route_economics(self):
        record = json.loads(RECORD.read_text())
        self.assertEqual(record["actual_status"], "passed")
        self.assertTrue(record["prefix_routes_identical"])
        self.assertEqual(record["golden_route_population"]["stacks"], 9)
        self.assertEqual(len(record["adjacent_stack_reuse"]), 8)
        self.assertGreater(record["adjacent_repeat_fraction_overall"], 0.35)
        self.assertFalse(record["decision"]["decoded_all_observed_routed_units_safe"])
        self.assertFalse(record["decision"]["feature_018_kernel_selected"])
        assert_public_safe(record)
        subprocess.run([sys.executable, str(SCRIPT), "--check"], cwd=ROOT, check=True)


if __name__ == "__main__":
    unittest.main()
