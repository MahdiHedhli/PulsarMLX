#!/usr/bin/env python3
"""Sealed V12 identity to V11 numerical execution-authority bridge."""
from __future__ import annotations

import hashlib
import re
from types import MappingProxyType

from f017_canonical_serialization_v10 import canonical_bytes
from f017_checkpoint_identity_authority_v12 import ValidatedIdentityAuthority
from f017_descriptor_lease_manager_v10 import LeaseSet, validate_descriptors
from f017_event06_execution_plan_v1 import ValidatedExecutionPlan

BRIDGE_SCHEMA = "pulsarmlx.f017.event06-v12-to-v11-numerical-authority-bridge/1.0.0"
IDENTITY_SCHEMA = "pulsarmlx.f017.event06-v12-identity-stage-binding/1.0.0"
EVENT_PLAN_SCHEMA = "pulsarmlx.f017.event06-event-identity-plan/1.0.0"
VIEW_SCHEMA = "pulsarmlx.f017.event06-v12-to-v11-consumer-view/1.0.0"
BINDING_SCHEMA = "pulsarmlx.f017.event06-v12-bridge-transition-binding/1.0.0"
PACKAGE_TERMINAL_SCHEMA = "pulsarmlx.f017.event06-v12-bridge-package-terminal/1.0.0"
BUNDLE_BINDING_SCHEMA = "pulsarmlx.f017.event06-v12-bridge-result-bundle-binding/1.0.0"
COMPARISON_BINDING_SCHEMA = "pulsarmlx.f017.event06-v12-bridge-comparison-binding/1.0.0"
RELEASE_BINDING_SCHEMA = "pulsarmlx.f017.event06-v12-bridge-release-binding/1.0.0"
ACCOUNTING_BINDING_SCHEMA = "pulsarmlx.f017.event06-v12-bridge-accounting-binding/1.0.0"
HEX64 = re.compile(r"[0-9a-f]{64}")
HEX40 = re.compile(r"[0-9a-f]{40}")
TYPED_ID = re.compile(r"[A-Z0-9](?:[A-Z0-9-]{0,190}[A-Z0-9])?")
IDENTITY_KEYS = {
    "schema", "authorization_id", "package_attempt_id", "checkpoint_set_sha256",
    "identity_manifest_sha256", "identity_terminal_sha256", "access_census_sha256",
    "descriptor_identity_sha256", "lease_owner", "graph_descriptors", "result",
}
IDENTITY_REPORT_KEYS = {
    "result", "authority_scope", "operation_class", "generation",
    "ordered_shard_digests", "checkpoint_shard_opens", "checkpoint_identity_hash_reads",
    "retained_lease_count", "identity_only_retained_count", "descriptor_identities",
    "path_reopen_count", "evidence",
}
IDENTITY_EVIDENCE_KEYS = {
    "access_journal_sha256", "shard_receipts_sha256", "lease_manifest_sha256",
    "deterministic_core_sha256", "identity_manifest_sha256", "identity_receipt_sha256",
    "identity_terminal_sha256", "identity_terminal_state",
}
EVENT_PLAN_KEYS = {
    "schema", "package_attempt_id", "primary_event_id", "secondary_event_id",
    "execution_plan_sha256",
}
DESCRIPTOR_KEYS = {"device", "inode", "mode", "size", "mtime_ns", "ctime_ns", "shard_ordinal", "role", "lease_id"}
BRIDGE_KEYS = {
    "schema", "state", "identity_authority_generation", "numerical_consumer_generation",
    "numerical_contract_generation", "result_authority_generation", "authorization_id",
    "package_attempt_id", "primary_event_id", "secondary_event_id", "source_head", "source_tree",
    "implementation_measurement_sha256", "installed_authority_sha256",
    "installation_receipt_sha256", "event_identity_plan_sha256", "execution_plan_sha256",
    "identity_manifest_sha256", "identity_terminal_sha256", "access_census_sha256",
    "checkpoint_set_sha256", "descriptor_identity_sha256", "lease_owner", "graph_descriptors",
    "shards", "tensor_catalog_path", "tensor_catalog_sha256", "primary_numerical_sha256",
    "secondary_numerical_sha256", "numerical_contract_path", "numerical_contract_sha256",
    "result_authority_path", "result_authority_sha256", "result_bundle_builder_sha256",
    "comparison_authority_sha256", "release_authority_sha256", "accounting_authority_sha256",
    "primary_target_source_sha256", "secondary_target_source_sha256", "attempts", "retries", "resume",
}
VIEW_KEYS = {
    "PRIMARY_NUMERICAL_V11": {"schema","role","bridge_sha256","authorization_id","package_attempt_id","consumer_event_id","producer_measurement_sha256","primary_numerical_sha256","tensor_catalog_path","tensor_catalog_sha256","shards","graph_descriptors","source_head","source_tree"},
    "SECONDARY_NUMERICAL_V11": {"schema","role","bridge_sha256","authorization_id","package_attempt_id","consumer_event_id","producer_measurement_sha256","secondary_numerical_sha256","tensor_catalog_path","tensor_catalog_sha256","shards","graph_descriptors","primary_terminal","primary_result_terminal_sha256","primary_receipt_sha256","primary_manifest_sha256","primary_bridge_bundle_binding_sha256","source_head","source_tree"},
    "RESULT_BUNDLE_V11": {"schema","role","bridge_sha256","authorization_id","package_attempt_id","consumer_event_id","producer_measurement_sha256","numerical_contract_sha256","durable_start_sha256","access_census_sha256"},
    "COMPARISON_V11": {"schema","bridge_sha256","authorization_id","package_attempt_id","primary_bridge_bundle_binding_sha256","secondary_bridge_bundle_binding_sha256","comparison_authority_sha256"},
    "RELEASE": {"schema","bridge_sha256","package_attempt_id","descriptor_identity_sha256","lease_owner","comparison_binding_sha256"},
    "ACCOUNTING": {"schema","bridge_sha256","authorization_id","package_attempt_id","primary_event_id","secondary_event_id","installed_authority_sha256","installation_receipt_sha256","release_binding_sha256"},
    "PACKAGE_TERMINAL": {"schema","bridge_sha256","package_attempt_id","binding_chain_head_sha256","v11_closure_root_sha256","accounting_binding_sha256"},
}
PHASES = ("PACKAGE_START","IDENTITY_TERMINAL","PRIMARY_START","PRIMARY_RESULT_TERMINAL",
          "SECONDARY_START","SECONDARY_RESULT_TERMINAL","COMPARISON_TERMINAL",
          "RELEASE_TERMINAL","ACCOUNTING_CLOSURE","V11_PACKAGE_CLOSURE")
