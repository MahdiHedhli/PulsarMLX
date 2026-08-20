#!/usr/bin/env python3
"""Read-only reconciliation for an interrupted routed-aggregate release."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
from typing import Any


EVENT_ID = "F017-REPRESENTATIVE-ROUTED-AGGREGATE-ANALYTICAL-1"
RELEASE_ID = EVENT_ID + "-RELEASE-1"
ATTEMPT_ID = EVENT_ID + "-ATTEMPT-1"
OUTPUT_BYTES = 49152


class ReconciliationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReconciliationError(message)


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate key: {key}")
        result[key] = value
    return result


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(), object_pairs_hook=_unique)
    require(isinstance(value, dict), "object required")
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_output(path: Path) -> str:
    metadata = path.lstat()
    require(stat.S_ISREG(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode), "output identity")
    require(metadata.st_nlink == 1 and stat.S_IMODE(metadata.st_mode) == 0o400 and metadata.st_size == OUTPUT_BYTES, "output geometry")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        observed = os.fstat(descriptor)
        require((metadata.st_dev, metadata.st_ino) == (observed.st_dev, observed.st_ino), "output substitution")
        raw = b""
        while len(raw) < OUTPUT_BYTES:
            chunk = os.read(descriptor, OUTPUT_BYTES - len(raw))
            require(bool(chunk), "short output")
            raw += chunk
        require(os.read(descriptor, 1) == b"", "long output")
    finally:
        os.close(descriptor)
    require(all(math.isfinite(value) for value in struct.unpack("<6144d", raw)), "non-finite output")
    return hashlib.sha256(raw).hexdigest()


def reconcile(state_root: Path, output_path: Path, release_path: Path) -> dict[str, Any]:
    if not state_root.exists():
        require(not output_path.exists(), "output without attempt")
        return {"disposition": "NO_ATTEMPT", "release_consumed": False, "output_authority": False,
                "output_present_for_adjudication": False}
    require(state_root.is_dir() and not state_root.is_symlink(), "state root identity")
    start_path = state_root / "attempt-start.json"
    require(start_path.is_file() and not start_path.is_symlink(), "ACCOUNTING_INTEGRITY_BLOCKER_NO_DURABLE_START")
    start = load(start_path)
    require(start.get("event_id") == EVENT_ID and start.get("release_id") == RELEASE_ID and start.get("attempt_id") == ATTEMPT_ID, "attempt identity")
    require(start.get("release_sha256") == sha(release_path), "attempt release binding")
    aggregate_start_path = state_root / "aggregate-start.json"
    aggregate_executions = 0
    if aggregate_start_path.exists():
        require(aggregate_start_path.is_file() and not aggregate_start_path.is_symlink(), "aggregate start identity")
        aggregate_start = load(aggregate_start_path)
        require(aggregate_start.get("event_id") == EVENT_ID and aggregate_start.get("release_id") == RELEASE_ID
                and aggregate_start.get("attempt_id") == ATTEMPT_ID, "aggregate start event identity")
        require(aggregate_start.get("release_sha256") == sha(release_path), "aggregate start release binding")
        require(aggregate_start.get("accounting_semantics") ==
                "DURABLE_START_COUNTS_ONE_AGGREGATE_EXECUTION_REGARDLESS_OF_OUTCOME", "aggregate accounting semantics")
        require(aggregate_start.get("aggregate_executions") == 1, "aggregate start count")
        aggregate_executions = 1
    terminal_path = state_root / "terminal.json"
    output_identity = validate_output(output_path) if output_path.exists() else None
    require(output_identity is None or aggregate_executions == 1, "output without aggregate start")
    output_authority = False
    if terminal_path.exists():
        terminal = load(terminal_path)
        require(terminal.get("event_id") == EVENT_ID and terminal.get("release_id") == RELEASE_ID and terminal.get("attempt_id") == ATTEMPT_ID, "terminal identity")
        require(terminal.get("retry") is False and terminal.get("resume") is False and terminal.get("second_attempt") is False, "terminal one-shot")
        require(terminal.get("aggregate_executions") == aggregate_executions, "terminal aggregate accounting")
        if terminal.get("disposition") == "COMPLETE":
            require(output_identity is not None and terminal.get("output_sha256") == output_identity, "complete output identity")
            require(aggregate_executions == 1, "complete without aggregate execution")
            disposition = "COMPLETE_RECONSTRUCTED"
            output_authority = True
        else:
            require(terminal.get("disposition") == "TERMINAL_FAILURE", "terminal disposition")
            disposition = "TERMINAL_FAILURE_RECONSTRUCTED"
    elif output_identity is not None:
        disposition = "INTERRUPTED_OUTPUT_PUBLISHED_REQUIRES_ADJUDICATION"
    else:
        disposition = "INTERRUPTED_NO_OUTPUT"
    return {
        "disposition": disposition,
        "release_consumed": True,
        "output_authority": output_authority,
        "output_present_for_adjudication": output_identity is not None,
        "output_sha256": output_identity,
        "ledger": 175,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "expert_executions": 0,
        "aggregate_executions": aggregate_executions,
        "retry": False,
        "resume": False,
        "second_attempt": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(reconcile(args.state_root, args.output, args.release), sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ReconciliationError, FileNotFoundError, PermissionError) as error:
        print(json.dumps({"disposition": "ACCOUNTING_INTEGRITY_BLOCKER", "error": type(error).__name__, "retry": False}, sort_keys=True))
        raise SystemExit(2)
