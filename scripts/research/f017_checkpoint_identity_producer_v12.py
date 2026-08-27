#!/usr/bin/env python3
"""Generic V12 six-shard identity stage with five retained leases."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import tempfile

from f017_accounting_root_continuity_v1 import open_directory_no_symlinks
from f017_bounded_artifact_decode_v1 import parse_artifact_bytes
from f017_checkpoint_identity_authority_v12 import ValidatedIdentityAuthority
from f017_checkpoint_identity_lifecycle_v12 import failure
from f017_descriptor_lease_manager_v10 import LeaseRecord, LeaseSet, validate_descriptors

ROOT = Path(__file__).resolve().parents[2]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _runtime_revalidate(authority: ValidatedIdentityAuthority, package_attempt_id: str) -> tuple[dict, dict]:
    if type(authority) is not ValidatedIdentityAuthority or authority.posture != "INSTALLED":
        raise failure("F017_V12_IDENTITY_RUNTIME_AUTHORITY_DRIFT", "immutable installed authority required")
    value = authority.as_dict()
    if value["package_attempt_id"] != package_attempt_id:
        raise failure("F017_V12_IDENTITY_PACKAGE_ATTEMPT_MISMATCH", "package attempt identity")
    bindings = (
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


def produce(authority: ValidatedIdentityAuthority, *, package_attempt_id: str,
            package_durable_start: bool, progress=None) -> tuple[LeaseSet, dict]:
    if package_durable_start is not True:
        raise failure("F017_V12_IDENTITY_RUNTIME_AUTHORITY_DRIFT", "package durable start required")
    value, contract = _runtime_revalidate(authority, package_attempt_id)
    root = Path(value["checkpoint_root"])
    try:
        resolved = root.resolve(strict=True)
        temporary = Path(tempfile.gettempdir()).resolve(strict=True)
    except OSError as exc:
        raise failure("F017_V12_IDENTITY_SHARD_OPEN_FAILURE", "checkpoint root", checkpoint_access=0) from exc
    synthetic = value["authority_scope"] == "SYNTHETIC"
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
    identity_only_digest = ""
    opens = 0
    try:
        for shard in contract["shards"]:
            ordinal = shard["ordinal"]
            try:
                descriptor = os.open(shard["filename"], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_fd)
                opens += 1
            except OSError as exc:
                raise failure("F017_V12_IDENTITY_SHARD_OPEN_FAILURE", f"shard {ordinal}", checkpoint_access=opens) from exc
            try:
                digest, metadata = _hash_descriptor(descriptor, shard["size_bytes"], require_single_link=synthetic)
                if digest != shard["sha256"]:
                    raise failure("F017_V12_IDENTITY_SHARD_HASH_MISMATCH", f"shard {ordinal}", checkpoint_access=opens)
                if progress is not None:
                    progress("SHARD_RECEIPT", ordinal, digest)
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
        return leases, {
            "result": "PASS", "authority_scope": value["authority_scope"],
            "operation_class": value["operation_class"], "generation": "V12",
            "ordered_shard_digests": [identity_only_digest, *digests],
            "checkpoint_shard_opens": opens, "checkpoint_identity_hash_reads": 6,
            "retained_lease_count": len(records), "identity_only_retained_count": 0,
            "descriptor_identities": leases.descriptors, "path_reopen_count": 0,
        }
    except Exception:
        for record in records:
            try:
                os.close(record.descriptor)
            except OSError:
                pass
        raise
    finally:
        os.close(root_fd)
