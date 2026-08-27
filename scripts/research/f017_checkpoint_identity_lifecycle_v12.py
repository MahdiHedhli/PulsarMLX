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

OUTCOME_DETAILS = {
    "F017_V12_IDENTITY_CANDIDATE_AUTHORITY_MISMATCH": ("IDENTITY_CANDIDATE_AUTHORITY_VALIDATE", (), "NONE", "PRE_CANDIDATE_FAILURE"),
    "F017_V12_IDENTITY_INSTALLED_AUTHORITY_MISMATCH": ("IDENTITY_INSTALLED_AUTHORITY_VALIDATE", ("AUTHORIZATION_INSTALLED",), "NONE", "INSTALLED_AUTHORITY_FAILURE"),
    "F017_V12_IDENTITY_CAPABILITY_DRIFT": ("IDENTITY_CAPABILITY_VALIDATE", ("AUTHORIZATION_INSTALLED",), "NONE", "INSTALLED_AUTHORITY_FAILURE"),
    "F017_V12_IDENTITY_PRODUCER_MEASUREMENT_DRIFT": ("IDENTITY_PRODUCER_MEASUREMENT_VALIDATE", ("AUTHORIZATION_INSTALLED",), "NONE", "INSTALLED_AUTHORITY_FAILURE"),
    "F017_V12_IDENTITY_RUNTIME_AUTHORITY_DRIFT": ("IDENTITY_RUNTIME_AUTHORITY_REVALIDATE", ("AUTHORIZATION_INSTALLED", "PACKAGE_DURABLE_START"), "NONE", "PACKAGE_FAILURE_TERMINAL"),
    "F017_V12_IDENTITY_PACKAGE_ATTEMPT_MISMATCH": ("IDENTITY_PACKAGE_ATTEMPT_VALIDATE", ("AUTHORIZATION_INSTALLED", "PACKAGE_DURABLE_START"), "NONE", "PACKAGE_FAILURE_TERMINAL"),
    "F017_V12_IDENTITY_CONTRACT_DRIFT": ("IDENTITY_CONTRACT_REVALIDATE", ("AUTHORIZATION_INSTALLED", "PACKAGE_DURABLE_START"), "NONE", "PACKAGE_FAILURE_TERMINAL"),
    "F017_V12_IDENTITY_SHARD_OPEN_FAILURE": ("CHECKPOINT_SHARD_OPEN", ("AUTHORIZATION_INSTALLED", "PACKAGE_DURABLE_START", "CHECKPOINT_IDENTITY_START"), "RELEASE_OPEN_DESCRIPTORS", "PACKAGE_FAILURE_TERMINAL"),
    "F017_V12_IDENTITY_SHARD_SIZE_MISMATCH": ("CHECKPOINT_SHARD_SIZE_VALIDATE", ("AUTHORIZATION_INSTALLED", "PACKAGE_DURABLE_START", "CHECKPOINT_IDENTITY_START"), "RELEASE_OPEN_DESCRIPTORS", "PACKAGE_FAILURE_TERMINAL"),
    "F017_V12_IDENTITY_SHARD_READ_FAILURE": ("CHECKPOINT_SHARD_HASH_READ", ("AUTHORIZATION_INSTALLED", "PACKAGE_DURABLE_START", "CHECKPOINT_IDENTITY_START"), "RELEASE_OPEN_DESCRIPTORS", "PACKAGE_FAILURE_TERMINAL"),
    "F017_V12_IDENTITY_SHARD_HASH_MISMATCH": ("CHECKPOINT_SHARD_HASH_VALIDATE", ("AUTHORIZATION_INSTALLED", "PACKAGE_DURABLE_START", "CHECKPOINT_IDENTITY_START"), "RELEASE_OPEN_DESCRIPTORS", "PACKAGE_FAILURE_TERMINAL"),
    "F017_V12_IDENTITY_DESCRIPTOR_CHANGED": ("CHECKPOINT_DESCRIPTOR_IDENTITY_REVALIDATE", ("AUTHORIZATION_INSTALLED", "PACKAGE_DURABLE_START", "CHECKPOINT_IDENTITY_START"), "RELEASE_OPEN_DESCRIPTORS", "PACKAGE_FAILURE_TERMINAL"),
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
        transition_id, durable_prefix, release_obligation, terminal_evidence = OUTCOME_DETAILS[self.outcome_id]
        return {
            "outcome_id": self.outcome_id,
            "transition_id": transition_id,
            "phase": phase,
            "durable_prefix": list(durable_prefix),
            "package_delta": package_delta,
            "consumer_delta": consumer_delta,
            "checkpoint_access": self.checkpoint_access,
            "release_obligation": release_obligation,
            "terminal_evidence": terminal_evidence,
            "generic_fallback": False,
            "detail": self.detail,
            "result": "FAIL",
        }

    def __str__(self) -> str:
        return f"{self.outcome_id}: {self.detail}"


def failure(outcome_id: str, detail: str, *, checkpoint_access: int | str = 0) -> IdentityAuthorityError:
    return IdentityAuthorityError(outcome_id, detail, checkpoint_access)
