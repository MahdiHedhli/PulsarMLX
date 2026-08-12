from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/research/validate_f017_m1d_attempt2_evidence.py"
EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-m1-d-real-projection-attempt-2-v1.json"
SPEC = importlib.util.spec_from_file_location("m1d_attempt2_evidence", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def document() -> dict:
    return json.loads(EVIDENCE.read_text())


class Attempt2EvidenceTests(unittest.TestCase):
    def test_banked_rejection_is_valid(self) -> None:
        MODULE.validate(document())

    def test_invalid_rejection_evidence_fails_closed(self) -> None:
        mutations = [
            ("provenance", "real_reference_preparer_source_sha256", "b" * 64),
            ("preparer", "checkpoint_opened", True),
            ("preparer", "matrix_payload_read_count", 1),
            ("execution", "candidate_started", True),
            ("execution", "native_dispatch_count", 1),
            ("result", "authorization_consumed", False),
            ("result", "retry_permitted", True),
        ]
        for section, field, value in mutations:
            candidate = copy.deepcopy(document())
            candidate[section][field] = value
            with self.assertRaises(ValueError):
                MODULE.validate(candidate)

    def test_duplicate_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate key"):
            json.loads('{"attempt": 2, "attempt": 3}', object_pairs_hook=MODULE.reject_duplicate_keys)


if __name__ == "__main__":
    unittest.main()
