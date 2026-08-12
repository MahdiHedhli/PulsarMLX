"""Negative tests for the banked F017 M1-D attempt-3 PASS validator."""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/research/validate_f017_m1d_attempt3_evidence.py"
EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-m1-d-real-projection-attempt-3-v1.json"
SPEC = importlib.util.spec_from_file_location("attempt3_evidence", SCRIPT)
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validator)


class Attempt3EvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.valid = json.loads(EVIDENCE.read_text())

    def test_banked_evidence_is_valid(self) -> None:
        validator.validate(self.valid)

    def test_repeat_divergence_fails(self) -> None:
        value = copy.deepcopy(self.valid)
        value["execution"]["numerical"]["repeat_integrity"]["outputs"][5]["output_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            validator.validate(value)

    def test_oracle_order_regression_fails(self) -> None:
        value = copy.deepcopy(self.valid)
        ordering = value["execution"]["numerical"]["oracle_ordering"]
        ordering["candidate_started_at"] = ordering["oracle_completed_at"]
        with self.assertRaises(ValueError):
            validator.validate(value)

    def test_dispatch_or_lifecycle_mismatch_fails(self) -> None:
        for mutation in ("dispatch", "lifecycle"):
            value = copy.deepcopy(self.valid)
            if mutation == "dispatch":
                value["execution"]["dispatch"]["native"] = 9
            else:
                value["lifecycle"]["post"]["derived_destroyed"] = 9
            with self.assertRaises(ValueError):
                validator.validate(value)

    def test_config_or_pass_mutation_fails(self) -> None:
        for mutation in ("config", "pass"):
            value = copy.deepcopy(self.valid)
            if mutation == "config":
                value["identity"]["execution_config_sha256"] = "0" * 64
            else:
                value["result"]["classification"] = "FAIL_NUMERICAL_BEHAVIORAL"
            with self.assertRaises(ValueError):
                validator.validate(value)


if __name__ == "__main__":
    unittest.main()
