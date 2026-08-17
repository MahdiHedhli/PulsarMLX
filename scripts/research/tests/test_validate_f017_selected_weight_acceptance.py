from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.research import validate_f017_selected_weight_acceptance as validator


ROOT = Path(__file__).resolve().parents[3]


class SelectedWeightFreezeValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = validator.load_json(validator.CONTRACT)

    def test_committed_contract_passes_before_evidence_is_installed(self) -> None:
        validator.validate_contract(self.contract)
        validator.validate_implementation()
        validator.validate_history()

    def test_duplicate_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"schema":"one","schema":"two"}')
            with self.assertRaisesRegex(validator.WeightFreezeValidationError, "duplicate key"):
                validator.load_json(path)

    def test_threshold_mutation_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["mathematical_acceptance"]["budget"] = 2.0e-5
        with self.assertRaisesRegex(validator.WeightFreezeValidationError, "mathematical budget"):
            validator.validate_contract(mutated)

    def test_engineering_as_truth_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["engineering_acceptance"]["engineering_is_mathematical_truth"] = True
        with self.assertRaisesRegex(validator.WeightFreezeValidationError, "engineering truth"):
            validator.validate_contract(mutated)

    def test_real_interval_evaluation_claim_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["anti_fitting"]["real_f017_weight_intervals_evaluated"] = True
        with self.assertRaisesRegex(validator.WeightFreezeValidationError, "anti-fitting"):
            validator.validate_contract(mutated)

    def test_unreviewed_aggregate_threshold_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["joint_normalization"]["additional_aggregate_width_threshold"] = 1.0e-5
        with self.assertRaisesRegex(validator.WeightFreezeValidationError, "aggregate threshold"):
            validator.validate_contract(mutated)

    def test_private_path_leak_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["scope"] = "/Users/private/package"
        with self.assertRaisesRegex(validator.WeightFreezeValidationError, "path leak"):
            validator.validate_contract(mutated)

    def test_prior_route_evidence_is_hash_checked_without_parsing_intervals(self) -> None:
        self.assertEqual(
            validator.sha256_path(validator.PRIOR_ROUTE_EVIDENCE),
            validator.PRIOR_ROUTE_EVIDENCE_SHA256,
        )


if __name__ == "__main__":
    unittest.main()
