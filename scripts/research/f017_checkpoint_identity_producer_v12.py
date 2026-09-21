#!/usr/bin/env python3
"""Generic V12 six-shard identity stage with five retained leases."""
from __future__ import annotations

import errno
import hashlib
import os
from pathlib import Path
import stat
import sys
import tempfile
from contextvars import ContextVar, Token

from f017_accounting_root_continuity_v1 import open_directory_no_symlinks
from f017_bounded_artifact_decode_v1 import parse_artifact_bytes
from f017_canonical_serialization_v10 import bank_exclusive, canonical_bytes
from f017_checkpoint_identity_authority_v12 import (
    MINIMUM_INSTALLED_SCHEMA,
    ValidatedIdentityAuthority,
)
from f017_checkpoint_identity_lifecycle_v12 import (
    IdentityAccessCensus,
    IdentityAuthorityError,
    IdentityDescriptorDisposition,
    IdentityOperationObservation,
    failure,
    with_failure_context,
)
from f017_descriptor_lease_manager_v10 import LeaseRecord, LeaseSet, validate_descriptors
from f017_write_once_artifact_v1 import _bank_exclusive_write_once

ROOT = Path(__file__).resolve().parents[2]
__all__ = (
    "IdentityAccessPrefixValidationError",
    "identity_success_evidence_leaves",
    "missing_identity_access_prefix_census",
    "validate_banked_identity_access_prefix",
    "validate_banked_identity_evidence",
)

_RAW_OS_CLOSE = os.close
_MAXIMUM_ACCESS_RECEIPT_BYTES = 65_536

_ACCESS_PREFIX_RECEIPT_SCHEMA = (
    "pulsarmlx.f017.checkpoint-identity-access-prefix-receipt/12.1.0"
)
_ACCESS_PREFIX_GENESIS_SCHEMA = (
    "pulsarmlx.f017.checkpoint-identity-access-prefix-genesis/12.1.0"
)
_ACCESS_JOURNAL_SCHEMA = (
    "pulsarmlx.f017.checkpoint-identity-access-journal/12.1.0"
)
_SHARD_RECEIPTS_SCHEMA = (
    "pulsarmlx.f017.checkpoint-identity-shard-receipts/12.1.0"
)
_LEASE_MANIFEST_SCHEMA = (
    "pulsarmlx.f017.checkpoint-identity-lease-manifest/12.1.0"
)
_IDENTITY_CORE_SCHEMA = (
    "pulsarmlx.f017.checkpoint-identity-core/12.1.0"
)
_IDENTITY_MANIFEST_SCHEMA = (
    "pulsarmlx.f017.checkpoint-identity-manifest/12.1.0"
)
_IDENTITY_RECEIPT_SCHEMA = (
    "pulsarmlx.f017.checkpoint-identity-receipt/12.1.0"
)
_IDENTITY_TERMINAL_SCHEMA = (
    "pulsarmlx.f017.checkpoint-identity-terminal/12.1.0"
)
_ACCESS_RECEIPT_KEYS = frozenset({
    "schema", "authorization_id", "package_attempt_id",
    "checkpoint_identity_contract_sha256", "checkpoint_set_sha256",
    "sequence", "ordinal", "shard_name", "role", "operation", "phase",
    "predecessor_sha256", "expected_bytes", "observed_bytes",
    "effect_count", "descriptor_identity_sha256", "observed_sha256",
    "disposition", "result",
})
_IDENTITY_BASE_LEAVES = frozenset({
    "access-journal.json", "shard-receipts.json", "lease-manifest.json",
    "identity-core.json", "identity-manifest.json", "identity-receipt.json",
    "identity-terminal.json",
})
_ACCESS_STEPS_PER_SHARD = (
    ("SHARD_OPEN", "INTENT"),
    ("SHARD_OPEN", "COMPLETE"),
    ("IDENTITY_HASH_READ", "INTENT"),
    ("IDENTITY_HASH_READ", "COMPLETE"),
)


class IdentityAccessPrefixValidationError(ValueError):
    """A damaged prefix with the maximal independently validated census."""

    def __init__(self, detail: str, access_census: dict[str, object]) -> None:
        if type(detail) is not str or not detail:
            raise ValueError("identity access validation detail")
        if type(access_census) is not dict:
            raise TypeError("identity access validation census")
        super().__init__(detail)
        self.detail = detail
        self.access_census = dict(access_census)


def identity_success_evidence_leaves() -> tuple[str, ...]:
    """Return the exact source-derived V12.1 successful identity inventory."""
    prefix = {
        f"access-prefix-{sequence:02d}.json" for sequence in range(1, 25)
    }
    return tuple(sorted(set(_IDENTITY_BASE_LEAVES) | prefix))

_QUALIFICATION_ROOT_DESCRIPTOR: ContextVar[int | None] = ContextVar(
    "f017_sequence41_qualification_checkpoint_root_descriptor", default=None
)
_QUALIFICATION_ROOT_DESCRIPTOR_SEAL = object()


def _bind_qualification_root_descriptor(seal: object, descriptor: int) -> Token:
    """Carry one sealed graph-owned root descriptor into the private producer."""
    if seal is not _QUALIFICATION_ROOT_DESCRIPTOR_SEAL or type(descriptor) is not int:
        raise TypeError("sealed qualification checkpoint root descriptor")
    observed = os.fstat(descriptor)
    if not stat.S_ISDIR(observed.st_mode) or observed.st_uid != os.getuid():
        raise ValueError("qualification checkpoint root descriptor identity")
    if _QUALIFICATION_ROOT_DESCRIPTOR.get() is not None:
        raise RuntimeError("qualification checkpoint root descriptor already bound")
    return _QUALIFICATION_ROOT_DESCRIPTOR.set(descriptor)


def _reset_qualification_root_descriptor(seal: object, token: Token) -> None:
    if seal is not _QUALIFICATION_ROOT_DESCRIPTOR_SEAL or type(token) is not Token:
        raise TypeError("sealed qualification checkpoint root descriptor token")
    _QUALIFICATION_ROOT_DESCRIPTOR.reset(token)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _runtime_revalidate(authority: ValidatedIdentityAuthority, package_attempt_id: str) -> tuple[dict, dict]:
    if type(authority) is not ValidatedIdentityAuthority or authority.posture != "INSTALLED":
        raise failure("F017_V12_IDENTITY_RUNTIME_AUTHORITY_DRIFT", "immutable installed authority required")
    value = authority.as_dict()
    if value["package_attempt_id"] != package_attempt_id:
        raise failure("F017_V12_IDENTITY_PACKAGE_ATTEMPT_MISMATCH", "package attempt identity")
    bindings = (
        (
            "checkpoint_identity_contract_path",
            "checkpoint_identity_contract_sha256",
        ),
        ("measured_producer_path", "measured_producer_sha256"),
        ("measured_validator_path", "measured_validator_sha256"),
    ) if value["schema"] == MINIMUM_INSTALLED_SCHEMA else (
        ("checkpoint_identity_contract_path", "checkpoint_identity_contract_sha256"),
        ("producer_capability_path", "producer_capability_sha256"),
        ("measured_producer_path", "measured_producer_sha256"),
        ("primary_candidate_validator_path", "primary_candidate_validator_sha256"),
        ("secondary_candidate_validator_path", "secondary_candidate_validator_sha256"),
        ("identity_candidate_validator_path", "identity_candidate_validator_sha256"),
    )
    for path_key, digest_key in bindings:
        path = ROOT / value[path_key]
        if not path.is_file() or path.is_symlink() or _sha(path) != value[digest_key]:
            outcome = ("F017_V12_IDENTITY_CONTRACT_DRIFT" if path_key == "checkpoint_identity_contract_path"
                       else "F017_V12_IDENTITY_RUNTIME_AUTHORITY_DRIFT")
            raise failure(outcome, path_key)
    contract = parse_artifact_bytes((ROOT / value["checkpoint_identity_contract_path"]).read_bytes())
    return value, contract


