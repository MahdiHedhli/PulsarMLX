#!/usr/bin/env python3
"""Canonical live-GO and production-installation composition for Event 06.

The public producer/sealer path is success-capable only after a future human
GO.  Sequence 11 qualifies its exact bytes and signatures but never calls a
live sealer, capability producer, durable commit, or package boundary.
"""

from __future__ import annotations

# Superseded live build surface. Types and functions remain addressable only
# for historical qualification; no symbol here is current production authority.
__all__: tuple[str, ...] = ()

import copy
import hashlib
import pickle
import re
import time
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Final, Never, Self, SupportsIndex, cast

from f017_bounded_artifact_decode_v1 import parse_artifact_bytes
from f017_canonical_serialization_v10 import canonical_bytes
from f017_checkpoint_identity_authority_v12 import (
    ValidatedIdentityAuthority,
    installed_document,
    installed_expected,
    validate_candidate_bytes,
    validate_installed_bytes,
)
from f017_corrected_oracle_primary_wrapper_v12 import (
    validate_identity_authority as validate_primary,
)
from f017_corrected_oracle_secondary_wrapper_v12 import (
    validate_identity_authority as validate_secondary,
)
from f017_event06_durable_installation_transaction_v1 import (
    DurableTransactionResult,
    TransactionPayload,
    _commit_bound_production_transaction,
)
from f017_event06_execution_plan_v1 import ValidatedExecutionPlan
from f017_event06_live_go_contract_v3 import (
    APPROVAL_FIELDS,
    APPROVAL_SCHEMA,
    APPROVAL_TYPES,
    EVENT_IDENTITY_FIELDS,
    EVENT_IDENTITY_SCHEMA,
    EVENT_IDENTITY_TYPES,
    LIVE_GO_DECISION,
    LIVE_GO_FIELDS,
    LIVE_GO_SCHEMA,
    LIVE_GO_SCOPE,
    LIVE_GO_TYPES,
)
from f017_event06_production_installation_v1 import (
    _SealedDocument,
    installation_failure,
)
from f017_event06_readiness_authority_v3 import (
    ValidatedEvent06ReadinessV3,
    assert_readiness_v3_sealed,
)

ROOT: Final = Path(__file__).resolve().parents[2]
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
TYPED_ID = re.compile(r"[A-Z0-9](?:[A-Z0-9-]{0,190}[A-Z0-9])?")
_LIVE_GO_SEAL = object()
_APPROVAL_SEAL = object()
_IDENTITY_SEAL = object()
_PREPARED_SEAL = object()
_CAPABILITY_SEAL = object()

PREPARATION_RECEIPT_SCHEMA: Final = (
    "pulsarmlx.f017.event06-v12-production-installation-preparation-receipt/3.1.0"
)
PREPARATION_RECEIPT_FIELDS: Final = (
    "schema",
    "candidate_sha256",
    "readiness_sha256",
    "live_go_envelope_sha256",
    "operator_approval_sha256",
    "execution_plan_sha256",
    "event_identity_plan_sha256",
    "prompt_repository_commit",
    "prompt_repository_path",
    "prompt_sha256",
    "checkpoint_census_sha256",
    "integration_sha256",
    "authorization_id",
    "package_attempt_id",
    "target_parent",
    "target_leaf",
    "nonce_sha256",
    "expires_at_unix_ns",
    "state",
    "live_authority",
    "result",
)
PREPARATION_RECEIPT_TYPES: Final = {
    "schema": "str",
    "candidate_sha256": "sha256",
    "readiness_sha256": "sha256",
    "live_go_envelope_sha256": "sha256",
    "operator_approval_sha256": "sha256",
    "execution_plan_sha256": "sha256",
    "event_identity_plan_sha256": "sha256",
    "prompt_repository_commit": "git_object",
    "prompt_repository_path": "repository_path",
    "prompt_sha256": "sha256",
    "checkpoint_census_sha256": "sha256",
    "integration_sha256": "sha256",
    "authorization_id": "typed_id",
    "package_attempt_id": "typed_id",
    "target_parent": "absolute_path",
    "target_leaf": "safe_leaf",
    "nonce_sha256": "sha256",
    "expires_at_unix_ns": "non_boolean_integer",
    "state": "str",
    "live_authority": "bool",
    "result": "str",
}


