#!/usr/bin/env python3

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class PostIq3BottleneckTests(unittest.TestCase):
    def test_generator_parses_and_uses_committed_inputs_only(self) -> None:
        source = (ROOT / "scripts/research/analyze_glm52_post_iq3_bottlenecks.py").read_text()
        ast.parse(source)
        self.assertNotIn("PULSARMLX_GLM_GGUF", source)
        self.assertIn("post-f018-output-head-profile-0001.json", source)
        self.assertIn("post-f018-dense-multilayer-profile-0001.json", source)

    def test_decision_is_reuse_before_third_kernel(self) -> None:
        source = (ROOT / "scripts/research/analyze_glm52_post_iq3_bottlenecks.py").read_text()
        self.assertIn('"outcome": "B"', source)
        self.assertIn('"third_kernel_admitted": False', source)
        self.assertIn('"fresh_p1_run": False', source)


if __name__ == "__main__":
    unittest.main()
