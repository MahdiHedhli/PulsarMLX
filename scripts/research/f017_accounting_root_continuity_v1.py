#!/usr/bin/env python3
"""Identity-preserving accounting root and transition journal for F017."""
from __future__ import annotations

from dataclasses import dataclass
import errno
import hashlib
import os
from pathlib import Path
import stat
from typing import Final

from f017_bounded_artifact_decode_v1 import ArtifactDecodeError, parse_artifact_bytes, read_artifact_at
from f017_canonical_serialization_v10 import canonical_bytes


ZERO_SHA256: Final = "0" * 64
START_TRANSITIONS: Final = {
    "PACKAGE_DURABLE_START": "package",
    "PRIMARY_DURABLE_START": "primary",
    "SECONDARY_DURABLE_START": "secondary",
}


def _is_sha256(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
TRANSITION_ORDER: Final = {
    "INSTALLATION_RECEIPT_BANKED": 0,
    "COORDINATOR_HANDSHAKE": 1,
    "PACKAGE_CLAIM": 2,
    "PACKAGE_DURABLE_START": 3,
    "CHECKPOINT_IDENTITY_START": 4,
    "CHECKPOINT_IDENTITY_TERMINAL": 5,
    "PRIMARY_DURABLE_START": 6,
    "PRIMARY_TERMINAL": 7,
    "SECONDARY_DURABLE_START": 8,
    "SECONDARY_TERMINAL": 9,
    "COMPARISON_TERMINAL": 10,
    "DESCRIPTOR_RELEASE_TERMINAL": 11,
    "PACKAGE_TERMINAL": 12,
}


class AccountingAuthorityError(ValueError):
    """Stable failure boundary for root identity or journal authority."""


@dataclass(frozen=True)
class DirectoryIdentity:
    canonical_parent: str
    leaf_name: str
    device: int
    inode: int
    mode: int

    def as_dict(self) -> dict:
        return {
            "canonical_parent": self.canonical_parent,
            "leaf_name": self.leaf_name,
            "device": self.device,
            "inode": self.inode,
            "mode": self.mode,
        }


def _directory_identity(path: Path, descriptor: int) -> DirectoryIdentity:
    parent = path.parent
    if path.name in {"", ".", ".."} or "/" in path.name:
        raise AccountingAuthorityError("root leaf grammar")
    observed = os.fstat(descriptor)
    if not stat.S_ISDIR(observed.st_mode):
        raise AccountingAuthorityError("root descriptor is not a directory")
    return DirectoryIdentity(str(parent), path.name, observed.st_dev, observed.st_ino, observed.st_mode)


def open_directory_no_symlinks(path: Path) -> tuple[int, Path]:
    """Open an absolute directory by descriptor-relative component traversal.

    ``Path.resolve`` is used only to select a canonical spelling.  No resolved
    pathname is then opened as a unit: every component is opened relative to
    the already retained parent with ``O_NOFOLLOW``.  A final pathname/handle
    identity comparison detects replacement during acquisition.
    """
    if not isinstance(path, Path) or not path.is_absolute():
        raise AccountingAuthorityError("absolute directory path required")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise AccountingAuthorityError("directory resolution") from exc
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(resolved.anchor, flags)
    try:
        for component in resolved.parts[1:]:
            if component in {"", ".", ".."} or "/" in component:
                raise AccountingAuthorityError("directory component grammar")
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        opened = os.fstat(descriptor)
        named = os.stat(resolved, follow_symlinks=False)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or not stat.S_ISDIR(named.st_mode)
            or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
        ):
            raise AccountingAuthorityError("directory identity changed during acquisition")
        return descriptor, resolved
    except Exception:
        os.close(descriptor)
        raise


