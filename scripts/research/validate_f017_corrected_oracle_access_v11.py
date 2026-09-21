#!/usr/bin/env python3
"""Two-phase, one-shot V11 Event-05 authorizer and no-access rehearsal path."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from f017_bounded_artifact_decode_v1 import read_artifact
from f017_canonical_serialization_v10 import bank_exclusive, canonical_bytes, sha256_bytes
from f017_corrected_oracle_authorization_v11 import (
    LIVE_KEYS, SCHEMA, parse_candidate, production_shards,
    NUMERICAL_V4, PRIMARY_V3, SECONDARY_V3, RESULT_AUTHORITY,
    IMPLEMENTATION_MEASUREMENT,
)
from f017_corrected_oracle_primary_wrapper_v11 import validate_candidate_document as validate_primary
from f017_corrected_oracle_secondary_wrapper_v11 import validate_candidate_document as validate_secondary
from f017_memory_gate_v9 import observe
from f017_event05_candidate_builder_v1 import (
    CandidateContext,
    build_operator_go_candidate,
    validate_operator_approval,
)
from f017_event05_readiness_authority_v1 import validate_readiness_declaration

ROOT = Path(__file__).resolve().parents[2]
DAG = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-result-artifact-dag-v11.json"
PRODUCTION_CATALOG = ROOT / "docs/research/glm52/raw/f016-c01-catalog-0001.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_document(path: Path) -> dict:
    candidate, digest = parse_candidate(path)
    primary = validate_primary(candidate); secondary = validate_secondary(candidate)
    return {"candidate":candidate, "candidate_sha256":digest,
            "primary":primary, "secondary":secondary}


def render_rehearsal_candidate(checkpoint_root: Path, shards: list[dict], catalog_path: Path,
                               output: Path, identity_suffix: str, *, scope: str) -> dict:
    if scope != "PRODUCTION_SHADOW_NO_ACCESS":
        raise ValueError("V11 rehearsal scope")
    suffix = identity_suffix.replace("_", "-")
    candidate = {
        "schema":SCHEMA, "state":"REHEARSAL_CANDIDATE", "live":False,
        "scope":scope, "authority_generation":11,
        "authorization_id":f"F017-V11-EVENT05-SHADOW-AUTH-{suffix}",
        "package_attempt_id":f"F017-V11-EVENT05-SHADOW-PACKAGE-{suffix}",
        "primary_event_id":f"F017-V11-EVENT05-SHADOW-PRIMARY-{suffix}",
        "secondary_event_id":f"F017-V11-EVENT05-SHADOW-SECONDARY-{suffix}",
        "causal_dag_sha256":_sha(DAG),
        "numerical_contract_sha256":_sha(NUMERICAL_V4),
        "primary_numerical_sha256":_sha(PRIMARY_V3),
        "secondary_numerical_sha256":_sha(SECONDARY_V3),
        "result_authority_sha256":_sha(RESULT_AUTHORITY),
        "implementation_measurement_sha256":_sha(IMPLEMENTATION_MEASUREMENT),
        "checkpoint_root":str(checkpoint_root), "shards":shards,
        "attempts":1, "retries":0, "resume":False, "active_generation":"V11",
        "synthetic_root_manifest_path":None, "synthetic_root_manifest_sha256":None,
        "tensor_catalog_path":str(catalog_path), "tensor_catalog_sha256":_sha(catalog_path),
        "mint_memory_gate":observe(enforce=False),
    }
    digest = bank_exclusive(output, candidate)
    validated = _validate_document(output)
    if validated["candidate_sha256"] != digest:
        raise ValueError("V11 candidate identity")
    return {**validated, "result":"PASS", "state_created":False,
            "checkpoint_opens":0, "checkpoint_reads":0, "numerical_operations":0}


def _install(candidate_path: Path, installed_path: Path, receipt_path: Path,
             *, authoritative: bool, expected_candidate_sha256: str | None = None) -> dict:
    report = _validate_document(candidate_path)
    candidate = report["candidate"]
    if authoritative != (set(candidate) == LIVE_KEYS):
        raise ValueError("V11 installation posture")
    if expected_candidate_sha256 is not None and report["candidate_sha256"] != expected_candidate_sha256:
        raise ValueError("V11 candidate changed before installation")
    raw = candidate_path.read_bytes()
    if sha256_bytes(raw) != report["candidate_sha256"]:
        raise ValueError("V11 candidate changed during installation validation")
    installed_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(installed_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0: raise ValueError("V11 installation short write")
            offset += written
        os.fsync(descriptor)
    finally: os.close(descriptor)
    directory = os.open(installed_path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try: os.fsync(directory)
    finally: os.close(directory)
    if installed_path.read_bytes() != raw:
        raise ValueError("V11 candidate/install identity")
    receipt = {
        "schema":"pulsarmlx.f017.corrected-oracle-installation-receipt/11.0.0",
        "authority":authoritative,
        "installation_kind":"CANONICAL_LIVE" if authoritative else "NONCANONICAL_REHEARSAL",
        "authorization_id":candidate["authorization_id"],
        "package_attempt_id":candidate["package_attempt_id"],
        "candidate_sha256":report["candidate_sha256"],
        "installed_sha256":sha256_bytes(raw),
        "installed_path":str(installed_path.resolve()),
        "candidate_install_bytes_equal":True,
        "result":"PASS",
    }
    receipt_sha = bank_exclusive(receipt_path, receipt)
    return {**receipt, "receipt_sha256":receipt_sha}


def install_rehearsal_candidate(candidate_path: Path, installed_path: Path,
                                receipt_path: Path) -> dict:
    return _install(candidate_path, installed_path, receipt_path, authoritative=False)


def _validate_installed(installed_path: Path, receipt_path: Path, *, authoritative: bool) -> dict:
    report = _validate_document(installed_path)
    receipt = read_artifact(receipt_path)
    keys = {"schema","authority","installation_kind","authorization_id","package_attempt_id",
            "candidate_sha256","installed_sha256","installed_path","candidate_install_bytes_equal","result"}
    candidate = report["candidate"]
    if (type(receipt) is not dict or set(receipt) != keys
            or receipt.get("schema") != "pulsarmlx.f017.corrected-oracle-installation-receipt/11.0.0"
            or receipt.get("authority") is not authoritative
            or receipt.get("installation_kind") != ("CANONICAL_LIVE" if authoritative else "NONCANONICAL_REHEARSAL")
            or receipt.get("authorization_id") != candidate["authorization_id"]
            or receipt.get("package_attempt_id") != candidate["package_attempt_id"]
            or receipt.get("candidate_sha256") != report["candidate_sha256"]
            or receipt.get("installed_sha256") != report["candidate_sha256"]
            or receipt.get("installed_path") != str(installed_path.resolve())
            or receipt.get("candidate_install_bytes_equal") is not True
            or receipt.get("result") != "PASS"):
        raise ValueError("V11 installation receipt")
    return {**report, "installation_receipt_sha256":_sha(receipt_path),
            "result":"PASS", "checkpoint_opens":0, "checkpoint_reads":0,
            "state_created":False, "numerical_operations":0}


def validate_installed_rehearsal(installed_path: Path, receipt_path: Path) -> dict:
    return _validate_installed(installed_path, receipt_path, authoritative=False)


def validate_installed_operator_go(installed_path: Path, receipt_path: Path) -> dict:
    return _validate_installed(installed_path, receipt_path, authoritative=True)


def install_operator_go_candidate(candidate_path: Path) -> dict:
    report = validate_live_candidate_for_install(candidate_path)
    candidate = report["candidate"]
    return _install(candidate_path, Path(candidate["canonical_authorization_path"]),
                    Path(candidate["installation_receipt_path"]), authoritative=True,
                    expected_candidate_sha256=report["candidate_sha256"])


def validate_live_candidate_for_install(candidate_path: Path) -> dict:
    """Rederive exact future-live bytes from bound authorities before install."""
    candidate, digest = parse_candidate(candidate_path)
    if set(candidate) != LIVE_KEYS:
        raise ValueError("V11 live candidate")
    approval_path = Path(candidate["operator_approval_path"])
    readiness_path = Path(candidate["execution_readiness_declaration_path"])
    approval = validate_operator_approval(approval_path, "LIVE_OPERATOR_GO")
    readiness = validate_readiness_declaration(
        readiness_path, expected_scope="FINAL_EVENT05_EXECUTION_READINESS",
    )
    if (approval.source_sha256 != candidate["operator_approval_sha256"]
            or readiness.source_sha256 != candidate["execution_readiness_declaration_sha256"]
            or approval.values["readiness_declaration_sha256"] != readiness.source_sha256
            or approval.values["authority_manifest_sha256"] != readiness.authority_manifest_sha256):
        raise ValueError("V11 live approval readback")
    context = _candidate_context(PRODUCTION_CATALOG)
    rebuilt = build_operator_go_candidate(
        approval, readiness, context, candidate["mint_memory_gate"],
    )
    raw = candidate_path.read_bytes()
    if canonical_bytes(rebuilt) != raw or sha256_bytes(raw) != digest:
        raise ValueError("V11 live candidate rederivation")
    return _validate_document(candidate_path)


def _candidate_context(catalog_path: Path) -> CandidateContext:
    return CandidateContext(
        causal_dag_sha256=_sha(DAG), numerical_contract_sha256=_sha(NUMERICAL_V4),
        primary_numerical_sha256=_sha(PRIMARY_V3), secondary_numerical_sha256=_sha(SECONDARY_V3),
        result_authority_sha256=_sha(RESULT_AUTHORITY),
        implementation_measurement_sha256=_sha(IMPLEMENTATION_MEASUREMENT),
        shards=tuple(production_shards()), tensor_catalog_path=str(catalog_path),
        tensor_catalog_sha256=_sha(catalog_path),
    )


def _render_operator_candidate(approval_path: Path, readiness_path: Path,
                               catalog_path: Path, output: Path, *, posture: str,
                               memory_observation: dict) -> dict:
    if (posture == "LIVE_OPERATOR_GO"
            and catalog_path.resolve(strict=True) != PRODUCTION_CATALOG.resolve(strict=True)):
        raise ValueError("V11 production tensor catalog")
    approval = validate_operator_approval(approval_path, posture)
    expected_scope = "FINAL_EVENT05_EXECUTION_READINESS" if posture == "LIVE_OPERATOR_GO" else None
    readiness = validate_readiness_declaration(readiness_path, expected_scope=expected_scope)
    candidate = build_operator_go_candidate(
        approval, readiness, _candidate_context(catalog_path), memory_observation,
    )
    digest = bank_exclusive(output, candidate)
    validated = _validate_document(output)
    if digest != validated["candidate_sha256"]: raise ValueError("V11 live candidate identity")
    return {**validated,"result":"PASS","checkpoint_opens":0,"checkpoint_reads":0,
            "state_created":False,"numerical_operations":0,"live_authority_installed":False,
            "event_05_ids_consumed":0}


def render_validation_only_operator_go_candidate(approval_path: Path, readiness_path: Path,
                                                 catalog_path: Path, output: Path,
                                                 memory_observation: dict) -> dict:
    """Exercise exact candidate construction without admitting a live approval."""
    return _render_operator_candidate(
        approval_path, readiness_path, catalog_path, output,
        posture="VALIDATION_ONLY", memory_observation=memory_observation,
    )


def render_operator_go_candidate(approval_path: Path, readiness_path: Path,
                                 catalog_path: Path, output: Path) -> dict:
    """Render only after a future, separately banked Event-05 human GO."""
    return _render_operator_candidate(
        approval_path, readiness_path, catalog_path, output,
        posture="LIVE_OPERATOR_GO", memory_observation=observe(enforce=True),
    )
