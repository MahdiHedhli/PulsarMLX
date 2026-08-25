#!/usr/bin/env python3
"""Strict V10 authorization model with separate rehearsal and future-live postures."""
from __future__ import annotations

import re
from pathlib import Path

from f017_bounded_artifact_decode_v1 import ArtifactLimits, DEFAULT_LIMITS, parse_artifact_bytes, read_artifact
from f017_canonical_serialization_v10 import sha256_bytes, strict_bytes
from f017_memory_gate_v9 import MAX_AGE_NS, THRESHOLD_BYTES, validate_observation


SCHEMA = "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/10.0.0"
KEYS = {"schema", "state", "live", "scope", "authority_generation", "authorization_id", "package_attempt_id",
        "primary_event_id", "secondary_event_id", "causal_dag_sha256", "numerical_contract_sha256",
        "primary_numerical_sha256", "secondary_numerical_sha256", "checkpoint_root", "shards", "attempts",
        "retries", "resume", "active_generation", "synthetic_root_manifest_path", "synthetic_root_manifest_sha256",
        "tensor_catalog_path", "tensor_catalog_sha256", "mint_memory_gate"}
LIVE_KEYS = KEYS | {"operator_approval_path", "operator_approval_sha256", "canonical_authorization_path",
                    "installation_receipt_path", "emergency_evidence_root", "authority_manifest_sha256",
                    "terminal_fallback_evidence_root",
                    "execution_readiness_declaration_path", "execution_readiness_declaration_sha256"}
ID_PATTERN = re.compile(r"[A-Z0-9](?:[A-Z0-9-]{0,126}[A-Z0-9])?")
ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT_METADATA = ROOT / "docs/validation/glm52-checkpoint.json"


def _memory_gate(value: object, *, live_posture: bool) -> None:
    keys = {"result", "enforced", "threshold_bytes", "sample_age_ns", "observation"}
    if type(value) is not dict or set(value) != keys or type(value["observation"]) is not dict:
        raise ValueError("mint memory gate census")
    if (type(value["threshold_bytes"]) is not int or value["threshold_bytes"] != THRESHOLD_BYTES
            or type(value["sample_age_ns"]) is not int or not 0 <= value["sample_age_ns"] <= MAX_AGE_NS):
        raise ValueError("mint memory gate scalar binding")
    observation = value["observation"]
    if live_posture:
        if value["result"] != "PASS" or value["enforced"] is not True:
            raise ValueError("live mint memory gate posture")
        # Durable bytes attest the threshold at mint.  Freshness is enforced
        # when observe(enforce=True) creates the sample and again from a new
        # sample before package claim; immutable authority bytes do not expire.
        validate_observation(observation, now_ns=observation.get("observed_at_unix_ns"), enforce=True)
    else:
        if value["enforced"] is not False:
            raise ValueError("rehearsal memory gate posture")
        validate_observation(observation, enforce=False)


def production_shards() -> list[dict]:
    metadata = read_artifact(
        CHECKPOINT_METADATA,
        limits=ArtifactLimits(**{**DEFAULT_LIMITS.__dict__, "require_canonical_bytes": False}),
    )
    if type(metadata) is not dict or metadata.get("file_count") != 6 or type(metadata.get("files")) is not list:
        raise ValueError("checkpoint metadata authority")
    return [{"filename": item["filename"], "size_bytes": item["size_bytes"], "sha256": item["sha256"],
             "role": "IDENTITY_ONLY" if ordinal == 1 else "GRAPH_PAYLOAD"}
            for ordinal, item in enumerate(metadata["files"], start=1)]


def _identifier(value: object, name: str) -> str:
    if type(value) is not str or ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"invalid {name}")
    return value


def parse_candidate_bytes(raw: bytes) -> dict:
    value = parse_artifact_bytes(raw)
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
    if value["active_generation"] != "V10":
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
    if live_posture and value["shards"] != production_shards():
        raise ValueError("live checkpoint shard authority")
    if live_posture:
        if value["synthetic_root_manifest_path"] is not None or value["synthetic_root_manifest_sha256"] is not None:
            raise ValueError("live authority must not carry synthetic authority")
        for name in ("operator_approval_path", "canonical_authorization_path", "installation_receipt_path",
                     "emergency_evidence_root", "terminal_fallback_evidence_root",
                     "execution_readiness_declaration_path"):
            if type(value[name]) is not str or not Path(value[name]).is_absolute():
                raise ValueError(f"live authority path: {name}")
        for name in ("operator_approval_sha256", "authority_manifest_sha256", "execution_readiness_declaration_sha256"):
            if type(value[name]) is not str or re.fullmatch(r"[0-9a-f]{64}", value[name]) is None:
                raise ValueError(f"live authority digest: {name}")
        _memory_gate(value["mint_memory_gate"], live_posture=True)
    elif value["scope"] == "SYNTHETIC_QUALIFICATION":
        if type(value["synthetic_root_manifest_path"]) is not str or type(value["synthetic_root_manifest_sha256"]) is not str or re.fullmatch(r"[0-9a-f]{64}", value["synthetic_root_manifest_sha256"]) is None:
            raise ValueError("synthetic root authority")
        _memory_gate(value["mint_memory_gate"], live_posture=False)
    else:
        if value["synthetic_root_manifest_path"] is not None or value["synthetic_root_manifest_sha256"] is not None:
            raise ValueError("shadow must not carry synthetic root authority")
        # A shadow rehearsal records the host observation but cannot claim that
        # an undersized CI runner is a production execution machine.  Live
        # production authority (introduced only under a future operator GO)
        # must use the separately enforced production posture.
        _memory_gate(value["mint_memory_gate"], live_posture=False)
    return value


def parse_candidate(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes(); return parse_candidate_bytes(raw), sha256_bytes(raw)
