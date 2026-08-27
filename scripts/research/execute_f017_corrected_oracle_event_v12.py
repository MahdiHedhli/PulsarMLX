#!/usr/bin/env python3
"""V12 checkpoint-identity package gate; Event 06 execution is not invoked here."""
from __future__ import annotations

from pathlib import Path

from f017_checkpoint_identity_capability_v12 import validate_capability
from f017_checkpoint_identity_producer_v12 import produce
from validate_f017_corrected_oracle_access_v12 import validate_candidate_triple, validate_installed_triple


def validate_package_start(candidate_path: Path, installed_path: Path, receipt_path: Path) -> dict:
    candidate = validate_candidate_triple(candidate_path)
    installed = validate_installed_triple(installed_path, receipt_path, candidate["authority"])
    if candidate["authority"].source_sha256 != installed["authority"].get("installed_authorization_sha256"):
        raise ValueError("V12 candidate/install authority identity")
    capability = validate_capability()
    return {
        "candidate_triple":"PASS", "installed_triple":"PASS",
        "capability":capability["result"],
        "package_claim_eligible":True, "checkpoint_opens":0,
        "checkpoint_reads":0, "state_created":False, "result":"PASS",
        "installed_authority":installed["authority"],
    }


def run_identity_stage(installed_authority, *, package_attempt_id: str, package_durable_start: bool,
                       evidence_directory: Path | None = None):
    return produce(installed_authority, package_attempt_id=package_attempt_id,
                   package_durable_start=package_durable_start,
                   evidence_directory=evidence_directory)
