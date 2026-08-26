from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = ROOT / "scripts/research/validate_f017_numerical_output_interface_design_v1.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("f017_output_design", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class NumericalOutputInterfaceDesignTests(unittest.TestCase):
    def test_mechanical_design_gates(self):
        result = load_validator().validate()
        self.assertEqual(result["result"], "PASS")
        self.assertGreaterEqual(result["design_mutations_rejected"], 90)
        self.assertEqual(result["unexpected_passes"], 0)
        self.assertEqual(result["original_checkpoint_access"], 0)

    def test_cli_is_deterministic_json(self):
        command = [sys.executable, str(VALIDATOR), "--json"]
        first = subprocess.check_output(command, cwd=ROOT)
        second = subprocess.check_output(command, cwd=ROOT)
        self.assertEqual(first, second)
        self.assertEqual(json.loads(first)["result"], "PASS")


if __name__ == "__main__":
    unittest.main()
