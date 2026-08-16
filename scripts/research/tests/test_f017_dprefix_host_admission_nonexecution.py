from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
RAW = EVIDENCE / "f017-dense-prefix-real-attempt-1-not-executed-host-admission-v1.json"
ATTEMPT_V6 = EVIDENCE / "f017-dense-prefix-attempt-ledger-v6.json"
ATTEMPT_V7 = EVIDENCE / "f017-dense-prefix-attempt-ledger-v7.json"
PAYLOAD_LEDGER = EVIDENCE / "f017-real-payload-access-ledger-v1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    def no_duplicates(items: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate key: {key}")
            result[key] = value
        return result

    return json.loads(path.read_text(), object_pairs_hook=no_duplicates)


def validate(raw: dict, attempt: dict, payload: dict) -> None:
    state = raw["state"]
    access = raw["access"]
    assert raw["verdict"] == "NOT_EXECUTED"
    assert raw["terminal_class"] == "HOST_ADMISSION"
    assert raw["reason_code"] == "REVIEWED_CHECKPOINT_MOUNT_ABSENT"
    assert raw["preflight"]["canonical_identity_result"] == "REAL_EVENT_ORCHESTRATOR_IDENTITY_VERIFIED"
    assert raw["preflight"]["host_admission_result"] == "NOT_READY"
    assert raw["host_admission"]["reviewed_checkpoint_object"]["exists"] is False
    assert raw["host_admission"]["free_memory_gib"] >= raw["host_admission"]["memory_floor_gib"]
    assert access == {
        "checkpoint_path_resolved": False,
        "checkpoint_reads": 0,
        "packed_bytes": 0,
        "payloads": 0,
        "positional_reads": 0,
        "shard_opens": 0,
    }
    assert state["authorized"] is True
    assert state["consumed"] is False
    assert state["executed"] is False
    assert state["checkpoint_accessed"] is False
    assert state["ledger_before"] == state["ledger_after"] == 59
    assert attempt["current_state"]["consumed"] is False
    assert attempt["current_state"]["checkpoint_accessed"] is False
    assert attempt["current_state"]["ledger"] == 59
    assert attempt["history"][-1]["evidence_sha256"] == sha256(RAW)
    q6 = next(item for item in payload["events"] if item["attempt"] == "Q6K-REAL-1")
    assert q6["cumulative_tensor_payloads_after_event"] == 59
    assert payload["cumulative_tensor_payloads"] >= 59


class HostAdmissionNonExecutionTests(unittest.TestCase):
    def test_banked_nonexecution_is_consistent_and_append_only(self) -> None:
        raw = load(RAW)
        before = load(ATTEMPT_V6)
        after = load(ATTEMPT_V7)
        payload = load(PAYLOAD_LEDGER)
        self.assertEqual(sha256(RAW), "b7abb1999f6e018cf9a41279b161d7ac84a300984f7f8960776bc5f461065c08")
        self.assertEqual(after["append_only_predecessor"]["sha256"], sha256(ATTEMPT_V6))
        self.assertEqual(after["history"][:-1], before["history"])
        validate(raw, after, payload)

    def test_mutations_fail_closed(self) -> None:
        raw = load(RAW)
        attempt = load(ATTEMPT_V7)
        payload = load(PAYLOAD_LEDGER)
        mutations = [
            lambda value: value["state"].__setitem__("consumed", True),
            lambda value: value["state"].__setitem__("ledger_after", 60),
            lambda value: value["access"].__setitem__("payloads", 1),
            lambda value: value["host_admission"]["reviewed_checkpoint_object"].__setitem__("exists", True),
            lambda value: value.__setitem__("terminal_class", "EXACT_REAL_BYTE_QUALIFIED"),
        ]
        for mutation in mutations:
            changed = copy.deepcopy(raw)
            mutation(changed)
            with self.assertRaises(AssertionError):
                validate(changed, attempt, payload)

    def test_public_evidence_has_no_absolute_machine_path(self) -> None:
        text = RAW.read_text()
        self.assertNotIn("/Users/", text)
        self.assertNotIn("/Volumes/", text)


if __name__ == "__main__":
    unittest.main()
