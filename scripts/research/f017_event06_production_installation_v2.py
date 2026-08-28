#!/usr/bin/env python3
"""Instantiable future-GO and production-installation boundary for Event 06.

This module contains a real success-capable producer/checker/transaction path.
Sequence 9 never supplies an accepted live GO and therefore never constructs a
production capability or invokes the production commit successfully.
"""

from __future__ import annotations

import copy
import hashlib
import pickle
import re
import time
from pathlib import Path
from typing import Final, Never, Self, SupportsIndex, cast

from f017_bounded_artifact_decode_v1 import parse_artifact_bytes
from f017_canonical_serialization_v10 import canonical_bytes
from f017_checkpoint_identity_authority_v12 import ValidatedIdentityAuthority
from f017_event06_durable_installation_transaction_v1 import (
    DurableTransactionResult,
    TransactionPayload,
    _commit_bound_production_transaction,
)
from f017_event06_execution_plan_v1 import ValidatedExecutionPlan
from f017_event06_production_installation_v1 import (
    FAILURE_OUTCOMES,
    PreparedProductionInstallation,
    ProductionInstallationError,
    _SealedDocument,
    prepare_production_installation,
    validate_prepared_production_installation,
)
from f017_event06_readiness_authority_v3 import (
    ValidatedEvent06ReadinessV3,
    _repository_delegate,
    assert_readiness_v3_sealed,
)

HEX64 = re.compile(r"[0-9a-f]{64}")
TYPED_ID = re.compile(r"[A-Z0-9](?:[A-Z0-9-]{0,190}[A-Z0-9])?")
_CAPABILITY_SEAL = object()

FUTURE_GO_SCHEMA: Final = "pulsarmlx.f017.event06-v12-future-human-go/2.0.0"
FUTURE_GO_DECISION: Final = "GO_FRESH_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_06"
FUTURE_GO_FIELDS: Final = {
    "schema",
    "decision",
    "live",
    "issued_at_unix_ns",
    "expires_at_unix_ns",
    "authorization_id",
    "package_attempt_id",
    "prepared_installation_sha256",
    "readiness_sha256",
    "target_parent",
    "target_leaf",
    "nonce_sha256",
    "attempts",
    "retries",
    "resume",
}


class FutureGoCapabilityV2:
    """Opaque one-shot capability produced only from an exact fresh live GO."""

    __slots__ = (
        "authorization_id",
        "package_attempt_id",
        "prepared_installation_sha256",
        "readiness_sha256",
        "target_parent",
        "target_leaf",
        "nonce_sha256",
        "expires_at_unix_ns",
        "source_sha256",
        "_locked",
    )
    authorization_id: str
    package_attempt_id: str
    prepared_installation_sha256: str
    readiness_sha256: str
    target_parent: Path
    target_leaf: str
    nonce_sha256: str
    expires_at_unix_ns: int
    source_sha256: str
    _locked: bool

    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _CAPABILITY_SEAL:
            raise TypeError("future Event 06 GO capabilities are producer-created")
        return super().__new__(cls)

    def __init__(self, seal: object, value: dict[str, object], raw: bytes) -> None:
        del seal
        object.__setattr__(
            self, "authorization_id", cast(str, value["authorization_id"])
        )
        object.__setattr__(
            self, "package_attempt_id", cast(str, value["package_attempt_id"])
        )
        object.__setattr__(
            self,
            "prepared_installation_sha256",
            cast(str, value["prepared_installation_sha256"]),
        )
        object.__setattr__(
            self, "readiness_sha256", cast(str, value["readiness_sha256"])
        )
        object.__setattr__(
            self, "target_parent", Path(cast(str, value["target_parent"]))
        )
        object.__setattr__(self, "target_leaf", cast(str, value["target_leaf"]))
        object.__setattr__(self, "nonce_sha256", cast(str, value["nonce_sha256"]))
        object.__setattr__(
            self, "expires_at_unix_ns", cast(int, value["expires_at_unix_ns"])
        )
        object.__setattr__(self, "source_sha256", hashlib.sha256(raw).hexdigest())
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> Never:
        del name, value
        raise TypeError("future Event 06 GO capabilities are immutable")

    def __copy__(self) -> Never:
        raise TypeError("future Event 06 GO capabilities cannot be copied")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("future Event 06 GO capabilities cannot be copied")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        del protocol
        raise TypeError("future Event 06 GO capabilities cannot be pickled")


