from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "scripts/research/validate_f017_canonical_shared_expert_recovery_evidence.py"
SPEC = importlib.util.spec_from_file_location("shared_recovery_evidence", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SharedRecoveryEvidenceTests(unittest.TestCase):
    def test_banked_evidence_validates(self):
        self.assertEqual(len(MODULE.validate()), 64)


if __name__ == "__main__":
    unittest.main()
