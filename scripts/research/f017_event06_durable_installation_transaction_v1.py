#!/usr/bin/env python3
"""No-replace durable transaction engine for Event 06 installation bytes.

The public surface qualifies synthetic, non-authority bytes.  The production
entry point is private and is called only after the version-forward future-GO
capability checker accepts a sealed capability.
"""

from __future__ import annotations

import copy
import hashlib
import os
import pickle
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Never, Self, SupportsIndex

from f017_canonical_serialization_v10 import canonical_bytes

FAILURE_OUTCOMES: Final = {
    "exclusive_create": "F017_V12_PRODUCTION_INSTALL_TARGET_EXISTS",
    "target_identity": "F017_V12_PRODUCTION_INSTALL_TARGET_EXISTS",
    "write_short": "F017_V12_PRODUCTION_INSTALL_WRITE_FAILURE",
    "write_error": "F017_V12_PRODUCTION_INSTALL_WRITE_FAILURE",
    "file_fsync": "F017_V12_PRODUCTION_INSTALL_FSYNC_FAILURE",
    "directory_fsync": "F017_V12_PRODUCTION_INSTALL_FSYNC_FAILURE",
    "readback_identity": "F017_V12_PRODUCTION_INSTALL_READBACK_MISMATCH",
    "concurrent_replacement": "F017_V12_PRODUCTION_INSTALL_PARTIAL_COMMIT",
    "capability_expiry": "F017_V12_PRODUCTION_INSTALL_CAPABILITY_EXPIRED",
    "candidate_replay": "F017_V12_PRODUCTION_INSTALL_REPLAY",
}

RACE_FAMILIES: Final = tuple(FAILURE_OUTCOMES)
_RESULT_SEAL = object()


class DurableTransactionError(RuntimeError):
    """Stable transaction failure with the accepted installation outcome ID."""

    def __init__(self, outcome_id: str, detail: str):
        super().__init__(f"{outcome_id}: {detail}")
        self.outcome_id = outcome_id
        self.detail = detail


@dataclass(frozen=True, slots=True)
class TransactionPayload:
    """One immutable leaf written by the storage engine."""

    role: str
    leaf: str
    data: bytes


class DurableTransactionResult:
    """Opaque repository-created durable transaction result."""

    __slots__ = (
        "transaction_sha256",
        "receipt_sha256",
        "payload_sha256",
        "scope",
        "target_leaf",
        "_locked",
    )
    transaction_sha256: str
    receipt_sha256: str
    payload_sha256: tuple[tuple[str, str], ...]
    scope: str
    target_leaf: str
    _locked: bool

    def __new__(cls, seal: object = None, *args: object, **kwargs: object) -> Self:
        del args, kwargs
        if seal is not _RESULT_SEAL:
            raise TypeError("durable transaction results are repository-created")
        return super().__new__(cls)

    def __init__(
        self,
        seal: object,
        *,
        transaction_sha256: str,
        receipt_sha256: str,
        payload_sha256: tuple[tuple[str, str], ...],
        scope: str,
        target_leaf: str,
    ) -> None:
        del seal
        object.__setattr__(self, "transaction_sha256", transaction_sha256)
        object.__setattr__(self, "receipt_sha256", receipt_sha256)
        object.__setattr__(self, "payload_sha256", payload_sha256)
        object.__setattr__(self, "scope", scope)
        object.__setattr__(self, "target_leaf", target_leaf)
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> Never:
        del name, value
        raise TypeError("durable transaction results are immutable")

    def __copy__(self) -> Never:
        raise TypeError("durable transaction results cannot be copied")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("durable transaction results cannot be copied")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        del protocol
        raise TypeError("durable transaction results cannot be pickled")


def _fail(family: str, detail: str) -> DurableTransactionError:
    outcome = FAILURE_OUTCOMES.get(family)
    if outcome is None:
        raise ValueError(f"unknown transaction failure family: {family}")
    return DurableTransactionError(outcome, detail)


def _leaf(value: str) -> str:
    if (
        type(value) is not str
        or not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or value.startswith(".")
    ):
        raise ValueError("transaction leaf must be one visible path component")
    return value


