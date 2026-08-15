import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-q4-k-real-byte-qualification-attempt-1-not-executed-v1.json"
ATTEMPT = ROOT / "docs/architecture/reviews/evidence/f017-q4-k-attempt-ledger-v1.json"
CONFIG = ROOT / "docs/architecture/reviews/evidence/f017-q4-k-execution-config-v1.json"
AUTH = ROOT / "docs/architecture/reviews/evidence/f017-q4-k-authorization-binding-v1.json"


def load(path: Path):
    def reject_duplicates(pairs):
        value = {}
        for key, child in pairs:
            if key in value:
                raise ValueError(f"duplicate key: {key}")
            value[key] = child
        return value

    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Q4KNotExecutedPreflightTests(unittest.TestCase):
    def test_authority_is_fail_closed_and_evidence_matches(self):
        evidence, attempt, config, auth = map(load, (EVIDENCE, ATTEMPT, CONFIG, AUTH))
        authorized_attempts = [
            item for item in attempt["attempts"]
            if item.get("attempt_id") == "Q4K-REAL-1"
            and item.get("authorized") is True
            and item.get("consumed") is False
        ]
        self.assertEqual([], authorized_attempts)
        self.assertFalse(config["execution_authorized"])
        self.assertFalse(auth["execution_authorized"])
        self.assertEqual("Q4_K_NOT_EXECUTED", evidence["verdict"])
        self.assertEqual("AUTHORIZATION_BINDING", evidence["failed_preflight"]["classification"])
        self.assertFalse(evidence["attempt_state"]["consumed"])
        self.assertEqual(0, evidence["execution_accounting"]["tensor_payloads"])
        self.assertEqual({"before": 57, "after": 57, "event_appended": False}, evidence["ledger"])

    def test_control_artifact_hashes_are_exact(self):
        evidence = load(EVIDENCE)["verified_bindings"]
        self.assertEqual(evidence["execution_config_sha256"], sha256(CONFIG))
        self.assertEqual(evidence["authorization_binding_sha256"], sha256(AUTH))

    def test_operator_text_cannot_bypass_unpopulated_attempt_ledger(self):
        attempt, config, auth = map(load, (ATTEMPT, CONFIG, AUTH))
        operator_instruction_present = True
        machine_authorized = bool(attempt["attempts"]) and config["execution_authorized"] and auth["execution_authorized"]
        self.assertTrue(operator_instruction_present)
        self.assertFalse(machine_authorized)

    def test_target_block_arithmetic(self):
        target = load(EVIDENCE)["verified_bindings"]["target"]
        self.assertEqual(target["element_count"], target["logical_shape"][0] * target["logical_shape"][1])
        self.assertEqual(target["block_count"], target["element_count"] // target["elements_per_block"])
        self.assertEqual(target["packed_length"], target["block_count"] * target["packed_bytes_per_block"])

    def test_public_evidence_has_no_absolute_private_path(self):
        evidence = EVIDENCE.read_text()
        self.assertNotIn("/Users/", evidence)
        self.assertNotIn("file://", evidence)

    def test_schema_and_evidence_required_surface(self):
        schema = load(ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-q4-k-not-executed-evidence-v1.schema.json")
        evidence = load(EVIDENCE)
        self.assertEqual(schema["properties"]["verdict"]["const"], evidence["verdict"])
        self.assertEqual(set(schema["required"]), set(evidence))
        self.assertEqual(12, evidence["failed_preflight"]["condition"])


if __name__ == "__main__":
    unittest.main()
