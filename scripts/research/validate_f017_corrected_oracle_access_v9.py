#!/usr/bin/env python3
"""V9 rehearsal authorizer; it cannot mint or install live authority."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from f017_canonical_serialization_v8 import bank_exclusive, sha256_bytes, strict_bytes
from f017_corrected_oracle_authorization_v9 import SCHEMA, parse_candidate
from f017_corrected_oracle_primary_v9 import validate_candidate as validate_primary
from f017_corrected_oracle_secondary_v9 import validate_candidate as validate_secondary
from f017_memory_gate_v9 import observe


ROOT = Path(__file__).resolve().parents[2]


def _sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()


def render_rehearsal_candidate(checkpoint_root: Path, shards: list[dict], catalog_path: Path,
                               output: Path, identity_suffix: str, *, scope: str,
                               manifest_path: Path | None = None) -> dict:
    """Render non-authoritative candidate bytes after the required mint-time gate."""
    identity_suffix = identity_suffix.replace("_", "-")
    gate = observe(enforce=scope == "PRODUCTION_SHADOW_NO_ACCESS")
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
