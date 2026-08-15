#!/usr/bin/env python3
"""Reconcile Q6K-REAL-1 start, terminal evidence, attempt, and payload ledgers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.research.validate_f017_q6_k_evidence import (
    EvidenceError,
    load_json,
    require,
    sha256,
    validate_evidence_object,
)


EVIDENCE_SHA = "375e6b852733e8ac885d53c3814a03deb3a80e639bf61d427f1e49f1aae57086"
START_SHA = "5798bfeede1a9b53946f7d33d1fe4ebb636a51cf42b9aea41333278889c42db5"


def validate_objects(
    start: dict[str, Any],
    evidence: dict[str, Any],
    attempt_ledger: dict[str, Any],
    real_ledger: dict[str, Any],
    evidence_sha: str = EVIDENCE_SHA,
    start_sha: str = START_SHA,
) -> str:
    status = validate_evidence_object(evidence)
    require(start["schema"] == "pulsarmlx.f017.q6-k-real-execution-start", "start schema")
    require(start["attempt_id"] == "Q6K-REAL-1", "start attempt")
    require(start["authorized"] is True and start["consumed"] is True and start["executed"] is True, "start state")
    require(start["checkpoint_accessed"] is False, "start must precede read")
    require(start["ledger_before"] == 58, "start ledger")
    require(start["target"] == {
        "tensor_name": "blk.0.ffn_down.weight",
        "shard_ordinal": 2,
        "offset": 1203482464,
        "packed_length": 61931520,
    }, "start target")

    require(attempt_ledger["append_only"] is True, "attempt ledger append-only")
    require(attempt_ledger["status"] == "CONSUMED_EXECUTED_EXACT_REAL_BYTE_QUALIFIED", "attempt status")
    require(attempt_ledger["real_checkpoint_access"] == 1, "attempt access")
    require(attempt_ledger["real_payload_ledger"] == 59, "attempt cumulative ledger")
    records = [row for row in attempt_ledger["attempts"] if row.get("attempt_id") == "Q6K-REAL-1"]
    require(len(records) == 1, "attempt record count")
    record = records[0]
    for field in ("authorized", "consumed", "executed", "checkpoint_accessed"):
        require(record[field] is True, f"attempt {field}")
    require(record["terminal_class"] == status, "attempt terminal class")
    require(record["evidence_sha256"] == evidence_sha == EVIDENCE_SHA, "attempt evidence SHA")
    require(record["execution_start_sha256"] == start_sha == START_SHA, "attempt start SHA")
    require(record["packed_sha256"] == evidence["identity"]["packed_sha256"], "attempt packed SHA")
    require(record["ledger_before"] == 58 and record["ledger_after"] == 59, "attempt ledger transition")
    require(record["payload_count"] == 1, "attempt payload count")
    require(record["automatic_retry"] is False, "attempt retry")
    require(record["automatic_dense_prefix_continuation"] is False, "attempt dense continuation")
    require(record["automatic_other_gate_continuation"] is False, "attempt other continuation")

    require(real_ledger["cumulative_tensor_payloads"] == 59, "real ledger cumulative count")
    events = [row for row in real_ledger["events"] if row.get("attempt") == "Q6K-REAL-1"]
    require(len(events) == 1, "real ledger event count")
    event = events[0]
    require(event["phase"] == "Q6_K-REAL-BYTE-QUALIFICATION", "real ledger phase")
    require(event["access_kind"] == "qualification_only", "real ledger kind")
    require(event["consumed_attempt"] is True, "real ledger consumed")
    require(event["tensor_payload_count"] == 1, "real ledger payload count")
    require(event["tensor_symbolic_names"] == ["blk.0.ffn_down.weight"], "real ledger target")
    require(event["cumulative_tensor_payloads_after_event"] == 59, "real ledger transition")
    require(event["evidence"]["sha256"] == evidence_sha, "real ledger evidence SHA")
    require(evidence["ledger"] == {"before": 58, "actual_payloads": 1, "after": 59}, "terminal ledger")
    return status


def validate_repository_evidence(root: Path, evidence_path: Path) -> str:
    start_path = root / "docs/architecture/reviews/evidence/f017-q6-k-real-byte-qualification-attempt-1-execution-start-v1.json"
    attempt_path = root / "docs/architecture/reviews/evidence/f017-q6-k-attempt-ledger-v2.json"
    ledger_path = root / "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json"
    require(sha256(evidence_path) == EVIDENCE_SHA, "terminal evidence file SHA")
    require(sha256(start_path) == START_SHA, "execution-start file SHA")
    status = validate_objects(
        load_json(start_path),
        load_json(evidence_path),
        load_json(attempt_path),
        load_json(ledger_path),
    )
    closure = load_json(root / "docs/architecture/reviews/evidence/f017-q6-k-decoder-defect-real-byte-closure-v1.json")
    require(closure["status"] == "REAL_BYTE_SIDE_CLOSED", "defect closure status")
    require(closure["terminal_evidence"]["sha256"] == EVIDENCE_SHA, "defect closure evidence")
    require(closure["exact_bitwise_equality"] is True, "defect closure equality")
    return status


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    evidence = args.evidence.resolve(strict=True)
    status = validate_repository_evidence(args.repository_root.resolve(strict=True), evidence)
    print(json.dumps({"status": status, "evidence_sha256": sha256(evidence)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EvidenceError as error:
        raise SystemExit(str(error)) from error
