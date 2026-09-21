#!/usr/bin/env python3
"""Closed V12 checkpoint-identity failure vocabulary and accounting."""
from __future__ import annotations

from dataclasses import dataclass
import re


_HEX64 = re.compile(r"[0-9a-f]{64}")


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
class IdentityOperationObservation:
    """The bounded physical effect known when one identity operation fails."""

    effect_count: int
    observed_bytes: int
    observed_sha256: str | None
    disposition: str

    def __post_init__(self) -> None:
        if type(self.effect_count) is not int or self.effect_count not in {0, 1}:
            raise ValueError("identity operation effect count")
        if type(self.observed_bytes) is not int or self.observed_bytes < 0:
            raise ValueError("identity operation observed bytes")
        if self.observed_sha256 is not None and (
            type(self.observed_sha256) is not str
            or _HEX64.fullmatch(self.observed_sha256) is None
        ):
            raise ValueError("identity operation observed SHA-256")
        if type(self.disposition) is not str or not self.disposition:
            raise ValueError("identity operation disposition")

    @property
    def evidence(self) -> dict:
        return {
            "effect_count": self.effect_count,
            "observed_bytes": self.observed_bytes,
            "observed_sha256": self.observed_sha256,
            "disposition": self.disposition,
        }


@dataclass(frozen=True)
class IdentityAccessCensus:
    """Validated receipt-derived lower/upper access bounds for one prefix."""

    genesis_sha256: str
    head_sha256: str
    receipt_count: int
    checkpoint_shard_opens_lower_bound: int
    checkpoint_shard_opens_upper_bound: int
    checkpoint_shard_opens_unconfirmed: int
    checkpoint_identity_hash_reads_lower_bound: int
    checkpoint_identity_hash_reads_upper_bound: int
    checkpoint_identity_hash_reads_unconfirmed: int
    identity_hash_bytes_lower_bound: int
    identity_hash_bytes_upper_bound: int
    identity_hash_bytes_unconfirmed: int
    exact: bool
    unresolved_operation: str | None
    unresolved_ordinal: int
    prefix_complete: bool

    def __post_init__(self) -> None:
        for label, digest in (
            ("access genesis", self.genesis_sha256),
            ("access head", self.head_sha256),
        ):
            if type(digest) is not str or _HEX64.fullmatch(digest) is None:
                raise ValueError(f"{label} SHA-256")
        integer_fields = (
            self.receipt_count,
            self.checkpoint_shard_opens_lower_bound,
            self.checkpoint_shard_opens_upper_bound,
            self.checkpoint_shard_opens_unconfirmed,
            self.checkpoint_identity_hash_reads_lower_bound,
            self.checkpoint_identity_hash_reads_upper_bound,
            self.checkpoint_identity_hash_reads_unconfirmed,
            self.identity_hash_bytes_lower_bound,
            self.identity_hash_bytes_upper_bound,
            self.identity_hash_bytes_unconfirmed,
            self.unresolved_ordinal,
        )
        if any(type(item) is not int or item < 0 for item in integer_fields):
            raise ValueError("identity access census nonnegative integers")
        if (
            self.checkpoint_shard_opens_upper_bound
            != self.checkpoint_shard_opens_lower_bound
            + self.checkpoint_shard_opens_unconfirmed
            or self.checkpoint_identity_hash_reads_upper_bound
            != self.checkpoint_identity_hash_reads_lower_bound
            + self.checkpoint_identity_hash_reads_unconfirmed
            or self.identity_hash_bytes_upper_bound
            != self.identity_hash_bytes_lower_bound
            + self.identity_hash_bytes_unconfirmed
        ):
            raise ValueError("identity access census bounds")
        if type(self.exact) is not bool or type(self.prefix_complete) is not bool:
            raise ValueError("identity access census booleans")
        if self.exact is not (
            self.checkpoint_shard_opens_unconfirmed == 0
            and self.checkpoint_identity_hash_reads_unconfirmed == 0
            and self.identity_hash_bytes_unconfirmed == 0
        ):
            raise ValueError("identity access census exactness")
        if self.unresolved_operation is None:
            if self.unresolved_ordinal != 0:
                raise ValueError("identity access unresolved ordinal")
        elif (
            self.unresolved_operation not in {"SHARD_OPEN", "IDENTITY_HASH_READ"}
            or self.unresolved_ordinal not in range(1, 7)
            or self.exact
        ):
            raise ValueError("identity access unresolved operation")

    @property
    def evidence(self) -> dict:
        return {
            "schema": (
                "pulsarmlx.f017.checkpoint-identity-access-census/12.1.0"
            ),
            "genesis_sha256": self.genesis_sha256,
            "head_sha256": self.head_sha256,
            "receipt_count": self.receipt_count,
            "checkpoint_shard_opens_lower_bound": (
                self.checkpoint_shard_opens_lower_bound
            ),
            "checkpoint_shard_opens_upper_bound": (
                self.checkpoint_shard_opens_upper_bound
            ),
            "checkpoint_shard_opens_unconfirmed": (
                self.checkpoint_shard_opens_unconfirmed
            ),
            "checkpoint_identity_hash_reads_lower_bound": (
                self.checkpoint_identity_hash_reads_lower_bound
            ),
            "checkpoint_identity_hash_reads_upper_bound": (
                self.checkpoint_identity_hash_reads_upper_bound
            ),
            "checkpoint_identity_hash_reads_unconfirmed": (
                self.checkpoint_identity_hash_reads_unconfirmed
            ),
            "identity_hash_bytes_lower_bound": self.identity_hash_bytes_lower_bound,
            "identity_hash_bytes_upper_bound": self.identity_hash_bytes_upper_bound,
            "identity_hash_bytes_unconfirmed": self.identity_hash_bytes_unconfirmed,
            "exact": self.exact,
            "unresolved_operation": self.unresolved_operation,
            "unresolved_ordinal": self.unresolved_ordinal,
            "prefix_complete": self.prefix_complete,
            "result": "PASS",
        }


