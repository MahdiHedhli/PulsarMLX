from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.research.validate_f017_routing_contract_v31 import (
    CONTRACT,
    EVIDENCE,
    FreezeValidationError,
    ROOT,
    load_json,
    validate_contract,
    validate_evidence,
    validate_freeze,
)


class RoutingV31FreezeValidationTests(unittest.TestCase):
    def test_committed_freeze_validates(self) -> None:
        validate_freeze()

    def test_duplicate_key_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"schema":"one","schema":"two"}\n')
            with self.assertRaisesRegex(FreezeValidationError, "duplicate key"):
                load_json(path)

    def test_missing_rounding_mechanism_rejected(self) -> None:
        contract = copy.deepcopy(load_json(CONTRACT))
        contract["outward_rounding"]["mechanism"] = "round-to-nearest"
        with self.assertRaisesRegex(FreezeValidationError, "outward-rounding"):
            validate_contract(contract)

    def test_ordered_top8_mutation_rejected(self) -> None:
        contract = copy.deepcopy(load_json(CONTRACT))
        contract["routing_semantics"]["ordered_top8_requirement"] = "PASS_REQUIRED"
        with self.assertRaisesRegex(FreezeValidationError, "ordered top-8"):
            validate_contract(contract)

    def test_private_path_leak_rejected(self) -> None:
        contract = copy.deepcopy(load_json(CONTRACT))
        contract["notes"] = "/Users/operator/private/antecedents/router_matrix.bin"
        with self.assertRaisesRegex(FreezeValidationError, "path leaked"):
            validate_contract(contract)

    def test_real_evaluation_mutation_rejected(self) -> None:
        evidence = copy.deepcopy(load_json(EVIDENCE))
        evidence["real_evaluation"]["performed"] = True
        with self.assertRaisesRegex(FreezeValidationError, "real evaluation"):
            validate_evidence(evidence)

    def test_ledger_mutation_in_evidence_rejected(self) -> None:
        evidence = copy.deepcopy(load_json(EVIDENCE))
        evidence["isolation"]["real_payload_ledger_after"] = 140
        with self.assertRaisesRegex(FreezeValidationError, "isolation"):
            validate_evidence(evidence)

    def test_artifact_hash_mutation_rejected(self) -> None:
        evidence = copy.deepcopy(load_json(EVIDENCE))
        evidence["artifacts"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(FreezeValidationError, "artifact identity"):
            validate_evidence(evidence)

    def test_contract_has_no_private_artifact_names(self) -> None:
        text = (ROOT / CONTRACT.relative_to(ROOT)).read_text()
        self.assertNotIn("antecedents/", text)
        self.assertNotIn("/Users/", text)

    def test_evidence_has_no_private_or_absolute_path(self) -> None:
        text = (ROOT / EVIDENCE.relative_to(ROOT)).read_text()
        self.assertNotIn("antecedents/", text)
        self.assertNotIn("/Users/", text)
        json.loads(text)


if __name__ == "__main__":
    unittest.main()
