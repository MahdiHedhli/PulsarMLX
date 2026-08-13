from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-m1-e-real-expert-attempt-2-v1.json"
SPEC = importlib.util.spec_from_file_location(
    "m1e_attempt2_validator", ROOT / "scripts/research/validate_f017_m1e_attempt2_evidence.py"
)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class Attempt2EvidenceTest(unittest.TestCase):
    def test_banked_rejection_is_valid(self) -> None:
        validator.validate(EVIDENCE)

    def test_false_execution_claim_fails(self) -> None:
        document = json.loads(EVIDENCE.read_text())
        document["execution"]["native_matvec_dispatch_count"] = 30
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(document))
            with self.assertRaisesRegex(ValueError, "native_matvec_dispatch_count"):
                validator.validate(path)

    def test_duplicate_and_private_path_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            duplicate = Path(directory) / "duplicate.json"
            duplicate.write_text('{"schema":"a","schema":"b"}')
            with self.assertRaisesRegex(ValueError, "duplicate key"):
                validator.validate(duplicate)
            document = json.loads(EVIDENCE.read_text())
            document["private_path"] = "/private/example"
            leaked = Path(directory) / "leaked.json"
            leaked.write_text(json.dumps(document))
            with self.assertRaisesRegex(ValueError, "private path"):
                validator.validate(leaked)


if __name__ == "__main__":
    unittest.main()