_ISSUED_CAPABILITIES: dict[int, FutureGoCapabilityV2] = {}


def _prepared_sha256(prepared: PreparedProductionInstallation) -> str:
    return hashlib.sha256(
        prepared.payload("candidate")
        + prepared.payload("receipt")
        + prepared.payload("installed")
    ).hexdigest()


def _valid_leaf(value: object) -> bool:
    return (
        type(value) is str
        and bool(value)
        and value not in {".", ".."}
        and not value.startswith(".")
        and "/" not in value
        and "\\" not in value
    )


def _validate_future_go_value(
    value: object, raw: bytes, now_unix_ns: int
) -> dict[str, object]:
    if type(value) is not dict or set(value) != FUTURE_GO_FIELDS:
        raise ProductionInstallationError(
            FAILURE_OUTCOMES["go"], "future GO field census"
        )
    if canonical_bytes(value) != raw:
        raise ProductionInstallationError(
            FAILURE_OUTCOMES["go"], "future GO canonical bytes"
        )
    if (
        value.get("schema") != FUTURE_GO_SCHEMA
        or value.get("decision") != FUTURE_GO_DECISION
        or value.get("live") is not True
        or type(value.get("issued_at_unix_ns")) is not int
        or type(value.get("expires_at_unix_ns")) is not int
        or value["issued_at_unix_ns"] > now_unix_ns
        or value["expires_at_unix_ns"] <= now_unix_ns
        or value["issued_at_unix_ns"] >= value["expires_at_unix_ns"]
        or value.get("attempts") != 1
        or type(value.get("attempts")) is bool
        or value.get("retries") != 0
        or type(value.get("retries")) is bool
        or value.get("resume") is not False
    ):
        raise ProductionInstallationError(
            FAILURE_OUTCOMES["go"], "future GO posture or freshness"
        )
    for name in ("authorization_id", "package_attempt_id"):
        item = value.get(name)
        if type(item) is not str or TYPED_ID.fullmatch(item) is None:
            raise ProductionInstallationError(FAILURE_OUTCOMES["identity"], name)
    if value["authorization_id"] == value["package_attempt_id"]:
        raise ProductionInstallationError(
            FAILURE_OUTCOMES["identity"], "distinct identities"
        )
    for name in (
        "prepared_installation_sha256",
        "readiness_sha256",
        "nonce_sha256",
    ):
        item = value.get(name)
        if type(item) is not str or HEX64.fullmatch(item) is None:
            raise ProductionInstallationError(FAILURE_OUTCOMES["go"], name)
    parent = value.get("target_parent")
    if type(parent) is not str or not parent.startswith("/") or "\x00" in parent:
        raise ProductionInstallationError(FAILURE_OUTCOMES["target"], "target parent")
    if not _valid_leaf(value.get("target_leaf")):
        raise ProductionInstallationError(FAILURE_OUTCOMES["target"], "target leaf")
    return dict(value)


def produce_future_go_capability(
    raw: bytes,
    *,
    prepared: PreparedProductionInstallation,
    readiness: ValidatedEvent06ReadinessV3,
) -> FutureGoCapabilityV2:
    """Create a capability only after exact fresh live GO validation.

    Sequence 9 must not call this with an accepted live document.  The future
    human-GO graph supplies the exact bytes and consumes the returned capability
    once through :func:`commit_production_installation_v2`.
    """

    validate_prepared_production_installation(prepared)
    readiness = assert_readiness_v3_sealed(readiness)
    try:
        decoded = parse_artifact_bytes(raw)
    except Exception as exc:
        raise ProductionInstallationError(
            FAILURE_OUTCOMES["go"], "future GO decode"
        ) from exc
    value = _validate_future_go_value(decoded, raw, time.time_ns())
    if value["prepared_installation_sha256"] != _prepared_sha256(prepared):
        raise ProductionInstallationError(
            FAILURE_OUTCOMES["candidate"], "prepared binding"
        )
    if value["readiness_sha256"] != readiness.source_sha256:
        raise ProductionInstallationError(
            FAILURE_OUTCOMES["readiness"], "readiness binding"
        )
    parent = Path(cast(str, value["target_parent"]))
    try:
        identity = parent.lstat()
    except OSError as exc:
        raise ProductionInstallationError(
            FAILURE_OUTCOMES["target"], "target parent unavailable"
        ) from exc
    if parent.is_symlink() or not parent.is_dir() or identity.st_nlink < 1:
        raise ProductionInstallationError(
            FAILURE_OUTCOMES["target"], "target parent identity"
        )
    capability = FutureGoCapabilityV2(_CAPABILITY_SEAL, value, raw)
    _ISSUED_CAPABILITIES[id(capability)] = capability
    return capability


