#!/usr/bin/env python3
"""Strict V9 authorization model with separate rehearsal and future-live postures."""
from __future__ import annotations

import re
from pathlib import Path

from f017_canonical_serialization_v8 import sha256_bytes, strict_bytes
from f017_memory_gate_v9 import validate_observation


SCHEMA = "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/9.0.0"
KEYS = {"schema", "state", "live", "scope", "authority_generation", "authorization_id", "package_attempt_id",
        "primary_event_id", "secondary_event_id", "causal_dag_sha256", "numerical_contract_sha256",
        "primary_numerical_sha256", "secondary_numerical_sha256", "checkpoint_root", "shards", "attempts",
        "retries", "resume", "active_generation", "synthetic_root_manifest_path", "synthetic_root_manifest_sha256",
        "tensor_catalog_path", "tensor_catalog_sha256", "mint_memory_gate"}
LIVE_KEYS = KEYS | {"operator_approval_path", "operator_approval_sha256", "canonical_authorization_path",
                    "installation_receipt_path", "emergency_evidence_root", "authority_manifest_sha256",
                    "execution_readiness_declaration_path", "execution_readiness_declaration_sha256"}
ID_PATTERN = re.compile(r"[A-Z0-9](?:[A-Z0-9-]{0,126}[A-Z0-9])?")


def _identifier(value: object, name: str) -> str:
    if type(value) is not str or ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"invalid {name}")
    return value


def parse_candidate_bytes(raw: bytes) -> dict:
    value = strict_bytes(raw)
    if type(value) is not dict or set(value) not in (KEYS, LIVE_KEYS):
        raise ValueError("authorization key census")
    live_posture = set(value) == LIVE_KEYS
    if value["schema"] != SCHEMA or value["authority_generation"] != 9:
        raise ValueError("authorization generation")
    if live_posture:
        # Candidate bytes never assert authority themselves.  Canonical
        # no-replace installation plus a bound receipt activates these exact
        # bytes under a future operator GO.
        if value["state"] != "OPERATOR_APPROVED_CANDIDATE" or value["live"] is not False or value["scope"] != "PRODUCTION_EVENT_04":
            raise ValueError("future-live candidate posture")
    elif value["state"] != "REHEARSAL_CANDIDATE" or value["live"] is not False:
        raise ValueError("rehearsal authorization posture")
    if value["scope"] not in {"SYNTHETIC_QUALIFICATION", "PRODUCTION_SHADOW_NO_ACCESS", "PRODUCTION_EVENT_04"}:
        raise ValueError("authorization scope")
    if type(value["attempts"]) is not int or value["attempts"] != 1 or type(value["retries"]) is not int or value["retries"] != 0 or value["resume"] is not False:
        raise ValueError("lifecycle limits")
    if value["active_generation"] != "V9":
        raise ValueError("active generation")
    identities = [_identifier(value[key], key) for key in ("authorization_id", "package_attempt_id", "primary_event_id", "secondary_event_id")]
    if len(set(identities)) != 4:
        raise ValueError("identity uniqueness")
    if live_posture and any(marker in identity for identity in identities for marker in ("INERT", "FIXTURE", "TEST", "SYNTHETIC", "REHEARSAL", "QUAL", "SHADOW")):
        raise ValueError("live identity marker")
    for name in ("causal_dag_sha256", "numerical_contract_sha256", "primary_numerical_sha256", "secondary_numerical_sha256", "tensor_catalog_sha256"):
        if type(value[name]) is not str or re.fullmatch(r"[0-9a-f]{64}", value[name]) is None:
            raise ValueError(f"authority digest: {name}")
    if type(value["checkpoint_root"]) is not str or type(value["tensor_catalog_path"]) is not str:
        raise ValueError("authority path type")
    if type(value["shards"]) is not list or len(value["shards"]) != 6:
        raise ValueError("shard census")
    expected = {"filename", "size_bytes", "sha256", "role"}
    for ordinal, shard in enumerate(value["shards"], start=1):
        if type(shard) is not dict or set(shard) != expected or type(shard["filename"]) is not str or "/" in shard["filename"] or "\\" in shard["filename"]:
            raise ValueError("shard descriptor")
        if type(shard["size_bytes"]) is not int or shard["size_bytes"] < 0 or type(shard["sha256"]) is not str or re.fullmatch(r"[0-9a-f]{64}", shard["sha256"]) is None:
            raise ValueError("shard scalar")
        if shard["role"] != ("IDENTITY_ONLY" if ordinal == 1 else "GRAPH_PAYLOAD"):
            raise ValueError("shard role")
    if live_posture:
        if value["synthetic_root_manifest_path"] is not None or value["synthetic_root_manifest_sha256"] is not None:
            raise ValueError("live authority must not carry synthetic authority")
        for name in ("operator_approval_path", "canonical_authorization_path", "installation_receipt_path",
                     "emergency_evidence_root", "execution_readiness_declaration_path"):
            if type(value[name]) is not str or not Path(value[name]).is_absolute():
                raise ValueError(f"live authority path: {name}")
        for name in ("operator_approval_sha256", "authority_manifest_sha256", "execution_readiness_declaration_sha256"):
            if type(value[name]) is not str or re.fullmatch(r"[0-9a-f]{64}", value[name]) is None:
                raise ValueError(f"live authority digest: {name}")
        validate_observation(value["mint_memory_gate"]["observation"], enforce=True)
    elif value["scope"] == "SYNTHETIC_QUALIFICATION":
        if type(value["synthetic_root_manifest_path"]) is not str or type(value["synthetic_root_manifest_sha256"]) is not str or re.fullmatch(r"[0-9a-f]{64}", value["synthetic_root_manifest_sha256"]) is None:
            raise ValueError("synthetic root authority")
        validate_observation(value["mint_memory_gate"]["observation"], enforce=False)
    else:
        if value["synthetic_root_manifest_path"] is not None or value["synthetic_root_manifest_sha256"] is not None:
            raise ValueError("shadow must not carry synthetic root authority")
        # A shadow rehearsal records the host observation but cannot claim that
        # an undersized CI runner is a production execution machine.  Live
        # production authority (introduced only under a future operator GO)
        # must use the separately enforced production posture.
        validate_observation(value["mint_memory_gate"]["observation"], enforce=False)
    return value


def parse_candidate(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes(); return parse_candidate_bytes(raw), sha256_bytes(raw)
