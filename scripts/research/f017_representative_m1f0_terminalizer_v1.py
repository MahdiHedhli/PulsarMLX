#!/usr/bin/env python3
"""Fail-closed interrupted-attempt terminalizer for representative M1-F0."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from f017_representative_m1f0_executor_v3 import EventError, atomic_json, sha_file


LEDGER_BEFORE = 166


def reconcile_interrupted_attempt(state_root: Path, retention_root: Path) -> dict[str, Any]:
    if not (state_root / "attempt.json").is_file() or not (state_root / "execution-start.json").is_file():
        raise EventError("NO_STARTED_ATTEMPT")
    if (state_root / "terminal.json").exists():
        raise EventError("ATTEMPT_ALREADY_TERMINAL")
    receipts: dict[int, dict[str, Any]] = {}
    receipt_root = state_root / "receipts"
    for path in sorted(receipt_root.glob("*.json")) if receipt_root.exists() else []:
        item = json.loads(path.read_text(encoding="utf-8"))
        ordinal = int(item["sequence"])
        if ordinal in receipts:
            raise EventError("ACCOUNTING_INTEGRITY_DUPLICATE_RECEIPT")
        retained = retention_root / item["retained_artifact"]
        if not retained.is_file() or retained.stat().st_size != item["actual_bytes"]:
            raise EventError("ACCOUNTING_INTEGRITY_RECEIPT_PAYLOAD")
        if sha_file(retained) != item["packed_sha256"]:
            raise EventError("ACCOUNTING_INTEGRITY_RECEIPT_HASH")
        receipts[ordinal] = item
    if sorted(receipts) != list(range(len(receipts))):
        raise EventError("ACCOUNTING_INTEGRITY_RECEIPT_GAP")

    # A crash after durable retention but before receipt is recoverable because
    # the frozen ordinal filename and packed identity prove that consumption.
    recovered = []
    packed_root = retention_root / "packed"
    for path in sorted(packed_root.glob("*.bin")) if packed_root.exists() else []:
        ordinal = int(path.stem)
        if ordinal < len(receipts):
            continue
        if ordinal != len(receipts) + len(recovered):
            raise EventError("ACCOUNTING_INTEGRITY_ORPHAN_GAP")
        recovered.append({"ordinal": ordinal, "sha256": sha_file(path),
                          "byte_length": path.stat().st_size,
                          "basis": "DURABLE_RETAINED_PAYLOAD_WITH_FROZEN_ORDINAL"})
    consumed = len(receipts) + len(recovered)
    if consumed > 9:
        raise EventError("ACCOUNTING_INTEGRITY_READ_OVERFLOW")
    terminal = {
        "status": "TERMINAL_FAILURE", "reason": "INTERRUPTED_ATTEMPT",
        "consumed_reads": consumed, "durable_receipts": len(receipts),
        "recovered_unreceipted_payloads": recovered,
        "ledger": LEDGER_BEFORE + consumed, "resume_authorized": False,
        "retry_authorized": False, "new_shard_reads_authorized": 0,
        "second_attempt_authorized": False,
    }
    terminal["sha256"] = hashlib.sha256(json.dumps(terminal, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    atomic_json(state_root / "terminal.json", terminal)
    return terminal


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--retention-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(reconcile_interrupted_attempt(args.state_root, args.retention_root), sort_keys=True))
        return 0
    except EventError as exc:
        print(json.dumps({"result": "BLOCKED", "reason": exc.code}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
