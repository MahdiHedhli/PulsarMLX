from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from scripts.research import validate_f017_weighted_moe_aggregate_theorem as validator


class WeightedMoeAggregateFreezeValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = validator.load_json(validator.CONTRACT)

    def test_committed_contract_and_history_pass_before_freeze_evidence(self) -> None:
        validator.validate_contract(self.contract)
        validator.validate_implementation()
        validator.validate_history()

    def test_duplicate_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"schema":"one","schema":"two"}')
            with self.assertRaisesRegex(validator.AggregateFreezeValidationError, "duplicate key"):
                validator.load_json(path)

    def test_budget_mutation_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["acceptance"]["max_absolute_error"] = 0.03125
        with self.assertRaisesRegex(validator.AggregateFreezeValidationError, "accepted budget"):
            validator.validate_contract(mutated)

    def test_coefficient_pass_substitution_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["authority_separation"]["coefficient_qualification"] = "PASS"
        with self.assertRaisesRegex(validator.AggregateFreezeValidationError, "coefficient authority"):
            validator.validate_contract(mutated)

    def test_real_output_evaluation_claim_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["anti_fitting"]["real_f017_expert_outputs_evaluated"] = True
        with self.assertRaisesRegex(validator.AggregateFreezeValidationError, "anti-fitting"):
            validator.validate_contract(mutated)

    def test_missing_output_evidence_contract_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["required_future_evidence"] = mutated["required_future_evidence"][:-1]
        with self.assertRaisesRegex(validator.AggregateFreezeValidationError, "future evidence"):
            validator.validate_contract(mutated)

    def test_unreviewed_tolerance_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["acceptance"]["additional_tolerances"] = [0.01]
        with self.assertRaisesRegex(validator.AggregateFreezeValidationError, "unreviewed tolerance"):
            validator.validate_contract(mutated)

    def test_private_path_leak_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["scope"] = "/Users/private/expert-output.bin"
        with self.assertRaisesRegex(validator.AggregateFreezeValidationError, "path leak"):
            validator.validate_contract(mutated)

    def test_prior_authority_is_hash_checked(self) -> None:
        self.assertEqual(
            validator.sha256_path(validator.PRIOR_QUALIFICATION_EVIDENCE),
            validator.PRIOR_QUALIFICATION_EVIDENCE_SHA256,
        )


if __name__ == "__main__":
    unittest.main()
