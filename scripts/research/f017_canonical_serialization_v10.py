#!/usr/bin/env python3
"""Canonical bytes and append-only banking for active F017 lifecycle V10."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8") + b"\n"


def strict_bytes(raw: bytes) -> object:
    from f017_bounded_artifact_decode_v1 import parse_artifact_bytes
    return parse_artifact_bytes(raw)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def bank_exclusive(path: Path, value: object) -> str:
    raw = canonical_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)
    directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    if path.read_bytes() != raw:
        raise ValueError("artifact readback mismatch")
    return sha256_bytes(raw)