def _freeze(value: object) -> object:
    if type(value) is dict:
        return tuple((key, _freeze(value[key])) for key in sorted(value))
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: object) -> object:
    if type(value) is tuple:
        if value and all(
            type(item) is tuple and len(item) == 2 and type(item[0]) is str
            for item in value
        ):
            return {key: _thaw(item) for key, item in value}
        return [_thaw(item) for item in value]
    return value


class _ClosedDocument:
    __slots__ = ("_items", "_locked", "kind", "source_sha256")
    _items: tuple[tuple[str, object], ...]
    source_sha256: str
    kind: str
    _locked: bool

    def _initialize(self, value: dict[str, object], raw: bytes, kind: str) -> None:
        object.__setattr__(
            self, "_items", cast(tuple[tuple[str, object], ...], _freeze(value))
        )
        object.__setattr__(self, "source_sha256", hashlib.sha256(raw).hexdigest())
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> Never:
        del name, value
        raise TypeError("live installation documents are immutable")

    def __delattr__(self, name: str) -> Never:
        del name
        raise TypeError("live installation documents cannot delete attributes")

    def get(self, key: str) -> object:
        for name, value in self._items:
            if name == key:
                return _thaw(value)
        raise KeyError(key)

    def __copy__(self) -> Never:
        raise TypeError("live installation documents cannot be copied")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("live installation documents cannot be copied")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        del protocol
        raise TypeError("live installation documents cannot be pickled")


class LiveHumanGoV3(_ClosedDocument):
    __slots__ = ()

    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _LIVE_GO_SEAL:
            raise TypeError("live human-GO documents are producer-created")
        return super().__new__(cls)

    def __init__(self, seal: object, value: dict[str, object], raw: bytes) -> None:
        del seal
        self._initialize(value, raw, "LIVE_GO")


class LiveOperatorApprovalV3(_ClosedDocument):
    __slots__ = ()

    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _APPROVAL_SEAL:
            raise TypeError("live approvals are producer-created")
        return super().__new__(cls)

    def __init__(self, seal: object, value: dict[str, object], raw: bytes) -> None:
        del seal
        self._initialize(value, raw, "LIVE_APPROVAL")


class PromptBoundEventIdentityPlanV2(_ClosedDocument):
    __slots__ = ()

    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _IDENTITY_SEAL:
            raise TypeError("prompt-bound identity plans are producer-created")
        return super().__new__(cls)

    def __init__(self, seal: object, value: dict[str, object], raw: bytes) -> None:
        del seal
        self._initialize(value, raw, "PROMPT_BOUND_EVENT_IDENTITY")


def _safe_leaf(value: object) -> bool:
    return (
        type(value) is str
        and bool(value)
        and value not in {".", ".."}
        and not value.startswith(".")
        and "/" not in value
        and "\\" not in value
    )


def _repo_path(value: object) -> bool:
    if type(value) is not str or not value or value.startswith("/") or "\\" in value:
        return False
    parts = PurePosixPath(value).parts
    return bool(parts) and all(part not in {"", ".", ".."} for part in parts)


def _exact_type(value: object, category: str) -> bool:
    if category == "str":
        return type(value) is str
    if category == "bool":
        return type(value) is bool
    if category == "sha256":
        return type(value) is str and HEX64.fullmatch(value) is not None
    if category == "git_object":
        return type(value) is str and HEX40.fullmatch(value) is not None
    if category == "typed_id":
        return type(value) is str and TYPED_ID.fullmatch(value) is not None
    if category == "non_boolean_integer":
        return type(value) is int
    if category == "absolute_path":
        return (
            type(value) is str
            and Path(value).is_absolute()
            and ".." not in Path(value).parts
        )
    if category == "safe_leaf":
        return _safe_leaf(value)
    if category == "repository_path":
        return _repo_path(value)
    raise ValueError(f"unknown exact type category: {category}")


