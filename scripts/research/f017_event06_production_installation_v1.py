#!/usr/bin/env python3
"""Production-shaped, validation-only Event 06 V12 installation boundary."""

from __future__ import annotations

import copy
import hashlib
import re
from pathlib import Path
from typing import Any, Final, Never, Self, SupportsIndex, cast

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
from f017_event06_execution_plan_v1 import ValidatedExecutionPlan
from f017_event06_readiness_authority_v2 import ValidatedEvent06ReadinessV2

ROOT: Final = Path(__file__).resolve().parents[2]
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
TYPED_ID = re.compile(r"[A-Z0-9](?:[A-Z0-9-]{0,190}[A-Z0-9])?")
_DOCUMENT_SEAL = object()
_PREPARED_SEAL = object()
_GATE_SEAL = object()

FAILURE_OUTCOMES: Final = {
    "candidate": "F017_V12_PRODUCTION_INSTALL_CANDIDATE_MISMATCH",
    "capability": "F017_V12_PRODUCTION_INSTALL_CAPABILITY_REQUIRED",
    "capability_expired": "F017_V12_PRODUCTION_INSTALL_CAPABILITY_EXPIRED",
    "fsync": "F017_V12_PRODUCTION_INSTALL_FSYNC_FAILURE",
    "go": "F017_V12_PRODUCTION_INSTALL_GO_MISMATCH",
    "identity": "F017_V12_PRODUCTION_INSTALL_IDENTITY_MISMATCH",
    "input": "F017_V12_PRODUCTION_INSTALL_INPUT_MISMATCH",
    "partial": "F017_V12_PRODUCTION_INSTALL_PARTIAL_COMMIT",
    "plan": "F017_V12_PRODUCTION_INSTALL_PLAN_MISMATCH",
    "posture": "F017_V12_PRODUCTION_INSTALL_POSTURE_MISMATCH",
    "readback": "F017_V12_PRODUCTION_INSTALL_READBACK_MISMATCH",
    "readiness": "F017_V12_PRODUCTION_INSTALL_READINESS_MISMATCH",
    "receipt": "F017_V12_PRODUCTION_INSTALL_RECEIPT_MISMATCH",
    "replay": "F017_V12_PRODUCTION_INSTALL_REPLAY",
    "target": "F017_V12_PRODUCTION_INSTALL_TARGET_EXISTS",
    "write": "F017_V12_PRODUCTION_INSTALL_WRITE_FAILURE",
}


class ProductionInstallationError(ValueError):
    """Exact modeled terminal outcome for production installation preparation."""

    def __init__(self, outcome_id: str, detail: str):
        super().__init__(f"{outcome_id}: {detail}")
        self.outcome_id = outcome_id
        self.detail = detail


def installation_failure(category: str, detail: str) -> ProductionInstallationError:
    if type(category) is not str or category not in FAILURE_OUTCOMES:
        raise ValueError("unknown Event 06 installation failure category")
    return ProductionInstallationError(FAILURE_OUTCOMES[category], detail)


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


class _SealedDocument:
    __slots__ = ("_items", "sha256", "kind", "_locked")
    _items: tuple[tuple[str, object], ...]
    sha256: str
    kind: str
    _locked: bool

    def __new__(
        cls, seal: object = None, value: object = None, kind: object = None
    ) -> Self:
        if seal is not _DOCUMENT_SEAL:
            raise TypeError("installation inputs are validator-created")
        return super().__new__(cls)

    def __init__(self, seal: object, value: dict[str, object], kind: str) -> None:
        del seal
        object.__setattr__(
            self, "_items", cast(tuple[tuple[str, object], ...], _freeze(value))
        )
        object.__setattr__(
            self, "sha256", hashlib.sha256(canonical_bytes(value)).hexdigest()
        )
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise TypeError("installation inputs are immutable")

    def get(self, key: str) -> object:
        for name, value in self._items:
            if name == key:
                return _thaw(value)
        raise KeyError(key)

    def __copy__(self) -> Never:
        raise TypeError("installation inputs cannot be copied")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("installation inputs cannot be copied")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        del protocol
        raise TypeError("installation inputs cannot be pickled")


