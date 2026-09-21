from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "scripts/research/validate_f017_oracle_independence.py"
SPEC = importlib.util.spec_from_file_location("f017_oracle_policy", PATH)
assert SPEC and SPEC.loader
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


class OracleIndependencePolicyTests(unittest.TestCase):
    def test_committed_generator_passes(self) -> None:
        policy.validate(ROOT / "scripts/research/generate_f017_independent_oracle.py")

    def reject(self, source: str) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "generator.py"
            path.write_text(source)
            with self.assertRaises(policy.IndependencePolicyError):
                policy.validate(path)

    def test_production_and_execution_dependencies_are_rejected(self) -> None:
        for source in [
            "import subprocess\n",
            "import mlx\n",
            "import ctypes\n",
            "import pulsar_mlx\n",
            "from pathlib import Path\nPath('checkpoint').read_bytes()\n",
            "import os\nos.system('cargo run')\n",
        ]:
            with self.subTest(source=source):
                self.reject(source)


if __name__ == "__main__":
    unittest.main()
