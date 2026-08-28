#!/usr/bin/env python3
"""Version-forward V12 candidate adapter for sealed Sequence 9 readiness."""

from __future__ import annotations

from pathlib import Path

from f017_checkpoint_identity_authority_v12 import ValidatedIdentityAuthority
from f017_corrected_oracle_authorization_v12_v2 import (
    build_identity_candidate_from_readiness_v2,
)
from f017_event06_readiness_authority_v3 import (
    ValidatedEvent06ReadinessV3,
    _repository_delegate,
    assert_readiness_v3_sealed,
)


def build_identity_candidate_from_readiness_v3(
    readiness: ValidatedEvent06ReadinessV3,
    *,
    authorization_id: str,
    package_attempt_id: str,
    checkpoint_root: Path,
    event_identity_plan_sha256: str,
) -> ValidatedIdentityAuthority:
    readiness = assert_readiness_v3_sealed(readiness)
    return build_identity_candidate_from_readiness_v2(
        _repository_delegate(readiness),
        authorization_id=authorization_id,
        package_attempt_id=package_attempt_id,
        checkpoint_root=checkpoint_root,
        event_identity_plan_sha256=event_identity_plan_sha256,
    )