def _decode_exact(
    raw: bytes,
    *,
    fields: tuple[str, ...],
    types: dict[str, str],
    schema: str,
    kind: str,
) -> dict[str, object]:
    try:
        value = parse_artifact_bytes(raw)
    except Exception as exc:
        raise installation_failure("input", f"{kind} bounded decode") from exc
    if type(value) is not dict or set(value) != set(fields):
        raise installation_failure("input", f"{kind} field census")
    if value.get("schema") != schema or canonical_bytes(value) != raw:
        raise installation_failure("input", f"{kind} schema or canonical bytes")
    for name in fields:
        if not _exact_type(value[name], types[name]):
            raise installation_failure("input", f"{kind} exact type: {name}")
    return value


def _validate_live_go_value(raw: bytes, *, now_unix_ns: int) -> dict[str, object]:
    value = _decode_exact(
        raw,
        fields=LIVE_GO_FIELDS,
        types=LIVE_GO_TYPES,
        schema=LIVE_GO_SCHEMA,
        kind="LIVE_GO",
    )
    issued_at = cast(int, value["issued_at_unix_ns"])
    expires_at = cast(int, value["expires_at_unix_ns"])
    if (
        value["decision"] != LIVE_GO_DECISION
        or value["live"] is not True
        or value["scope"] != LIVE_GO_SCOPE
        or value["attempts"] != 1
        or value["retries"] != 0
        or value["resume"] is not False
        or issued_at > now_unix_ns
        or expires_at <= now_unix_ns
        or issued_at >= expires_at
    ):
        raise installation_failure("go", "live GO predicate")
    return value


def inspect_live_go_envelope_without_sealing(
    raw: bytes,
    *,
    now_unix_ns: int,
    expected_raw_human_go_sha256: str,
    expected_authorization_id: str,
    expected_package_attempt_id: str,
    expected_readiness_sha256: str,
    expected_target_parent: str,
    expected_target_leaf: str,
    expected_issued_at_unix_ns: int,
    expected_expires_at_unix_ns: int,
    expected_nonce_sha256: str,
) -> MappingProxyType[str, object]:
    """Validate canonical live bytes without producing a live authority object."""

    value = _validate_live_go_value(raw, now_unix_ns=now_unix_ns)
    expected = {
        "raw_human_go_sha256": expected_raw_human_go_sha256,
        "authorization_id": expected_authorization_id,
        "package_attempt_id": expected_package_attempt_id,
        "readiness_sha256": expected_readiness_sha256,
        "target_parent": expected_target_parent,
        "target_leaf": expected_target_leaf,
        "issued_at_unix_ns": expected_issued_at_unix_ns,
        "expires_at_unix_ns": expected_expires_at_unix_ns,
        "nonce_sha256": expected_nonce_sha256,
    }
    if any(value[name] != expected_value for name, expected_value in expected.items()):
        raise installation_failure("go", "live GO expected binding")
    return MappingProxyType(dict(value))


def render_live_go_envelope(
    raw_human_go: bytes,
    *,
    authorization_id: str,
    package_attempt_id: str,
    readiness_sha256: str,
    target_parent: Path,
    target_leaf: str,
    issued_at_unix_ns: int,
    expires_at_unix_ns: int,
    nonce_sha256: str,
) -> bytes:
    """Future-only pure producer; it does not seal, install, or consume authority."""

    return cast(
        bytes,
        canonical_bytes(
            {
                "schema": LIVE_GO_SCHEMA,
                "decision": LIVE_GO_DECISION,
                "live": True,
                "raw_human_go_sha256": hashlib.sha256(raw_human_go).hexdigest(),
                "authorization_id": authorization_id,
                "package_attempt_id": package_attempt_id,
                "readiness_sha256": readiness_sha256,
                "target_parent": target_parent.as_posix(),
                "target_leaf": target_leaf,
                "issued_at_unix_ns": issued_at_unix_ns,
                "expires_at_unix_ns": expires_at_unix_ns,
                "nonce_sha256": nonce_sha256,
                "scope": LIVE_GO_SCOPE,
                "attempts": 1,
                "retries": 0,
                "resume": False,
            }
        ),
    )


