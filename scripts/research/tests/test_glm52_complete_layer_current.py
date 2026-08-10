#!/usr/bin/env python3
"""Checkpoint-free contracts for the current complete-layer harness."""
from __future__ import annotations
import sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]; sys.path.insert(0,str(ROOT/"scripts/research"))
from benchmark_glm52_complete_layer_current import _summaries  # noqa: E402
class CompleteLayerCurrentTests(unittest.TestCase):
    def test_summary_accepts_zero_stages(self):
        sample={field:1.0 for field in ("total_seconds","attention_seconds","moe_seconds","boundary_overhead_seconds","dense_total_seconds","dense_storage_seconds","dense_dequant_seconds","dense_buffer_seconds","dense_build_seconds","dense_matvec_seconds")}; sample["moe_stage_totals"]={field:0.0 for field in ("activation_swiglu_seconds","weighting_seconds","router_projection_seconds","router_selection_seconds","routed_aggregation_seconds","shared_aggregation_seconds","explicit_stage_seconds","uninstrumented_residual_seconds")}; sample["moe_stage_totals"].update({scope:{field:0.0 for field in ("storage_read_seconds","dequant_seconds","contiguous_buffer_seconds","mlx_matrix_construct_seconds","mlx_matrix_eval_seconds","mlx_matvec_seconds","cleanup_seconds")} for scope in ("routed_matrix_stages","shared_matrix_stages")}); self.assertEqual(_summaries([sample])["total_seconds"]["sample_count"],1)
if __name__=="__main__": unittest.main()
