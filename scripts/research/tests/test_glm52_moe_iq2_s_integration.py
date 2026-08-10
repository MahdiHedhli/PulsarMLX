#!/usr/bin/env python3
"""CI-safe validation for the exact layer-8 IQ2_S MoE integration."""

from __future__ import annotations
import json, subprocess, sys, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]; SCRIPT=ROOT/"scripts/research/analyze_glm52_moe_iq2_s_integration.py"; RECORD=ROOT/"docs/research/glm52/raw/post-f016-moe-layer8-iq2-s-analysis-0001.json"
sys.path.insert(0,str(ROOT/"scripts/research"))
from glm52_telemetry import assert_public_safe  # noqa: E402


class MoeIQ2SIntegrationTests(unittest.TestCase):
    def test_analysis(self):
        record=json.loads(RECORD.read_text()); self.assertEqual(record["actual_status"],"passed"); self.assertTrue(record["exact_f32_bits_against_scalar_reference"]); self.assertEqual(record["retained_samples"],10); self.assertEqual(record["cpu_fallbacks"],0); self.assertEqual(record["evictions"],0); self.assertEqual(record["resource_levels"],["normal"]); self.assertGreater(record["boundary_speedup"],4.0); self.assertEqual(record["candidate"]["quantization_ranking"][0]["quantization"],"IQ4_XS"); self.assertFalse(record["feature_018_kernel_selected"]); assert_public_safe(record); subprocess.run([sys.executable,str(SCRIPT),"--check"],cwd=ROOT,check=True)


if __name__=="__main__": unittest.main()