def seal_live_go_envelope(
    raw: bytes, raw_human_go: bytes, *, now_unix_ns: int | None = None
) -> LiveHumanGoV3:
    value = _validate_live_go_value(
        raw, now_unix_ns=time.time_ns() if now_unix_ns is None else now_unix_ns
    )
    if value["raw_human_go_sha256"] != hashlib.sha256(raw_human_go).hexdigest():
        raise installation_failure("go", "raw human GO binding")
    return LiveHumanGoV3(_LIVE_GO_SEAL, value, raw)


def _validate_identity_value(
    raw: bytes,
    *,
    prompt_bytes: bytes,
    prompt_repository_commit: str,
    prompt_repository_path: str,
) -> dict[str, object]:
    value = _decode_exact(
        raw,
        fields=EVENT_IDENTITY_FIELDS,
        types=EVENT_IDENTITY_TYPES,
        schema=EVENT_IDENTITY_SCHEMA,
        kind="EVENT_IDENTITY",
    )
    identities = [
        value["authorization_id"],
        value["package_attempt_id"],
        value["primary_event_id"],
        value["secondary_event_id"],
    ]
    if len(set(identities)) != 4:
        raise installation_failure("identity", "event identities must be distinct")
    if (
        value["prompt_repository_commit"] != prompt_repository_commit
        or value["prompt_repository_path"] != prompt_repository_path
        or value["prompt_sha256"] != hashlib.sha256(prompt_bytes).hexdigest()
    ):
        raise installation_failure("identity", "prompt binding")
    return value


def inspect_prompt_bound_event_identity_plan_without_sealing(
    raw: bytes,
    *,
    prompt_bytes: bytes,
    prompt_repository_commit: str,
    prompt_repository_path: str,
    expected_authorization_id: str,
    expected_package_attempt_id: str,
    expected_primary_event_id: str,
    expected_secondary_event_id: str,
    expected_execution_plan_sha256: str,
) -> MappingProxyType[str, object]:
    value = _validate_identity_value(
        raw,
        prompt_bytes=prompt_bytes,
        prompt_repository_commit=prompt_repository_commit,
        prompt_repository_path=prompt_repository_path,
    )
    expected = {
        "authorization_id": expected_authorization_id,
        "package_attempt_id": expected_package_attempt_id,
        "primary_event_id": expected_primary_event_id,
        "secondary_event_id": expected_secondary_event_id,
        "execution_plan_sha256": expected_execution_plan_sha256,
    }
    if any(value[name] != expected_value for name, expected_value in expected.items()):
        raise installation_failure("identity", "event identity expected binding")
    return MappingProxyType(dict(value))


def seal_prompt_bound_event_identity_plan(
    raw: bytes,
    *,
    prompt_bytes: bytes,
    prompt_repository_commit: str,
    prompt_repository_path: str,
) -> PromptBoundEventIdentityPlanV2:
    value = _validate_identity_value(
        raw,
        prompt_bytes=prompt_bytes,
        prompt_repository_commit=prompt_repository_commit,
        prompt_repository_path=prompt_repository_path,
    )
    return PromptBoundEventIdentityPlanV2(_IDENTITY_SEAL, value, raw)


def _validate_approval_value(raw: bytes) -> dict[str, object]:
    value = _decode_exact(
        raw,
        fields=APPROVAL_FIELDS,
        types=APPROVAL_TYPES,
        schema=APPROVAL_SCHEMA,
        kind="APPROVAL",
    )
    if (
        value["live"] is not True
        or value["attempts"] != 1
        or value["retries"] != 0
        or value["resume"] is not False
    ):
        raise installation_failure("go", "approval one-shot posture")
    return value


def inspect_live_operator_approval_without_sealing(
    raw: bytes,
    *,
    expected_live_go_envelope_sha256: str,
    expected_readiness_sha256: str,
    expected_authorization_id: str,
    expected_package_attempt_id: str,
    expected_execution_plan_sha256: str,
    expected_event_identity_plan_sha256: str,
    expected_candidate_sha256: str,
) -> MappingProxyType[str, object]:
    value = _validate_approval_value(raw)
    expected = {
        "live_go_envelope_sha256": expected_live_go_envelope_sha256,
        "readiness_sha256": expected_readiness_sha256,
        "authorization_id": expected_authorization_id,
        "package_attempt_id": expected_package_attempt_id,
        "execution_plan_sha256": expected_execution_plan_sha256,
        "event_identity_plan_sha256": expected_event_identity_plan_sha256,
        "candidate_sha256": expected_candidate_sha256,
    }
    if any(value[name] != expected_value for name, expected_value in expected.items()):
        raise installation_failure("go", "approval expected binding")
    return MappingProxyType(dict(value))


