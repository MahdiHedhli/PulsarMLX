import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str) -> dict:
    return json.loads((EVIDENCE / name).read_text())


class Real3TerminalEvidenceTests(unittest.TestCase):
    def test_terminal_rejection_is_fail_closed_and_zero_read(self) -> None:
        raw = load("f017-dprefix-real3-rejected-oracle-state-identity-v1.json")
        state = raw["state"]
        self.assertEqual(raw["terminal_class"], "EVIDENCE_VALIDATION")
        self.assertEqual(raw["reason_code"], "ORACLE_STATE_IDENTITY_MISMATCH")
        self.assertEqual(raw["access"]["checkpoint_reads"], 0)
        self.assertEqual(raw["access"]["shard_opens"], 0)
        self.assertTrue(state["consumed"] and state["executed"])
        self.assertFalse(state["checkpoint_accessed"])
        self.assertEqual(state["ledger_before"], state["ledger_after"])
        self.assertEqual(state["ledger_after"], 139)
        self.assertFalse(state["automatic_retry"])
        self.assertFalse(state["automatic_m1f0_continuation"])

    def test_identity_gate_overrides_provisional_runtime_pass(self) -> None:
        raw = load("f017-dprefix-real3-rejected-oracle-state-identity-v1.json")
        gate = raw["oracle"]["release_identity_gate"]
        self.assertEqual(gate["expected_sha256"], "541d8dbcf459b49e9b5c69ae44f919a64c2eaaefa4f6daeb7e0d13443b521aff")
        self.assertEqual(gate["actual_sha256"], "ad71c3b10531283f55117b8b72f3f754653dfa74f6fbe96faf520f728432ac1a")
        self.assertFalse(gate["exact"])
        self.assertEqual(gate["result"], "FAIL_CLOSED")
        self.assertEqual(raw["evidence_validation"]["bound_runner_provisional_terminal_class"], "PASS")
        provisional = EVIDENCE / "f017-dprefix-real3-bound-runner-provisional-terminal-v1.json"
        self.assertEqual(raw["evidence_validation"]["bound_runner_provisional_terminal"]["sha256"], sha(provisional))
        self.assertEqual(json.loads(provisional.read_text())["terminal_class"], "PASS")
        self.assertEqual(raw["verdict"], "REJECTED")

    def test_runtime_accounting_and_numerical_evidence_are_complete(self) -> None:
        raw = load("f017-dprefix-real3-rejected-oracle-state-identity-v1.json")
        accounting = raw["runtime_accounting"]
        self.assertEqual(accounting["actual_host_copy_count"], 4050)
        self.assertEqual(accounting["native_matvecs"], 4050)
        self.assertEqual(accounting["actual_host_copy_bytes"], 10_145_280)
        self.assertEqual(accounting["fallback"], 0)
        self.assertEqual(accounting["backend_errors"], 0)
        self.assertEqual(raw["lifecycle"]["result"], "PASS")
        self.assertEqual(len(raw["decoded_identity_confirmation"]["identities"]), 40)
        self.assertEqual(len(raw["numerical_surfaces"]), 8)
        self.assertTrue(all(item["pass"] for item in raw["numerical_surfaces"]))
        self.assertTrue(all(item["candidate_non_finite_count"] == item["oracle_non_finite_count"] == 0 for item in raw["numerical_surfaces"]))
        self.assertTrue(all(item["signed_zero_mismatch_count"] == 0 for item in raw["numerical_surfaces"]))

    def test_attempt_terminal_and_payload_ledger_immutable(self) -> None:
        raw_path = EVIDENCE / "f017-dprefix-real3-rejected-oracle-state-identity-v1.json"
        attempt = load("f017-dense-prefix-replay-attempt-ledger-v2.json")
        payload = load("f017-real-payload-access-ledger-v1.json")
        state = attempt["current_state"]
        self.assertEqual(state["attempt_id"], "DPREFIX-REAL-3")
        self.assertTrue(state["consumed"] and state["executed"])
        self.assertFalse(state["checkpoint_accessed"])
        self.assertEqual(state["evidence_sha256"], sha(raw_path))
        self.assertEqual(state["ledger_before"], 139)
        self.assertEqual(state["ledger_after"], 139)
        real2 = next(item for item in payload["events"] if item["attempt"] == "DPREFIX-REAL-2")
        self.assertEqual(real2["cumulative_tensor_payloads_after_event"], 139)
        self.assertGreaterEqual(payload["cumulative_tensor_payloads"], 139)
        self.assertFalse(state["automatic_retry"])

    def test_downstream_remains_blocked(self) -> None:
        raw = load("f017-dprefix-real3-rejected-oracle-state-identity-v1.json")
        self.assertEqual(raw["downstream"]["representative_m1f0"], "NOT_AUTHORIZED_NOT_EXECUTED")
        self.assertFalse(raw["downstream"]["automatic_continuation"])
        self.assertFalse(raw["downstream"]["replayed_oracle_state_admitted"])


if __name__ == "__main__":
    unittest.main()
