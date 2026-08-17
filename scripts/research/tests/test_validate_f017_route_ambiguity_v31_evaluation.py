from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

import validate_f017_route_ambiguity_v31_evaluation as validator


class RouteAmbiguityV31EvidenceValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = json.loads(validator.EVIDENCE.read_text())

    def validate(self, mutation=None) -> None:
        document = copy.deepcopy(self.document)
        if mutation is not None:
            mutation(document)
        validator.validate_document(document)

    def test_committed_evidence_passes(self) -> None:
        self.validate()

    def test_missing_pair_fails(self) -> None:
        with self.assertRaises(validator.ValidationError):
            self.validate(lambda d: d["evaluation"]["membership"]["pairs"].pop())

    def test_stale_pair_factor_fails(self) -> None:
        with self.assertRaises(validator.ValidationError):
            self.validate(lambda d: d["evaluation"]["membership"]["pairs"][0].__setitem__("mathematical_safety_factor", 999.0))

    def test_changed_top8_fails(self) -> None:
        with self.assertRaises(validator.ValidationError):
            self.validate(lambda d: d["evaluation"]["exact_route"]["selected_top8"].reverse())

    def test_weight_by_rank_substitution_fails(self) -> None:
        with self.assertRaises(validator.ValidationError):
            self.validate(lambda d: d["evaluation"]["selected_weights"].__setitem__("key_semantics", "rank"))

    def test_false_full_positive_disposition_fails(self) -> None:
        def mutation(document):
            document["result"] = "ROUTE INVARIANT OVER DPREFIX ORACLE AMBIGUITY"
            document["evaluation"]["route_insensitivity_disposition"] = document["result"]
        with self.assertRaises(validator.ValidationError):
            self.validate(mutation)

    def test_checkpoint_read_fails(self) -> None:
        with self.assertRaises(validator.ValidationError):
            self.validate(lambda d: d["isolation"].__setitem__("checkpoint_reads", 1))

    def test_ledger_mutation_fails(self) -> None:
        with self.assertRaises(validator.ValidationError):
            self.validate(lambda d: d["isolation"].__setitem__("real_payload_ledger_after", 140))

    def test_private_path_leak_fails(self) -> None:
        with self.assertRaises(validator.ValidationError):
            self.validate(lambda d: d["private_reuse"].__setitem__("path", "/Users/private/package"))

    def test_historical_reclassification_fails(self) -> None:
        with self.assertRaises(validator.ValidationError):
            self.validate(lambda d: d["historical_immutability"].__setitem__("DPREFIX_REAL_3", "ACCEPTED"))


if __name__ == "__main__":
    unittest.main()