def seal_live_operator_approval(
    raw: bytes,
    *,
    live_go: LiveHumanGoV3,
    readiness: ValidatedEvent06ReadinessV3,
    execution_plan: ValidatedExecutionPlan,
    event_identity: PromptBoundEventIdentityPlanV2,
    candidate: ValidatedIdentityAuthority,
) -> LiveOperatorApprovalV3:
    value = _validate_approval_value(raw)
    candidate_raw = canonical_bytes(candidate.as_dict())
    checks = (
        (value["live_go_envelope_sha256"], live_go.source_sha256),
        (value["readiness_sha256"], readiness.source_sha256),
        (value["authorization_id"], candidate.get("authorization_id")),
        (value["package_attempt_id"], candidate.get("package_attempt_id")),
        (value["execution_plan_sha256"], execution_plan.sha256),
        (value["event_identity_plan_sha256"], event_identity.source_sha256),
        (value["candidate_sha256"], hashlib.sha256(candidate_raw).hexdigest()),
    )
    if any(observed != expected for observed, expected in checks):
        raise installation_failure("go", "approval dependency binding")
    return LiveOperatorApprovalV3(_APPROVAL_SEAL, value, raw)


class PreparedProductionInstallationV3:
    __slots__ = (
        "_candidate",
        "_installed",
        "_locked",
        "_receipt",
        "candidate_sha256",
        "installed_sha256",
        "posture",
        "prepared_sha256",
        "receipt_sha256",
    )
    _candidate: bytes
    _installed: bytes
    _locked: bool
    _receipt: bytes
    candidate_sha256: str
    installed_sha256: str
    posture: str
    prepared_sha256: str
    receipt_sha256: str

    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _PREPARED_SEAL:
            raise TypeError("prepared installations V3 are repository-created")
        return super().__new__(cls)

    def __init__(
        self, seal: object, candidate: bytes, receipt: bytes, installed: bytes
    ) -> None:
        del seal
        object.__setattr__(self, "_candidate", candidate)
        object.__setattr__(self, "_receipt", receipt)
        object.__setattr__(self, "_installed", installed)
        object.__setattr__(
            self, "candidate_sha256", hashlib.sha256(candidate).hexdigest()
        )
        object.__setattr__(self, "receipt_sha256", hashlib.sha256(receipt).hexdigest())
        object.__setattr__(
            self, "installed_sha256", hashlib.sha256(installed).hexdigest()
        )
        object.__setattr__(
            self,
            "prepared_sha256",
            hashlib.sha256(candidate + receipt + installed).hexdigest(),
        )
        object.__setattr__(self, "posture", "PREPARED_PRODUCTION_INSTALLATION")
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> Never:
        del name, value
        raise TypeError("prepared installations V3 are immutable")

    def __delattr__(self, name: str) -> Never:
        del name
        raise TypeError("prepared installations V3 cannot delete attributes")

    def payload(self, role: str) -> bytes:
        payloads: dict[str, bytes] = {
            "candidate": self._candidate,
            "receipt": self._receipt,
            "installed": self._installed,
        }
        return payloads[role]

    def __copy__(self) -> Never:
        raise TypeError("prepared installations V3 cannot be copied")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("prepared installations V3 cannot be copied")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        del protocol
        raise TypeError("prepared installations V3 cannot be pickled")


def _candidate_triple(candidate: ValidatedIdentityAuthority) -> bytes:
    if (
        type(candidate) is not ValidatedIdentityAuthority
        or candidate.posture != "CANDIDATE"
    ):
        raise installation_failure("candidate", "sealed candidate posture")
    reports = (
        validate_primary(candidate, posture="CANDIDATE"),
        validate_secondary(candidate, posture="CANDIDATE"),
    )
    if candidate.get("authority_scope") != "PRODUCTION" or any(
        report.get("result") != "PASS" for report in reports
    ):
        raise installation_failure("candidate", "consumer candidate validation")
    return cast(bytes, canonical_bytes(candidate.as_dict()))


