#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_f017_checkpoint_identity_design_v7 import validate


class DesignTests(unittest.TestCase):
    def test_design_authorities(self):
        self.assertEqual(validate()["result"], "PASS")


if __name__ == "__main__":
    unittest.main()
