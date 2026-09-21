#!/usr/bin/env python3
"""Strict, non-numerical authorization interface for corrected-oracle v3.

This module deliberately contains no model graph, decoder, tensor reader, or
checkpoint payload access.  It is shared only to make the producer/consumer
authorization boundary exact; each consumer still applies role-specific
identity checks in its own entry point.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/3.0.0"
INTERFACE_SCHEMA = "pulsarmlx.f017.corrected-oracle-authorization-consumer-interface/1.0.0"
CONTRACT_SCHEMA = "pulsarmlx.f017.corrected-full-checkpoint-oracle-scientific-access-contract/3.0.0"
PRIMARY_ROLE = "INDEPENDENT_CPU_REFERENCE"
SECONDARY_ROLE = "INDEPENDENT_ACCELERATED_CROSS_CHECK"
HEX = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
SAFE_ID = re.compile(r"[A-Z0-9][A-Z0-9-]{1,126}[A-Z0-9]\Z", re.ASCII)
FORBIDDEN_LIVE_ID_PARTS = ("INERT", "FIXTURE", "TEST", "SYNTHETIC")

AUTH_KEYS = frozenset({
    "schema", "state", "live", "authority_scope", "authorization_id",
    "branch", "implementation_head", "contract_sha256", "interface_sha256",
    "authorizer_sha256", "event_coordinator_sha256", "memory_observer_sha256",
    "memory_parser_contract_sha256", "geometry_sha256", "numerical_contract_sha256",
    "synthetic_qualification_sha256", "checkpoint_root", "checkpoint_manifest_sha256",
    "checkpoint_catalog_path", "checkpoint_catalog_sha256", "checkpoint_set_sha256",
    "shards", "prompt_token", "position", "top_n", "attempts", "retries", "resume",
    "consumers", "package_state_root", "package_output_root", "primary", "secondary",
    "historical_master_ledger_sha256", "historical_master_terminal",
    "historical_master_delta", "event_accounting", "p1_authority",
    "operator_approval_sha256", "memory_preflight_sha256",
    "memory_observed_at_unix_ns", "memory_available_bytes", "candidate_nonce",
})

GRANT_KEYS = frozenset({
    "role", "event_id", "producer_path", "producer_sha256", "decoder_path",
    "decoder_sha256", "state_root", "output_root", "attempts", "retries", "resume",
})

ACCOUNTING_KEYS = frozenset({
    "package_attempt_delta_on_durable_start",
    "primary_event_delta_on_durable_start",
    "secondary_event_delta_on_durable_start",
    "authorization_mint_delta",
    "unstarted_consumer_delta",
})

SHARD_KEYS = frozenset({"filename", "size_bytes", "sha256", "access_role"})


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_bytes(data: bytes) -> dict[str, Any]:
    if len(data) > 1_048_576:
        raise ValueError("authorization exceeds one MiB")
    value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs)
    if not isinstance(value, dict):
        raise ValueError("authorization must be an object")
    return value


def read_regular_nofollow(path: Path, maximum: int = 1_048_576) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise ValueError("bounded regular file required")
        data = os.read(descriptor, info.st_size)
        if len(data) != info.st_size or os.read(descriptor, 1):
            raise ValueError("exact file read required")
        return data
    finally:
        os.close(descriptor)


def strict_path(path: Path) -> dict[str, Any]:
    return strict_bytes(read_regular_nofollow(path))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("regular authority file required")
        offset = 0
        while offset < info.st_size:
            chunk = os.pread(descriptor, min(1024 * 1024, info.st_size - offset), offset)
            if not chunk:
                raise ValueError("short authority read")
            digest.update(chunk)
            offset += len(chunk)
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def canonical_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _exact_keys(value: Any, expected: frozenset[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{name} key census")
    return value


def _plain_int(value: Any, name: str, minimum: int | None = None) -> int:
    if type(value) is not int or (minimum is not None and value < minimum):
        raise ValueError(f"{name} integer")
    return value


def _plain_bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} boolean")
    return value


def _hash(value: Any, name: str, allow_zero: bool = False) -> str:
    if not isinstance(value, str) or not HEX.fullmatch(value):
        raise ValueError(f"{name} hash")
    if not allow_zero and value == "0" * 64:
        raise ValueError(f"{name} zero hash")
    return value


def _safe_id(value: Any, name: str, *, live: bool) -> str:
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise ValueError(f"{name} identifier")
    if live and any(part in value for part in FORBIDDEN_LIVE_ID_PARTS):
        raise ValueError(f"{name} live identifier contains prohibited marker")
    return value


def _no_symlink_ancestry(path: Path, *, leaf_may_be_absent: bool) -> Path:
    if not path.is_absolute():
        raise ValueError("absolute path required")
    probe = path.parent if leaf_may_be_absent else path
    resolved = probe.resolve(strict=True)
    if resolved != probe:
        raise ValueError("canonical path required")
    for item in (probe, *probe.parents):
        if item.is_symlink():
            raise ValueError("symlink ancestry prohibited")
    if leaf_may_be_absent and (path.exists() or path.is_symlink()):
        raise ValueError("unused root required")
    return path


@dataclass(frozen=True)
class ConsumerGrant:
    role: str
    event_id: str
    producer_path: str
    producer_sha256: str
    decoder_path: str
    decoder_sha256: str
    state_root: str
    output_root: str
    attempts: int
    retries: int
    resume: bool


@dataclass(frozen=True)
class Authorization:
    document: dict[str, Any]
    primary: ConsumerGrant
    secondary: ConsumerGrant
    sha256: str


def _grant(value: Any, expected_role: str, *, live: bool) -> ConsumerGrant:
    item = _exact_keys(value, GRANT_KEYS, f"{expected_role} grant")
    if item["role"] != expected_role:
        raise ValueError("consumer role")
    _safe_id(item["event_id"], "consumer event", live=live)
    for key in ("producer_path", "decoder_path"):
        if not isinstance(item[key], str) or not item[key] or Path(item[key]).is_absolute():
            raise ValueError(f"{key} relative path")
    _hash(item["producer_sha256"], "producer")
    _hash(item["decoder_sha256"], "decoder")
    if _plain_int(item["attempts"], "consumer attempts", 0) != 1 or _plain_int(item["retries"], "consumer retries", 0) != 0 or _plain_bool(item["resume"], "resume"):
        raise ValueError("consumer one-shot lifecycle")
    if live:
        state, output = Path(item["state_root"]), Path(item["output_root"])
        if not state.is_absolute() or not output.is_absolute() or state.is_symlink() or output.is_symlink():
            raise ValueError("absolute non-symlink consumer roots required")
        if state != output:
            raise ValueError("consumer state/output root mismatch")
    elif item["state_root"] != "INERT_NO_STATE_ROOT" or item["output_root"] != "INERT_NO_OUTPUT_ROOT":
        raise ValueError("inert consumer roots")
    return ConsumerGrant(**item)


def validate_document(document: dict[str, Any], contract: dict[str, Any], repo: Path,
                      *, require_live: bool, expected_scope: str | None = None,
                      contract_sha256: str | None = None,
                      root_phase: str = "PRE_MINT_OR_HANDSHAKE") -> Authorization:
    auth = _exact_keys(document, AUTH_KEYS, "authorization")
    if auth["schema"] != SCHEMA or contract.get("schema") != CONTRACT_SCHEMA:
        raise ValueError("authorization/contract schema")
    live = _plain_bool(auth["live"], "live")
    if auth["state"] not in {"INERT_FIXTURE", "AUTHORIZED"} or live != (auth["state"] == "AUTHORIZED"):
        raise ValueError("authorization state")
    if require_live and not live:
        raise ValueError("live authority required")
    if auth["authority_scope"] not in {"PRODUCTION", "SYNTHETIC_QUALIFICATION"}:
        raise ValueError("authority scope")
    if expected_scope is not None and auth["authority_scope"] != expected_scope:
        raise ValueError("authority scope mismatch")
    _safe_id(auth["authorization_id"], "authorization", live=live)
    if _plain_int(auth["attempts"], "attempts", 0) != 1 or _plain_int(auth["retries"], "retries", 0) != 0 or _plain_bool(auth["resume"], "resume"):
        raise ValueError("package one-shot lifecycle")
    context = contract["context"]
    if auth["prompt_token"] != context["prompt_token"] or auth["position"] != context["position"] or auth["top_n"] != context["top_n"]:
        raise ValueError("context authority")
    if auth["consumers"] != [PRIMARY_ROLE, SECONDARY_ROLE]:
        raise ValueError("consumer census/order")
    if auth["p1_authority"] != "PROHIBITED":
        raise ValueError("P1 boundary")
    if not isinstance(auth["branch"], str) or not re.fullmatch(r"[0-9a-f]{40}", auth["implementation_head"]):
        raise ValueError("Git authority")
    for key in (
        "contract_sha256", "interface_sha256", "authorizer_sha256", "event_coordinator_sha256",
        "memory_observer_sha256", "memory_parser_contract_sha256", "geometry_sha256",
        "numerical_contract_sha256", "synthetic_qualification_sha256", "checkpoint_manifest_sha256",
        "checkpoint_catalog_sha256", "checkpoint_set_sha256", "historical_master_ledger_sha256",
    ):
        _hash(auth[key], key)
    _hash(auth["operator_approval_sha256"], "operator approval", allow_zero=not live)
    _hash(auth["memory_preflight_sha256"], "memory preflight", allow_zero=not live)
    _hash(auth["candidate_nonce"], "candidate nonce")
    if auth["historical_master_terminal"] != 175 or auth["historical_master_delta"] != 0:
        raise ValueError("historical ledger")
    accounting = _exact_keys(auth["event_accounting"], ACCOUNTING_KEYS, "event accounting")
    for key, expected in (
        ("authorization_mint_delta", 0), ("package_attempt_delta_on_durable_start", 1),
        ("primary_event_delta_on_durable_start", 1), ("secondary_event_delta_on_durable_start", 1),
        ("unstarted_consumer_delta", 0),
    ):
        if _plain_int(accounting[key], key, 0) != expected:
            raise ValueError("event accounting semantics")
    primary = _grant(auth["primary"], PRIMARY_ROLE, live=live)
    secondary = _grant(auth["secondary"], SECONDARY_ROLE, live=live)
    for name, grant in (("primary", primary), ("secondary", secondary)):
        binding = contract["bindings"][name]
        decoder_binding = contract["bindings"]["primary_decoders" if name == "primary" else "secondary_decoder_authority"]
        if grant.producer_path != binding["path"] or grant.producer_sha256 != binding["sha256"]:
            raise ValueError(f"{name} producer contract binding")
        if grant.decoder_path != decoder_binding["path"] or grant.decoder_sha256 != decoder_binding["sha256"]:
            raise ValueError(f"{name} decoder contract binding")
    if primary.event_id == secondary.event_id:
        raise ValueError("consumer event identities must differ")
    if live:
        if root_phase not in {"PRE_MINT_OR_HANDSHAKE", "POST_PACKAGE_START"}:
            raise ValueError("root validation phase")
        package_path = Path(auth["package_state_root"])
        if root_phase == "PRE_MINT_OR_HANDSHAKE":
            package_state = _no_symlink_ancestry(package_path, leaf_may_be_absent=True)
            for consumer_root in (Path(primary.state_root), Path(secondary.state_root)):
                if consumer_root.exists() or consumer_root.is_symlink():
                    raise ValueError("unused consumer root required")
        else:
            package_state = _no_symlink_ancestry(package_path, leaf_may_be_absent=False)
            if not package_state.is_dir():
                raise ValueError("owned package root directory")
            for consumer_root in (Path(primary.state_root), Path(secondary.state_root)):
                if consumer_root.exists() and (not consumer_root.is_dir() or consumer_root.is_symlink()):
                    raise ValueError("owned consumer root directory")
        package_output = Path(auth["package_output_root"])
        if package_state != package_output:
            raise ValueError("package state/output mismatch")
        if Path(primary.state_root).parent != package_state or Path(secondary.state_root).parent != package_state:
            raise ValueError("consumer roots not bound beneath package root")
        if primary.state_root == secondary.state_root:
            raise ValueError("consumer roots must differ")
        root = _no_symlink_ancestry(Path(auth["checkpoint_root"]), leaf_may_be_absent=False)
        if not root.is_dir():
            raise ValueError("checkpoint root directory")
    else:
        for key, expected in (
            ("checkpoint_root", "INERT_NO_CHECKPOINT_PATH"),
            ("package_state_root", "INERT_NO_STATE_ROOT"),
            ("package_output_root", "INERT_NO_OUTPUT_ROOT"),
        ):
            if auth[key] != expected:
                raise ValueError("inert root boundary")
    if not isinstance(auth["checkpoint_catalog_path"], str) or Path(auth["checkpoint_catalog_path"]).is_absolute():
        raise ValueError("catalog relative path")
    catalog = repo / auth["checkpoint_catalog_path"]
    if auth["authority_scope"] == "PRODUCTION":
        if not catalog.is_file() or catalog.is_symlink() or sha256_path(catalog) != auth["checkpoint_catalog_sha256"]:
            raise ValueError("production catalog identity")
    elif live:
        synthetic_catalog = Path(contract["qualification"]["synthetic_catalog_path"])
        if catalog.resolve(strict=True) != synthetic_catalog.resolve(strict=True) or sha256_path(catalog) != auth["checkpoint_catalog_sha256"]:
            raise ValueError("synthetic catalog identity")
        if Path(auth["checkpoint_root"]).resolve(strict=True) != Path(contract["qualification"]["synthetic_checkpoint_root"]).resolve(strict=True):
            raise ValueError("synthetic checkpoint root identity")
    shards = auth["shards"]
    if not isinstance(shards, list) or len(shards) != 6:
        raise ValueError("six-shard census")
    names: set[str] = set()
    for shard in shards:
        item = _exact_keys(shard, SHARD_KEYS, "shard")
        if not isinstance(item["filename"], str) or Path(item["filename"]).name != item["filename"]:
            raise ValueError("shard filename")
        if item["filename"] in names:
            raise ValueError("duplicate shard")
        names.add(item["filename"])
        _plain_int(item["size_bytes"], "shard size", 1)
        _hash(item["sha256"], "shard")
        if item["access_role"] not in {"GRAPH_PAYLOAD", "IDENTITY_ONLY"}:
            raise ValueError("shard access role")
    if live:
        for key in ("memory_observed_at_unix_ns", "memory_available_bytes"):
            _plain_int(auth[key], key, 1)
    else:
        if auth["memory_observed_at_unix_ns"] != 0 or auth["memory_available_bytes"] != 0:
            raise ValueError("inert memory boundary")
    expected = contract["authorization_bindings"]
    for key in (
        "interface_sha256", "authorizer_sha256", "event_coordinator_sha256",
        "memory_observer_sha256", "memory_parser_contract_sha256", "geometry_sha256",
        "numerical_contract_sha256", "synthetic_qualification_sha256", "checkpoint_manifest_sha256",
        "checkpoint_set_sha256", "historical_master_ledger_sha256",
    ):
        if auth[key] != expected[key]:
            raise ValueError(f"contract binding {key}")
    if auth["branch"] != contract["branch"] or auth["implementation_head"] != contract["implementation_head"]:
        raise ValueError("contract Git binding")
    if contract_sha256 is not None and auth["contract_sha256"] != contract_sha256:
        raise ValueError("contract self binding")
    if auth["authority_scope"] == "PRODUCTION" and auth["shards"] != contract["production_checkpoint"]["shards"]:
        raise ValueError("production shard binding")
    data = canonical_bytes(auth)
    return Authorization(auth, primary, secondary, sha256_bytes(data))


def validate_role(authority: Authorization, contract: dict[str, Any], repo: Path,
                  role: str, executing_path: Path) -> ConsumerGrant:
    grant = authority.primary if role == PRIMARY_ROLE else authority.secondary if role == SECONDARY_ROLE else None
    if grant is None or grant.role != role:
        raise ValueError("role-specific authority absent")
    executing = executing_path.resolve(strict=True)
    expected = (repo / grant.producer_path).resolve(strict=True)
    if executing != expected or sha256_path(executing) != grant.producer_sha256:
        raise ValueError("consumer producer identity")
    binding_name = "primary" if role == PRIMARY_ROLE else "secondary"
    binding = contract["bindings"][binding_name]
    if binding["path"] != grant.producer_path or binding["sha256"] != grant.producer_sha256:
        raise ValueError("consumer contract binding")
    decoder = repo / grant.decoder_path
    if not decoder.is_file() or decoder.is_symlink() or sha256_path(decoder) != grant.decoder_sha256:
        raise ValueError("consumer decoder identity")
    return grant


def load_and_validate(path: Path, contract_path: Path, repo: Path, *, require_live: bool,
                      role: str | None = None, executing_path: Path | None = None,
                      expected_scope: str | None = None,
                      root_phase: str = "PRE_MINT_OR_HANDSHAKE") -> Authorization:
    data = read_regular_nofollow(path)
    document = strict_bytes(data)
    contract = strict_path(contract_path)
    authority = validate_document(
        document, contract, repo, require_live=require_live, expected_scope=expected_scope,
        contract_sha256=sha256_path(contract_path), root_phase=root_phase,
    )
    if sha256_bytes(data) != authority.sha256:
        raise ValueError("authorization is not canonical serialized bytes")
    if role is not None:
        if executing_path is None:
            raise ValueError("executing consumer path required")
        validate_role(authority, contract, repo, role, executing_path)
    return authority
