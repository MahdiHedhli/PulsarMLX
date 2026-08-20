#!/usr/bin/env python3
"""Read-only reconciliation for the representative S2 one-shot release."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Any


EVENT_ID = "F017-REPRESENTATIVE-S2-PROOF-REFERENCE-DERIVED-1"
RELEASE_ID = EVENT_ID + "-RELEASE-1"
ATTEMPT_ID = EVENT_ID + "-ATTEMPT-1"


class ReconciliationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReconciliationError(message)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), "JSON_OBJECT_REQUIRED")
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_output(output: Path, manifest: Path) -> tuple[str, str]:
    raw = output.read_bytes()
    require(len(raw) == 24576 and all(math.isfinite(value) for value in struct.unpack("<6144f", raw)), "OUTPUT_INVALID")
    output_sha = hashlib.sha256(raw).hexdigest()
    doc = load(manifest)
    entries = doc.get("artifacts")
    require(isinstance(entries, list) and len(entries) == 1, "MANIFEST_CENSUS")
    entry = entries[0]
    require(entry == {"symbolic_path": "representative-s2.f32le", "sha256": output_sha,
        "semantic_role": "REPRESENTATIVE_M1F0_S2_PROOF_REFERENCE_DERIVED", "dtype": "little-endian-f32",
        "shape": [6144], "byte_length": 24576, "finite": True}, "MANIFEST_BINDING")
    return output_sha, sha(manifest)


def reconcile(state_root: Path, output: Path, manifest: Path, release: Path) -> dict[str, Any]:
    if not state_root.exists():
        require(not output.exists() and not manifest.exists(), "OUTPUT_WITHOUT_ATTEMPT")
        return {"disposition": "NOT_STARTED", "release_consumed": False, "s2_constructions": 0,
            "ledger": 175, "checkpoint_reads": 0, "shard_opens": 0}
    attempt = load(state_root / "attempt-start.json")
    require((attempt.get("event_id"), attempt.get("release_id"), attempt.get("attempt_id")) == (EVENT_ID, RELEASE_ID, ATTEMPT_ID), "ATTEMPT_IDENTITY")
    require(attempt.get("release_sha256") == sha(release), "ATTEMPT_RELEASE")
    start_path = state_root / "s2-start.json"
    count = int(start_path.exists())
    if count:
        start = load(start_path)
        require(start.get("s2_constructions") == 1 and start.get("accounting_semantics") == "DURABLE_START_COUNTS_ONE_S2_CONSTRUCTION_REGARDLESS_OF_OUTCOME", "S2_START")
    output_sha = manifest_sha = None
    if output.exists() or manifest.exists():
        require(output.exists() and manifest.exists() and count == 1, "PARTIAL_PUBLICATION")
        output_sha, manifest_sha = validate_output(output, manifest)
    receipt_path = state_root / "s2-execution-receipt.json"
    receipt = load(receipt_path) if receipt_path.exists() else None
    if receipt:
        require(count == 1 and receipt.get("output_sha256") == output_sha and receipt.get("output_manifest_sha256") == manifest_sha, "RECEIPT_BINDING")
        require(receipt.get("s1_materializations") == 0 and receipt.get("ffn_compositions") == 0 and receipt.get("s2_constructions") == 1, "RECEIPT_ACCOUNTING")
    terminal_path = state_root / "terminal.json"
    authority = False
    if terminal_path.exists():
        terminal = load(terminal_path)
        require(terminal.get("s2_constructions") == count and terminal.get("retry") is False and terminal.get("resume") is False and terminal.get("second_attempt") is False, "TERMINAL_ACCOUNTING")
        if terminal.get("disposition") == "COMPLETE":
            require(receipt is not None and terminal.get("execution_receipt_sha256") == sha(receipt_path), "COMPLETE_RECEIPT")
            require(terminal.get("output_sha256") == output_sha and terminal.get("output_manifest_sha256") == manifest_sha, "COMPLETE_OUTPUT")
            require(terminal.get("output_authority") is True and count == 1, "COMPLETE_AUTHORITY")
            disposition = "COMPLETE_RECONSTRUCTED"
            authority = True
        else:
            require(terminal.get("disposition") == "TERMINAL_FAILURE" and terminal.get("output_authority") is False, "FAILURE_TERMINAL")
            disposition = "TERMINAL_FAILURE_RECONSTRUCTED"
    elif output_sha:
        disposition = "INTERRUPTED_OUTPUT_PUBLISHED_REQUIRES_ADJUDICATION"
    elif count:
        disposition = "INTERRUPTED_AFTER_S2_START"
    else:
        disposition = "INTERRUPTED_AFTER_ATTEMPT_START_BEFORE_S2"
    return {"disposition": disposition, "release_consumed": True, "output_authority": authority,
        "output_sha256": output_sha, "output_manifest_sha256": manifest_sha,
        "ledger": 175, "checkpoint_reads": 0, "shard_opens": 0,
        "s1_materializations": 0, "ffn_compositions": 0, "s2_constructions": count,
        "retry": False, "resume": False, "second_attempt": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(reconcile(args.state_root, args.output, args.manifest, args.release), sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ReconciliationError, FileNotFoundError, PermissionError) as error:
        print(json.dumps({"disposition": "ACCOUNTING_INTEGRITY_BLOCKER", "error": type(error).__name__, "retry": False}, sort_keys=True))
        raise SystemExit(2)