def _hash_descriptor(descriptor: int, expected_size: int, *, require_single_link: bool) -> tuple[str, os.stat_result]:
    try:
        before = os.fstat(descriptor)
    except OSError as exc:
        raise failure(
            "F017_V12_IDENTITY_DESCRIPTOR_CHANGED",
            "descriptor pre-hash identity",
            checkpoint_access="RECEIPT_DERIVED",
            operation_observation=IdentityOperationObservation(
                0,
                0,
                hashlib.sha256(b"").hexdigest(),
                "DESCRIPTOR_STAT_FAILURE",
            ),
        ) from exc
    if not stat.S_ISREG(before.st_mode):
        raise failure(
            "F017_V12_IDENTITY_DESCRIPTOR_CHANGED",
            "shard is not regular",
            checkpoint_access="RECEIPT_DERIVED",
            operation_observation=IdentityOperationObservation(
                0, 0, hashlib.sha256(b"").hexdigest(), "DESCRIPTOR_NOT_REGULAR"
            ),
        )
    if before.st_size != expected_size:
        raise failure(
            "F017_V12_IDENTITY_SHARD_SIZE_MISMATCH",
            "shard size",
            checkpoint_access="RECEIPT_DERIVED",
            operation_observation=IdentityOperationObservation(
                0, 0, hashlib.sha256(b"").hexdigest(), "SIZE_MISMATCH"
            ),
        )
    if require_single_link and before.st_nlink != 1:
        raise failure(
            "F017_V12_IDENTITY_DESCRIPTOR_CHANGED",
            "synthetic hard link",
            checkpoint_access="RECEIPT_DERIVED",
            operation_observation=IdentityOperationObservation(
                0, 0, hashlib.sha256(b"").hexdigest(), "LINK_IDENTITY_MISMATCH"
            ),
        )
    digest = hashlib.sha256()
    offset = 0
    try:
        while offset < expected_size:
            block = os.pread(descriptor, min(1024 * 1024, expected_size - offset), offset)
            if not block:
                raise failure(
                    "F017_V12_IDENTITY_SHARD_READ_FAILURE",
                    "short descriptor read",
                    checkpoint_access="RECEIPT_DERIVED",
                    operation_observation=IdentityOperationObservation(
                        0, offset, digest.hexdigest(), "SHORT_READ"
                    ),
                )
            digest.update(block)
            offset += len(block)
    except OSError as exc:
        raise failure(
            "F017_V12_IDENTITY_SHARD_READ_FAILURE",
            type(exc).__name__,
            checkpoint_access="RECEIPT_DERIVED",
            operation_observation=IdentityOperationObservation(
                0, offset, digest.hexdigest(), "READ_FAILURE"
            ),
        ) from exc
    try:
        after = os.fstat(descriptor)
    except OSError as exc:
        raise failure(
            "F017_V12_IDENTITY_DESCRIPTOR_CHANGED",
            "descriptor post-hash identity",
            checkpoint_access="RECEIPT_DERIVED",
            operation_observation=IdentityOperationObservation(
                1,
                offset,
                digest.hexdigest(),
                "DESCRIPTOR_REVALIDATION_FAILURE",
            ),
        ) from exc
    identity = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
    if identity(before) != identity(after):
        raise failure(
            "F017_V12_IDENTITY_DESCRIPTOR_CHANGED",
            "descriptor identity changed",
            checkpoint_access="RECEIPT_DERIVED",
            operation_observation=IdentityOperationObservation(
                1, offset, digest.hexdigest(), "DESCRIPTOR_CHANGED"
            ),
        )
    return digest.hexdigest(), after


def _required_shard_names(contract: dict) -> tuple[str, ...]:
    """Derive the exact ordered shard-name authority from one selected contract."""
    shards = contract.get("shards")
    if type(shards) is not list or len(shards) != 6:
        raise failure(
            "F017_V12_IDENTITY_CONTRACT_DRIFT",
            "required shard name census",
        )
    if [item.get("ordinal") if type(item) is dict else None for item in shards] != list(
        range(1, 7)
    ):
        raise failure(
            "F017_V12_IDENTITY_CONTRACT_DRIFT",
            "required shard order",
        )
    names: list[str] = []
    for shard in shards:
        name = shard.get("filename") if type(shard) is dict else None
        if (
            type(name) is not str
            or not name
            or name in {".", ".."}
            or os.path.basename(name) != name
        ):
            raise failure(
                "F017_V12_IDENTITY_CONTRACT_DRIFT",
                "unsafe required shard basename",
            )
        names.append(name)
    if len(set(names)) != len(names):
        raise failure(
            "F017_V12_IDENTITY_CONTRACT_DRIFT",
            "duplicate required shard basename",
        )
    return tuple(names)


def _require_checkpoint_root_membership(
    root_fd: int, required_names: tuple[str, ...]
) -> None:
    """Require every exact contract name while ignoring unrelated root leaves."""
    try:
        observed_names = os.listdir(root_fd)
    except OSError as exc:
        raise failure(
            "F017_V12_IDENTITY_SHARD_OPEN_FAILURE",
            "checkpoint root leaf census",
            checkpoint_access=0,
        ) from exc
    missing = set(required_names).difference(observed_names)
    if missing:
        present_required = len(required_names) - len(missing)
        raise failure(
            "F017_V12_IDENTITY_SHARD_OPEN_FAILURE",
            (
                "checkpoint root leaf census: "
                f"required={len(required_names)} "
                f"present={present_required} missing={len(missing)}"
            ),
            checkpoint_access=0,
        )


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _access_prefix_plan(contract: dict) -> tuple[dict[str, object], ...]:
    names = _required_shard_names(contract)
    shards = contract.get("shards")
    if type(shards) is not list or len(shards) != len(names):
        raise failure("F017_V12_IDENTITY_CONTRACT_DRIFT", "access receipt plan")
    plan: list[dict[str, object]] = []
    sequence = 0
    for shard, name in zip(shards, names, strict=True):
        for operation, phase in _ACCESS_STEPS_PER_SHARD:
            sequence += 1
            plan.append({
                "leaf": f"access-prefix-{sequence:02d}.json",
                "sequence": sequence,
                "ordinal": shard["ordinal"],
                "shard_name": name,
                "role": shard["role"],
                "operation": operation,
                "phase": phase,
                "expected_bytes": shard["size_bytes"],
                "expected_sha256": shard["sha256"],
            })
    return tuple(plan)


def _access_prefix_genesis(
    authority: ValidatedIdentityAuthority, contract: dict
) -> str:
    return _canonical_sha256({
        "schema": _ACCESS_PREFIX_GENESIS_SCHEMA,
        "authorization_id": authority.get("authorization_id"),
        "package_attempt_id": authority.get("package_attempt_id"),
        "checkpoint_identity_contract_sha256": authority.get(
            "checkpoint_identity_contract_sha256"
        ),
        "checkpoint_set_sha256": contract.get("checkpoint_set_sha256"),
    })


def _descriptor_identity_sha256(observed: os.stat_result) -> str:
    return _canonical_sha256({
        "device": observed.st_dev,
        "inode": observed.st_ino,
        "mode": observed.st_mode,
        "size": observed.st_size,
        "mtime_ns": observed.st_mtime_ns,
        "ctime_ns": observed.st_ctime_ns,
    })


def _retire_descriptor(descriptor: int) -> tuple[bool, OSError | None]:
    """Close normally, using the captured primitive only to prevent a leak."""
    try:
        os.close(descriptor)
        return True, None
    except OSError as first_error:
        try:
            os.fstat(descriptor)
        except OSError as status_error:
            if status_error.errno == errno.EBADF:
                return True, first_error
        try:
            _RAW_OS_CLOSE(descriptor)
        except OSError:
            try:
                os.fstat(descriptor)
            except OSError as status_error:
                if status_error.errno == errno.EBADF:
                    return True, first_error
            return False, first_error
        return True, first_error


