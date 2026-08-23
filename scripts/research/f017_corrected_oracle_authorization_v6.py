#!/usr/bin/env python3
"""Strict, non-numerical authorization parser for generation v6."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/6.0.0"
INTERFACE_SCHEMA = "pulsarmlx.f017.corrected-oracle-authorization-consumer-interface/6.0.0"
PRIMARY_ROLE = "INDEPENDENT_CPU_REFERENCE"
SECONDARY_ROLE = "INDEPENDENT_ACCELERATED_CROSS_CHECK"
ID_PATTERN = re.compile(r"^[A-Z0-9](?:[A-Z0-9-]{0,126}[A-Z0-9])?$")
FORBIDDEN_ID_PARTS = ("INERT", "FIXTURE", "TEST", "SYNTHETIC")


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON number: {value}")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8") + b"\n"


def strict_bytes(data: bytes, *, require_canonical: bool = True) -> dict:
    if len(data) > 16 * 1024 * 1024 or data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("bounded BOM-free authorization bytes required")
    value = json.loads(
        data.decode("utf-8"),
        object_pairs_hook=_pairs,
        parse_constant=_reject_constant,
    )
    if not isinstance(value, dict):
        raise ValueError("authorization object required")
    if require_canonical and data != canonical_bytes(value):
        raise ValueError("noncanonical authorization bytes")
    return value


def read_regular_nofollow(path: Path, maximum: int = 16 * 1024 * 1024) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        observed = os.fstat(descriptor)
        if not stat.S_ISREG(observed.st_mode) or observed.st_size > maximum:
            raise ValueError("bounded regular file required")
        data = os.read(descriptor, observed.st_size)
        if len(data) != observed.st_size or os.read(descriptor, 1):
            raise ValueError("exact regular-file readback")
        return data
    finally:
        os.close(descriptor)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _exact_keys(value: dict, expected: list[str], label: str) -> None:
    if type(value) is not dict or set(value) != set(expected) or len(value) != len(expected):
        raise ValueError(f"{label} key census")


def _live_id(value: object, label: str) -> str:
    if type(value) is not str or not ID_PATTERN.fullmatch(value):
        raise ValueError(f"{label} grammar")
    upper = value.upper()
    if any(part in upper for part in FORBIDDEN_ID_PARTS):
        raise ValueError(f"{label} inert/test identity")
    return value


def load_interface(path: Path) -> dict:
    value = strict_bytes(read_regular_nofollow(path))
    if value.get("schema") != INTERFACE_SCHEMA:
        raise ValueError("v6 authorization interface required")
    return value


@dataclass(frozen=True)
class ParsedAuthorization:
    document: dict
    sha256: str
    role: str
    grant: dict


def parse_authorization(
    authorization_path: Path,
    interface_path: Path,
    *,
    role: str,
    executing_path: Path,
    target_source_path: Path,
    require_installed: bool,
    installation_receipt_path: Path | None = None,
) -> ParsedAuthorization:
    interface = load_interface(interface_path)
    data = read_regular_nofollow(authorization_path)
    document = strict_bytes(data)
    _exact_keys(document, interface["top_level_keys"], "authorization")
    _exact_keys(document["package"], interface["package_keys"], "package grant")
    _exact_keys(document["primary"], interface["consumer_keys"], "primary grant")
    _exact_keys(document["secondary"], interface["consumer_keys"], "secondary grant")
    _exact_keys(document["context"], interface["context_keys"], "context")
    _exact_keys(document["limits"], interface["limits_keys"], "limits")
    if type(document["shards"]) is not list or len(document["shards"]) != document["limits"]["checkpoint_shard_count"]:
        raise ValueError("checkpoint shard census")
    for shard in document["shards"]:
        _exact_keys(shard, interface["shard_keys"], "checkpoint shard")
        if type(shard["filename"]) is not str or type(shard["size_bytes"]) is not int or type(shard["sha256"]) is not str or type(shard["access_role"]) is not str:
            raise ValueError("checkpoint shard types")
    if document["schema"] != SCHEMA or document["authority_generation"] != 6:
        raise ValueError("authorization generation")
    if interface.get("interface_scope") != document["authority_scope"]:
        raise ValueError("authorization/interface scope")
    canonical_interface = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-authorization-consumer-interface-v6.json"
    if document["authority_scope"] == "PRODUCTION" and interface_path.resolve(strict=True) != canonical_interface.resolve(strict=True):
        raise ValueError("canonical production interface required")
    if document["state"] != "AUTHORIZED" or document["live"] is not True:
        raise ValueError("authorized document required")
    identifiers = [
        _live_id(document["authorization_id"], "authorization_id"),
        _live_id(document["package_attempt_id"], "package_attempt_id"),
        _live_id(document["primary_event_id"], "primary_event_id"),
        _live_id(document["secondary_event_id"], "secondary_event_id"),
    ]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("lifecycle identity uniqueness")
    if document["package"]["attempts"] != 1 or document["package"]["retries"] != 0 or document["package"]["resume"] is not False:
        raise ValueError("package lifecycle")
    selected = "primary" if role == PRIMARY_ROLE else "secondary" if role == SECONDARY_ROLE else None
    if selected is None:
        raise ValueError("consumer role")
    grant = document[selected]
    if grant["role"] != role or grant["event_id"] != document[f"{selected}_event_id"]:
        raise ValueError("consumer grant identity")
    if grant["attempts"] != 1 or grant["retries"] != 0 or grant["resume"] is not False:
        raise ValueError("consumer lifecycle")
    executing = executing_path.resolve(strict=True)
    target_source = target_source_path.resolve(strict=True)
    if grant["producer_path"] != executing.relative_to(ROOT).as_posix() or grant["producer_sha256"] != sha256_path(executing):
        raise ValueError("consumer producer binding")
    if grant["target_source_path"] != target_source.relative_to(ROOT).as_posix() or grant["target_source_sha256"] != sha256_path(target_source):
        raise ValueError("target source binding")
    if document["context"] != interface["pinned_context"] or document["limits"] != interface["pinned_limits"]:
        raise ValueError("context or limits binding")
    if require_installed:
        if installation_receipt_path is None:
            raise ValueError("installation receipt required")
        canonical = Path(document["canonical_install_path"])
        if authorization_path.resolve(strict=True) != canonical:
            raise ValueError("canonical installation path")
        receipt_data = read_regular_nofollow(installation_receipt_path)
        receipt = strict_bytes(receipt_data)
        required = {
            "schema", "result", "authorization_id", "package_attempt_id",
            "primary_event_id", "secondary_event_id", "candidate_sha256",
            "installed_authorization_sha256", "installation_path",
            "candidate_install_byte_identity",
        }
        if set(receipt) != required or receipt["result"] != "PASS":
            raise ValueError("installation receipt census")
        if receipt["authorization_id"] != document["authorization_id"] or receipt["package_attempt_id"] != document["package_attempt_id"]:
            raise ValueError("installation receipt identity")
        if receipt["installed_authorization_sha256"] != hashlib.sha256(data).hexdigest() or receipt["candidate_install_byte_identity"] is not True:
            raise ValueError("installed authorization readback")
    return ParsedAuthorization(document, hashlib.sha256(data).hexdigest(), role, grant)
