import copy
import json
import unittest
from pathlib import Path

from scripts.research.f017_identity_gate_v2 import validate_contract

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-identity-gate-contract-v2.json"


class IdentityGateV2Tests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads(CONTRACT.read_text())

    def test_contract(self):
        validate_contract(self.document)

    def test_missing_mechanism_rejected(self):
        changed = copy.deepcopy(self.document)
        del changed["gate_audit"][0]["mechanism"]
        with self.assertRaisesRegex(ValueError, "fields"):
            validate_contract(changed)

    def test_blas_exact_sha_rejected(self):
        changed = copy.deepcopy(self.document)
        gate = next(item for item in changed["gate_audit"] if item["reproducibility_class"] == "BOUNDED_CLASS")
        gate["comparison_rule"] = "SHA-256 exact equality"
        with self.assertRaisesRegex(ValueError, "bounded"):
            validate_contract(changed)

    def test_persisted_authority_cannot_be_replaced_by_recompute(self):
        changed = copy.deepcopy(self.document)
        gate = next(item for item in changed["gate_audit"] if item["reproducibility_class"] == "PERSISTED_AUTHORITY")
        gate["comparison_rule"] = "recomputed SHA-256 exact equality"
        with self.assertRaisesRegex(ValueError, "persisted"):
            validate_contract(changed)

    def test_real3_history_required(self):
        changed = copy.deepcopy(self.document)
        changed["historical_real3_rejected_unchanged"] = False
        with self.assertRaisesRegex(ValueError, "REAL-3"):
            validate_contract(changed)


if __name__ == "__main__":
    unittest.main()
