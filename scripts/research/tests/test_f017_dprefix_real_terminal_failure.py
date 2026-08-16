from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
RAW = EVIDENCE / "f017-dense-prefix-real-attempt-1-rejected-native-runtime-v1.json"
ATTEMPT = EVIDENCE / "f017-dense-prefix-attempt-ledger-v8.json"
PAYLOAD = EVIDENCE / "f017-real-payload-access-ledger-v1.json"


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
    state = raw["state"]
    access = raw["access"]
    current = attempt["current_state"]
    event = payload["events"][-1]
    assert raw["verdict"] == "REJECTED"
    assert raw["terminal_class"] == "NATIVE_RUNTIME"
    assert raw["reason_code"] == "NATIVE_CANDIDATE_MATVEC_SHAPE"
    assert access["payloads"] == access["positional_reads"] == 40
    assert access["packed_bytes"] == 1_431_263_232
    assert len(access["read_records"]) == 40
    assert [item["ordinal"] for item in access["read_records"]] == list(range(40))
    assert state["consumed"] and state["executed"] and state["checkpoint_accessed"]
    assert state["ledger_before"] == 59 and state["ledger_after"] == 99
    assert current["evidence_sha256"] == sha256(RAW)
    assert current["terminal_class"] == raw["terminal_class"]
    assert current["payloads_read"] == event["tensor_payload_count"] == 40
    assert current["ledger_before"] == 59 and current["ledger_after"] == 99
    assert event["evidence"]["sha256"] == sha256(RAW)
    assert event["cumulative_tensor_payloads_after_event"] == payload["cumulative_tensor_payloads"] == 99
    assert raw["identity_confirmations"]["Q4_K"]["exact_match"] is True
    assert raw["identity_confirmations"]["Q6_K"]["exact_match"] is True
    assert raw["candidate"]["evidence_artifact_created"] is False
    assert raw["retention"]["layer_3_entry_created"] is False
    assert state["automatic_retry"] is False
    assert state["automatic_m1f0_continuation"] is False


class DensePrefixRealTerminalFailureTests(unittest.TestCase):
    def test_terminal_failure_state_is_reconciled(self) -> None:
        validate(load(RAW), load(ATTEMPT), load(PAYLOAD))

    def test_state_mutations_fail_closed(self) -> None:
        raw = load(RAW)
        attempt = load(ATTEMPT)
        payload = load(PAYLOAD)
        mutations = [
            lambda value: value["state"].__setitem__("consumed", False),
            lambda value: value["access"].__setitem__("payloads", 39),
            lambda value: value["state"].__setitem__("ledger_after", 59),
            lambda value: value.__setitem__("terminal_class", "DENSE_PREFIX_EXACT_TIER_B_QUALIFIED"),
            lambda value: value["retention"].__setitem__("layer_3_entry_created", True),
        ]
        for mutation in mutations:
            changed = copy.deepcopy(raw)
            mutation(changed)
            with self.assertRaises(AssertionError):
                validate(changed, attempt, payload)

    def test_public_evidence_contains_no_machine_local_absolute_path(self) -> None:
        text = RAW.read_text()
        self.assertNotIn("/Users/", text)
        self.assertNotIn("/Volumes/", text)


if __name__ == "__main__":
    unittest.main()
