#!/usr/bin/env python3
"""Checkpoint-free validation for the golden-eight post-run calculations."""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from glm52_telemetry import assert_public_safe  # noqa: E402

SCRIPT = ROOT / "scripts/research/analyze_glm52_post_run.py"
RECORD = ROOT / "docs/research/glm52/raw/f016-golden8-post-run-calculations-0001.json"
INVENTORY = ROOT / "docs/research/glm52/raw/f016-gguf-trunk-inventory-0001.json"
REPORT = ROOT / "docs/research/glm52/POST_GOLDEN8_CALCULATIONS.md"
EXPERT_RE = re.compile(r"\.ffn_(?:down|gate|up)_(?:exps|shexp)\.weight$")


class Glm52PostRunCalculationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        subprocess.run([sys.executable, str(SCRIPT), "--check"], cwd=ROOT, check=True)
        cls.record = json.loads(RECORD.read_text())
        cls.inventory = json.loads(INVENTORY.read_text())

    def test_record_is_calculation_only_and_bound_to_committed_inputs(self) -> None:
        record = self.record
        self.assertEqual(record["actual_status"], "passed")
        self.assertTrue(record["calculation_only"])
        self.assertFalse(record["model_inference_executed"])
        self.assertEqual(
            record["sources"]["golden_source_commit"],
            "1a2ca76ee2df0f518bfc9ddbaafd31500a5e6a26",
        )
        self.assertEqual(record["already_verified_metrics"]["watcher_valid_one_stack_interval_count"], 7)
        self.assertEqual(record["already_verified_metrics"]["watcher_counter_reset_interval_count"], 0)
        self.assertEqual(record["already_verified_metrics"]["decoded_cache_hits"], 1_824)
        self.assertEqual(record["already_verified_metrics"]["cpu_fallbacks"], 0)
        self.assertEqual(record["already_verified_metrics"]["evictions"], 0)

    def test_user_visible_boundary_reconciles_without_calling_wall_time_token_eight(self) -> None:
        timing = self.record["user_visible_timing"]
        self.assertAlmostEqual(
            timing["total_evidence_wall_seconds"]
            - timing["terminal_state_advance_stack_seconds"],
            timing["time_through_token_eight_selection_wall_minus_terminal_seconds"],
            places=9,
        )
        self.assertAlmostEqual(
            timing["time_through_token_eight_selection_wall_minus_terminal_seconds"]
            - timing["time_through_token_eight_selection_recorded_components_seconds"],
            timing["unassigned_runner_bookkeeping_seconds"],
            places=9,
        )
        self.assertEqual(len(timing["generated_token_selection_records"]), 8)
        self.assertEqual(timing["tokens_2_through_8_inter_token_latency_seconds"]["sample_count"], 7)
        self.assertTrue(timing["wall_minus_terminal_is_upper_bound"])

    def test_per_layer_residual_and_cleanup_claim_are_bounded(self) -> None:
        analysis = self.record["per_layer_analysis"]
        self.assertEqual(analysis["residual_label"], "uninstrumented residual")
        self.assertEqual(len(analysis["cold_by_layer"]), 79)
        self.assertEqual(len(analysis["warm_by_layer"]), 79)
        for layer in analysis["warm_by_layer"]:
            samples = layer["warm_uninstrumented_residual_samples_seconds"]
            self.assertEqual(len(samples), 8)
            self.assertGreaterEqual(min(samples), 0.0)
            self.assertTrue(
                math.isclose(
                    layer["uninstrumented_residual_seconds"]["sample_variance"],
                    sum((value - sum(samples) / len(samples)) ** 2 for value in samples)
                    / (len(samples) - 1),
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
            )
        cleanup = self.record["cleanup_hypothesis"]
        self.assertIsNone(cleanup["pearson_residual_vs_transient_releases"])
        self.assertIsNone(cleanup["pearson_residual_vs_routed_matrix_misses"])
        self.assertFalse(cleanup["correlation_is_meaningful"])
        self.assertFalse(cleanup["causal_cleanup_cost_isolated"])

    def test_trunk_inventory_excludes_experts_and_reconciles(self) -> None:
        inventory = self.inventory
        tensors = inventory["tensors"]
        self.assertEqual(len(tensors), 1_353)
        self.assertEqual(inventory["excluded_expert_matrix_count"], 456)
        self.assertFalse(any(EXPERT_RE.search(tensor["name"]) for tensor in tensors))
        self.assertEqual(
            sum(tensor["compressed_bytes"] for tensor in tensors),
            inventory["total_compressed_bytes"],
        )
        self.assertEqual(
            sum(tensor["decoded_f32_bytes"] for tensor in tensors),
            inventory["total_decoded_f32_bytes"],
        )
        required = {
            "layer",
            "semantic_role",
            "name",
            "quantization",
            "dimensions",
            "compressed_bytes",
            "decoded_f32_bytes",
            "expected_touches_per_prompt_token",
            "expected_touches_per_decode_token",
            "token_invariant",
            "layer_specific",
            "natural_residency_candidate",
            "short_context_read_behavior",
        }
        self.assertTrue(all(required <= tensor.keys() for tensor in tensors))
        summary = self.record["trunk_inventory"]
        self.assertEqual(summary["tensor_count"], len(tensors))
        self.assertEqual(
            summary["machine_readable_inventory"],
            "docs/research/glm52/raw/f016-gguf-trunk-inventory-0001.json",
        )
        self.assertEqual(
            summary["machine_readable_inventory_sha256"],
            hashlib.sha256(INVENTORY.read_bytes()).hexdigest(),
        )

    def test_budgets_amplification_and_next_gate_remain_non_claiming(self) -> None:
        options = {
            row["option"]: row
            for row in self.record["trunk_residency_memory_budgets"]["options"]
        }
        self.assertEqual(options["B"]["admission"], "unsafe_exceeds_24_gib_reserve")
        self.assertEqual(options["F"]["admission"], "unsafe_exceeds_24_gib_reserve")
        amplification = self.record["row_read_request_amplification"]["prompt_token"]
        self.assertEqual(
            amplification["current_total_read_operations"],
            amplification["current_row_level_pread_calls"]
            + amplification["current_direct_tensor_read_calls"],
        )
        self.assertGreater(amplification["request_count_reduction_factor"], 1.0)
        self.assertIn(
            "no latency or speedup is inferred",
            self.record["row_read_request_amplification"]["interpretation"],
        )
        self.assertFalse(self.record["feature_018"]["first_kernel_selected"])
        self.assertFalse(self.record["another_full_m1_ultra_run_required_now"])

    def test_outputs_are_public_safe_and_report_is_explicit(self) -> None:
        assert_public_safe(self.record)
        assert_public_safe(self.inventory)
        report = REPORT.read_text()
        self.assertIn("calculation-only analysis with no model inference", report)
        self.assertIn("uninstrumented residual", report)
        self.assertIn("request arithmetic, not a speedup claim", report)
        self.assertIn("Another full M1 Ultra run is **not required now**", report)


if __name__ == "__main__":
    unittest.main()
