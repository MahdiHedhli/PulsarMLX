#!/usr/bin/env python3
"""Idempotent package-owned descriptor leases for lifecycle V9."""
from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


FIELDS = {"device", "inode", "mode", "size", "mtime_ns", "ctime_ns", "shard_ordinal", "role", "lease_id"}
LEASE_PATTERN = re.compile(r"[A-Z0-9](?:[A-Z0-9-]{0,126}[A-Z0-9])?")
STATES = {"OPEN", "CLOSE_ATTEMPTED", "CLOSED", "CLOSE_FAILED", "UNKNOWN"}


def validate_descriptors(value: object, expected_sizes: list[int] | None = None) -> list[dict]:
    if type(value) is not list or len(value) != 5:
        raise ValueError("descriptor collection must contain exactly five entries")
    if any(type(item) is not dict for item in value):
        raise ValueError("descriptor entry must be an exact dictionary")
    entries: list[dict] = value
    if any(set(item) != FIELDS for item in entries):
        raise ValueError("descriptor key census")
    lease_ids: list[str] = []
    for item in entries:
        for key in ("device", "inode", "mode", "size", "mtime_ns", "ctime_ns", "shard_ordinal"):
            if type(item[key]) is not int or item[key] < 0:
                raise ValueError(f"descriptor integer field: {key}")
        mode = item["mode"]
        if mode >= 2**16:
            raise ValueError("descriptor mode outside 16-bit POSIX domain")
        if not stat.S_ISREG(mode):
            raise ValueError("descriptor is not a regular file")
        if type(item["role"]) is not str or item["role"] != "GRAPH_PAYLOAD":
            raise ValueError("descriptor role")
        lease_id = item["lease_id"]
        if type(lease_id) is not str:
            raise ValueError("lease-id type")
        if LEASE_PATTERN.fullmatch(lease_id) is None or any(marker in lease_id for marker in ("INERT", "FIXTURE", "TEST", "SYNTHETIC")):
            raise ValueError("lease-id grammar")
        lease_ids.append(lease_id)
    if [item["shard_ordinal"] for item in entries] != [2, 3, 4, 5, 6]:
        raise ValueError("descriptor ordinal census")
    if expected_sizes is not None and [item["size"] for item in entries] != expected_sizes:
        raise ValueError("descriptor size census")
    if len(set(lease_ids)) != 5 or len({(item["device"], item["inode"]) for item in entries}) != 5:
        raise ValueError("duplicate descriptor lease")
    return entries


@dataclass
class LeaseRecord:
    identity: dict
    descriptor: int
    state: str = "OPEN"
    close_attempt_count: int = 0
    close_result: str | None = None
    close_event_sha256: str | None = None
    pending_close_event: dict | None = None
    close_evidence_error: str | None = None

    def __post_init__(self) -> None:
        if self.state not in STATES or type(self.descriptor) is not int or self.descriptor < 0:
            raise ValueError("lease runtime record")


CloseFunction = Callable[[int, str], None]
EventFunction = Callable[[dict], str]
IdentityProgress = Callable[[str, int, str], None]


