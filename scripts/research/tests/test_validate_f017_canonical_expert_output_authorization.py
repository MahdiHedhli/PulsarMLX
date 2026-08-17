"""Fail-closed tests for the canonical expert-output recovery authorization."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.research import validate_f017_canonical_expert_output_authorization as validator


ROOT = Path(__file__).resolve().parents[3]


class CanonicalExpertOutputAuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = validator.load_json(ROOT / validator.CONTRACT_PATH)
        self.evidence = validator.load_json(ROOT / validator.EVIDENCE_PATH)

    def test_committed_package_validates(self) -> None:
        result = validator.validate_documents(ROOT, self.contract, self.evidence)
        self.assertEqual(result["inventory_count"], 24)
        self.assertEqual(result["packed_bytes"], 90_439_680)

    def test_duplicate_expert_fails(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["selected_expert_ids"][-1] = mutated["selected_expert_ids"][0]
        with self.assertRaisesRegex(validator.AuthorizationValidationError, "selected expert"):
            validator.validate_documents(ROOT, mutated, self.evidence)

    def test_offset_mutation_fails(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["payload_inventory"][0]["offset"] += 1
        with self.assertRaisesRegex(validator.AuthorizationValidationError, "payload inventory"):
            validator.validate_documents(ROOT, mutated, self.evidence)

    def test_extra_payload_fails(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["payload_inventory"].append(copy.deepcopy(mutated["payload_inventory"][0]))
        with self.assertRaisesRegex(validator.AuthorizationValidationError, "payload inventory"):
            validator.validate_documents(ROOT, mutated, self.evidence)

    def test_shard_open_budget_mutation_fails(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["shard_access"]["maximum_opens"] = 2
        with self.assertRaisesRegex(validator.AuthorizationValidationError, "shard"):
            validator.validate_documents(ROOT, mutated, self.evidence)

    def test_ledger_mutation_fails(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["ledger"]["successful_after"] = 164
        with self.assertRaisesRegex(validator.AuthorizationValidationError, "ledger"):
            validator.validate_documents(ROOT, mutated, self.evidence)

    def test_premature_execution_authority_fails(self) -> None:
        mutated = copy.deepcopy(self.evidence)
        mutated["authorization_state"]["execution_authorized"] = True
        with self.assertRaisesRegex(validator.AuthorizationValidationError, "authorization state"):
            validator.validate_documents(ROOT, self.contract, mutated)

    def test_known_hash_cannot_be_invented(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["payload_inventory"][0]["expected_packed_sha256"] = "0" * 64
        with self.assertRaisesRegex(validator.AuthorizationValidationError, "payload inventory"):
            validator.validate_documents(ROOT, mutated, self.evidence)

    def test_output_identity_and_size_mutations_fail(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["output_retention"]["outputs"][0]["expert_id"] = 10
        with self.assertRaisesRegex(validator.AuthorizationValidationError, "output retention"):
            validator.validate_documents(ROOT, mutated, self.evidence)
        mutated = copy.deepcopy(self.contract)
        mutated["output_retention"]["outputs"][0]["byte_length"] = 24_575
        with self.assertRaisesRegex(validator.AuthorizationValidationError, "output retention"):
            validator.validate_documents(ROOT, mutated, self.evidence)

    def test_private_absolute_path_fails(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["shard_access"]["symbolic_private_path"] = "/" + "Users/example/checkpoint.gguf"
        with self.assertRaisesRegex(validator.AuthorizationValidationError, "private path"):
            validator.validate_documents(ROOT, mutated, self.evidence)

    def test_duplicate_json_key_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
            with self.assertRaisesRegex(validator.AuthorizationValidationError, "duplicate key"):
                validator.load_json(path)

    def test_historical_and_isolation_mutations_fail(self) -> None:
        mutated = copy.deepcopy(self.evidence)
        mutated["historical_immutability"]["DPREFIX_REAL_2"] = "ACCEPTED"
        with self.assertRaisesRegex(validator.AuthorizationValidationError, "historical"):
            validator.validate_documents(ROOT, self.contract, mutated)
        mutated = copy.deepcopy(self.evidence)
        mutated["isolation"]["checkpoint_reads"] = 1
        with self.assertRaisesRegex(validator.AuthorizationValidationError, "isolation"):
            validator.validate_documents(ROOT, self.contract, mutated)


if __name__ == "__main__":
    unittest.main()