BINDING_KEYS = {"schema","phase","bridge_sha256","package_attempt_id","subject_artifact_kind","subject_sha256","predecessor_binding_sha256","state"}
RELEASE_REPORT_KEYS = {
    "release_pass", "expected_leases", "attempted_closures", "successful_closures",
    "duplicate_closures", "unknown_leases", "live_leases_after_release",
    "remaining_live_lease_ids", "lease_states", "close_events", "idempotent_noop",
    "pending_close_evidence", "evidence_banking_failures", "result",
}
_SEAL = object()


def _freeze(value):
    if type(value) is dict:
        return tuple((key, _freeze(value[key])) for key in sorted(value))
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value):
    if type(value) is tuple:
        if value and all(type(item) is tuple and len(item) == 2 and type(item[0]) is str for item in value):
            return {key: _thaw(item) for key, item in value}
        return [_thaw(item) for item in value]
    return value


class _Sealed:
    __slots__ = ("_items", "sha256")

    def __new__(cls, seal=None, value=None):
        if seal is not _SEAL:
            raise TypeError(f"{cls.__name__} is validator-created")
        return super().__new__(cls)

    def __init__(self, seal, value):
        self._items = _freeze(value)
        self.sha256 = hashlib.sha256(canonical_bytes(value)).hexdigest()

    def get(self, key):
        for name, value in self._items:
            if name == key:
                return _thaw(value)
        raise KeyError(key)

    def immutable_view(self):
        return MappingProxyType({name: _freeze(value) for name, value in self._items})

    def as_dict(self):
        return {name: _thaw(value) for name, value in self._items}

    def __copy__(self):
        raise TypeError("sealed authority cannot be copied")

    def __deepcopy__(self, memo):
        raise TypeError("sealed authority cannot be copied")

    def __reduce_ex__(self, protocol):
        raise TypeError("sealed authority cannot be pickled")


class ValidatedIdentityStage(_Sealed):
    pass


class ValidatedNumericalBridge(_Sealed):
    pass


class ValidatedConsumerView(_Sealed):
    pass


class ValidatedBundleBinding(_Sealed):
    pass


class ValidatedComparisonBinding(_Sealed):
    pass


class ValidatedReleaseBinding(_Sealed):
    pass


class ValidatedAccountingBinding(_Sealed):
    pass


def _sha(value, name):
    if type(value) is not str or HEX64.fullmatch(value) is None:
        raise ValueError(f"bridge SHA: {name}")


def validate_identity_stage(value: object) -> ValidatedIdentityStage:
    if type(value) is not dict or set(value) != IDENTITY_KEYS:
        raise ValueError("identity-stage key census")
    if value["schema"] != IDENTITY_SCHEMA or value["result"] != "PASS":
        raise ValueError("identity-stage posture")
    for key in ("checkpoint_set_sha256","identity_manifest_sha256","identity_terminal_sha256","access_census_sha256","descriptor_identity_sha256"):
        _sha(value[key], key)
    descriptors = value["graph_descriptors"]
    validate_descriptors(descriptors)
    if set().union(*(set(item) for item in descriptors)) != DESCRIPTOR_KEYS:
        raise ValueError("identity-stage descriptor keys")
    if hashlib.sha256(canonical_bytes(descriptors)).hexdigest() != value["descriptor_identity_sha256"]:
        raise ValueError("identity-stage descriptor digest")
    if (type(value["lease_owner"]) is not str
            or value["lease_owner"] != value["package_attempt_id"]):
        raise ValueError("identity-stage lease owner")
    for descriptor in descriptors:
        expected = f"LEASE-{value['lease_owner']}-{descriptor['shard_ordinal']}"
        if descriptor["lease_id"] != expected:
            raise ValueError("identity-stage lease ownership")
    return ValidatedIdentityStage(_SEAL, value)


