from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.research import validate_f017_selected_weight_qualification as validation


ROOT = Path(__file__).resolve().parents[3]


class SelectedWeightQualificationValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evidence = validation.load_json(validation.EVIDENCE)

    def test_committed_evidence_validates(self) -> None:
        validation.validate_evidence(self.evidence)

    def test_missing_or_stale_result_fails_closed(self) -> None:
        for mutation in ("qualification", "membership", "isolation"):
            bad = copy.deepcopy(self.evidence)
            bad.pop(mutation)
            with self.assertRaises(validation.QualificationValidationError):
                validation.validate_evidence(bad)
        bad = copy.deepcopy(self.evidence)
        bad["qualification"]["mathematical_pass_count"] = 8
        with self.assertRaises(validation.QualificationValidationError):
            validation.validate_evidence(bad)

    def test_identity_and_historical_mutations_fail_closed(self) -> None:
        bad = copy.deepcopy(self.evidence)
        bad["authority"]["weight_acceptance_contract_sha256"] = "0" * 64
        with self.assertRaises(validation.QualificationValidationError):
            validation.validate_evidence(bad)
        bad = copy.deepcopy(self.evidence)
        bad["historical_immutability"]["DPREFIX_REAL_2"] = "ACCEPTED"
        with self.assertRaises(validation.QualificationValidationError):
            validation.validate_evidence(bad)

    def test_duplicate_key_is_rejected(self) -> None:
        with self.assertRaises(validation.QualificationValidationError):
            json.loads('{"schema":"a","schema":"b"}', object_pairs_hook=validation.reject_duplicates)

    def test_private_path_is_rejected(self) -> None:
        bad = copy.deepcopy(self.evidence)
        bad["next_action"] = "/Users/private/package"
        with self.assertRaises(validation.QualificationValidationError):
            validation.validate_evidence(bad)


if __name__ == "__main__":
    unittest.main()
