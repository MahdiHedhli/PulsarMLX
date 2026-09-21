#!/usr/bin/env python3
"""Version-forward V12 candidate adapter for sealed readiness V2."""

from __future__ import annotations

from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes
from f017_checkpoint_identity_authority_v12 import (
    ValidatedIdentityAuthority,
    validate_candidate_bytes,
)
from f017_corrected_oracle_authorization_v12 import build_identity_candidate
from f017_event06_readiness_authority_v2 import ValidatedEvent06ReadinessV2

PRODUCTION_CONTRACT = (
    "specs/017-rust-native-inference-runtime/contracts/"
    "f017-corrected-oracle-checkpoint-identity-v12.json"
)


def build_identity_candidate_from_readiness_v2(
    readiness: ValidatedEvent06ReadinessV2,
    *,
    authorization_id: str,
    package_attempt_id: str,
    checkpoint_root: Path,
    event_identity_plan_sha256: str,
) -> ValidatedIdentityAuthority:
    if type(readiness) is not ValidatedEvent06ReadinessV2:
        raise TypeError("sealed Event 06 readiness V2 required")
    if (
        readiness.get("active_corrected_oracle_generation") != "V12"
        or readiness.get("current_executable_readiness") is not True
        or readiness.get("ready_for_fresh_corrected_full_checkpoint_oracle_event_06_go")
        is not True
    ):
        raise ValueError("Event 06 readiness posture")
    value = build_identity_candidate(
        authority_scope="PRODUCTION",
        authorization_id=authorization_id,
        package_attempt_id=package_attempt_id,
        checkpoint_root=checkpoint_root,
        checkpoint_identity_contract_path=PRODUCTION_CONTRACT,
        event_identity_plan_sha256=event_identity_plan_sha256,
    )
    return validate_candidate_bytes(canonical_bytes(value))
