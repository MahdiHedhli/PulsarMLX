#!/usr/bin/env python3
"""Closed V12 checkpoint-identity failure vocabulary and accounting."""
from __future__ import annotations

from dataclasses import dataclass


OUTCOMES = {
    "F017_V12_IDENTITY_CANDIDATE_AUTHORITY_MISMATCH": ("PRE_CANDIDATE", 0, 0),
    "F017_V12_IDENTITY_INSTALLED_AUTHORITY_MISMATCH": ("POST_INSTALL_PRE_PACKAGE", 0, 0),
    "F017_V12_IDENTITY_CAPABILITY_DRIFT": ("POST_INSTALL_PRE_PACKAGE", 0, 0),
    "F017_V12_IDENTITY_PRODUCER_MEASUREMENT_DRIFT": ("POST_INSTALL_PRE_PACKAGE", 0, 0),
    "F017_V12_IDENTITY_RUNTIME_AUTHORITY_DRIFT": ("POST_PACKAGE_PRE_OPEN", 1, 0),
    "F017_V12_IDENTITY_PACKAGE_ATTEMPT_MISMATCH": ("POST_PACKAGE_PRE_OPEN", 1, 0),
    "F017_V12_IDENTITY_CONTRACT_DRIFT": ("POST_PACKAGE_PRE_OPEN", 1, 0),
    "F017_V12_IDENTITY_SHARD_OPEN_FAILURE": ("POST_OPEN", 1, 0),
    "F017_V12_IDENTITY_SHARD_SIZE_MISMATCH": ("POST_OPEN", 1, 0),
    "F017_V12_IDENTITY_SHARD_READ_FAILURE": ("POST_OPEN", 1, 0),
    "F017_V12_IDENTITY_SHARD_HASH_MISMATCH": ("POST_OPEN", 1, 0),
    "F017_V12_IDENTITY_DESCRIPTOR_CHANGED": ("POST_OPEN", 1, 0),
}


@dataclass(frozen=True)
class IdentityAuthorityError(ValueError):
    outcome_id: str
    detail: str
    checkpoint_access: int | str = 0

    def __post_init__(self) -> None:
        if self.outcome_id not in OUTCOMES:
            raise ValueError("unmodeled identity-authority outcome")
        if type(self.detail) is not str or not self.detail:
            raise ValueError("identity-authority failure detail")

    @property
    def evidence(self) -> dict:
        phase, package_delta, consumer_delta = OUTCOMES[self.outcome_id]
        return {
            "outcome_id": self.outcome_id,
            "phase": phase,
            "package_delta": package_delta,
            "consumer_delta": consumer_delta,
            "checkpoint_access": self.checkpoint_access,
            "generic_fallback": False,
            "detail": self.detail,
            "result": "FAIL",
        }

    def __str__(self) -> str:
        return f"{self.outcome_id}: {self.detail}"


def failure(outcome_id: str, detail: str, *, checkpoint_access: int | str = 0) -> IdentityAuthorityError:
    return IdentityAuthorityError(outcome_id, detail, checkpoint_access)
