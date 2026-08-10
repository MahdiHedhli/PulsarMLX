#!/usr/bin/env python3
"""CI-safe validator for routed-expert reuse evidence."""
from __future__ import annotations
import json, subprocess, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/research/analyze_glm52_expert_reuse.py"
RECORD = ROOT / "docs/research/glm52/raw/post-f016-routed-expert-reuse-analysis-0001.json"
sys.path.insert(0, str(ROOT / "scripts/research"))
from glm52_telemetry import assert_public_safe  # noqa: E402


class ExpertReuseRecordTests(unittest.TestCase):
    def test_exact_bounded_lifecycle_result(self):
        record = json.loads(RECORD.read_text())
        self.assertEqual(record["actual_status"], "passed")
        self.assertTrue(record["decision"]["decode_remains_largest_transient_stage"])
        self.assertFalse(record["decision"]["mlx_build_import_dominant"])
        self.assertTrue(record["decision"]["retained_mlx_matrix_has_material_reuse_benefit"])
        self.assertFalse(record["decision"]["safe_static_per_layer_cache_proven"])
        self.assertFalse(record["decision"]["feature_018_kernel_selected"])
        self.assertGreater(record["reuse_ratios"]["transient_to_mlx_ready_reuse"], 50.0)
        assert_public_safe(record)
        subprocess.run([sys.executable, str(SCRIPT), "--check"], cwd=ROOT, check=True)


if __name__ == "__main__":
    unittest.main()
