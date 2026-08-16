from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
RAW = EVIDENCE / "f017-dense-prefix-real-attempt-2-rejected-evidence-validation-v1.json"
ATTEMPT = EVIDENCE / "f017-dense-prefix-attempt-ledger-v10.json"
PAYLOAD = EVIDENCE / "f017-real-payload-access-ledger-v1.json"
PACKED = EVIDENCE / "f017-dprefix-real2-packed-package-descriptor-v1.json"
ORACLE = EVIDENCE / "f017-dprefix-real2-oracle-retention-descriptor-v1.json"
CANDIDATE = EVIDENCE / "f017-dprefix-real2-candidate-retention-descriptor-v1.json"


def load(path: Path) -> dict:
    def reject_duplicates(items: list[tuple[str, object]]) -> dict:
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"duplicate key: {key}")
            value[key] = item
        return value

    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(raw: dict, attempt: dict, payload: dict) -> None:
    current = attempt["current_state"]
    event = payload["events"][-1]
    assert raw["attempt_id"] == current["attempt_id"] == event["attempt"] == "DPREFIX-REAL-2"
    assert raw["verdict"] == "REJECTED"
    assert raw["terminal_class"] == current["terminal_class"] == "EVIDENCE_VALIDATION"
    assert raw["reason_code"] == current["reason_code"] == "SUCCESS_PATH_RUNTIME_ACCOUNTING_MISSING"
    assert raw["access"]["payloads"] == raw["access"]["positional_reads"] == 40
    assert len(raw["access"]["read_records"]) == 40
    assert raw["access"]["packed_bytes"] == 1_431_263_232
    assert raw["access"]["all_40_packed_identity_exact"] is True
    assert raw["identity_confirmations"]["Q4_K"]["exact"] is True
    assert raw["identity_confirmations"]["Q6_K"]["exact"] is True
    assert raw["oracle"]["persisted_before_candidate"] is True
    assert raw["oracle"]["post_candidate_rehash"] == "PASS"
    assert raw["candidate"]["repeats_completed"] == 10
    assert raw["candidate"]["repeat_determinism"] is True
    assert len(raw["numerical_surfaces"]) == 8
    assert all(item["pass"] for item in raw["numerical_surfaces"])
    assert raw["numerical_result"]["all_required_surfaces_pass"] is True
    assert raw["runtime_accounting"]["fallback"] == 0
    assert raw["runtime_accounting"]["backend_errors"] == 0
    assert raw["runtime_accounting"]["host_copies"] == "NOT_RECORDED_BY_BOUND_SUCCESS_PATH"
    assert raw["lifecycle"]["terminal_pass_requirement_satisfied"] is False
    assert raw["evidence_validation"]["result"] == "FAIL_CLOSED"
    assert raw["state"]["consumed"] and raw["state"]["executed"] and raw["state"]["checkpoint_accessed"]
    assert raw["state"]["ledger_before"] == 99 and raw["state"]["ledger_after"] == 139
    assert current["evidence_sha256"] == event["evidence"]["sha256"] == sha256(RAW)
    assert current["payloads_read"] == event["tensor_payload_count"] == 40
    assert current["ledger_before"] == 99 and current["ledger_after"] == 139
    assert event["cumulative_tensor_payloads_after_event"] == payload["cumulative_tensor_payloads"] == 139
    assert current["automatic_retry"] is False
    assert current["automatic_m1f0_continuation"] is False


class DensePrefixReal2TerminalEvidenceTests(unittest.TestCase):
    def test_terminal_state_is_reconciled(self) -> None:
        validate(load(RAW), load(ATTEMPT), load(PAYLOAD))

    def test_retention_descriptors_are_consistent(self) -> None:
        raw = load(RAW)
        packed = load(PACKED)
        oracle = load(ORACLE)
        candidate = load(CANDIDATE)
        assert packed["payloads"] == 40 and packed["packed_bytes"] == 1_431_263_232
        assert len(packed["entries"]) == 40
        assert packed["manifest_sha256"] == raw["packed_retention"]["private_manifest_sha256"]
        assert sha256(ORACLE) == raw["oracle"]["descriptor"]["sha256"]
        assert oracle["artifacts"]["layer_3_entry"]["sha256"] == raw["oracle"]["layer_3_entry"]["sha256"]
        assert sha256(CANDIDATE) == raw["candidate"]["retention_descriptor"]["sha256"]

    def test_state_mutations_fail_closed(self) -> None:
        raw = load(RAW)
        attempt = load(ATTEMPT)
        payload = load(PAYLOAD)
        mutations = [
            lambda value: value["state"].__setitem__("consumed", False),
            lambda value: value["access"].__setitem__("payloads", 39),
            lambda value: value["state"].__setitem__("ledger_after", 99),
            lambda value: value.__setitem__("verdict", "ACCEPTED"),
            lambda value: value["lifecycle"].__setitem__("terminal_pass_requirement_satisfied", True),
        ]
        for mutation in mutations:
            changed = copy.deepcopy(raw)
            mutation(changed)
            with self.assertRaises(AssertionError):
                validate(changed, attempt, payload)

    def test_public_evidence_contains_no_private_absolute_path(self) -> None:
        for path in (RAW, PACKED, ORACLE, CANDIDATE):
            text = path.read_text()
            self.assertNotIn("/Users/", text)
            self.assertNotIn("/Volumes/", text)


if __name__ == "__main__":
    unittest.main()
