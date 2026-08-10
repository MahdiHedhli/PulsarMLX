#!/usr/bin/env python3
"""CI-safe validation for the final bounded multi-layer MoE reprofile."""
from __future__ import annotations
import json, subprocess, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]; SCRIPT=ROOT/"scripts/research/analyze_glm52_moe_multilayer.py"; RECORD=ROOT/"docs/research/glm52/raw/post-f016-moe-multilayer-all-vector-analysis-0001.json"; sys.path.insert(0,str(ROOT/"scripts/research"))
from glm52_telemetry import assert_public_safe  # noqa: E402
class MoeMultilayerTests(unittest.TestCase):
    def test_analysis(self):
        record=json.loads(RECORD.read_text()); self.assertEqual(record["actual_status"],"passed"); self.assertEqual([row["layer"] for row in record["layers"]],[8,40,75,76,77,78]); self.assertEqual(record["retained_sample_count"],60); self.assertTrue(record["all_exact_f32_bits_against_scalar_reference"]); self.assertEqual(record["cpu_fallbacks"],0); self.assertEqual(record["evictions"],0); self.assertEqual(record["resource_levels"],["normal"]); self.assertEqual(len(record["top_20_routed_experts"]),20); self.assertEqual(record["decision"]["largest_measured_layer"],78); self.assertFalse(record["decision"]["feature_018_kernel_selected"]); assert_public_safe(record); subprocess.run([sys.executable,str(SCRIPT),"--check"],cwd=ROOT,check=True)
if __name__=="__main__": unittest.main()
