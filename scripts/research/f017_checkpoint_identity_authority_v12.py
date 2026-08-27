#!/usr/bin/env python3
"""Strict typed V12 checkpoint-identity authority validation."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
from typing import Mapping

from f017_bounded_artifact_decode_v1 import parse_artifact_bytes
from f017_canonical_serialization_v10 import canonical_bytes, sha256_bytes
from f017_checkpoint_identity_lifecycle_v12 import failure

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_SCHEMA = "pulsarmlx.f017.corrected-oracle-checkpoint-identity-candidate-authority/12.1.0"
INSTALLED_SCHEMA = "pulsarmlx.f017.corrected-oracle-checkpoint-identity-installed-authority/12.1.0"
HEX64 = re.compile(r"[0-9a-f]{64}")
TYPED_ID = re.compile(r"[A-Z0-9](?:[A-Z0-9-]{0,190}[A-Z0-9])?")

CANDIDATE_KEYS = {
    "schema", "authority_scope", "operation_class", "generation",
    "authorization_id", "package_attempt_id", "checkpoint_set_sha256",
    "checkpoint_root", "checkpoint_identity_contract_path",
    "checkpoint_identity_contract_sha256", "producer_capability_path",
    "producer_capability_sha256", "measured_producer_path",
    "measured_producer_sha256", "primary_candidate_validator_path",
    "primary_candidate_validator_sha256", "secondary_candidate_validator_path",
    "secondary_candidate_validator_sha256", "identity_candidate_validator_path",
    "identity_candidate_validator_sha256", "expected_shard_count",
    "expected_identity_only_shard_count", "expected_graph_payload_shard_count",
    "expected_total_bytes", "attempts", "retries", "resume",
    "event_identity_plan_sha256",
}
INSTALLED_EXTRA_KEYS = {"installed_authorization_sha256", "installation_receipt_sha256"}
PATH_KEYS = {
    "checkpoint_identity_contract_path", "producer_capability_path",
    "measured_producer_path", "primary_candidate_validator_path",
    "secondary_candidate_validator_path", "identity_candidate_validator_path",
}
SHA_KEYS = {key for key in CANDIDATE_KEYS | INSTALLED_EXTRA_KEYS if key.endswith("_sha256")}
COUNT_KEYS = {
    "expected_shard_count", "expected_identity_only_shard_count",
    "expected_graph_payload_shard_count", "expected_total_bytes", "attempts", "retries",
}


@dataclass(frozen=True)
class ValidatedIdentityAuthority:
    """Immutable authority token. Runtime production accepts this type only."""

    items: tuple[tuple[str, object], ...]
    source_sha256: str
    posture: str

    def get(self, key: str) -> object:
        for name, value in self.items:
            if name == key:
                return value
        raise KeyError(key)

    def as_dict(self) -> dict:
        return dict(self.items)


def _repo_path(value: object) -> Path:
    if type(value) is not str or not value or value.startswith("/") or "\\" in value:
        raise ValueError("repository-relative path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("canonical repository-relative path")
    path = ROOT.joinpath(*pure.parts)
    if not path.is_file() or path.is_symlink():
        raise ValueError("bound repository file")
    return path


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contract(value: Mapping[str, object]) -> dict:
    contract_path = _repo_path(value["checkpoint_identity_contract_path"])
    if _sha(contract_path) != value["checkpoint_identity_contract_sha256"]:
        raise ValueError("checkpoint identity contract binding")
    contract = parse_artifact_bytes(contract_path.read_bytes())
    if type(contract) is not dict or type(contract.get("shards")) is not list:
        raise ValueError("checkpoint identity contract")
    shards = contract["shards"]
    if len(shards) != value["expected_shard_count"]:
        raise ValueError("checkpoint shard count")
    if [item.get("ordinal") for item in shards] != list(range(1, len(shards) + 1)):
        raise ValueError("checkpoint shard ordinals")
    identity = sum(item.get("role") == "IDENTITY_ONLY" for item in shards)
    graph = sum(item.get("role") == "GRAPH_PAYLOAD" for item in shards)
    total = sum(item.get("size_bytes", -1) for item in shards)
    if (identity != value["expected_identity_only_shard_count"]
            or graph != value["expected_graph_payload_shard_count"]
            or total != value["expected_total_bytes"]
            or contract.get("checkpoint_set_sha256") != value["checkpoint_set_sha256"]):
        raise ValueError("checkpoint census binding")
    return contract


def _validate(raw: bytes, *, installed: bool, expected: Mapping[str, object] | None) -> ValidatedIdentityAuthority:
    outcome = ("F017_V12_IDENTITY_INSTALLED_AUTHORITY_MISMATCH" if installed
               else "F017_V12_IDENTITY_CANDIDATE_AUTHORITY_MISMATCH")
    try:
        value = parse_artifact_bytes(raw)
        keys = CANDIDATE_KEYS | (INSTALLED_EXTRA_KEYS if installed else set())
        if type(value) is not dict or set(value) != keys:
            raise ValueError("authority key census")
        if value["schema"] != (INSTALLED_SCHEMA if installed else CANDIDATE_SCHEMA):
            raise ValueError("authority schema")
        if value["authority_scope"] not in {"SYNTHETIC", "PRODUCTION"}:
            raise ValueError("authority scope")
        expected_operation = ("CHECKPOINT_IDENTITY_QUALIFICATION" if value["authority_scope"] == "SYNTHETIC"
                              else "CORRECTED_FULL_CHECKPOINT_ORACLE")
        if value["operation_class"] != expected_operation or value["generation"] != "V12":
            raise ValueError("operation or generation")
        for key in ("authorization_id", "package_attempt_id"):
            if type(value[key]) is not str or TYPED_ID.fullmatch(value[key]) is None:
                raise ValueError(f"typed identity: {key}")
        if value["authorization_id"] == value["package_attempt_id"]:
            raise ValueError("distinct typed identities")
        for key in SHA_KEYS & keys:
            if type(value[key]) is not str or HEX64.fullmatch(value[key]) is None:
                raise ValueError(f"sha256 type: {key}")
        for key in COUNT_KEYS:
            if type(value[key]) is not int or value[key] < 0:
                raise ValueError(f"nonnegative integer: {key}")
        if value["attempts"] != 1 or value["retries"] != 0 or value["resume"] is not False:
            raise ValueError("one-shot limits")
        checkpoint_root = value["checkpoint_root"]
        if type(checkpoint_root) is not str or not checkpoint_root.startswith("/") or "/../" in checkpoint_root:
            raise ValueError("checkpoint root syntax")
        for key in PATH_KEYS:
            path = _repo_path(value[key])
            digest_key = key.removesuffix("_path") + "_sha256"
            if _sha(path) != value[digest_key]:
                raise ValueError(f"repository binding: {key}")
        contract = _contract(value)
        if contract.get("authority_scope") != value["authority_scope"]:
            raise ValueError("contract scope")
        if expected is not None:
            for key, expected_value in expected.items():
                if value.get(key) != expected_value:
                    raise ValueError(f"expected binding: {key}")
        if installed and value["installed_authorization_sha256"] == sha256_bytes(raw):
            raise ValueError("installed authority self reference")
        return ValidatedIdentityAuthority(tuple(sorted(value.items())), sha256_bytes(raw),
                                          "INSTALLED" if installed else "CANDIDATE")
    except Exception as exc:
        if hasattr(exc, "outcome_id"):
            raise
        raise failure(outcome, str(exc)) from exc


def validate_candidate_bytes(raw: bytes, expected: Mapping[str, object] | None = None) -> ValidatedIdentityAuthority:
    return _validate(raw, installed=False, expected=expected)


def validate_installed_bytes(raw: bytes, expected: Mapping[str, object] | None = None) -> ValidatedIdentityAuthority:
    return _validate(raw, installed=True, expected=expected)


def validate_candidate_path(path: Path, expected: Mapping[str, object] | None = None) -> ValidatedIdentityAuthority:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        raw = os.read(descriptor, 262_145)
        if os.read(descriptor, 1):
            raise failure("F017_V12_IDENTITY_CANDIDATE_AUTHORITY_MISMATCH", "authority bytes exceed bound")
    finally:
        os.close(descriptor)
    return validate_candidate_bytes(raw, expected)


def validate_installed_path(path: Path, expected: Mapping[str, object] | None = None) -> ValidatedIdentityAuthority:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        raw = os.read(descriptor, 262_145)
        if os.read(descriptor, 1):
            raise failure("F017_V12_IDENTITY_INSTALLED_AUTHORITY_MISMATCH", "authority bytes exceed bound")
    finally:
        os.close(descriptor)
    return validate_installed_bytes(raw, expected)


def installed_document(candidate: ValidatedIdentityAuthority, installation_receipt_sha256: str) -> dict:
    if type(candidate) is not ValidatedIdentityAuthority or candidate.posture != "CANDIDATE":
        raise failure("F017_V12_IDENTITY_INSTALLED_AUTHORITY_MISMATCH", "candidate authority type")
    if type(installation_receipt_sha256) is not str or HEX64.fullmatch(installation_receipt_sha256) is None:
        raise failure("F017_V12_IDENTITY_INSTALLED_AUTHORITY_MISMATCH", "installation receipt digest")
    value = candidate.as_dict()
    value["schema"] = INSTALLED_SCHEMA
    value["installed_authorization_sha256"] = candidate.source_sha256
    value["installation_receipt_sha256"] = installation_receipt_sha256
    return value


def canonical_candidate(value: Mapping[str, object]) -> bytes:
    raw = canonical_bytes(dict(value))
    validate_candidate_bytes(raw)
    return raw
