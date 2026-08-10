#!/usr/bin/env python3

from __future__ import annotations

import ast
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class PostIq3OutputHeadTests(unittest.TestCase):
    def test_runner_is_checkpoint_explicit_and_does_not_search_home(self) -> None:
        source = (ROOT / "scripts/research/benchmark_glm52_post_iq3_logits.py").read_text()
        tree = ast.parse(source)
        self.assertNotIn("Path.home", source)
        self.assertIn("PULSARMLX_GLM_GGUF", source)
        self.assertTrue(any(isinstance(node, ast.FunctionDef) and node.name == "benchmark" for node in ast.walk(tree)))

    def test_committed_record_is_complete_and_generated_table_matches(self) -> None:
        record_path = ROOT / "docs/research/glm52/raw/post-f018-output-head-profile-0001.json"
        table_path = ROOT / "docs/research/glm52/tables/post-f018-output-head-profile-0001.md"
        record = json.loads(record_path.read_text())

        self.assertEqual(record["actual_status"], "passed")
        self.assertFalse(record["source"]["dirty"])
        self.assertEqual(record["binding"]["tensor"], "output.weight")
        self.assertEqual(record["binding"]["quantization"], "Q4_K")
        self.assertEqual(record["binding"]["shape"], [6144, 154880])
        self.assertEqual(record["protocol"]["warmups"], 3)
        self.assertEqual(record["protocol"]["measured_samples"], 10)
        self.assertEqual(record["determinism"]["unique_output_hashes"], 1)
        self.assertEqual(record["summaries"]["total_seconds"]["sample_count"], 10)
        self.assertEqual(record["resource_before"]["level"], "normal")
        self.assertEqual(record["resource_after"]["level"], "normal")

        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/research/analyze_glm52_post_iq3_logits.py"),
                "--input",
                str(record_path),
                "--output",
                str(table_path),
                "--check",
            ],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()