def _validate_payloads(
    payloads: tuple[TransactionPayload, ...],
) -> tuple[TransactionPayload, ...]:
    if type(payloads) is not tuple or not payloads:
        raise ValueError("transaction payloads must be a nonempty tuple")
    roles: set[str] = set()
    leaves: set[str] = set()
    for payload in payloads:
        if type(payload) is not TransactionPayload:
            raise TypeError("transaction payload type")
        if type(payload.role) is not str or not payload.role:
            raise ValueError("transaction payload role")
        leaf = _leaf(payload.leaf)
        if payload.role in roles or leaf in leaves or type(payload.data) is not bytes:
            raise ValueError("transaction payload census")
        roles.add(payload.role)
        leaves.add(leaf)
    if "transaction-receipt.json" in leaves:
        raise ValueError("transaction receipt leaf is reserved")
    return payloads


def _write_all(descriptor: int, data: bytes, *, short: bool = False) -> None:
    offset = 0
    limit = len(data) - 1 if short and data else len(data)
    while offset < limit:
        written = os.write(descriptor, data[offset:limit])
        if written <= 0:
            raise OSError("zero-length transaction write")
        offset += written
    if offset != len(data):
        raise _fail("write_short", "payload byte counter")


def _read_exact(directory_fd: int, leaf: str, expected: bytes) -> tuple[int, int]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(leaf, flags, dir_fd=directory_fd)
    try:
        identity = os.fstat(descriptor)
        if not stat.S_ISREG(identity.st_mode) or identity.st_nlink != 1:
            raise _fail("readback_identity", leaf)
        chunks: list[bytes] = []
        remaining = len(expected) + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        observed = b"".join(chunks)
        if observed != expected:
            raise _fail("readback_identity", leaf)
        return identity.st_dev, identity.st_ino
    finally:
        os.close(descriptor)


def _commit_no_replace(
    parent: Path,
    target_leaf: str,
    payloads: tuple[TransactionPayload, ...],
    *,
    scope: str,
    consumption_marker: str | None,
    fault_stage: str | None,
) -> DurableTransactionResult:
    """Commit one transaction beneath an already-existing trusted parent."""

    target_leaf = _leaf(target_leaf)
    payloads = _validate_payloads(payloads)
    if scope not in {"SYNTHETIC_NON_AUTHORITY", "PRODUCTION"}:
        raise ValueError("transaction scope")
    if fault_stage is not None and fault_stage not in RACE_FAMILIES:
        raise ValueError("unknown transaction fault stage")
    if scope == "PRODUCTION" and fault_stage is not None:
        raise ValueError("production fault injection is prohibited")

    parent_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    parent_fd = os.open(parent, parent_flags)
    target_fd = -1
    created = False
    try:
        parent_identity = os.fstat(parent_fd)
        if not stat.S_ISDIR(parent_identity.st_mode):
            raise _fail("target_identity", "parent is not a directory")
        if fault_stage == "capability_expiry":
            raise _fail("capability_expiry", "injected before authority consumption")

        if consumption_marker is not None:
            marker = _leaf(consumption_marker)
            marker_fd = os.open(
                marker,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o400,
                dir_fd=parent_fd,
            )
            try:
                _write_all(marker_fd, b"CONSUMED\n")
                os.fsync(marker_fd)
            finally:
                os.close(marker_fd)
            os.fsync(parent_fd)

        if fault_stage in {"exclusive_create", "candidate_replay"}:
            raise _fail(fault_stage, "injected before target creation")
        try:
            os.mkdir(target_leaf, 0o700, dir_fd=parent_fd)
            created = True
        except FileExistsError as exc:
            family = (
                "candidate_replay"
                if consumption_marker is not None
                else "exclusive_create"
            )
            raise _fail(family, target_leaf) from exc

        target_fd = os.open(
            target_leaf,
            parent_flags,
            dir_fd=parent_fd,
        )
        target_identity = os.fstat(target_fd)
        if not stat.S_ISDIR(target_identity.st_mode):
            raise _fail("target_identity", target_leaf)
        if fault_stage == "target_identity":
            raise _fail("target_identity", "injected target identity change")

        payload_digests: list[tuple[str, str]] = []
        file_identities: list[tuple[str, int, int]] = []
        for index, payload in enumerate(payloads):
            descriptor = -1
            try:
                descriptor = os.open(
                    payload.leaf,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o400,
                    dir_fd=target_fd,
                )
                if fault_stage == "write_error" and index == 0:
                    raise OSError("injected transaction write failure")
                _write_all(
                    descriptor,
                    payload.data,
                    short=fault_stage == "write_short" and index == 0,
                )
                if fault_stage == "file_fsync" and index == 0:
                    raise OSError("injected file fsync failure")
                os.fsync(descriptor)
                identity = os.fstat(descriptor)
                if not stat.S_ISREG(identity.st_mode) or identity.st_nlink != 1:
                    raise _fail("target_identity", payload.leaf)
                file_identities.append((payload.role, identity.st_dev, identity.st_ino))
                payload_digests.append(
                    (payload.role, hashlib.sha256(payload.data).hexdigest())
                )
            except DurableTransactionError:
                raise
            except OSError as exc:
                family = "file_fsync" if "fsync" in str(exc) else "write_error"
                raise _fail(family, payload.leaf) from exc
            finally:
                if descriptor >= 0:
                    os.close(descriptor)

        if fault_stage == "concurrent_replacement":
            raise _fail("concurrent_replacement", "injected identity replacement")

        for payload, (_, expected_dev, expected_ino) in zip(
            payloads, file_identities, strict=True
        ):
            observed_dev, observed_ino = _read_exact(
                target_fd, payload.leaf, payload.data
            )
            if (observed_dev, observed_ino) != (expected_dev, expected_ino):
                raise _fail("readback_identity", payload.leaf)
        if fault_stage == "readback_identity":
            raise _fail("readback_identity", "injected readback mismatch")

        receipt_value = {
            "schema": "pulsarmlx.f017.event06-durable-installation-transaction-receipt/1.0.0",
            "scope": scope,
            "target_leaf": target_leaf,
            "parent_device": parent_identity.st_dev,
            "parent_inode": parent_identity.st_ino,
            "target_device": target_identity.st_dev,
            "target_inode": target_identity.st_ino,
            "payloads": [
                {
                    "role": payload.role,
                    "leaf": payload.leaf,
                    "bytes": len(payload.data),
                    "sha256": digest,
                }
                for payload, (_, digest) in zip(payloads, payload_digests, strict=True)
            ],
            "payload_count": len(payloads),
            "result": "PASS",
        }
        receipt_raw = canonical_bytes(receipt_value)
        receipt_descriptor = os.open(
            "transaction-receipt.json",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o400,
            dir_fd=target_fd,
        )
        try:
            _write_all(receipt_descriptor, receipt_raw)
            os.fsync(receipt_descriptor)
        finally:
            os.close(receipt_descriptor)
        _read_exact(target_fd, "transaction-receipt.json", receipt_raw)

        if fault_stage == "directory_fsync":
            raise _fail("directory_fsync", "injected directory fsync failure")
        os.fsync(target_fd)
        os.fsync(parent_fd)
        transaction_sha = hashlib.sha256(
            b"".join(payload.data for payload in payloads) + receipt_raw
        ).hexdigest()
        return DurableTransactionResult(
            _RESULT_SEAL,
            transaction_sha256=transaction_sha,
            receipt_sha256=hashlib.sha256(receipt_raw).hexdigest(),
            payload_sha256=tuple(payload_digests),
            scope=scope,
            target_leaf=target_leaf,
        )
    except DurableTransactionError:
        raise
    except OSError as exc:
        family = "directory_fsync" if created else "exclusive_create"
        raise _fail(family, str(exc)) from exc
    finally:
        if target_fd >= 0:
            os.close(target_fd)
        os.close(parent_fd)


