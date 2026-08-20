#!/usr/bin/env python3
"""Open-once, checkpoint-free resolver for the banked routed aggregate."""

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


def _read_fd(fd: int, size: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = os.read(fd, min(remaining, 1024 * 1024))
        require(bool(chunk), "short retained aggregate read")
        chunks.append(chunk)
        remaining -= len(chunk)
    require(os.read(fd, 1) == b"", "retained aggregate exceeds expected size")
    return b"".join(chunks)


def _open_validated(root_fd: int, name: str, expected_size: int) -> tuple[int, os.stat_result, bytes]:
    require(Path(name).name == name, "pure basename required")
    fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
    meta = os.fstat(fd)
    require(stat.S_ISREG(meta.st_mode), "regular file required")
    require(meta.st_nlink == 1, "single hard link required")
    require(meta.st_mode & 0o222 == 0, "read-only file required")
    require(meta.st_size == expected_size, "unexpected byte length")
    return fd, meta, _read_fd(fd, expected_size)


def preflight_and_consume(authorization: dict[str, Any], output_root: Path) -> dict[str, Any]:
    artifact = authorization.get("retained_aggregate", {})
    manifest = authorization.get("private_manifest", {})
    root_fd = os.open(output_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        root_meta = os.fstat(root_fd)
        require(stat.S_ISDIR(root_meta.st_mode), "output root must be a directory")

        manifest_name = manifest.get("relative_path")
        manifest_fd, _, manifest_raw = _open_validated(root_fd, manifest_name, manifest.get("byte_length"))
        try:
            require(hashlib.sha256(manifest_raw).hexdigest() == manifest.get("sha256"), "private manifest identity")
            manifest_doc = json.loads(manifest_raw)
            require(manifest_doc.get("schema") == "pulsarmlx.f017.representative-routed-aggregate-private-manifest", "private manifest schema")
            entries = manifest_doc.get("artifacts")
            require(isinstance(entries, list) and len(entries) == 1, "one manifest artifact required")
            entry = entries[0]
            require(entry.get("symbolic_path") == artifact.get("relative_path"), "manifest path binding")
            require(entry.get("sha256") == artifact.get("sha256"), "manifest output binding")
            require(entry.get("semantic_role") == artifact.get("semantic_role"), "manifest role binding")
        finally:
            os.close(manifest_fd)

        fd, before_stat, before = _open_validated(root_fd, artifact.get("relative_path"), 49152)
        try:
            before_sha = hashlib.sha256(before).hexdigest()
            require(before_sha == artifact.get("sha256"), "retained aggregate BEFORE identity")
            require(artifact.get("dtype") == "little-endian-f64", "aggregate dtype")
            require(artifact.get("shape") == [6144] and artifact.get("byte_length") == 49152, "aggregate geometry")
            values = struct.unpack("<6144d", before)
            require(all(math.isfinite(value) for value in values), "non-finite retained aggregate")

            consumed_sha = hashlib.sha256(before).hexdigest()
            after = _read_fd(fd, 49152)
            after_stat = os.fstat(fd)
            after_sha = hashlib.sha256(after).hexdigest()
            require((before_stat.st_dev, before_stat.st_ino) == (after_stat.st_dev, after_stat.st_ino), "retained object changed")
            require(before_sha == consumed_sha == after_sha == artifact.get("sha256"), "EXPECTED != BEFORE != CONSUMED != AFTER")
        finally:
            os.close(fd)
    finally:
        os.close(root_fd)

    return {
        "disposition": "REPRESENTATIVE_ROUTED_AGGREGATE_REUSE_PREFLIGHT_PASS",
        "expected_sha256": artifact["sha256"],
        "before_sha256": before_sha,
        "consumed_sha256": consumed_sha,
        "after_sha256": after_sha,
        "finite_count": len(values),
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "aggregate_recomputations": 0,
        "shared_expert_executions": 0,
        "ffn_completions": 0,
        "s2_constructions": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    doc = json.loads(args.authorization.read_text())
    print(json.dumps(preflight_and_consume(doc, args.output_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
