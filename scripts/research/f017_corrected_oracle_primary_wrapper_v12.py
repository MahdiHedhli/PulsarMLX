#!/usr/bin/env python3
"""V12 primary identity-authority validation leg; numerical path remains V11."""
from __future__ import annotations

from f017_checkpoint_identity_authority_v12 import ValidatedIdentityAuthority
from f017_checkpoint_identity_lifecycle_v12 import failure
from f017_corrected_oracle_primary_wrapper_v11 import execute_target_and_bank


def validate_identity_authority(authority: ValidatedIdentityAuthority, *, posture: str) -> dict:
    if type(authority) is not ValidatedIdentityAuthority or authority.posture != posture:
        outcome = ("F017_V12_IDENTITY_CANDIDATE_AUTHORITY_MISMATCH" if posture == "CANDIDATE"
                   else "F017_V12_IDENTITY_INSTALLED_AUTHORITY_MISMATCH")
        raise failure(outcome, "primary authority posture")
    return {"member":"PRIMARY_CONSUMER","posture":posture,"result":"PASS","checkpoint_opens":0,"checkpoint_reads":0,"state_created":False}
