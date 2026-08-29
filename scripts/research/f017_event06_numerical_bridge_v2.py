#!/usr/bin/env python3
"""Collapsed-prompt-bound V12 identity to unchanged V11 numerical bridge.

This successor accepts only the producer-created collapsed prompt identity.
It never reconstructs the obsolete prompt-bound event-plan type.  The
historical bridge remains an immutable inner authority for unchanged V11
consumers, while collapsed preparation, GO, prompt, and installed digests are
carried through every downstream control-plane view.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath
from types import MappingProxyType

from f017_canonical_serialization_v10 import canonical_bytes
from f017_checkpoint_identity_authority_v12 import ValidatedIdentityAuthority
from f017_event06_execution_plan_v1 import ValidatedExecutionPlan
from f017_event06_identity_bridge_contract_v2 import (
    ACCOUNTING_FIELDS, ACCOUNTING_SCHEMA, ACCOUNTING_TYPES,
    BRIDGE_FIELDS, BRIDGE_SCHEMA, BRIDGE_TYPES,
    CONSUMER_ROLES, CONSUMER_VIEW_FIELDS, CONSUMER_VIEW_SCHEMA,
    CONSUMER_VIEW_TYPES, IDENTITY_INPUT_FIELDS, IDENTITY_INPUT_SCHEMA,
    IDENTITY_INPUT_TYPES, PACKAGE_TERMINAL_FIELDS, PACKAGE_TERMINAL_SCHEMA,
    PACKAGE_TERMINAL_TYPES,
)
from f017_event06_collapsed_live_installation_v2 import CollapsedLivePromptIdentityV2
import f017_event06_numerical_bridge_v1 as legacy

HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
TYPED_ID = re.compile(r"[A-Z0-9](?:[A-Z0-9-]{0,190}[A-Z0-9])?")
_SEAL = object()


def _freeze(value: object) -> object:
    if type(value) is dict:
        return tuple((key, _freeze(value[key])) for key in sorted(value))
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: object) -> object:
    if type(value) is tuple:
        if value and all(type(item) is tuple and len(item) == 2 and type(item[0]) is str for item in value):
            return {key: _thaw(item) for key, item in value}
        return [_thaw(item) for item in value]
    return value


class _Sealed:
    __slots__ = ("_inner", "_items", "sha256")

    def __new__(cls, seal: object = None, *args: object):
        del args
        if seal is not _SEAL:
            raise TypeError(f"{cls.__name__} is producer-created")
        return super().__new__(cls)

    def __init__(self, seal: object, value: dict[str, object], inner: object = None):
        del seal
        object.__setattr__(self, "_items", _freeze(value))
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "sha256", hashlib.sha256(canonical_bytes(value)).hexdigest())

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise TypeError("prompt-bound bridge authorities are immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise TypeError("prompt-bound bridge authorities are immutable")

    def get(self, key: str) -> object:
        for name, value in self._items:
            if name == key:
                return _thaw(value)
        raise KeyError(key)

    def as_dict(self) -> dict[str, object]:
        return {name: _thaw(value) for name, value in self._items}

    def immutable_view(self) -> MappingProxyType:
        return MappingProxyType(self.as_dict())

    def __copy__(self):
        raise TypeError("prompt-bound bridge authorities cannot be copied")

    def __deepcopy__(self, memo: object):
        del memo
        raise TypeError("prompt-bound bridge authorities cannot be copied")

    def __reduce_ex__(self, protocol: int):
        del protocol
        raise TypeError("prompt-bound bridge authorities cannot be pickled")


class PromptBoundIdentityBridgeInputV2(_Sealed):
    __slots__ = ()


class ValidatedNumericalBridgeV2(_Sealed):
    __slots__ = ()

    @property
    def legacy_bridge(self) -> legacy.ValidatedNumericalBridge:
        if type(self._inner) is not legacy.ValidatedNumericalBridge:
            raise TypeError("sealed historical bridge missing")
        return self._inner


class PromptBoundConsumerViewV2(_Sealed):
    __slots__ = ()

    @property
    def legacy_view(self) -> legacy.ValidatedConsumerView:
        if type(self._inner) is not legacy.ValidatedConsumerView:
            raise TypeError("sealed historical consumer view missing")
        return self._inner


def _repo_path(value: object) -> bool:
    if type(value) is not str or not value or value.startswith("/") or "\\" in value:
        return False
    return all(part not in {"", ".", ".."} for part in PurePosixPath(value).parts)


def _valid_type(value: object, category: str) -> bool:
    if category == "str":
        return type(value) is str
    if category == "sha256":
        return type(value) is str and HEX64.fullmatch(value) is not None
    if category == "git_object":
        return type(value) is str and HEX40.fullmatch(value) is not None
    if category == "typed_id":
        return type(value) is str and TYPED_ID.fullmatch(value) is not None
    if category == "repository_path":
        return _repo_path(value)
    return False


def _exact(value: object, fields: tuple[str, ...], types: dict[str, str], schema: str, kind: str) -> dict[str, object]:
    if type(value) is not dict or tuple(value) != fields or set(value) != set(fields):
        raise ValueError(f"{kind} field census")
    if value["schema"] != schema:
        raise ValueError(f"{kind} schema")
    for field in fields:
        if not _valid_type(value[field], types[field]):
            raise ValueError(f"{kind} type: {field}")
    return value


def produce_identity_bridge_input(
    event_identity: CollapsedLivePromptIdentityV2,
    installed: ValidatedIdentityAuthority,
    execution: ValidatedExecutionPlan,
) -> PromptBoundIdentityBridgeInputV2:
    """Seal the sole allowed bridge input from exact producer-created objects."""
    if type(event_identity) is not CollapsedLivePromptIdentityV2:
        raise TypeError("exact collapsed prompt identity required")
    if type(installed) is not ValidatedIdentityAuthority or installed.posture != "INSTALLED":
        raise TypeError("exact installed V12 authority required")
    if type(execution) is not ValidatedExecutionPlan:
        raise TypeError("exact sealed execution plan required")
    if event_identity.get("authority_mode") not in {
        "QUALIFICATION_ONLY", "LIVE_CANONICAL"
    }:
        raise ValueError("collapsed identity authority mode")
    installed_value = installed.as_dict()
    checks = (
        (event_identity.get("authorization_id"), installed_value["authorization_id"], "authorization"),
        (event_identity.get("package_attempt_id"), installed_value["package_attempt_id"], "package"),
        (event_identity.get("package_attempt_id"), execution.get("package_attempt_id"), "execution package"),
        (event_identity.get("primary_event_id"), execution.get("primary_event_id"), "primary event"),
        (event_identity.get("secondary_event_id"), execution.get("secondary_event_id"), "secondary event"),
        (event_identity.get("execution_plan_sha256"), execution.sha256, "execution plan"),
        (event_identity.source_sha256, installed_value["event_identity_plan_sha256"], "installed identity digest"),
        (installed.source_sha256, hashlib.sha256(canonical_bytes(installed_value)).hexdigest(), "installed digest"),
    )
    for observed, expected, detail in checks:
        if observed != expected:
            raise ValueError(f"prompt-bound bridge input: {detail}")
    value = {
        "schema": IDENTITY_INPUT_SCHEMA,
        "state": "SEALED_PROMPT_BOUND_INPUT",
        "posture": "VALIDATED_NON_AUTHORITY_VIEW",
        "authorization_id": event_identity.get("authorization_id"),
        "package_attempt_id": event_identity.get("package_attempt_id"),
        "primary_event_id": event_identity.get("primary_event_id"),
        "secondary_event_id": event_identity.get("secondary_event_id"),
        "execution_plan_sha256": event_identity.get("execution_plan_sha256"),
        "preparation_sha256": event_identity.get("preparation_sha256"),
        "collapsed_go_sha256": event_identity.get("collapsed_go_sha256"),
        "authority_mode": event_identity.get("authority_mode"),
        "prompt_repository_commit": event_identity.get("prompt_repository_commit"),
        "prompt_repository_path": event_identity.get("prompt_repository_path"),
        "prompt_sha256": event_identity.get("prompt_sha256"),
        "event_identity_plan_sha256": event_identity.source_sha256,
        "installed_authority_sha256": installed.source_sha256,
        "installation_receipt_sha256": installed_value["installation_receipt_sha256"],
    }
    _exact(value, IDENTITY_INPUT_FIELDS, IDENTITY_INPUT_TYPES, IDENTITY_INPUT_SCHEMA, "identity bridge input")
    return PromptBoundIdentityBridgeInputV2(_SEAL, value, event_identity)


def _derive_historical_bridge(
    bridge_input: PromptBoundIdentityBridgeInputV2,
    installed: ValidatedIdentityAuthority,
    identity: legacy.ValidatedIdentityStage,
    execution: ValidatedExecutionPlan,
) -> legacy.ValidatedNumericalBridge:
    """Construct the unchanged numerical authority without a legacy event-plan projection."""
    installed_value = installed.as_dict()
    equalities = (
        (bridge_input.get("installed_authority_sha256"), installed.source_sha256, "installed authority"),
        (bridge_input.get("installation_receipt_sha256"), installed_value["installation_receipt_sha256"], "receipt"),
        (bridge_input.get("event_identity_plan_sha256"), installed_value["event_identity_plan_sha256"], "identity digest"),
        (bridge_input.get("execution_plan_sha256"), execution.sha256, "execution plan"),
        (bridge_input.get("authorization_id"), identity.get("authorization_id"), "identity authorization"),
        (bridge_input.get("package_attempt_id"), identity.get("package_attempt_id"), "identity package"),
    )
    for observed, expected, detail in equalities:
        if observed != expected:
            raise ValueError(f"successor bridge provenance: {detail}")
    value = {
        "schema": legacy.BRIDGE_SCHEMA, "state": "VALIDATED",
        "identity_authority_generation": "V12", "numerical_consumer_generation": "V11",
        "numerical_contract_generation": "V4", "result_authority_generation": "V11",
        "authorization_id": bridge_input.get("authorization_id"),
        "package_attempt_id": bridge_input.get("package_attempt_id"),
        "primary_event_id": bridge_input.get("primary_event_id"),
        "secondary_event_id": bridge_input.get("secondary_event_id"),
        "source_head": execution.get("source_head"), "source_tree": execution.get("source_tree"),
        "implementation_measurement_sha256": execution.get("implementation_measurement_sha256"),
        "installed_authority_sha256": installed.source_sha256,
        "installation_receipt_sha256": installed_value["installation_receipt_sha256"],
        "event_identity_plan_sha256": bridge_input.get("event_identity_plan_sha256"),
        "execution_plan_sha256": execution.sha256,
        "identity_manifest_sha256": identity.get("identity_manifest_sha256"),
        "identity_terminal_sha256": identity.get("identity_terminal_sha256"),
        "access_census_sha256": identity.get("access_census_sha256"),
        "checkpoint_set_sha256": identity.get("checkpoint_set_sha256"),
        "descriptor_identity_sha256": identity.get("descriptor_identity_sha256"),
        "lease_owner": identity.get("lease_owner"), "graph_descriptors": identity.get("graph_descriptors"),
        "shards": execution.get("shards"), "tensor_catalog_path": execution.get("tensor_catalog_path"),
        "tensor_catalog_sha256": execution.get("tensor_catalog_sha256"),
        "primary_numerical_sha256": execution.get("primary_numerical_sha256"),
        "secondary_numerical_sha256": execution.get("secondary_numerical_sha256"),
        "numerical_contract_path": execution.get("numerical_contract_path"),
        "numerical_contract_sha256": execution.get("numerical_contract_sha256"),
        "result_authority_path": execution.get("result_authority_path"),
        "result_authority_sha256": execution.get("result_authority_sha256"),
        "result_bundle_builder_sha256": execution.get("result_bundle_builder_sha256"),
        "comparison_authority_sha256": execution.get("comparison_authority_sha256"),
        "release_authority_sha256": execution.get("release_authority_sha256"),
        "accounting_authority_sha256": execution.get("accounting_authority_sha256"),
        "primary_target_source_sha256": execution.get("primary_target_source_sha256"),
        "secondary_target_source_sha256": execution.get("secondary_target_source_sha256"),
        "attempts": 1, "retries": 0, "resume": False,
    }
    return legacy._validate_bridge_value(value)


def derive_bridge(
    bridge_input: PromptBoundIdentityBridgeInputV2,
    installed: ValidatedIdentityAuthority,
    identity: legacy.ValidatedIdentityStage,
    execution: ValidatedExecutionPlan,
) -> ValidatedNumericalBridgeV2:
    if type(bridge_input) is not PromptBoundIdentityBridgeInputV2:
        raise TypeError("sealed prompt-bound bridge input required")
    if type(installed) is not ValidatedIdentityAuthority or installed.posture != "INSTALLED":
        raise TypeError("installed V12 authority required")
    if type(identity) is not legacy.ValidatedIdentityStage or type(execution) is not ValidatedExecutionPlan:
        raise TypeError("sealed identity stage and execution plan required")
    historical = _derive_historical_bridge(bridge_input, installed, identity, execution)
    value = {
        "schema": BRIDGE_SCHEMA, "state": "VALIDATED_PROMPT_BOUND",
        "identity_bridge_input_sha256": bridge_input.sha256,
        "event_identity_plan_sha256": bridge_input.get("event_identity_plan_sha256"),
        "preparation_sha256": bridge_input.get("preparation_sha256"),
        "collapsed_go_sha256": bridge_input.get("collapsed_go_sha256"),
        "authority_mode": bridge_input.get("authority_mode"),
        "authorization_id": bridge_input.get("authorization_id"),
        "package_attempt_id": bridge_input.get("package_attempt_id"),
        "primary_event_id": bridge_input.get("primary_event_id"),
        "secondary_event_id": bridge_input.get("secondary_event_id"),
        "execution_plan_sha256": bridge_input.get("execution_plan_sha256"),
        "prompt_repository_commit": bridge_input.get("prompt_repository_commit"),
        "prompt_repository_path": bridge_input.get("prompt_repository_path"),
        "prompt_sha256": bridge_input.get("prompt_sha256"),
        "installed_authority_sha256": bridge_input.get("installed_authority_sha256"),
        "installation_receipt_sha256": bridge_input.get("installation_receipt_sha256"),
        "legacy_bridge_sha256": historical.sha256,
    }
    _exact(value, BRIDGE_FIELDS, BRIDGE_TYPES, BRIDGE_SCHEMA, "successor bridge")
    if historical.get("event_identity_plan_sha256") != value["event_identity_plan_sha256"]:
        raise ValueError("historical numerical bridge identity digest")
    if value["authority_mode"] != bridge_input.get("authority_mode"):
        raise ValueError("collapsed identity authority-mode continuity")
    return ValidatedNumericalBridgeV2(_SEAL, value, historical)


def consumer_view(
    bridge: ValidatedNumericalBridgeV2,
    role: str,
    historical_view: legacy.ValidatedConsumerView,
) -> PromptBoundConsumerViewV2:
    if type(bridge) is not ValidatedNumericalBridgeV2 or type(historical_view) is not legacy.ValidatedConsumerView:
        raise TypeError("exact sealed bridge and historical consumer view required")
    if role not in CONSUMER_ROLES or historical_view.get("bridge_sha256") != bridge.get("legacy_bridge_sha256"):
        raise ValueError("consumer bridge continuity")
    consumer_event_id = (
        bridge.get("primary_event_id") if role.startswith("PRIMARY") else
        bridge.get("secondary_event_id") if role.startswith("SECONDARY") else
        bridge.get("package_attempt_id")
    )
    value = {
        "schema": CONSUMER_VIEW_SCHEMA, "role": role,
        "bridge_sha256": bridge.sha256, "legacy_view_sha256": historical_view.sha256,
        "identity_bridge_input_sha256": bridge.get("identity_bridge_input_sha256"),
        "event_identity_plan_sha256": bridge.get("event_identity_plan_sha256"),
        "preparation_sha256": bridge.get("preparation_sha256"),
        "collapsed_go_sha256": bridge.get("collapsed_go_sha256"),
        "authority_mode": bridge.get("authority_mode"),
        "authorization_id": bridge.get("authorization_id"),
        "package_attempt_id": bridge.get("package_attempt_id"),
        "consumer_event_id": consumer_event_id,
        "prompt_repository_commit": bridge.get("prompt_repository_commit"),
        "prompt_repository_path": bridge.get("prompt_repository_path"),
        "prompt_sha256": bridge.get("prompt_sha256"),
    }
    _exact(value, CONSUMER_VIEW_FIELDS, CONSUMER_VIEW_TYPES, CONSUMER_VIEW_SCHEMA, "consumer view")
    return PromptBoundConsumerViewV2(_SEAL, value, historical_view)


def build_accounting_closure(
    bridge: ValidatedNumericalBridgeV2,
    accounting: PromptBoundConsumerViewV2,
    legacy_accounting_binding: dict[str, object],
) -> tuple[dict[str, object], str]:
    if type(bridge) is not ValidatedNumericalBridgeV2 or type(accounting) is not PromptBoundConsumerViewV2:
        raise TypeError("sealed accounting authorities required")
    if accounting.get("role") != "ACCOUNTING" or accounting.get("bridge_sha256") != bridge.sha256:
        raise ValueError("accounting consumer continuity")
    legacy_sha = hashlib.sha256(canonical_bytes(legacy_accounting_binding)).hexdigest()
    if legacy_accounting_binding.get("bridge_sha256") != bridge.get("legacy_bridge_sha256"):
        raise ValueError("legacy accounting bridge")
    value = {
        "schema": ACCOUNTING_SCHEMA, "bridge_sha256": bridge.sha256,
        "legacy_accounting_binding_sha256": legacy_sha,
        "event_identity_plan_sha256": bridge.get("event_identity_plan_sha256"),
        "preparation_sha256": bridge.get("preparation_sha256"),
        "collapsed_go_sha256": bridge.get("collapsed_go_sha256"),
        "authority_mode": bridge.get("authority_mode"),
        "prompt_repository_commit": bridge.get("prompt_repository_commit"),
        "prompt_repository_path": bridge.get("prompt_repository_path"),
        "prompt_sha256": bridge.get("prompt_sha256"),
        "authorization_id": bridge.get("authorization_id"),
        "package_attempt_id": bridge.get("package_attempt_id"),
        "primary_event_id": bridge.get("primary_event_id"),
        "secondary_event_id": bridge.get("secondary_event_id"),
        "installed_authority_sha256": bridge.get("installed_authority_sha256"),
        "installation_receipt_sha256": bridge.get("installation_receipt_sha256"),
        "result": "PASS",
    }
    _exact(value, ACCOUNTING_FIELDS, ACCOUNTING_TYPES, ACCOUNTING_SCHEMA, "accounting closure")
    return value, hashlib.sha256(canonical_bytes(value)).hexdigest()


def build_package_terminal(
    bridge: ValidatedNumericalBridgeV2,
    package_view: PromptBoundConsumerViewV2,
    legacy_package_terminal: dict[str, object],
    accounting_closure_sha256: str,
) -> tuple[dict[str, object], str]:
    if type(bridge) is not ValidatedNumericalBridgeV2 or type(package_view) is not PromptBoundConsumerViewV2:
        raise TypeError("sealed package terminal authorities required")
    if package_view.get("role") != "PACKAGE_TERMINAL" or package_view.get("bridge_sha256") != bridge.sha256:
        raise ValueError("package terminal consumer continuity")
    if type(accounting_closure_sha256) is not str or HEX64.fullmatch(accounting_closure_sha256) is None:
        raise ValueError("accounting closure digest")
    if legacy_package_terminal.get("bridge_sha256") != bridge.get("legacy_bridge_sha256"):
        raise ValueError("legacy package terminal bridge")
    value = {
        "schema": PACKAGE_TERMINAL_SCHEMA, "bridge_sha256": bridge.sha256,
        "legacy_package_terminal_sha256": hashlib.sha256(canonical_bytes(legacy_package_terminal)).hexdigest(),
        "accounting_closure_sha256": accounting_closure_sha256,
        "event_identity_plan_sha256": bridge.get("event_identity_plan_sha256"),
        "preparation_sha256": bridge.get("preparation_sha256"),
        "collapsed_go_sha256": bridge.get("collapsed_go_sha256"),
        "authority_mode": bridge.get("authority_mode"),
        "prompt_repository_commit": bridge.get("prompt_repository_commit"),
        "prompt_repository_path": bridge.get("prompt_repository_path"),
        "prompt_sha256": bridge.get("prompt_sha256"),
        "package_attempt_id": bridge.get("package_attempt_id"), "result": "COMPLETE",
    }
    _exact(value, PACKAGE_TERMINAL_FIELDS, PACKAGE_TERMINAL_TYPES, PACKAGE_TERMINAL_SCHEMA, "package terminal")
    return value, hashlib.sha256(canonical_bytes(value)).hexdigest()
