#!/usr/bin/env python3
"""Read-only terminal reconstruction for one S1 materialization attempt."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def reconstruct(state_root: Path, output: Path, manifest: Path) -> dict[str, Any]:
    attempt, start, receipt, terminal = (load(state_root / name) for name in
        ("attempt-start.json", "materialization-start.json", "s1-execution-receipt.json", "terminal.json"))
    output_sha, manifest_sha = sha(output), sha(manifest)
    complete = bool(terminal and terminal.get("status") == "COMPLETE")
    authority = bool(complete and receipt and receipt.get("output_sha256") == output_sha
                     and receipt.get("manifest_sha256") == manifest_sha)
    return {
        "attempt_starts": int(attempt is not None),
        "materialization_starts": int(start is not None),
        "materializations": int(start is not None),
        "terminal": terminal.get("status") if terminal else "ABSENT",
        "output_authority": authority,
        "output_sha256": output_sha,
        "manifest_sha256": manifest_sha,
        "retry_authorized": False,
        "resume_authorized": False,
    }