DOCUMENT_RULES: Final[dict[str, dict[str, Any]]] = {
    "GO": {
        "schema": "pulsarmlx.f017.event06-v12-inert-human-go/1.0.0",
        "keys": {
            "schema",
            "decision",
            "live",
            "authorization_id",
            "package_attempt_id",
            "issued_at_unix_ns",
            "expires_at_unix_ns",
            "nonce_sha256",
        },
    },
    "APPROVAL": {
        "schema": "pulsarmlx.f017.event06-v12-inert-operator-approval/1.0.0",
        "keys": {
            "schema",
            "human_go_sha256",
            "authorization_id",
            "package_attempt_id",
            "event_identity_plan_sha256",
            "execution_plan_sha256",
            "candidate_sha256",
            "live",
            "attempts",
            "retries",
            "resume",
        },
    },
    "EVENT_IDENTITY": {
        "schema": "pulsarmlx.f017.event06-event-identity-plan/1.0.0",
        "keys": {
            "schema",
            "package_attempt_id",
            "primary_event_id",
            "secondary_event_id",
            "execution_plan_sha256",
        },
    },
    "CHECKPOINT_CENSUS": {
        "schema": "pulsarmlx.f017.event06-v12-checkpoint-census/1.0.0",
        "keys": {
            "schema",
            "checkpoint_set_sha256",
            "expected_shard_count",
            "expected_identity_only_shard_count",
            "expected_graph_payload_shard_count",
            "expected_total_bytes",
            "checkpoint_root",
            "checkpoint_root_resolved",
            "checkpoint_access",
        },
    },
    "INTEGRATION": {
        "schema": "pulsarmlx.f017.event06-v12-installation-integration-authority/1.0.0",
        "keys": {
            "schema",
            "source_head",
            "source_tree",
            "implementation_measurement_sha256",
            "bridge_declaration_sha256",
            "numerical_contract_sha256",
            "primary_numerical_sha256",
            "secondary_numerical_sha256",
            "result_authority_sha256",
            "primary_wrapper_sha256",
            "secondary_wrapper_sha256",
            "result_consumer_sha256",
            "candidate_sha256",
            "checkpoint_census_sha256",
        },
    },
}


def _canonical_document(raw: bytes, kind: str) -> _SealedDocument:
    rule = DOCUMENT_RULES.get(kind)
    if rule is None:
        raise installation_failure("input", "unknown input role")
    try:
        value = parse_artifact_bytes(raw)
    except Exception as exc:
        raise installation_failure("input", f"{kind} canonical bytes") from exc
    if type(value) is not dict or set(value) != rule["keys"]:
        raise installation_failure("input", f"{kind} field census")
    if value.get("schema") != rule["schema"] or canonical_bytes(value) != raw:
        raise installation_failure("input", f"{kind} schema or canonical bytes")
    return _SealedDocument(_DOCUMENT_SEAL, value, kind)


def validate_inert_human_go(raw: bytes) -> _SealedDocument:
    value = _canonical_document(raw, "GO")
    issued = value.get("issued_at_unix_ns")
    expires = value.get("expires_at_unix_ns")
    nonce = value.get("nonce_sha256")
    if (
        value.get("decision") != "INERT_VALIDATION_ONLY_NOT_HUMAN_GO"
        or value.get("live") is not False
        or type(issued) is not int
        or type(expires) is not int
        or issued >= expires
        or type(nonce) is not str
        or HEX64.fullmatch(nonce) is None
    ):
        raise installation_failure("go", "inert GO predicate")
    _validate_ids(value, ("authorization_id", "package_attempt_id"))
    return value


def validate_inert_operator_approval(raw: bytes) -> _SealedDocument:
    value = _canonical_document(raw, "APPROVAL")
    _validate_ids(value, ("authorization_id", "package_attempt_id"))
    for name in (
        "human_go_sha256",
        "event_identity_plan_sha256",
        "execution_plan_sha256",
        "candidate_sha256",
    ):
        item = value.get(name)
        if type(item) is not str or HEX64.fullmatch(item) is None:
            raise installation_failure("go", f"approval digest: {name}")
    if (
        value.get("live") is not False
        or type(value.get("attempts")) is not int
        or value.get("attempts") != 1
        or type(value.get("retries")) is not int
        or value.get("retries") != 0
        or value.get("resume") is not False
    ):
        raise installation_failure("go", "approval one-shot posture")
    return value


def validate_event_identity_plan_document(raw: bytes) -> _SealedDocument:
    value = _canonical_document(raw, "EVENT_IDENTITY")
    _validate_ids(
        value, ("package_attempt_id", "primary_event_id", "secondary_event_id")
    )
    if (
        len(
            {
                value.get("package_attempt_id"),
                value.get("primary_event_id"),
                value.get("secondary_event_id"),
            }
        )
        != 3
    ):
        raise installation_failure("identity", "event identities must be distinct")
    execution_plan_sha = value.get("execution_plan_sha256")
    if (
        type(execution_plan_sha) is not str
        or HEX64.fullmatch(execution_plan_sha) is None
    ):
        raise installation_failure("identity", "execution plan digest")
    return value


