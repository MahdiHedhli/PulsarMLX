#!/usr/bin/env python3
"""Open-once resolver for banked representative F017 expert outputs.

This module validates and consumes the same file descriptor.  It has no
checkpoint, shard, expert-compute, or aggregate-compute capability.
"""

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


def load_json(path: Path) -> dict[str, Any]:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            require(key not in result, f"duplicate key: {key}")
            result[key] = value
        return result

    value = json.loads(path.read_text(), object_pairs_hook=no_duplicates)
    require(isinstance(value, dict), "authorization must be an object")
    return value


def _read_fd(fd: int, expected_size: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = expected_size
    while remaining:
        chunk = os.read(fd, min(remaining, 1024 * 1024))
        require(bool(chunk), "short retained-output read")
        chunks.append(chunk)
        remaining -= len(chunk)
    require(os.read(fd, 1) == b"", "retained output exceeds expected size")
    return b"".join(chunks)


def preflight_and_consume(authorization: dict[str, Any], output_root: Path) -> dict[str, Any]:
    records = authorization.get("atomic_id_weight_output_triples")
    require(isinstance(records, list) and len(records) == 8, "eight atomic triples required")
    root_meta = output_root.lstat()
    require(stat.S_ISDIR(root_meta.st_mode) and not stat.S_ISLNK(root_meta.st_mode), "output root")
    results: list[dict[str, Any]] = []
    for ordinal, item in enumerate(records):
        require(item.get("ordinal") == ordinal, "triple order")
        relative = item.get("private_relative_path")
        require(isinstance(relative, str) and Path(relative).name == relative, "private relative path")
        target = output_root / relative
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(target, flags)
        try:
            before_stat = os.fstat(fd)
            require(stat.S_ISREG(before_stat.st_mode), "retained output must be regular")
            require(before_stat.st_nlink == 1, "retained output link count")
            require(before_stat.st_mode & 0o222 == 0, "retained output must be read-only")
            require(before_stat.st_size == item.get("byte_length") == 24576, "retained output size")
            before = _read_fd(fd, 24576)
            before_sha = hashlib.sha256(before).hexdigest()
            require(before_sha == item.get("output_sha256"), "retained output BEFORE identity")
            values = struct.unpack("<6144f", before)
            require(item.get("dtype") == "little-endian-f32" and item.get("shape") == [6144], "dtype/shape")
            require(all(math.isfinite(value) for value in values), "non-finite retained output")

            # Consumer bytes are the exact bytes read from the validated descriptor.
            consumed_sha = hashlib.sha256(before).hexdigest()
            after = _read_fd(fd, 24576)
            after_stat = os.fstat(fd)
            after_sha = hashlib.sha256(after).hexdigest()
            require((before_stat.st_dev, before_stat.st_ino) == (after_stat.st_dev, after_stat.st_ino),
                    "retained output object changed")
            require(before_sha == consumed_sha == after_sha == item.get("output_sha256"),
                    "EXPECTED != BEFORE != CONSUMED != AFTER")
            results.append({
                "ordinal": ordinal,
                "expert_id": item["expert_id"],
                "expected_sha256": item["output_sha256"],
                "before_sha256": before_sha,
                "consumed_sha256": consumed_sha,
                "after_sha256": after_sha,
                "finite_count": len(values),
                "device": before_stat.st_dev,
                "inode": before_stat.st_ino,
            })
        finally:
            os.close(fd)
    return {
        "disposition": "REPRESENTATIVE_EXPERT_OUTPUT_REUSE_PREFLIGHT_PASS",
        "outputs": results,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "expert_executions": 0,
        "aggregate_executions": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(preflight_and_consume(load_json(args.authorization), args.output_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
