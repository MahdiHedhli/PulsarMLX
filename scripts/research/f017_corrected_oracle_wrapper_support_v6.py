#!/usr/bin/env python3
"""Shared non-numerical evidence helpers for v6 consumer wrappers."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from f017_corrected_oracle_authorization_v6 import canonical_bytes, strict_bytes

ROOT = Path(__file__).resolve().parents[2]
ACTIVE_REGISTRY = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-active-generation-v1.json"


def bank(path: Path, value: dict) -> str:
    data = canonical_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(parent)
        read_descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        with os.fdopen(read_descriptor, "rb") as source:
            observed = source.read()
    finally:
        os.close(parent)
    if observed != data:
        raise ValueError("consumer evidence exact readback")
    strict_bytes(observed)
    return hashlib.sha256(observed).hexdigest()


def require_active(scope: str) -> None:
    registry = strict_bytes(ACTIVE_REGISTRY.read_bytes())
    if scope == "SYNTHETIC_QUALIFICATION":
        if registry["synthetic_qualification_generation"] != "V6":
            raise ValueError("v6 synthetic qualification disabled")
        return
    if scope != "PRODUCTION" or registry["active_live_generation"] != "V6":
        raise ValueError("active v6 production generation required")
