#!/usr/bin/env python3

from __future__ import annotations

import sys
import subprocess
import unittest
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from benchmark_glm52_post_iq3_dense import group_operations  # noqa: E402
from glm52_dense_primitives import DenseOperationMetrics  # noqa: E402


class PostIq3DenseProfileTests(unittest.TestCase):
    def test_per_head_operations_group_without_losing_stage_or_slice_accounting(self) -> None:
        values = [
            DenseOperationMetrics(
                tensor="blk.3.attn_k_b.weight",
                quantization="Q8_0",
                rows=512,
                cols=192,
                encoded_bytes=104448,
                storage_read_count=1,
                storage_read_seconds=0.01,
                dequant_seconds=0.02,
                contiguous_buffer_seconds=0.001,
                mlx_matrix_build_seconds=0.003,
                mlx_matvec_seconds=0.004,
                total_seconds=0.04,
                read_mode="whole_matrix_numpy_q5_q8_q6_head_numpy",
                decoder_mode="numpy_vectorized_q8_0",
                slice_index=index,
            )
            for index in range(2)
        ]
        grouped = group_operations(values)
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["slice_count"], 2)
        self.assertEqual(grouped[0]["slice_indices"], [0, 1])
        self.assertEqual(grouped[0]["encoded_bytes"], 208896)
        self.assertAlmostEqual(grouped[0]["dequant_seconds"], 0.04)
        self.assertAlmostEqual(grouped[0]["total_seconds"], 0.08)

    def test_committed_multilayer_profile_and_table(self) -> None:
        raw = ROOT / "docs/research/glm52/raw/post-f018-dense-multilayer-profile-0001.json"
        table = ROOT / "docs/research/glm52/tables/post-f018-dense-multilayer-profile-0001.md"
        record = json.loads(raw.read_text())
        self.assertEqual(record["actual_status"], "passed")
        self.assertEqual(record["classification"], "golden_identical")
        self.assertEqual(record["protocol"]["layers"], [3, 8, 40, 78])
        self.assertTrue(all(layer["comparison"]["exact_f32_output_hash"] for layer in record["layers"]))
        self.assertTrue(all(layer["candidate_summaries"]["wall_seconds"]["sample_count"] == 10 for layer in record["layers"]))
        self.assertEqual(record["resource_before"]["level"], "normal")
        self.assertEqual(record["resource_after"]["level"], "normal")
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/research/analyze_glm52_post_iq3_dense.py"),
                "--check",
            ],
            cwd=ROOT,
            check=True,
        )


if __name__ == "__main__":
    unittest.main()