def prepare_production_installation_v3(
    readiness: ValidatedEvent06ReadinessV3,
    human_go: LiveHumanGoV3,
    execution_plan: ValidatedExecutionPlan,
    approval: LiveOperatorApprovalV3,
    event_identity: PromptBoundEventIdentityPlanV2,
    candidate: ValidatedIdentityAuthority,
    checkpoint_census: _SealedDocument,
    integration: _SealedDocument,
) -> PreparedProductionInstallationV3:
    assert_readiness_v3_sealed(readiness)
    if (
        type(human_go) is not LiveHumanGoV3
        or type(approval) is not LiveOperatorApprovalV3
    ):
        raise installation_failure("go", "exact live GO and approval types")
    if type(execution_plan) is not ValidatedExecutionPlan:
        raise installation_failure("plan", "sealed execution plan")
    if type(event_identity) is not PromptBoundEventIdentityPlanV2:
        raise installation_failure("identity", "prompt-bound event identity type")
    if (
        type(checkpoint_census) is not _SealedDocument
        or checkpoint_census.kind != "CHECKPOINT_CENSUS"
    ):
        raise installation_failure("input", "sealed checkpoint census")
    if type(integration) is not _SealedDocument or integration.kind != "INTEGRATION":
        raise installation_failure("input", "sealed integration authority")
    candidate_raw = _candidate_triple(candidate)
    candidate_sha = hashlib.sha256(candidate_raw).hexdigest()
    checks = (
        (human_go.get("readiness_sha256"), readiness.source_sha256, "GO readiness"),
        (
            human_go.get("authorization_id"),
            candidate.get("authorization_id"),
            "GO authorization",
        ),
        (
            human_go.get("package_attempt_id"),
            candidate.get("package_attempt_id"),
            "GO package",
        ),
        (
            approval.get("live_go_envelope_sha256"),
            human_go.source_sha256,
            "approval GO",
        ),
        (
            approval.get("readiness_sha256"),
            readiness.source_sha256,
            "approval readiness",
        ),
        (approval.get("execution_plan_sha256"), execution_plan.sha256, "approval plan"),
        (
            approval.get("event_identity_plan_sha256"),
            event_identity.source_sha256,
            "approval identity",
        ),
        (approval.get("candidate_sha256"), candidate_sha, "approval candidate"),
        (
            event_identity.get("execution_plan_sha256"),
            execution_plan.sha256,
            "identity plan",
        ),
        (
            event_identity.get("authorization_id"),
            candidate.get("authorization_id"),
            "identity authorization",
        ),
        (
            event_identity.get("package_attempt_id"),
            execution_plan.get("package_attempt_id"),
            "identity package",
        ),
        (
            event_identity.get("primary_event_id"),
            execution_plan.get("primary_event_id"),
            "primary event",
        ),
        (
            event_identity.get("secondary_event_id"),
            execution_plan.get("secondary_event_id"),
            "secondary event",
        ),
        (
            candidate.get("event_identity_plan_sha256"),
            event_identity.source_sha256,
            "candidate identity",
        ),
        (
            checkpoint_census.get("checkpoint_set_sha256"),
            candidate.get("checkpoint_set_sha256"),
            "checkpoint set",
        ),
        (
            checkpoint_census.sha256,
            integration.get("checkpoint_census_sha256"),
            "checkpoint census",
        ),
        (candidate_sha, integration.get("candidate_sha256"), "integration candidate"),
        (
            execution_plan.get("source_head"),
            integration.get("source_head"),
            "source head",
        ),
        (
            execution_plan.get("source_tree"),
            integration.get("source_tree"),
            "source tree",
        ),
        (
            execution_plan.get("implementation_measurement_sha256"),
            integration.get("implementation_measurement_sha256"),
            "measurement",
        ),
        (
            execution_plan.get("numerical_contract_sha256"),
            integration.get("numerical_contract_sha256"),
            "numerical contract",
        ),
        (
            execution_plan.get("result_authority_sha256"),
            integration.get("result_authority_sha256"),
            "result authority",
        ),
    )
    for observed, expected, detail in checks:
        if observed != expected:
            raise installation_failure("input", detail)
    receipt = canonical_bytes(
        {
            "schema": PREPARATION_RECEIPT_SCHEMA,
            "candidate_sha256": candidate_sha,
            "readiness_sha256": readiness.source_sha256,
            "live_go_envelope_sha256": human_go.source_sha256,
            "operator_approval_sha256": approval.source_sha256,
            "execution_plan_sha256": execution_plan.sha256,
            "event_identity_plan_sha256": event_identity.source_sha256,
            "prompt_repository_commit": event_identity.get("prompt_repository_commit"),
            "prompt_repository_path": event_identity.get("prompt_repository_path"),
            "prompt_sha256": event_identity.get("prompt_sha256"),
            "checkpoint_census_sha256": checkpoint_census.sha256,
            "integration_sha256": integration.sha256,
            "authorization_id": candidate.get("authorization_id"),
            "package_attempt_id": candidate.get("package_attempt_id"),
            "target_parent": human_go.get("target_parent"),
            "target_leaf": human_go.get("target_leaf"),
            "nonce_sha256": human_go.get("nonce_sha256"),
            "expires_at_unix_ns": human_go.get("expires_at_unix_ns"),
            "state": "PREPARED_PRODUCTION_INSTALLATION",
            "live_authority": False,
            "result": "PASS",
        }
    )
    installed = canonical_bytes(
        installed_document(candidate, hashlib.sha256(receipt).hexdigest())
    )
    return PreparedProductionInstallationV3(
        _PREPARED_SEAL, candidate_raw, receipt, installed
    )


