#!/usr/bin/env python3
"""CI-safe semantic validator for the post-MoE P2 record."""
from __future__ import annotations
import json, subprocess, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "docs/research/glm52/raw/post-f016-inference-p2-moe-vector-0001.json"
ANALYSIS = ROOT / "docs/research/glm52/raw/post-f016-inference-p2-moe-vector-analysis-0001.json"
SCRIPT = ROOT / "scripts/research/analyze_glm52_moe_p2.py"
sys.path.insert(0, str(ROOT / "scripts/research"))
from glm52_telemetry import assert_public_safe  # noqa: E402


def _load(path):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out: raise ValueError(f"duplicate key: {key}")
            out[key] = value
        return out
    return json.loads(path.read_text(), object_pairs_hook=unique)


class MoeP2RecordTests(unittest.TestCase):
    def test_exact_p2_and_analysis(self):
        raw, analysis = _load(RAW), _load(ANALYSIS)
        self.assertEqual(raw["actual_status"], "passed")
        self.assertFalse(raw["source_dirty"])
        self.assertEqual(raw["generated_token_ids"], [9703, 21615, 220])
        self.assertTrue(raw["matches_golden_prefix"])
        self.assertEqual(raw["dense_read_mode"], "whole_matrix_numpy_q5_q8_q6_head_numpy")
        self.assertEqual(len(raw["timings"]), 3)
        self.assertTrue(all(len(stack["layers"]) == 79 for stack in raw["timings"]))
        self.assertTrue(all(len(stack["layers"]) == 76 for stack in raw["routing"]))
        self.assertTrue(all(len(layer["expert_ids"]) == 8 for stack in raw["routing"] for layer in stack["layers"]))
        self.assertEqual(raw["expert_cache"]["decoded_cache_hits"], 456)
        self.assertEqual(raw["expert_cache"]["resident_entries"], 228)
        for key in ("cpu_fallbacks", "evictions", "admission_rejections"): self.assertEqual(raw["expert_cache"][key], 0)
        self.assertTrue(all(stack["resource_after"]["level"] == "normal" for stack in raw["timings"]))
        self.assertEqual(analysis["actual_status"], "passed")
        self.assertTrue(analysis["decision"]["feature_018_scope_sufficient"])
        self.assertEqual(analysis["decision"]["feature_018_first_kernel_candidate"]["quantization"], "IQ2_XXS")
        self.assertFalse(analysis["decision"]["another_full_model_run_required"])
        self.assertLess(analysis["modeled_warm_quantization_opportunity"]["relative_error_fraction"], 0.05)
        subprocess.run(["git", "cat-file", "-e", f"{raw['source_commit']}^{{commit}}"], cwd=ROOT, check=True)
        guarded = json.loads(json.dumps(raw))
        for stack in guarded["timings"]: stack.pop("token", None)
        for stack in guarded["routing"]: stack.pop("token", None)
        guarded_analysis = json.loads(json.dumps(analysis))
        for stack in guarded_analysis["timing"]["stacks"]: stack.pop("token", None)
        assert_public_safe(guarded); assert_public_safe(guarded_analysis)
        subprocess.run([sys.executable, str(SCRIPT), "--check"], cwd=ROOT, check=True)


if __name__ == "__main__": unittest.main()
