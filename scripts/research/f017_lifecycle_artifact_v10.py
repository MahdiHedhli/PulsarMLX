#!/usr/bin/env python3
"""Append-only V10 runtime evidence envelope."""
from __future__ import annotations

from pathlib import Path

from f017_canonical_serialization_v10 import bank_exclusive


def bank_runtime_artifact(path: Path, kind: str, payload: dict) -> str:
    if type(kind) is not str or not kind:
        raise ValueError("artifact kind")
    if type(payload) is not dict:
        raise ValueError("artifact payload")
    return bank_exclusive(path, {"schema": f"pulsarmlx.f017.v10.runtime.{kind}/1.0.0", "artifact_kind": kind, "payload": payload})