def validate_prepared_production_installation_v3(
    prepared: PreparedProductionInstallationV3,
) -> PreparedProductionInstallationV3:
    if (
        type(prepared) is not PreparedProductionInstallationV3
        or prepared.posture != "PREPARED_PRODUCTION_INSTALLATION"
    ):
        raise installation_failure("posture", "prepared installation V3")
    candidate = validate_candidate_bytes(prepared.payload("candidate"))
    receipt = _decode_exact(
        prepared.payload("receipt"),
        fields=PREPARATION_RECEIPT_FIELDS,
        types=PREPARATION_RECEIPT_TYPES,
        schema=PREPARATION_RECEIPT_SCHEMA,
        kind="PREPARATION_RECEIPT",
    )
    if (
        receipt.get("state") != "PREPARED_PRODUCTION_INSTALLATION"
        or receipt.get("live_authority") is not False
        or receipt.get("result") != "PASS"
        or receipt.get("candidate_sha256") != candidate.source_sha256
        or hashlib.sha256(prepared.payload("receipt")).hexdigest()
        != prepared.receipt_sha256
    ):
        raise installation_failure("receipt", "prepared receipt V3")
    installed = validate_installed_bytes(
        prepared.payload("installed"), installed_expected(candidate)
    )
    if installed.get("installation_receipt_sha256") != prepared.receipt_sha256:
        raise installation_failure("readback", "prepared installed V3")
    return prepared


