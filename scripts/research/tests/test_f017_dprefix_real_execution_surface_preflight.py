from __future__ import annotations

import hashlib
import json
import unittest

from scripts.research import f017_dprefix_real_execution_surface_preflight as M


class DensePrefixRealExecutionSurfacePreflightTests(unittest.TestCase):
    def test_released_surface_fails_closed_without_orchestrator(self) -> None:
        evidence = M.evidence_artifact()
        self.assertEqual(evidence["verdict"], "NOT_EXECUTED")
        self.assertEqual(evidence["terminal_class"], "EXECUTION_SURFACE_DRIFT")
        self.assertEqual(evidence["reason_code"], "REAL_EVENT_ORCHESTRATOR_UNBOUND")
        self.assertEqual(evidence["finding"]["committed_material_package_invocations"], [])
        self.assertFalse(evidence["finding"]["config_binds_real_event_launcher"])
        self.assertFalse(evidence["finding"]["authorization_binds_real_event_launcher"])

    def test_access_and_attempt_remain_nonconsuming(self) -> None:
        evidence = M.evidence_artifact()
        self.assertEqual(evidence["access"], {
            "checkpoint_path_resolved": False,
            "shard_opens": 0,
            "positional_reads": 0,
            "payloads": 0,
            "packed_bytes": 0,
        })
        self.assertEqual(evidence["state"], {
            "authorized": True,
            "consumed": False,
            "executed": False,
            "checkpoint_accessed": False,
            "payloads_read": 0,
            "packed_bytes_read": 0,
            "ledger_before": 59,
            "ledger_after": 59,
            "automatic_retry": False,
            "automatic_m1f0_continuation": False,
        })

    def test_attempt_ledger_is_append_only_and_preserves_state(self) -> None:
        generated = M.generate()
        predecessor = M.load(M.ATTEMPT_V4)
        attempt = generated["attempt"]
        self.assertEqual(attempt["append_only_predecessor"]["sha256"], M.ATTEMPT_V4_SHA)
        self.assertEqual(attempt["history"][:-1], predecessor["history"])
        self.assertEqual(attempt["current_state"], predecessor["current_state"])
        self.assertEqual(attempt["history"][-1]["evidence_sha256"], M.canonical_sha(generated["evidence"]))

    def test_banked_artifacts_regenerate_exactly(self) -> None:
        banked = json.loads(M.EVIDENCE.read_text())
        if M.sha256(M.CANDIDATE) != banked["bindings"]["candidate_source_sha256"]:
            # This refusal is immutable REAL-1 history; a later append-only
            # candidate successor must not cause its evidence to be rewritten.
            self.assertEqual(M.canonical_sha(banked), M.sha256(M.EVIDENCE))
            return
        generated = M.generate()
        self.assertEqual(M.EVIDENCE.read_bytes(), M.canonical_bytes(generated["evidence"]))
        self.assertEqual(M.ATTEMPT_V5.read_bytes(), M.canonical_bytes(generated["attempt"]))
        self.assertEqual(M.REVIEW.read_text(encoding="utf-8"), generated["review"])

    def test_frozen_execution_identities_and_payload_ledger_unchanged(self) -> None:
        self.assertEqual(M.sha256(M.CONFIG), M.CONFIG_SHA)
        self.assertEqual(M.sha256(M.AUTH), M.AUTH_SHA)
        self.assertEqual(M.sha256(M.ATTEMPT_V4), M.ATTEMPT_V4_SHA)
        self.assertEqual(hashlib.sha256(M.released_payload_ledger_bytes()).hexdigest(), M.PAYLOAD_LEDGER_SHA)
        ledger = json.loads(M.PAYLOAD_LEDGER.read_text(encoding="utf-8"))
        real2 = next(event for event in ledger["events"] if event["attempt"] == "DPREFIX-REAL-2")
        self.assertEqual(real2["cumulative_tensor_payloads_after_event"], 139)
        self.assertGreaterEqual(ledger["cumulative_tensor_payloads"], 139)
        self.assertEqual(
            sum(event["tensor_payload_count"] for event in ledger["events"]),
            ledger["cumulative_tensor_payloads"],
        )

    def test_prior_nonexecution_evidence_immutable(self) -> None:
        prior = M.EVIDENCE_DIR / "f017-dense-prefix-real-attempt-1-not-executed-numerical-surface-v1.json"
        self.assertEqual(hashlib.sha256(prior.read_bytes()).hexdigest(), "a730fb123fd86319b199579c79bdcbff1b282b7f7ec4003daa694f9e37a176b6")


if __name__ == "__main__":
    unittest.main()