class _AccessPrefixWriter:
    """Bank one canonical predecessor-linked access receipt at a time."""

    __slots__ = (
        "directory", "authority", "contract", "plan", "bank_control",
        "head_sha256", "receipt_count",
    )

    def __init__(
        self,
        directory: Path,
        authority: ValidatedIdentityAuthority,
        contract: dict,
        *,
        write_once: bool,
    ) -> None:
        if type(write_once) is not bool:
            raise TypeError("identity access write-once policy")
        self.directory = directory
        self.authority = authority
        self.contract = contract
        self.plan = _access_prefix_plan(contract)
        self.bank_control = (
            _bank_exclusive_write_once if write_once else bank_exclusive
        )
        self.head_sha256 = _access_prefix_genesis(authority, contract)
        self.receipt_count = 0
        directory.mkdir(parents=True, exist_ok=False)

    def bank(
        self,
        *,
        operation: str,
        phase: str,
        effect_count: int,
        observed_bytes: int,
        descriptor_identity_sha256: str | None,
        observed_sha256: str | None,
        disposition: str,
        result: str,
    ) -> str:
        if self.receipt_count >= len(self.plan):
            raise ValueError("identity access receipt excess")
        expected = self.plan[self.receipt_count]
        if operation != expected["operation"] or phase != expected["phase"]:
            raise ValueError("identity access receipt order")
        value = {
            "schema": _ACCESS_PREFIX_RECEIPT_SCHEMA,
            "authorization_id": self.authority.get("authorization_id"),
            "package_attempt_id": self.authority.get("package_attempt_id"),
            "checkpoint_identity_contract_sha256": self.authority.get(
                "checkpoint_identity_contract_sha256"
            ),
            "checkpoint_set_sha256": self.contract["checkpoint_set_sha256"],
            "sequence": expected["sequence"],
            "ordinal": expected["ordinal"],
            "shard_name": expected["shard_name"],
            "role": expected["role"],
            "operation": operation,
            "phase": phase,
            "predecessor_sha256": self.head_sha256,
            "expected_bytes": expected["expected_bytes"],
            "observed_bytes": observed_bytes,
            "effect_count": effect_count,
            "descriptor_identity_sha256": descriptor_identity_sha256,
            "observed_sha256": observed_sha256,
            "disposition": disposition,
            "result": result,
        }
        digest = self.bank_control(self.directory / str(expected["leaf"]), value)
        if digest != _canonical_sha256(value):
            raise ValueError("identity access receipt digest")
        self.head_sha256 = digest
        self.receipt_count += 1
        return digest


def _conservative_access_validation_census(
    *,
    contract: dict,
    genesis_sha256: str,
    head_sha256: str,
    receipt_count: int,
    opened: int,
    hashed: int,
    observed_hash_bytes: int,
    next_operation: str | None,
    next_ordinal: int,
) -> dict[str, object]:
    """Retain a validated lower bound and conservatively bound its suffix."""
    shard_count = len(contract["shards"])
    expected_bytes = sum(int(item["size_bytes"]) for item in contract["shards"])
    return {
        "schema": "pulsarmlx.f017.checkpoint-identity-access-census/12.1.0",
        "genesis_sha256": genesis_sha256,
        "head_sha256": head_sha256,
        "receipt_count": receipt_count,
        "checkpoint_shard_opens_lower_bound": opened,
        "checkpoint_shard_opens_upper_bound": shard_count,
        "checkpoint_shard_opens_unconfirmed": shard_count - opened,
        "checkpoint_identity_hash_reads_lower_bound": hashed,
        "checkpoint_identity_hash_reads_upper_bound": shard_count,
        "checkpoint_identity_hash_reads_unconfirmed": shard_count - hashed,
        "identity_hash_bytes_lower_bound": observed_hash_bytes,
        "identity_hash_bytes_upper_bound": expected_bytes,
        "identity_hash_bytes_unconfirmed": expected_bytes - observed_hash_bytes,
        "exact": (
            opened == shard_count
            and hashed == shard_count
            and observed_hash_bytes == expected_bytes
        ),
        "unresolved_operation": next_operation,
        "unresolved_ordinal": next_ordinal,
        "prefix_complete": receipt_count == shard_count * 4,
        "result": "FAIL",
    }


def missing_identity_access_prefix_census(
    expected_bindings: dict,
    contract: dict,
) -> dict[str, object]:
    """Return conservative restart bounds for an absent identity directory."""
    required = {
        "authorization_id", "package_attempt_id",
        "checkpoint_identity_contract_sha256", "checkpoint_set_sha256",
    }
    if type(expected_bindings) is not dict or not required.issubset(
        expected_bindings
    ):
        raise ValueError("identity access expected bindings")
    if (
        type(contract) is not dict
        or contract.get("checkpoint_set_sha256")
        != expected_bindings["checkpoint_set_sha256"]
    ):
        raise ValueError("identity access checkpoint-set binding")
    authority = {key: expected_bindings[key] for key in required}
    plan = _access_prefix_plan(contract)
    genesis = _access_prefix_genesis(authority, contract)
    return _conservative_access_validation_census(
        contract=contract,
        genesis_sha256=genesis,
        head_sha256=genesis,
        receipt_count=0,
        opened=0,
        hashed=0,
        observed_hash_bytes=0,
        next_operation=str(plan[0]["operation"]),
        next_ordinal=int(plan[0]["ordinal"]),
    )


def _open_access_evidence_directory(directory: Path) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    descriptor = os.open(directory, flags)
    observed = os.fstat(descriptor)
    if not stat.S_ISDIR(observed.st_mode) or observed.st_uid != os.getuid():
        _RAW_OS_CLOSE(descriptor)
        raise ValueError("identity access evidence directory identity")
    return descriptor


