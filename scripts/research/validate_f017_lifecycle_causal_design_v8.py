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
EXPECTED_INVARIANTS = {
    "NO_EVENT04_AUTHORIZATION": ("lifecycle_model", "/unconditional_invariants/no_event04_authorization", False),
    "NO_EVENT04_EXECUTION": ("lifecycle_model", "/unconditional_invariants/no_event04_execution", False),
    "NO_ORIGINAL_CHECKPOINT_ACCESS": ("checkpoint_identity", "/original_checkpoint_access_during_design", 0),
    "HISTORICAL_LEDGER_STABLE": ("accounting", "/historical_real_payload_ledger/after", 175),
    "IDENTITY_AFTER_PACKAGE_START": ("interface", "/identity_producer_invoked_after_package_durable_start", True),
    "PRIMARY_AFTER_IDENTITY_TERMINAL": ("lifecycle_model", "/unconditional_invariants/primary_after_identity_terminal", True),
    "SECONDARY_AFTER_PRIMARY_TERMINAL": ("lifecycle_model", "/unconditional_invariants/secondary_after_primary_terminal", True),
    "UNSTARTED_PRIMARY_DELTA_ZERO": ("accounting", "/unstarted_consumer_delta", 0),
    "UNSTARTED_SECONDARY_DELTA_ZERO": ("accounting", "/unstarted_consumer_delta", 0),
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
        if set(item) != {"actor", "artifact_id", "artifact_kind", "creation_rank", "dependencies", "outcome_applicability", "payload_keys", "payload_constants", "producer_transition_id", "schema_id"}:
            raise ValueError("DAG_NODE_KEY_CENSUS")
        if item["actor"] not in {"OPERATOR", "AUTHORIZER", "PRIMARY_CONSUMER", "SECONDARY_CONSUMER", "COORDINATOR", "CHECKPOINT_IDENTITY_PRODUCER", "COMPARATOR", "EVIDENCE_BANKER"}:
            raise ValueError("DAG_NODE_ACTOR")
        if not set(item["outcome_applicability"]).issubset(expected_outcomes) or not item["outcome_applicability"]:
            raise ValueError("OUTCOME_APPLICABILITY")
        if set(item["payload_constants"]) - set(item["payload_keys"]):
            raise ValueError("PAYLOAD_CONSTANT_CENSUS")
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
        if set(descriptor) != {"schema_id", "keys", "payload_keys", "payload_constants", "creation_rank"} or descriptor["keys"] != ENVELOPE_KEYS or descriptor["creation_rank"] != node_map[artifact_id]["creation_rank"] or descriptor["schema_id"] != node_map[artifact_id]["schema_id"] or descriptor["payload_keys"] != node_map[artifact_id]["payload_keys"] or descriptor["payload_constants"] != node_map[artifact_id]["payload_constants"]:
            raise ValueError("SCHEMA_EXACT_BINDING")
        if any(key.endswith("_sha256") and key == f"{artifact_id}_sha256" for key in descriptor["payload_keys"]):
            raise ValueError("PAYLOAD_SELF_SHA")

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
            declarations = [item for item in derived_required if item.startswith("final_declaration__")]
            if len(declarations) != 1:
                raise ValueError("FAILURE_FINAL_DECLARATION")
            retained = sum(receipt_rank <= cut for receipt_rank in (15, 17, 19, 21, 23)) if cut < 44 else 0
            release_reports = [item for item in derived_required if item.startswith("descriptor_release_report")]
            if cut >= 45 and len(release_reports) != 1:
                raise ValueError("DUPLICATE_RELEASE_CHAIN")
            if retained and len(release_reports) != 1:
                raise ValueError("MISSING_RELEASE_CHAIN")
            for report_id in release_reports:
                keys = node_map[report_id]["payload_keys"]
                if not {"duplicate_closures", "unknown_leases"}.issubset(keys):
                    raise ValueError("RELEASE_OBSERVABILITY")

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

    if accounting["authorization_mint_delta"] != 0 or accounting["unstarted_consumer_delta"] != 0 or accounting["historical_real_payload_ledger"]["before"] != 175 or accounting["historical_real_payload_ledger"]["after"] != 175 or accounting["historical_real_payload_ledger"]["delta"] != 0:
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
    if interface != {"schema": "pulsarmlx.f017.corrected-oracle-authorization-consumer-interface/8.0.0", "status": STATUS, "active_live_generation": "NONE", "external_checkpoint_identity_path_permitted": False, "identity_producer_invoked_after_package_durable_start": True, "graph_path_reopen_permitted": False, "descriptor_transport": "SUBPROCESS_PASS_FDS_EXPLICIT", "attempts": 1, "retries": 0, "resume": False}:
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