def commit_synthetic_non_authority_transaction(
    disposable_root: Path,
    target_leaf: str,
    payloads: tuple[TransactionPayload, ...],
    *,
    fault_stage: str | None = None,
) -> DurableTransactionResult:
    """Qualify the engine using only an isolated synthetic root."""

    if not isinstance(disposable_root, Path):
        raise TypeError("synthetic root must be a Path")
    identity = disposable_root.lstat()
    if disposable_root.is_symlink() or not stat.S_ISDIR(identity.st_mode):
        raise ValueError("synthetic root must be a real directory")
    return _commit_no_replace(
        disposable_root,
        target_leaf,
        payloads,
        scope="SYNTHETIC_NON_AUTHORITY",
        consumption_marker=None,
        fault_stage=fault_stage,
    )


def _commit_bound_production_transaction(
    parent: Path,
    target_leaf: str,
    payloads: tuple[TransactionPayload, ...],
    *,
    consumption_marker: str,
) -> DurableTransactionResult:
    """Private success-capable production path behind the capability checker."""

    return _commit_no_replace(
        parent,
        target_leaf,
        payloads,
        scope="PRODUCTION",
        consumption_marker=consumption_marker,
        fault_stage=None,
    )


def assert_transaction_result_sealed(value: DurableTransactionResult) -> None:
    for operation in (copy.copy, copy.deepcopy, pickle.dumps):
        try:
            operation(value)
        except TypeError:
            continue
        raise TypeError("transaction result copy surface")
