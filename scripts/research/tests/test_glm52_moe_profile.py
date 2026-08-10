#!/usr/bin/env python3
"""Checkpoint-free contracts for detailed MoE stage attribution."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))
from benchmark_glm52_moe_profile import stage_totals  # noqa: E402


def _event(projection: str, *, shared: bool, hit: bool) -> dict:
    return {
        "projection": projection,
        "shared": shared,
        "cache_hit": hit,
        "storage_read_seconds": 0.0 if hit else 1.0,
        "dequant_seconds": 0.0 if hit else 2.0,
        "contiguous_buffer_seconds": 0.0 if hit else 3.0,
        "mlx_matrix_construct_seconds": 0.0 if hit else 4.0,
        "mlx_matrix_eval_seconds": 0.0 if hit else 5.0,
        "mlx_matvec_seconds": 6.0,
        "cleanup_seconds": 0.0 if hit else 7.0,
    }


def _expert(expert_id: int, *, shared: bool, hit: bool) -> dict:
    return {
        "expert_id": expert_id,
        "shared": shared,
        "activation_swiglu_seconds": 0.5,
        "weighting_seconds": 0.25,
        "matrix_events": [
            _event(projection, shared=shared, hit=hit)
            for projection in ("gate", "up", "down")
        ],
    }


class MoeStageProfileTests(unittest.TestCase):
    def test_stage_totals_keep_routed_shared_and_residual_disjoint(self) -> None:
        detail = {
            "total_seconds": 1000.0,
            "ffn_norm_seconds": 1.0,
            "router_projection_seconds": 2.0,
            "router_selection_seconds": 3.0,
            "routed_experts": [_expert(index, shared=False, hit=False) for index in range(8)],
            "shared_expert": _expert(0, shared=True, hit=True),
            "routed_aggregation_seconds": 4.0,
            "shared_aggregation_seconds": 5.0,
            "residual_add_seconds": 6.0,
        }
        totals = stage_totals(detail)
        self.assertEqual(totals["routed_matrix_event_count"], 24)
        self.assertEqual(totals["shared_matrix_event_count"], 3)
        self.assertEqual(totals["shared_matrix_hit_count"], 3)
        self.assertEqual(totals["routed_matrix_stages"]["dequant_seconds"], 48.0)
        self.assertEqual(totals["shared_matrix_stages"]["dequant_seconds"], 0.0)
        self.assertGreater(totals["uninstrumented_residual_seconds"], 0.0)
        self.assertAlmostEqual(
            totals["explicit_stage_seconds"] + totals["uninstrumented_residual_seconds"],
            detail["total_seconds"],
        )


if __name__ == "__main__":
    unittest.main()
