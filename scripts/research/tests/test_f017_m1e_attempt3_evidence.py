from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-m1-e-real-expert-attempt-3-v1.json"
SPEC = importlib.util.spec_from_file_location(
    "m1e_attempt3_validator", ROOT / "scripts/research/validate_f017_m1e_attempt3_evidence.py"
)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class Attempt3EvidenceTest(unittest.TestCase):
    def mutate(self, callback) -> Path:
        document = json.loads(EVIDENCE.read_text())
        callback(document)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "invalid.json"
        path.write_text(json.dumps(document))
        return path

    def test_banked_acceptance_is_valid(self) -> None:
        validator.validate(EVIDENCE)

    def test_repeat_divergence_fails(self) -> None:
        path = self.mutate(lambda doc: doc["execution"]["numerical"]
                           ["expert_repeat_integrity"]["outputs"][5]
                           .__setitem__("final_output_sha256", "0" * 64))
        with self.assertRaisesRegex(ValueError, "repeat equality final_output_sha256"):
            validator.validate(path)

    def test_dispatch_mismatch_fails(self) -> None:
        path = self.mutate(lambda doc: doc["execution"]["dispatch"].__setitem__("native", 29))
        with self.assertRaisesRegex(ValueError, "dispatch"):
            validator.validate(path)

    def test_oracle_order_failure_fails(self) -> None:
        path = self.mutate(lambda doc: doc["execution"]["numerical"]
                           ["oracle_ordering"].__setitem__("structural_order_valid", False))
        with self.assertRaisesRegex(ValueError, "oracle structural order"):
            validator.validate(path)

    def test_lifecycle_mismatch_fails(self) -> None:
        path = self.mutate(lambda doc: doc["lifecycle"]["post"]
                           .__setitem__("managed_destroyed", 13))
        with self.assertRaisesRegex(ValueError, "managed lifecycle"):
            validator.validate(path)

    def test_duplicate_and_private_path_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            duplicate = Path(directory) / "duplicate.json"
            duplicate.write_text('{"schema":"a","schema":"b"}')
            with self.assertRaisesRegex(ValueError, "duplicate key"):
                validator.validate(duplicate)
        path = self.mutate(lambda doc: doc.__setitem__("private_path", "/private/example"))
        with self.assertRaisesRegex(ValueError, "private path"):
            validator.validate(path)


if __name__ == "__main__":
    unittest.main()
