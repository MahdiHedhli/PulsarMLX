#!/usr/bin/env python3
"""Structurally independent checker for the Sequence 13 causal design.

The checker intentionally does not import the generator or generated Python
constants.  It accepts canonical bytes and independently enforces the causal
ordering and exact public-boundary model.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict, deque
from pathlib import PurePosixPath

HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
TYPED_ID = re.compile(r"[A-Z0-9](?:[A-Z0-9-]{0,190}[A-Z0-9])?")
SUPPORTED_TYPES = {"str", "enum", "bool", "sha256", "git_object", "repository_path", "typed_id", "non_boolean_integer"}
REQ_SCHEMA = "pulsarmlx.f017.event06-v12-causal-identity-to-numerical-bridge-requirements/2.0.0"
CONTRACT_SCHEMA = "pulsarmlx.f017.event06-v12-causal-identity-to-numerical-bridge-contract/3.0.0"
ORDER = (
    "RAW_FUTURE_HUMAN_GO", "SEALED_LIVE_GO_ENVELOPE", "PROMPT_BOUND_EVENT_IDENTITY_PLAN",
    "LIVE_OPERATOR_APPROVAL", "PREPARED_PRODUCTION_INSTALLATION", "FUTURE_GO_CAPABILITY",
    "DURABLE_INSTALLATION_TRANSACTION", "INSTALLED_V12_AUTHORITY", "PRE_PACKAGE_EXECUTION_CONTEXT",
    "PACKAGE_DURABLE_START", "V12_CHECKPOINT_IDENTITY_STAGE", "POST_IDENTITY_NUMERICAL_BRIDGE",
    "PRIMARY_CONSUMER_TERMINAL", "SECONDARY_CONSUMER_TERMINAL",
    "INDEPENDENT_COMPARISON_TERMINAL", "DESCRIPTOR_RELEASE_TERMINAL", "ACCOUNTING_CLOSURE",
    "PACKAGE_TERMINAL",
)
PREDECESSORS = {
    "RAW_FUTURE_HUMAN_GO": (),
    "SEALED_LIVE_GO_ENVELOPE": ("RAW_FUTURE_HUMAN_GO",),
    "PROMPT_BOUND_EVENT_IDENTITY_PLAN": ("SEALED_LIVE_GO_ENVELOPE",),
    "LIVE_OPERATOR_APPROVAL": ("SEALED_LIVE_GO_ENVELOPE", "PROMPT_BOUND_EVENT_IDENTITY_PLAN"),
    "PREPARED_PRODUCTION_INSTALLATION": ("LIVE_OPERATOR_APPROVAL", "PROMPT_BOUND_EVENT_IDENTITY_PLAN"),
    "FUTURE_GO_CAPABILITY": ("PREPARED_PRODUCTION_INSTALLATION",),
    "DURABLE_INSTALLATION_TRANSACTION": ("PREPARED_PRODUCTION_INSTALLATION", "FUTURE_GO_CAPABILITY"),
    "INSTALLED_V12_AUTHORITY": ("DURABLE_INSTALLATION_TRANSACTION", "PROMPT_BOUND_EVENT_IDENTITY_PLAN"),
    "PRE_PACKAGE_EXECUTION_CONTEXT": ("INSTALLED_V12_AUTHORITY", "PROMPT_BOUND_EVENT_IDENTITY_PLAN"),
    "PACKAGE_DURABLE_START": ("PRE_PACKAGE_EXECUTION_CONTEXT", "INSTALLED_V12_AUTHORITY"),
    "V12_CHECKPOINT_IDENTITY_STAGE": ("PACKAGE_DURABLE_START", "PRE_PACKAGE_EXECUTION_CONTEXT"),
    "POST_IDENTITY_NUMERICAL_BRIDGE": ("PRE_PACKAGE_EXECUTION_CONTEXT", "INSTALLED_V12_AUTHORITY", "V12_CHECKPOINT_IDENTITY_STAGE"),
    "PRIMARY_CONSUMER_TERMINAL": ("POST_IDENTITY_NUMERICAL_BRIDGE",),
    "SECONDARY_CONSUMER_TERMINAL": ("POST_IDENTITY_NUMERICAL_BRIDGE", "PRIMARY_CONSUMER_TERMINAL"),
    "INDEPENDENT_COMPARISON_TERMINAL": ("POST_IDENTITY_NUMERICAL_BRIDGE", "PRIMARY_CONSUMER_TERMINAL", "SECONDARY_CONSUMER_TERMINAL"),
    "DESCRIPTOR_RELEASE_TERMINAL": ("V12_CHECKPOINT_IDENTITY_STAGE", "INDEPENDENT_COMPARISON_TERMINAL"),
    "ACCOUNTING_CLOSURE": ("POST_IDENTITY_NUMERICAL_BRIDGE", "INDEPENDENT_COMPARISON_TERMINAL", "DESCRIPTOR_RELEASE_TERMINAL"),
    "PACKAGE_TERMINAL": ("INDEPENDENT_COMPARISON_TERMINAL", "DESCRIPTOR_RELEASE_TERMINAL", "ACCOUNTING_CLOSURE"),
}
EXACT_BOUNDARIES = {
    "RAW_FUTURE_HUMAN_GO": ("capture_future_human_go_evidence_v4", "RawFutureHumanGoEvidenceV4", "seal_live_go_envelope_v4", "RawFutureHumanGoEvidenceV4"),
    "SEALED_LIVE_GO_ENVELOPE": ("seal_live_go_envelope_v4", "SealedLiveGoEnvelopeV4", "produce_prompt_bound_event_identity_plan_v3", "SealedLiveGoEnvelopeV4"),
    "PROMPT_BOUND_EVENT_IDENTITY_PLAN": ("produce_prompt_bound_event_identity_plan_v3", "PromptBoundEventIdentityPlanV3", "produce_live_operator_approval_v4", "PromptBoundEventIdentityPlanV3"),
    "LIVE_OPERATOR_APPROVAL": ("produce_live_operator_approval_v4", "LiveOperatorApprovalV4", "prepare_production_installation_v4", "LiveOperatorApprovalV4"),
    "PREPARED_PRODUCTION_INSTALLATION": ("prepare_production_installation_v4", "PreparedProductionInstallationV4", "produce_future_go_capability_v4", "PreparedProductionInstallationV4"),
    "FUTURE_GO_CAPABILITY": ("produce_future_go_capability_v4", "FutureGoCapabilityV4", "commit_durable_installation_v4", "FutureGoCapabilityV4"),
    "DURABLE_INSTALLATION_TRANSACTION": ("commit_durable_installation_v4", "DurableInstallationTransactionV4", "validate_installed_v12_authority_v4", "DurableInstallationTransactionV4"),
    "INSTALLED_V12_AUTHORITY": ("validate_installed_v12_authority_v4", "InstalledV12AuthorityV4", "produce_pre_package_execution_context_v1", "InstalledV12AuthorityV4"),
    "PRE_PACKAGE_EXECUTION_CONTEXT": ("produce_pre_package_execution_context_v1", "PrePackageExecutionContextV1", "start_event06_package_v12", "PrePackageExecutionContextV1"),
    "PACKAGE_DURABLE_START": ("start_event06_package_v12", "PackageDurableStartV12", "produce_v12_checkpoint_identity_stage", "PackageDurableStartV12"),
    "V12_CHECKPOINT_IDENTITY_STAGE": ("produce_v12_checkpoint_identity_stage", "V12CheckpointIdentityStage", "produce_post_identity_numerical_bridge_v3", "V12CheckpointIdentityStage"),
    "POST_IDENTITY_NUMERICAL_BRIDGE": ("produce_post_identity_numerical_bridge_v3", "PostIdentityNumericalBridgeV3", "produce_primary_consumer_terminal_v12", "PostIdentityNumericalBridgeV3"),
    "PRIMARY_CONSUMER_TERMINAL": ("produce_primary_consumer_terminal_v12", "PrimaryConsumerTerminalV12", "produce_secondary_consumer_terminal_v12", "PrimaryConsumerTerminalV12"),
    "SECONDARY_CONSUMER_TERMINAL": ("produce_secondary_consumer_terminal_v12", "SecondaryConsumerTerminalV12", "produce_independent_comparison_terminal_v12", "SecondaryConsumerTerminalV12"),
    "INDEPENDENT_COMPARISON_TERMINAL": ("produce_independent_comparison_terminal_v12", "IndependentComparisonTerminalV12", "produce_descriptor_release_terminal_v12", "IndependentComparisonTerminalV12"),
    "DESCRIPTOR_RELEASE_TERMINAL": ("produce_descriptor_release_terminal_v12", "DescriptorReleaseTerminalV12", "produce_accounting_closure_v12", "DescriptorReleaseTerminalV12"),
    "ACCOUNTING_CLOSURE": ("produce_accounting_closure_v12", "CoordinatorAccountingClosureV12", "produce_package_terminal_v12", "CoordinatorAccountingClosureV12"),
    "PACKAGE_TERMINAL": ("produce_package_terminal_v12", "CoordinatorPackageTerminalV12", "validate_package_terminal_closure_v12", "CoordinatorPackageTerminalV12"),
}
CONTINUITY = {"authorization_id": "typed_id", "package_attempt_id": "typed_id", "event_identity_plan_sha256": "sha256", "prompt_repository_commit": "git_object", "prompt_repository_path": "repository_path", "prompt_sha256": "sha256"}
ESSENTIAL = {
    "RAW_FUTURE_HUMAN_GO": {"raw_human_go_sha256": "sha256", "target_machine": "enum", "scope": "enum", "attempts": "non_boolean_integer", "retries": "non_boolean_integer", "resume": "bool", "generation": "enum"},
    "SEALED_LIVE_GO_ENVELOPE": {"raw_human_go_sha256": "sha256", "authorization_id": "typed_id", "package_attempt_id": "typed_id", "primary_event_id": "typed_id", "secondary_event_id": "typed_id", "prompt_repository_commit": "git_object", "prompt_repository_path": "repository_path", "prompt_sha256": "sha256", "generation": "enum"},
    "PROMPT_BOUND_EVENT_IDENTITY_PLAN": {"authorization_id": "typed_id", "package_attempt_id": "typed_id", "primary_event_id": "typed_id", "secondary_event_id": "typed_id", "execution_plan_sha256": "sha256", "prompt_repository_commit": "git_object", "prompt_repository_path": "repository_path", "prompt_sha256": "sha256"},
    "LIVE_OPERATOR_APPROVAL": {**CONTINUITY, "candidate_sha256": "sha256", "execution_plan_sha256": "sha256", "live": "bool"},
    "PREPARED_PRODUCTION_INSTALLATION": {**CONTINUITY, "candidate_sha256": "sha256", "installation_receipt_sha256": "sha256", "installed_authority_candidate_sha256": "sha256", "live_authority": "bool"},
    "FUTURE_GO_CAPABILITY": {"authorization_id": "typed_id", "package_attempt_id": "typed_id", "nonce_sha256": "sha256", "expires_at_unix_ns": "non_boolean_integer", "single_use": "bool"},
    "DURABLE_INSTALLATION_TRANSACTION": {"authorization_id": "typed_id", "package_attempt_id": "typed_id", "candidate_sha256": "sha256", "installation_receipt_sha256": "sha256", "installed_authority_sha256": "sha256", "transaction_journal_sha256": "sha256", "capability_consumed": "bool"},
    "INSTALLED_V12_AUTHORITY": {**CONTINUITY, "installed_authority_sha256": "sha256", "installation_receipt_sha256": "sha256", "execution_plan_sha256": "sha256", "state": "enum"},
    "PRE_PACKAGE_EXECUTION_CONTEXT": {**CONTINUITY, "installed_authority_sha256": "sha256", "execution_plan_sha256": "sha256", "context_sha256": "sha256", "numerical_contract_sha256": "sha256", "result_authority_sha256": "sha256"},
    "PACKAGE_DURABLE_START": {**CONTINUITY, "installed_authority_sha256": "sha256", "package_claim_sha256": "sha256", "package_start_receipt_sha256": "sha256", "package_delta": "non_boolean_integer"},
    "V12_CHECKPOINT_IDENTITY_STAGE": {**CONTINUITY, "checkpoint_set_sha256": "sha256", "identity_terminal_sha256": "sha256", "access_census_sha256": "sha256", "descriptor_identity_set_sha256": "sha256", "lease_manifest_sha256": "sha256", "lease_owner_id": "typed_id", "graph_descriptor_count": "non_boolean_integer"},
    "POST_IDENTITY_NUMERICAL_BRIDGE": {**CONTINUITY, "installed_authority_sha256": "sha256", "execution_plan_sha256": "sha256", "checkpoint_set_sha256": "sha256", "identity_terminal_sha256": "sha256", "access_census_sha256": "sha256", "descriptor_identity_set_sha256": "sha256", "lease_manifest_sha256": "sha256", "lease_owner_id": "typed_id"},
    "PRIMARY_CONSUMER_TERMINAL": {**CONTINUITY, "consumer_event_id": "typed_id", "checkpoint_set_sha256": "sha256", "result_bundle_sha256": "sha256", "routing_manifest_sha256": "sha256", "consumer_terminal_sha256": "sha256", "core_execution_count": "non_boolean_integer"},
    "SECONDARY_CONSUMER_TERMINAL": {**CONTINUITY, "consumer_event_id": "typed_id", "checkpoint_set_sha256": "sha256", "result_bundle_sha256": "sha256", "routing_manifest_sha256": "sha256", "consumer_terminal_sha256": "sha256", "core_execution_count": "non_boolean_integer"},
    "INDEPENDENT_COMPARISON_TERMINAL": {**CONTINUITY, "checkpoint_set_sha256": "sha256", "primary_result_bundle_sha256": "sha256", "secondary_result_bundle_sha256": "sha256", "comparison_summary_sha256": "sha256", "comparison_terminal_sha256": "sha256", "classification": "enum"},
    "DESCRIPTOR_RELEASE_TERMINAL": {**CONTINUITY, "checkpoint_set_sha256": "sha256", "lease_manifest_sha256": "sha256", "release_report_sha256": "sha256", "release_terminal_sha256": "sha256", "attempted_closures": "non_boolean_integer", "successful_closures": "non_boolean_integer", "live_leases": "non_boolean_integer"},
    "ACCOUNTING_CLOSURE": {**CONTINUITY, "checkpoint_set_sha256": "sha256", "authorization_delta": "non_boolean_integer", "package_delta": "non_boolean_integer", "primary_delta": "non_boolean_integer", "secondary_delta": "non_boolean_integer", "historical_master_ledger": "non_boolean_integer", "accounting_receipt_sha256": "sha256"},
    "PACKAGE_TERMINAL": {**CONTINUITY, "checkpoint_set_sha256": "sha256", "primary_consumer_terminal_sha256": "sha256", "secondary_consumer_terminal_sha256": "sha256", "comparison_terminal_sha256": "sha256", "release_terminal_sha256": "sha256", "accounting_closure_sha256": "sha256", "package_receipt_sha256": "sha256", "result": "enum"},
}
NODE_KEYS = {"node_id", "stage", "producer_api", "sealed_output_type", "validator_or_consumer_api", "sealed_input_type", "direct_predecessors", "required_fields", "field_types", "allowed_side_effects", "failure_outcome", "after_package_start", "after_identity", "caller_mapping_permitted", "public_exact_type_required", "output_digest_is_external"}
REQ_KEYS = {"schema", "authority_posture", "eligible_transition", "generation", "numerical_authority", "result_authority", "historical_master_ledger", "nodes", "edges", "node_count", "edge_count", "historical_public_interfaces", "superseded_future_authority", "canonical_event_identity_plan_fields", "pre_package_forbidden_fields", "post_identity_first_authorized_fields", "prohibitions", "production_implementation_exists", "operationally_ratified", "checkpoint_access_permitted", "event06_execution_permitted"}
CONTRACT_KEYS = {"schema", "requirements_path", "requirements_sha256", "authority_posture", "eligible_transition", "generation", "numerical_authority", "result_authority", "historical_master_ledger", "superseded_future_authority", "nodes", "edges", "node_count", "edge_count", "canonical_event_identity_plan_fields", "pre_package_forbidden_fields", "post_identity_first_authorized_fields", "prohibitions", "public_construction_api", "public_validation_api", "production_implementation_exists", "operationally_ratified", "checkpoint_access_permitted", "event06_execution_permitted"}


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _load_exact(raw: bytes) -> dict[str, object]:
    value = json.loads(raw)
    if type(value) is not dict or _canonical(value) != raw:
        raise ValueError("candidate canonical object")
    return value


def _topological(nodes: list[str], edges: list[str]) -> tuple[str, ...]:
    incoming = {node: 0 for node in nodes}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if type(edge) is not str or edge.count("->") != 1:
            raise ValueError("edge syntax")
        left, right = edge.split("->")
        if left not in incoming or right not in incoming or left == right:
            raise ValueError("edge endpoint")
        incoming[right] += 1
        outgoing[left].append(right)
    queue = deque(node for node in nodes if incoming[node] == 0)
    result: list[str] = []
    while queue:
        node = queue.popleft()
        result.append(node)
        for target in outgoing[node]:
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)
    if len(result) != len(nodes):
        raise ValueError("cycle")
    return tuple(result)


def _repo_path(value: object) -> bool:
    return type(value) is str and not value.startswith("/") and "\\" not in value and all(part not in {"", ".", ".."} for part in PurePosixPath(value).parts)


def _validate_value(value: object, category: str) -> bool:
    if category in {"str", "enum"}: return type(value) is str and bool(value)
    if category == "bool": return type(value) is bool
    if category == "sha256": return type(value) is str and HEX64.fullmatch(value) is not None
    if category == "git_object": return type(value) is str and HEX40.fullmatch(value) is not None
    if category == "repository_path": return _repo_path(value)
    if category == "typed_id": return type(value) is str and TYPED_ID.fullmatch(value) is not None
    if category == "non_boolean_integer": return type(value) is int and type(value) is not bool and value >= 0
    return False


def validate_causal_bridge_candidate_v3(requirements_raw: bytes, contract_raw: bytes) -> dict[str, object]:
    req = _load_exact(requirements_raw)
    contract = _load_exact(contract_raw)
    if set(req) != REQ_KEYS or set(contract) != CONTRACT_KEYS:
        raise ValueError("top-level key census")
    if req.get("schema") != REQ_SCHEMA or contract.get("schema") != CONTRACT_SCHEMA:
        raise ValueError("schema")
    if contract.get("requirements_sha256") != hashlib.sha256(requirements_raw).hexdigest():
        raise ValueError("requirements digest")
    for key in ("authority_posture", "eligible_transition", "generation", "numerical_authority", "result_authority", "historical_master_ledger", "superseded_future_authority", "nodes", "edges", "node_count", "edge_count", "canonical_event_identity_plan_fields", "pre_package_forbidden_fields", "post_identity_first_authorized_fields", "prohibitions", "production_implementation_exists", "operationally_ratified", "checkpoint_access_permitted", "event06_execution_permitted"):
        if contract.get(key) != req.get(key):
            raise ValueError(f"requirements/contract divergence: {key}")
    if req.get("authority_posture") != "PROSPECTIVE_LIQUID_CANDIDATE" or req.get("operationally_ratified") is not False or req.get("production_implementation_exists") is not False:
        raise ValueError("truthful design posture")
    if req.get("checkpoint_access_permitted") is not False or req.get("event06_execution_permitted") is not False:
        raise ValueError("zero capability")
    if req.get("generation") != "V12" or req.get("numerical_authority") != "V4_UNCHANGED" or req.get("result_authority") != "V11_UNCHANGED" or req.get("historical_master_ledger") != 175:
        raise ValueError("frozen authority drift")
    expected_superseded = [
        {"path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event06-identity-to-numerical-bridge-requirements-v1.json", "sha256": "1e7f3a1269127bf2c40cdd2eae69133f806dd094bc1fb777ad7beff4154aa5fd", "historical_bytes_preserved": True, "future_selection_permitted": False},
        {"path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event06-identity-to-numerical-bridge-v2.json", "sha256": "fdf3485232a763da602bf15afe0514e4b39b012e28d88194aeb207dd1132fb0b", "historical_bytes_preserved": True, "future_selection_permitted": False},
        {"path": "docs/architecture/reviews/evidence/f017-event06-v12-sequence12-preobservation-freeze-v1.json", "sha256": "4e9352a860ad828213a85dbe1b0cb95db05784d3190d9593a0cd9087ef858afe", "historical_bytes_preserved": True, "future_selection_permitted": False},
    ]
    if req.get("superseded_future_authority") != expected_superseded:
        raise ValueError("historical supersession guard")
    nodes = req.get("nodes")
    edges = req.get("edges")
    if type(nodes) is not list or type(edges) is not list or len(nodes) != len(ORDER):
        raise ValueError("node/edge collections")
    ids = [node.get("node_id") if type(node) is dict else None for node in nodes]
    if tuple(ids) != ORDER or req.get("node_count") != len(nodes) or req.get("edge_count") != len(edges):
        raise ValueError("derived census/order")
    expected_edges = [f"{pred}->{node}" for node in ORDER for pred in PREDECESSORS[node]]
    if edges != expected_edges or _topological(list(ORDER), edges) != ORDER:
        raise ValueError("causal graph")
    forbidden_pre = set(req.get("pre_package_forbidden_fields", []))
    first_identity = ORDER.index("V12_CHECKPOINT_IDENTITY_STAGE")
    first_bridge = ORDER.index("POST_IDENTITY_NUMERICAL_BRIDGE")
    for index, node in enumerate(nodes):
        assert type(node) is dict
        node_id = ORDER[index]
        if set(node) != NODE_KEYS or tuple(node["direct_predecessors"]) != PREDECESSORS[node_id]:
            raise ValueError(f"node shape/predecessors: {node_id}")
        boundary = (node["producer_api"], node["sealed_output_type"], node["validator_or_consumer_api"], node["sealed_input_type"])
        if boundary != EXACT_BOUNDARIES[node_id] or any(type(item) is not str or item.startswith("_") for item in boundary):
            raise ValueError(f"public exact boundary: {node_id}")
        if any(token in str(boundary).lower() for token in ("mapping", "callback", "adapter", "private", "legacy")):
            raise ValueError(f"forbidden public capability: {node_id}")
        expected_fields = {"schema": "str", "node_id": "enum", **ESSENTIAL[node_id], **{f"{pred.lower()}_sha256": "sha256" for pred in PREDECESSORS[node_id]}}
        if node["field_types"] != expected_fields or node["required_fields"] != list(expected_fields):
            raise ValueError(f"exact fields/types: {node_id}")
        if set(node["field_types"].values()) - SUPPORTED_TYPES:
            raise ValueError(f"unsupported type: {node_id}")
        if node["caller_mapping_permitted"] is not False or node["public_exact_type_required"] is not True or node["output_digest_is_external"] is not True:
            raise ValueError(f"boundary posture: {node_id}")
        if "self_sha256" in node["field_types"] or f"{node_id.lower()}_sha256" in node["field_types"]:
            raise ValueError(f"self digest: {node_id}")
        if index < first_identity and set(node["field_types"]) & forbidden_pre:
            raise ValueError(f"future identity reference: {node_id}")
        if index < first_bridge and "post_identity_numerical_bridge_sha256" in node["field_types"]:
            raise ValueError(f"future bridge reference: {node_id}")
        if node["after_package_start"] is not (index >= ORDER.index("PACKAGE_DURABLE_START")):
            raise ValueError(f"package stage flag: {node_id}")
        if node["after_identity"] is not (index >= first_identity):
            raise ValueError(f"identity stage flag: {node_id}")
    if req.get("canonical_event_identity_plan_fields") != ["schema", "authorization_id", "package_attempt_id", "primary_event_id", "secondary_event_id", "execution_plan_sha256", "prompt_repository_commit", "prompt_repository_path", "prompt_sha256"]:
        raise ValueError("canonical nine-field identity plan")
    required_prohibitions = {"ALIASES", "COERCIONS", "OPTIONAL_AUTHORITY_FIELDS", "UNKNOWN_FIELDS", "SCHEMA_UNIONS", "CALLBACKS", "CALLER_PROVIDED_ADAPTERS", "FUTURE_REFERENCES", "SELF_DIGESTS", "CYCLES", "AMBIGUOUS_OWNERSHIP", "CHECKPOINT_SET_SUBSTITUTION", "PROMPT_SUBSTITUTION", "EVENT_ID_SUBSTITUTION", "ROLE_SUBSTITUTION", "CALLER_CREATED_ACCOUNTING", "CALLER_CREATED_TERMINAL", "PRIVATE_RESEAL", "LEGACY_PROJECTION", "SERIALIZATION_ROUND_TRIP_AUTHORITY"}
    if set(req.get("prohibitions", [])) != required_prohibitions:
        raise ValueError("prohibition census")
    return {"result": "PASS", "node_count": len(nodes), "edge_count": len(edges), "topological_order": list(ORDER), "future_references": 0, "private_reseal_or_legacy_projection": 0, "caller_created_accounting_or_terminal": 0, "public_exact_type_boundaries": "PASS"}


def validate_witness_instances(contract_raw: bytes, witness_raw: bytes) -> dict[str, object]:
    contract = _load_exact(contract_raw)
    witness = _load_exact(witness_raw)
    instances = witness.get("instances")
    if type(instances) is not list or len(instances) != len(ORDER):
        raise ValueError("witness instance census")
    digests: dict[str, str] = {}
    identity_digest = None
    checkpoint_set = None
    continuity: dict[str, object] = {}
    for index, record in enumerate(instances):
        if type(record) is not dict or set(record) != {"sealed_type", "value", "sha256"}:
            raise ValueError("witness record")
        spec = contract["nodes"][index]
        value = record["value"]
        if record["sealed_type"] != spec["sealed_output_type"] or type(value) is not dict or set(value) != set(spec["required_fields"]):
            raise ValueError("witness exact type/fields")
        raw = _canonical(value)
        if record["sha256"] != hashlib.sha256(raw).hexdigest():
            raise ValueError("witness digest")
        node_id = ORDER[index]
        if value["node_id"] != node_id:
            raise ValueError("witness node identity")
        for field, category in spec["field_types"].items():
            if not _validate_value(value[field], category):
                raise ValueError(f"witness value type: {node_id}:{field}")
        for predecessor in PREDECESSORS[node_id]:
            if value[f"{predecessor.lower()}_sha256"] != digests[predecessor]:
                raise ValueError("witness predecessor binding")
        if node_id == "PROMPT_BOUND_EVENT_IDENTITY_PLAN":
            identity_digest = record["sha256"]
            continuity = {name: value[name] for name in ("authorization_id", "package_attempt_id", "prompt_repository_commit", "prompt_repository_path", "prompt_sha256")}
        if index > ORDER.index("PROMPT_BOUND_EVENT_IDENTITY_PLAN") and "event_identity_plan_sha256" in value and value["event_identity_plan_sha256"] != identity_digest:
            raise ValueError("identity digest continuity")
        for field, expected in continuity.items():
            if field in value and value[field] != expected:
                raise ValueError("prompt/identity continuity")
        if node_id == "V12_CHECKPOINT_IDENTITY_STAGE": checkpoint_set = value["checkpoint_set_sha256"]
        if index > ORDER.index("V12_CHECKPOINT_IDENTITY_STAGE") and "checkpoint_set_sha256" in value and value["checkpoint_set_sha256"] != checkpoint_set:
            raise ValueError("checkpoint-set splice")
        digests[node_id] = record["sha256"]
    if witness.get("construction_order") != list(ORDER) or witness.get("construction_counts") != {node: 1 for node in ORDER}:
        raise ValueError("one-pass construction")
    return {"result": "PASS", "instances": len(instances), "one_pass_topological_constructibility": True, "event_identity_plan_continuity": True, "checkpoint_set_splice_resistance": True}


if __name__ == "__main__":
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    req = (root / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event06-causal-identity-to-numerical-bridge-requirements-v2.json").read_bytes()
    contract = (root / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event06-causal-identity-to-numerical-bridge-v3.json").read_bytes()
    print(json.dumps(validate_causal_bridge_candidate_v3(req, contract), sort_keys=True, separators=(",", ":")))
