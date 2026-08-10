#!/usr/bin/env python3
"""CI-safe validation for the exact layer-78 Q2_K MoE integration."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/research/analyze_glm52_moe_q2_integration.py"
RECORD = ROOT / "docs/research/glm52/raw/post-f016-moe-layer78-q2-analysis-0001.json"
sys.path.insert(0, str(ROOT / "scripts/research"))
from glm52_telemetry import assert_public_safe  # noqa: E402


class MoeQ2IntegrationTests(unittest.TestCase):
    def test_analysis(self) -> None:
        record = json.loads(RECORD.read_text())
        self.assertEqual(record["actual_status"], "passed")
        self.assertTrue(record["candidate"]["exact_f32_bits_against_scalar_reference"])
        self.assertEqual(record["candidate"]["retained_samples"], 10)
        self.assertEqual(record["candidate"]["cpu_fallbacks"], 0)
        self.assertEqual(record["candidate"]["evictions"], 0)
        self.assertEqual(record["candidate"]["resource_levels"], ["normal"])
        self.assertGreater(record["boundary_speedup"], 2.0)
        self.assertEqual(record["candidate"]["quantization_ranking"][0]["quantization"], "Q3_K")
        self.assertFalse(record["feature_018_kernel_selected"])
        assert_public_safe(record)
        subprocess.run([sys.executable, str(SCRIPT), "--check"], cwd=ROOT, check=True)


if __name__ == "__main__":
    unittest.main()
