#!/usr/bin/env python3
"""CI-safe validation for the exact post-trunk P1 and derived profile."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))
from glm52_telemetry import assert_public_safe  # noqa: E402

RECORD = ROOT / "docs/research/glm52/raw/post-f016-inference-p1-trunk-q6-0001.json"
RANKING = ROOT / "docs/research/glm52/raw/post-f016-p1-trunk-q6-expert-hotspots-0001.json"
RANK_TABLE = ROOT / "docs/research/glm52/tables/post-f016-p1-trunk-q6-expert-hotspots-0001.md"
PROFILE = ROOT / "docs/research/glm52/raw/post-f016-p1-trunk-profile-0001.json"
PROFILE_TABLE = ROOT / "docs/research/glm52/tables/post-f016-p1-trunk-profile-0001.md"
RANKER = ROOT / "scripts/research/rank_glm52_quant_hotspots.py"
ANALYZER = ROOT / "scripts/research/analyze_glm52_trunk_p1.py"
SOURCE = "9b6ab666c9dc89eda9b2ddf284a9a2767516d87e"


class Glm52TrunkP1RecordTests(unittest.TestCase):
    def test_p1_semantics_and_generated_profiles(self) -> None:
        record = json.loads(RECORD.read_text(), object_pairs_hook=_unique)
        profile = json.loads(PROFILE.read_text(), object_pairs_hook=_unique)
        self.assertEqual(record["actual_status"], "passed")
        self.assertEqual(record["source_commit"], SOURCE)
        self.assertFalse(record["source_dirty"])
        self.assertEqual(record["generated_token_ids"], [9703, 21615])
        self.assertTrue(record["matches_golden_prefix"])
        self.assertEqual(record["dense_read_mode"], "whole_matrix_numpy_q5_q8_q6_head_numpy")
        self.assertEqual(record["decoder_mode"], "numpy_vectorized")
        cache = record["expert_cache"]
        self.assertEqual(cache["backend"], "mlx")
        self.assertIn("gpu", cache["device"])
        self.assertEqual(cache["cpu_fallbacks"], 0)
        self.assertEqual(cache["decoded_cache_hits"], 228)
        self.assertEqual(cache["evictions"], 0)
        self.assertEqual(cache["admission_rejections"], 0)
        self.assertEqual(cache["resident_entries"], 228)
        self.assertEqual(len(record["timings"]), 2)
        self.assertTrue(all(len(stack["layers"]) == 79 for stack in record["timings"]))
        self.assertTrue(all(stack["resource_after"]["level"] == "normal" for stack in record["timings"]))
        self.assertEqual(len(record["routing"]), 2)
        self.assertTrue(all(len(stack["layers"]) == 76 for stack in record["routing"]))
        self.assertTrue(all(len(layer["expert_ids"]) == 8 for stack in record["routing"] for layer in stack["layers"]))
        self.assertEqual(profile["actual_status"], "passed")
        self.assertFalse(profile["decision"]["another_full_model_run_required_in_this_sprint"])
        self.assertFalse(profile["decision"]["feature_018_first_kernel_selected"])
        self.assertGreater(profile["timing"]["terminal_state_advance_stack_seconds"], 0)
        subprocess.run(["git", "cat-file", "-e", f"{SOURCE}^{{commit}}"], cwd=ROOT, check=True)
        guarded = json.loads(json.dumps(record))
        for stack in guarded["timings"]:
            stack.pop("token", None)
        for stack in guarded["routing"]:
            stack.pop("token", None)
        assert_public_safe(guarded)
        assert_public_safe(profile)
        subprocess.run([sys.executable, str(RANKER), "--source", str(RECORD), "--json-out", str(RANKING), "--table-out", str(RANK_TABLE), "--check"], cwd=ROOT, check=True)
        subprocess.run([sys.executable, str(ANALYZER), "--source", str(RECORD), "--ranking", str(RANKING), "--json-out", str(PROFILE), "--table-out", str(PROFILE_TABLE), "--check"], cwd=ROOT, check=True)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


if __name__ == "__main__":
    unittest.main()
