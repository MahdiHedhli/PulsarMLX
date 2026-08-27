#!/usr/bin/env python3
"""Shared, side-effect-free Event-05 candidate construction authority."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import time
from types import MappingProxyType
from typing import Any, Mapping

from f017_bounded_artifact_decode_v1 import read_artifact
from f017_corrected_oracle_authorization_v11 import SCHEMA
from f017_event05_readiness_authority_v1 import ValidatedReadiness

APPROVAL_FIELDS = {
    "schema", "decision", "live", "approved_at_unix_ns", "approval_expires_at_unix_ns",
    "active_generation", "authorization_id", "package_attempt_id", "primary_event_id",
    "secondary_event_id", "checkpoint_root", "canonical_authorization_path",
    "installation_receipt_path", "emergency_evidence_root", "terminal_fallback_evidence_root",
    "authority_manifest_sha256", "readiness_declaration_sha256",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _exact_string(value: object) -> bool:
    return type(value) is str and bool(value)


def _sha256(value: object) -> bool:
    return type(value) is str and len(value) == 64 and value == value.lower() and all(c in "0123456789abcdef" for c in value)


@dataclass(frozen=True, slots=True)
class ValidatedApproval:
    values: Mapping[str, Any]
    source_path: Path
    source_sha256: str


@dataclass(frozen=True, slots=True)
class CandidateContext:
    causal_dag_sha256: str
    numerical_contract_sha256: str
    primary_numerical_sha256: str
    secondary_numerical_sha256: str
    result_authority_sha256: str
    implementation_measurement_sha256: str
    shards: tuple[dict, ...]
    tensor_catalog_path: str
    tensor_catalog_sha256: str


def validate_operator_approval(path: Path, expected_posture: str, *, now_ns: int | None = None) -> ValidatedApproval:
    value = read_artifact(path)
    if type(value) is not dict or set(value) != APPROVAL_FIELDS:
        raise ValueError("Event 05 approval key census")
    string_fields = APPROVAL_FIELDS - {"live", "approved_at_unix_ns", "approval_expires_at_unix_ns"}
    if any(not _exact_string(value[name]) for name in string_fields):
        raise ValueError("Event 05 approval field type")
    if type(value["live"]) is not bool or type(value["approved_at_unix_ns"]) is not int or type(value["approval_expires_at_unix_ns"]) is not int:
        raise ValueError("Event 05 approval field type")
    if not _sha256(value["authority_manifest_sha256"]) or not _sha256(value["readiness_declaration_sha256"]):
        raise ValueError("Event 05 approval SHA")
    if value["active_generation"] != "V11" or len({value["authorization_id"], value["package_attempt_id"], value["primary_event_id"], value["secondary_event_id"]}) != 4:
        raise ValueError("Event 05 approval identity")
    current = time.time_ns() if now_ns is None else now_ns
    if expected_posture == "VALIDATION_ONLY":
        valid = (value["schema"] == "pulsarmlx.f017.event05-readiness-validation-only-approval/1.0.0"
                 and value["decision"] == "VALIDATE_EVENT05_CANDIDATE_CONSTRUCTION_ONLY"
                 and value["live"] is False and value["approved_at_unix_ns"] == 0
                 and value["approval_expires_at_unix_ns"] == 0)
    elif expected_posture == "LIVE_OPERATOR_GO":
        valid = (value["schema"] == "pulsarmlx.f017.corrected-oracle-event05-operator-approval/11.1.0"
                 and value["decision"] == "GO_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_05"
                 and value["live"] is True and type(current) is int
                 and 0 < value["approved_at_unix_ns"] <= current < value["approval_expires_at_unix_ns"])
    else:
        raise ValueError("Event 05 approval posture")
    if not valid:
        raise ValueError("Event 05 approval posture")
    normalized = {name:value[name] for name in APPROVAL_FIELDS - {"schema", "decision", "live"}}
    return ValidatedApproval(MappingProxyType(normalized), path.resolve(strict=True), _sha(path))


def build_operator_go_candidate(approval: ValidatedApproval, readiness: ValidatedReadiness,
                                context: CandidateContext, memory_observation: Mapping[str, Any]) -> dict:
    """Build candidate bytes identically for validation-only and future live admission."""
    if not isinstance(approval, ValidatedApproval) or not isinstance(readiness, ValidatedReadiness):
        raise ValueError("Event 05 validated authority type")
    values = approval.values
    if (values["readiness_declaration_sha256"] != readiness.source_sha256
            or values["authority_manifest_sha256"] != readiness.authority_manifest_sha256):
        raise ValueError("Event 05 approval/readiness binding")
    hashes = (
        context.causal_dag_sha256, context.numerical_contract_sha256,
        context.primary_numerical_sha256, context.secondary_numerical_sha256,
        context.result_authority_sha256, context.implementation_measurement_sha256,
        context.tensor_catalog_sha256,
    )
    if any(not _sha256(item) for item in hashes) or type(context.shards) is not tuple:
        raise ValueError("Event 05 candidate context")
    if type(memory_observation) is not dict or memory_observation.get("result") != "PASS":
        raise ValueError("Event 05 memory observation")
    return {
        "schema":SCHEMA, "state":"OPERATOR_APPROVED_CANDIDATE", "live":False,
        "scope":"PRODUCTION_EVENT_05", "authority_generation":11,
        "authorization_id":values["authorization_id"], "package_attempt_id":values["package_attempt_id"],
        "primary_event_id":values["primary_event_id"], "secondary_event_id":values["secondary_event_id"],
        "causal_dag_sha256":context.causal_dag_sha256,
        "numerical_contract_sha256":context.numerical_contract_sha256,
        "primary_numerical_sha256":context.primary_numerical_sha256,
        "secondary_numerical_sha256":context.secondary_numerical_sha256,
        "result_authority_sha256":context.result_authority_sha256,
        "implementation_measurement_sha256":context.implementation_measurement_sha256,
        "checkpoint_root":values["checkpoint_root"], "shards":[dict(item) for item in context.shards],
        "attempts":1, "retries":0, "resume":False, "active_generation":"V11",
        "synthetic_root_manifest_path":None, "synthetic_root_manifest_sha256":None,
        "tensor_catalog_path":context.tensor_catalog_path, "tensor_catalog_sha256":context.tensor_catalog_sha256,
        "mint_memory_gate":dict(memory_observation),
        "operator_approval_path":str(approval.source_path), "operator_approval_sha256":approval.source_sha256,
        "canonical_authorization_path":values["canonical_authorization_path"],
        "installation_receipt_path":values["installation_receipt_path"],
        "emergency_evidence_root":values["emergency_evidence_root"],
        "terminal_fallback_evidence_root":values["terminal_fallback_evidence_root"],
        "authority_manifest_sha256":values["authority_manifest_sha256"],
        "execution_readiness_declaration_path":str(readiness.source_path),
        "execution_readiness_declaration_sha256":readiness.source_sha256,
    }
