#!/usr/bin/env python3
"""Reconcile Q4K-REAL-1 raw evidence with append-only repository ledgers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.research.validate_f017_q4_k_evidence import (
    EXPECTED,
    load_json,
    require,
    sha256,
    validate_evidence_object,
)


def validate_repository_evidence(root: Path, evidence_path: Path) -> str:
    evidence = load_json(evidence_path)
    status = validate_evidence_object(evidence)
    evidence_sha = sha256(evidence_path)
    attempt_ledger = load_json(root / "docs/architecture/reviews/evidence/f017-q4-k-attempt-ledger-v2.json")
    real_ledger = load_json(root / "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json")

    require(attempt_ledger["status"] == "CONSUMED_EXECUTED_EXACT_REAL_BYTE_QUALIFIED", "attempt ledger status")
    require(attempt_ledger["real_checkpoint_access"] == 1, "attempt ledger access")
    require(attempt_ledger["real_payload_ledger"] == 58, "attempt ledger cumulative count")
    records = [record for record in attempt_ledger["attempts"] if record.get("attempt_id") == EXPECTED["attempt_id"]]
    require(len(records) == 1, "attempt ledger record count")
    record = records[0]
    for field in ("authorized", "consumed", "executed", "checkpoint_accessed"):
        require(record[field] is True, f"attempt ledger {field}")
    require(record["terminal_classification"] == status, "attempt ledger terminal class")
    require(record["evidence_artifact_sha256"] == evidence_sha, "attempt ledger evidence hash")
    require(record["packed_sha256"] == evidence["identity"]["packed_sha256"], "attempt ledger packed hash")
    require(record["ledger_before"] == 57 and record["ledger_after"] == 58, "attempt ledger transition")
    require(record["automatic_retry"] is False, "attempt ledger retry")
    require(record["automatic_q6_continuation"] is False, "attempt ledger Q6 continuation")
    require(record["automatic_dense_prefix_continuation"] is False, "attempt ledger dense continuation")

    require(real_ledger["cumulative_tensor_payloads"] >= 58, "real ledger cumulative count")
    events = [event for event in real_ledger["events"] if event.get("attempt") == EXPECTED["attempt_id"]]
    require(len(events) == 1, "real ledger event count")
    event = events[0]
    require(event["access_kind"] == "qualification_only", "real ledger kind")
    require(event["consumed_attempt"] is True, "real ledger consumed")
    require(event["tensor_payload_count"] == 1, "real ledger payload count")
    require(event["tensor_symbolic_names"] == ["token_embd.weight"], "real ledger tensor")
    require(event["cumulative_tensor_payloads_after_event"] == 58, "real ledger transition")
    require(event["evidence"]["sha256"] == evidence_sha, "real ledger evidence hash")
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
    raise SystemExit(main())
