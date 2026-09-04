#!/usr/bin/env python3
"""Generic V12 six-shard identity stage with five retained leases."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import tempfile
from contextvars import ContextVar, Token

from f017_accounting_root_continuity_v1 import open_directory_no_symlinks
from f017_bounded_artifact_decode_v1 import parse_artifact_bytes
from f017_canonical_serialization_v10 import bank_exclusive, canonical_bytes
from f017_checkpoint_identity_authority_v12 import (
    MINIMUM_INSTALLED_SCHEMA,
    ValidatedIdentityAuthority,
)
from f017_checkpoint_identity_lifecycle_v12 import failure
from f017_descriptor_lease_manager_v10 import LeaseRecord, LeaseSet, validate_descriptors
from f017_write_once_artifact_v1 import _bank_exclusive_write_once

ROOT = Path(__file__).resolve().parents[2]
__all__ = ("validate_banked_identity_evidence",)

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
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        raise failure("F017_V12_IDENTITY_DESCRIPTOR_CHANGED", "shard is not regular", checkpoint_access="OBSERVED_PREFIX")
    if before.st_size != expected_size:
        raise failure("F017_V12_IDENTITY_SHARD_SIZE_MISMATCH", "shard size", checkpoint_access="OBSERVED_PREFIX")
    if require_single_link and before.st_nlink != 1:
        raise failure("F017_V12_IDENTITY_DESCRIPTOR_CHANGED", "synthetic hard link", checkpoint_access="OBSERVED_PREFIX")
    digest = hashlib.sha256()
    offset = 0
    try:
        while offset < expected_size:
            block = os.pread(descriptor, min(1024 * 1024, expected_size - offset), offset)
            if not block:
                raise failure("F017_V12_IDENTITY_SHARD_READ_FAILURE", "short descriptor read", checkpoint_access="OBSERVED_PREFIX")
            digest.update(block)
            offset += len(block)
    except OSError as exc:
        raise failure("F017_V12_IDENTITY_SHARD_READ_FAILURE", type(exc).__name__, checkpoint_access="OBSERVED_PREFIX") from exc
    after = os.fstat(descriptor)
    identity = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
    if identity(before) != identity(after):
        raise failure("F017_V12_IDENTITY_DESCRIPTOR_CHANGED", "descriptor identity changed", checkpoint_access="OBSERVED_PREFIX")
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


def _bank_identity_evidence(directory: Path, authority: ValidatedIdentityAuthority,
                            contract: dict, leases: LeaseSet, report: dict,
                            *, _write_once: bool = False) -> dict:
    if type(_write_once) is not bool:
        raise TypeError("identity evidence write-once policy")
    bank_control = _bank_exclusive_write_once if _write_once else bank_exclusive
    directory.mkdir(parents=True, exist_ok=False)
    access_journal = {
        "schema":"pulsarmlx.f017.checkpoint-identity-access-journal/12.0.0",
        "authorization_id":authority.get("authorization_id"),
        "package_attempt_id":authority.get("package_attempt_id"),
        "entries":[{"ordinal":item["ordinal"],"role":item["role"],"bytes":item["size_bytes"],"sha256":digest}
                   for item, digest in zip(contract["shards"], report["ordered_shard_digests"], strict=True)],
        "checkpoint_shard_opens":6,"checkpoint_identity_hash_reads":6,"result":"PASS",
    }
    journal_sha = bank_control(directory / "access-journal.json", access_journal)
    receipts = {
        "schema":"pulsarmlx.f017.checkpoint-identity-shard-receipts/12.0.0",
        "package_attempt_id":authority.get("package_attempt_id"),
        "receipts":access_journal["entries"],"result":"PASS",
    }
    receipts_sha = bank_control(directory / "shard-receipts.json", receipts)
    lease_manifest = {
        "schema":"pulsarmlx.f017.checkpoint-identity-lease-manifest/12.0.0",
        "package_attempt_id":authority.get("package_attempt_id"),
        "identity_only_retained_count":0,"retained_lease_count":5,
        "descriptors":leases.descriptors,"result":"PASS",
    }
    lease_sha = bank_control(directory / "lease-manifest.json", lease_manifest)
    deterministic_core = {
        "authority_scope":authority.get("authority_scope"),
        "operation_class":authority.get("operation_class"),
        "checkpoint_set_sha256":authority.get("checkpoint_set_sha256"),
        "ordered_shard_digests":report["ordered_shard_digests"],
        "shard_roles":[item["role"] for item in contract["shards"]],
        "shard_sizes":[item["size_bytes"] for item in contract["shards"]],
        "identity_only_retained_count":0,"retained_lease_count":5,
    }
    core_sha = bank_control(directory / "identity-core.json", deterministic_core)
    manifest = {
        "schema":"pulsarmlx.f017.checkpoint-identity-manifest/12.0.0",
        "authorization_id":authority.get("authorization_id"),
        "package_attempt_id":authority.get("package_attempt_id"),
        "access_journal_sha256":journal_sha,"shard_receipts_sha256":receipts_sha,
        "lease_manifest_sha256":lease_sha,"deterministic_core_sha256":core_sha,
        "result":"PASS",
    }
    manifest_sha = bank_control(directory / "identity-manifest.json", manifest)
    receipt = {
        "schema":"pulsarmlx.f017.checkpoint-identity-receipt/12.0.0",
        "authorization_id":authority.get("authorization_id"),
        "package_attempt_id":authority.get("package_attempt_id"),
        "identity_manifest_sha256":manifest_sha,"result":"PASS",
    }
    receipt_sha = bank_control(directory / "identity-receipt.json", receipt)
    terminal = {
        "schema":"pulsarmlx.f017.checkpoint-identity-terminal/12.0.0",
        "package_attempt_id":authority.get("package_attempt_id"),
        "identity_receipt_sha256":receipt_sha,"state":"COMPLETE","result":"PASS",
    }
    terminal_sha = bank_control(directory / "identity-terminal.json", terminal)
    result = {"access_journal_sha256":journal_sha,"shard_receipts_sha256":receipts_sha,
            "lease_manifest_sha256":lease_sha,"deterministic_core_sha256":core_sha,
            "identity_manifest_sha256":manifest_sha,"identity_receipt_sha256":receipt_sha,
            "identity_terminal_sha256":terminal_sha,"identity_terminal_state":"COMPLETE"}
    validate_banked_identity_evidence(directory, report)
    return result


def validate_banked_identity_evidence(directory: Path, report: dict | None = None) -> dict:
    """Validate the complete bounded identity-evidence closure from committed bytes."""
    names = {
        "access-journal.json", "shard-receipts.json", "lease-manifest.json",
        "identity-core.json", "identity-manifest.json", "identity-receipt.json",
        "identity-terminal.json",
    }
    if directory.is_symlink() or set(os.listdir(directory)) != names:
        raise ValueError("identity evidence leaf census")

    def load(name: str) -> tuple[dict, str]:
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"identity evidence leaf: {name}")
        raw = path.read_bytes()
        value = parse_artifact_bytes(raw)
        if type(value) is not dict:
            raise ValueError(f"identity evidence object: {name}")
        return value, hashlib.sha256(raw).hexdigest()

    journal, journal_sha = load("access-journal.json")
    receipts, receipts_sha = load("shard-receipts.json")
    lease, lease_sha = load("lease-manifest.json")
    core, core_sha = load("identity-core.json")
    manifest, manifest_sha = load("identity-manifest.json")
    receipt, receipt_sha = load("identity-receipt.json")
    terminal, terminal_sha = load("identity-terminal.json")
    entries = journal.get("entries")
    descriptors = lease.get("descriptors")
    if (type(entries) is not list or len(entries) != 6
            or [item.get("ordinal") for item in entries] != [1, 2, 3, 4, 5, 6]
            or journal.get("checkpoint_shard_opens") != 6
            or journal.get("checkpoint_identity_hash_reads") != 6
            or receipts.get("receipts") != entries):
        raise ValueError("identity journal or receipt census")
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
    }
    if any(manifest.get(key) != value for key, value in expected_manifest.items()):
        raise ValueError("identity manifest closure")
    if receipt.get("identity_manifest_sha256") != manifest_sha:
        raise ValueError("identity receipt closure")
    if (terminal.get("identity_receipt_sha256") != receipt_sha
            or terminal.get("state") != "COMPLETE" or terminal.get("result") != "PASS"):
        raise ValueError("identity terminal closure")
    if report is not None:
        if (core.get("ordered_shard_digests") != report.get("ordered_shard_digests")
                or descriptors != report.get("descriptor_identities")):
            raise ValueError("identity report closure")
    return {"result":"PASS", "leaf_count":len(names), "terminal_sha256":terminal_sha,
            "deterministic_core_sha256":core_sha}


def _minimum_gate_produce(authority: ValidatedIdentityAuthority, *, package_attempt_id: str,
                          package_durable_start: bool,
                          evidence_directory: Path | None = None) -> tuple[LeaseSet, dict]:
    if package_durable_start is not True:
        raise failure("F017_V12_IDENTITY_RUNTIME_AUTHORITY_DRIFT", "package durable start required")
    value, contract = _runtime_revalidate(authority, package_attempt_id)
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
            os.close(root_fd)
            raise failure("F017_V12_IDENTITY_SHARD_OPEN_FAILURE", "checkpoint root identity", checkpoint_access=0)
    records: list[LeaseRecord] = []
    digests: list[str] = []
    all_shard_descriptor_identities: list[dict[str, object]] = []
    identity_only_digest = ""
    opens = 0
    try:
        root_identity = os.fstat(root_fd)
        required_names = _required_shard_names(contract)
        _require_checkpoint_root_membership(root_fd, required_names)
        for shard in contract["shards"]:
            ordinal = shard["ordinal"]
            try:
                descriptor = os.open(shard["filename"], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_fd)
                opens += 1
            except OSError as exc:
                raise failure("F017_V12_IDENTITY_SHARD_OPEN_FAILURE", f"shard {ordinal}", checkpoint_access=opens) from exc
            try:
                digest, metadata = _hash_descriptor(descriptor, shard["size_bytes"], require_single_link=synthetic)
                all_shard_descriptor_identities.append({
                    "filename": shard["filename"],
                    "device": metadata.st_dev,
                    "inode": metadata.st_ino,
                })
                if digest != shard["sha256"]:
                    raise failure("F017_V12_IDENTITY_SHARD_HASH_MISMATCH", f"shard {ordinal}", checkpoint_access=opens)
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
                    os.close(descriptor)
        validate_descriptors([record.identity for record in records], [item["size_bytes"] for item in contract["shards"] if item["role"] == "GRAPH_PAYLOAD"])
        leases = LeaseSet(records, identity_only_digest, digests)
        report = {
            "result": "PASS", "authority_scope": value["authority_scope"],
            "operation_class": value["operation_class"], "generation": "V12",
            "ordered_shard_digests": [identity_only_digest, *digests],
            "checkpoint_shard_opens": opens, "checkpoint_identity_hash_reads": 6,
            "retained_lease_count": len(records), "identity_only_retained_count": 0,
            "descriptor_identities": leases.descriptors, "path_reopen_count": 0,
            "checkpoint_root_descriptor_identity": {
                "device": root_identity.st_dev,
                "inode": root_identity.st_ino,
            },
            "all_shard_descriptor_identities": all_shard_descriptor_identities,
        }
        if evidence_directory is not None:
            report["evidence"] = _bank_identity_evidence(
                evidence_directory, authority, contract, leases, report,
                _write_once=value["schema"] == MINIMUM_INSTALLED_SCHEMA,
            )
        return leases, report
    except Exception:
        for record in records:
            try:
                os.close(record.descriptor)
            except OSError:
                pass
        raise
    finally:
        os.close(root_fd)


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
