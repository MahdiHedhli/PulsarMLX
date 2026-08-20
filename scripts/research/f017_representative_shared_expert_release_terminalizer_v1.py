#!/usr/bin/env python3
"""Checkpoint-free reconciliation for an interrupted shared-expert release."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct

OUTPUT_NAME = "representative-shared-expert-output.f32le"
OUTPUT_BYTES = 24576


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def inspect_output(path: Path) -> dict | None:
    if not path.exists():
        return None
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        metadata = os.fstat(fd)
        require(stat.S_ISREG(metadata.st_mode), "OUTPUT_REGULAR")
        require(stat.S_IMODE(metadata.st_mode) == 0o400, "OUTPUT_MODE")
        require(metadata.st_nlink == 1 and metadata.st_size == OUTPUT_BYTES, "OUTPUT_GEOMETRY")
        raw = b""
        while len(raw) < OUTPUT_BYTES:
            chunk = os.read(fd, OUTPUT_BYTES - len(raw))
            require(bool(chunk), "OUTPUT_SHORT_READ")
            raw += chunk
        require(os.read(fd, 1) == b"", "OUTPUT_LONG_READ")
        values = struct.unpack("<6144f", raw)
        require(all(value == value and abs(value) != float("inf") for value in values), "OUTPUT_NONFINITE")
        return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": OUTPUT_BYTES}
    finally:
        os.close(fd)


def reconcile(state_root: Path, output_root: Path) -> dict:
    require(state_root.is_dir(), "NO_ATTEMPT_STATE")
    attempt = state_root / "attempt-start.json"
    require(attempt.is_file(), "NO_DURABLE_ATTEMPT_START")
    attempt_doc = load(attempt)
    require(attempt_doc.get("schema") == "pulsarmlx.f017.representative-shared-expert-release-attempt-start", "ATTEMPT_SCHEMA")
    existing_terminal = state_root / "terminal.json"
    if existing_terminal.exists():
        return load(existing_terminal)
    computation_started = (state_root / "shared-computation-start.json").is_file()
    output = inspect_output(output_root / OUTPUT_NAME)
    return {
        "schema": "pulsarmlx.f017.representative-shared-expert-release-interruption-reconciliation",
        "schema_version": "1.0.0",
        "disposition": "INTERRUPTED_TERMINAL_NO_RESUME",
        "attempt_id": attempt_doc.get("attempt_id"),
        "release_id": attempt_doc.get("release_id"),
        "ledger": 175,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "shared_expert_executions": 1 if computation_started else 0,
        "output_observed": output,
        "output_authority": False,
        "retry": False,
        "resume": False,
        "second_attempt": False,
        "stop_boundary": "AFTER_REPRESENTATIVE_SHARED_EXPERT_OUTPUT_ONLY",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(reconcile(args.state_root, args.output_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
