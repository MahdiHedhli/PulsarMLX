#!/usr/bin/env python3
"""Package-owned descriptor leases for synthetic V8 qualification."""
from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path


FIELDS = {"device", "inode", "mode", "size", "mtime_ns", "ctime_ns", "shard_ordinal", "role", "lease_id"}
LEASE_PATTERN = re.compile(r"[A-Z0-9](?:[A-Z0-9-]{0,126}[A-Z0-9])?")


def validate_descriptors(value: object, expected_sizes: list[int] | None = None) -> list[dict]:
    if type(value) is not list or len(value) != 5:
        raise ValueError("descriptor collection must contain exactly five entries")
    if any(type(item) is not dict for item in value):
        raise ValueError("descriptor entry must be an exact dictionary")
    entries: list[dict] = value
    if any(set(item) != FIELDS for item in entries):
        raise ValueError("descriptor key census")
    for item in entries:
        for key in ("device", "inode", "mode", "size", "mtime_ns", "ctime_ns", "shard_ordinal"):
            if type(item[key]) is not int or item[key] < 0:
                raise ValueError(f"descriptor integer field: {key}")
        if item["mode"] >= 2**16:
            raise ValueError("descriptor mode outside 16-bit POSIX domain")
        if not stat.S_ISREG(item["mode"]):
            raise ValueError("descriptor is not a regular file")
        if type(item["role"]) is not str or item["role"] != "GRAPH_PAYLOAD":
            raise ValueError("descriptor role")
        lease_id = item["lease_id"]
        if (type(lease_id) is not str or LEASE_PATTERN.fullmatch(lease_id) is None
                or any(marker in lease_id for marker in ("INERT", "FIXTURE", "TEST", "SYNTHETIC"))):
            raise ValueError("lease-id type or grammar")
    if [item["shard_ordinal"] for item in entries] != [2, 3, 4, 5, 6]:
        raise ValueError("descriptor ordinal census")
    if expected_sizes is not None and [item["size"] for item in entries] != expected_sizes:
        raise ValueError("descriptor size census")
    lease_ids = [item["lease_id"] for item in entries]
    if len(set(lease_ids)) != 5 or len({(item["device"], item["inode"]) for item in entries}) != 5:
        raise ValueError("duplicate descriptor lease")
    return entries


@dataclass
class LeaseSet:
    descriptors: list[dict]
    file_descriptors: list[int]
    identity_only_digest: str
    graph_digests: list[str]
    closed: bool = False

    def inherited_fds(self) -> list[int]:
        if self.closed:
            raise ValueError("descriptor leases already released")
        return list(self.file_descriptors)

    def release(self) -> dict:
        if self.closed:
            raise ValueError("descriptor leases already released")
        successful = 0
        for descriptor in self.file_descriptors:
            os.close(descriptor)
            successful += 1
        self.closed = True
        return {"attempted_closures": 5, "successful_closures": successful, "duplicate_closures": 0, "unknown_leases": 0, "live_leases_after_release": 0, "lease_ids": [item["lease_id"] for item in self.descriptors]}


def _hash_descriptor(descriptor: int, expected_size: int) -> tuple[str, os.stat_result]:
    before = os.fstat(descriptor)
    if type(before.st_mode) is not int or before.st_mode < 0 or before.st_mode >= 2**16 or not stat.S_ISREG(before.st_mode):
        raise ValueError("opened shard mode")
    if before.st_size != expected_size:
        raise ValueError("opened shard size")
    digest = hashlib.sha256()
    offset = 0
    while offset < expected_size:
        block = os.pread(descriptor, min(1024 * 1024, expected_size - offset), offset)
        if not block:
            raise ValueError("short descriptor read")
        digest.update(block)
        offset += len(block)
    after = os.fstat(descriptor)
    if (before.st_dev, before.st_ino, before.st_mode, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_mode, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError("shard changed during identity hash")
    return digest.hexdigest(), after


def acquire_synthetic_leases(candidate: dict) -> LeaseSet:
    if candidate.get("synthetic_only") is not True or candidate.get("live") is not False:
        raise ValueError("V8 qualification leases require non-live synthetic authority")
    root = Path(candidate["checkpoint_root"])
    root_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    graph_fds: list[int] = []
    descriptors: list[dict] = []
    digests: list[str] = []
    identity_only_digest = ""
    try:
        for ordinal, shard in enumerate(candidate["shards"], start=1):
            fd = os.open(shard["filename"], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
            try:
                observed_digest, metadata = _hash_descriptor(fd, shard["size_bytes"])
                if observed_digest != shard["sha256"]:
                    raise ValueError("shard identity hash mismatch")
                if ordinal == 1:
                    identity_only_digest = observed_digest
                else:
                    graph_fds.append(fd)
                    fd = -1
                    digests.append(observed_digest)
                    descriptors.append({
                        "device": metadata.st_dev,
                        "inode": metadata.st_ino,
                        "mode": metadata.st_mode,
                        "size": metadata.st_size,
                        "mtime_ns": metadata.st_mtime_ns,
                        "ctime_ns": metadata.st_ctime_ns,
                        "shard_ordinal": ordinal,
                        "role": "GRAPH_PAYLOAD",
                        "lease_id": f"LEASE-{candidate['package_attempt_id']}-{ordinal}",
                    })
            finally:
                if fd >= 0:
                    os.close(fd)
        validate_descriptors(descriptors, [item["size_bytes"] for item in candidate["shards"][1:]])
        return LeaseSet(descriptors, graph_fds, identity_only_digest, digests)
    except Exception:
        for fd in graph_fds:
            try:
                os.close(fd)
            except OSError:
                pass
        raise
    finally:
        os.close(root_fd)
