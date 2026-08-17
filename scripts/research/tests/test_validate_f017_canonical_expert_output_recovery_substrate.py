"""Fail-closed tests for the public recovery-substrate evidence."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.research import validate_f017_canonical_expert_output_recovery_substrate as validator


ROOT = Path(__file__).resolve().parents[3]


class SubstrateValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = validator.load(ROOT / validator.CONTRACT)
        self.evidence = validator.load(ROOT / validator.EVIDENCE)

    def test_committed_substrate_validates(self) -> None:
        result = validator.validate(ROOT, self.contract, self.evidence)
        self.assertEqual(result["result"], "RECOVERY_EXECUTION_SUBSTRATE_VALID")
        self.assertEqual(result["ledger"], 139)

    def test_component_source_mutation_fails(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["component_bindings"]["event_executor"]["source_sha256"] = "0" * 64
        with self.assertRaisesRegex(validator.SubstrateValidationError, "component source"):
            validator.validate(ROOT, mutated, self.evidence)

    def test_retry_mutation_fails(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["access_contract"]["automatic_retry"] = True
        with self.assertRaisesRegex(validator.SubstrateValidationError, "access contract"):
            validator.validate(ROOT, mutated, self.evidence)

    def test_real_path_capability_mutation_fails(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["test_isolation"]["checkpoint_path_resolver_present"] = True
        with self.assertRaisesRegex(validator.SubstrateValidationError, "test isolation"):
            validator.validate(ROOT, mutated, self.evidence)

    def test_failure_matrix_mutation_fails(self) -> None:
        mutated = copy.deepcopy(self.evidence)
        mutated["failure_matrix"]["required_cases_passed"] = 23
        with self.assertRaisesRegex(validator.SubstrateValidationError, "failure matrix"):
            validator.validate(ROOT, self.contract, mutated)

    def test_historical_mutation_fails(self) -> None:
        mutated = copy.deepcopy(self.evidence)
        mutated["historical_immutability"]["DPREFIX_REAL_2"] = "ACCEPTED"
        with self.assertRaisesRegex(validator.SubstrateValidationError, "historical"):
            validator.validate(ROOT, self.contract, mutated)

    def test_duplicate_json_key_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
            with self.assertRaisesRegex(validator.SubstrateValidationError, "duplicate key"):
                validator.load(path)


if __name__ == "__main__":
    unittest.main()
