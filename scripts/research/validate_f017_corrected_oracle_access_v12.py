#!/usr/bin/env python3
"""Triple validation, noncanonical installation, and V12 package gate."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from f017_canonical_serialization_v10 import bank_exclusive, canonical_bytes, sha256_bytes
from f017_checkpoint_identity_authority_v12 import (
    ValidatedIdentityAuthority, installed_document, validate_candidate_path,
    validate_installed_path,
)
from f017_checkpoint_identity_lifecycle_v12 import failure
from f017_corrected_oracle_primary_wrapper_v12 import validate_identity_authority as validate_primary
from f017_corrected_oracle_secondary_wrapper_v12 import validate_identity_authority as validate_secondary


def _validate_producer(authority: ValidatedIdentityAuthority, *, posture: str) -> dict:
    if type(authority) is not ValidatedIdentityAuthority or authority.posture != posture:
        outcome = ("F017_V12_IDENTITY_CANDIDATE_AUTHORITY_MISMATCH" if posture == "CANDIDATE"
                   else "F017_V12_IDENTITY_INSTALLED_AUTHORITY_MISMATCH")
        raise failure(outcome, "identity producer authority posture")
    return {"member":"CHECKPOINT_IDENTITY_PRODUCER","posture":posture,"result":"PASS","checkpoint_opens":0,"checkpoint_reads":0,"state_created":False}


def validate_candidate_triple(path: Path) -> dict:
    authority = validate_candidate_path(path)
    reports = [validate_primary(authority, posture="CANDIDATE"),
               validate_secondary(authority, posture="CANDIDATE"),
               _validate_producer(authority, posture="CANDIDATE")]
    return {"authority":authority,"reports":reports,"result":"PASS","checkpoint_opens":0,
            "checkpoint_reads":0,"state_created":False,"numerical_operations":0}


def install_noncanonical_candidate(candidate_path: Path, installed_path: Path, receipt_path: Path) -> dict:
    report = validate_candidate_triple(candidate_path)
    candidate = report["authority"]
    receipt = {
        "schema":"pulsarmlx.f017.checkpoint-identity-installation-receipt/12.0.0",
        "candidate_sha256":candidate.source_sha256,
        "authorization_id":candidate.get("authorization_id"),
        "package_attempt_id":candidate.get("package_attempt_id"),
        "installation_kind":"NONCANONICAL_SYNTHETIC_QUALIFICATION",
        "live_authority":False,
        "result":"PASS",
    }
    receipt_sha = bank_exclusive(receipt_path, receipt)
    installed = installed_document(candidate, receipt_sha)
    installed_sha = bank_exclusive(installed_path, installed)
    return {"installed_sha256":installed_sha,"receipt_sha256":receipt_sha,
            "candidate_sha256":candidate.source_sha256,"result":"PASS",
            "live_authority_installed":False,"checkpoint_opens":0,"checkpoint_reads":0}


def validate_installed_triple(installed_path: Path, receipt_path: Path) -> dict:
    authority = validate_installed_path(installed_path)
    receipt_raw = receipt_path.read_bytes()
    receipt_sha = sha256_bytes(receipt_raw)
    if authority.get("installation_receipt_sha256") != receipt_sha:
        raise failure("F017_V12_IDENTITY_INSTALLED_AUTHORITY_MISMATCH", "installation receipt binding")
    receipt = __import__("f017_bounded_artifact_decode_v1").parse_artifact_bytes(receipt_raw)
    if (receipt.get("candidate_sha256") != authority.get("installed_authorization_sha256")
            or receipt.get("live_authority") is not False):
        raise failure("F017_V12_IDENTITY_INSTALLED_AUTHORITY_MISMATCH", "installation receipt authority")
    reports = [validate_primary(authority, posture="INSTALLED"),
               validate_secondary(authority, posture="INSTALLED"),
               _validate_producer(authority, posture="INSTALLED")]
    return {"authority":authority,"reports":reports,"result":"PASS","checkpoint_opens":0,
            "checkpoint_reads":0,"state_created":False,"numerical_operations":0}


def bank_candidate(path: Path, value: dict) -> str:
    raw = canonical_bytes(value)
    authority = __import__("f017_checkpoint_identity_authority_v12").validate_candidate_bytes(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return authority.source_sha256
