#!/usr/bin/env python3
"""Strict, non-numerical authorization parser for generation v6."""
from __future__ import annotations

import hashlib
import json
import math
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
FORBIDDEN_ID_PARTS = ("INERT", "FIXTURE", "TEST", "SYNTHETIC", "REHEARSAL")
PRODUCTION_AUTHORITY_PATHS = {
    "implementation_measurement_manifest_path": "docs/architecture/reviews/evidence/f017-corrected-oracle-lifecycle-v6-implementation-measurement-v1.json",
    "authorization_interface_path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-authorization-consumer-interface-v6.json",
    "scientific_access_contract_path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v6.json",
    "event_accounting_contract_path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event-accounting-v6.json",
    "path_timing_contract_path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-path-timing-v6.json",
    "canonical_serialization_contract_path": "specs/017-rust-native-inference-runtime/contracts/f017-canonical-json-bytes-v6.json",
    "lifecycle_semantic_model_path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-lifecycle-semantic-model-v6.json",
    "numerical_contract_path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v3.json",
    "numerical_capability_policy_path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-numerical-capability-policy-v1.json",
    "numerical_requalification_path": "docs/architecture/reviews/evidence/f017-corrected-oracle-numerical-requalification-v3.json",
    "numerical_methodology_path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v1.json",
    "checkpoint_manifest_path": "docs/validation/glm52-checkpoint.json",
    "checkpoint_catalog_path": "docs/research/glm52/raw/f016-c01-catalog-0001.json",
}
PRODUCTION_CAPABILITY_PATHS = {
    "primary": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-primary-capability-v6.json",
    "secondary": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-secondary-capability-v6.json",
}
PRODUCTION_GEOMETRY_PATH = "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-geometry-v1.json"


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON number: {value}")


def _canonical_value(value: Any) -> Any:
    """Map every finite float to its one cross-runtime authority spelling."""
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("nonfinite JSON number")
        return value.hex()
    if type(value) is list:
        return [_canonical_value(item) for item in value]
    if type(value) is dict:
        return {key: _canonical_value(item) for key, item in value.items()}
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8") + b"\n"


def decode_canonical_floats(value: Any) -> Any:
    """Decode only the frozen hexadecimal float spelling at numerical edges."""
    if type(value) is str and re.fullmatch(r"-?0x[0-9a-f]+(?:\.[0-9a-f]*)?p[+-][0-9]+", value):
        return float.fromhex(value)
    if type(value) is list:
        return [decode_canonical_floats(item) for item in value]
    if type(value) is dict:
        return {key: decode_canonical_floats(item) for key, item in value.items()}
    return value


