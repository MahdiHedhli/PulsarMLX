#!/usr/bin/env python3
"""Pure minimum-gate contracts for the F017 Event 06 production composer.

This module deliberately contains no filesystem, checkpoint, lifecycle-state,
or production-root capability.  It turns already validated authority digests
and already banked receipt digests into immutable, canonically hashed values.
The effectful composer is responsible for exclusively banking the deterministic
package-start receipt and the sole deterministic package terminal.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, Self

MINIMUM_GATE_CONTRACT_SCHEMA: Final = (
    "pulsarmlx.f017.event06-minimum-gate-contract/1.0.0"
)
PACKAGE_START_GATE_SCHEMA: Final = (
    "pulsarmlx.f017.event06-minimum-package-start-gate/1.0.0"
)
PACKAGE_START_RECEIPT_SCHEMA: Final = (
    "pulsarmlx.f017.event06-minimum-package-start-receipt/1.0.0"
)
CONSUMED_PACKAGE_START_GATE_SCHEMA: Final = (
    "pulsarmlx.f017.event06-minimum-consumed-package-start-gate/1.0.0"
)
IDENTITY_READ_RECEIPT_SCHEMA: Final = (
    "pulsarmlx.f017.event06-minimum-identity-read-receipt/1.0.0"
)
ACCOUNTING_CLOSURE_SCHEMA: Final = (
    "pulsarmlx.f017.event06-minimum-receipt-derived-accounting/1.0.0"
)
PACKAGE_TERMINAL_SCHEMA: Final = (
    "pulsarmlx.f017.event06-minimum-package-terminal/1.0.0"
)

REQUIRED_MECHANISMS: Final = (
    ("M001", "one_shot_claim"),
    ("M002", "per_read_receipts"),
    ("M003", "fail_closed_preflight"),
    ("M004", "stop_boundary"),
    ("M005", "receipt_derived_ledger"),
    ("M006", "no_retry_or_resume"),
    ("M007", "numeric_acceptance_contract"),
    ("M008", "comparison_rules"),
    ("M009", "stage_vocabulary"),
    ("M010", "accounting_units"),
    ("M011", "historical_master_ledger_175"),
    ("M012", "fresh_human_decision_bound_to_exact_package_authority"),
    ("M013", "exact_checkpoint_identity_and_descriptor_stability"),
    ("M014", "causal_prerequisite_order"),
    ("M015", "independent_primary_secondary_numerical_evidence"),
    ("M016", "immutable_result_receipt_and_terminal_closure"),
    ("M017", "resource_release_before_package_terminal"),
)
REQUIRED_MECHANISM_IDS: Final = tuple(item[0] for item in REQUIRED_MECHANISMS)
OPTIONAL_NON_GATING_MECHANISM_IDS: Final = (
    "M023", "M024", "M025", "M033", "M035",
)
REMOVED_MECHANISM_IDS: Final = (
    "M018", "M019", "M020", "M021", "M022", "M026", "M027",
    "M028", "M029", "M030", "M031", "M032", "M034",
)
IMPLEMENTATION_DEPENDENCY_MECHANISM_IDS: Final = (
    "M018", "M019", "M020", "M021", "M022", "M023", "M024",
    "M025", "M026", "M027", "M028", "M029", "M030", "M031",
    "M032", "M035",
)
REQUIRED_GATE_COUNT: Final = 17
OPTIONAL_NON_GATING_COUNT: Final = 5
REMOVED_MECHANISM_COUNT: Final = 13
IMPLEMENTATION_DEPENDENCY_COUNT: Final = 16
HISTORICAL_MASTER_LEDGER: Final = 175

# This is the accepted vocabulary, not a newly introduced transition graph.
STAGE_VOCABULARY: Final = (
    "PREPARED",
    "INSTALLED",
    "PACKAGE_START_ELIGIBLE_DRY_STOP",
    "PACKAGE_START",
    "IDENTITY_TERMINAL",
    "PRIMARY_RESULT_TERMINAL",
    "SECONDARY_RESULT_TERMINAL",
    "COMPARISON_TERMINAL",
    "RELEASE_TERMINAL",
    "ACCOUNTING_CLOSURE",
    "PACKAGE_TERMINAL",
)
ACCOUNTING_UNITS: Final = ("authorization", "package", "primary", "secondary")

_HEX64 = re.compile(r"[0-9a-f]{64}")
_TYPED_ID = re.compile(r"[A-Z0-9](?:[A-Z0-9-]{0,190}[A-Z0-9])?")


def canonical_sha256(value: object) -> str:
    """Return the repository-canonical SHA-256 for a JSON-safe value."""
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8") + b"\n"
    return hashlib.sha256(raw).hexdigest()


_MINIMUM_GATE_CONTRACT: Final = {
    "schema": MINIMUM_GATE_CONTRACT_SCHEMA,
    "required_mechanisms": [
        {"mechanism_id": mechanism_id, "name": name}
        for mechanism_id, name in REQUIRED_MECHANISMS
    ],
    "required_mechanism_ids": list(REQUIRED_MECHANISM_IDS),
    "required_gate_count": REQUIRED_GATE_COUNT,
    "stage_vocabulary": list(STAGE_VOCABULARY),
    "accounting_units": list(ACCOUNTING_UNITS),
    "historical_master_ledger": HISTORICAL_MASTER_LEDGER,
    "result": "PASS",
}
MINIMUM_GATE_CONTRACT_SHA256: Final = canonical_sha256(_MINIMUM_GATE_CONTRACT)


def minimum_gate_contract() -> dict[str, object]:
    """Return an independent copy of the exact Sequence 39 gate profile."""
    return copy.deepcopy(_MINIMUM_GATE_CONTRACT)


def validate_minimum_gate_contract(value: object) -> dict[str, object]:
    """Fail closed unless *value* is the exact 17/5/13/16 profile."""
    if type(value) is not dict or value != _MINIMUM_GATE_CONTRACT:
        raise ValueError("minimum-gate contract mismatch")
    required = value["required_mechanism_ids"]
    if (
        type(required) is not list
        or len(set(required)) != REQUIRED_GATE_COUNT
        or canonical_sha256(value) != MINIMUM_GATE_CONTRACT_SHA256
    ):
        raise ValueError("minimum-gate profile integrity")
    return copy.deepcopy(value)


def _freeze(value: object) -> object:
    if type(value) is dict:
        return MappingProxyType({key: _freeze(value[key]) for key in sorted(value)})
    if type(value) in {list, tuple}:
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if type(value) is tuple:
        return [_thaw(item) for item in value]
    return value


class _SealedArtifact:
    __slots__ = ("_items", "sha256", "_locked")

    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if _ARTIFACT_SEALS.get(cls) is not seal:
            raise TypeError(f"{cls.__name__} is producer-created")
        return super().__new__(cls)

    def __init__(self, seal: object, value: dict[str, object]) -> None:
        if _ARTIFACT_SEALS.get(type(self)) is not seal:
            raise TypeError("sealed artifact constructor")
        object.__setattr__(self, "_items", _freeze(value))
        object.__setattr__(self, "sha256", canonical_sha256(value))
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise TypeError("minimum-gate artifacts are immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise TypeError("minimum-gate artifacts are immutable")

    def get(self, key: str) -> object:
        if not isinstance(self._items, Mapping) or key not in self._items:
            raise KeyError(key)
        return _thaw(self._items[key])

    def as_dict(self) -> dict[str, object]:
        value = _thaw(self._items)
        if type(value) is not dict:
            raise TypeError("sealed artifact object")
        return value

    def immutable_view(self) -> MappingProxyType[str, object]:
        return MappingProxyType(self.as_dict())

    def __copy__(self) -> Self:
        raise TypeError("minimum-gate artifacts cannot be copied")

    def __deepcopy__(self, memo: object) -> Self:
        del memo
        raise TypeError("minimum-gate artifacts cannot be copied")

    def __reduce_ex__(self, protocol: int) -> object:
        del protocol
        raise TypeError("minimum-gate artifacts cannot be pickled")


class _PackageStartGate(_SealedArtifact):
    __slots__ = ()


class _ConsumedPackageStartGate(_SealedArtifact):
    __slots__ = ()


class _AccountingClosure(_SealedArtifact):
    __slots__ = ()


class _PackageTerminal(_SealedArtifact):
    __slots__ = ()


_PACKAGE_GATE_SEAL = object()
_CONSUMED_GATE_SEAL = object()
_ACCOUNTING_SEAL = object()
_TERMINAL_SEAL = object()
_ARTIFACT_SEALS: Final = {
    _PackageStartGate: _PACKAGE_GATE_SEAL,
    _ConsumedPackageStartGate: _CONSUMED_GATE_SEAL,
    _AccountingClosure: _ACCOUNTING_SEAL,
    _PackageTerminal: _TERMINAL_SEAL,
}


def _require_sha256(value: object, label: str) -> str:
    if type(value) is not str or _HEX64.fullmatch(value) is None:
        raise ValueError(f"{label} SHA-256")
    return value


def _require_typed_id(value: object, label: str) -> str:
    if type(value) is not str or _TYPED_ID.fullmatch(value) is None:
        raise ValueError(f"{label} typed identity")
    return value


def _require_nonnegative_integer(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} nonnegative integer")
    return value


def _require_exact_keys(value: object, keys: frozenset[str], label: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise ValueError(f"{label} field census")
    return value


_GATE_KEYS = frozenset({
    "schema", "minimum_gate_contract_sha256", "authorization_id",
    "package_attempt_id", "primary_event_id", "secondary_event_id",
    "collapsed_go_sha256", "installed_authority_sha256",
    "checkpoint_authority_sha256",
    "numerical_acceptance_contract_sha256", "comparison_rules_sha256",
    "result_authority_sha256", "stage_vocabulary_sha256",
    "accounting_units_sha256", "historical_master_ledger",
    "preflight_passed", "one_shot_claim", "attempts", "retries", "resume",
    "package_started", "checkpoint_opens", "checkpoint_reads",
    "numerical_operations", "state", "result",
})


def _build_package_start_gate(
    *,
    authorization_id: str,
    package_attempt_id: str,
    primary_event_id: str,
    secondary_event_id: str,
    collapsed_go_sha256: str,
    installed_authority_sha256: str,
    checkpoint_authority_sha256: str,
    numerical_acceptance_contract_sha256: str,
    comparison_rules_sha256: str,
    result_authority_sha256: str,
    preflight_passed: bool,
    checkpoint_opens: int = 0,
    checkpoint_reads: int = 0,
    numerical_operations: int = 0,
) -> object:
    """Build the sole pre-effect package-start capability."""
    identities = (
        _require_typed_id(authorization_id, "authorization"),
        _require_typed_id(package_attempt_id, "package"),
        _require_typed_id(primary_event_id, "primary"),
        _require_typed_id(secondary_event_id, "secondary"),
    )
    if len(set(identities)) != 4:
        raise ValueError("package identities must be pairwise distinct")
    if preflight_passed is not True:
        raise ValueError("fail-closed preflight")
    for label, value in (
        ("checkpoint opens", checkpoint_opens),
        ("checkpoint reads", checkpoint_reads),
        ("numerical operations", numerical_operations),
    ):
        if _require_nonnegative_integer(value, label) != 0:
            raise ValueError("package-start gate precedes protected effects")
    value: dict[str, object] = {
        "schema": PACKAGE_START_GATE_SCHEMA,
        "minimum_gate_contract_sha256": MINIMUM_GATE_CONTRACT_SHA256,
        "authorization_id": authorization_id,
        "package_attempt_id": package_attempt_id,
        "primary_event_id": primary_event_id,
        "secondary_event_id": secondary_event_id,
        "collapsed_go_sha256": _require_sha256(collapsed_go_sha256, "collapsed GO"),
        "installed_authority_sha256": _require_sha256(
            installed_authority_sha256, "installed authority"
        ),
        "checkpoint_authority_sha256": _require_sha256(
            checkpoint_authority_sha256, "checkpoint authority"
        ),
        "numerical_acceptance_contract_sha256": _require_sha256(
            numerical_acceptance_contract_sha256, "numerical acceptance contract"
        ),
        "comparison_rules_sha256": _require_sha256(
            comparison_rules_sha256, "comparison rules"
        ),
        "result_authority_sha256": _require_sha256(
            result_authority_sha256, "result authority"
        ),
        "stage_vocabulary_sha256": canonical_sha256(list(STAGE_VOCABULARY)),
        "accounting_units_sha256": canonical_sha256(list(ACCOUNTING_UNITS)),
        "historical_master_ledger": HISTORICAL_MASTER_LEDGER,
        "preflight_passed": True,
        "one_shot_claim": "PASS",
        "attempts": 1,
        "retries": 0,
        "resume": False,
        "package_started": False,
        "checkpoint_opens": 0,
        "checkpoint_reads": 0,
        "numerical_operations": 0,
        "state": "PACKAGE_START_ELIGIBLE_DRY_STOP",
        "result": "PASS",
    }
    gate = _PackageStartGate(_PACKAGE_GATE_SEAL, value)
    return _validate_package_start_gate(gate)


def _validate_package_start_gate(value: object) -> object:
    if type(value) is not _PackageStartGate:
        raise TypeError("exact sealed package-start gate required")
    data = _require_exact_keys(value.as_dict(), _GATE_KEYS, "package-start gate")
    if (
        data["schema"] != PACKAGE_START_GATE_SCHEMA
        or data["minimum_gate_contract_sha256"] != MINIMUM_GATE_CONTRACT_SHA256
        or data["stage_vocabulary_sha256"] != canonical_sha256(list(STAGE_VOCABULARY))
        or data["accounting_units_sha256"] != canonical_sha256(list(ACCOUNTING_UNITS))
        or data["historical_master_ledger"] != HISTORICAL_MASTER_LEDGER
        or data["preflight_passed"] is not True
        or data["one_shot_claim"] != "PASS"
        or data["attempts"] != 1
        or data["retries"] != 0
        or data["resume"] is not False
        or data["package_started"] is not False
        or data["checkpoint_opens"] != 0
        or data["checkpoint_reads"] != 0
        or data["numerical_operations"] != 0
        or data["state"] != "PACKAGE_START_ELIGIBLE_DRY_STOP"
        or data["result"] != "PASS"
        or canonical_sha256(data) != value.sha256
    ):
        raise ValueError("package-start gate semantics")
    identities = [data[key] for key in (
        "authorization_id", "package_attempt_id", "primary_event_id", "secondary_event_id"
    )]
    for key, identity in zip(
        ("authorization", "package", "primary", "secondary"), identities, strict=True
    ):
        _require_typed_id(identity, key)
    if len(set(identities)) != 4:
        raise ValueError("package identity alias")
    for key in (
        "collapsed_go_sha256", "installed_authority_sha256",
        "checkpoint_authority_sha256",
        "numerical_acceptance_contract_sha256", "comparison_rules_sha256",
        "result_authority_sha256",
    ):
        _require_sha256(data[key], key)
    return value


_CONSUMED_GATE_KEYS = frozenset({
    "schema", "package_start_gate_sha256", "package_start_receipt",
    "package_start_receipt_sha256", "authorization_id", "package_attempt_id",
    "primary_event_id", "secondary_event_id", "collapsed_go_sha256",
    "installed_authority_sha256",
    "checkpoint_authority_sha256", "numerical_acceptance_contract_sha256",
    "comparison_rules_sha256", "result_authority_sha256", "state", "result",
})
_PACKAGE_START_RECEIPT_KEYS = frozenset({
    "schema", "stage", "package_start_gate_sha256", "authorization_id",
    "package_attempt_id", "primary_event_id", "secondary_event_id",
    "attempts", "retries", "resume", "result",
})


def _package_start_receipt(gate: _PackageStartGate) -> dict[str, object]:
    return {
        "schema": PACKAGE_START_RECEIPT_SCHEMA,
        "stage": "PACKAGE_START",
        "package_start_gate_sha256": gate.sha256,
        "authorization_id": gate.get("authorization_id"),
        "package_attempt_id": gate.get("package_attempt_id"),
        "primary_event_id": gate.get("primary_event_id"),
        "secondary_event_id": gate.get("secondary_event_id"),
        "attempts": 1,
        "retries": 0,
        "resume": False,
        "result": "PASS",
    }


def _consume_package_start_gate(gate: object) -> object:
    """Derive the one canonical package-start receipt and consumed gate.

    Re-derivation is byte-identical.  The effectful caller uses exclusive
    creation of this deterministic receipt, making one package the sole winner.
    """
    validated = _validate_package_start_gate(gate)
    if type(validated) is not _PackageStartGate:
        raise TypeError("exact package-start gate")
    receipt = _package_start_receipt(validated)
    value = {
        "schema": CONSUMED_PACKAGE_START_GATE_SCHEMA,
        "package_start_gate_sha256": validated.sha256,
        "package_start_receipt": receipt,
        "package_start_receipt_sha256": canonical_sha256(receipt),
        "authorization_id": validated.get("authorization_id"),
        "package_attempt_id": validated.get("package_attempt_id"),
        "primary_event_id": validated.get("primary_event_id"),
        "secondary_event_id": validated.get("secondary_event_id"),
        "collapsed_go_sha256": validated.get("collapsed_go_sha256"),
        "installed_authority_sha256": validated.get("installed_authority_sha256"),
        "checkpoint_authority_sha256": validated.get("checkpoint_authority_sha256"),
        "numerical_acceptance_contract_sha256": validated.get(
            "numerical_acceptance_contract_sha256"
        ),
        "comparison_rules_sha256": validated.get("comparison_rules_sha256"),
        "result_authority_sha256": validated.get("result_authority_sha256"),
        "state": "PACKAGE_STARTED",
        "result": "PASS",
    }
    consumed = _ConsumedPackageStartGate(_CONSUMED_GATE_SEAL, value)
    return _validate_consumed_package_start_gate(consumed)


def _validate_consumed_package_start_gate(value: object) -> object:
    if type(value) is not _ConsumedPackageStartGate:
        raise TypeError("exact consumed package-start gate required")
    data = _require_exact_keys(value.as_dict(), _CONSUMED_GATE_KEYS, "consumed gate")
    receipt = _require_exact_keys(
        data["package_start_receipt"], _PACKAGE_START_RECEIPT_KEYS,
        "package-start receipt",
    )
    if (
        data["schema"] != CONSUMED_PACKAGE_START_GATE_SCHEMA
        or receipt["schema"] != PACKAGE_START_RECEIPT_SCHEMA
        or receipt["stage"] != "PACKAGE_START"
        or receipt["package_start_gate_sha256"] != data["package_start_gate_sha256"]
        or receipt["attempts"] != 1
        or receipt["retries"] != 0
        or receipt["resume"] is not False
        or receipt["result"] != "PASS"
        or data["package_start_receipt_sha256"] != canonical_sha256(receipt)
        or data["state"] != "PACKAGE_STARTED"
        or data["result"] != "PASS"
        or canonical_sha256(data) != value.sha256
    ):
        raise ValueError("consumed package-start gate semantics")
    _require_sha256(data["package_start_gate_sha256"], "package-start gate")
    _require_sha256(data["package_start_receipt_sha256"], "package-start receipt")
    for key in ("authorization_id", "package_attempt_id", "primary_event_id", "secondary_event_id"):
        _require_typed_id(data[key], key)
        if receipt[key] != data[key]:
            raise ValueError("package-start receipt identity continuity")
    for key in (
        "collapsed_go_sha256", "installed_authority_sha256",
        "checkpoint_authority_sha256",
        "numerical_acceptance_contract_sha256", "comparison_rules_sha256",
        "result_authority_sha256",
    ):
        _require_sha256(data[key], key)
    return value


_IDENTITY_READ_KEYS = frozenset({
    "schema", "ordinal", "role", "byte_count", "sha256", "result",
})
_RECEIPT_BINDING_KEYS = frozenset({
    "package_start_receipt_sha256", "identity_receipt_sha256",
    "identity_terminal_sha256", "primary_start_receipt_sha256",
    "primary_result_receipt_sha256", "primary_result_terminal_sha256",
    "primary_consumer_terminal_sha256", "secondary_start_receipt_sha256",
    "secondary_result_receipt_sha256", "secondary_result_terminal_sha256",
    "secondary_consumer_terminal_sha256", "comparison_receipt_sha256",
    "comparison_terminal_sha256", "release_start_receipt_sha256",
    "release_report_sha256", "release_receipt_sha256", "release_terminal_sha256",
})
_ACCOUNTING_KEYS = frozenset({
    "schema", "consumed_package_start_gate_sha256", "authorization_id",
    "package_attempt_id", "primary_event_id", "secondary_event_id",
    "identity_read_receipts", "identity_read_receipt_root_sha256",
    "identity_read_receipt_count", "identity_bytes_read",
    "receipt_bindings", "receipt_root_sha256", "authorization_delta",
    "package_delta", "primary_delta", "secondary_delta",
    "historical_master_ledger_before", "historical_master_ledger_after",
    "attempted_closures", "successful_closures", "duplicate_closes",
    "unknown_leases", "live_leases", "stage", "result",
})


def _validate_identity_read_receipts(value: object) -> list[dict[str, object]]:
    if type(value) is not tuple or len(value) != 6:
        raise ValueError("six identity read receipts required")
    result: list[dict[str, object]] = []
    for index, item in enumerate(value, 1):
        receipt = _require_exact_keys(item, _IDENTITY_READ_KEYS, "identity read receipt")
        expected_role = "IDENTITY_ONLY" if index == 1 else "GRAPH_PAYLOAD"
        if (
            receipt["schema"] != IDENTITY_READ_RECEIPT_SCHEMA
            or receipt["ordinal"] != index
            or type(receipt["ordinal"]) is not int
            or receipt["role"] != expected_role
            or _require_nonnegative_integer(receipt["byte_count"], "read byte count") < 0
            or receipt["result"] != "PASS"
        ):
            raise ValueError("identity read receipt semantics")
        _require_sha256(receipt["sha256"], "identity read")
        result.append(copy.deepcopy(receipt))
    return result


def _build_accounting_closure(
    consumed_gate: object,
    *,
    identity_read_receipts: tuple[dict[str, object], ...],
    identity_receipt_sha256: str,
    identity_terminal_sha256: str,
    primary_start_receipt_sha256: str,
    primary_result_receipt_sha256: str,
    primary_result_terminal_sha256: str,
    primary_consumer_terminal_sha256: str,
    secondary_start_receipt_sha256: str,
    secondary_result_receipt_sha256: str,
    secondary_result_terminal_sha256: str,
    secondary_consumer_terminal_sha256: str,
    comparison_receipt_sha256: str,
    comparison_terminal_sha256: str,
    release_start_receipt_sha256: str,
    release_report_sha256: str,
    release_receipt_sha256: str,
    release_terminal_sha256: str,
    attempted_closures: int,
    successful_closures: int,
    duplicate_closes: int,
    unknown_leases: int,
    live_leases: int,
) -> object:
    """Derive the successful package accounting solely from receipt presence."""
    gate = _validate_consumed_package_start_gate(consumed_gate)
    if type(gate) is not _ConsumedPackageStartGate:
        raise TypeError("consumed package-start gate")
    reads = _validate_identity_read_receipts(identity_read_receipts)
    bindings = {
        "package_start_receipt_sha256": gate.get("package_start_receipt_sha256"),
        "identity_receipt_sha256": identity_receipt_sha256,
        "identity_terminal_sha256": identity_terminal_sha256,
        "primary_start_receipt_sha256": primary_start_receipt_sha256,
        "primary_result_receipt_sha256": primary_result_receipt_sha256,
        "primary_result_terminal_sha256": primary_result_terminal_sha256,
        "primary_consumer_terminal_sha256": primary_consumer_terminal_sha256,
        "secondary_start_receipt_sha256": secondary_start_receipt_sha256,
        "secondary_result_receipt_sha256": secondary_result_receipt_sha256,
        "secondary_result_terminal_sha256": secondary_result_terminal_sha256,
        "secondary_consumer_terminal_sha256": secondary_consumer_terminal_sha256,
        "comparison_receipt_sha256": comparison_receipt_sha256,
        "comparison_terminal_sha256": comparison_terminal_sha256,
        "release_start_receipt_sha256": release_start_receipt_sha256,
        "release_report_sha256": release_report_sha256,
        "release_receipt_sha256": release_receipt_sha256,
        "release_terminal_sha256": release_terminal_sha256,
    }
    for name, digest in bindings.items():
        _require_sha256(digest, name)
    if len(set(bindings.values())) != len(bindings):
        raise ValueError("receipt digest alias")
    release_values = {
        "attempted_closures": attempted_closures,
        "successful_closures": successful_closures,
        "duplicate_closes": duplicate_closes,
        "unknown_leases": unknown_leases,
        "live_leases": live_leases,
    }
    for name, count in release_values.items():
        _require_nonnegative_integer(count, name)
    if release_values != {
        "attempted_closures": 5,
        "successful_closures": 5,
        "duplicate_closes": 0,
        "unknown_leases": 0,
        "live_leases": 0,
    }:
        raise ValueError("release must complete before accounting closure")
    receipt_root_input = {
        "identity_read_receipts": reads,
        "receipt_bindings": bindings,
    }
    value = {
        "schema": ACCOUNTING_CLOSURE_SCHEMA,
        "consumed_package_start_gate_sha256": gate.sha256,
        "authorization_id": gate.get("authorization_id"),
        "package_attempt_id": gate.get("package_attempt_id"),
        "primary_event_id": gate.get("primary_event_id"),
        "secondary_event_id": gate.get("secondary_event_id"),
        "identity_read_receipts": reads,
        "identity_read_receipt_root_sha256": canonical_sha256(reads),
        "identity_read_receipt_count": len(reads),
        "identity_bytes_read": sum(item["byte_count"] for item in reads),
        "receipt_bindings": bindings,
        "receipt_root_sha256": canonical_sha256(receipt_root_input),
        # These values are projections of the exact durable-start receipts above.
        "authorization_delta": 0,
        "package_delta": int("package_start_receipt_sha256" in bindings),
        "primary_delta": int("primary_start_receipt_sha256" in bindings),
        "secondary_delta": int("secondary_start_receipt_sha256" in bindings),
        "historical_master_ledger_before": HISTORICAL_MASTER_LEDGER,
        "historical_master_ledger_after": HISTORICAL_MASTER_LEDGER,
        **release_values,
        "stage": "ACCOUNTING_CLOSURE",
        "result": "PASS",
    }
    closure = _AccountingClosure(_ACCOUNTING_SEAL, value)
    return _validate_accounting_closure(closure)


def _validate_accounting_document(value: object) -> dict[str, object]:
    """Validate the complete raw accounting document without minting authority."""
    data = _require_exact_keys(value, _ACCOUNTING_KEYS, "accounting closure")
    reads_value = data["identity_read_receipts"]
    if type(reads_value) is not list:
        raise ValueError("identity read receipt array")
    reads = _validate_identity_read_receipts(tuple(reads_value))
    bindings = _require_exact_keys(
        data["receipt_bindings"], _RECEIPT_BINDING_KEYS, "receipt bindings"
    )
    for name, digest in bindings.items():
        _require_sha256(digest, name)
    if len(set(bindings.values())) != len(bindings):
        raise ValueError("receipt digest alias")
    if (
        data["schema"] != ACCOUNTING_CLOSURE_SCHEMA
        or data["identity_read_receipt_root_sha256"] != canonical_sha256(reads)
        or data["identity_read_receipt_count"] != 6
        or type(data["identity_read_receipt_count"]) is not int
        or data["identity_bytes_read"] != sum(item["byte_count"] for item in reads)
        or type(data["identity_bytes_read"]) is not int
        or data["receipt_root_sha256"] != canonical_sha256({
            "identity_read_receipts": reads, "receipt_bindings": bindings,
        })
        or data["authorization_delta"] != 0
        or data["package_delta"] != 1
        or data["primary_delta"] != 1
        or data["secondary_delta"] != 1
        or data["historical_master_ledger_before"] != HISTORICAL_MASTER_LEDGER
        or data["historical_master_ledger_after"] != HISTORICAL_MASTER_LEDGER
        or data["attempted_closures"] != 5
        or data["successful_closures"] != 5
        or data["duplicate_closes"] != 0
        or data["unknown_leases"] != 0
        or data["live_leases"] != 0
        or data["stage"] != "ACCOUNTING_CLOSURE"
        or data["result"] != "PASS"
    ):
        raise ValueError("receipt-derived accounting semantics")
    _require_sha256(
        data["consumed_package_start_gate_sha256"], "consumed package-start gate"
    )
    for key in ("authorization_id", "package_attempt_id", "primary_event_id", "secondary_event_id"):
        _require_typed_id(data[key], key)
    return data


def _validate_accounting_closure(value: object) -> object:
    if type(value) is not _AccountingClosure:
        raise TypeError("exact sealed accounting closure required")
    data = _validate_accounting_document(value.as_dict())
    if canonical_sha256(data) != value.sha256:
        raise ValueError("receipt-derived accounting digest")
    return value


_TERMINAL_KEYS = frozenset({
    "schema", "authorization_id", "package_attempt_id", "primary_event_id",
    "secondary_event_id", "accounting_closure_sha256", "receipt_root_sha256",
    "package_start_receipt_sha256", "primary_consumer_terminal_sha256",
    "secondary_consumer_terminal_sha256", "comparison_terminal_sha256",
    "release_terminal_sha256", "package_receipt_sha256",
    "v11_closure_root_sha256", "terminal_winner_sha256", "terminal_ordinal",
    "single_winner", "stage", "outcome", "result",
})


def _build_package_terminal(
    accounting: object,
    *,
    package_receipt_sha256: str,
    v11_closure_root_sha256: str,
) -> object:
    """Build the one successful terminal after complete release and accounting."""
    closure = _validate_accounting_closure(accounting)
    if type(closure) is not _AccountingClosure:
        raise TypeError("receipt-derived accounting closure")
    bindings = closure.get("receipt_bindings")
    if type(bindings) is not dict:
        raise TypeError("receipt bindings")
    package_id = closure.get("package_attempt_id")
    winner = canonical_sha256({
        "package_attempt_id": package_id,
        "stage": "PACKAGE_TERMINAL",
        "terminal_ordinal": 1,
    })
    value = {
        "schema": PACKAGE_TERMINAL_SCHEMA,
        "authorization_id": closure.get("authorization_id"),
        "package_attempt_id": package_id,
        "primary_event_id": closure.get("primary_event_id"),
        "secondary_event_id": closure.get("secondary_event_id"),
        "accounting_closure_sha256": closure.sha256,
        "receipt_root_sha256": closure.get("receipt_root_sha256"),
        "package_start_receipt_sha256": bindings["package_start_receipt_sha256"],
        "primary_consumer_terminal_sha256": bindings[
            "primary_consumer_terminal_sha256"
        ],
        "secondary_consumer_terminal_sha256": bindings[
            "secondary_consumer_terminal_sha256"
        ],
        "comparison_terminal_sha256": bindings["comparison_terminal_sha256"],
        "release_terminal_sha256": bindings["release_terminal_sha256"],
        "package_receipt_sha256": _require_sha256(
            package_receipt_sha256, "package receipt"
        ),
        "v11_closure_root_sha256": _require_sha256(
            v11_closure_root_sha256, "V11 closure root"
        ),
        "terminal_winner_sha256": winner,
        "terminal_ordinal": 1,
        "single_winner": True,
        "stage": "PACKAGE_TERMINAL",
        "outcome": "COMPLETE_SUCCESS",
        "result": "PASS",
    }
    forbidden_aliases = set(bindings.values())
    if (
        value["package_receipt_sha256"] in forbidden_aliases
        or value["v11_closure_root_sha256"] in forbidden_aliases
        or value["package_receipt_sha256"] == value["v11_closure_root_sha256"]
    ):
        raise ValueError("package closure artifact alias")
    terminal = _PackageTerminal(_TERMINAL_SEAL, value)
    return _validate_package_terminal(terminal, closure)


def _validate_package_terminal_document(
    value: object, accounting: object
) -> dict[str, object]:
    """Validate complete raw terminal/accounting bytes without sealing them."""
    data = _require_exact_keys(value, _TERMINAL_KEYS, "package terminal")
    closure = _validate_accounting_document(accounting)
    bindings = closure.get("receipt_bindings")
    if type(bindings) is not dict:
        raise TypeError("receipt bindings")
    winner = canonical_sha256({
        "package_attempt_id": closure.get("package_attempt_id"),
        "stage": "PACKAGE_TERMINAL",
        "terminal_ordinal": 1,
    })
    continuity = {
        "authorization_id": closure.get("authorization_id"),
        "package_attempt_id": closure.get("package_attempt_id"),
        "primary_event_id": closure.get("primary_event_id"),
        "secondary_event_id": closure.get("secondary_event_id"),
        "accounting_closure_sha256": canonical_sha256(closure),
        "receipt_root_sha256": closure.get("receipt_root_sha256"),
        "package_start_receipt_sha256": bindings["package_start_receipt_sha256"],
        "primary_consumer_terminal_sha256": bindings[
            "primary_consumer_terminal_sha256"
        ],
        "secondary_consumer_terminal_sha256": bindings[
            "secondary_consumer_terminal_sha256"
        ],
        "comparison_terminal_sha256": bindings["comparison_terminal_sha256"],
        "release_terminal_sha256": bindings["release_terminal_sha256"],
    }
    if any(data[key] != expected for key, expected in continuity.items()):
        raise ValueError("package terminal accounting continuity")
    for key in (
        "accounting_closure_sha256", "receipt_root_sha256",
        "package_start_receipt_sha256", "primary_consumer_terminal_sha256",
        "secondary_consumer_terminal_sha256", "comparison_terminal_sha256",
        "release_terminal_sha256", "package_receipt_sha256",
        "v11_closure_root_sha256", "terminal_winner_sha256",
    ):
        _require_sha256(data[key], key)
    if (
        data["schema"] != PACKAGE_TERMINAL_SCHEMA
        or data["terminal_winner_sha256"] != winner
        or data["terminal_ordinal"] != 1
        or type(data["terminal_ordinal"]) is not int
        or data["single_winner"] is not True
        or data["stage"] != "PACKAGE_TERMINAL"
        or data["outcome"] != "COMPLETE_SUCCESS"
        or data["result"] != "PASS"
    ):
        raise ValueError("single-winner package terminal semantics")
    return data


def _validate_package_terminal(value: object, accounting: object) -> object:
    if type(value) is not _PackageTerminal:
        raise TypeError("exact sealed package terminal required")
    closure = _validate_accounting_closure(accounting)
    if type(closure) is not _AccountingClosure:
        raise TypeError("exact accounting closure")
    data = _validate_package_terminal_document(
        value.as_dict(), closure.as_dict()
    )
    if canonical_sha256(data) != value.sha256:
        raise ValueError("single-winner package terminal digest")
    return value


__all__ = (
    "MINIMUM_GATE_CONTRACT_SCHEMA",
    "PACKAGE_START_GATE_SCHEMA",
    "PACKAGE_START_RECEIPT_SCHEMA",
    "CONSUMED_PACKAGE_START_GATE_SCHEMA",
    "IDENTITY_READ_RECEIPT_SCHEMA",
    "ACCOUNTING_CLOSURE_SCHEMA",
    "PACKAGE_TERMINAL_SCHEMA",
    "REQUIRED_MECHANISMS",
    "REQUIRED_MECHANISM_IDS",
    "OPTIONAL_NON_GATING_MECHANISM_IDS",
    "REMOVED_MECHANISM_IDS",
    "IMPLEMENTATION_DEPENDENCY_MECHANISM_IDS",
    "REQUIRED_GATE_COUNT",
    "OPTIONAL_NON_GATING_COUNT",
    "REMOVED_MECHANISM_COUNT",
    "IMPLEMENTATION_DEPENDENCY_COUNT",
    "HISTORICAL_MASTER_LEDGER",
    "STAGE_VOCABULARY",
    "ACCOUNTING_UNITS",
    "MINIMUM_GATE_CONTRACT_SHA256",
    "canonical_sha256",
    "minimum_gate_contract",
    "validate_minimum_gate_contract",
)