def validate_checkpoint_census_document(raw: bytes) -> _SealedDocument:
    value = _canonical_document(raw, "CHECKPOINT_CENSUS")
    checkpoint_set_sha = value.get("checkpoint_set_sha256")
    expected_total_bytes = value.get("expected_total_bytes")
    if (
        type(checkpoint_set_sha) is not str
        or HEX64.fullmatch(checkpoint_set_sha) is None
        or value.get("expected_shard_count") != 6
        or value.get("expected_identity_only_shard_count") != 1
        or value.get("expected_graph_payload_shard_count") != 5
        or type(expected_total_bytes) is not int
        or type(expected_total_bytes) is bool
        or expected_total_bytes < 0
        or value.get("checkpoint_root") != "/NONEXISTENT/F017/EVENT06/SEQUENCE08"
        or value.get("checkpoint_root_resolved") is not False
        or value.get("checkpoint_access") != 0
    ):
        raise installation_failure("input", "checkpoint census")
    return value


def validate_integration_authority_document(raw: bytes) -> _SealedDocument:
    value = _canonical_document(raw, "INTEGRATION")
    for name in ("source_head", "source_tree"):
        item = value.get(name)
        if type(item) is not str or HEX40.fullmatch(item) is None:
            raise installation_failure("input", name)
    integration_keys = cast(set[str], DOCUMENT_RULES["INTEGRATION"]["keys"])
    for name in integration_keys - {
        "schema",
        "source_head",
        "source_tree",
    }:
        item = value.get(name)
        if type(item) is not str or HEX64.fullmatch(item) is None:
            raise installation_failure("input", name)
    return value


def _validate_ids(value: _SealedDocument, names: tuple[str, ...]) -> None:
    for name in names:
        item = value.get(name)
        if type(item) is not str or TYPED_ID.fullmatch(item) is None:
            raise installation_failure("identity", name)


