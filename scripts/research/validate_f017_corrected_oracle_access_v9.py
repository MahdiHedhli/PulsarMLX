#!/usr/bin/env python3
"""Two-phase V9 authorizer.

Rehearsal helpers are usable now.  The production candidate renderer is called
only by checkpoint-free instantiability tests; canonical installation requires
a separately banked readiness declaration and fresh operator approval and is
never invoked by this preparation phase.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from f017_canonical_serialization_v8 import bank_exclusive, sha256_bytes, strict_bytes
from f017_corrected_oracle_authorization_v9 import LIVE_KEYS, SCHEMA, parse_candidate, production_shards
from f017_corrected_oracle_primary_v9 import validate_candidate as validate_primary
from f017_corrected_oracle_secondary_v9 import validate_candidate as validate_secondary
from f017_memory_gate_v9 import observe


ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_PLAN = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-production-tensor-plan-v9.json"
READINESS_KEYS = {"schema", "F017_CORRECTED_ORACLE_EVENT04_EXECUTION_READINESS",
                  "READY_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_EXECUTION_GO",
                  "ACTIVE_CORRECTED_ORACLE_GENERATION", "accepted_implementation_head",
                  "accepted_authority_manifest_sha256", "accepted_at_unix_ns"}


def _sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()


def render_rehearsal_candidate(checkpoint_root: Path, shards: list[dict], catalog_path: Path,
                               output: Path, identity_suffix: str, *, scope: str,
                               manifest_path: Path | None = None) -> dict:
    """Render non-authoritative candidate bytes after the required mint-time gate."""
    identity_suffix = identity_suffix.replace("_", "-")
    gate = observe(enforce=False)
    candidate = {
        "schema": SCHEMA, "state": "REHEARSAL_CANDIDATE", "live": False, "scope": scope, "authority_generation": 9,
        "authorization_id": f"F017-V9-QUAL-AUTH-{identity_suffix}", "package_attempt_id": f"F017-V9-QUAL-PACKAGE-{identity_suffix}",
        "primary_event_id": f"F017-V9-QUAL-PRIMARY-{identity_suffix}", "secondary_event_id": f"F017-V9-QUAL-SECONDARY-{identity_suffix}",
        "causal_dag_sha256": _sha(ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-causal-artifact-dag-v8.json"),
        "numerical_contract_sha256": _sha(ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v3.json"),
        "primary_numerical_sha256": _sha(ROOT / "scripts/research/f017_corrected_oracle_primary_numerics_v2.py"),
        "secondary_numerical_sha256": _sha(ROOT / "scripts/research/f017_corrected_oracle_secondary_numerics_v2.py"),
        "checkpoint_root": str(checkpoint_root), "shards": shards, "attempts": 1, "retries": 0, "resume": False,
        "active_generation": "V9", "synthetic_root_manifest_path": str(manifest_path) if manifest_path else None,
        "synthetic_root_manifest_sha256": _sha(manifest_path) if manifest_path else None,
        "tensor_catalog_path": str(catalog_path), "tensor_catalog_sha256": _sha(catalog_path), "mint_memory_gate": gate,
    }
    digest = bank_exclusive(output, candidate)
    primary = validate_primary(output); secondary = validate_secondary(output)
    if primary["candidate_sha256"] != digest or secondary["candidate_sha256"] != digest:
        raise ValueError("candidate validation digest divergence")
    return {"result": "PASS", "candidate_sha256": digest, "candidate": candidate, "primary": primary, "secondary": secondary,
            "checkpoint_opens": 0, "checkpoint_reads": 0, "state_created": False}


def validate_existing_candidate(path: Path) -> dict:
    candidate, digest = parse_candidate(path)
    return {"candidate": candidate, "candidate_sha256": digest, "primary": validate_primary(path), "secondary": validate_secondary(path)}


def install_rehearsal_candidate(candidate_path: Path, installed_path: Path, receipt_path: Path) -> dict:
    """Exercise exact no-replace installation mechanics at a noncanonical path only."""
    report = validate_existing_candidate(candidate_path); raw = candidate_path.read_bytes()
    installed_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = installed_path.open("xb")
    try:
        descriptor.write(raw); descriptor.flush(); os.fsync(descriptor.fileno())
    finally: descriptor.close()
    directory = os.open(installed_path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try: os.fsync(directory)
    finally: os.close(directory)
    readback = installed_path.read_bytes()
    if readback != raw or sha256_bytes(readback) != report["candidate_sha256"]: raise ValueError("candidate/install byte identity")
    receipt = {"schema": "pulsarmlx.f017.corrected-oracle-installation-receipt/9.0.0", "authority": False,
               "installation_kind": "NONCANONICAL_REHEARSAL", "authorization_id": report["candidate"]["authorization_id"],
               "package_attempt_id": report["candidate"]["package_attempt_id"], "candidate_sha256": report["candidate_sha256"],
               "installed_sha256": sha256_bytes(readback), "installed_path": str(installed_path.resolve()),
               "primary_validation_sha256": sha256_bytes(json.dumps(report["primary"], sort_keys=True, separators=(",", ":")).encode()),
               "secondary_validation_sha256": sha256_bytes(json.dumps(report["secondary"], sort_keys=True, separators=(",", ":")).encode()),
               "candidate_install_bytes_equal": True, "result": "PASS"}
    receipt_sha = bank_exclusive(receipt_path, receipt); return {**receipt, "receipt_sha256": receipt_sha}


def validate_installed_rehearsal(installed_path: Path, receipt_path: Path) -> dict:
    report = validate_existing_candidate(installed_path); receipt = strict_bytes(receipt_path.read_bytes())
    expected = {"schema", "authority", "installation_kind", "authorization_id", "package_attempt_id", "candidate_sha256",
                "installed_sha256", "installed_path", "primary_validation_sha256", "secondary_validation_sha256",
                "candidate_install_bytes_equal", "result"}
    if type(receipt) is not dict or set(receipt) != expected or receipt["schema"] != "pulsarmlx.f017.corrected-oracle-installation-receipt/9.0.0":
        raise ValueError("installation receipt census")
    candidate = report["candidate"]; installed_sha = sha256_bytes(installed_path.read_bytes())
    if receipt["authority"] is not False or receipt["installation_kind"] != "NONCANONICAL_REHEARSAL" or receipt["result"] != "PASS" or receipt["candidate_install_bytes_equal"] is not True:
        raise ValueError("installation receipt posture")
    if (receipt["authorization_id"] != candidate["authorization_id"] or receipt["package_attempt_id"] != candidate["package_attempt_id"]
            or receipt["candidate_sha256"] != report["candidate_sha256"] or receipt["installed_sha256"] != installed_sha
            or receipt["candidate_sha256"] != installed_sha or receipt["installed_path"] != str(installed_path.resolve())):
        raise ValueError("installation receipt binding")
    return {"result": "PASS", "candidate": candidate, "candidate_sha256": report["candidate_sha256"],
            "installation_receipt_sha256": sha256_bytes(receipt_path.read_bytes()), "primary": report["primary"], "secondary": report["secondary"],
            "checkpoint_opens": 0, "checkpoint_reads": 0, "state_created": False, "numerical_operations": 0}


def render_operator_go_candidate(approval_path: Path, readiness_path: Path, catalog_path: Path, output: Path) -> dict:
    """Render future Event-04 candidate bytes; rendering does not install authority."""
    approval = strict_bytes(approval_path.read_bytes()); readiness = strict_bytes(readiness_path.read_bytes())
    approval_keys = {"schema", "result", "active_generation", "authorization_id", "package_attempt_id",
                     "primary_event_id", "secondary_event_id", "checkpoint_root", "shards",
                     "canonical_authorization_path", "installation_receipt_path", "emergency_evidence_root",
                     "authority_manifest_sha256", "readiness_declaration_sha256", "approved_at_unix_ns",
                     "approval_expires_at_unix_ns"}
    if type(approval) is not dict or set(approval) != approval_keys or approval["schema"] != "pulsarmlx.f017.corrected-oracle-event04-operator-approval/9.0.0":
        raise ValueError("operator approval census")
    if approval["result"] != "APPROVED_FOR_ONE_EVENT_04" or approval["active_generation"] != "V9":
        raise ValueError("operator approval posture")
    readiness_sha = _sha(readiness_path)
    if (type(readiness) is not dict or set(readiness) != READINESS_KEYS
            or readiness.get("schema") != "pulsarmlx.f017.event04-execution-readiness-declaration/9.0.0"
            or readiness.get("F017_CORRECTED_ORACLE_EVENT04_EXECUTION_READINESS") != "ACCEPTED"
            or readiness.get("READY_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_EXECUTION_GO") != "YES"
            or readiness.get("ACTIVE_CORRECTED_ORACLE_GENERATION") != "V9"):
        raise ValueError("execution-readiness authority")
    now = time.time_ns()
    for key in ("accepted_at_unix_ns",):
        if type(readiness[key]) is not int or readiness[key] < 0:
            raise ValueError("readiness time")
    for key in ("approved_at_unix_ns", "approval_expires_at_unix_ns"):
        if type(approval[key]) is not int or approval[key] < 0:
            raise ValueError("approval time")
    if not approval["approved_at_unix_ns"] <= now <= approval["approval_expires_at_unix_ns"]:
        raise ValueError("operator approval freshness")
    if approval["readiness_declaration_sha256"] != readiness_sha:
        raise ValueError("operator approval/readiness binding")
    if catalog_path.resolve() != PRODUCTION_PLAN.resolve() or approval["shards"] != production_shards():
        raise ValueError("operator approval checkpoint authority")
    plan_raw = catalog_path.read_bytes()
    candidate = {
        "schema": SCHEMA, "state": "OPERATOR_APPROVED_CANDIDATE", "live": False, "scope": "PRODUCTION_EVENT_04",
        "authority_generation": 9, "authorization_id": approval["authorization_id"],
        "package_attempt_id": approval["package_attempt_id"], "primary_event_id": approval["primary_event_id"],
        "secondary_event_id": approval["secondary_event_id"],
        "causal_dag_sha256": _sha(ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-causal-artifact-dag-v8.json"),
        "numerical_contract_sha256": _sha(ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v3.json"),
        "primary_numerical_sha256": _sha(ROOT / "scripts/research/f017_corrected_oracle_primary_numerics_v2.py"),
        "secondary_numerical_sha256": _sha(ROOT / "scripts/research/f017_corrected_oracle_secondary_numerics_v2.py"),
        "checkpoint_root": approval["checkpoint_root"], "shards": approval["shards"], "attempts": 1, "retries": 0,
        "resume": False, "active_generation": "V9", "synthetic_root_manifest_path": None,
        "synthetic_root_manifest_sha256": None, "tensor_catalog_path": str(catalog_path.resolve()),
        "tensor_catalog_sha256": hashlib.sha256(plan_raw).hexdigest(), "mint_memory_gate": observe(enforce=True),
        "operator_approval_path": str(approval_path.resolve()), "operator_approval_sha256": _sha(approval_path),
        "canonical_authorization_path": approval["canonical_authorization_path"],
        "installation_receipt_path": approval["installation_receipt_path"],
        "emergency_evidence_root": approval["emergency_evidence_root"],
        "authority_manifest_sha256": approval["authority_manifest_sha256"],
        "execution_readiness_declaration_path": str(readiness_path.resolve()),
        "execution_readiness_declaration_sha256": readiness_sha,
    }
    if set(candidate) != LIVE_KEYS:
        raise ValueError("future-live candidate census")
    digest = bank_exclusive(output, candidate)
    primary = validate_primary(output); secondary = validate_secondary(output)
    if primary["candidate_sha256"] != digest or secondary["candidate_sha256"] != digest:
        raise ValueError("future-live dual validation divergence")
    return {"result": "PASS", "authority_created": False, "candidate_sha256": digest, "candidate": candidate,
            "primary": primary, "secondary": secondary, "checkpoint_opens": 0, "checkpoint_reads": 0}


def install_operator_go_candidate(candidate_path: Path) -> dict:
    """Atomically install exact approved bytes and bank their activation receipt."""
    report = validate_existing_candidate(candidate_path); candidate = report["candidate"]
    if candidate["scope"] != "PRODUCTION_EVENT_04":
        raise ValueError("production installation scope")
    installed_path = Path(candidate["canonical_authorization_path"])
    receipt_path = Path(candidate["installation_receipt_path"])
    if installed_path.exists() or receipt_path.exists():
        raise FileExistsError("Event-04 authority or receipt already exists")
    raw = candidate_path.read_bytes(); installed_path.parent.mkdir(parents=True, exist_ok=True)
    with installed_path.open("xb") as sink:
        sink.write(raw); sink.flush(); os.fsync(sink.fileno())
    directory = os.open(installed_path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try: os.fsync(directory)
    finally: os.close(directory)
    readback = installed_path.read_bytes()
    if readback != raw or sha256_bytes(readback) != report["candidate_sha256"]:
        raise ValueError("production candidate/install byte identity")
    emergency = Path(candidate["emergency_evidence_root"])
    emergency.parent.mkdir(parents=True, exist_ok=True); emergency.mkdir(mode=0o700, exist_ok=False)
    receipt = {"schema": "pulsarmlx.f017.corrected-oracle-installation-receipt/9.0.0", "authority": True,
               "installation_kind": "CANONICAL_EVENT04_NO_REPLACE", "authorization_id": candidate["authorization_id"],
               "package_attempt_id": candidate["package_attempt_id"], "candidate_sha256": report["candidate_sha256"],
               "installed_sha256": sha256_bytes(readback), "installed_path": str(installed_path.resolve()),
               "operator_approval_sha256": candidate["operator_approval_sha256"],
               "execution_readiness_declaration_sha256": candidate["execution_readiness_declaration_sha256"],
               "emergency_evidence_root": str(emergency.resolve()),
               "candidate_install_bytes_equal": True, "result": "PASS"}
    receipt_sha = bank_exclusive(receipt_path, receipt)
    return {**receipt, "receipt_sha256": receipt_sha}


def validate_installed_operator_go(installed_path: Path, receipt_path: Path) -> dict:
    report = validate_existing_candidate(installed_path); candidate = report["candidate"]
    if candidate["scope"] != "PRODUCTION_EVENT_04" or str(installed_path.resolve()) != candidate["canonical_authorization_path"]:
        raise ValueError("canonical installed authorization")
    receipt = strict_bytes(receipt_path.read_bytes())
    expected = {"schema", "authority", "installation_kind", "authorization_id", "package_attempt_id", "candidate_sha256",
                "installed_sha256", "installed_path", "operator_approval_sha256", "execution_readiness_declaration_sha256",
                "emergency_evidence_root",
                "candidate_install_bytes_equal", "result"}
    if type(receipt) is not dict or set(receipt) != expected or receipt["authority"] is not True or receipt["result"] != "PASS":
        raise ValueError("production installation receipt")
    digest = sha256_bytes(installed_path.read_bytes())
    if (receipt["installation_kind"] != "CANONICAL_EVENT04_NO_REPLACE" or receipt["candidate_sha256"] != digest
            or receipt["installed_sha256"] != digest or receipt["authorization_id"] != candidate["authorization_id"]
            or receipt["package_attempt_id"] != candidate["package_attempt_id"]
            or receipt["operator_approval_sha256"] != candidate["operator_approval_sha256"]
            or receipt["execution_readiness_declaration_sha256"] != candidate["execution_readiness_declaration_sha256"]
            or receipt["emergency_evidence_root"] != candidate["emergency_evidence_root"]):
        raise ValueError("production installation binding")
    return {"result": "PASS", "authority": True, "candidate": candidate, "candidate_sha256": digest,
            "installation_receipt_sha256": sha256_bytes(receipt_path.read_bytes()), "checkpoint_opens": 0, "checkpoint_reads": 0}
