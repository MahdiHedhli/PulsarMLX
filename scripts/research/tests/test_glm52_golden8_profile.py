#!/usr/bin/env python3
"""Checkpoint-free validation for the generated golden-eight closeout profile."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from glm52_telemetry import assert_public_safe  # noqa: E402

SCRIPT = ROOT / "scripts/research/analyze_glm52_golden8.py"
PROFILE = ROOT / "docs/research/glm52/raw/f016-golden8-derived-profile-0001.json"
TABLE = ROOT / "docs/research/glm52/tables/f016-golden8-derived-profile.md"


class Glm52Golden8ProfileTests(unittest.TestCase):
    def test_generated_profile_is_current_bounded_and_public_safe(self) -> None:
        subprocess.run([sys.executable, str(SCRIPT), "--check"], cwd=ROOT, check=True)
        profile = json.loads(PROFILE.read_text())
        self.assertEqual(profile["actual_status"], "passed")
        self.assertEqual(profile["generated_token_ids"], [9703, 21615, 220, 16, 13, 16, 16, 15, 15])
        self.assertEqual(profile["total"]["stack_count"], 9)
        self.assertEqual(profile["total"]["decoded_cache_hits"], 1_824)

        watcher = profile["watcher"]
        self.assertEqual(watcher["snapshot_count"], 8)
        self.assertEqual(watcher["valid_one_stack_interval_count"], 7)
        self.assertEqual(watcher["counter_reset_interval_count"], 0)
        self.assertFalse(watcher["earlier_overwritten_snapshots_reconstructed"])
        self.assertFalse(watcher["cold_only_snapshot_available"])
        self.assertFalse(watcher["first_warm_only_interval_available"])
        for interval in watcher["valid_one_stack_intervals"]:
            self.assertTrue(interval["cumulative_counters_monotonic"])
            for metrics in interval["expert_cache_delta"]["quantization_metrics"].values():
                self.assertTrue(all(value >= 0 for value in metrics.values()))

        cold = profile["cold"]
        self.assertEqual(
            cold["per_quant_status"],
            "unavailable_watcher_began_after_cold_and_first_warm",
        )
        self.assertGreater(cold["uninstrumented_residual_fraction"], 0.6)

        warm = profile["warm"]
        self.assertEqual(warm["sample_count"], 8)
        self.assertEqual(warm["per_quant_interval_coverage"], "tokens_2_through_8_only")
        self.assertEqual(warm["per_quant_scope"], "EXPERT-CACHE PATH ONLY")
        self.assertGreater(warm["uninstrumented_residual_fraction"]["median"], 0.8)
        self.assertEqual(warm["decoded_cache_hits_per_stack"], [228] * 8)
        self.assertTrue(all(level == "normal" for level in warm["resource_levels"]))
        ranked = warm["per_quant_ranked"]
        self.assertEqual(ranked[0]["quantization"], "IQ2_XXS")
        self.assertEqual(next(item for item in ranked if item["quantization"] == "Q6_K")["rank_by_mean_component_seconds"], 8)

        decisions = profile["decisions"]
        self.assertEqual(
            decisions["prefetch_storage"],
            "deferred_no_measured_warm_storage_dominance",
        )
        self.assertLess(decisions["warm_storage_fraction_of_stack_mean"], 0.01)
        self.assertFalse(decisions["feature_018_first_kernel_selected"])
        self.assertEqual(decisions["feature_018_title"], "018-direct-quantized-metal-runtime")

        table = TABLE.read_text()
        self.assertIn("EXPERT-CACHE PATH ONLY", table)
        self.assertIn("Cold per-quant attribution is unavailable", table)
        assert_public_safe(profile)


if __name__ == "__main__":
    unittest.main()