class FutureGoCapabilityV3:
    __slots__ = (
        "_locked",
        "authorization_id",
        "expires_at_unix_ns",
        "live_go_sha256",
        "nonce_sha256",
        "package_attempt_id",
        "prepared_sha256",
        "target_leaf",
        "target_parent",
    )
    _locked: bool
    authorization_id: str
    expires_at_unix_ns: int
    live_go_sha256: str
    nonce_sha256: str
    package_attempt_id: str
    prepared_sha256: str
    target_leaf: str
    target_parent: Path

    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _CAPABILITY_SEAL:
            raise TypeError("future GO capabilities V3 are producer-created")
        return super().__new__(cls)

    def __init__(
        self,
        seal: object,
        prepared: PreparedProductionInstallationV3,
    ) -> None:
        del seal
        receipt = cast(
            dict[str, object], parse_artifact_bytes(prepared.payload("receipt"))
        )
        object.__setattr__(
            self, "authorization_id", cast(str, receipt["authorization_id"])
        )
        object.__setattr__(
            self, "package_attempt_id", cast(str, receipt["package_attempt_id"])
        )
        object.__setattr__(
            self, "live_go_sha256", cast(str, receipt["live_go_envelope_sha256"])
        )
        object.__setattr__(self, "prepared_sha256", prepared.prepared_sha256)
        object.__setattr__(
            self, "target_parent", Path(cast(str, receipt["target_parent"]))
        )
        object.__setattr__(self, "target_leaf", cast(str, receipt["target_leaf"]))
        object.__setattr__(self, "nonce_sha256", cast(str, receipt["nonce_sha256"]))
        object.__setattr__(
            self, "expires_at_unix_ns", cast(int, receipt["expires_at_unix_ns"])
        )
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> Never:
        del name, value
        raise TypeError("future GO capabilities V3 are immutable")

    def __delattr__(self, name: str) -> Never:
        del name
        raise TypeError("future GO capabilities V3 cannot delete attributes")

    def __copy__(self) -> Never:
        raise TypeError("future GO capabilities V3 cannot be copied")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("future GO capabilities V3 cannot be copied")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        del protocol
        raise TypeError("future GO capabilities V3 cannot be pickled")


_ISSUED_CAPABILITIES: dict[int, FutureGoCapabilityV3] = {}


def _qualification_produce_future_go_capability_v3(
    prepared: PreparedProductionInstallationV3,
) -> FutureGoCapabilityV3:
    validate_prepared_production_installation_v3(prepared)
    receipt = cast(dict[str, object], parse_artifact_bytes(prepared.payload("receipt")))
    if cast(int, receipt["expires_at_unix_ns"]) <= time.time_ns():
        raise installation_failure(
            "capability_expired", "capability dependency binding"
        )
    capability = FutureGoCapabilityV3(_CAPABILITY_SEAL, prepared)
    _ISSUED_CAPABILITIES[id(capability)] = capability
    return capability


def produce_future_go_capability_v3(
    prepared: PreparedProductionInstallationV3,
) -> FutureGoCapabilityV3:
    """Fail closed: the V3 live capability issuer is superseded."""
    del prepared
    raise RuntimeError("superseded by F017 Sequence 39 minimum-gate path")


def validate_future_go_capability_v3(
    capability: object,
    *,
    prepared: PreparedProductionInstallationV3,
) -> FutureGoCapabilityV3:
    if (
        type(capability) is not FutureGoCapabilityV3
        or _ISSUED_CAPABILITIES.get(id(capability)) is not capability
    ):
        raise installation_failure("capability", "producer-issued capability required")
    validate_prepared_production_installation_v3(prepared)
    if capability.prepared_sha256 != prepared.prepared_sha256:
        raise installation_failure("candidate", "capability prepared binding")
    if capability.expires_at_unix_ns <= time.time_ns():
        raise installation_failure("capability_expired", "future GO capability expired")
    return capability


def _qualification_commit_production_installation_v3(
    prepared: PreparedProductionInstallationV3,
    capability: FutureGoCapabilityV3,
) -> DurableTransactionResult:
    validated = validate_future_go_capability_v3(capability, prepared=prepared)
    if _ISSUED_CAPABILITIES.pop(id(validated), None) is not validated:
        raise installation_failure("replay", "future GO capability already consumed")
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
    return _commit_bound_production_transaction(
        validated.target_parent,
        validated.target_leaf,
        payloads,
        consumption_marker=f"consumed-{validated.nonce_sha256[:16]}",
    )


def commit_production_installation_v3(
    prepared: PreparedProductionInstallationV3,
    capability: FutureGoCapabilityV3,
) -> DurableTransactionResult:
    """Fail closed: superseded V3 installation cannot mint live authority."""
    del prepared, capability
    raise RuntimeError("superseded by F017 Sequence 39 minimum-gate path")


def assert_closed_security_surface(*values: object) -> None:
    for value in values:
        for operation in (copy.copy, copy.deepcopy, pickle.dumps):
            try:
                operation(value)
            except TypeError:
                continue
            raise TypeError("live call-path copy surface")
