#!/usr/bin/env python3
"""CI-safe validation for the current complete layer-8 record."""
from __future__ import annotations
import json, subprocess, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]; SCRIPT=ROOT/"scripts/research/analyze_glm52_complete_layer_current.py"; RECORD=ROOT/"docs/research/glm52/raw/post-f016-complete-layer8-all-vector-analysis-0001.json"; sys.path.insert(0,str(ROOT/"scripts/research"))
from glm52_telemetry import assert_public_safe  # noqa: E402
class CompleteLayerCurrentRecordTests(unittest.TestCase):
    def test_analysis(self):
        record=json.loads(RECORD.read_text()); self.assertEqual(record["actual_status"],"passed"); self.assertTrue(record["exact_boundary_identity_preserved"]); self.assertEqual(record["current"]["retained_samples"],10); self.assertEqual(record["current"]["cpu_fallbacks"],0); self.assertEqual(record["current"]["evictions"],0); self.assertEqual(record["current"]["resource_levels"],["normal"]); self.assertGreater(record["cross_commit_complete_layer_ratio"],10.0); self.assertGreater(record["cross_commit_moe_ratio"],20.0); self.assertFalse(record["feature_018_kernel_selected"]); assert_public_safe(record); subprocess.run([sys.executable,str(SCRIPT),"--check"],cwd=ROOT,check=True)
if __name__=="__main__": unittest.main()
