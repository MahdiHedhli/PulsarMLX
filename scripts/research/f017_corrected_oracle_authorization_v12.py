#!/usr/bin/env python3
"""Candidate construction for the V12 checkpoint-identity authority."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Mapping

from f017_canonical_serialization_v10 import canonical_bytes
from f017_checkpoint_identity_authority_v12 import CANDIDATE_SCHEMA, validate_candidate_bytes

ROOT = Path(__file__).resolve().parents[2]
PRIMARY = "scripts/research/f017_corrected_oracle_primary_wrapper_v12.py"
SECONDARY = "scripts/research/f017_corrected_oracle_secondary_wrapper_v12.py"
IDENTITY_VALIDATOR = "scripts/research/f017_checkpoint_identity_authority_v12.py"
PRODUCER = "scripts/research/f017_checkpoint_identity_producer_v12.py"
CAPABILITY = "scripts/research/f017_checkpoint_identity_capability_v12.py"


def _sha(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def build_identity_candidate(*, authority_scope: str, authorization_id: str,
                             package_attempt_id: str, checkpoint_root: Path,
                             checkpoint_identity_contract_path: str,
                             event_identity_plan_sha256: str) -> dict:
    contract = __import__("json").loads((ROOT / checkpoint_identity_contract_path).read_text(encoding="utf-8"))
    census = contract["derived_census"]
    operation = ("CHECKPOINT_IDENTITY_QUALIFICATION" if authority_scope == "SYNTHETIC"
                 else "CORRECTED_FULL_CHECKPOINT_ORACLE")
    value = {
        "schema": CANDIDATE_SCHEMA, "authority_scope": authority_scope,
        "operation_class": operation, "generation": "V12",
        "authorization_id": authorization_id, "package_attempt_id": package_attempt_id,
        "checkpoint_set_sha256": contract["checkpoint_set_sha256"],
        "checkpoint_root": str(checkpoint_root),
        "checkpoint_identity_contract_path": checkpoint_identity_contract_path,
        "checkpoint_identity_contract_sha256": _sha(checkpoint_identity_contract_path),
        "producer_capability_path": CAPABILITY, "producer_capability_sha256": _sha(CAPABILITY),
        "measured_producer_path": PRODUCER, "measured_producer_sha256": _sha(PRODUCER),
        "primary_candidate_validator_path": PRIMARY, "primary_candidate_validator_sha256": _sha(PRIMARY),
        "secondary_candidate_validator_path": SECONDARY, "secondary_candidate_validator_sha256": _sha(SECONDARY),
        "identity_candidate_validator_path": IDENTITY_VALIDATOR,
        "identity_candidate_validator_sha256": _sha(IDENTITY_VALIDATOR),
        "expected_shard_count": census["expected_shard_count"],
        "expected_identity_only_shard_count": census["expected_identity_only_count"],
        "expected_graph_payload_shard_count": census["expected_graph_payload_count"],
        "expected_total_bytes": census["expected_total_bytes"],
        "attempts": 1, "retries": 0, "resume": False,
        "event_identity_plan_sha256": event_identity_plan_sha256,
    }
    validate_candidate_bytes(canonical_bytes(value))
    return value


def candidate_bytes(value: Mapping[str, object]) -> bytes:
    raw = canonical_bytes(dict(value))
    validate_candidate_bytes(raw)
    return raw
