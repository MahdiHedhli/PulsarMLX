#!/usr/bin/env python3
"""Independent validation of the F017 V8 causal lifecycle design.

This module intentionally imports no generator, constructor, or generated
validation helper. Its semantic expectations are independently encoded here.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
STATUS = "DESIGN_FROZEN_NOT_LIVE"
FILENAMES = {
    "artifact_dag": "f017-corrected-oracle-causal-artifact-dag-v8.json",
    "artifact_schemas": "f017-corrected-oracle-artifact-schemas-v8.json",
    "checkpoint_identity": "f017-corrected-oracle-checkpoint-identity-v8.json",
    "continuity": "f017-corrected-oracle-descriptor-continuity-v8.json",
    "lifecycle_model": "f017-corrected-oracle-lifecycle-semantic-model-v8.json",
    "outcomes": "f017-corrected-oracle-outcome-obligations-v8.json",
    "path_timing": "f017-corrected-oracle-path-timing-v8.json",
    "safety_invariants": "f017-corrected-oracle-safety-invariants-v8.json",
    "accounting": "f017-corrected-oracle-event-accounting-v8.json",
    "serialization": "f017-corrected-oracle-canonical-serialization-v8.json",
    "interface": "f017-corrected-oracle-authorization-consumer-interface-v8.json",
}
OUTCOME_CLASSES = {
    "PRE_MINT_FAILURE", "AUTHORIZATION_INSTALLATION_FAILURE", "COORDINATOR_HANDSHAKE_FAILURE",
    "PACKAGE_PRE_START_FAILURE", "PACKAGE_POST_CLAIM_PRE_START_FAILURE", "CHECKPOINT_IDENTITY_PRE_START_FAILURE",
    "CHECKPOINT_IDENTITY_FAILURE", "DESCRIPTOR_LEASE_ACTIVATION_FAILURE", "PRIMARY_PRE_START_FAILURE",
    "PRIMARY_POST_START_FAILURE", "SECONDARY_PRE_START_FAILURE", "SECONDARY_POST_START_FAILURE",
    "COMPARISON_FAILURE", "EVIDENCE_BANKING_FAILURE", "COMPLETE_SUCCESS",
}
ENVELOPE_KEYS = ["schema", "artifact_id", "artifact_kind", "authorization_id", "package_attempt_id", "outcome", "creation_rank", "dependencies", "root_authorities", "payload", "result"]
FAILURE_CAPSULE_KEYS = ["failed_transition_id", "last_completed_transition_id", "durable_prefix_id", "failure_class", "atomic_terminalization", "package_delta", "primary_delta", "secondary_delta", "expected_leases", "attempted_closures", "successful_closures", "duplicate_closures", "unknown_leases", "live_leases_after_release", "lease_ordinals", "lease_evidence_artifact_ids", "classification", "mandatory_stop", "active_generation", "event_04_executed", "original_checkpoint_access"]
ROOT_AUTHORITY_PATHS = {
    "checkpoint_metadata": "docs/validation/glm52-checkpoint.json",
    "historical_master_ledger": "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v2.json",
    "numerical_contract": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v3.json",
    "numerical_requalification": "docs/architecture/reviews/evidence/f017-corrected-oracle-numerical-requalification-v3.json",
    "v7_budget_closeout": "docs/architecture/reviews/evidence/f017-checkpoint-identity-v7-design-review-budget-exhaustion-v1.json",
}


def expected_actor(artifact_id: str) -> str:
    if artifact_id == "operator_approval": return "OPERATOR"
    if artifact_id in {"candidate_authorization", "installed_authorization", "installation_receipt"}: return "AUTHORIZER"
    if artifact_id.startswith("primary_"): return "PRIMARY_CONSUMER"
    if artifact_id.startswith("secondary_"): return "SECONDARY_CONSUMER"
    if artifact_id.startswith("checkpoint_") or artifact_id == "descriptor_lease_manifest": return "CHECKPOINT_IDENTITY_PRODUCER"
    if artifact_id.startswith("comparison_"): return "COMPARATOR"
    if artifact_id.startswith("package_receipt") or artifact_id.startswith("package_terminal") or artifact_id.startswith("final_declaration") or artifact_id.startswith("failure_terminal_capsule__"): return "EVIDENCE_BANKER"
    return "COORDINATOR"


def expected_payload_keys(artifact_id: str) -> list[str]:
    fixed = {
        "operator_approval": ["operator_approval_id"], "candidate_authorization": ["authorization_id", "package_attempt_id"],
        "primary_candidate_validation": ["consumer_role", "side_effect_count"], "secondary_candidate_validation": ["consumer_role", "side_effect_count"],
        "installed_authorization": ["authorization_id", "candidate_digest"], "installation_receipt": ["candidate_digest", "installed_digest"],
        "coordinator_handshake": ["checkpoint_opens", "checkpoint_reads"], "package_claim": ["owner_nonce"],
        "package_durable_start": ["package_ledger_entry_id"], "package_ledger_entry": ["delta", "prior_entry_id"],
        "checkpoint_identity_durable_start": ["expected_total_bytes", "checkpoint_set_digest"],
        "checkpoint_access_journal_terminal": ["event_count", "terminal_event_digest"],
        "descriptor_lease_manifest": ["lease_count", "ordinals", "lease_ids", "descriptor_identities"],
        "checkpoint_identity_manifest": ["expected_total_bytes", "observed_total_bytes", "ordered_shard_receipt_digests"],
        "checkpoint_identity_receipt": ["retained_lease_count", "identity_only_retained_count"],
        "checkpoint_identity_terminal": ["mandatory_transition", "retained_lease_count"],
        "primary_descriptor_continuity_report": ["consumer_role", "descriptor_count", "ordinals", "lease_ids", "descriptor_identities", "path_reopen_count"],
        "primary_durable_start": ["event_id"], "primary_ledger_entry": ["delta", "event_id"], "primary_execution_evidence": ["synthetic_only", "layers_completed"], "primary_receipt": ["event_id", "result"], "primary_terminal": ["event_id", "result"],
        "secondary_descriptor_continuity_report": ["consumer_role", "descriptor_count", "ordinals", "lease_ids", "descriptor_identities", "path_reopen_count"],
        "secondary_durable_start": ["event_id"], "secondary_ledger_entry": ["delta", "event_id"], "secondary_execution_evidence": ["synthetic_only", "layers_completed"], "secondary_receipt": ["event_id", "result"], "secondary_terminal": ["event_id", "result"],
        "comparison_receipt": ["classification", "frozen_thresholds"], "comparison_terminal": ["classification", "result"],
        "descriptor_release_start": ["expected_leases"], "descriptor_release_report": ["attempted_closures", "successful_closures", "duplicate_closures", "unknown_leases", "live_leases_after_release", "lease_ids"], "descriptor_release_terminal": ["live_leases_after_release", "result"],
        "package_receipt": ["package_delta", "primary_delta", "secondary_delta"], "package_terminal": ["classification", "mandatory_stop"], "final_declaration": ["active_generation", "event_04_executed", "original_checkpoint_access"],
    }
    if artifact_id.startswith("checkpoint_access_event_"): return ["ordinal", "operation", "prior_event_digest"]
    if artifact_id.startswith("checkpoint_shard_receipt_"): return ["ordinal", "role", "expected_size", "observed_size", "expected_checkpoint_digest", "observed_checkpoint_digest", "retain_disposition"]
    if artifact_id.startswith("failure_terminal_capsule__"): return FAILURE_CAPSULE_KEYS
    return fixed[artifact_id]


def expected_default_rule(key: str, constants: dict) -> dict:
    if key in constants:
        return {"kind": "EXACT_CONSTANT", "value": constants[key]}
    integer_keys = {"side_effect_count", "checkpoint_opens", "checkpoint_reads", "delta", "expected_total_bytes", "observed_total_bytes", "ordinal", "expected_size", "observed_size", "event_count", "lease_count", "retained_lease_count", "identity_only_retained_count", "descriptor_count", "path_reopen_count", "layers_completed", "expected_leases", "attempted_closures", "successful_closures", "duplicate_closures", "unknown_leases", "live_leases_after_release", "package_delta", "primary_delta", "secondary_delta", "original_checkpoint_access"}
    boolean_keys = {"synthetic_only", "mandatory_stop", "event_04_executed", "cleanup_anomaly"}
    array_keys = {"ordinals", "lease_ids", "descriptor_identities", "ordered_shard_receipt_digests", "lease_ordinals", "lease_evidence_artifact_ids"}
    if key in integer_keys: return {"kind": "TYPE", "type": "INTEGER"}
    if key in boolean_keys: return {"kind": "TYPE", "type": "BOOLEAN"}
    if key in array_keys: return {"kind": "TYPE", "type": "ARRAY"}
    if key == "frozen_thresholds": return {"kind": "TYPE", "type": "OBJECT"}
    return {"kind": "TYPE", "type": "STRING"}
EXPECTED_INVARIANTS = {
    "NO_EVENT04_AUTHORIZATION": ("lifecycle_model", "/unconditional_invariants/no_event04_authorization", False),
    "NO_EVENT04_EXECUTION": ("lifecycle_model", "/unconditional_invariants/no_event04_execution", False),
    "NO_ORIGINAL_CHECKPOINT_ACCESS": ("checkpoint_identity", "/original_checkpoint_access_during_design", 0),
    "HISTORICAL_LEDGER_STABLE": ("accounting", "/historical_real_payload_ledger/after", 175),
    "IDENTITY_AFTER_PACKAGE_START": ("interface", "/identity_producer_invoked_after_package_durable_start", True),
    "PRIMARY_AFTER_IDENTITY_TERMINAL": ("lifecycle_model", "/unconditional_invariants/primary_after_identity_terminal", True),
    "SECONDARY_AFTER_PRIMARY_TERMINAL": ("lifecycle_model", "/unconditional_invariants/secondary_after_primary_terminal", True),
    "UNSTARTED_PRIMARY_DELTA_ZERO": ("accounting", "/unstarted_primary_delta", 0),
    "UNSTARTED_SECONDARY_DELTA_ZERO": ("accounting", "/unstarted_secondary_delta", 0),
    "IDENTITY_ONLY_NOT_RETAINED": ("checkpoint_identity", "/identity_only_disposition", "CLOSE_AFTER_IDENTITY_VERIFICATION"),
    "GRAPH_LEASE_COUNT": ("checkpoint_identity", "/derived_census/expected_retained_lease_count", 5),
    "PRIMARY_DESCRIPTOR_COUNT": ("continuity", "/success_reports/primary/count", 5),
    "SECONDARY_DESCRIPTOR_COUNT": ("continuity", "/success_reports/secondary/count", 5),
    "PATH_REOPEN_COUNT": ("continuity", "/path_reopen_count", 0),
    "PACKAGE_TERMINAL_AFTER_RELEASE": ("continuity", "/release/package_terminal_after_release", True),
    "NO_LIVE_LEASES_AT_TERMINAL": ("continuity", "/release/live_leases_after_success", 0),
    "NO_SELF_SHA": ("artifact_dag", "/self_references_permitted", False),
    "NO_FUTURE_SHA": ("artifact_dag", "/future_references_permitted", False),
    "NO_ARTIFACT_CYCLES": ("artifact_dag", "/conditional_cycles_permitted", False),
    "NO_P1_TRANSITION": ("lifecycle_model", "/unconditional_invariants/no_p1_transition", False),
    "RETRY_DISABLED": ("interface", "/retries", 0),
    "RESUME_DISABLED": ("interface", "/resume", False),
    "IDENTITY_HASH_EXACT_BYTES": ("checkpoint_identity", "/processing/exact_byte_count", True),
    "IDENTITY_DESCRIPTOR_STABLE": ("checkpoint_identity", "/processing/pre_post_fstat_equal", True),
    "EVIDENCE_APPEND_ONLY": ("lifecycle_model", "/unconditional_invariants/evidence_append_only", True),
}


def failure_class_for_rank(rank: int) -> str:
    if rank == 1: return "PRE_MINT_FAILURE"
    if rank <= 6: return "AUTHORIZATION_INSTALLATION_FAILURE"
    if rank == 7: return "COORDINATOR_HANDSHAKE_FAILURE"
    if rank == 8: return "PACKAGE_PRE_START_FAILURE"
    if rank <= 10: return "PACKAGE_POST_CLAIM_PRE_START_FAILURE"
    if rank == 11: return "CHECKPOINT_IDENTITY_PRE_START_FAILURE"
    if rank <= 23: return "CHECKPOINT_IDENTITY_FAILURE"
    if rank <= 28: return "DESCRIPTOR_LEASE_ACTIVATION_FAILURE"
    if rank == 29: return "PRIMARY_PRE_START_FAILURE"
    if rank <= 34: return "PRIMARY_POST_START_FAILURE"
    if rank == 35: return "SECONDARY_PRE_START_FAILURE"
    if rank <= 40: return "SECONDARY_POST_START_FAILURE"
    if rank <= 42: return "COMPARISON_FAILURE"
    return "EVIDENCE_BANKING_FAILURE"


def resolve_pointer(value: object, pointer: str) -> object:
    current = value
    for component in pointer.removeprefix("/").split("/"):
        if not component:
            continue
        if not isinstance(current, dict) or component not in current:
            raise ValueError(f"UNRESOLVED_JSON_POINTER:{pointer}")
        current = current[component]
    return current


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode() + b"\n"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_documents() -> dict[str, dict]:
    values = {}
    for key, filename in FILENAMES.items():
        path = CONTRACTS / filename
        raw = path.read_bytes()
        value = json.loads(raw)
        if raw != canonical(value):
            raise ValueError(f"NONCANONICAL_AUTHORITY:{key}")
        values[key] = value
    return values


def validate_documents(docs: dict[str, dict]) -> dict:
    dag = docs["artifact_dag"]
    schemas = docs["artifact_schemas"]
    identity = docs["checkpoint_identity"]
    continuity = docs["continuity"]
    model = docs["lifecycle_model"]
    obligations = docs["outcomes"]
    path_timing = docs["path_timing"]
    safety = docs["safety_invariants"]
    accounting = docs["accounting"]
    serialization = docs["serialization"]
    interface = docs["interface"]

    if any(value.get("status") != STATUS for value in docs.values()):
        raise ValueError("AUTHORITY_STATUS")
    if dag.get("self_references_permitted") is not False or dag.get("future_references_permitted") is not False or dag.get("conditional_cycles_permitted") is not False:
        raise ValueError("CAUSAL_POLICY")
    if dag.get("edge_semantics") != "DEPENDENCY_SHA_MUST_BE_SERIALIZED_AT_STRICTLY_LOWER_CREATION_RANK":
        raise ValueError("EDGE_SEMANTICS")
    nodes = dag["nodes"]
    node_map = {item["artifact_id"]: item for item in nodes}
    if len(node_map) != len(nodes):
        raise ValueError("DUPLICATE_ARTIFACT_ID")
    ranks = [item["creation_rank"] for item in nodes]
    if len(set(ranks)) != len(ranks) or sorted(ranks) != list(range(1, len(nodes) + 1)):
        raise ValueError("CREATION_RANK_REGISTRY")
    transition_ids = [item["producer_transition_id"] for item in nodes]
    if len(set(transition_ids)) != len(transition_ids):
        raise ValueError("TRANSITION_ID_UNIQUENESS")
    success_nodes = sorted((item for item in nodes if "COMPLETE_SUCCESS" in item["outcome_applicability"]), key=lambda item: item["creation_rank"])
    if len(success_nodes) != 48 or [item["creation_rank"] for item in success_nodes] != list(range(1, 49)):
        raise ValueError("SUCCESS_NODE_CENSUS")
    expected_outcomes = {f"{failure_class_for_rank(rank)}__AFTER_RANK_{rank:03d}" for rank in range(1, 48)} | {"COMPLETE_SUCCESS"}
    edges = 0
    for item in nodes:
        if item["artifact_kind"] != item["artifact_id"] or item["schema_id"] != f"pulsarmlx.f017.v8.artifact.{item['artifact_id']}/1.0.0":
            raise ValueError("ARTIFACT_IDENTITY")
        if set(item) != {"actor", "artifact_id", "artifact_kind", "creation_rank", "dependencies", "outcome_applicability", "payload_keys", "payload_constants", "payload_rules", "producer_transition_id", "schema_id"}:
            raise ValueError("DAG_NODE_KEY_CENSUS")
        if item["actor"] != expected_actor(item["artifact_id"]):
            raise ValueError("DAG_NODE_ACTOR")
        if not set(item["outcome_applicability"]).issubset(expected_outcomes) or not item["outcome_applicability"]:
            raise ValueError("OUTCOME_APPLICABILITY")
        if set(item["payload_constants"]) - set(item["payload_keys"]):
            raise ValueError("PAYLOAD_CONSTANT_CENSUS")
        if item["payload_keys"] != expected_payload_keys(item["artifact_id"]) or set(item["payload_rules"]) != set(item["payload_keys"]):
            raise ValueError("PAYLOAD_SEMANTIC_CENSUS")
        for dependency in item["dependencies"]:
            edges += 1
            if dependency == item["artifact_id"]:
                raise ValueError("SELF_REFERENCE")
            if dependency not in node_map:
                raise ValueError("UNKNOWN_DEPENDENCY")
            if node_map[dependency]["creation_rank"] >= item["creation_rank"]:
                raise ValueError("FUTURE_REFERENCE")
        if len(item["dependencies"]) != len(set(item["dependencies"])):
            raise ValueError("DUPLICATE_DEPENDENCY")
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(artifact_id: str) -> None:
        if artifact_id in visiting:
            raise ValueError("ARTIFACT_CYCLE")
        if artifact_id in visited:
            return
        visiting.add(artifact_id)
        for dependency in node_map[artifact_id]["dependencies"]:
            visit(dependency)
        visiting.remove(artifact_id)
        visited.add(artifact_id)
    for artifact_id in node_map:
        visit(artifact_id)
    if set(dag["root_authorities"]) != set(ROOT_AUTHORITY_PATHS):
        raise ValueError("ROOT_AUTHORITY_CENSUS")
    for authority_id, expected_path in ROOT_AUTHORITY_PATHS.items():
        binding = dag["root_authorities"][authority_id]
        if binding["path"] != expected_path or sha(ROOT / expected_path) != binding["sha256"]:
            raise ValueError("ROOT_AUTHORITY_BINDING")

    success_order = [item["artifact_id"] for item in success_nodes]
    required_subsequence = [
        "package_durable_start", "checkpoint_identity_durable_start", "checkpoint_access_journal_terminal",
        "descriptor_lease_manifest", "checkpoint_identity_manifest", "checkpoint_identity_receipt",
        "checkpoint_identity_terminal", "primary_descriptor_continuity_report", "primary_durable_start",
        "primary_terminal", "secondary_descriptor_continuity_report", "secondary_durable_start",
        "secondary_terminal", "comparison_terminal", "descriptor_release_start", "descriptor_release_report",
        "descriptor_release_terminal", "package_receipt", "package_terminal", "final_declaration",
    ]
    positions = [success_order.index(item) for item in required_subsequence]
    if positions != sorted(positions) or model["success_artifact_order"] != success_order:
        raise ValueError("SUCCESS_CAUSAL_ORDER")
    if node_map["checkpoint_identity_receipt"]["dependencies"] != ["checkpoint_identity_manifest"]:
        raise ValueError("IDENTITY_RECEIPT_DEPENDENCY")
    if "primary_descriptor_continuity_report" in node_map["primary_descriptor_continuity_report"]["dependencies"]:
        raise ValueError("PRIMARY_CONTINUITY_SELF_REFERENCE")
    if "primary_descriptor_continuity_report" not in node_map["primary_durable_start"]["dependencies"] or "secondary_descriptor_continuity_report" not in node_map["secondary_durable_start"]["dependencies"]:
        raise ValueError("CONTINUITY_DURABLE_START_BINDING")

    shard_records = identity["shards"]
    if [item["ordinal"] for item in shard_records] != [1, 2, 3, 4, 5, 6] or len({item["filename"] for item in shard_records}) != 6:
        raise ValueError("SHARD_CENSUS")
    roles = [item["role"] for item in shard_records]
    derived = {"expected_shard_count": 6, "expected_identity_only_count": roles.count("IDENTITY_ONLY"), "expected_graph_payload_count": roles.count("GRAPH_PAYLOAD"), "expected_total_bytes": sum(item["size_bytes"] for item in shard_records), "expected_retained_lease_count": roles.count("GRAPH_PAYLOAD")}
    if roles != ["IDENTITY_ONLY"] + ["GRAPH_PAYLOAD"] * 5 or identity["derived_census"] != derived or derived != {"expected_shard_count": 6, "expected_identity_only_count": 1, "expected_graph_payload_count": 5, "expected_total_bytes": 238458632928, "expected_retained_lease_count": 5}:
        raise ValueError("DERIVED_BYTE_CENSUS")
    if identity["identity_only_disposition"] != "CLOSE_AFTER_IDENTITY_VERIFICATION" or identity["graph_payload_disposition"] != "RETAIN_AS_PACKAGE_OWNED_DESCRIPTOR_LEASE" or identity["original_checkpoint_access_during_design"] != 0:
        raise ValueError("SHARD_DISPOSITION")
    if identity.get("processing") != {"open": "ROOT_DESCRIPTOR_RELATIVE_NOFOLLOW_READ_ONLY", "hash": "COMPLETE_DESCRIPTOR_SHA256", "pre_post_fstat_equal": True, "exact_byte_count": True, "durable_shard_receipt_before_next": True}:
        raise ValueError("IDENTITY_PROCESSING")
    checkpoint_binding = dag["root_authorities"].get("checkpoint_metadata")
    checkpoint_path = ROOT / checkpoint_binding["path"]
    if sha(checkpoint_path) != checkpoint_binding["sha256"]:
        raise ValueError("CHECKPOINT_METADATA_BINDING")
    checkpoint_metadata = json.loads(checkpoint_path.read_bytes())
    expected_shards = [{**record, "ordinal": ordinal, "role": "IDENTITY_ONLY" if ordinal == 1 else "GRAPH_PAYLOAD"} for ordinal, record in enumerate(checkpoint_metadata["files"], start=1)]
    if shard_records != expected_shards or checkpoint_metadata["total_bytes"] != derived["expected_total_bytes"]:
        raise ValueError("CHECKPOINT_METADATA_SHARD_BINDING")

    expected_fields = ["device", "inode", "mode", "size", "mtime_ns", "ctime_ns", "shard_ordinal", "role", "lease_id"]
    if continuity["descriptor_transport"] != "SUBPROCESS_PASS_FDS_EXPLICIT" or continuity["path_reopen_permitted"] is not False or continuity["path_reopen_count"] != 0 or continuity["identity_only_descriptor_permitted"] is not False:
        raise ValueError("DESCRIPTOR_TRANSPORT")
    if continuity["descriptor_identity_fields"] != expected_fields or continuity["exact_comparison_to_lease_manifest"] is not True:
        raise ValueError("DESCRIPTOR_IDENTITY_FIELDS")
    for role in ("primary", "secondary"):
        report = continuity["success_reports"][role]
        if report["count"] != 5 or report["ordinals"] != [2, 3, 4, 5, 6] or report["self_sha_field_permitted"] is not False:
            raise ValueError(f"{role.upper()}_CONTINUITY_CENSUS")
    if continuity["release"] != {"expected_leases": 5, "duplicate_closures": 0, "unknown_leases": 0, "live_leases_after_success": 0, "package_terminal_after_release": True}:
        raise ValueError("DESCRIPTOR_RELEASE")

    if set(schemas["artifacts"]) != set(node_map) or schemas["strict_key_census"] is not True or schemas["unknown_fields"] != "REJECT":
        raise ValueError("SCHEMA_COVERAGE")
    for artifact_id, descriptor in schemas["artifacts"].items():
        if set(descriptor) != {"schema_id", "keys", "payload_keys", "payload_constants", "payload_rules", "creation_rank"} or descriptor["keys"] != ENVELOPE_KEYS or descriptor["creation_rank"] != node_map[artifact_id]["creation_rank"] or descriptor["schema_id"] != node_map[artifact_id]["schema_id"] or descriptor["payload_keys"] != node_map[artifact_id]["payload_keys"] or descriptor["payload_constants"] != node_map[artifact_id]["payload_constants"] or descriptor["payload_rules"] != node_map[artifact_id]["payload_rules"]:
            raise ValueError("SCHEMA_EXACT_BINDING")
        for key, rule in descriptor["payload_rules"].items():
            if rule.get("kind") not in {"EXACT_CONSTANT", "TYPE", "NONNEGATIVE_INTEGER", "EQUAL_PAYLOAD_FIELD", "EQUAL_ARTIFACT_PAYLOAD_FIELD"}:
                raise ValueError("PAYLOAD_RULE_KIND")
            if key in descriptor["payload_constants"] and rule != {"kind": "EXACT_CONSTANT", "value": descriptor["payload_constants"][key]}:
                raise ValueError("PAYLOAD_CONSTANT_RULE_BINDING")
            override = None
            if artifact_id.startswith("checkpoint_shard_receipt_") and key == "observed_size": override = {"kind": "EQUAL_PAYLOAD_FIELD", "field": "expected_size"}
            if artifact_id.startswith("checkpoint_shard_receipt_") and key == "observed_checkpoint_digest": override = {"kind": "EQUAL_PAYLOAD_FIELD", "field": "expected_checkpoint_digest"}
            if artifact_id in {"primary_descriptor_continuity_report", "secondary_descriptor_continuity_report"} and key in {"lease_ids", "descriptor_identities"}: override = {"kind": "EQUAL_ARTIFACT_PAYLOAD_FIELD", "artifact_id": "descriptor_lease_manifest", "field": key}
            if artifact_id == "descriptor_release_report" and key == "lease_ids": override = {"kind": "EQUAL_ARTIFACT_PAYLOAD_FIELD", "artifact_id": "descriptor_lease_manifest", "field": "lease_ids"}
            if artifact_id.startswith("failure_terminal_capsule__") and key in {"attempted_closures", "successful_closures", "duplicate_closures", "unknown_leases"}: override = {"kind": "NONNEGATIVE_INTEGER"}
            if rule != (override or expected_default_rule(key, descriptor["payload_constants"])):
                raise ValueError("PAYLOAD_RULE_EXACT_SEMANTICS")
        if any(key.endswith("_sha256") and key == f"{artifact_id}_sha256" for key in descriptor["payload_keys"]):
            raise ValueError("PAYLOAD_SELF_SHA")
    critical_constants = {
        "primary_candidate_validation": {"consumer_role": "PRIMARY", "side_effect_count": 0},
        "secondary_candidate_validation": {"consumer_role": "SECONDARY", "side_effect_count": 0},
        "coordinator_handshake": {"checkpoint_opens": 0, "checkpoint_reads": 0},
        "checkpoint_identity_durable_start": {"expected_total_bytes": checkpoint_metadata["total_bytes"], "checkpoint_set_digest": checkpoint_metadata["checkpoint_set_sha256"]},
        "checkpoint_access_journal_terminal": {"event_count": 6},
        "descriptor_lease_manifest": {"lease_count": 5, "ordinals": [2, 3, 4, 5, 6]},
        "checkpoint_identity_manifest": {"expected_total_bytes": checkpoint_metadata["total_bytes"], "observed_total_bytes": checkpoint_metadata["total_bytes"]},
        "checkpoint_identity_receipt": {"retained_lease_count": 5, "identity_only_retained_count": 0},
        "checkpoint_identity_terminal": {"mandatory_transition": "COMPLETE", "retained_lease_count": 5},
        "package_ledger_entry": {"delta": 1}, "primary_ledger_entry": {"delta": 1}, "secondary_ledger_entry": {"delta": 1},
        "primary_descriptor_continuity_report": {"consumer_role": "PRIMARY", "descriptor_count": 5, "ordinals": [2, 3, 4, 5, 6], "path_reopen_count": 0},
        "secondary_descriptor_continuity_report": {"consumer_role": "SECONDARY", "descriptor_count": 5, "ordinals": [2, 3, 4, 5, 6], "path_reopen_count": 0},
        "primary_execution_evidence": {"synthetic_only": True}, "secondary_execution_evidence": {"synthetic_only": True},
        "comparison_receipt": {"frozen_thresholds": {"max_abs": 0.0065169706285814755, "rmse": 0.003463567697419031, "cosine_min": 0.9999999985448085, "top_n": 32}},
        "descriptor_release_start": {"expected_leases": 5},
        "descriptor_release_report": {"attempted_closures": 5, "successful_closures": 5, "duplicate_closures": 0, "unknown_leases": 0, "live_leases_after_release": 0},
        "descriptor_release_terminal": {"live_leases_after_release": 0, "result": "PASS"},
        "package_receipt": {"package_delta": 1, "primary_delta": 1, "secondary_delta": 1},
        "package_terminal": {"classification": "COMPLETE_SUCCESS", "mandatory_stop": True},
        "final_declaration": {"active_generation": "NONE", "event_04_executed": False, "original_checkpoint_access": 0},
    }
    for artifact_id, expected in critical_constants.items():
        if node_map[artifact_id]["payload_constants"] != expected:
            raise ValueError(f"CRITICAL_PAYLOAD_CONSTANTS:{artifact_id}")
    for ordinal, shard in enumerate(expected_shards, start=1):
        access = node_map[f"checkpoint_access_event_{ordinal}"]
        receipt = node_map[f"checkpoint_shard_receipt_{ordinal}"]
        if access["payload_constants"] != {"ordinal": ordinal, "operation": "ROOT_RELATIVE_NOFOLLOW_OPEN_AND_COMPLETE_SHA256"}:
            raise ValueError("ACCESS_EVENT_CONSTANTS")
        expected_receipt = {"ordinal": ordinal, "role": shard["role"], "expected_size": shard["size_bytes"], "expected_checkpoint_digest": shard["sha256"], "retain_disposition": "CLOSE_AFTER_IDENTITY_VERIFICATION" if ordinal == 1 else "RETAIN_AS_PACKAGE_OWNED_DESCRIPTOR_LEASE"}
        if receipt["payload_constants"] != expected_receipt or receipt["payload_rules"]["observed_size"] != {"kind": "EQUAL_PAYLOAD_FIELD", "field": "expected_size"} or receipt["payload_rules"]["observed_checkpoint_digest"] != {"kind": "EQUAL_PAYLOAD_FIELD", "field": "expected_checkpoint_digest"}:
            raise ValueError("SHARD_RECEIPT_SEMANTICS")
    for report_id in ("primary_descriptor_continuity_report", "secondary_descriptor_continuity_report"):
        if node_map[report_id]["payload_rules"]["lease_ids"] != {"kind": "EQUAL_ARTIFACT_PAYLOAD_FIELD", "artifact_id": "descriptor_lease_manifest", "field": "lease_ids"} or node_map[report_id]["payload_rules"]["descriptor_identities"] != {"kind": "EQUAL_ARTIFACT_PAYLOAD_FIELD", "artifact_id": "descriptor_lease_manifest", "field": "descriptor_identities"}:
            raise ValueError("CONTINUITY_PAYLOAD_SEMANTICS")

    if set(obligations["outcomes"]) != expected_outcomes or obligations["derivation"] != "CAUSAL_DAG_OUTCOME_APPLICABILITY":
        raise ValueError("OUTCOME_CENSUS")
    all_ids = set(node_map)
    for outcome, obligation in obligations["outcomes"].items():
        derived_required = {item["artifact_id"] for item in nodes if outcome in item["outcome_applicability"]}
        if set(obligation["required"]) != derived_required or set(obligation["forbidden"]) != all_ids - derived_required or set(obligation["required"]) & set(obligation["forbidden"]):
            raise ValueError("OUTCOME_PARTITION")
        cut = obligation["durable_prefix_rank"]
        expected_class = "COMPLETE_SUCCESS" if outcome == "COMPLETE_SUCCESS" else failure_class_for_rank(cut)
        expected_last = next(item["artifact_id"] for item in success_nodes if item["creation_rank"] == cut)
        if obligation["outcome_class"] != expected_class or obligation["last_completed_artifact_id"] != expected_last or obligation["failed_transition_id"] != (None if outcome == "COMPLETE_SUCCESS" else f"FAIL_{outcome}"):
            raise ValueError("OUTCOME_CUT_BINDING")
        if obligation["package_delta"] != int(cut >= node_map["package_durable_start"]["creation_rank"]) or obligation["primary_delta"] != int(cut >= node_map["primary_durable_start"]["creation_rank"]) or obligation["secondary_delta"] != int(cut >= node_map["secondary_durable_start"]["creation_rank"]):
            raise ValueError("OUTCOME_ACCOUNTING")
        if obligation["primary_delta"] == 0 and "primary_durable_start" not in obligation["forbidden"]:
            raise ValueError("UNSTARTED_PRIMARY_EVIDENCE")
        if obligation["secondary_delta"] == 0 and "secondary_durable_start" not in obligation["forbidden"]:
            raise ValueError("UNSTARTED_SECONDARY_EVIDENCE")
        if obligation["outcome_class"] == "EVIDENCE_BANKING_FAILURE" and not {"primary_descriptor_continuity_report", "secondary_descriptor_continuity_report"}.issubset(derived_required):
            raise ValueError("EVIDENCE_BANKING_PREFIX")
        if obligation["live_leases_at_terminal"] != 0:
            raise ValueError("OUTCOME_LIVE_LEASES")
        if outcome != "COMPLETE_SUCCESS":
            capsules = [item for item in derived_required if item.startswith("failure_terminal_capsule__")]
            if len(capsules) != 1 or len(derived_required) != cut + 1:
                raise ValueError("ATOMIC_FAILURE_TERMINALIZATION_CENSUS")
            capsule = node_map[capsules[0]]
            access_ranks = {ordinal: node_map[f"checkpoint_access_event_{ordinal}"]["creation_rank"] for ordinal in range(2, 7)}
            retained_ordinals = [ordinal for ordinal, access_rank in access_ranks.items() if access_rank <= cut] if cut < node_map["descriptor_release_report"]["creation_rank"] else []
            expected_constants = {"failed_transition_id": f"FAIL_{outcome}", "last_completed_transition_id": node_map[expected_last]["producer_transition_id"], "durable_prefix_id": expected_last, "failure_class": expected_class, "atomic_terminalization": "SINGLE_CANONICAL_TEMP_WRITE_FSYNC_EXCLUSIVE_RENAME_DIRECTORY_FSYNC", "package_delta": obligation["package_delta"], "primary_delta": obligation["primary_delta"], "secondary_delta": obligation["secondary_delta"], "expected_leases": len(retained_ordinals), "live_leases_after_release": 0, "lease_ordinals": retained_ordinals, "lease_evidence_artifact_ids": [f"checkpoint_access_event_{ordinal}" for ordinal in retained_ordinals], "classification": expected_class, "mandatory_stop": True, "active_generation": "NONE", "event_04_executed": False, "original_checkpoint_access": 0}
            if capsule["payload_constants"] != expected_constants:
                raise ValueError("ATOMIC_FAILURE_TERMINALIZATION_SEMANTICS")
            for observable in ("attempted_closures", "successful_closures", "duplicate_closures", "unknown_leases"):
                if capsule["payload_rules"][observable] != {"kind": "NONNEGATIVE_INTEGER"}:
                    raise ValueError("CLEANUP_OBSERVABILITY")

    if path_timing["production_exception_count"] != 0 or path_timing["artifact_schema_count"] != len(node_map) or set(path_timing["paths"]) != set(node_map):
        raise ValueError("PATH_TIMING_COVERAGE")
    for artifact_id, timing in path_timing["paths"].items():
        if timing != {"producer_transition_id": node_map[artifact_id]["producer_transition_id"], "before": "MUST_NOT_EXIST", "after_successful_producer": "MUST_EXIST_REGULAR_FILE", "immutable_after_creation": True, "readback": "DESCRIPTOR_RELATIVE_EXACT_CANONICAL_BYTES_AND_SHA256", "terminal_retention": "RETAIN_AS_APPEND_ONLY_EVIDENCE"}:
            raise ValueError("PATH_TIMING_EXACT")

    invariant_map = {item["id"]: item for item in safety["invariants"]}
    if set(invariant_map) != set(EXPECTED_INVARIANTS):
        raise ValueError("SAFETY_INVARIANT_CENSUS")
    for invariant_id, (source_authority, source_pointer, expected) in EXPECTED_INVARIANTS.items():
        item = invariant_map[invariant_id]
        if set(item) != {"id", "scope", "source_authority", "source_json_pointer", "operation", "expected", "validator_id", "failure_class", "mutation_id"} or item["source_authority"] != source_authority or item["source_json_pointer"] != source_pointer or item["expected"] != expected or item["operation"] != "EXACT_EQUAL" or item["validator_id"] != f"VALIDATE_{invariant_id}" or item["mutation_id"] != f"MUTATE_{invariant_id}" or item["failure_class"] != "SAFETY_INVARIANT_FAILURE":
            raise ValueError("SAFETY_INVARIANT_EXACT")
        if resolve_pointer(docs[source_authority], source_pointer) != expected:
            raise ValueError("SAFETY_INVARIANT_SOURCE")

    if accounting["authorization_mint_delta"] != 0 or accounting["unstarted_primary_delta"] != 0 or accounting["unstarted_secondary_delta"] != 0 or accounting["historical_real_payload_ledger"]["before"] != 175 or accounting["historical_real_payload_ledger"]["after"] != 175 or accounting["historical_real_payload_ledger"]["delta"] != 0:
        raise ValueError("ACCOUNTING_ROOT")
    if accounting["package_start_rank"] != node_map["package_durable_start"]["creation_rank"] or accounting["primary_start_rank"] != node_map["primary_durable_start"]["creation_rank"] or accounting["secondary_start_rank"] != node_map["secondary_durable_start"]["creation_rank"]:
        raise ValueError("ACCOUNTING_START_RANKS")
    if set(accounting["outcome_deltas"]) != expected_outcomes:
        raise ValueError("ACCOUNTING_OUTCOME_CENSUS")
    for outcome in expected_outcomes:
        expected = {key: obligations["outcomes"][outcome][key] for key in ("package_delta", "primary_delta", "secondary_delta")}
        if accounting["outcome_deltas"][outcome] != expected:
            raise ValueError("ACCOUNTING_OUTCOME")
    if serialization != {"schema": "pulsarmlx.f017.canonical-json-bytes/1.0.0", "status": STATUS, "encoding": "UTF-8", "bom": False, "sort_keys": True, "separators": [",", ":"], "ensure_ascii": True, "allow_nan": False, "trailing_newline_count": 1, "duplicate_keys": "REJECT", "artifact_contains_own_sha256": False}:
        raise ValueError("CANONICAL_SERIALIZATION")
    if interface != {"schema": "pulsarmlx.f017.corrected-oracle-authorization-consumer-interface/8.0.0", "status": STATUS, "active_live_generation": "NONE", "external_checkpoint_identity_path_permitted": False, "identity_producer_invoked_after_package_durable_start": True, "graph_path_reopen_permitted": False, "descriptor_transport": "SUBPROCESS_PASS_FDS_EXPLICIT", "lease_inception": "SUCCESSFUL_GRAPH_PAYLOAD_CHECKPOINT_ACCESS_EVENT_OPEN", "failure_terminalization": "SINGLE_CANONICAL_TEMP_WRITE_FSYNC_EXCLUSIVE_RENAME_DIRECTORY_FSYNC", "failure_terminalization_partial_authority": "NONE", "failure_terminalization_failure_recursion_terminator": "NO_NEW_DURABLE_PREFIX_AND_PROCESS_EXIT_DESCRIPTOR_CLOSE", "attempts": 1, "retries": 0, "resume": False}:
        raise ValueError("AUTHORIZATION_INTERFACE")
    expected_transitions = [{"id": item["producer_transition_id"], "actor": item["actor"], "artifact_created": item["artifact_id"], "creation_rank": item["creation_rank"], "outcome_applicability": item["outcome_applicability"], "to": f"ARTIFACT_BANKED__{item['artifact_id'].upper()}"} for item in nodes]
    expected_states = sorted({"DESIGN_ONLY"} | {item["to"] for item in expected_transitions})
    expected_unconditional = {"no_event04_authorization": False, "no_event04_execution": False, "primary_after_identity_terminal": True, "secondary_after_primary_terminal": True, "no_p1_transition": False, "evidence_append_only": True}
    if set(model["outcomes"]) != expected_outcomes or set(model["outcome_classes"]) != OUTCOME_CLASSES or model["numerical_contract"] != dag["root_authorities"]["numerical_contract"] or model["transitions"] != expected_transitions or model["states"] != expected_states or model["unconditional_invariants"] != expected_unconditional or any("P1" in json.dumps(item) for item in model["transitions"]):
        raise ValueError("LIFECYCLE_MODEL")
    return {"result": "PASS", "artifact_count": len(nodes), "dependency_edge_count": edges, "outcome_count": len(expected_outcomes), "safety_invariant_count": len(invariant_map)}


def validate(run_symbolic: bool = True) -> dict:
    docs = load_documents()
    result = validate_documents(docs)
    manifest_path = CONTRACTS / "f017-corrected-oracle-v8-design-authority-manifest.json"
    raw_manifest = manifest_path.read_bytes()
    manifest = json.loads(raw_manifest)
    if raw_manifest != canonical(manifest) or manifest["status"] != STATUS or manifest["active_live_generation"] != "NONE" or manifest["implementation_phase_entered"] is not False:
        raise ValueError("MANIFEST_POSTURE")
    expected_authorities = set(FILENAMES) | {"finding_reproduction", "mechanical_qualification", "design_generator", "symbolic_constructor", "transitive_closure_validator", "independent_validator", "design_mutation_suite", "design_qualifier", "active_generation"}
    if set(manifest["authorities"]) != expected_authorities:
        raise ValueError("MANIFEST_CENSUS")
    for binding in list(manifest["authorities"].values()) + list(manifest["root_authorities"].values()):
        path = ROOT / binding["path"]
        if not path.is_file() or sha(path) != binding["sha256"]:
            raise ValueError("MANIFEST_BINDING")
    if run_symbolic:
        with tempfile.TemporaryDirectory() as raw_output:
            command = [sys.executable, str(ROOT / "scripts/research/construct_f017_lifecycle_v8_symbolically.py"), "--output-root", raw_output]
            completed = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
            symbolic = json.loads(completed.stdout)
        if symbolic["result"] != "PASS" or symbolic["constructed_outcomes"] != 48 or symbolic["self_references"] != 0 or symbolic["future_references"] != 0 or symbolic["artifact_cycles"] != 0 or symbolic["original_checkpoint_access"] != 0:
            raise ValueError("SYMBOLIC_CONSTRUCTIBILITY")
        result["symbolic"] = {key: symbolic[key] for key in ("constructed_outcomes", "real_artifacts_created", "maximum_closure_depth", "original_checkpoint_access")}
    return result


if __name__ == "__main__":
    print(json.dumps(validate(), sort_keys=True, separators=(",", ":")))
