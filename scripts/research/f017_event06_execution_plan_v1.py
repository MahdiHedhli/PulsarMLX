#!/usr/bin/env python3
"""Closed, sealed Event 06 execution plan for the V12-to-V11 bridge."""
from __future__ import annotations

import copy
import hashlib
import re
from types import MappingProxyType

from f017_canonical_serialization_v10 import canonical_bytes

SCHEMA = "pulsarmlx.f017.event06-v12-execution-plan/1.0.0"
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
ID = re.compile(r"[A-Z0-9](?:[A-Z0-9-]{0,190}[A-Z0-9])?")
KEYS = {
    "schema", "package_attempt_id", "primary_event_id", "secondary_event_id",
    "event_identity_plan_sha256", "source_head", "source_tree",
    "implementation_measurement_sha256", "tensor_catalog_path", "tensor_catalog_sha256",
    "primary_numerical_sha256", "secondary_numerical_sha256",
    "numerical_contract_path", "numerical_contract_sha256",
    "result_authority_path", "result_authority_sha256",
    "result_bundle_builder_sha256", "comparison_authority_sha256",
    "release_authority_sha256", "accounting_authority_sha256",
    "primary_target_source_sha256", "secondary_target_source_sha256",
    "shards", "attempts", "retries", "resume",
}
SHA_KEYS = {key for key in KEYS if key.endswith("_sha256")}
PATH_KEYS = {"tensor_catalog_path", "numerical_contract_path", "result_authority_path"}
SHARD_KEYS = {"filename", "size_bytes", "sha256", "role"}
_SEAL = object()


def _freeze(value):
    if type(value) is dict:
        return tuple((key, _freeze(value[key])) for key in sorted(value))
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value):
    if type(value) is tuple:
        if value and all(type(item) is tuple and len(item) == 2 and type(item[0]) is str for item in value):
            return {key: _thaw(item) for key, item in value}
        return [_thaw(item) for item in value]
    return value


class ValidatedExecutionPlan:
    __slots__ = ("_items", "sha256")

    def __new__(cls, seal=None, value=None):
        if seal is not _SEAL:
            raise TypeError("validated execution plans are validator-created")
        return super().__new__(cls)

    def __init__(self, seal, value):
        self._items = _freeze(value)
        self.sha256 = hashlib.sha256(canonical_bytes(value)).hexdigest()

    def get(self, key: str):
        for name, value in self._items:
            if name == key:
                return _thaw(value)
        raise KeyError(key)

    def immutable_view(self):
        return MappingProxyType({name: _freeze(value) for name, value in self._items})

    def __copy__(self):
        raise TypeError("validated execution plans cannot be copied")

    def __deepcopy__(self, memo):
        raise TypeError("validated execution plans cannot be copied")

    def __reduce_ex__(self, protocol):
        raise TypeError("validated execution plans cannot be pickled")


def _repo_path(value, name: str) -> None:
    if type(value) is not str or not value or value.startswith("/") or "\\" in value:
        raise ValueError(f"execution plan path: {name}")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError(f"execution plan path: {name}")


def validate_execution_plan(value: object) -> ValidatedExecutionPlan:
    if type(value) is not dict or set(value) != KEYS:
        raise ValueError("execution plan key census")
    if value["schema"] != SCHEMA:
        raise ValueError("execution plan schema")
    for key in ("package_attempt_id", "primary_event_id", "secondary_event_id"):
        if type(value[key]) is not str or ID.fullmatch(value[key]) is None:
            raise ValueError(f"execution plan identity: {key}")
    if len({value["package_attempt_id"], value["primary_event_id"], value["secondary_event_id"]}) != 3:
        raise ValueError("execution plan distinct identities")
    if type(value["source_head"]) is not str or HEX40.fullmatch(value["source_head"]) is None:
        raise ValueError("execution plan source head")
    if type(value["source_tree"]) is not str or HEX40.fullmatch(value["source_tree"]) is None:
        raise ValueError("execution plan source tree")
    for key in SHA_KEYS:
        if type(value[key]) is not str or HEX64.fullmatch(value[key]) is None:
            raise ValueError(f"execution plan SHA: {key}")
    for key in PATH_KEYS:
        _repo_path(value[key], key)
    shards = value["shards"]
    if type(shards) is not list or len(shards) != 6:
        raise ValueError("execution plan shard census")
    for ordinal, shard in enumerate(shards, start=1):
        if type(shard) is not dict or set(shard) != SHARD_KEYS:
            raise ValueError("execution plan shard keys")
        if (type(shard["filename"]) is not str or not shard["filename"]
                or "/" in shard["filename"] or "\\" in shard["filename"]):
            raise ValueError("execution plan shard filename")
        if type(shard["size_bytes"]) is not int or shard["size_bytes"] < 0:
            raise ValueError("execution plan shard size")
        if type(shard["sha256"]) is not str or HEX64.fullmatch(shard["sha256"]) is None:
            raise ValueError("execution plan shard SHA")
        expected_role = "IDENTITY_ONLY" if ordinal == 1 else "GRAPH_PAYLOAD"
        if shard["role"] != expected_role:
            raise ValueError("execution plan shard role")
    if (type(value["attempts"]) is not int or type(value["attempts"]) is bool or value["attempts"] != 1
            or type(value["retries"]) is not int or type(value["retries"]) is bool or value["retries"] != 0
            or value["resume"] is not False):
        raise ValueError("execution plan one-shot limits")
    return ValidatedExecutionPlan(_SEAL, value)


def reconstruct_execution_plan(raw: bytes) -> ValidatedExecutionPlan:
    from f017_bounded_artifact_decode_v1 import parse_artifact_bytes
    value = parse_artifact_bytes(raw)
    plan = validate_execution_plan(value)
    if canonical_bytes(value) != raw:
        raise ValueError("execution plan canonical bytes")
    return plan