def bind_identity_stage(installed: ValidatedIdentityAuthority, leases: LeaseSet,
                        report: object) -> ValidatedIdentityStage:
    """Adapt the real V12 identity producer result into the sealed bridge input."""
    if (type(installed) is not ValidatedIdentityAuthority or installed.posture != "INSTALLED"
            or type(leases) is not LeaseSet):
        raise TypeError("installed V12 authority and lease set required")
    if type(report) is not dict or set(report) != IDENTITY_REPORT_KEYS:
        raise ValueError("identity producer report census")
    evidence = report["evidence"]
    if type(evidence) is not dict or set(evidence) != IDENTITY_EVIDENCE_KEYS:
        raise ValueError("identity producer evidence census")
    if (report["result"] != "PASS" or report["generation"] != "V12"
            or report["checkpoint_shard_opens"] != 6
            or report["checkpoint_identity_hash_reads"] != 6
            or report["retained_lease_count"] != 5
            or report["identity_only_retained_count"] != 0
            or report["path_reopen_count"] != 0
            or evidence["identity_terminal_state"] != "COMPLETE"
            or report["descriptor_identities"] != leases.descriptors):
        raise ValueError("identity producer report posture")
    installed_value = installed.as_dict()
    descriptors = leases.descriptors
    value = {
        "schema": IDENTITY_SCHEMA,
        "authorization_id": installed_value["authorization_id"],
        "package_attempt_id": installed_value["package_attempt_id"],
        "checkpoint_set_sha256": installed_value["checkpoint_set_sha256"],
        "identity_manifest_sha256": evidence["identity_manifest_sha256"],
        "identity_terminal_sha256": evidence["identity_terminal_sha256"],
        "access_census_sha256": evidence["access_journal_sha256"],
        "descriptor_identity_sha256": hashlib.sha256(canonical_bytes(descriptors)).hexdigest(),
        "lease_owner": installed_value["package_attempt_id"],
        "graph_descriptors": descriptors,
        "result": "PASS",
    }
    return validate_identity_stage(value)