def inspect_future_go_shape_without_issuing(raw: bytes) -> str:
    """Validate rejection posture without ever constructing a capability."""

    try:
        decoded = parse_artifact_bytes(raw)
    except Exception as exc:
        raise ProductionInstallationError(
            FAILURE_OUTCOMES["go"], "future GO decode"
        ) from exc
    _validate_future_go_value(decoded, raw, time.time_ns())
    return "LIVE_GO_SHAPE_VALIDATED_CAPABILITY_NOT_ISSUED"


def prepare_production_installation_v2(
    readiness: ValidatedEvent06ReadinessV3,
    human_go: _SealedDocument,
    execution_plan: ValidatedExecutionPlan,
    approval: _SealedDocument,
    event_identity: _SealedDocument,
    candidate: ValidatedIdentityAuthority,
    checkpoint_census: _SealedDocument,
    integration: _SealedDocument,
) -> PreparedProductionInstallation:
    """Version-forward adapter retaining the Sequence 8 preparation semantics."""

    return prepare_production_installation(
        _repository_delegate(assert_readiness_v3_sealed(readiness)),
        human_go,
        execution_plan,
        approval,
        event_identity,
        candidate,
        checkpoint_census,
        integration,
    )


def validate_future_go_capability(
    capability: object,
    *,
    prepared: PreparedProductionInstallation,
) -> FutureGoCapabilityV2:
    if type(capability) is not FutureGoCapabilityV2:
        raise ProductionInstallationError(
            FAILURE_OUTCOMES["capability"], "sealed capability required"
        )
    if _ISSUED_CAPABILITIES.get(id(capability)) is not capability:
        raise ProductionInstallationError(
            FAILURE_OUTCOMES["capability"], "capability was not producer-issued"
        )
    validate_prepared_production_installation(prepared)
    if capability.expires_at_unix_ns <= time.time_ns():
        raise ProductionInstallationError(
            FAILURE_OUTCOMES["capability_expired"], "future GO expired"
        )
    if capability.prepared_installation_sha256 != _prepared_sha256(prepared):
        raise ProductionInstallationError(
            FAILURE_OUTCOMES["candidate"], "capability prepared binding"
        )
    return capability


def commit_production_installation_v2(
    prepared: PreparedProductionInstallation,
    capability: object,
) -> DurableTransactionResult:
    """Real success-capable production wrapper, unreachable without fresh GO."""

    validated = validate_future_go_capability(capability, prepared=prepared)
    if _ISSUED_CAPABILITIES.pop(id(validated), None) is not validated:
        raise ProductionInstallationError(
            FAILURE_OUTCOMES["capability"], "capability already consumed"
        )
    payloads = (
        TransactionPayload(
            "candidate", "candidate.json", prepared.payload("candidate")
        ),
        TransactionPayload(
            "receipt", "installation-receipt.json", prepared.payload("receipt")
        ),
        TransactionPayload(
            "installed", "installed-authorization.json", prepared.payload("installed")
        ),
    )
    marker = f"F017-CONSUMED-{validated.nonce_sha256}"
    return _commit_bound_production_transaction(
        validated.target_parent,
        validated.target_leaf,
        payloads,
        consumption_marker=marker,
    )


def assert_capability_sealed(value: FutureGoCapabilityV2) -> None:
    for operation in (copy.copy, copy.deepcopy, pickle.dumps):
        try:
            operation(value)
        except TypeError:
            continue
        raise TypeError("future GO capability copy surface")