@dataclass(frozen=True)
class IdentityDescriptorDisposition:
    """Producer-local descriptors retired before a failure crosses the boundary."""

    opened: int
    closed: int
    close_failures: int
    retained_leases: int

    def __post_init__(self) -> None:
        values = (self.opened, self.closed, self.close_failures, self.retained_leases)
        if any(type(item) is not int or item < 0 for item in values):
            raise ValueError("identity descriptor disposition")
        if self.closed + self.close_failures + self.retained_leases > self.opened:
            raise ValueError("identity descriptor disposition census")

    @property
    def evidence(self) -> dict:
        return {
            "opened": self.opened,
            "closed": self.closed,
            "close_failures": self.close_failures,
            "retained_leases": self.retained_leases,
        }


@dataclass(frozen=True)
class IdentityAuthorityError(ValueError):
    outcome_id: str
    detail: str
    checkpoint_access: int | str = 0
    operation_observation: IdentityOperationObservation | None = None
    access_census: IdentityAccessCensus | None = None
    descriptor_disposition: IdentityDescriptorDisposition | None = None
    evidence_failure_type: str | None = None

    def __post_init__(self) -> None:
        if self.outcome_id not in OUTCOMES:
            raise ValueError("unmodeled identity-authority outcome")
        if type(self.detail) is not str or not self.detail:
            raise ValueError("identity-authority failure detail")
        if self.evidence_failure_type is not None and (
            type(self.evidence_failure_type) is not str
            or not self.evidence_failure_type
        ):
            raise ValueError("identity evidence failure type")

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
            "operation_observation": (
                self.operation_observation.evidence
                if self.operation_observation is not None
                else None
            ),
            "access_census": (
                self.access_census.evidence
                if self.access_census is not None
                else None
            ),
            "descriptor_disposition": (
                self.descriptor_disposition.evidence
                if self.descriptor_disposition is not None
                else None
            ),
            "evidence_failure_type": self.evidence_failure_type,
            "release_obligation": release_obligation,
            "terminal_evidence": terminal_evidence,
            "generic_fallback": False,
            "detail": self.detail,
            "result": "FAIL",
        }

    def __str__(self) -> str:
        return f"{self.outcome_id}: {self.detail}"


def failure(
    outcome_id: str,
    detail: str,
    *,
    checkpoint_access: int | str = 0,
    operation_observation: IdentityOperationObservation | None = None,
    access_census: IdentityAccessCensus | None = None,
    descriptor_disposition: IdentityDescriptorDisposition | None = None,
    evidence_failure_type: str | None = None,
) -> IdentityAuthorityError:
    return IdentityAuthorityError(
        outcome_id,
        detail,
        checkpoint_access,
        operation_observation,
        access_census,
        descriptor_disposition,
        evidence_failure_type,
    )


def with_failure_context(
    error: IdentityAuthorityError,
    *,
    access_census: IdentityAccessCensus,
    descriptor_disposition: IdentityDescriptorDisposition,
) -> IdentityAuthorityError:
    """Return the same modeled cause with validated durable-prefix context."""
    if type(error) is not IdentityAuthorityError:
        raise TypeError("identity authority failure context")
    return failure(
        error.outcome_id,
        error.detail,
        checkpoint_access="RECEIPT_DERIVED",
        operation_observation=error.operation_observation,
        access_census=access_census,
        descriptor_disposition=descriptor_disposition,
        evidence_failure_type=error.evidence_failure_type,
    )