def _validate_event_plan(value: object) -> str:
    if type(value) is not dict or set(value) != EVENT_PLAN_KEYS or value["schema"] != EVENT_PLAN_SCHEMA:
        raise ValueError("event identity plan")
    if any(type(value[key]) is not str or not value[key]
           for key in EVENT_PLAN_KEYS - {"schema", "execution_plan_sha256"}):
        raise ValueError("event identity plan values")
    _sha(value["execution_plan_sha256"], "event identity execution plan")
    if len({value["package_attempt_id"], value["primary_event_id"], value["secondary_event_id"]}) != 3:
        raise ValueError("event identity plan distinct IDs")
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def derive_bridge(installed: ValidatedIdentityAuthority, identity: ValidatedIdentityStage,
                  execution: ValidatedExecutionPlan, event_identity_plan: dict) -> ValidatedNumericalBridge:
    if type(installed) is not ValidatedIdentityAuthority or installed.posture != "INSTALLED":
        raise TypeError("bridge requires validated installed V12 authority")
    if type(identity) is not ValidatedIdentityStage or type(execution) is not ValidatedExecutionPlan:
        raise TypeError("bridge requires sealed inputs")
    event_plan_sha = _validate_event_plan(event_identity_plan)
    installed_value = installed.as_dict()
    if hashlib.sha256(canonical_bytes(installed_value)).hexdigest() != installed.source_sha256:
        raise ValueError("bridge installed authority digest")
    equalities = (
        (installed_value["package_attempt_id"], identity.get("package_attempt_id"), "installed/identity package"),
        (installed_value["package_attempt_id"], execution.get("package_attempt_id"), "installed/execution package"),
        (installed_value["authorization_id"], identity.get("authorization_id"), "authorization identity"),
        (installed_value["checkpoint_set_sha256"], identity.get("checkpoint_set_sha256"), "checkpoint set"),
        (installed_value["event_identity_plan_sha256"], event_plan_sha, "installed event plan"),
        (event_identity_plan["execution_plan_sha256"], execution.sha256, "event/execution plan"),
        (event_identity_plan["package_attempt_id"], execution.get("package_attempt_id"), "event plan package"),
        (event_identity_plan["primary_event_id"], execution.get("primary_event_id"), "primary event"),
        (event_identity_plan["secondary_event_id"], execution.get("secondary_event_id"), "secondary event"),
    )
    for left, right, name in equalities:
        if left != right:
            raise ValueError(f"bridge provenance: {name}")
    value = {
        "schema": BRIDGE_SCHEMA, "state": "VALIDATED",
        "identity_authority_generation": "V12", "numerical_consumer_generation": "V11",
        "numerical_contract_generation": "V4", "result_authority_generation": "V11",
        "authorization_id": installed_value["authorization_id"],
        "package_attempt_id": installed_value["package_attempt_id"],
        "primary_event_id": execution.get("primary_event_id"), "secondary_event_id": execution.get("secondary_event_id"),
        "source_head": execution.get("source_head"), "source_tree": execution.get("source_tree"),
        "implementation_measurement_sha256": execution.get("implementation_measurement_sha256"),
        "installed_authority_sha256": installed.source_sha256,
        "installation_receipt_sha256": installed_value["installation_receipt_sha256"],
        "event_identity_plan_sha256": event_plan_sha, "execution_plan_sha256": execution.sha256,
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
    return _validate_bridge_value(value)


def _validate_bridge_value(value: object) -> ValidatedNumericalBridge:
    if type(value) is not dict or set(value) != BRIDGE_KEYS:
        raise ValueError("bridge key census")
    if (value["schema"] != BRIDGE_SCHEMA or value["state"] != "VALIDATED"
            or value["identity_authority_generation"] != "V12"
            or value["numerical_consumer_generation"] != "V11"
            or value["numerical_contract_generation"] != "V4"
            or value["result_authority_generation"] != "V11"):
        raise ValueError("bridge generation truth")
    validate_descriptors(value["graph_descriptors"], [item["size_bytes"] for item in value["shards"][1:]])
    if type(value["shards"]) is not list or len(value["shards"]) != 6:
        raise ValueError("bridge shard census")
    for ordinal, shard in enumerate(value["shards"], start=1):
        if type(shard) is not dict or set(shard) != {"filename","size_bytes","sha256","role"}:
            raise ValueError("bridge shard keys")
        expected_role = "IDENTITY_ONLY" if ordinal == 1 else "GRAPH_PAYLOAD"
        if (type(shard["filename"]) is not str or not shard["filename"] or "/" in shard["filename"]
                or type(shard["size_bytes"]) is not int or type(shard["size_bytes"]) is bool or shard["size_bytes"] < 0
                or type(shard["sha256"]) is not str or HEX64.fullmatch(shard["sha256"]) is None
                or shard["role"] != expected_role):
            raise ValueError("bridge shard record")
    if hashlib.sha256(canonical_bytes(value["graph_descriptors"])).hexdigest() != value["descriptor_identity_sha256"]:
        raise ValueError("bridge descriptor digest")
    for key, item in value.items():
        if key.endswith("_sha256"):
            _sha(item, key)
    for key in ("authorization_id","package_attempt_id","primary_event_id","secondary_event_id"):
        if type(value[key]) is not str or TYPED_ID.fullmatch(value[key]) is None:
            raise ValueError(f"bridge identity: {key}")
    if len({value["authorization_id"],value["package_attempt_id"],value["primary_event_id"],value["secondary_event_id"]}) != 4:
        raise ValueError("bridge distinct identities")
    if type(value["source_head"]) is not str or HEX40.fullmatch(value["source_head"]) is None:
        raise ValueError("bridge source head")
    if type(value["source_tree"]) is not str or HEX40.fullmatch(value["source_tree"]) is None:
        raise ValueError("bridge source tree")
    if (type(value["lease_owner"]) is not str
            or value["lease_owner"] != value["package_attempt_id"]):
        raise ValueError("bridge lease owner")
    for descriptor in value["graph_descriptors"]:
        if descriptor["lease_id"] != f"LEASE-{value['lease_owner']}-{descriptor['shard_ordinal']}":
            raise ValueError("bridge lease ownership")
    for key in ("tensor_catalog_path","numerical_contract_path","result_authority_path"):
        item = value[key]
        if type(item) is not str or not item or item.startswith("/") or "\\" in item or any(part in {"", ".", ".."} for part in item.split("/")):
            raise ValueError(f"bridge path: {key}")
    if type(value["attempts"]) is not int or type(value["attempts"]) is bool or value["attempts"] != 1:
        raise ValueError("bridge attempts")
    if type(value["retries"]) is not int or type(value["retries"]) is bool or value["retries"] != 0 or value["resume"] is not False:
        raise ValueError("bridge retry posture")
    return ValidatedNumericalBridge(_SEAL, value)


def reconstruct_bridge(raw: bytes, expected_sha256: str) -> ValidatedNumericalBridge:
    from f017_bounded_artifact_decode_v1 import parse_artifact_bytes
    _sha(expected_sha256, "expected bridge")
    value = parse_artifact_bytes(raw)
    bridge = _validate_bridge_value(value)
    if canonical_bytes(value) != raw:
        raise ValueError("bridge canonical bytes")
    if bridge.sha256 != expected_sha256:
        raise ValueError("bridge expected digest")
    return bridge


def canonical_bridge_bytes(bridge: ValidatedNumericalBridge) -> bytes:
    if type(bridge) is not ValidatedNumericalBridge:
        raise TypeError("sealed bridge required")
    return canonical_bytes({name:_thaw(value) for name, value in bridge._items})


def validate_consumer_view(role: str, value: object) -> ValidatedConsumerView:
    keys = VIEW_KEYS.get(role)
    if keys is None or type(value) is not dict or set(value) != keys:
        raise ValueError("bridge consumer view census")
    allowed_roles = ({"PRIMARY"} if role == "PRIMARY_NUMERICAL_V11" else
                     {"SECONDARY"} if role == "SECONDARY_NUMERICAL_V11" else
                     {"PRIMARY", "SECONDARY"} if role == "RESULT_BUNDLE_V11" else set())
    if value["schema"] != VIEW_SCHEMA or ("role" in value and value["role"] not in allowed_roles):
        raise ValueError("bridge consumer view role")
    _sha(value["bridge_sha256"], "bridge view")
    for key, item in value.items():
        if key.endswith("_sha256"):
            _sha(item, key)
    for key in ("authorization_id","package_attempt_id","consumer_event_id","primary_event_id","secondary_event_id"):
        if key in value and (type(value[key]) is not str or TYPED_ID.fullmatch(value[key]) is None):
            raise ValueError(f"bridge view identity: {key}")
    for key in ("source_head","source_tree"):
        if key in value and (type(value[key]) is not str or HEX40.fullmatch(value[key]) is None):
            raise ValueError(f"bridge view source: {key}")
    for key in ("tensor_catalog_path",):
        if key in value:
            item = value[key]
            if type(item) is not str or not item or item.startswith("/") or "\\" in item or any(part in {"", ".", ".."} for part in item.split("/")):
                raise ValueError(f"bridge view path: {key}")
    if "graph_descriptors" in value:
        validate_descriptors(value["graph_descriptors"], [item["size_bytes"] for item in value["shards"][1:]])
    if role == "SECONDARY_NUMERICAL_V11":
        from f017_result_artifacts_v11 import require_primary_terminal
        require_primary_terminal(value["primary_terminal"], value["primary_result_terminal_sha256"],
                                 value["primary_receipt_sha256"], value["primary_manifest_sha256"])
    if "lease_owner" in value and (type(value["lease_owner"]) is not str or not value["lease_owner"]):
        raise ValueError("bridge view lease owner")
    return ValidatedConsumerView(_SEAL, value)


def _base_view(bridge: ValidatedNumericalBridge) -> dict:
    if type(bridge) is not ValidatedNumericalBridge:
        raise TypeError("sealed bridge required")
    return {"schema": VIEW_SCHEMA, "bridge_sha256": bridge.sha256,
            "authorization_id": bridge.get("authorization_id"),
            "package_attempt_id": bridge.get("package_attempt_id")}


def numerical_view(bridge: ValidatedNumericalBridge, role: str, *,
                   primary_binding: ValidatedConsumerView | None = None) -> ValidatedConsumerView:
    if role not in {"PRIMARY", "SECONDARY"}:
        raise ValueError("numerical bridge role")
    value = _base_view(bridge) | {
        "role": role, "consumer_event_id": bridge.get(f"{role.lower()}_event_id"),
        "producer_measurement_sha256": bridge.get("implementation_measurement_sha256"),
        f"{role.lower()}_numerical_sha256": bridge.get(f"{role.lower()}_numerical_sha256"),
        "tensor_catalog_path": bridge.get("tensor_catalog_path"),
        "tensor_catalog_sha256": bridge.get("tensor_catalog_sha256"),
        "shards": bridge.get("shards"), "graph_descriptors": bridge.get("graph_descriptors"),
        "source_head": bridge.get("source_head"), "source_tree": bridge.get("source_tree"),
    }
    if role == "SECONDARY":
        if type(primary_binding) is not ValidatedConsumerView or primary_binding.get("role") != "PRIMARY_TERMINAL_BINDING":
            raise TypeError("validated primary terminal binding required")
        if primary_binding.get("bridge_sha256") != bridge.sha256:
            raise ValueError("primary terminal bridge mismatch")
        for key in ("primary_terminal","primary_result_terminal_sha256","primary_receipt_sha256","primary_manifest_sha256","primary_bridge_bundle_binding_sha256"):
            value[key] = primary_binding.get(key)
    return validate_consumer_view(f"{role}_NUMERICAL_V11", value)


def result_bundle_view(bridge: ValidatedNumericalBridge, role: str, durable_start_sha256: str) -> ValidatedConsumerView:
    _sha(durable_start_sha256, "durable start")
    value = _base_view(bridge) | {"role": role, "consumer_event_id": bridge.get(f"{role.lower()}_event_id"),
        "producer_measurement_sha256": bridge.get("implementation_measurement_sha256"),
        "numerical_contract_sha256": bridge.get("numerical_contract_sha256"),
        "durable_start_sha256": durable_start_sha256, "access_census_sha256": bridge.get("access_census_sha256")}
    return validate_consumer_view("RESULT_BUNDLE_V11", value)


def primary_terminal_binding(bundle: dict, bridge_sha256: str,
                             bridge_bundle_binding_sha256: str) -> ValidatedConsumerView:
    from f017_result_artifacts_v11 import require_primary_terminal
    if type(bundle) is not dict or not {"artifacts", "index"}.issubset(bundle):
        raise ValueError("primary bundle binding")
    artifacts, index = bundle["artifacts"], bundle["index"]
    terminal = artifacts["consumer_terminal"]
    _sha(bridge_sha256, "primary terminal bridge")
    _sha(bridge_bundle_binding_sha256, "primary bundle binding")
    values = {"schema":VIEW_SCHEMA,"role":"PRIMARY_TERMINAL_BINDING","bridge_sha256":bridge_sha256,
        "primary_terminal":terminal,"primary_result_terminal_sha256":index["result_terminal_sha256"],
        "primary_receipt_sha256":index["result_receipt_sha256"],"primary_manifest_sha256":index["manifest_sha256"],
        "primary_bridge_bundle_binding_sha256":bridge_bundle_binding_sha256}
    require_primary_terminal(terminal, values["primary_result_terminal_sha256"], values["primary_receipt_sha256"], values["primary_manifest_sha256"])
    keys = {"schema","role","bridge_sha256","primary_terminal","primary_result_terminal_sha256","primary_receipt_sha256","primary_manifest_sha256","primary_bridge_bundle_binding_sha256"}
    if set(values) != keys:
        raise ValueError("primary terminal binding census")
    return ValidatedConsumerView(_SEAL, values)


def source_projection(view: ValidatedConsumerView) -> tuple[dict, list[dict]]:
    if type(view) is not ValidatedConsumerView or view.get("role") not in {"PRIMARY", "SECONDARY"}:
        raise TypeError("numerical consumer view required")
    return ({"shards":view.get("shards"), "tensor_catalog_path":view.get("tensor_catalog_path"),
             "tensor_catalog_sha256":view.get("tensor_catalog_sha256")}, view.get("graph_descriptors"))


def bundle_kwargs(view: ValidatedConsumerView) -> dict:
    if type(view) is not ValidatedConsumerView or view.get("role") not in {"PRIMARY", "SECONDARY"}:
        raise TypeError("result bundle consumer view required")
    return {key:view.get(key) for key in ("authorization_id","package_attempt_id","consumer_event_id",
        "producer_measurement_sha256","durable_start_sha256","access_census_sha256")}


def build_comparison_binding(view: ValidatedConsumerView, summary: object) -> tuple[ValidatedComparisonBinding, str]:
    if type(view) is not ValidatedConsumerView:
        raise TypeError("sealed comparison view required")
    try:
        view.get("comparison_authority_sha256")
    except KeyError as exc:
        raise TypeError("sealed comparison view required") from exc
    if (type(summary) is not dict
            or summary.get("schema") != "pulsarmlx.f017.corrected-oracle-binary-comparison-summary/11.0.0"
            or summary.get("classification") not in {
                "EXACT_EXPECTED_TOKEN_STABLE", "NUMERICALLY_STABLE_TOP_K_ONLY",
                "TOP1_UNSTABLE_WITHIN_FROZEN_UNCERTAINTY", "ORACLE_DISAGREEMENT",
            }):
        raise ValueError("comparison summary posture")
    if (summary.get("authorization_id") != view.get("authorization_id")
            or summary.get("package_attempt_id") != view.get("package_attempt_id")):
        raise ValueError("comparison summary authority")
    value = {
        "schema": COMPARISON_BINDING_SCHEMA,
        "bridge_sha256": view.get("bridge_sha256"),
        "authorization_id": view.get("authorization_id"),
        "package_attempt_id": view.get("package_attempt_id"),
        "comparison_view_sha256": view.sha256,
        "comparison_summary_sha256": hashlib.sha256(canonical_bytes(summary)).hexdigest(),
        "result": "PASS",
    }
    binding = ValidatedComparisonBinding(_SEAL, value)
    return binding, binding.sha256


def build_release_binding(view: ValidatedConsumerView, report: dict) -> tuple[ValidatedReleaseBinding, str]:
    if type(view) is not ValidatedConsumerView:
        raise TypeError("sealed release view required")
    expected_lease_ids = [
        f"LEASE-{view.get('lease_owner')}-{ordinal}" for ordinal in range(2, 7)
    ]
    if (type(report) is not dict or set(report) != RELEASE_REPORT_KEYS
            or report.get("result") != "PASS"
            or report.get("expected_leases") != 5 or report.get("attempted_closures") != 5
            or report.get("successful_closures") != 5 or report.get("duplicate_closures") != 0
            or report.get("unknown_leases") != 0 or report.get("live_leases_after_release") != 0
            or report.get("remaining_live_lease_ids") != []
            or report.get("pending_close_evidence") != []
            or report.get("evidence_banking_failures") != 0
            or report.get("idempotent_noop") is not False
            or report.get("release_pass") != 1
            or set(report.get("lease_states", {})) != set(expected_lease_ids)
            or any(report["lease_states"].get(lease_id) != "CLOSED" for lease_id in expected_lease_ids)
            or type(report.get("close_events")) is not list or len(report["close_events"]) != 5
            or [event.get("lease_id") for event in report["close_events"]] != expected_lease_ids
            or [event.get("shard_ordinal") for event in report["close_events"]] != list(range(2, 7))
            or any(event.get("state") != "CLOSED" or event.get("result") != "PASS_CLOSE"
                   or event.get("evidence_result") != "PASS" for event in report["close_events"])):
        raise ValueError("release report posture")
    value = {
        "schema": RELEASE_BINDING_SCHEMA,
        "bridge_sha256": view.get("bridge_sha256"),
        "package_attempt_id": view.get("package_attempt_id"),
        "comparison_binding_sha256": view.get("comparison_binding_sha256"),
        "release_view_sha256": view.sha256,
        "release_report_sha256": hashlib.sha256(canonical_bytes(report)).hexdigest(),
        "result": "PASS",
    }
    binding = ValidatedReleaseBinding(_SEAL, value)
    return binding, binding.sha256


def build_accounting_binding(view: ValidatedConsumerView, release_binding: object) -> tuple[ValidatedAccountingBinding, str]:
    if type(view) is not ValidatedConsumerView:
        raise TypeError("sealed accounting view required")
    if (type(release_binding) is not ValidatedReleaseBinding
            or release_binding.get("schema") != RELEASE_BINDING_SCHEMA
            or release_binding.get("bridge_sha256") != view.get("bridge_sha256")
            or release_binding.sha256 != view.get("release_binding_sha256")):
        raise ValueError("accounting release binding")
    value = {
        "schema": ACCOUNTING_BINDING_SCHEMA,
        "bridge_sha256": view.get("bridge_sha256"),
        "authorization_id": view.get("authorization_id"),
        "package_attempt_id": view.get("package_attempt_id"),
        "primary_event_id": view.get("primary_event_id"),
        "secondary_event_id": view.get("secondary_event_id"),
        "installed_authority_sha256": view.get("installed_authority_sha256"),
        "installation_receipt_sha256": view.get("installation_receipt_sha256"),
        "release_binding_sha256": view.get("release_binding_sha256"),
        "package_delta": 1,
        "primary_delta": 1,
        "secondary_delta": 1,
        "historical_master_ledger": 175,
        "result": "PASS",
    }
    binding = ValidatedAccountingBinding(_SEAL, value)
    return binding, binding.sha256


def comparison_view(bridge: ValidatedNumericalBridge, primary_binding: ValidatedBundleBinding,
                    secondary_binding: ValidatedBundleBinding) -> ValidatedConsumerView:
    if type(primary_binding) is not ValidatedBundleBinding or type(secondary_binding) is not ValidatedBundleBinding:
        raise TypeError("sealed primary and secondary bundle bindings required")
    for binding, role, event_key in (
        (primary_binding, "PRIMARY", "primary_event_id"),
        (secondary_binding, "SECONDARY", "secondary_event_id"),
    ):
        if (binding.get("schema") != BUNDLE_BINDING_SCHEMA
                or binding.get("role") != role
                or binding.get("bridge_sha256") != bridge.sha256
                or binding.get("authorization_id") != bridge.get("authorization_id")
                or binding.get("package_attempt_id") != bridge.get("package_attempt_id")
                or binding.get("consumer_event_id") != bridge.get(event_key)
                or binding.get("result") != "PASS"):
            raise ValueError(f"{role.lower()} bundle binding continuity")
    if primary_binding.sha256 == secondary_binding.sha256:
        raise ValueError("primary and secondary bundle bindings must be distinct")
    value = _base_view(bridge) | {
        "primary_bridge_bundle_binding_sha256":primary_binding.sha256,
        "secondary_bridge_bundle_binding_sha256":secondary_binding.sha256,
        "comparison_authority_sha256":bridge.get("comparison_authority_sha256"),
    }
    return validate_consumer_view("COMPARISON_V11", value)


def release_view(bridge: ValidatedNumericalBridge, comparison_binding: ValidatedComparisonBinding) -> ValidatedConsumerView:
    if (type(comparison_binding) is not ValidatedComparisonBinding
            or comparison_binding.get("schema") != COMPARISON_BINDING_SCHEMA
            or comparison_binding.get("bridge_sha256") != bridge.sha256
            or comparison_binding.get("authorization_id") != bridge.get("authorization_id")
            or comparison_binding.get("package_attempt_id") != bridge.get("package_attempt_id")
            or comparison_binding.get("result") != "PASS"):
        raise TypeError("sealed comparison binding continuity")
    value = {"schema":VIEW_SCHEMA,"bridge_sha256":bridge.sha256,
        "package_attempt_id":bridge.get("package_attempt_id"),
        "descriptor_identity_sha256":bridge.get("descriptor_identity_sha256"),
        "lease_owner":bridge.get("lease_owner"),"comparison_binding_sha256":comparison_binding.sha256}
    return validate_consumer_view("RELEASE", value)


def accounting_view(bridge: ValidatedNumericalBridge, release_binding: ValidatedReleaseBinding) -> ValidatedConsumerView:
    if (type(release_binding) is not ValidatedReleaseBinding
            or release_binding.get("schema") != RELEASE_BINDING_SCHEMA
            or release_binding.get("bridge_sha256") != bridge.sha256
            or release_binding.get("package_attempt_id") != bridge.get("package_attempt_id")
            or release_binding.get("result") != "PASS"):
        raise TypeError("sealed release binding continuity")
    value = _base_view(bridge) | {"primary_event_id":bridge.get("primary_event_id"),
        "secondary_event_id":bridge.get("secondary_event_id"),
        "installed_authority_sha256":bridge.get("installed_authority_sha256"),
        "installation_receipt_sha256":bridge.get("installation_receipt_sha256"),
        "release_binding_sha256":release_binding.sha256}
    return validate_consumer_view("ACCOUNTING", value)


def package_terminal_view(bridge: ValidatedNumericalBridge, binding_chain_head_sha256: str,
                          v11_closure_root_sha256: str,
                          accounting_binding: ValidatedAccountingBinding) -> ValidatedConsumerView:
    for name, value in (("chain head",binding_chain_head_sha256),("V11 closure",v11_closure_root_sha256)):
        _sha(value, name)
    if (type(accounting_binding) is not ValidatedAccountingBinding
            or accounting_binding.get("schema") != ACCOUNTING_BINDING_SCHEMA
            or accounting_binding.get("bridge_sha256") != bridge.sha256
            or accounting_binding.get("package_attempt_id") != bridge.get("package_attempt_id")
            or accounting_binding.get("result") != "PASS"):
        raise TypeError("sealed accounting binding continuity")
    value = {"schema":VIEW_SCHEMA,"bridge_sha256":bridge.sha256,
        "package_attempt_id":bridge.get("package_attempt_id"),
        "binding_chain_head_sha256":binding_chain_head_sha256,
        "v11_closure_root_sha256":v11_closure_root_sha256,
        "accounting_binding_sha256":accounting_binding.sha256}
    return validate_consumer_view("PACKAGE_TERMINAL", value)


def build_bundle_binding(numerical: ValidatedConsumerView, bundle: ValidatedConsumerView,
                         bundle_index: dict) -> tuple[ValidatedBundleBinding, str]:
    if type(numerical) is not ValidatedConsumerView or type(bundle) is not ValidatedConsumerView:
        raise TypeError("sealed bundle views required")
    if numerical.get("bridge_sha256") != bundle.get("bridge_sha256"):
        raise ValueError("bundle bridge mismatch")
    if numerical.get("role") != bundle.get("role"):
        raise ValueError("bundle role mismatch")
    if type(bundle_index) is not dict or bundle_index.get("result") != "PASS":
        raise ValueError("bundle index")
    value = {"schema":BUNDLE_BINDING_SCHEMA,"role":numerical.get("role"),
        "bridge_sha256":numerical.get("bridge_sha256"),"authorization_id":bundle.get("authorization_id"),
        "package_attempt_id":bundle.get("package_attempt_id"),"consumer_event_id":bundle.get("consumer_event_id"),
        "bundle_index_sha256":hashlib.sha256(canonical_bytes(bundle_index)).hexdigest(),"result":"PASS"}
    binding = ValidatedBundleBinding(_SEAL, value)
    return binding, binding.sha256


def build_transition_binding(bridge: ValidatedNumericalBridge, phase: str, subject_artifact_kind: str,
                             subject_sha256: str, predecessor_binding_sha256: str) -> tuple[dict, str]:
    if phase not in PHASES or type(subject_artifact_kind) is not str or not subject_artifact_kind:
        raise ValueError("bridge transition phase")
    _sha(subject_sha256, "subject"); _sha(predecessor_binding_sha256, "predecessor")
    value = {"schema":BINDING_SCHEMA,"phase":phase,"bridge_sha256":bridge.sha256,
        "package_attempt_id":bridge.get("package_attempt_id"),"subject_artifact_kind":subject_artifact_kind,
        "subject_sha256":subject_sha256,"predecessor_binding_sha256":predecessor_binding_sha256,"state":"COMPLETE"}
    if set(value) != BINDING_KEYS:
        raise ValueError("bridge transition census")
    return value, hashlib.sha256(canonical_bytes(value)).hexdigest()


def validate_transition_chain(bridge: ValidatedNumericalBridge, records: list[dict]) -> str:
    if type(records) is not list or len(records) != len(PHASES):
        raise ValueError("bridge transition chain census")
    predecessor = "0" * 64
    for expected_phase, record in zip(PHASES, records, strict=True):
        if type(record) is not dict or set(record) != BINDING_KEYS or record["phase"] != expected_phase:
            raise ValueError("bridge transition record")
        if record["bridge_sha256"] != bridge.sha256 or record["predecessor_binding_sha256"] != predecessor:
            raise ValueError("bridge transition continuity")
        predecessor = hashlib.sha256(canonical_bytes(record)).hexdigest()
    return predecessor


def build_package_terminal(view: ValidatedConsumerView) -> dict:
    if type(view) is not ValidatedConsumerView:
        raise TypeError("package terminal view")
    expected = VIEW_KEYS["PACKAGE_TERMINAL"]
    value = {key:view.get(key) for key in expected}
    if set(value) != expected:
        raise ValueError("bridge package terminal census")
    return value | {"schema":PACKAGE_TERMINAL_SCHEMA,"result":"COMPLETE"}


def validate_package_terminal(value: object, bridge: ValidatedNumericalBridge) -> str:
    keys = {"schema","bridge_sha256","package_attempt_id","binding_chain_head_sha256",
            "v11_closure_root_sha256","accounting_binding_sha256","result"}
    if (type(value) is not dict or set(value) != keys or value["schema"] != PACKAGE_TERMINAL_SCHEMA
            or value["result"] != "COMPLETE" or value["bridge_sha256"] != bridge.sha256
            or value["package_attempt_id"] != bridge.get("package_attempt_id")):
        raise ValueError("bridge package terminal")
    for key in ("binding_chain_head_sha256","v11_closure_root_sha256","accounting_binding_sha256"):
        _sha(value[key], key)
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