def _read_evidence_leaf_from_directory_descriptor(
    directory_descriptor: int,
    leaf: str,
    *,
    maximum_bytes: int = _MAXIMUM_ACCESS_RECEIPT_BYTES,
    require_immutable: bool = False,
) -> bytes:
    """Read one sealed evidence leaf through one already-held directory."""
    if (
        type(directory_descriptor) is not int
        or type(leaf) is not str
        or not leaf
        or "/" in leaf
        or leaf in {".", ".."}
        or type(maximum_bytes) is not int
        or maximum_bytes <= 0
        or type(require_immutable) is not bool
    ):
        raise ValueError("identity evidence leaf read authority")
    receipt_descriptor = -1
    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
        receipt_descriptor = os.open(leaf, flags, dir_fd=directory_descriptor)
        before = os.fstat(receipt_descriptor)
        path_before = os.stat(
            leaf, dir_fd=directory_descriptor, follow_symlinks=False
        )
        identity = (before.st_dev, before.st_ino)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600
            or (path_before.st_dev, path_before.st_ino) != identity
            or before.st_size <= 0
            or before.st_size > maximum_bytes
        ):
            raise ValueError("identity evidence leaf descriptor identity")
        if require_immutable and sys.platform == "darwin" and (
            not (before.st_flags & stat.UF_IMMUTABLE)
        ):
            raise ValueError("identity evidence leaf immutability")

        remaining = before.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(receipt_descriptor, min(remaining, 65_536))
            if not chunk:
                raise ValueError("identity evidence leaf short read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(receipt_descriptor, 1):
            raise ValueError("identity evidence leaf excess bytes")

        after = os.fstat(receipt_descriptor)
        path_after = os.stat(
            leaf, dir_fd=directory_descriptor, follow_symlinks=False
        )
        if (
            (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_uid,
                after.st_nlink,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
                after.st_flags,
            )
            != (
                before.st_dev,
                before.st_ino,
                before.st_mode,
                before.st_uid,
                before.st_nlink,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
                before.st_flags,
            )
            or (path_after.st_dev, path_after.st_ino) != identity
        ):
            raise ValueError("identity evidence leaf identity changed")
        return b"".join(chunks)
    finally:
        if receipt_descriptor >= 0:
            _RAW_OS_CLOSE(receipt_descriptor)
def _validate_banked_identity_access_prefix_from_directory_descriptor(
    directory_descriptor: int,
    authority: ValidatedIdentityAuthority | dict,
    contract: dict,
    *,
    require_complete: bool = False,
) -> IdentityAccessCensus:
    """Validate one access prefix through a single held directory identity."""
    if type(require_complete) is not bool:
        raise TypeError("identity access completion policy")
    if type(directory_descriptor) is not int:
        raise TypeError("identity access evidence directory descriptor")
    plan = _access_prefix_plan(contract)
    expected_names = tuple(str(item["leaf"]) for item in plan)
    genesis = _access_prefix_genesis(authority, contract)
    predecessor = genesis
    opened = 0
    hashed = 0
    observed_hash_bytes = 0
    validated_count = 0
    open_identity_by_ordinal: dict[int, str] = {}
    final_receipt: dict[str, object] | None = None
    require_immutable = authority.get("schema") == MINIMUM_INSTALLED_SCHEMA

    def invalid(detail: str) -> Never:
        next_item = plan[validated_count] if validated_count < len(plan) else None
        raise IdentityAccessPrefixValidationError(
            detail,
            _conservative_access_validation_census(
                contract=contract,
                genesis_sha256=genesis,
                head_sha256=predecessor,
                receipt_count=validated_count,
                opened=opened,
                hashed=hashed,
                observed_hash_bytes=observed_hash_bytes,
                next_operation=(
                    str(next_item["operation"]) if next_item is not None else None
                ),
                next_ordinal=(
                    int(next_item["ordinal"]) if next_item is not None else 0
                ),
            ),
        )

    try:
        observed_names = set(os.listdir(directory_descriptor))
    except BaseException as exc:
        invalid(f"identity access evidence directory: {type(exc).__name__}")
    unknown = observed_names.difference(set(expected_names) | _IDENTITY_BASE_LEAVES)
    present = [name in observed_names for name in expected_names]
    count = 0
    while count < len(present) and present[count]:
        count += 1
    gap = any(present[count:])

    for index in range(count):
        expected = plan[index]
        try:
            raw = _read_evidence_leaf_from_directory_descriptor(
                directory_descriptor,
                str(expected["leaf"]),
                require_immutable=require_immutable,
            )
            receipt = parse_artifact_bytes(raw)
        except BaseException as exc:
            invalid(f"identity access receipt read: {type(exc).__name__}")
        if (
            type(receipt) is not dict
            or set(receipt) != _ACCESS_RECEIPT_KEYS
            or canonical_bytes(receipt) != raw
        ):
            invalid("identity access receipt bytes")
        continuity = {
            "schema": _ACCESS_PREFIX_RECEIPT_SCHEMA,
            "authorization_id": authority.get("authorization_id"),
            "package_attempt_id": authority.get("package_attempt_id"),
            "checkpoint_identity_contract_sha256": authority.get(
                "checkpoint_identity_contract_sha256"
            ),
            "checkpoint_set_sha256": contract.get("checkpoint_set_sha256"),
            "sequence": expected["sequence"],
            "ordinal": expected["ordinal"],
            "shard_name": expected["shard_name"],
            "role": expected["role"],
            "operation": expected["operation"],
            "phase": expected["phase"],
            "predecessor_sha256": predecessor,
            "expected_bytes": expected["expected_bytes"],
        }
        if any(receipt[key] != value for key, value in continuity.items()):
            invalid("identity access receipt continuity")
        if (
            type(receipt["observed_bytes"]) is not int
            or receipt["observed_bytes"] < 0
            or type(receipt["effect_count"]) is not int
            or receipt["effect_count"] not in {0, 1}
        ):
            invalid("identity access receipt counts")
        descriptor_sha = receipt["descriptor_identity_sha256"]
        observed_sha = receipt["observed_sha256"]
        for digest, label in (
            (descriptor_sha, "descriptor identity"),
            (observed_sha, "observed hash"),
        ):
            if digest is not None and (
                type(digest) is not str
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                invalid(f"identity access {label}")

        operation = str(expected["operation"])
        phase = str(expected["phase"])
        ordinal = int(expected["ordinal"])
        if phase == "INTENT":
            if (
                receipt["effect_count"] != 0
                or receipt["observed_bytes"] != 0
                or observed_sha is not None
                or receipt["disposition"] != f"{operation}_INTENT"
                or receipt["result"] != "PENDING"
                or (
                    operation == "SHARD_OPEN"
                    and descriptor_sha is not None
                )
                or (
                    operation == "IDENTITY_HASH_READ"
                    and descriptor_sha != open_identity_by_ordinal.get(ordinal)
                )
            ):
                invalid("identity access intent semantics")
        elif operation == "SHARD_OPEN":
            if receipt["observed_bytes"] != 0 or observed_sha is not None:
                invalid("identity open completion bytes")
            if receipt["effect_count"] == 1:
                if (
                    (
                        descriptor_sha is not None
                        and receipt["disposition"] == "SHARD_OPEN_COMPLETE"
                        and receipt["result"] == "PASS"
                    )
                    is not True
                ):
                    if not (
                        descriptor_sha is None
                        and receipt["disposition"]
                        == "SHARD_OPEN_IDENTITY_FAILURE"
                        and receipt["result"] == "FAIL"
                    ):
                        invalid("identity open completion semantics")
                opened += 1
                if descriptor_sha is not None:
                    open_identity_by_ordinal[ordinal] = str(descriptor_sha)
            elif (
                descriptor_sha is not None
                or receipt["disposition"] != "SHARD_OPEN_FAILURE"
                or receipt["result"] != "FAIL"
            ):
                invalid("identity open failure semantics")
        else:
            if descriptor_sha != open_identity_by_ordinal.get(ordinal):
                invalid("identity hash descriptor continuity")
            if observed_sha is None or receipt["observed_bytes"] > expected["expected_bytes"]:
                invalid("identity hash completion observation")
            if receipt["effect_count"] == 1:
                if receipt["observed_bytes"] != expected["expected_bytes"]:
                    invalid("identity completed hash byte count")
                hashed += 1
                if receipt["disposition"] == "IDENTITY_HASH_COMPLETE":
                    if (
                        observed_sha != expected["expected_sha256"]
                        or receipt["result"] != "PASS"
                    ):
                        invalid("identity hash completion semantics")
                elif (
                    receipt["disposition"] not in {
                        "IDENTITY_HASH_MISMATCH", "DESCRIPTOR_CHANGED",
                        "DESCRIPTOR_REVALIDATION_FAILURE",
                    }
                    or receipt["result"] != "FAIL"
                ):
                    invalid("identity completed hash failure semantics")
            elif (
                receipt["disposition"] not in {
                    "DESCRIPTOR_NOT_REGULAR", "SIZE_MISMATCH",
                    "LINK_IDENTITY_MISMATCH", "SHORT_READ", "READ_FAILURE",
                    "DESCRIPTOR_STAT_FAILURE",
                }
                or receipt["result"] != "FAIL"
            ):
                invalid("identity incomplete hash semantics")
            observed_hash_bytes += int(receipt["observed_bytes"])
        predecessor = hashlib.sha256(raw).hexdigest()
        final_receipt = receipt
        validated_count += 1
        if receipt["result"] == "FAIL" and index != count - 1:
            invalid("identity access after failed completion")

    if gap:
        invalid("identity access receipt gap")
    if unknown:
        invalid("identity access evidence leaf census")

    unresolved_operation: str | None = None
    unresolved_ordinal = 0
    open_unconfirmed = 0
    hash_unconfirmed = 0
    byte_unconfirmed = 0
    if final_receipt is not None and final_receipt["phase"] == "INTENT":
        unresolved_operation = str(final_receipt["operation"])
        unresolved_ordinal = int(final_receipt["ordinal"])
        if unresolved_operation == "SHARD_OPEN":
            open_unconfirmed = 1
        else:
            hash_unconfirmed = 1
            byte_unconfirmed = int(final_receipt["expected_bytes"])
    prefix_complete = validated_count == len(plan)
    if require_complete and (
        not prefix_complete
        or final_receipt is None
        or final_receipt["result"] != "PASS"
    ):
        invalid("complete identity access prefix required")
    return IdentityAccessCensus(
        genesis,
        predecessor,
        validated_count,
        opened,
        opened + open_unconfirmed,
        open_unconfirmed,
        hashed,
        hashed + hash_unconfirmed,
        hash_unconfirmed,
        observed_hash_bytes,
        observed_hash_bytes + byte_unconfirmed,
        byte_unconfirmed,
        unresolved_operation is None,
        unresolved_operation,
        unresolved_ordinal,
        prefix_complete,
    )


def _validate_banked_identity_access_prefix(
    directory: Path,
    authority: ValidatedIdentityAuthority | dict,
    contract: dict,
    *,
    require_complete: bool = False,
) -> IdentityAccessCensus:
    """Validate a prefix while continuously holding its exact directory."""
    if type(require_complete) is not bool:
        raise TypeError("identity access completion policy")
    plan = _access_prefix_plan(contract)
    genesis = _access_prefix_genesis(authority, contract)
    empty_census = _conservative_access_validation_census(
        contract=contract,
        genesis_sha256=genesis,
        head_sha256=genesis,
        receipt_count=0,
        opened=0,
        hashed=0,
        observed_hash_bytes=0,
        next_operation=str(plan[0]["operation"]),
        next_ordinal=int(plan[0]["ordinal"]),
    )
    directory_descriptor = -1
    validated: IdentityAccessCensus | None = None
    try:
        directory_descriptor = _open_access_evidence_directory(directory)
        before = os.fstat(directory_descriptor)
        path_before = os.stat(directory, follow_symlinks=False)
        identity = (before.st_dev, before.st_ino)
        if (
            not stat.S_ISDIR(before.st_mode)
            or before.st_uid != os.getuid()
            or not stat.S_ISDIR(path_before.st_mode)
            or (path_before.st_dev, path_before.st_ino) != identity
        ):
            raise ValueError("identity access evidence directory binding")
        validated = _validate_banked_identity_access_prefix_from_directory_descriptor(
            directory_descriptor,
            authority,
            contract,
            require_complete=require_complete,
        )
        after = os.fstat(directory_descriptor)
        path_after = os.stat(directory, follow_symlinks=False)
        if (
            (
                before.st_dev,
                before.st_ino,
                before.st_mode,
                before.st_uid,
                before.st_nlink,
                before.st_mtime_ns,
                before.st_ctime_ns,
                before.st_flags,
            )
            != (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_uid,
                after.st_nlink,
                after.st_mtime_ns,
                after.st_ctime_ns,
                after.st_flags,
            )
            or not stat.S_ISDIR(path_after.st_mode)
            or (path_after.st_dev, path_after.st_ino) != identity
        ):
            raise ValueError("identity access evidence directory changed")
        return validated
    except IdentityAccessPrefixValidationError:
        raise
    except BaseException as exc:
        census = (
            dict(validated.evidence) if validated is not None else empty_census
        )
        census["result"] = "FAIL"
        raise IdentityAccessPrefixValidationError(
            f"identity access evidence directory: {type(exc).__name__}",
            census,
        ) from exc
    finally:
        if directory_descriptor >= 0:
            _RAW_OS_CLOSE(directory_descriptor)


def validate_banked_identity_access_prefix(
    directory: Path,
    expected_bindings: dict,
    contract: dict,
    *,
    require_complete: bool = False,
) -> dict:
    """Validate a prefix from plain, already-authoritative closeout bindings.

    This reader has no checkpoint-opening capability.  The caller supplies the
    exact installed-document fields and already decoded checkpoint contract;
    only the four receipt-binding fields are consumed.
    """
    required = {
        "authorization_id", "package_attempt_id",
        "checkpoint_identity_contract_sha256", "checkpoint_set_sha256",
    }
    if type(expected_bindings) is not dict or not required.issubset(
        expected_bindings
    ):
        raise ValueError("identity access expected bindings")
    if (
        type(contract) is not dict
        or contract.get("checkpoint_set_sha256")
        != expected_bindings["checkpoint_set_sha256"]
    ):
        raise ValueError("identity access checkpoint-set binding")
    authority = {key: expected_bindings[key] for key in required}
    return _validate_banked_identity_access_prefix(
        directory,
        authority,
        contract,
        require_complete=require_complete,
    ).evidence


def _bank_identity_evidence(directory: Path, authority: ValidatedIdentityAuthority,
                            contract: dict, leases: LeaseSet, report: dict,
                            *, access_census: IdentityAccessCensus,
                            _write_once: bool = False) -> dict:
    if type(_write_once) is not bool:
        raise TypeError("identity evidence write-once policy")
    if type(access_census) is not IdentityAccessCensus or (
        not access_census.prefix_complete
        or not access_census.exact
        or access_census.checkpoint_shard_opens_lower_bound != 6
        or access_census.checkpoint_identity_hash_reads_lower_bound != 6
    ):
        raise ValueError("complete receipt-derived identity access census")
    bank_control = _bank_exclusive_write_once if _write_once else bank_exclusive
    access_journal = {
        "schema":_ACCESS_JOURNAL_SCHEMA,
        "authorization_id":authority.get("authorization_id"),
        "package_attempt_id":authority.get("package_attempt_id"),
        "checkpoint_identity_contract_sha256":authority.get(
            "checkpoint_identity_contract_sha256"
        ),
        "checkpoint_set_sha256":contract["checkpoint_set_sha256"],
        "entries":[{"ordinal":item["ordinal"],"shard_name":item["filename"],"role":item["role"],"bytes":item["size_bytes"],"sha256":digest}
                   for item, digest in zip(contract["shards"], report["ordered_shard_digests"], strict=True)],
        "access_prefix_genesis_sha256":access_census.genesis_sha256,
        "access_prefix_head_sha256":access_census.head_sha256,
        "access_prefix_receipt_count":access_census.receipt_count,
        "access_census":access_census.evidence,
        "checkpoint_shard_opens":6,"checkpoint_identity_hash_reads":6,"result":"PASS",
    }
    journal_sha = bank_control(directory / "access-journal.json", access_journal)
    receipts = {
        "schema":_SHARD_RECEIPTS_SCHEMA,
        "package_attempt_id":authority.get("package_attempt_id"),
        "access_prefix_head_sha256":access_census.head_sha256,
        "access_prefix_receipt_count":access_census.receipt_count,
        "receipts":access_journal["entries"],"result":"PASS",
    }
    receipts_sha = bank_control(directory / "shard-receipts.json", receipts)
    lease_manifest = {
        "schema":_LEASE_MANIFEST_SCHEMA,
        "package_attempt_id":authority.get("package_attempt_id"),
        "identity_only_retained_count":0,"retained_lease_count":5,
        "descriptors":leases.descriptors,"result":"PASS",
    }
    lease_sha = bank_control(directory / "lease-manifest.json", lease_manifest)
    deterministic_core = {
        "schema":_IDENTITY_CORE_SCHEMA,
        "authority_scope":authority.get("authority_scope"),
        "operation_class":authority.get("operation_class"),
        "checkpoint_set_sha256":authority.get("checkpoint_set_sha256"),
        "ordered_shard_digests":report["ordered_shard_digests"],
        "shard_roles":[item["role"] for item in contract["shards"]],
        "shard_sizes":[item["size_bytes"] for item in contract["shards"]],
        "identity_only_retained_count":0,"retained_lease_count":5,
        "access_prefix_head_sha256":access_census.head_sha256,
        "access_prefix_receipt_count":access_census.receipt_count,
    }
    core_sha = bank_control(directory / "identity-core.json", deterministic_core)
    manifest = {
        "schema":_IDENTITY_MANIFEST_SCHEMA,
        "authorization_id":authority.get("authorization_id"),
        "package_attempt_id":authority.get("package_attempt_id"),
        "access_journal_sha256":journal_sha,"shard_receipts_sha256":receipts_sha,
        "lease_manifest_sha256":lease_sha,"deterministic_core_sha256":core_sha,
        "access_prefix_genesis_sha256":access_census.genesis_sha256,
        "access_prefix_head_sha256":access_census.head_sha256,
        "access_prefix_receipt_count":access_census.receipt_count,
        "result":"PASS",
    }
    manifest_sha = bank_control(directory / "identity-manifest.json", manifest)
    receipt = {
        "schema":_IDENTITY_RECEIPT_SCHEMA,
        "authorization_id":authority.get("authorization_id"),
        "package_attempt_id":authority.get("package_attempt_id"),
        "identity_manifest_sha256":manifest_sha,
        "access_prefix_head_sha256":access_census.head_sha256,
        "result":"PASS",
    }
    receipt_sha = bank_control(directory / "identity-receipt.json", receipt)
    terminal = {
        "schema":_IDENTITY_TERMINAL_SCHEMA,
        "package_attempt_id":authority.get("package_attempt_id"),
        "identity_receipt_sha256":receipt_sha,
        "access_prefix_head_sha256":access_census.head_sha256,
        "state":"COMPLETE","result":"PASS",
    }
    terminal_sha = bank_control(directory / "identity-terminal.json", terminal)
    result = {"access_journal_sha256":journal_sha,"shard_receipts_sha256":receipts_sha,
            "lease_manifest_sha256":lease_sha,"deterministic_core_sha256":core_sha,
            "identity_manifest_sha256":manifest_sha,"identity_receipt_sha256":receipt_sha,
            "identity_terminal_sha256":terminal_sha,"identity_terminal_state":"COMPLETE",
            "access_prefix_genesis_sha256":access_census.genesis_sha256,
            "access_prefix_head_sha256":access_census.head_sha256,
            "access_prefix_receipt_count":access_census.receipt_count}
    validate_banked_identity_evidence(directory, report, authority=authority, contract=contract)
    return result


def validate_banked_identity_evidence(
    directory: Path,
    report: dict | None = None,
    *,
    authority: ValidatedIdentityAuthority | None = None,
    contract: dict | None = None,
) -> dict:
    """Validate the complete bounded identity-evidence closure from committed bytes."""
    access_names = {
        f"access-prefix-{sequence:02d}.json" for sequence in range(1, 25)
    }
    names = set(_IDENTITY_BASE_LEAVES) | access_names
    directory_descriptor = _open_access_evidence_directory(directory)
    require_immutable = (
        authority is not None
        and authority.get("schema") == MINIMUM_INSTALLED_SCHEMA
    )
    try:
        directory_before = os.fstat(directory_descriptor)
        path_before = os.stat(directory, follow_symlinks=False)
        directory_identity = (directory_before.st_dev, directory_before.st_ino)
        if (
            not stat.S_ISDIR(path_before.st_mode)
            or (path_before.st_dev, path_before.st_ino) != directory_identity
            or set(os.listdir(directory_descriptor)) != names
        ):
            raise ValueError("identity evidence leaf census")

        def load(name: str) -> tuple[dict, str]:
            raw = _read_evidence_leaf_from_directory_descriptor(
                directory_descriptor,
                name,
                require_immutable=require_immutable,
            )
            value = parse_artifact_bytes(raw)
            if type(value) is not dict or canonical_bytes(value) != raw:
                raise ValueError(f"identity evidence object: {name}")
            return value, hashlib.sha256(raw).hexdigest()

        journal, journal_sha = load("access-journal.json")
        receipts, receipts_sha = load("shard-receipts.json")
        lease, lease_sha = load("lease-manifest.json")
        core, core_sha = load("identity-core.json")
        manifest, manifest_sha = load("identity-manifest.json")
        receipt, receipt_sha = load("identity-receipt.json")
        terminal, terminal_sha = load("identity-terminal.json")
        directory_after = os.fstat(directory_descriptor)
        path_after = os.stat(directory, follow_symlinks=False)
        if (
            (
                directory_after.st_dev,
                directory_after.st_ino,
                directory_after.st_mode,
                directory_after.st_uid,
                directory_after.st_nlink,
                directory_after.st_mtime_ns,
                directory_after.st_ctime_ns,
                directory_after.st_flags,
            )
            != (
                directory_before.st_dev,
                directory_before.st_ino,
                directory_before.st_mode,
                directory_before.st_uid,
                directory_before.st_nlink,
                directory_before.st_mtime_ns,
                directory_before.st_ctime_ns,
                directory_before.st_flags,
            )
            or (path_after.st_dev, path_after.st_ino) != directory_identity
        ):
            raise ValueError("identity evidence directory identity changed")
    finally:
        _RAW_OS_CLOSE(directory_descriptor)
    entries = journal.get("entries")
    descriptors = lease.get("descriptors")
    if (
            journal.get("schema") != _ACCESS_JOURNAL_SCHEMA
            or receipts.get("schema") != _SHARD_RECEIPTS_SCHEMA
            or lease.get("schema") != _LEASE_MANIFEST_SCHEMA
            or core.get("schema") != _IDENTITY_CORE_SCHEMA
            or manifest.get("schema") != _IDENTITY_MANIFEST_SCHEMA
            or receipt.get("schema") != _IDENTITY_RECEIPT_SCHEMA
            or terminal.get("schema") != _IDENTITY_TERMINAL_SCHEMA
            or type(entries) is not list or len(entries) != 6
            or [item.get("ordinal") for item in entries] != [1, 2, 3, 4, 5, 6]
            or journal.get("checkpoint_shard_opens") != 6
            or journal.get("checkpoint_identity_hash_reads") != 6
            or receipts.get("receipts") != entries
            or receipts.get("access_prefix_receipt_count") != 24
            or journal.get("access_prefix_receipt_count") != 24):
        raise ValueError("identity journal or receipt census")
    if authority is None:
        authority_value: ValidatedIdentityAuthority | dict = {
            "authorization_id": journal.get("authorization_id"),
            "package_attempt_id": journal.get("package_attempt_id"),
            "checkpoint_identity_contract_sha256": journal.get(
                "checkpoint_identity_contract_sha256"
            ),
        }
    else:
        authority_value = authority
    if contract is None:
        reconstructed_shards: list[dict[str, object]] = []
        for item in entries:
            if type(item) is not dict:
                raise ValueError("identity journal entry")
            reconstructed_shards.append({
                "ordinal": item.get("ordinal"),
                "filename": item.get("shard_name"),
                "role": item.get("role"),
                "size_bytes": item.get("bytes"),
                "sha256": item.get("sha256"),
            })
        contract_value = {
            "checkpoint_set_sha256": journal.get("checkpoint_set_sha256"),
            "shards": reconstructed_shards,
        }
    else:
        contract_value = contract
    access_census = _validate_banked_identity_access_prefix(
        directory,
        authority_value,  # type: ignore[arg-type]
        contract_value,
        require_complete=True,
    )
    if (
        journal.get("access_prefix_genesis_sha256")
        != access_census.genesis_sha256
        or journal.get("access_prefix_head_sha256") != access_census.head_sha256
        or journal.get("access_census") != access_census.evidence
        or receipts.get("access_prefix_head_sha256") != access_census.head_sha256
        or core.get("access_prefix_head_sha256") != access_census.head_sha256
        or core.get("access_prefix_receipt_count") != 24
    ):
        raise ValueError("identity access summary closure")
    validate_descriptors(descriptors)
    if (lease.get("identity_only_retained_count") != 0
            or lease.get("retained_lease_count") != 5
            or core.get("identity_only_retained_count") != 0
            or core.get("retained_lease_count") != 5):
        raise ValueError("identity lease disposition")
    expected_manifest = {
        "access_journal_sha256":journal_sha,
        "shard_receipts_sha256":receipts_sha,
        "lease_manifest_sha256":lease_sha,
        "deterministic_core_sha256":core_sha,
        "access_prefix_genesis_sha256":access_census.genesis_sha256,
        "access_prefix_head_sha256":access_census.head_sha256,
        "access_prefix_receipt_count":24,
    }
    if any(manifest.get(key) != value for key, value in expected_manifest.items()):
        raise ValueError("identity manifest closure")
    if (
        receipt.get("identity_manifest_sha256") != manifest_sha
        or receipt.get("access_prefix_head_sha256") != access_census.head_sha256
    ):
        raise ValueError("identity receipt closure")
    if (terminal.get("identity_receipt_sha256") != receipt_sha
            or terminal.get("access_prefix_head_sha256") != access_census.head_sha256
            or terminal.get("state") != "COMPLETE" or terminal.get("result") != "PASS"):
        raise ValueError("identity terminal closure")
    if report is not None:
        if (core.get("ordered_shard_digests") != report.get("ordered_shard_digests")
                or descriptors != report.get("descriptor_identities")):
            raise ValueError("identity report closure")
    return {
        "result":"PASS", "leaf_count":len(names), "terminal_sha256":terminal_sha,
        "deterministic_core_sha256":core_sha,
        "access_prefix_receipt_count":access_census.receipt_count,
        "access_prefix_head_sha256":access_census.head_sha256,
        "access_census":access_census.evidence,
    }


def _minimum_gate_produce(authority: ValidatedIdentityAuthority, *, package_attempt_id: str,
                          package_durable_start: bool,
                          evidence_directory: Path | None = None) -> tuple[LeaseSet, dict]:
    if package_durable_start is not True:
        raise failure("F017_V12_IDENTITY_RUNTIME_AUTHORITY_DRIFT", "package durable start required")
    value, contract = _runtime_revalidate(authority, package_attempt_id)
    if not isinstance(evidence_directory, Path):
        raise failure(
            "F017_V12_IDENTITY_RUNTIME_AUTHORITY_DRIFT",
            "durable identity access receipt sink required",
            checkpoint_access=0,
        )
    access_writer = _AccessPrefixWriter(
        evidence_directory,
        authority,
        contract,
        write_once=value["schema"] == MINIMUM_INSTALLED_SCHEMA,
    )
    root = Path(value["checkpoint_root"])
    synthetic = value["authority_scope"] == "SYNTHETIC"
    bound_root_descriptor = _QUALIFICATION_ROOT_DESCRIPTOR.get()
    if bound_root_descriptor is not None:
        if not synthetic:
            raise failure(
                "F017_V12_IDENTITY_RUNTIME_AUTHORITY_DRIFT",
                "qualification root descriptor on production authority",
                checkpoint_access=0,
            )
        try:
            held = os.fstat(bound_root_descriptor)
            if (
                not stat.S_ISDIR(held.st_mode)
                or held.st_uid != os.getuid()
            ):
                raise OSError("qualification checkpoint root descriptor identity")
            root_fd = os.dup(bound_root_descriptor)
        except (OSError, TypeError, ValueError) as exc:
            raise failure(
                "F017_V12_IDENTITY_SHARD_OPEN_FAILURE",
                "qualification checkpoint root descriptor",
                checkpoint_access=0,
            ) from exc
    else:
        try:
            resolved = root.resolve(strict=True)
            temporary = Path(tempfile.gettempdir()).resolve(strict=True)
        except OSError as exc:
            raise failure("F017_V12_IDENTITY_SHARD_OPEN_FAILURE", "checkpoint root", checkpoint_access=0) from exc
        if root.is_symlink() or (synthetic and not resolved.is_relative_to(temporary)) or (not synthetic and resolved.is_relative_to(temporary)):
            raise failure("F017_V12_IDENTITY_SHARD_OPEN_FAILURE", "checkpoint root scope", checkpoint_access=0)
        try:
            root_fd, opened = open_directory_no_symlinks(resolved)
        except Exception as exc:
            raise failure("F017_V12_IDENTITY_SHARD_OPEN_FAILURE", "checkpoint root open", checkpoint_access=0) from exc
        if opened != resolved:
            retired, close_error = _retire_descriptor(root_fd)
            if close_error is not None:
                raise failure(
                    "F017_V12_IDENTITY_DESCRIPTOR_CHANGED",
                    "checkpoint root identity and descriptor close",
                    checkpoint_access="RECEIPT_DERIVED",
                    evidence_failure_type=(
                        f"ROOT_DESCRIPTOR_CLOSE:{type(close_error).__name__}"
                    ),
                ) from close_error
            if not retired:
                raise failure(
                    "F017_V12_IDENTITY_DESCRIPTOR_CHANGED",
                    "checkpoint root descriptor retained after identity mismatch",
                    checkpoint_access="RECEIPT_DERIVED",
                )
            raise failure("F017_V12_IDENTITY_SHARD_OPEN_FAILURE", "checkpoint root identity", checkpoint_access=0)
    records: list[LeaseRecord] = []
    digests: list[str] = []
    all_shard_descriptor_identities: list[dict[str, object]] = []
    identity_only_digest = ""
    opens = 0
    closed_descriptors = 0
    close_failures = 0
    unretired_descriptors: list[int] = []
    close_faults: list[str] = []

    def retire_retained_records() -> int:
        nonlocal closed_descriptors, close_failures
        retained = 0
        for record in records:
            retired, close_error = _retire_descriptor(record.descriptor)
            if close_error is None:
                closed_descriptors += 1
            else:
                close_failures += 1
                close_faults.append(
                    f"GRAPH_DESCRIPTOR_CLOSE:{type(close_error).__name__}"
                )
            if not retired:
                retained += 1
        for descriptor in unretired_descriptors:
            try:
                _RAW_OS_CLOSE(descriptor)
            except OSError as close_error:
                if close_error.errno != errno.EBADF:
                    retained += 1
        unretired_descriptors.clear()
        return retained

    def retire_root_descriptor() -> OSError | None:
        nonlocal root_fd
        if root_fd < 0:
            return None
        retired, close_error = _retire_descriptor(root_fd)
        if retired:
            root_fd = -1
        if close_error is not None:
            close_faults.append(
                f"ROOT_DESCRIPTOR_CLOSE:{type(close_error).__name__}"
            )
        return close_error

    def bank_access(
        *,
        operation: str,
        phase: str,
        effect_count: int,
        observed_bytes: int,
        descriptor_identity_sha256: str | None,
        observed_sha256: str | None,
        disposition: str,
        result: str,
        failure_outcome: str,
        failure_detail: str,
        observation: IdentityOperationObservation | None = None,
    ) -> str:
        try:
            return access_writer.bank(
                operation=operation,
                phase=phase,
                effect_count=effect_count,
                observed_bytes=observed_bytes,
                descriptor_identity_sha256=descriptor_identity_sha256,
                observed_sha256=observed_sha256,
                disposition=disposition,
                result=result,
            )
        except BaseException as exc:
            raise failure(
                failure_outcome,
                failure_detail,
                checkpoint_access="RECEIPT_DERIVED",
                operation_observation=observation,
                evidence_failure_type=type(exc).__name__,
            ) from exc

    try:
        root_identity = os.fstat(root_fd)
        required_names = _required_shard_names(contract)
        _require_checkpoint_root_membership(root_fd, required_names)
        for shard in contract["shards"]:
            ordinal = shard["ordinal"]
            bank_access(
                operation="SHARD_OPEN",
                phase="INTENT",
                effect_count=0,
                observed_bytes=0,
                descriptor_identity_sha256=None,
                observed_sha256=None,
                disposition="SHARD_OPEN_INTENT",
                result="PENDING",
                failure_outcome="F017_V12_IDENTITY_SHARD_OPEN_FAILURE",
                failure_detail=f"shard {ordinal} open intent evidence",
            )
            try:
                descriptor = os.open(shard["filename"], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_fd)
                opens += 1
            except OSError as exc:
                observation = IdentityOperationObservation(
                    0, 0, None, "SHARD_OPEN_FAILURE"
                )
                bank_access(
                    operation="SHARD_OPEN",
                    phase="COMPLETE",
                    effect_count=0,
                    observed_bytes=0,
                    descriptor_identity_sha256=None,
                    observed_sha256=None,
                    disposition="SHARD_OPEN_FAILURE",
                    result="FAIL",
                    failure_outcome="F017_V12_IDENTITY_SHARD_OPEN_FAILURE",
                    failure_detail=f"shard {ordinal} open completion evidence",
                    observation=observation,
                )
                raise failure(
                    "F017_V12_IDENTITY_SHARD_OPEN_FAILURE",
                    f"shard {ordinal}",
                    checkpoint_access="RECEIPT_DERIVED",
                    operation_observation=observation,
                ) from exc
            try:
                try:
                    opened_metadata = os.fstat(descriptor)
                    descriptor_sha256 = _descriptor_identity_sha256(opened_metadata)
                except OSError as exc:
                    observation = IdentityOperationObservation(
                        1, 0, None, "SHARD_OPEN_IDENTITY_FAILURE"
                    )
                    bank_access(
                        operation="SHARD_OPEN",
                        phase="COMPLETE",
                        effect_count=1,
                        observed_bytes=0,
                        descriptor_identity_sha256=None,
                        observed_sha256=None,
                        disposition="SHARD_OPEN_IDENTITY_FAILURE",
                        result="FAIL",
                        failure_outcome="F017_V12_IDENTITY_DESCRIPTOR_CHANGED",
                        failure_detail=f"shard {ordinal} open identity evidence",
                        observation=observation,
                    )
                    raise failure(
                        "F017_V12_IDENTITY_DESCRIPTOR_CHANGED",
                        f"shard {ordinal} open identity",
                        checkpoint_access="RECEIPT_DERIVED",
                        operation_observation=observation,
                    ) from exc
                bank_access(
                    operation="SHARD_OPEN",
                    phase="COMPLETE",
                    effect_count=1,
                    observed_bytes=0,
                    descriptor_identity_sha256=descriptor_sha256,
                    observed_sha256=None,
                    disposition="SHARD_OPEN_COMPLETE",
                    result="PASS",
                    failure_outcome="F017_V12_IDENTITY_SHARD_OPEN_FAILURE",
                    failure_detail=f"shard {ordinal} open completion evidence",
                    observation=IdentityOperationObservation(
                        1, 0, None, "SHARD_OPEN_COMPLETE"
                    ),
                )
                bank_access(
                    operation="IDENTITY_HASH_READ",
                    phase="INTENT",
                    effect_count=0,
                    observed_bytes=0,
                    descriptor_identity_sha256=descriptor_sha256,
                    observed_sha256=None,
                    disposition="IDENTITY_HASH_READ_INTENT",
                    result="PENDING",
                    failure_outcome="F017_V12_IDENTITY_SHARD_READ_FAILURE",
                    failure_detail=f"shard {ordinal} hash intent evidence",
                )
                try:
                    digest, metadata = _hash_descriptor(
                        descriptor,
                        shard["size_bytes"],
                        require_single_link=synthetic,
                    )
                except IdentityAuthorityError as exc:
                    observation = exc.operation_observation
                    if observation is None:
                        raise
                    bank_access(
                        operation="IDENTITY_HASH_READ",
                        phase="COMPLETE",
                        effect_count=observation.effect_count,
                        observed_bytes=observation.observed_bytes,
                        descriptor_identity_sha256=descriptor_sha256,
                        observed_sha256=observation.observed_sha256,
                        disposition=observation.disposition,
                        result="FAIL",
                        failure_outcome=exc.outcome_id,
                        failure_detail=f"shard {ordinal} hash completion evidence",
                        observation=observation,
                    )
                    raise
                all_shard_descriptor_identities.append({
                    "filename": shard["filename"],
                    "device": metadata.st_dev,
                    "inode": metadata.st_ino,
                })
                if digest != shard["sha256"]:
                    observation = IdentityOperationObservation(
                        1,
                        shard["size_bytes"],
                        digest,
                        "IDENTITY_HASH_MISMATCH",
                    )
                    bank_access(
                        operation="IDENTITY_HASH_READ",
                        phase="COMPLETE",
                        effect_count=1,
                        observed_bytes=shard["size_bytes"],
                        descriptor_identity_sha256=descriptor_sha256,
                        observed_sha256=digest,
                        disposition="IDENTITY_HASH_MISMATCH",
                        result="FAIL",
                        failure_outcome="F017_V12_IDENTITY_SHARD_HASH_MISMATCH",
                        failure_detail=f"shard {ordinal} hash completion evidence",
                        observation=observation,
                    )
                    raise failure(
                        "F017_V12_IDENTITY_SHARD_HASH_MISMATCH",
                        f"shard {ordinal}",
                        checkpoint_access="RECEIPT_DERIVED",
                        operation_observation=observation,
                    )
                bank_access(
                    operation="IDENTITY_HASH_READ",
                    phase="COMPLETE",
                    effect_count=1,
                    observed_bytes=shard["size_bytes"],
                    descriptor_identity_sha256=descriptor_sha256,
                    observed_sha256=digest,
                    disposition="IDENTITY_HASH_COMPLETE",
                    result="PASS",
                    failure_outcome="F017_V12_IDENTITY_SHARD_READ_FAILURE",
                    failure_detail=f"shard {ordinal} hash completion evidence",
                    observation=IdentityOperationObservation(
                        1,
                        shard["size_bytes"],
                        digest,
                        "IDENTITY_HASH_COMPLETE",
                    ),
                )
                if shard["role"] == "IDENTITY_ONLY":
                    identity_only_digest = digest
                else:
                    identity = {
                        "device": metadata.st_dev, "inode": metadata.st_ino, "mode": metadata.st_mode,
                        "size": metadata.st_size, "mtime_ns": metadata.st_mtime_ns,
                        "ctime_ns": metadata.st_ctime_ns, "shard_ordinal": ordinal,
                        "role": "GRAPH_PAYLOAD", "lease_id": f"LEASE-{package_attempt_id}-{ordinal}",
                    }
                    records.append(LeaseRecord(identity, descriptor))
                    descriptor = -1
                    digests.append(digest)
            finally:
                if descriptor >= 0:
                    active_error = sys.exception()
                    retired, close_error = _retire_descriptor(descriptor)
                    if close_error is None:
                        closed_descriptors += 1
                    else:
                        close_failures += 1
                        close_faults.append(
                            f"SHARD_DESCRIPTOR_CLOSE:{type(close_error).__name__}"
                        )
                    if not retired:
                        unretired_descriptors.append(descriptor)
                    if close_error is not None and active_error is None:
                        raise failure(
                            "F017_V12_IDENTITY_DESCRIPTOR_CHANGED",
                            f"shard {ordinal} descriptor close",
                            checkpoint_access="RECEIPT_DERIVED",
                            evidence_failure_type=close_faults[-1],
                        ) from close_error
        validate_descriptors([record.identity for record in records], [item["size_bytes"] for item in contract["shards"] if item["role"] == "GRAPH_PAYLOAD"])
        leases = LeaseSet(records, identity_only_digest, digests)
        access_census = _validate_banked_identity_access_prefix(
            evidence_directory,
            authority,
            contract,
            require_complete=True,
        )
        report = {
            "result": "PASS", "authority_scope": value["authority_scope"],
            "operation_class": value["operation_class"], "generation": "V12",
            "ordered_shard_digests": [identity_only_digest, *digests],
            "checkpoint_shard_opens": opens, "checkpoint_identity_hash_reads": 6,
            "checkpoint_identity_hash_bytes": (
                access_census.identity_hash_bytes_lower_bound
            ),
            "access_prefix_receipt_count": access_census.receipt_count,
            "access_prefix_head_sha256": access_census.head_sha256,
            "access_census": access_census.evidence,
            "retained_lease_count": len(records), "identity_only_retained_count": 0,
            "producer_internal_descriptors_opened": opens,
            "producer_internal_descriptors_closed": closed_descriptors,
            "producer_internal_descriptor_close_failures": close_failures,
            "descriptor_identities": leases.descriptors, "path_reopen_count": 0,
            "checkpoint_root_descriptor_identity": {
                "device": root_identity.st_dev,
                "inode": root_identity.st_ino,
            },
            "all_shard_descriptor_identities": all_shard_descriptor_identities,
        }
        report["evidence"] = _bank_identity_evidence(
            evidence_directory, authority, contract, leases, report,
            access_census=access_census,
            _write_once=value["schema"] == MINIMUM_INSTALLED_SCHEMA,
        )
        root_close_error = retire_root_descriptor()
        if root_close_error is not None:
            raise failure(
                "F017_V12_IDENTITY_DESCRIPTOR_CHANGED",
                "checkpoint root descriptor close",
                checkpoint_access="RECEIPT_DERIVED",
                evidence_failure_type=close_faults[-1],
            ) from root_close_error
        return leases, report
    except IdentityAuthorityError as exc:
        retained_descriptors = retire_retained_records()
        retire_root_descriptor()
        if close_faults:
            exc = failure(
                exc.outcome_id,
                exc.detail,
                checkpoint_access="RECEIPT_DERIVED",
                operation_observation=exc.operation_observation,
                evidence_failure_type=";".join(close_faults),
            )
        try:
            access_census = _validate_banked_identity_access_prefix(
                evidence_directory,
                authority,
                contract,
            )
        except IdentityAccessPrefixValidationError:
            raise
        raise with_failure_context(
            exc,
            access_census=access_census,
            descriptor_disposition=IdentityDescriptorDisposition(
                opens,
                closed_descriptors,
                close_failures,
                retained_descriptors,
            ),
        ) from exc
    except Exception as exc:
        retire_retained_records()
        retire_root_descriptor()
        if close_faults:
            raise failure(
                "F017_V12_IDENTITY_DESCRIPTOR_CHANGED",
                "producer descriptor close after internal failure",
                checkpoint_access="RECEIPT_DERIVED",
                evidence_failure_type=";".join(close_faults),
            ) from exc
        raise


def produce(authority: ValidatedIdentityAuthority, *, package_attempt_id: str,
            package_durable_start: bool,
            evidence_directory: Path | None = None) -> tuple[LeaseSet, dict]:
    """Superseded public producer entrypoint; production uses the sealed path."""
    del authority, package_attempt_id, package_durable_start, evidence_directory
    raise RuntimeError(
        "superseded by F017 Sequence 39 minimum-gate identity entrypoint"
    )


def _qualification_produce(
    authority: ValidatedIdentityAuthority,
    *,
    package_attempt_id: str,
    package_durable_start: bool,
    evidence_directory: Path | None = None,
) -> tuple[LeaseSet, dict]:
    """Historical synthetic qualification adapter; never accepts production."""
    if (
        type(authority) is not ValidatedIdentityAuthority
        or authority.get("authority_scope") != "SYNTHETIC"
    ):
        raise failure(
            "F017_V12_IDENTITY_RUNTIME_AUTHORITY_DRIFT",
            "qualification producer requires synthetic authority",
        )
    return _minimum_gate_produce(
        authority,
        package_attempt_id=package_attempt_id,
        package_durable_start=package_durable_start,
        evidence_directory=evidence_directory,
    )
