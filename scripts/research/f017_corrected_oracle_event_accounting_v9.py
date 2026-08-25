#!/usr/bin/env python3
"""Runtime-derived V9 event accounting from validated durable evidence."""
from __future__ import annotations

import json
import stat
from pathlib import Path


HISTORICAL_REAL_PAYLOAD_LEDGER = 175


def _valid(path: Path, kind: str) -> bool:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return False
    # Any existing but unreadable, redirected, malformed, or wrongly typed
    # durable-start artifact is an accounting observation failure.  Only true
    # absence is represented by False.
    if not stat.S_ISREG(mode):
        raise ValueError("durable-start artifact type")
    try:
        value = json.loads(path.read_bytes())
    except OSError:
        raise
    except (UnicodeError, ValueError) as exc:
        raise ValueError("durable-start artifact bytes") from exc
    if type(value) is not dict or value.get("artifact_kind") != kind:
        raise ValueError("durable-start artifact binding")
    return True


def derive(evidence_root: Path) -> dict:
    package = _valid(evidence_root / "package-durable-start.json", "package_durable_start")
    primary = _valid(evidence_root / "primary-durable-start.json", "primary_durable_start")
    secondary = _valid(evidence_root / "secondary-durable-start.json", "secondary_durable_start")
    if (primary or secondary) and not package: raise ValueError("consumer start without package start")
    return {"authorization": 0, "package": int(package), "primary": int(primary), "secondary": int(secondary),
            "historical_before": HISTORICAL_REAL_PAYLOAD_LEDGER, "historical_after": HISTORICAL_REAL_PAYLOAD_LEDGER}


def validate_against_outcome(accounting: dict, outcome: dict, failed_transition_id: str,
                             last_completed_artifact_id: str) -> None:
    expected = {"package": outcome["package_delta"], "primary": outcome["primary_delta"], "secondary": outcome["secondary_delta"]}
    if any(accounting[key] != value for key, value in expected.items()): raise ValueError("runtime/outcome accounting mismatch")
    if outcome["failed_transition_id"] != failed_transition_id: raise ValueError("failed transition mismatch")
    if outcome["last_completed_artifact_id"] != last_completed_artifact_id:
        raise ValueError("last completed artifact mismatch")


def validate_snapshot(actual: object, expected: dict) -> None:
    keys = {"authorization", "package", "primary", "secondary", "historical_before", "historical_after"}
    if type(actual) is not dict or set(actual) != keys:
        raise ValueError("accounting census")
    for key in keys:
        if type(actual[key]) is not int:
            raise ValueError("accounting type")
    if actual != expected:
        raise ValueError("accounting snapshot mismatch")