@dataclass
class LeaseSet:
    records: list[LeaseRecord]
    identity_only_digest: str
    graph_digests: list[str]
    release_passes: int = 0
    journal: list[dict] = field(default_factory=list)

    @property
    def descriptors(self) -> list[dict]:
        return [record.identity for record in self.records]

    @property
    def closed(self) -> bool:
        return all(record.state == "CLOSED" for record in self.records)

    def inherited_fds(self) -> list[int]:
        if any(record.state != "OPEN" for record in self.records):
            raise ValueError("descriptor lease is not open")
        return [record.descriptor for record in self.records]

    def release(self, *, close_function: CloseFunction | None = None, event_function: EventFunction | None = None,
                retry_failed: bool = False) -> dict:
        self.release_passes += 1
        close_function = close_function or (lambda descriptor, _lease_id: os.close(descriptor))
        attempted = successful = duplicates = 0
        events: list[dict] = []
        for record in self.records:
            # A prior pass may have closed the descriptor successfully while
            # durable close-event banking failed.  Recovery banks evidence
            # only; it never closes the descriptor again.
            if record.state == "CLOSED" and record.pending_close_event is not None and event_function is not None:
                pending = dict(record.pending_close_event)
                try:
                    record.close_event_sha256 = event_function(pending)
                except Exception as exc:
                    record.close_evidence_error = type(exc).__name__
                else:
                    record.pending_close_event = None
                    record.close_evidence_error = None
                pending["close_event_sha256"] = record.close_event_sha256
                pending["evidence_result"] = "PASS" if record.pending_close_event is None else "FAIL_BANKING"
                events.append(pending); self.journal.append(dict(pending))
                continue
            if record.state == "CLOSED":
                continue
            if record.state == "CLOSE_FAILED" and not retry_failed:
                continue
            if record.state not in {"OPEN", "CLOSE_FAILED"}:
                record.state = "UNKNOWN"
                continue
            record.state = "CLOSE_ATTEMPTED"
            record.close_attempt_count += 1
            attempted += 1
            event = {"lease_id": record.identity["lease_id"], "shard_ordinal": record.identity["shard_ordinal"],
                     "attempt": record.close_attempt_count, "prior_state": "OPEN" if record.close_attempt_count == 1 else "CLOSE_FAILED"}
            try:
                close_function(record.descriptor, record.identity["lease_id"])
                record.state = "CLOSED"; record.close_result = "PASS_CLOSE"; successful += 1
            except OSError as exc:
                record.state = "CLOSE_FAILED"
                record.close_result = "FAIL_EBADF" if exc.errno == errno.EBADF else f"FAIL_ERRNO_{exc.errno}"
            event["result"] = record.close_result; event["state"] = record.state
            if event_function is not None:
                try:
                    record.close_event_sha256 = event_function(event)
                except Exception as exc:
                    record.pending_close_event = dict(event)
                    record.close_evidence_error = type(exc).__name__
            event["close_event_sha256"] = record.close_event_sha256
            event["evidence_result"] = "PASS" if record.pending_close_event is None else "FAIL_BANKING"
            events.append(event); self.journal.append(dict(event))
        live = [record.identity["lease_id"] for record in self.records if record.state != "CLOSED"]
        pending_evidence = [record.identity["lease_id"] for record in self.records if record.pending_close_event is not None]
        return {
            "release_pass": self.release_passes, "expected_leases": 5, "attempted_closures": attempted,
            "successful_closures": successful, "duplicate_closures": duplicates,
            "unknown_leases": sum(record.state == "UNKNOWN" for record in self.records),
            "live_leases_after_release": len(live), "remaining_live_lease_ids": live,
            "lease_states": {record.identity["lease_id"]: record.state for record in self.records},
            "close_events": events, "idempotent_noop": attempted == 0,
            "pending_close_evidence": pending_evidence, "evidence_banking_failures": len(pending_evidence),
            "result": "PASS" if not live and not pending_evidence else ("EVIDENCE_FAILURE" if not live else "PARTIAL_FAILURE"),
        }


def _hash_descriptor(descriptor: int, expected_size: int) -> tuple[str, os.stat_result]:
    before = os.fstat(descriptor)
    if type(before.st_mode) is not int or before.st_mode < 0 or before.st_mode >= 2**16 or not stat.S_ISREG(before.st_mode):
        raise ValueError("opened shard mode")
    if before.st_size != expected_size:
        raise ValueError("opened shard size")
    digest = hashlib.sha256(); offset = 0
    while offset < expected_size:
        block = os.pread(descriptor, min(1024 * 1024, expected_size - offset), offset)
        if not block:
            raise ValueError("short descriptor read")
        digest.update(block); offset += len(block)
    after = os.fstat(descriptor)
    identity = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    if identity(before) != identity(after):
        raise ValueError("shard changed during identity hash")
    return digest.hexdigest(), after


def _validate_synthetic_root(candidate: dict) -> tuple[Path, dict]:
    root = Path(candidate["checkpoint_root"])
    if root.is_symlink():
        raise ValueError("synthetic root symlink")
    resolved = root.resolve(strict=True)
    temporary_authority = Path(tempfile.gettempdir()).resolve(strict=True)
    if not resolved.is_relative_to(temporary_authority):
        raise ValueError("synthetic root is outside test-owned temporary authority")
    manifest_path = Path(candidate["synthetic_root_manifest_path"])
    if manifest_path.parent.resolve(strict=True) != resolved or manifest_path.is_symlink():
        raise ValueError("synthetic root manifest location")
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != candidate["synthetic_root_manifest_sha256"]:
        raise ValueError("synthetic root manifest digest")
    manifest = json.loads(raw)
    expected = {"schema", "purpose", "production_access", "synthetic_package_id", "root_canonical_path", "shards", "catalog_sha256"}
    if type(manifest) is not dict or set(manifest) != expected:
        raise ValueError("synthetic root manifest census")
    if manifest["schema"] != "pulsarmlx.f017.synthetic-root-manifest/9.0.0" or manifest["purpose"] != "SYNTHETIC_QUALIFICATION" or manifest["production_access"] != "PROHIBITED":
        raise ValueError("synthetic root authority")
    if manifest["root_canonical_path"] != str(resolved) or manifest["shards"] != candidate["shards"]:
        raise ValueError("synthetic root binding")
    if any(not item["filename"].startswith("synthetic-v9-") for item in candidate["shards"]):
        raise ValueError("production shard name rejected in synthetic mode")
    return resolved, manifest


