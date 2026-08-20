#!/usr/bin/env python3
"""Read-only reconciliation for an interrupted representative FFN release."""

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


EVENT_ID = "F017-REPRESENTATIVE-FFN-COMPOSITION-PROOF-REFERENCE-1"
RELEASE_ID = EVENT_ID + "-RELEASE-1"
ATTEMPT_ID = EVENT_ID + "-ATTEMPT-1"
OUTPUT_BYTES = 49152


class ReconciliationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReconciliationError(message)


def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"DUPLICATE_KEY:{key}")
        result[key] = value
    return result


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    require(isinstance(value, dict), "OBJECT_REQUIRED")
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_file(path: Path, size: int) -> bytes:
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and not stat.S_ISLNK(before.st_mode), "FILE_IDENTITY")
    require(before.st_uid == os.getuid() and before.st_nlink == 1 and stat.S_IMODE(before.st_mode) == 0o400, "FILE_MODE")
    require(before.st_size == size, "FILE_SIZE")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        observed = os.fstat(descriptor)
        require((before.st_dev, before.st_ino) == (observed.st_dev, observed.st_ino), "FILE_SUBSTITUTION")
        raw = b""
        while len(raw) < size:
            chunk = os.read(descriptor, size - len(raw))
            require(bool(chunk), "SHORT_READ")
            raw += chunk
        require(os.read(descriptor, 1) == b"", "LONG_READ")
    finally:
        os.close(descriptor)
    return raw


def validate_json_file(path: Path) -> tuple[dict[str, Any], bytes]:
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and not stat.S_ISLNK(before.st_mode), "JSON_FILE_IDENTITY")
    require(before.st_uid == os.getuid() and before.st_nlink == 1 and stat.S_IMODE(before.st_mode) == 0o400, "JSON_FILE_MODE")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        observed = os.fstat(descriptor)
        require((before.st_dev, before.st_ino) == (observed.st_dev, observed.st_ino), "JSON_FILE_SUBSTITUTION")
        raw = b""
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            raw += chunk
    finally:
        os.close(descriptor)
    value = json.loads(raw, object_pairs_hook=unique)
    require(isinstance(value, dict), "JSON_FILE_OBJECT")
    return value, raw


def validate_output(output_path: Path, manifest_path: Path) -> tuple[str, str]:
    output = validate_file(output_path, OUTPUT_BYTES)
    require(all(math.isfinite(value) for value in struct.unpack("<6144d", output)), "OUTPUT_NONFINITE")
    output_sha = hashlib.sha256(output).hexdigest()
    manifest, manifest_raw = validate_json_file(manifest_path)
    require(manifest.get("schema") == "pulsarmlx.f017.representative-ffn-output-private-manifest", "MANIFEST_SCHEMA")
    entries = manifest.get("artifacts")
    require(isinstance(entries, list) and len(entries) == 1, "MANIFEST_CENSUS")
    entry = entries[0]
    require(entry.get("sha256") == output_sha and entry.get("dtype") == "little-endian-f64" and entry.get("shape") == [6144] and entry.get("byte_length") == OUTPUT_BYTES, "MANIFEST_OUTPUT")
    return output_sha, hashlib.sha256(manifest_raw).hexdigest()


