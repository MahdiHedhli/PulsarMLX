#!/usr/bin/env python3
"""Measured durability boundary for Event 06 safety-authoritative storage.

Production calls here reach Darwin filesystem primitives directly.  Sequence
18 qualification replaces these module functions only inside a disposable
child process, before importing the production registry.  There is no runtime
provider, callback, environment variable, option, or public setter.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

from f017_bounded_artifact_decode_v1 import parse_artifact_bytes
from f017_canonical_serialization_v10 import canonical_bytes, sha256_bytes


def canonical_identity(path: Path) -> Path:
    lexical = Path(os.path.abspath(os.fspath(path)))
    if len(lexical.parts) > 1 and lexical.parts[1] in {"var", "tmp"}:
        lexical = Path("/private", *lexical.parts[1:])
    return lexical


def resolved_identity(path: Path) -> Path:
    return Path(os.path.realpath(Path(os.path.abspath(os.fspath(path)))))


def secure_directory(path: Path) -> Path:
    """Create a private nonsymlink directory and verify its identity."""
    if not isinstance(path, Path):
        raise TypeError("safety storage path type")
    lexical = Path(os.path.abspath(os.fspath(path)))
    if lexical.is_symlink():
        raise ValueError("safety storage symlink component")
    expected = canonical_identity(lexical)
    if Path(os.path.realpath(lexical)) != expected:
        raise ValueError("safety storage ancestor substitution")
    lexical.mkdir(mode=0o700, parents=True, exist_ok=True)
    observed = Path(os.path.realpath(lexical))
    metadata = os.lstat(observed)
    if (stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid() or metadata.st_mode & 0o077
            or observed != expected):
        raise ValueError("safety storage directory identity")
    return observed


def bank_exclusive(path: Path, value: object) -> str:
    """Exclusive create, full write, file fsync, parent fsync, and readback."""
    raw = canonical_bytes(value)
    secure_directory(path.parent)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                raise OSError("short Event 06 safety-state write")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    observed = path.read_bytes()
    if observed != raw:
        raise ValueError("Event 06 safety-state readback")
    return sha256_bytes(raw)


def read_artifact(path: Path) -> object:
    return parse_artifact_bytes(path.read_bytes())


__all__ = [
    "bank_exclusive", "canonical_identity", "read_artifact", "resolved_identity",
    "secure_directory",
]
