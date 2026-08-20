#!/usr/bin/env python3
"""Open-once resolver for the banked representative shared-expert output."""

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


class ReuseError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReuseError(message)


def read_exact(fd: int, size: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = os.read(fd, min(remaining, 1024 * 1024))
        require(bool(chunk), "SHORT_READ")
        chunks.append(chunk)
        remaining -= len(chunk)
    require(os.read(fd, 1) == b"", "LONG_READ")
    return b"".join(chunks)


def open_leaf(root_fd: int, name: str, size: int) -> tuple[int, os.stat_result, bytes]:
    require(isinstance(name, str) and Path(name).name == name, "PURE_BASENAME_REQUIRED")
    fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
    metadata = os.fstat(fd)
    require(stat.S_ISREG(metadata.st_mode), "REGULAR_FILE_REQUIRED")
    require(metadata.st_uid == os.getuid(), "OWNER_REQUIRED")
    require(metadata.st_nlink == 1, "SINGLE_HARD_LINK_REQUIRED")
    require(metadata.st_mode & 0o222 == 0, "READ_ONLY_REQUIRED")
    require(metadata.st_size == size, "BYTE_LENGTH")
    return fd, metadata, read_exact(fd, size)


def validate_manifest(raw: bytes, artifact: dict[str, Any]) -> None:
    document = json.loads(raw)
    require(document.get("schema") == "pulsarmlx.f017.representative-shared-expert-output-private-manifest", "MANIFEST_SCHEMA")
    require(document.get("schema_version") == "1.0.0", "MANIFEST_VERSION")
    require(document.get("semantic_surface") == "CANONICAL_REPRESENTATIVE_POST_ATTENTION_SHARED_EXPERT_STRICT_F32_SURFACE", "MANIFEST_SURFACE")
    entries = document.get("artifacts")
    require(isinstance(entries, list) and len(entries) == 1, "MANIFEST_CENSUS")
    entry = entries[0]
    require(entry.get("symbolic_path") == artifact.get("relative_path"), "MANIFEST_PATH")
    require(entry.get("sha256") == artifact.get("sha256"), "MANIFEST_SHA")
    require(entry.get("semantic_role") == artifact.get("semantic_role"), "MANIFEST_ROLE")
    require(entry.get("dtype") == artifact.get("dtype"), "MANIFEST_DTYPE")
    require(entry.get("shape") == artifact.get("shape"), "MANIFEST_SHAPE")
    require(entry.get("byte_length") == artifact.get("byte_length"), "MANIFEST_BYTES")


def preflight_and_consume(authorization: dict[str, Any], output_root: Path) -> dict[str, Any]:
    require(authorization.get("schema") == "pulsarmlx.f017.representative-shared-expert-output-reuse-authorization", "AUTHORIZATION_SCHEMA")
    artifact = authorization.get("retained_shared_output", {})
    manifest = authorization.get("private_manifest", {})
    root_fd = os.open(output_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        root_metadata = os.fstat(root_fd)
        require(stat.S_ISDIR(root_metadata.st_mode), "OUTPUT_ROOT_DIRECTORY")
        require(root_metadata.st_uid == os.getuid(), "OUTPUT_ROOT_OWNER")

        manifest_fd, _, manifest_raw = open_leaf(root_fd, manifest.get("relative_path"), manifest.get("byte_length"))
        try:
            require(hashlib.sha256(manifest_raw).hexdigest() == manifest.get("sha256"), "PRIVATE_MANIFEST_IDENTITY")
            validate_manifest(manifest_raw, artifact)
        finally:
            os.close(manifest_fd)

        descriptor, before_metadata, before = open_leaf(root_fd, artifact.get("relative_path"), 24576)
        try:
            before_sha = hashlib.sha256(before).hexdigest()
            require(before_sha == artifact.get("sha256"), "SHARED_OUTPUT_BEFORE_IDENTITY")
            require(artifact.get("dtype") == "little-endian-f32", "SHARED_OUTPUT_DTYPE")
            require(artifact.get("shape") == [6144] and artifact.get("byte_length") == 24576, "SHARED_OUTPUT_GEOMETRY")
            values = struct.unpack("<6144f", before)
            require(all(math.isfinite(value) for value in values), "SHARED_OUTPUT_NONFINITE")
            consumed_sha = hashlib.sha256(before).hexdigest()
            after = read_exact(descriptor, 24576)
            after_metadata = os.fstat(descriptor)
            after_sha = hashlib.sha256(after).hexdigest()
            require((before_metadata.st_dev, before_metadata.st_ino) == (after_metadata.st_dev, after_metadata.st_ino), "SHARED_OUTPUT_OBJECT_CHANGED")
            require(before_sha == consumed_sha == after_sha == artifact.get("sha256"), "EXPECTED_BEFORE_CONSUMED_AFTER")
        finally:
            os.close(descriptor)
    finally:
        os.close(root_fd)

    return {
        "disposition": "REPRESENTATIVE_SHARED_EXPERT_OUTPUT_REUSE_PREFLIGHT_PASS",
        "expected_sha256": artifact["sha256"],
        "before_sha256": before_sha,
        "consumed_sha256": consumed_sha,
        "after_sha256": after_sha,
        "finite_count": len(values),
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "shared_expert_recomputations": 0,
        "ffn_completions": 0,
        "s2_constructions": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    arguments = parser.parse_args()
    document = json.loads(arguments.authorization.read_text(encoding="utf-8"))
    print(json.dumps(preflight_and_consume(document, arguments.output_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