class PreparedProductionInstallation:
    """Opaque in-memory candidate/receipt/installed triple."""

    __slots__ = (
        "_candidate",
        "_receipt",
        "_installed",
        "candidate_sha256",
        "receipt_sha256",
        "installed_sha256",
        "posture",
        "integration_sha256",
        "_locked",
    )
    _candidate: bytes
    _receipt: bytes
    _installed: bytes
    candidate_sha256: str
    receipt_sha256: str
    installed_sha256: str
    posture: str
    integration_sha256: str
    _locked: bool

    def __new__(cls, seal: object = None, *args: object, **kwargs: object) -> Self:
        del args, kwargs
        if seal is not _PREPARED_SEAL:
            raise TypeError("prepared installations are repository-created")
        return super().__new__(cls)

    def __init__(
        self,
        seal: object,
        candidate: bytes,
        receipt: bytes,
        installed: bytes,
        integration_sha256: str,
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
        object.__setattr__(self, "integration_sha256", integration_sha256)
        object.__setattr__(self, "posture", "PREPARED_VALIDATION_ONLY")
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise TypeError("prepared installations are immutable")

    def payload(self, role: str) -> bytes:
        return {
            "candidate": self._candidate,
            "receipt": self._receipt,
            "installed": self._installed,
        }[role]

    def __copy__(self) -> Never:
        raise TypeError("prepared installations cannot be copied")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("prepared installations cannot be copied")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        del protocol
        raise TypeError("prepared installations cannot be pickled")


class PackageStartEligibleDryStop:
    __slots__ = ("terminal", "prepared_sha256", "_locked")
    terminal: str
    prepared_sha256: str
    _locked: bool

    def __new__(cls, seal: object = None, prepared_sha256: object = None) -> Self:
        if seal is not _GATE_SEAL:
            raise TypeError("dry package gates are validator-created")
        return super().__new__(cls)

    def __init__(self, seal: object, prepared_sha256: str) -> None:
        del seal
        object.__setattr__(self, "terminal", "PACKAGE_START_ELIGIBLE_DRY_STOP")
        object.__setattr__(self, "prepared_sha256", prepared_sha256)
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise TypeError("dry package gates are immutable")


def _candidate_triple(authority: ValidatedIdentityAuthority) -> None:
    if (
        type(authority) is not ValidatedIdentityAuthority
        or authority.posture != "CANDIDATE"
    ):
        raise installation_failure("candidate", "sealed candidate posture")
    if authority.get("authority_scope") != "PRODUCTION":
        raise installation_failure("posture", "production scope")
    reports = (
        validate_primary(authority, posture="CANDIDATE"),
        validate_secondary(authority, posture="CANDIDATE"),
    )
    if any(report.get("result") != "PASS" for report in reports):
        raise installation_failure("candidate", "consumer candidate validation")


def _repository_sha(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def prepare_production_installation(
    readiness: ValidatedEvent06ReadinessV2,
    human_go: _SealedDocument,
    execution_plan: ValidatedExecutionPlan,
    approval: _SealedDocument,
    event_identity: _SealedDocument,
    candidate: ValidatedIdentityAuthority,
    checkpoint_census: _SealedDocument,
    integration: _SealedDocument,
) -> PreparedProductionInstallation:
    if type(readiness) is not ValidatedEvent06ReadinessV2:
        raise installation_failure("readiness", "sealed readiness")
    if human_go.kind != "GO" or approval.kind != "APPROVAL":
        raise installation_failure("go", "sealed GO and approval")
    if type(execution_plan) is not ValidatedExecutionPlan:
        raise installation_failure("plan", "sealed execution plan")
    if event_identity.kind != "EVENT_IDENTITY":
        raise installation_failure("identity", "sealed event identity")
    if (
        checkpoint_census.kind != "CHECKPOINT_CENSUS"
        or integration.kind != "INTEGRATION"
    ):
        raise installation_failure("input", "sealed census and integration")
    _candidate_triple(candidate)

    candidate_raw = canonical_bytes(candidate.as_dict())
    candidate_sha = hashlib.sha256(candidate_raw).hexdigest()
    checks = (
        (approval.get("human_go_sha256"), human_go.sha256, "GO"),
        (approval.get("execution_plan_sha256"), execution_plan.sha256, "plan"),
        (
            approval.get("event_identity_plan_sha256"),
            event_identity.sha256,
            "event identity",
        ),
        (approval.get("candidate_sha256"), candidate_sha, "candidate"),
        (
            approval.get("authorization_id"),
            candidate.get("authorization_id"),
            "authorization",
        ),
        (
            approval.get("package_attempt_id"),
            candidate.get("package_attempt_id"),
            "package",
        ),
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
            event_identity.get("execution_plan_sha256"),
            execution_plan.sha256,
            "identity plan",
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
            event_identity.sha256,
            "candidate identity plan",
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
            execution_plan.get("primary_numerical_sha256"),
            integration.get("primary_numerical_sha256"),
            "primary numerics",
        ),
        (
            execution_plan.get("secondary_numerical_sha256"),
            integration.get("secondary_numerical_sha256"),
            "secondary numerics",
        ),
        (
            execution_plan.get("result_authority_sha256"),
            integration.get("result_authority_sha256"),
            "result authority",
        ),
        (
            readiness.get("bridge_declaration_sha256"),
            integration.get("bridge_declaration_sha256"),
            "bridge declaration",
        ),
        (
            readiness.get("numerical_contract_sha256"),
            integration.get("numerical_contract_sha256"),
            "readiness numerical contract",
        ),
        (
            readiness.get("result_authority_sha256"),
            integration.get("result_authority_sha256"),
            "readiness result authority",
        ),
        (
            _repository_sha(
                "scripts/research/f017_corrected_oracle_primary_wrapper_v11.py"
            ),
            integration.get("primary_wrapper_sha256"),
            "primary wrapper",
        ),
        (
            _repository_sha(
                "scripts/research/f017_corrected_oracle_secondary_wrapper_v11.py"
            ),
            integration.get("secondary_wrapper_sha256"),
            "secondary wrapper",
        ),
        (
            _repository_sha("scripts/research/f017_result_bundle_authority_v11.py"),
            integration.get("result_consumer_sha256"),
            "result consumer",
        ),
    )
    for observed, expected, detail in checks:
        if observed != expected:
            category = "go" if detail.startswith("GO") else "input"
            if "plan" in detail:
                category = "plan"
            elif "identity" in detail or "event" in detail:
                category = "identity"
            elif "candidate" in detail:
                category = "candidate"
            raise installation_failure(category, detail)

    receipt_value = {
        "schema": "pulsarmlx.f017.event06-v12-production-installation-preparation-receipt/1.0.0",
        "candidate_sha256": candidate_sha,
        "readiness_sha256": readiness.source_sha256,
        "human_go_sha256": human_go.sha256,
        "operator_approval_sha256": approval.sha256,
        "execution_plan_sha256": execution_plan.sha256,
        "event_identity_plan_sha256": event_identity.sha256,
        "checkpoint_census_sha256": checkpoint_census.sha256,
        "integration_sha256": integration.sha256,
        "authorization_id": candidate.get("authorization_id"),
        "package_attempt_id": candidate.get("package_attempt_id"),
        "state": "PREPARED_VALIDATION_ONLY",
        "live_authority": False,
        "result": "PASS",
    }
    receipt_raw = canonical_bytes(receipt_value)
    receipt_sha = hashlib.sha256(receipt_raw).hexdigest()
    installed_raw = canonical_bytes(installed_document(candidate, receipt_sha))
    return PreparedProductionInstallation(
        _PREPARED_SEAL, candidate_raw, receipt_raw, installed_raw, integration.sha256
    )


def validate_prepared_production_installation(
    prepared: PreparedProductionInstallation,
) -> PreparedProductionInstallation:
    if type(prepared) is not PreparedProductionInstallation:
        raise installation_failure("posture", "sealed prepared installation")
    if prepared.posture != "PREPARED_VALIDATION_ONLY":
        raise installation_failure("posture", "prepared installation posture")
    candidate = validate_candidate_bytes(prepared.payload("candidate"))
    receipt = parse_artifact_bytes(prepared.payload("receipt"))
    if (
        type(receipt) is not dict
        or receipt.get("state") != "PREPARED_VALIDATION_ONLY"
        or receipt.get("live_authority") is not False
        or receipt.get("result") != "PASS"
        or receipt.get("candidate_sha256") != candidate.source_sha256
        or hashlib.sha256(prepared.payload("receipt")).hexdigest()
        != prepared.receipt_sha256
    ):
        raise installation_failure("receipt", "prepared receipt")
    installed = validate_installed_bytes(
        prepared.payload("installed"), installed_expected(candidate)
    )
    if (
        installed.get("installation_receipt_sha256") != prepared.receipt_sha256
        or hashlib.sha256(prepared.payload("installed")).hexdigest()
        != prepared.installed_sha256
    ):
        raise installation_failure("readback", "prepared installed bytes")
    return prepared


def validate_prepared_package_start_eligibility(
    prepared: PreparedProductionInstallation,
) -> PackageStartEligibleDryStop:
    prepared = validate_prepared_production_installation(prepared)
    digest = hashlib.sha256(
        prepared.payload("candidate")
        + prepared.payload("receipt")
        + prepared.payload("installed")
    ).hexdigest()
    return PackageStartEligibleDryStop(_GATE_SEAL, digest)


class _FutureGoCapability:
    """Future-only nominal type. Sequence 8 intentionally has no factory."""

    __slots__ = ()

    def __new__(cls, *args: object, **kwargs: object) -> Never:
        del args, kwargs
        raise TypeError("future Event 06 GO capability factory unavailable")


def commit_production_installation(
    prepared: PreparedProductionInstallation,
    capability: object,
    target: Path,
) -> None:
    """Capability-sealed future boundary; success is unreachable in Sequence 8."""
    if type(prepared) is not PreparedProductionInstallation:
        raise installation_failure("posture", "prepared installation required")
    if type(capability) is not _FutureGoCapability:
        raise installation_failure("capability", "sealed future GO capability required")
    del target
    raise installation_failure("capability_expired", "future capability unavailable")


def assert_sealed_objects_closed(*values: object) -> None:
    for value in values:
        for operation in (copy.copy, copy.deepcopy):
            try:
                operation(value)
            except TypeError:
                continue
            raise installation_failure("input", "copy surface")


def _fail_before_write_test_spy(family: str) -> None:
    """Test-only modeled race edge; every branch fails before any path write."""
    categories = {
        "capability_expiry": "capability_expired",
        "candidate_replay": "replay",
        "exclusive_create": "target",
        "target_identity": "target",
        "write_short": "write",
        "write_error": "write",
        "file_fsync": "fsync",
        "directory_fsync": "fsync",
        "readback_identity": "readback",
        "concurrent_replacement": "partial",
    }
    if family not in categories:
        raise ValueError("unknown test race family")
    raise installation_failure(categories[family], family)
