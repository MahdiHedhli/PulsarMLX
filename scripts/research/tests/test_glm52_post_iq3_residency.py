#!/usr/bin/env python3

from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class PostIq3ResidencyTests(unittest.TestCase):
    def test_runner_is_checkpoint_explicit_and_process_isolated(self) -> None:
        path = ROOT / "scripts/research/benchmark_glm52_post_iq3_residency.py"
        source = path.read_text()
        ast.parse(source)
        self.assertNotIn("Path.home", source)
        self.assertIn("PULSARMLX_GLM_GGUF", source)
        self.assertIn("one fresh process per measured candidate", source)

    def test_targets_and_lifecycles_are_bounded(self) -> None:
        source = (ROOT / "scripts/research/benchmark_glm52_post_iq3_residency.py").read_text()
        self.assertIn('"output.weight"', source)
        self.assertIn('"blk.78.attn_output.weight"', source)
        self.assertIn('("transient", "decoded_host_rebuild", "mlx_ready")', source)
        self.assertNotIn("golden-eight", source)

    def test_committed_q5_record_is_exact_and_resource_admitted(self) -> None:
        path = ROOT / "docs/research/glm52/raw/post-f018-late-attention-q5-residency-0001.json"
        record = json.loads(path.read_text())
        self.assertEqual(record["actual_status"], "passed")
        self.assertFalse(record["source"]["dirty"])
        self.assertEqual(record["binding"]["tensor"], "blk.78.attn_output.weight")
        self.assertEqual(record["binding"]["quantization"], "Q5_K")
        self.assertTrue(record["comparison"]["exact_output_hash_across_candidates"])
        self.assertEqual(len(record["comparison"]["output_f32_sha256"]), 1)
        self.assertEqual(
            [candidate["candidate"] for candidate in record["candidates"]],
            ["transient", "decoded_host_rebuild", "mlx_ready"],
        )
        for candidate in record["candidates"]:
            self.assertEqual(candidate["resource_after_setup"]["level"], "normal")
            self.assertEqual(candidate["resource_after_teardown"]["level"], "normal")
            self.assertEqual(candidate["summaries"]["total_seconds"]["sample_count"], 10)

    def test_committed_q4_record_matches_transient_baseline(self) -> None:
        path = ROOT / "docs/research/glm52/raw/post-f018-output-q4-residency-0001.json"
        record = json.loads(path.read_text())
        baseline = json.loads(
            (ROOT / "docs/research/glm52/raw/post-f018-output-head-profile-0001.json").read_text()
        )
        self.assertEqual(record["actual_status"], "passed")
        self.assertFalse(record["source"]["dirty"])
        self.assertEqual(record["binding"]["tensor"], "output.weight")
        self.assertEqual(record["binding"]["quantization"], "Q4_K")
        self.assertTrue(record["comparison"]["exact_output_hash_across_candidates"])
        self.assertEqual(
            record["comparison"]["output_f32_sha256"],
            baseline["determinism"]["output_f32_sha256"],
        )
        self.assertEqual(
            [candidate["candidate"] for candidate in record["candidates"]],
            ["decoded_host_rebuild", "mlx_ready"],
        )
        for candidate in record["candidates"]:
            self.assertEqual(candidate["resource_after_setup"]["level"], "normal")
            self.assertEqual(candidate["resource_after_teardown"]["level"], "normal")
            self.assertEqual(candidate["summaries"]["total_seconds"]["sample_count"], 10)


if __name__ == "__main__":
    unittest.main()
