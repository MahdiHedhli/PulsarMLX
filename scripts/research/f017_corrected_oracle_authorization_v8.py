#!/usr/bin/env python3
"""Strict, non-live V8 authorization candidate model."""
from __future__ import annotations

import re
from pathlib import Path

from f017_canonical_serialization_v8 import sha256_bytes, strict_bytes


SCHEMA = "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/8.0.0"
KEYS = {
    "schema", "state", "live", "synthetic_only", "authority_generation",
    "authorization_id", "package_attempt_id", "primary_event_id", "secondary_event_id",
    "causal_dag_sha256", "descriptor_scalar_contract_sha256", "numerical_contract_sha256",
    "primary_numerical_sha256", "secondary_numerical_sha256", "checkpoint_root",
    "shards", "attempts", "retries", "resume", "active_generation",
}
ID_PATTERN = re.compile(r"[A-Z0-9](?:[A-Z0-9-]{0,126}[A-Z0-9])?")
FORBIDDEN = ("INERT", "FIXTURE", "TEST", "SYNTHETIC")


def _live_id(value: object, name: str) -> str:
    if (type(value) is not str or ID_PATTERN.fullmatch(value) is None
            or any(marker in value for marker in FORBIDDEN)):
        raise ValueError(f"invalid {name}")
    return value


def parse_candidate_bytes(raw: bytes) -> dict:
    value = strict_bytes(raw)
    if type(value) is not dict or set(value) != KEYS:
        raise ValueError("authorization key census")
    if value["schema"] != SCHEMA or value["authority_generation"] != 8:
        raise ValueError("authorization schema")
    if value["state"] != "REHEARSAL_CANDIDATE" or value["live"] is not False or value["synthetic_only"] is not True:
        raise ValueError("candidate is not non-authoritative rehearsal bytes")
    if value["attempts"] != 1 or type(value["attempts"]) is not int or value["retries"] != 0 or type(value["retries"]) is not int or value["resume"] is not False:
        raise ValueError("lifecycle limits")
    if value["active_generation"] != "NONE":
        raise ValueError("live generation must remain inactive during qualification")
    identities = [_live_id(value[name], name) for name in ("authorization_id", "package_attempt_id", "primary_event_id", "secondary_event_id")]
    if len(set(identities)) != 4:
        raise ValueError("authorization identities not unique")
    for name in ("causal_dag_sha256", "descriptor_scalar_contract_sha256", "numerical_contract_sha256", "primary_numerical_sha256", "secondary_numerical_sha256"):
        if type(value[name]) is not str or re.fullmatch(r"[0-9a-f]{64}", value[name]) is None:
            raise ValueError(f"invalid authority digest: {name}")
    if type(value["checkpoint_root"]) is not str or type(value["shards"]) is not list or len(value["shards"]) != 6:
        raise ValueError("checkpoint descriptor census")
    expected_keys = {"filename", "size_bytes", "sha256", "role"}
    for ordinal, shard in enumerate(value["shards"], start=1):
        if type(shard) is not dict or set(shard) != expected_keys:
            raise ValueError("shard descriptor type or census")
        if type(shard["filename"]) is not str or "/" in shard["filename"] or "\\" in shard["filename"]:
            raise ValueError("shard filename")
        if type(shard["size_bytes"]) is not int or shard["size_bytes"] < 0:
            raise ValueError("shard size")
        if type(shard["sha256"]) is not str or re.fullmatch(r"[0-9a-f]{64}", shard["sha256"]) is None:
            raise ValueError("shard sha")
        expected_role = "IDENTITY_ONLY" if ordinal == 1 else "GRAPH_PAYLOAD"
        if shard["role"] != expected_role:
            raise ValueError("shard role")
    return value


def parse_candidate(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    return parse_candidate_bytes(raw), sha256_bytes(raw)