def _typed_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return set(left) == set(right) and all(_typed_equal(left[key], right[key]) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(_typed_equal(a, b) for a, b in zip(left, right, strict=True))
    return left == right


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


def _authority_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def validate_authority_bindings(document: dict, interface: dict, interface_path: Path) -> None:
    """Verify every path/SHA pair against exact bytes before installation."""
    pairs = interface.get("authority_path_sha_pairs")
    if type(pairs) is not dict or not pairs:
        raise ValueError("authority path/SHA registry")
    if document["authority_scope"] == "PRODUCTION" and set(pairs) != set(PRODUCTION_AUTHORITY_PATHS):
        raise ValueError("production authority path census")
    if document["authority_scope"] == "PRODUCTION":
        if document["geometry_path"] != PRODUCTION_GEOMETRY_PATH:
            raise ValueError("canonical production geometry path")
        for role, expected_path in PRODUCTION_CAPABILITY_PATHS.items():
            if document[role]["capability_path"] != expected_path:
                raise ValueError(f"canonical production {role} capability path")
        if document["lifecycle_semantic_model_sha256"] != interface["semantic_model_sha256"]:
            raise ValueError("reviewed lifecycle model binding")
    for path_field, sha_field in pairs.items():
        declared = document[path_field]
        expected_sha = document[sha_field]
        if type(declared) is not str or type(expected_sha) is not str or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            raise ValueError(f"authority path/SHA types: {path_field}")
        if document["authority_scope"] == "PRODUCTION" and declared != PRODUCTION_AUTHORITY_PATHS[path_field]:
            raise ValueError(f"canonical production authority path: {path_field}")
        path = _authority_path(declared)
        if path_field == "authorization_interface_path" and path.resolve(strict=True) != interface_path.resolve(strict=True):
            raise ValueError("authorization interface path identity")
        if sha256_path(path.resolve(strict=True)) != expected_sha:
            raise ValueError(f"authority byte binding: {path_field}")
    for role in ("primary", "secondary"):
        grant = document[role]
        capability = _authority_path(grant["capability_path"])
        if sha256_path(capability.resolve(strict=True)) != grant["capability_sha256"]:
            raise ValueError(f"{role} capability byte binding")
    if document["authority_scope"] == "SYNTHETIC_QUALIFICATION":
        checkpoint_root = Path(document["checkpoint_root"])
        catalog = Path(document["checkpoint_catalog_path"])
        manifest = Path(document["checkpoint_manifest_path"])
        if (
            not checkpoint_root.is_absolute()
            or checkpoint_root.name != "checkpoint"
            or not catalog.is_absolute()
            or not manifest.is_absolute()
            or catalog.parent.resolve(strict=True) != checkpoint_root.parent.resolve(strict=True)
            or manifest.parent.resolve(strict=True) != checkpoint_root.parent.resolve(strict=True)
            or any(not shard["filename"].startswith("synthetic-") for shard in document["shards"])
        ):
            raise ValueError("synthetic checkpoint is not structurally isolated")


def validate_checkpoint_root_descriptor(document: dict, supplied: Path) -> None:
    """Validate the checkpoint-root descriptor without opening any shard."""
    declared = Path(document["checkpoint_root"])
    if (
        not declared.is_absolute()
        or not supplied.is_absolute()
        or ".." in declared.parts
        or ".." in supplied.parts
    ):
        raise ValueError("absolute checkpoint root descriptor")
    # A production-shaped rehearsal remains non-authoritative and must run on
    # CI hosts where the production volume is intentionally absent.  Preserve
    # the exact path text there; if the root exists, apply the production check.
    if document["authority_scope"] == "PRODUCTION_SHAPED_REHEARSAL":
        if str(declared) != str(supplied):
            raise ValueError("checkpoint root descriptor text")
        if not supplied.exists():
            return
    declared_canonical = declared.resolve(strict=True)
    supplied_canonical = supplied.resolve(strict=True)
    if declared_canonical != supplied_canonical:
        raise ValueError("canonical checkpoint root descriptor")
    cursor = Path(supplied_canonical.anchor)
    for component in supplied_canonical.parts[1:]:
        cursor /= component
        if cursor.is_symlink() or not cursor.is_dir():
            raise ValueError("checkpoint root nonsymlink ancestry")


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


def _validate_all_live_ids(value: object, prefix: str = "$") -> None:
    if type(value) is dict:
        for key, nested in value.items():
            if key.endswith("_id"):
                _live_id(nested, f"{prefix}.{key}")
            _validate_all_live_ids(nested, f"{prefix}.{key}")
    elif type(value) is list:
        for index, nested in enumerate(value):
            _validate_all_live_ids(nested, f"{prefix}[{index}]")


def _pinned_value(document: dict, name: str) -> object:
    if name in document:
        return document[name]
    for section in ("package", "primary", "secondary"):
        prefix = section + "_"
        if name.startswith(prefix) and name[len(prefix):] in document[section]:
            return document[section][name[len(prefix):]]
    if name in document["context"]:
        return document["context"][name]
    if name in document["limits"]:
        return document["limits"][name]
    raise ValueError(f"pinned value has no authorization field: {name}")


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
    for name, expected in interface["pinned_values"].items():
        if type(_pinned_value(document, name)) is not type(expected) or _pinned_value(document, name) != expected:
            raise ValueError(f"pinned authorization value: {name}")
    _validate_all_live_ids(document)
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
    if not _typed_equal(document["context"], interface["pinned_context"]) or not _typed_equal(document["limits"], interface["pinned_limits"]):
        raise ValueError("context or limits binding")
    validate_authority_bindings(document, interface, interface_path)
    if require_installed:
        if installation_receipt_path is None:
            raise ValueError("installation receipt required")
        canonical = Path(document["canonical_install_path"])
        if authorization_path.resolve(strict=True) != canonical:
            raise ValueError("canonical installation path")
        receipt_data = read_regular_nofollow(installation_receipt_path)
        receipt = strict_bytes(receipt_data)
        if set(receipt) != {"schema", "bindings", "payload"} or receipt["schema"] != "pulsarmlx.f017.corrected-oracle-authorization-installation-receipt/6.0.0":
            raise ValueError("installation receipt census")
        receipt_bindings = receipt["bindings"]
        receipt_payload = receipt["payload"]
        if receipt_payload.get("result") != "PASS":
            raise ValueError("installation receipt result")
        if (
            receipt_bindings["authorization_id"] != document["authorization_id"]
            or receipt_bindings["package_attempt_id"] != document["package_attempt_id"]
            or receipt_bindings["primary_event_id"] != document["primary_event_id"]
            or receipt_bindings["secondary_event_id"] != document["secondary_event_id"]
            or receipt_bindings["operator_approval_sha256"] != document["operator_approval_sha256"]
        ):
            raise ValueError("installation receipt identity")
        if receipt_payload["installed_authorization_sha256"] != hashlib.sha256(data).hexdigest() or receipt_payload["candidate_install_byte_identity"] is not True:
            raise ValueError("installed authorization readback")
    return ParsedAuthorization(document, hashlib.sha256(data).hexdigest(), role, grant)