def _bank_at(directory_fd: int, leaf: str, value: dict) -> str:
    if type(leaf) is not str or not leaf or "/" in leaf or leaf in {".", ".."}:
        raise AccountingAuthorityError("artifact leaf grammar")
    raw = canonical_bytes(value)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(leaf, flags, 0o600, dir_fd=directory_fd)
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError(errno.EIO, "short artifact write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.fsync(directory_fd)
    check = os.open(leaf, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
    try:
        observed = bytearray()
        offset = 0
        while True:
            chunk = os.pread(check, 65_536, offset)
            if not chunk:
                break
            observed.extend(chunk)
            offset += len(chunk)
    finally:
        os.close(check)
    if bytes(observed) != raw:
        raise AccountingAuthorityError("descriptor-relative readback mismatch")
    return hashlib.sha256(raw).hexdigest()


class AccountingRootAuthority:
    """Package-lifetime root descriptors; fallback is an evidence sink only."""

    def __init__(self, primary: Path, fallback: Path, package_attempt_id: str,
                 authorization_sha256: str, installation_receipt_sha256: str):
        if any(type(value) is not str or not value for value in (package_attempt_id, authorization_sha256, installation_receipt_sha256)):
            raise AccountingAuthorityError("root authority binding")
        self.primary_path = primary
        self.fallback_path = fallback
        self.primary_fd = -1
        self.fallback_fd = -1
        self._journal_fd = -1
        try:
            self.primary_fd, primary_canonical = open_directory_no_symlinks(primary)
            self.fallback_fd, fallback_canonical = open_directory_no_symlinks(fallback)
            self.primary_identity = _directory_identity(primary_canonical, self.primary_fd)
            self.fallback_identity = _directory_identity(fallback_canonical, self.fallback_fd)
            if (self.primary_identity.device, self.primary_identity.inode) == (self.fallback_identity.device, self.fallback_identity.inode):
                raise AccountingAuthorityError("primary and fallback identities must differ")
            self.package_attempt_id = package_attempt_id
            self.authorization_sha256 = authorization_sha256
            self.installation_receipt_sha256 = installation_receipt_sha256
            self._journal_fd = os.open(
                "accounting-transition-journal.ndjson",
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=self.primary_fd,
            )
            journal_stat = os.fstat(self._journal_fd)
            self.journal_identity = {"device": journal_stat.st_dev, "inode": journal_stat.st_ino, "mode": journal_stat.st_mode}
        except Exception:
            self.close()
            raise
        self._sequence = 0
        self._previous_sha256 = ZERO_SHA256
        self._last_completed = "INSTALLATION_RECEIPT_BANKED"
        self._starts = {"package": 0, "primary": 0, "secondary": 0}
        self._monotonic_lower_bound = {"package": 0, "primary": 0, "secondary": 0}

    @classmethod
    def create(cls, primary: Path, fallback: Path, package_attempt_id: str,
               authorization_sha256: str, installation_receipt_sha256: str) -> "AccountingRootAuthority":
        primary.mkdir(parents=True, exist_ok=False, mode=0o700)
        fallback.mkdir(parents=True, exist_ok=False, mode=0o700)
        return cls(primary, fallback, package_attempt_id, authorization_sha256, installation_receipt_sha256)

    @classmethod
    def bind_existing(cls, primary: Path, fallback: Path, package_attempt_id: str,
                      authorization_sha256: str,
                      installation_receipt_sha256: str) -> "AccountingRootAuthority":
        return cls(primary, fallback, package_attempt_id, authorization_sha256, installation_receipt_sha256)

    def authority_record(self) -> dict:
        return {
            "schema": "pulsarmlx.f017.accounting-root-authority/1.0.0",
            "package_attempt_id": self.package_attempt_id,
            "authorization_sha256": self.authorization_sha256,
            "installation_receipt_sha256": self.installation_receipt_sha256,
            "primary_root_identity": self.primary_identity.as_dict(),
            "fallback_root_identity": self.fallback_identity.as_dict(),
            "journal_identity": self.journal_identity,
            "fallback_semantics": "EVIDENCE_SINK_NOT_ACCOUNTING_SOURCE",
        }

    def path_status(self) -> str:
        try:
            observed = self.primary_path.lstat()
        except FileNotFoundError:
            return "AUTHORITY_UNAVAILABLE"
        except OSError:
            return "AUTHORITY_UNAVAILABLE"
        if stat.S_ISLNK(observed.st_mode):
            return "IDENTITY_MISMATCH"
        if not stat.S_ISDIR(observed.st_mode):
            return "IDENTITY_MISMATCH"
        if (observed.st_dev, observed.st_ino) != (self.primary_identity.device, self.primary_identity.inode):
            return "IDENTITY_MISMATCH"
        return "OBSERVED_PRESENT"

    def verify_retained_identity(self) -> None:
        observed = os.fstat(self.primary_fd)
        if not stat.S_ISDIR(observed.st_mode) or (observed.st_dev, observed.st_ino) != (
            self.primary_identity.device, self.primary_identity.inode
        ):
            raise AccountingAuthorityError("retained root identity mismatch")

    def append_transition(self, transition_id: str, artifact_sha256: str,
                          lifecycle_outcome: str | None = None) -> dict:
        if type(transition_id) is not str or transition_id not in TRANSITION_ORDER:
            raise AccountingAuthorityError("transition identity")
        if TRANSITION_ORDER[transition_id] < TRANSITION_ORDER[self._last_completed]:
            raise AccountingAuthorityError("nonmonotonic transition")
        if not _is_sha256(artifact_sha256):
            raise AccountingAuthorityError("transition artifact digest")
        if lifecycle_outcome is not None and type(lifecycle_outcome) is not str:
            raise AccountingAuthorityError("transition lifecycle outcome")
        record = {
            "artifact_sha256": artifact_sha256,
            "lifecycle_outcome": lifecycle_outcome,
            "package_attempt_id": self.package_attempt_id,
            "previous_record_sha256": self._previous_sha256,
            "sequence": self._sequence,
            "transition_id": transition_id,
        }
        raw = canonical_bytes(record)
        view = memoryview(raw)
        while view:
            written = os.write(self._journal_fd, view)
            if written <= 0:
                raise OSError(errno.EIO, "short transition journal write")
            view = view[written:]
        os.fsync(self._journal_fd)
        digest = hashlib.sha256(raw).hexdigest()
        self._sequence += 1
        self._previous_sha256 = digest
        self._last_completed = transition_id
        role = START_TRANSITIONS.get(transition_id)
        if role is not None:
            self._starts[role] = 1
            self._monotonic_lower_bound[role] = 1
        return {**record, "record_sha256": digest}

    def bank_artifact(self, leaf: str, kind: str, payload: dict,
                      transition_id: str | None = None) -> str:
        if type(kind) is not str or not kind or type(payload) is not dict:
            raise AccountingAuthorityError("runtime artifact binding")
        digest = _bank_at(
            self.primary_fd,
            leaf,
            {"schema": f"pulsarmlx.f017.v10.runtime.{kind}/1.0.0", "artifact_kind": kind, "payload": payload},
        )
        if transition_id is not None:
            self.append_transition(transition_id, digest)
        return digest

    def bank_fallback_capsule(self, leaf: str, payload: dict) -> str:
        return _bank_at(
            self.fallback_fd,
            leaf,
            {
                "schema": "pulsarmlx.f017.v10.runtime.fallback_failure_capsule/1.0.0",
                "artifact_kind": "fallback_failure_capsule",
                "payload": {
                    **payload,
                    "accounting_authority": self.authority_record(),
                    "conservative_start_lower_bounds": dict(self._starts),
                    "last_completed_transition_id": self._last_completed,
                },
            },
        )

    def bank_terminal_artifact(self, leaf: str, kind: str, payload: dict) -> dict:
        errors: list[dict] = []
        try:
            digest = self.bank_artifact(leaf, kind, payload)
            return {"result": "PASS", "target": "BOUND_PRIMARY", "sha256": digest, "errors": errors}
        except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
            errors.append({"target": "BOUND_PRIMARY", "error": type(exc).__name__})
        try:
            digest = self.bank_fallback_capsule(
                leaf,
                {"original_artifact_kind": kind, "original_payload": payload, "primary_write_errors": errors},
            )
            return {"result": "PASS", "target": "BOUND_FALLBACK", "sha256": digest, "errors": errors}
        except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
            errors.append({"target": "BOUND_FALLBACK", "error": type(exc).__name__})
            return {"result": "MAXIMAL_CONSTRUCTIBLE_NO_DURABLE_WRITE", "target": None, "sha256": None, "errors": errors}

    def observe_start_artifact(self, leaf: str, expected_kind: str) -> str:
        try:
            value = read_artifact_at(self.primary_fd, leaf)
        except FileNotFoundError:
            return "OBSERVED_ABSENT"
        except ArtifactDecodeError:
            return "AUTHORITY_CORRUPT"
        except OSError:
            return "AUTHORITY_UNAVAILABLE"
        expected_schema = f"pulsarmlx.f017.v10.runtime.{expected_kind}/1.0.0"
        if (
            type(value) is not dict
            or set(value) != {"schema", "artifact_kind", "payload"}
            or value.get("schema") != expected_schema
            or value.get("artifact_kind") != expected_kind
            or type(value.get("payload")) is not dict
        ):
            return "AUTHORITY_CORRUPT"
        return "OBSERVED_PRESENT"

    def _observe_journal(self) -> tuple[str, dict[str, int], str]:
        starts = {"package": 0, "primary": 0, "secondary": 0}
        descriptor = self._journal_fd
        try:
            observed = os.fstat(descriptor)
            if (
                observed.st_dev != self.journal_identity["device"]
                or observed.st_ino != self.journal_identity["inode"]
                or observed.st_mode != self.journal_identity["mode"]
            ):
                return "IDENTITY_MISMATCH", starts, ZERO_SHA256
            raw = bytearray()
            offset = 0
            while True:
                chunk = os.pread(descriptor, 65_536, offset)
                if not chunk:
                    break
                raw.extend(chunk)
                offset += len(chunk)
                if len(raw) > 4_194_304:
                    return "AUTHORITY_CORRUPT", starts, ZERO_SHA256
        except OSError:
            return "AUTHORITY_UNAVAILABLE", starts, ZERO_SHA256
        previous = ZERO_SHA256
        previous_rank = -1
        lines = bytes(raw).splitlines(keepends=True)
        for sequence, line in enumerate(lines):
            try:
                record = parse_artifact_bytes(line)
            except ArtifactDecodeError:
                return "AUTHORITY_CORRUPT", starts, previous
            expected_keys = {
                "artifact_sha256", "lifecycle_outcome", "package_attempt_id",
                "previous_record_sha256", "sequence", "transition_id",
            }
            if type(record) is not dict or set(record) != expected_keys:
                return "AUTHORITY_CORRUPT", starts, previous
            transition = record.get("transition_id")
            if (
                type(record.get("sequence")) is not int
                or record.get("sequence") != sequence
                or not _is_sha256(record.get("previous_record_sha256"))
                or record.get("previous_record_sha256") != previous
                or not _is_sha256(record.get("artifact_sha256"))
                or record.get("package_attempt_id") != self.package_attempt_id
                or (
                    record.get("lifecycle_outcome") is not None
                    and type(record.get("lifecycle_outcome")) is not str
                )
                or type(transition) is not str
                or transition not in TRANSITION_ORDER
                or TRANSITION_ORDER[transition] < previous_rank
            ):
                return "AUTHORITY_CORRUPT", starts, previous
            previous = hashlib.sha256(line).hexdigest()
            previous_rank = TRANSITION_ORDER[transition]
            role = START_TRANSITIONS.get(transition)
            if role is not None:
                starts[role] = 1
        if len(lines) != self._sequence or previous != self._previous_sha256:
            return "AUTHORITY_CORRUPT", starts, previous
        return "OBSERVED_PRESENT", starts, previous

    def accounting_lower_bound(self) -> dict:
        observations = {
            "package": self.observe_start_artifact("package-durable-start.json", "package_durable_start"),
            "primary": self.observe_start_artifact("primary-durable-start.json", "primary_durable_start"),
            "secondary": self.observe_start_artifact("secondary-durable-start.json", "secondary_durable_start"),
        }
        journal_status, journal_starts, journal_sha = self._observe_journal()
        values: dict[str, int] = {}
        for role, status in observations.items():
            if status == "OBSERVED_PRESENT":
                values[role] = 1
            elif status == "OBSERVED_ABSENT":
                values[role] = max(self._starts[role], journal_starts[role])
            else:
                # Unavailable/corrupt evidence is never evidence of absence.
                values[role] = max(self._starts[role], journal_starts[role])
        if (values["primary"] or values["secondary"]) and not values["package"]:
            values["package"] = 1
        for role in values:
            values[role] = max(values[role], self._monotonic_lower_bound[role])
            self._monotonic_lower_bound[role] = values[role]
        return {
            "authorization": 0,
            **values,
            "historical_before": 175,
            "historical_after": 175,
            "observations": observations,
            "journal_observation": journal_status,
            "path_identity_status": self.path_status(),
            "last_completed_transition_id": self._last_completed,
            "journal_last_record_sha256": journal_sha,
            "fallback_used_as_accounting_source": False,
        }

    def close(self) -> None:
        for descriptor in (self._journal_fd, self.primary_fd, self.fallback_fd):
            if type(descriptor) is int and descriptor >= 0:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        self._journal_fd = -1
        self.primary_fd = -1
        self.fallback_fd = -1

    def __enter__(self) -> "AccountingRootAuthority":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
