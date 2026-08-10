#!/usr/bin/env python3

from __future__ import annotations

import ast
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


if __name__ == "__main__":
    unittest.main()