def acquire_synthetic_leases(candidate: dict, progress: IdentityProgress | None = None) -> LeaseSet:
    if candidate.get("scope") != "SYNTHETIC_QUALIFICATION" or candidate.get("live") is not False:
        raise ValueError("V9 qualification leases require non-live synthetic authority")
    root, _ = _validate_synthetic_root(candidate)
    root_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    records: list[LeaseRecord] = []; digests: list[str] = []; identity_only_digest = ""
    try:
        for ordinal, shard in enumerate(candidate["shards"], start=1):
            fd = os.open(shard["filename"], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
            try:
                observed_digest, metadata = _hash_descriptor(fd, shard["size_bytes"])
                if observed_digest != shard["sha256"]:
                    raise ValueError("shard identity hash mismatch")
                if progress is not None:
                    progress("ACCESS_EVENT", ordinal, observed_digest)
                    progress("SHARD_RECEIPT", ordinal, observed_digest)
                if ordinal == 1:
                    identity_only_digest = observed_digest
                else:
                    identity = {"device": metadata.st_dev, "inode": metadata.st_ino, "mode": metadata.st_mode,
                                "size": metadata.st_size, "mtime_ns": metadata.st_mtime_ns, "ctime_ns": metadata.st_ctime_ns,
                                "shard_ordinal": ordinal, "role": "GRAPH_PAYLOAD",
                                "lease_id": f"LEASE-{candidate['package_attempt_id']}-{ordinal}"}
                    records.append(LeaseRecord(identity, fd)); fd = -1; digests.append(observed_digest)
            finally:
                if fd >= 0:
                    os.close(fd)
        validate_descriptors([record.identity for record in records], [item["size_bytes"] for item in candidate["shards"][1:]])
        return LeaseSet(records, identity_only_digest, digests)
    except Exception:
        for record in records:
            try: os.close(record.descriptor)
            except OSError: pass
        raise
    finally:
        os.close(root_fd)


def acquire_production_leases(candidate: dict, installation_receipt_sha256: str,
                              progress: IdentityProgress | None = None) -> LeaseSet:
    """Acquire six production shards after installed-authority validation.

    This function is intentionally unreachable from rehearsal and synthetic
    entry points.  It is the future Event-04 identity-stage primitive and is
    never invoked during this no-access preparation phase.
    """
    if (candidate.get("scope") != "PRODUCTION_EVENT_04" or candidate.get("state") != "OPERATOR_APPROVED_CANDIDATE"
            or type(installation_receipt_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", installation_receipt_sha256) is None):
        raise ValueError("production lease authority")
    root = Path(candidate["checkpoint_root"])
    if not root.is_absolute() or root.is_symlink():
        raise ValueError("production checkpoint root")
    resolved = root.resolve(strict=True)
    root_fd = os.open(resolved, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    records: list[LeaseRecord] = []; digests: list[str] = []; identity_only_digest = ""
    try:
        for ordinal, shard in enumerate(candidate["shards"], start=1):
            fd = os.open(shard["filename"], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
            try:
                observed_digest, metadata = _hash_descriptor(fd, shard["size_bytes"])
                if observed_digest != shard["sha256"]:
                    raise ValueError("production shard identity hash mismatch")
                if progress is not None:
                    progress("ACCESS_EVENT", ordinal, observed_digest)
                    progress("SHARD_RECEIPT", ordinal, observed_digest)
                if ordinal == 1:
                    identity_only_digest = observed_digest
                else:
                    identity = {"device": metadata.st_dev, "inode": metadata.st_ino, "mode": metadata.st_mode,
                                "size": metadata.st_size, "mtime_ns": metadata.st_mtime_ns, "ctime_ns": metadata.st_ctime_ns,
                                "shard_ordinal": ordinal, "role": "GRAPH_PAYLOAD",
                                "lease_id": f"LEASE-{candidate['package_attempt_id']}-{ordinal}"}
                    records.append(LeaseRecord(identity, fd)); fd = -1; digests.append(observed_digest)
            finally:
                if fd >= 0:
                    os.close(fd)
        validate_descriptors([record.identity for record in records], [item["size_bytes"] for item in candidate["shards"][1:]])
        return LeaseSet(records, identity_only_digest, digests)
    except Exception:
        for record in records:
            try: os.close(record.descriptor)
            except OSError: pass
        raise
    finally:
        os.close(root_fd)
