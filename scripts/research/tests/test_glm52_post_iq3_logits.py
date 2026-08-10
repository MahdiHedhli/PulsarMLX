#!/usr/bin/env python3

from __future__ import annotations

import ast
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


if __name__ == "__main__":
    unittest.main()