def reconcile(state_root: Path, output_path: Path, manifest_path: Path, release_path: Path) -> dict[str, Any]:
    if not state_root.exists():
        require(not output_path.exists() and not manifest_path.exists(), "OUTPUT_WITHOUT_ATTEMPT")
        return {"disposition": "NO_ATTEMPT", "release_consumed": False, "output_authority": False,
                "ffn_compositions": 0, "ledger": 175, "checkpoint_reads": 0, "shard_opens": 0}
    require(state_root.is_dir() and not state_root.is_symlink(), "STATE_ROOT_IDENTITY")
    start_path = state_root / "attempt-start.json"
    if not start_path.exists():
        require(not (state_root / "ffn-start.json").exists() and not output_path.exists() and not manifest_path.exists(), "PARTIAL_START_HAS_WORK")
        return {"disposition": "PARTIAL_START_ROOT_ZERO_COMPUTE_REQUIRES_ADJUDICATION", "release_consumed": False,
                "output_authority": False, "ffn_compositions": 0, "ledger": 175, "checkpoint_reads": 0, "shard_opens": 0}
    start = load(start_path)
    require((start.get("event_id"), start.get("release_id"), start.get("attempt_id")) == (EVENT_ID, RELEASE_ID, ATTEMPT_ID), "ATTEMPT_IDENTITY")
    require(start.get("release_sha256") == sha(release_path), "ATTEMPT_RELEASE")
    ffn_path = state_root / "ffn-start.json"
    ffn_count = 0
    if ffn_path.exists():
        ffn = load(ffn_path)
        require((ffn.get("event_id"), ffn.get("release_id"), ffn.get("attempt_id")) == (EVENT_ID, RELEASE_ID, ATTEMPT_ID), "FFN_IDENTITY")
        require(ffn.get("release_sha256") == sha(release_path), "FFN_RELEASE")
        require(ffn.get("accounting_semantics") == "DURABLE_START_COUNTS_ONE_FFN_COMPOSITION_REGARDLESS_OF_OUTCOME", "FFN_ACCOUNTING")
        require(ffn.get("ffn_compositions") == 1, "FFN_COUNT")
        ffn_count = 1
    output_sha: str | None = None
    manifest_sha: str | None = None
    if output_path.exists() or manifest_path.exists():
        require(output_path.exists() and manifest_path.exists() and ffn_count == 1, "PARTIAL_PUBLICATION_REQUIRES_ADJUDICATION")
        output_sha, manifest_sha = validate_output(output_path, manifest_path)
    receipt_path = state_root / "ffn-execution-receipt.json"
    receipt = load(receipt_path) if receipt_path.exists() else None
    if receipt is not None:
        require(ffn_count == 1 and output_sha is not None, "RECEIPT_WITHOUT_OUTPUT")
        require(receipt.get("output_sha256") == output_sha and receipt.get("output_manifest_sha256") == manifest_sha, "RECEIPT_OUTPUT")
        require(receipt.get("ffn_compositions") == 1 and receipt.get("s2_constructions") == 0, "RECEIPT_ACCOUNTING")
    terminal_path = state_root / "terminal.json"
    output_authority = False
    if terminal_path.exists():
        terminal = load(terminal_path)
        require((terminal.get("event_id"), terminal.get("release_id"), terminal.get("attempt_id")) == (EVENT_ID, RELEASE_ID, ATTEMPT_ID), "TERMINAL_IDENTITY")
        require(terminal.get("ffn_compositions") == ffn_count, "TERMINAL_ACCOUNTING")
        require(terminal.get("retry") is False and terminal.get("resume") is False and terminal.get("second_attempt") is False, "TERMINAL_ONE_SHOT")
        if terminal.get("disposition") == "COMPLETE":
            require(receipt is not None and terminal.get("execution_receipt_sha256") == sha(receipt_path), "COMPLETE_RECEIPT")
            require(terminal.get("output_sha256") == output_sha and terminal.get("output_manifest_sha256") == manifest_sha, "COMPLETE_OUTPUT")
            require(terminal.get("output_authority") is True and ffn_count == 1, "COMPLETE_AUTHORITY")
            disposition = "COMPLETE_RECONSTRUCTED"
            output_authority = True
        else:
            require(terminal.get("disposition") == "TERMINAL_FAILURE" and terminal.get("output_authority") is False, "FAILURE_TERMINAL")
            disposition = "TERMINAL_FAILURE_RECONSTRUCTED"
    elif output_sha is not None:
        disposition = "INTERRUPTED_OUTPUT_PUBLISHED_REQUIRES_ADJUDICATION"
    elif ffn_count:
        disposition = "INTERRUPTED_AFTER_FFN_START_NO_OUTPUT"
    else:
        disposition = "INTERRUPTED_AFTER_ATTEMPT_START_BEFORE_FFN"
    return {
        "disposition": disposition,
        "release_consumed": True,
        "output_authority": output_authority,
        "output_present_for_adjudication": output_sha is not None,
        "output_sha256": output_sha,
        "output_manifest_sha256": manifest_sha,
        "ledger": 175,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "expert_executions": 0,
        "shared_expert_executions": 0,
        "ffn_compositions": ffn_count,
        "s1_materializations": 0,
        "s2_constructions": 0,
        "retry": False,
        "resume": False,
        "second_attempt": False,
    }


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
