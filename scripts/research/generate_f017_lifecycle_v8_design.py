#!/usr/bin/env python3
"""Generate the F017 V8 causal lifecycle design authorities.

This generator is not used by the independent validator. It converts the
reviewed causal source model below into canonical, reviewable JSON views.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
STATUS = "DESIGN_FROZEN_NOT_LIVE"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode() + b"\n"


def bank(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def authority(path: str) -> dict[str, str]:
    return {"path": path, "sha256": sha(ROOT / path)}


def node(artifact_id: str, rank: int, transition_id: str, dependencies: list[str], outcomes: list[str], payload_keys: list[str], actor: str, payload_constants: dict | None = None) -> dict:
    return {
        "actor": actor,
        "artifact_id": artifact_id,
        "artifact_kind": artifact_id,
        "creation_rank": rank,
        "dependencies": dependencies,
        "outcome_applicability": outcomes,
        "payload_keys": payload_keys,
        "payload_constants": payload_constants or {},
        "producer_transition_id": transition_id,
        "schema_id": f"pulsarmlx.f017.v8.artifact.{artifact_id}/1.0.0",
    }


OUTCOME_CLASSES = [
    "PRE_MINT_FAILURE",
    "AUTHORIZATION_INSTALLATION_FAILURE",
    "COORDINATOR_HANDSHAKE_FAILURE",
    "PACKAGE_PRE_START_FAILURE",
    "PACKAGE_POST_CLAIM_PRE_START_FAILURE",
    "CHECKPOINT_IDENTITY_PRE_START_FAILURE",
    "CHECKPOINT_IDENTITY_FAILURE",
    "DESCRIPTOR_LEASE_ACTIVATION_FAILURE",
    "PRIMARY_PRE_START_FAILURE",
    "PRIMARY_POST_START_FAILURE",
    "SECONDARY_PRE_START_FAILURE",
    "SECONDARY_POST_START_FAILURE",
    "COMPARISON_FAILURE",
    "EVIDENCE_BANKING_FAILURE",
    "COMPLETE_SUCCESS",
]


def failure_class_for_rank(rank: int) -> str:
    """Classify every durable success-prefix rank into one terminal class."""
    if rank == 1:
        return "PRE_MINT_FAILURE"
    if rank <= 6:
        return "AUTHORIZATION_INSTALLATION_FAILURE"
    if rank == 7:
        return "COORDINATOR_HANDSHAKE_FAILURE"
    if rank == 8:
        return "PACKAGE_PRE_START_FAILURE"
    if rank <= 10:
        return "PACKAGE_POST_CLAIM_PRE_START_FAILURE"
    if rank == 11:
        return "CHECKPOINT_IDENTITY_PRE_START_FAILURE"
    if rank <= 23:
        return "CHECKPOINT_IDENTITY_FAILURE"
    if rank <= 28:
        return "DESCRIPTOR_LEASE_ACTIVATION_FAILURE"
    if rank == 29:
        return "PRIMARY_PRE_START_FAILURE"
    if rank <= 34:
        return "PRIMARY_POST_START_FAILURE"
    if rank == 35:
        return "SECONDARY_PRE_START_FAILURE"
    if rank <= 40:
        return "SECONDARY_POST_START_FAILURE"
    if rank <= 42:
        return "COMPARISON_FAILURE"
    return "EVIDENCE_BANKING_FAILURE"

_CHECKPOINT_METADATA = json.loads((ROOT / "docs/validation/glm52-checkpoint.json").read_bytes())
SHARDS = [
    {
        **record,
        "ordinal": ordinal,
        "role": "IDENTITY_ONLY" if ordinal == 1 else "GRAPH_PAYLOAD",
    }
    for ordinal, record in enumerate(_CHECKPOINT_METADATA["files"], start=1)
]


def build_nodes() -> tuple[list[dict], dict[str, int], dict[str, str]]:
    success = [
        ("operator_approval", "OPERATOR", ["operator_approval_id"]),
        ("candidate_authorization", "AUTHORIZER", ["authorization_id", "package_attempt_id"]),
        ("primary_candidate_validation", "PRIMARY_CONSUMER", ["consumer_role", "side_effect_count"]),
        ("secondary_candidate_validation", "SECONDARY_CONSUMER", ["consumer_role", "side_effect_count"]),
        ("installed_authorization", "AUTHORIZER", ["authorization_id", "candidate_digest"]),
        ("installation_receipt", "AUTHORIZER", ["candidate_digest", "installed_digest"]),
        ("coordinator_handshake", "COORDINATOR", ["checkpoint_opens", "checkpoint_reads"]),
        ("package_claim", "COORDINATOR", ["owner_nonce"]),
        ("package_durable_start", "COORDINATOR", ["package_ledger_entry_id"]),
        ("package_ledger_entry", "COORDINATOR", ["delta", "prior_entry_id"]),
        ("checkpoint_identity_durable_start", "CHECKPOINT_IDENTITY_PRODUCER", ["expected_total_bytes", "checkpoint_set_digest"]),
    ]
    for ordinal in range(1, 7):
        success.append((f"checkpoint_access_event_{ordinal}", "CHECKPOINT_IDENTITY_PRODUCER", ["ordinal", "operation", "prior_event_digest"]))
        success.append((f"checkpoint_shard_receipt_{ordinal}", "CHECKPOINT_IDENTITY_PRODUCER", ["ordinal", "role", "expected_size", "observed_size", "expected_checkpoint_digest", "observed_checkpoint_digest", "retain_disposition"]))
    success.extend([
        ("checkpoint_access_journal_terminal", "CHECKPOINT_IDENTITY_PRODUCER", ["event_count", "terminal_event_digest"]),
        ("descriptor_lease_manifest", "CHECKPOINT_IDENTITY_PRODUCER", ["lease_count", "ordinals", "lease_ids", "descriptor_identities"]),
        ("checkpoint_identity_manifest", "CHECKPOINT_IDENTITY_PRODUCER", ["expected_total_bytes", "observed_total_bytes", "ordered_shard_receipt_digests"]),
        ("checkpoint_identity_receipt", "CHECKPOINT_IDENTITY_PRODUCER", ["retained_lease_count", "identity_only_retained_count"]),
        ("checkpoint_identity_terminal", "CHECKPOINT_IDENTITY_PRODUCER", ["mandatory_transition", "retained_lease_count"]),
        ("primary_descriptor_continuity_report", "PRIMARY_CONSUMER", ["consumer_role", "descriptor_count", "ordinals", "lease_ids", "descriptor_identities", "path_reopen_count"]),
        ("primary_durable_start", "PRIMARY_CONSUMER", ["event_id"]),
        ("primary_ledger_entry", "PRIMARY_CONSUMER", ["delta", "event_id"]),
        ("primary_execution_evidence", "PRIMARY_CONSUMER", ["synthetic_only", "layers_completed"]),
        ("primary_receipt", "PRIMARY_CONSUMER", ["event_id", "result"]),
        ("primary_terminal", "PRIMARY_CONSUMER", ["event_id", "result"]),
        ("secondary_descriptor_continuity_report", "SECONDARY_CONSUMER", ["consumer_role", "descriptor_count", "ordinals", "lease_ids", "descriptor_identities", "path_reopen_count"]),
        ("secondary_durable_start", "SECONDARY_CONSUMER", ["event_id"]),
        ("secondary_ledger_entry", "SECONDARY_CONSUMER", ["delta", "event_id"]),
        ("secondary_execution_evidence", "SECONDARY_CONSUMER", ["synthetic_only", "layers_completed"]),
        ("secondary_receipt", "SECONDARY_CONSUMER", ["event_id", "result"]),
        ("secondary_terminal", "SECONDARY_CONSUMER", ["event_id", "result"]),
        ("comparison_receipt", "COMPARATOR", ["classification", "frozen_thresholds"]),
        ("comparison_terminal", "COMPARATOR", ["classification", "result"]),
        ("descriptor_release_start", "COORDINATOR", ["expected_leases"]),
        ("descriptor_release_report", "COORDINATOR", ["attempted_closures", "successful_closures", "duplicate_closures", "unknown_leases", "live_leases_after_release", "lease_ids"]),
        ("descriptor_release_terminal", "COORDINATOR", ["live_leases_after_release", "result"]),
        ("package_receipt", "EVIDENCE_BANKER", ["package_delta", "primary_delta", "secondary_delta"]),
        ("package_terminal", "EVIDENCE_BANKER", ["classification", "mandatory_stop"]),
        ("final_declaration", "EVIDENCE_BANKER", ["active_generation", "event_04_executed", "original_checkpoint_access"]),
    ])
    failure_variants = {
        f"{failure_class_for_rank(rank)}__AFTER_RANK_{rank:03d}": rank
        for rank in range(1, len(success))
    }
    cuts = {**failure_variants, "COMPLETE_SUCCESS": len(success)}
    nodes: list[dict] = []
    previous: str | None = None
    for rank, (artifact_id, actor, payload_keys) in enumerate(success, start=1):
        applicable = [name for name, cut in cuts.items() if cut >= rank]
        dependencies = [previous] if previous else []
        if artifact_id == "candidate_authorization":
            dependencies = ["operator_approval"]
        if artifact_id == "primary_durable_start":
            dependencies.append("primary_descriptor_continuity_report")
        if artifact_id == "secondary_descriptor_continuity_report":
            dependencies.append("primary_terminal")
        if artifact_id == "secondary_durable_start":
            dependencies.append("secondary_descriptor_continuity_report")
        dependencies = list(dict.fromkeys(dependencies))
        constants: dict[str, object] = {}
        if artifact_id == "package_receipt":
            constants = {"package_delta": 1, "primary_delta": 1, "secondary_delta": 1}
        elif artifact_id == "package_terminal":
            constants = {"classification": "COMPLETE_SUCCESS", "mandatory_stop": True}
        elif artifact_id == "final_declaration":
            constants = {"active_generation": "NONE", "event_04_executed": False, "original_checkpoint_access": 0}
        nodes.append(node(artifact_id, rank, f"T{rank:03d}", dependencies, applicable, payload_keys, actor, constants))
        previous = artifact_id
    success_ids = [item["artifact_id"] for item in nodes]
    rank = len(nodes) + 1
    for outcome in failure_variants:
        prefix = success_ids[cuts[outcome] - 1]
        failure_class = outcome.split("__AFTER_RANK_", 1)[0]
        retained_ordinals = [ordinal for ordinal, receipt_rank in zip(range(2, 7), (15, 17, 19, 21, 23)) if receipt_rank <= cuts[outcome]]
        if cuts[outcome] >= 44:
            retained_ordinals = []
        failure_id = f"failure_evidence__{outcome.lower()}"
        prefix_transition = next(item["producer_transition_id"] for item in nodes if item["artifact_id"] == prefix)
        nodes.append(node(failure_id, rank, f"F_{outcome}_EVIDENCE", [prefix], [outcome], ["failed_transition_id", "last_completed_transition_id", "durable_prefix_id", "failure_class"], "EVIDENCE_BANKER", {"failed_transition_id": f"FAIL_{outcome}", "last_completed_transition_id": prefix_transition, "failure_class": failure_class, "durable_prefix_id": prefix})); rank += 1
        tail = failure_id
        release_suffixes: list[tuple[str, list[str]]] = []
        if retained_ordinals and cuts[outcome] < 43:
            release_suffixes.append(("descriptor_release_start", ["expected_leases"]))
        if retained_ordinals and cuts[outcome] < 44:
            release_suffixes.append(("descriptor_release_report", ["attempted_closures", "successful_closures", "duplicate_closures", "unknown_leases", "live_leases_after_release", "lease_ids"]))
        if retained_ordinals and cuts[outcome] < 45:
            release_suffixes.append(("descriptor_release_terminal", ["live_leases_after_release", "result"]))
        for suffix, keys in release_suffixes:
                artifact_id = f"{suffix}__{outcome.lower()}"
                constants: dict[str, object] = {}
                if suffix == "descriptor_release_start":
                    constants["expected_leases"] = len(retained_ordinals)
                elif suffix == "descriptor_release_report":
                    constants.update({"attempted_closures": len(retained_ordinals), "successful_closures": len(retained_ordinals), "duplicate_closures": 0, "unknown_leases": 0, "live_leases_after_release": 0, "lease_ids": [f"LEASE-{ordinal}" for ordinal in retained_ordinals]})
                else:
                    constants.update({"live_leases_after_release": 0, "result": "PASS"})
                nodes.append(node(artifact_id, rank, f"F_{outcome}_{suffix.upper()}", [tail], [outcome], keys, "COORDINATOR", constants)); rank += 1
                tail = artifact_id
        receipt_id = f"package_receipt__{outcome.lower()}"
        terminal_id = f"package_terminal__{outcome.lower()}"
        declaration_id = f"final_declaration__{outcome.lower()}"
        deltas = {"package_delta": int(cuts[outcome] >= 9), "primary_delta": int(cuts[outcome] >= 30), "secondary_delta": int(cuts[outcome] >= 36)}
        nodes.append(node(receipt_id, rank, f"F_{outcome}_PACKAGE_RECEIPT", [tail], [outcome], ["package_delta", "primary_delta", "secondary_delta", "failure_class"], "EVIDENCE_BANKER", {**deltas, "failure_class": failure_class})); rank += 1
        nodes.append(node(terminal_id, rank, f"F_{outcome}_PACKAGE_TERMINAL", [receipt_id], [outcome], ["classification", "mandatory_stop"], "EVIDENCE_BANKER", {"classification": failure_class, "mandatory_stop": True})); rank += 1
        nodes.append(node(declaration_id, rank, f"F_{outcome}_FINAL_DECLARATION", [terminal_id], [outcome], ["active_generation", "event_04_executed", "original_checkpoint_access"], "EVIDENCE_BANKER", {"active_generation": "NONE", "event_04_executed": False, "original_checkpoint_access": 0})); rank += 1
    return nodes, cuts, {name: ("COMPLETE_SUCCESS" if name == "COMPLETE_SUCCESS" else name.split("__AFTER_RANK_", 1)[0]) for name in cuts}


def main() -> None:
    nodes, cuts, outcome_classes = build_nodes()
    node_map = {item["artifact_id"]: item for item in nodes}
    roots = {
        "checkpoint_metadata": authority("docs/validation/glm52-checkpoint.json"),
        "historical_master_ledger": authority("docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v2.json"),
        "numerical_contract": authority("specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v3.json"),
        "numerical_requalification": authority("docs/architecture/reviews/evidence/f017-corrected-oracle-numerical-requalification-v3.json"),
        "v7_budget_closeout": authority("docs/architecture/reviews/evidence/f017-checkpoint-identity-v7-design-review-budget-exhaustion-v1.json"),
    }
    dag = {
        "schema": "pulsarmlx.f017.corrected-oracle-causal-artifact-dag/8.0.0",
        "status": STATUS,
        "edge_semantics": "DEPENDENCY_SHA_MUST_BE_SERIALIZED_AT_STRICTLY_LOWER_CREATION_RANK",
        "nodes": nodes,
        "root_authorities": roots,
        "self_references_permitted": False,
        "future_references_permitted": False,
        "conditional_cycles_permitted": False,
    }
    bank(CONTRACTS / "f017-corrected-oracle-causal-artifact-dag-v8.json", dag)

    identity = {
        "schema": "pulsarmlx.f017.corrected-oracle-checkpoint-identity-contract/8.0.0",
        "status": STATUS,
        "shards": SHARDS,
        "derived_census": {
            "expected_shard_count": len(SHARDS),
            "expected_identity_only_count": sum(item["role"] == "IDENTITY_ONLY" for item in SHARDS),
            "expected_graph_payload_count": sum(item["role"] == "GRAPH_PAYLOAD" for item in SHARDS),
            "expected_total_bytes": sum(item["size_bytes"] for item in SHARDS),
            "expected_retained_lease_count": sum(item["role"] == "GRAPH_PAYLOAD" for item in SHARDS),
        },
        "processing": {"open": "ROOT_DESCRIPTOR_RELATIVE_NOFOLLOW_READ_ONLY", "hash": "COMPLETE_DESCRIPTOR_SHA256", "pre_post_fstat_equal": True, "exact_byte_count": True, "durable_shard_receipt_before_next": True},
        "identity_only_disposition": "CLOSE_AFTER_IDENTITY_VERIFICATION",
        "graph_payload_disposition": "RETAIN_AS_PACKAGE_OWNED_DESCRIPTOR_LEASE",
        "original_checkpoint_access_during_design": 0,
    }
    bank(CONTRACTS / "f017-corrected-oracle-checkpoint-identity-v8.json", identity)

    continuity = {
        "schema": "pulsarmlx.f017.corrected-oracle-descriptor-continuity/8.0.0",
        "status": STATUS,
        "descriptor_transport": "SUBPROCESS_PASS_FDS_EXPLICIT",
        "path_reopen_permitted": False,
        "path_reopen_count": 0,
        "identity_only_descriptor_permitted": False,
        "success_reports": {
            "primary": {"count": 5, "ordinals": [2, 3, 4, 5, 6], "created_before": "primary_durable_start", "self_sha_field_permitted": False},
            "secondary": {"count": 5, "ordinals": [2, 3, 4, 5, 6], "created_after": "primary_terminal", "created_before": "secondary_durable_start", "self_sha_field_permitted": False},
        },
        "descriptor_identity_fields": ["device", "inode", "mode", "size", "mtime_ns", "ctime_ns", "shard_ordinal", "role", "lease_id"],
        "exact_comparison_to_lease_manifest": True,
        "release": {"expected_leases": 5, "duplicate_closures": 0, "unknown_leases": 0, "live_leases_after_success": 0, "package_terminal_after_release": True},
    }
    bank(CONTRACTS / "f017-corrected-oracle-descriptor-continuity-v8.json", continuity)

    envelope_keys = ["schema", "artifact_id", "artifact_kind", "authorization_id", "package_attempt_id", "outcome", "creation_rank", "dependencies", "root_authorities", "payload", "result"]
    schemas = {
        "schema": "pulsarmlx.f017.corrected-oracle-artifact-schema-registry/8.0.0",
        "status": STATUS,
        "strict_key_census": True,
        "unknown_fields": "REJECT",
        "canonical_serialization": "F017_CANONICAL_JSON_BYTES_V1",
        "artifacts": {item["artifact_id"]: {"schema_id": item["schema_id"], "keys": envelope_keys, "payload_keys": item["payload_keys"], "payload_constants": item["payload_constants"], "creation_rank": item["creation_rank"]} for item in nodes},
    }
    bank(CONTRACTS / "f017-corrected-oracle-artifact-schemas-v8.json", schemas)

    obligations = {}
    all_ids = set(node_map)
    for outcome in cuts:
        required = sorted(item["artifact_id"] for item in nodes if outcome in item["outcome_applicability"])
        forbidden = sorted(all_ids - set(required))
        cut = cuts[outcome]
        obligations[outcome] = {
            "durable_prefix_rank": cut,
            "failed_transition_id": None if outcome == "COMPLETE_SUCCESS" else f"FAIL_{outcome}",
            "outcome_class": outcome_classes[outcome],
            "last_completed_artifact_id": [item["artifact_id"] for item in nodes if item["creation_rank"] == cut][0],
            "required": required,
            "forbidden": forbidden,
            "package_delta": int(cut >= 9),
            "primary_delta": int(cut >= 30),
            "secondary_delta": int(cut >= 36),
            "live_leases_at_terminal": 0,
        }
    bank(CONTRACTS / "f017-corrected-oracle-outcome-obligations-v8.json", {"schema": "pulsarmlx.f017.corrected-oracle-outcome-obligations/8.0.0", "status": STATUS, "derivation": "CAUSAL_DAG_OUTCOME_APPLICABILITY", "outcomes": obligations})

    path_timing = {
        "schema": "pulsarmlx.f017.corrected-oracle-path-timing/8.0.0",
        "status": STATUS,
        "production_exception_count": 0,
        "artifact_schema_count": len(nodes),
        "paths": {item["artifact_id"]: {"producer_transition_id": item["producer_transition_id"], "before": "MUST_NOT_EXIST", "after_successful_producer": "MUST_EXIST_REGULAR_FILE", "immutable_after_creation": True, "readback": "DESCRIPTOR_RELATIVE_EXACT_CANONICAL_BYTES_AND_SHA256", "terminal_retention": "RETAIN_AS_APPEND_ONLY_EVIDENCE"} for item in nodes},
    }
    bank(CONTRACTS / "f017-corrected-oracle-path-timing-v8.json", path_timing)

    expected_invariants = [
        ("NO_EVENT04_AUTHORIZATION", "lifecycle_model", "/unconditional_invariants/no_event04_authorization", False),
        ("NO_EVENT04_EXECUTION", "lifecycle_model", "/unconditional_invariants/no_event04_execution", False),
        ("NO_ORIGINAL_CHECKPOINT_ACCESS", "checkpoint_identity", "/original_checkpoint_access_during_design", 0),
        ("HISTORICAL_LEDGER_STABLE", "accounting", "/historical_real_payload_ledger/after", 175),
        ("IDENTITY_AFTER_PACKAGE_START", "interface", "/identity_producer_invoked_after_package_durable_start", True),
        ("PRIMARY_AFTER_IDENTITY_TERMINAL", "lifecycle_model", "/unconditional_invariants/primary_after_identity_terminal", True),
        ("SECONDARY_AFTER_PRIMARY_TERMINAL", "lifecycle_model", "/unconditional_invariants/secondary_after_primary_terminal", True),
        ("UNSTARTED_PRIMARY_DELTA_ZERO", "accounting", "/unstarted_consumer_delta", 0),
        ("UNSTARTED_SECONDARY_DELTA_ZERO", "accounting", "/unstarted_consumer_delta", 0),
        ("IDENTITY_ONLY_NOT_RETAINED", "checkpoint_identity", "/identity_only_disposition", "CLOSE_AFTER_IDENTITY_VERIFICATION"),
        ("GRAPH_LEASE_COUNT", "checkpoint_identity", "/derived_census/expected_retained_lease_count", 5),
        ("PRIMARY_DESCRIPTOR_COUNT", "continuity", "/success_reports/primary/count", 5),
        ("SECONDARY_DESCRIPTOR_COUNT", "continuity", "/success_reports/secondary/count", 5),
        ("PATH_REOPEN_COUNT", "continuity", "/path_reopen_count", 0),
        ("PACKAGE_TERMINAL_AFTER_RELEASE", "continuity", "/release/package_terminal_after_release", True),
        ("NO_LIVE_LEASES_AT_TERMINAL", "continuity", "/release/live_leases_after_success", 0),
        ("NO_SELF_SHA", "artifact_dag", "/self_references_permitted", False),
        ("NO_FUTURE_SHA", "artifact_dag", "/future_references_permitted", False),
        ("NO_ARTIFACT_CYCLES", "artifact_dag", "/conditional_cycles_permitted", False),
        ("NO_P1_TRANSITION", "lifecycle_model", "/unconditional_invariants/no_p1_transition", False),
        ("RETRY_DISABLED", "interface", "/retries", 0),
        ("RESUME_DISABLED", "interface", "/resume", False),
        ("IDENTITY_HASH_EXACT_BYTES", "checkpoint_identity", "/processing/exact_byte_count", True),
        ("IDENTITY_DESCRIPTOR_STABLE", "checkpoint_identity", "/processing/pre_post_fstat_equal", True),
        ("EVIDENCE_APPEND_ONLY", "lifecycle_model", "/unconditional_invariants/evidence_append_only", True),
    ]
    invariants = [{"id": item[0], "scope": "V8_DESIGN_AND_SYNTHETIC", "source_authority": item[1], "source_json_pointer": item[2], "operation": "EXACT_EQUAL", "expected": item[3], "validator_id": f"VALIDATE_{item[0]}", "failure_class": "SAFETY_INVARIANT_FAILURE", "mutation_id": f"MUTATE_{item[0]}"} for item in expected_invariants]
    bank(CONTRACTS / "f017-corrected-oracle-safety-invariants-v8.json", {"schema": "pulsarmlx.f017.corrected-oracle-safety-invariants/8.0.0", "status": STATUS, "invariants": invariants})

    transitions = []
    states = ["DESIGN_ONLY"]
    for item in nodes:
        state = f"ARTIFACT_BANKED__{item['artifact_id'].upper()}"
        states.append(state)
        transitions.append({"id": item["producer_transition_id"], "actor": item["actor"], "artifact_created": item["artifact_id"], "creation_rank": item["creation_rank"], "outcome_applicability": item["outcome_applicability"], "to": state})
    unconditional = {
        "no_event04_authorization": False,
        "no_event04_execution": False,
        "primary_after_identity_terminal": True,
        "secondary_after_primary_terminal": True,
        "no_p1_transition": False,
        "evidence_append_only": True,
    }
    model = {
        "schema": "pulsarmlx.f017.corrected-oracle-lifecycle-semantic-model/8.0.0",
        "status": STATUS,
        "states": sorted(set(states)),
        "transitions": transitions,
        "outcome_classes": OUTCOME_CLASSES,
        "outcomes": list(cuts),
        "success_artifact_order": [item["artifact_id"] for item in nodes if "COMPLETE_SUCCESS" in item["outcome_applicability"]],
        "unconditional_invariants": unconditional,
        "numerical_contract": roots["numerical_contract"],
    }
    bank(CONTRACTS / "f017-corrected-oracle-lifecycle-semantic-model-v8.json", model)

    accounting = {
        "schema": "pulsarmlx.f017.corrected-oracle-event-accounting/8.0.0",
        "status": STATUS,
        "historical_real_payload_ledger": {**roots["historical_master_ledger"], "before": 175, "after": 175, "delta": 0},
        "authorization_mint_delta": 0,
        "package_start_rank": node_map["package_durable_start"]["creation_rank"],
        "primary_start_rank": node_map["primary_durable_start"]["creation_rank"],
        "secondary_start_rank": node_map["secondary_durable_start"]["creation_rank"],
        "unstarted_consumer_delta": 0,
        "outcome_deltas": {name: {key: obligations[name][key] for key in ("package_delta", "primary_delta", "secondary_delta")} for name in cuts},
    }
    bank(CONTRACTS / "f017-corrected-oracle-event-accounting-v8.json", accounting)

    serialization = {"schema": "pulsarmlx.f017.canonical-json-bytes/1.0.0", "status": STATUS, "encoding": "UTF-8", "bom": False, "sort_keys": True, "separators": [",", ":"], "ensure_ascii": True, "allow_nan": False, "trailing_newline_count": 1, "duplicate_keys": "REJECT", "artifact_contains_own_sha256": False}
    bank(CONTRACTS / "f017-corrected-oracle-canonical-serialization-v8.json", serialization)

    interface = {"schema": "pulsarmlx.f017.corrected-oracle-authorization-consumer-interface/8.0.0", "status": STATUS, "active_live_generation": "NONE", "external_checkpoint_identity_path_permitted": False, "identity_producer_invoked_after_package_durable_start": True, "graph_path_reopen_permitted": False, "descriptor_transport": "SUBPROCESS_PASS_FDS_EXPLICIT", "attempts": 1, "retries": 0, "resume": False}
    bank(CONTRACTS / "f017-corrected-oracle-authorization-consumer-interface-v8.json", interface)

    active_generation = {
        "schema": "pulsarmlx.f017.corrected-oracle-active-generation/1.0.0",
        "status": STATUS,
        "active_live_generation": "NONE",
        "frozen_design_generations": ["V8"],
        "historical_live_generations": ["V1", "V2", "V3", "V6"],
        "rejected_design_generations": ["V4", "V5", "V7"],
        "synthetic_qualification_generation": "V6",
    }
    bank(CONTRACTS / "f017-corrected-oracle-active-generation-v1.json", active_generation)

    reproduction = {
        "schema": "pulsarmlx.f017.v7-cycle05-finding-reproduction/1.0.0",
        "branch": "feat/017-rust-native-inference-runtime",
        "reviewed_head": "833d96109f79f51a7627da61d8e854a95e2b15d7",
        "findings": [
            {"id": "IDENTITY_RECEIPT_LEASE_MANIFEST_CREATION_ORDER_UNSATISFIABLE", "affected": "checkpoint_identity_receipt.descriptor_lease_manifest_sha256", "reproduction": "receipt rank preceded lease-manifest producer rank", "repair": "lease manifest rank precedes identity manifest and receipt"},
            {"id": "PRIMARY_CONTINUITY_REPORT_SELF_SHA_UNSATISFIABLE", "affected": "primary_descriptor_continuity_report.primary_continuity_report_sha256", "reproduction": "schema_ref resolved field to same artifact", "repair": "report contains no self SHA; primary durable start binds report"},
            {"id": "SECONDARY_SUCCESS_CONTINUITY_ZERO_DESCRIPTOR_ALLOWED", "affected": "secondary_descriptor_continuity_report.descriptor_identities", "reproduction": "minimum_count zero accepted", "repair": "exact count five and ordinals 2..6"},
            {"id": "TRANSITIVE_SHA_BINDING_CLOSURE_ABSENT", "affected": "global SHA binding closure", "reproduction": "one-level walk omitted package claim and identity start", "repair": "recursive terminal-to-root closure"},
            {"id": "UNSTARTED_CONSUMER_DURABLE_START_NOT_FORBIDDEN", "affected": "pre-start outcome obligations", "reproduction": "delta zero admitted durable-start artifact", "repair": "DAG-derived forbidden complement"},
            {"id": "UNCONDITIONAL_SAFETY_INVARIANTS_UNGATED", "affected": "lifecycle unconditional_invariants", "reproduction": "false values passed V7 validator", "repair": "committed invariant registry with mutation per invariant"},
            {"id": "EVIDENCE_BANKING_CONTINUITY_EVIDENCE_OMITTED", "affected": "EVIDENCE_BANKING_FAILURE.required", "reproduction": "complete execution omitted continuity reports", "repair": "durable-prefix-derived requirements"},
            {"id": "PATH_TIMING_ARTIFACT_COVERAGE_INCOMPLETE", "affected": "path timing", "reproduction": "15 of 30 kinds absent", "repair": "one generated record per DAG artifact"},
            {"id": "TRANSITION_NAME_PATH_TIMING_AMBIGUOUS", "affected": "path producer identity", "reproduction": "shared transition name had multiple sources", "repair": "immutable unique transition IDs"},
            {"id": "LEASE_ARTIFACT_FAILURE_PROHIBITIONS_ABSENT", "affected": "identity failure obligations", "reproduction": "leases admitted before creation", "repair": "forbidden complement of applicability"},
            {"id": "POST_CLAIM_TERMINAL_RELEASE_SHAPE_BYPASS", "affected": "package terminal routes", "reproduction": "terminal bypassed release states", "repair": "release required iff leases exist; zero-lease prefix explicitly typed"},
            {"id": "BYTE_CENSUS_BARE_VALIDATOR_LITERAL", "affected": "identity expected bytes", "reproduction": "literal not derived from shard records", "repair": "independent sum of six records"},
            {"id": "PATH_REOPEN_COUNT_UNCONSTRAINED", "affected": "continuity report", "reproduction": "nonzero count admitted", "repair": "exact zero in contract and invariant"},
            {"id": "INTERFACE_PATH_REOPEN_DECLARATION_UNGATED", "affected": "interface path reopen", "reproduction": "duplicate declaration mutated independently", "repair": "exact interface/continuity equality"},
            {"id": "DESCRIPTOR_IDENTITY_FIELD_RESTATEMENTS_UNCHECKED", "affected": "descriptor fields", "reproduction": "schema restatement drift accepted", "repair": "one exact field registry and equality check"},
            {"id": "IGNORED_PATH_ALLOWLIST_NOT_AUTHORITY", "affected": "validator local allowlist", "reproduction": "local exception widened coverage", "repair": "production exception count zero in authority"},
        ],
        "original_checkpoint_access": 0,
        "event_04_authority_created": False,
    }
    bank(EVIDENCE / "f017-corrected-oracle-v7-cycle05-findings-reproduction-v1.json", reproduction)

    paths = {
        "artifact_dag": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-causal-artifact-dag-v8.json",
        "artifact_schemas": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-artifact-schemas-v8.json",
        "checkpoint_identity": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-checkpoint-identity-v8.json",
        "continuity": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-descriptor-continuity-v8.json",
        "lifecycle_model": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-lifecycle-semantic-model-v8.json",
        "outcomes": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-outcome-obligations-v8.json",
        "path_timing": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-path-timing-v8.json",
        "safety_invariants": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-safety-invariants-v8.json",
        "accounting": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event-accounting-v8.json",
        "serialization": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-canonical-serialization-v8.json",
        "interface": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-authorization-consumer-interface-v8.json",
        "finding_reproduction": "docs/architecture/reviews/evidence/f017-corrected-oracle-v7-cycle05-findings-reproduction-v1.json",
        "mechanical_qualification": "docs/architecture/reviews/evidence/f017-corrected-oracle-lifecycle-v8-mechanical-qualification-v1.json",
        "design_generator": "scripts/research/generate_f017_lifecycle_v8_design.py",
        "symbolic_constructor": "scripts/research/construct_f017_lifecycle_v8_symbolically.py",
        "transitive_closure_validator": "scripts/research/check_f017_transitive_artifact_closure_v8.py",
        "independent_validator": "scripts/research/validate_f017_lifecycle_causal_design_v8.py",
        "design_mutation_suite": "scripts/research/test_f017_lifecycle_causal_design_v8.py",
        "design_qualifier": "scripts/research/qualify_f017_lifecycle_v8_design.py",
        "active_generation": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-active-generation-v1.json",
    }
    manifest = {"schema": "pulsarmlx.f017.corrected-oracle-v8-design-authority-manifest/8.0.0", "status": STATUS, "generation": 8, "active_live_generation": "NONE", "implementation_phase_entered": False, "authorities": {name: authority(path) for name, path in paths.items()}, "root_authorities": roots}
    bank(CONTRACTS / "f017-corrected-oracle-v8-design-authority-manifest.json", manifest)
    print(json.dumps({"result": "PASS", "artifact_count": len(nodes), "outcome_count": len(cuts)}, sort_keys=True))


if __name__ == "__main__":
    main()
