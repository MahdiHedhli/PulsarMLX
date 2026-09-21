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
    constants = payload_constants or {}
    integer_keys = {"side_effect_count", "checkpoint_opens", "checkpoint_reads", "delta", "expected_total_bytes", "observed_total_bytes", "ordinal", "expected_size", "observed_size", "event_count", "lease_count", "retained_lease_count", "identity_only_retained_count", "descriptor_count", "path_reopen_count", "layers_completed", "expected_leases", "attempted_closures", "successful_closures", "duplicate_closures", "unknown_leases", "live_leases_after_release", "package_delta", "primary_delta", "secondary_delta", "original_checkpoint_access"}
    boolean_keys = {"synthetic_only", "mandatory_stop", "event_04_executed"}
    array_keys = {"ordinals", "lease_ids", "descriptor_identities", "ordered_shard_receipt_digests", "lease_ordinals", "lease_evidence_artifact_ids"}
    object_keys = {"frozen_thresholds"}
    rules = {}
    for key in payload_keys:
        if key in constants:
            rules[key] = {"kind": "EXACT_CONSTANT", "value": constants[key]}
        elif key in integer_keys:
            rules[key] = {"kind": "TYPE", "type": "INTEGER"}
        elif key in boolean_keys:
            rules[key] = {"kind": "TYPE", "type": "BOOLEAN"}
        elif key in array_keys:
            rules[key] = {"kind": "TYPE", "type": "ARRAY"}
        elif key in object_keys:
            rules[key] = {"kind": "TYPE", "type": "OBJECT"}
        elif "digest" in key:
            rules[key] = {"kind": "SHA256"}
        else:
            rules[key] = {"kind": "TYPE", "type": "STRING"}
    return {
        "actor": actor,
        "artifact_id": artifact_id,
        "artifact_kind": artifact_id,
        "creation_rank": rank,
        "dependencies": dependencies,
        "outcome_applicability": outcomes,
        "payload_keys": payload_keys,
        "payload_constants": constants,
        "producer_transition_id": transition_id,
        "payload_rules": rules,
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
_NUMERICAL_CONTRACT = json.loads((ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v3.json").read_bytes())
_ALL_COMPARISON_CLASSIFICATIONS = list(_NUMERICAL_CONTRACT["future_p1_consequence"])
_SUCCESS_COMPARISON_CLASSIFICATIONS = [name for name in _ALL_COMPARISON_CLASSIFICATIONS if _NUMERICAL_CONTRACT["future_p1_consequence"][name] != "ATTEMPT_2_BLOCKED"]
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
        ("primary_execution_evidence", "PRIMARY_CONSUMER", ["consumer_role", "event_id", "numerical_output_digest", "synthetic_only", "layers_completed"]),
        ("primary_receipt", "PRIMARY_CONSUMER", ["event_id", "result"]),
        ("primary_terminal", "PRIMARY_CONSUMER", ["event_id", "result"]),
        ("secondary_descriptor_continuity_report", "SECONDARY_CONSUMER", ["consumer_role", "descriptor_count", "ordinals", "lease_ids", "descriptor_identities", "path_reopen_count"]),
        ("secondary_durable_start", "SECONDARY_CONSUMER", ["event_id"]),
        ("secondary_ledger_entry", "SECONDARY_CONSUMER", ["delta", "event_id"]),
        ("secondary_execution_evidence", "SECONDARY_CONSUMER", ["consumer_role", "event_id", "numerical_output_digest", "synthetic_only", "layers_completed"]),
        ("secondary_receipt", "SECONDARY_CONSUMER", ["event_id", "result"]),
        ("secondary_terminal", "SECONDARY_CONSUMER", ["event_id", "result"]),
        ("comparison_receipt", "COMPARATOR", ["classification", "primary_output_digest", "secondary_output_digest", "frozen_thresholds"]),
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
        dependencies = list(dict.fromkeys(dependencies))
        constants: dict[str, object] = {}
        if artifact_id in {"primary_candidate_validation", "secondary_candidate_validation"}:
            constants = {"consumer_role": "PRIMARY" if artifact_id.startswith("primary") else "SECONDARY", "side_effect_count": 0}
        elif artifact_id == "coordinator_handshake":
            constants = {"checkpoint_opens": 0, "checkpoint_reads": 0}
        elif artifact_id == "checkpoint_identity_durable_start":
            constants = {"expected_total_bytes": _CHECKPOINT_METADATA["total_bytes"], "checkpoint_set_digest": _CHECKPOINT_METADATA["checkpoint_set_sha256"]}
        elif artifact_id.startswith("checkpoint_access_event_"):
            ordinal = int(artifact_id.rsplit("_", 1)[1])
            constants = {"ordinal": ordinal, "operation": "ROOT_RELATIVE_NOFOLLOW_OPEN_AND_COMPLETE_SHA256"}
        elif artifact_id.startswith("checkpoint_shard_receipt_"):
            ordinal = int(artifact_id.rsplit("_", 1)[1])
            shard = SHARDS[ordinal - 1]
            constants = {"ordinal": ordinal, "role": shard["role"], "expected_size": shard["size_bytes"], "expected_checkpoint_digest": shard["sha256"], "retain_disposition": "CLOSE_AFTER_IDENTITY_VERIFICATION" if ordinal == 1 else "RETAIN_AS_PACKAGE_OWNED_DESCRIPTOR_LEASE"}
        elif artifact_id == "checkpoint_access_journal_terminal":
            constants = {"event_count": 6}
        elif artifact_id == "descriptor_lease_manifest":
            constants = {"lease_count": 5, "ordinals": [2, 3, 4, 5, 6]}
        elif artifact_id == "checkpoint_identity_manifest":
            constants = {"expected_total_bytes": _CHECKPOINT_METADATA["total_bytes"], "observed_total_bytes": _CHECKPOINT_METADATA["total_bytes"]}
        elif artifact_id == "checkpoint_identity_receipt":
            constants = {"retained_lease_count": 5, "identity_only_retained_count": 0}
        elif artifact_id == "checkpoint_identity_terminal":
            constants = {"mandatory_transition": "COMPLETE", "retained_lease_count": 5}
        elif artifact_id in {"package_ledger_entry", "primary_ledger_entry", "secondary_ledger_entry"}:
            constants = {"delta": 1}
        elif artifact_id in {"primary_descriptor_continuity_report", "secondary_descriptor_continuity_report"}:
            constants = {"consumer_role": "PRIMARY" if artifact_id.startswith("primary") else "SECONDARY", "descriptor_count": 5, "ordinals": [2, 3, 4, 5, 6], "path_reopen_count": 0}
        elif artifact_id in {"primary_execution_evidence", "secondary_execution_evidence"}:
            constants = {"consumer_role": "PRIMARY" if artifact_id.startswith("primary") else "SECONDARY", "synthetic_only": True, "layers_completed": 79}
        elif artifact_id in {"primary_receipt", "primary_terminal", "secondary_receipt", "secondary_terminal"}:
            constants = {"result": "COMPLETE"}
        elif artifact_id == "comparison_receipt":
            constants = {"frozen_thresholds": {"max_abs": 0.0065169706285814755, "rmse": 0.003463567697419031, "cosine_min": 0.9999999985448085, "top_n": 32}}
        elif artifact_id == "descriptor_release_start":
            constants = {"expected_leases": 5}
        elif artifact_id == "descriptor_release_report":
            constants = {"attempted_closures": 5, "successful_closures": 5, "duplicate_closures": 0, "unknown_leases": 0, "live_leases_after_release": 0}
        elif artifact_id == "descriptor_release_terminal":
            constants = {"live_leases_after_release": 0, "result": "PASS"}
        elif artifact_id == "comparison_terminal":
            constants = {"result": "COMPLETE"}
        elif artifact_id == "package_receipt":
            constants = {"package_delta": 1, "primary_delta": 1, "secondary_delta": 1}
        elif artifact_id == "package_terminal":
            constants = {"classification": "COMPLETE_SUCCESS", "mandatory_stop": True}
        elif artifact_id == "final_declaration":
            constants = {"active_generation": "NONE", "event_04_executed": False, "original_checkpoint_access": 0}
        built = node(artifact_id, rank, f"T{rank:03d}", dependencies, applicable, payload_keys, actor, constants)
        if artifact_id == "installed_authorization":
            built["payload_rules"]["candidate_digest"] = {"kind": "ARTIFACT_SHA256", "artifact_id": "candidate_authorization"}
        if artifact_id == "installation_receipt":
            built["payload_rules"]["candidate_digest"] = {"kind": "ARTIFACT_SHA256", "artifact_id": "candidate_authorization"}
            built["payload_rules"]["installed_digest"] = {"kind": "ARTIFACT_SHA256", "artifact_id": "installed_authorization"}
        if artifact_id.startswith("checkpoint_access_event_"):
            ordinal = int(artifact_id.rsplit("_", 1)[1])
            prior_id = "checkpoint_identity_durable_start" if ordinal == 1 else f"checkpoint_shard_receipt_{ordinal - 1}"
            built["payload_rules"]["prior_event_digest"] = {"kind": "ARTIFACT_SHA256", "artifact_id": prior_id}
        if artifact_id.startswith("checkpoint_shard_receipt_"):
            built["payload_rules"]["observed_size"] = {"kind": "EQUAL_PAYLOAD_FIELD", "field": "expected_size"}
            built["payload_rules"]["observed_checkpoint_digest"] = {"kind": "EQUAL_PAYLOAD_FIELD", "field": "expected_checkpoint_digest"}
        if artifact_id == "checkpoint_access_journal_terminal":
            built["payload_rules"]["terminal_event_digest"] = {"kind": "ARTIFACT_SHA256", "artifact_id": "checkpoint_shard_receipt_6"}
        if artifact_id == "descriptor_lease_manifest":
            built["payload_rules"]["lease_ids"] = {"kind": "ARRAY_EXACT_LENGTH", "length": 5}
            built["payload_rules"]["descriptor_identities"] = {
                "kind": "DESCRIPTOR_IDENTITY_ARRAY",
                "length": 5,
                "ordinals": [2, 3, 4, 5, 6],
                "sizes": [SHARDS[ordinal - 1]["size_bytes"] for ordinal in range(2, 7)],
            }
        if artifact_id == "checkpoint_identity_manifest":
            built["payload_rules"]["ordered_shard_receipt_digests"] = {"kind": "ARTIFACT_SHA256_SEQUENCE", "artifact_ids": [f"checkpoint_shard_receipt_{ordinal}" for ordinal in range(1, 7)]}
        if artifact_id in {"primary_descriptor_continuity_report", "secondary_descriptor_continuity_report"}:
            built["payload_rules"]["lease_ids"] = {"kind": "EQUAL_ARTIFACT_PAYLOAD_FIELD", "artifact_id": "descriptor_lease_manifest", "field": "lease_ids"}
            built["payload_rules"]["descriptor_identities"] = {"kind": "EQUAL_ARTIFACT_PAYLOAD_FIELD", "artifact_id": "descriptor_lease_manifest", "field": "descriptor_identities"}
        if artifact_id == "descriptor_release_report":
            built["payload_rules"]["lease_ids"] = {"kind": "EQUAL_ARTIFACT_PAYLOAD_FIELD", "artifact_id": "descriptor_lease_manifest", "field": "lease_ids"}
        if artifact_id == "comparison_receipt":
            built["payload_rules"]["classification"] = {"kind": "OUTCOME_CLASSIFICATION_ENUM", "success_values": _SUCCESS_COMPARISON_CLASSIFICATIONS, "failure_values": _ALL_COMPARISON_CLASSIFICATIONS}
            built["payload_rules"]["primary_output_digest"] = {"kind": "EQUAL_ARTIFACT_PAYLOAD_FIELD", "artifact_id": "primary_execution_evidence", "field": "numerical_output_digest"}
            built["payload_rules"]["secondary_output_digest"] = {"kind": "EQUAL_ARTIFACT_PAYLOAD_FIELD", "artifact_id": "secondary_execution_evidence", "field": "numerical_output_digest"}
        if artifact_id == "comparison_terminal":
            built["payload_rules"]["classification"] = {"kind": "EQUAL_ARTIFACT_PAYLOAD_FIELD", "artifact_id": "comparison_receipt", "field": "classification"}
        if artifact_id == "operator_approval":
            built["payload_rules"]["operator_approval_id"] = {"kind": "NONEMPTY_STRING"}
        if artifact_id == "candidate_authorization":
            built["payload_rules"]["authorization_id"] = {"kind": "EQUAL_ENVELOPE_FIELD", "field": "authorization_id"}
            built["payload_rules"]["package_attempt_id"] = {"kind": "EQUAL_ENVELOPE_FIELD", "field": "package_attempt_id"}
        if artifact_id == "installed_authorization":
            built["payload_rules"]["authorization_id"] = {"kind": "EQUAL_ENVELOPE_FIELD", "field": "authorization_id"}
        if artifact_id == "package_claim":
            built["payload_rules"]["owner_nonce"] = {"kind": "NONEMPTY_STRING"}
        if artifact_id == "package_durable_start":
            built["payload_rules"]["package_ledger_entry_id"] = {"kind": "NONEMPTY_STRING"}
        if artifact_id == "package_ledger_entry":
            built["payload_rules"]["prior_entry_id"] = {"kind": "EQUAL_ARTIFACT_PAYLOAD_FIELD", "artifact_id": "package_durable_start", "field": "package_ledger_entry_id"}
        for role in ("primary", "secondary"):
            durable_start = f"{role}_durable_start"
            if artifact_id == durable_start:
                built["payload_rules"]["event_id"] = {"kind": "NONEMPTY_STRING"}
            if artifact_id in {f"{role}_ledger_entry", f"{role}_execution_evidence", f"{role}_receipt", f"{role}_terminal"}:
                built["payload_rules"]["event_id"] = {"kind": "EQUAL_ARTIFACT_PAYLOAD_FIELD", "artifact_id": durable_start, "field": "event_id"}
        nodes.append(built)
        previous = artifact_id
    success_ids = [item["artifact_id"] for item in nodes]
    rank = len(nodes) + 1
    for outcome in failure_variants:
        prefix = success_ids[cuts[outcome] - 1]
        failure_class = outcome.split("__AFTER_RANK_", 1)[0]
        access_ranks = {ordinal: next(item["creation_rank"] for item in nodes if item["artifact_id"] == f"checkpoint_access_event_{ordinal}") for ordinal in range(2, 7)}
        retained_ordinals = [ordinal for ordinal, access_rank in access_ranks.items() if access_rank <= cuts[outcome]]
        if cuts[outcome] >= 44:
            retained_ordinals = []
        failure_id = f"failure_terminal_capsule__{outcome.lower()}"
        prefix_transition = next(item["producer_transition_id"] for item in nodes if item["artifact_id"] == prefix)
        deltas = {"package_delta": int(cuts[outcome] >= 9), "primary_delta": int(cuts[outcome] >= 30), "secondary_delta": int(cuts[outcome] >= 36)}
        keys = ["failed_transition_id", "last_completed_transition_id", "durable_prefix_id", "failure_class", "atomic_terminalization", "package_delta", "primary_delta", "secondary_delta", "expected_leases", "attempted_closures", "successful_closures", "duplicate_closures", "unknown_leases", "live_leases_after_release", "lease_ordinals", "lease_evidence_artifact_ids", "classification", "mandatory_stop", "active_generation", "event_04_executed", "original_checkpoint_access"]
        constants = {"failed_transition_id": f"FAIL_{outcome}", "last_completed_transition_id": prefix_transition, "durable_prefix_id": prefix, "failure_class": failure_class, "atomic_terminalization": "SINGLE_CANONICAL_TEMP_WRITE_FSYNC_EXCLUSIVE_RENAME_DIRECTORY_FSYNC", **deltas, "expected_leases": len(retained_ordinals), "live_leases_after_release": 0, "lease_ordinals": retained_ordinals, "lease_evidence_artifact_ids": [f"checkpoint_access_event_{ordinal}" for ordinal in retained_ordinals], "classification": failure_class, "mandatory_stop": True, "active_generation": "NONE", "event_04_executed": False, "original_checkpoint_access": 0}
        capsule = node(failure_id, rank, f"F_{outcome}_ATOMIC_TERMINALIZATION", [prefix], [outcome], keys, "EVIDENCE_BANKER", constants)
        for observable in ("attempted_closures", "successful_closures", "duplicate_closures", "unknown_leases"):
            capsule["payload_rules"][observable] = {"kind": "NONNEGATIVE_INTEGER"}
        nodes.append(capsule); rank += 1
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

    descriptor_scalars = {
        "schema": "pulsarmlx.f017.corrected-oracle-descriptor-scalar-contract/8.0.0",
        "status": STATUS,
        "controlled_failure_class": "ValueError",
        "descriptor_collection": {"type": "EXACT_LIST", "count": 5},
        "descriptor_entry": {
            "type": "EXACT_DICT",
            "unknown_keys": "REJECT",
            "keys": ["device", "inode", "mode", "size", "mtime_ns", "ctime_ns", "shard_ordinal", "role", "lease_id"],
        },
        "fields": {
            "device": {"type": "EXACT_INT_NOT_BOOL", "minimum": 0},
            "inode": {"type": "EXACT_INT_NOT_BOOL", "minimum": 0},
            "mode": {"type": "EXACT_INT_NOT_BOOL", "minimum": 0, "exclusive_maximum": 65536, "semantic": "POSIX_16_BIT_MODE_T_REGULAR_FILE"},
            "size": {"type": "EXACT_INT_NOT_BOOL", "minimum": 0},
            "mtime_ns": {"type": "EXACT_INT_NOT_BOOL", "minimum": 0},
            "ctime_ns": {"type": "EXACT_INT_NOT_BOOL", "minimum": 0},
            "shard_ordinal": {"type": "EXACT_INT_NOT_BOOL", "values": [2, 3, 4, 5, 6]},
            "role": {"type": "EXACT_STRING", "values": ["GRAPH_PAYLOAD"]},
            "lease_id": {"type": "EXACT_STRING", "grammar": "[A-Z0-9](?:[A-Z0-9-]{0,126}[A-Z0-9])?", "forbidden_markers": ["INERT", "FIXTURE", "TEST", "SYNTHETIC"]},
        },
        "validation_order": [
            "DESCRIPTOR_COLLECTION_TYPE_AND_COUNT",
            "DESCRIPTOR_ENTRY_EXACT_TYPE",
            "DESCRIPTOR_ENTRY_EXACT_KEY_CENSUS",
            "FIELD_EXACT_TYPES",
            "FIELD_RANGES_AND_ENUMERATIONS",
            "LEASE_ID_GRAMMAR",
            "MODE_REGULAR_FILE_SEMANTIC",
            "EXACT_AUTHORITY_EQUALITY",
            "DUPLICATE_DETECTION",
        ],
        "mode_semantic_precondition": "STAT_S_ISREG_CALLED_ONLY_AFTER_EXACT_INT_AND_0_LE_MODE_LT_65536",
        "lease_deduplication_precondition": "SET_CONSTRUCTION_ONLY_AFTER_ALL_LEASE_IDS_ARE_VALID_STRINGS",
        "ordinals": [2, 3, 4, 5, 6],
        "roles": ["GRAPH_PAYLOAD"],
    }
    bank(CONTRACTS / "f017-corrected-oracle-descriptor-scalar-contract-v8.json", descriptor_scalars)

    envelope_keys = ["schema", "artifact_id", "artifact_kind", "authorization_id", "package_attempt_id", "outcome", "creation_rank", "dependencies", "root_authorities", "payload", "result"]
    schemas = {
        "schema": "pulsarmlx.f017.corrected-oracle-artifact-schema-registry/8.0.0",
        "status": STATUS,
        "strict_key_census": True,
        "unknown_fields": "REJECT",
        "canonical_serialization": "F017_CANONICAL_JSON_BYTES_V1",
        "outcome_field_semantics": {"durable_prefix": "PENDING_IMMUTABLE", "terminal_artifact": "EXACT_TERMINAL_OUTCOME"},
        "result_field_semantics": {"ordinary_artifact": "PASS", "failure_terminal_capsule": "FAILURE_EVIDENCE"},
        "artifacts": {item["artifact_id"]: {"schema_id": item["schema_id"], "keys": envelope_keys, "payload_keys": item["payload_keys"], "payload_constants": item["payload_constants"], "payload_rules": item["payload_rules"], "creation_rank": item["creation_rank"]} for item in nodes},
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
        ("UNSTARTED_PRIMARY_DELTA_ZERO", "accounting", "/unstarted_primary_delta", 0),
        ("UNSTARTED_SECONDARY_DELTA_ZERO", "accounting", "/unstarted_secondary_delta", 0),
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
        "unstarted_primary_delta": 0,
        "unstarted_secondary_delta": 0,
        "outcome_deltas": {name: {key: obligations[name][key] for key in ("package_delta", "primary_delta", "secondary_delta")} for name in cuts},
    }
    bank(CONTRACTS / "f017-corrected-oracle-event-accounting-v8.json", accounting)

    serialization = {"schema": "pulsarmlx.f017.canonical-json-bytes/1.0.0", "status": STATUS, "encoding": "UTF-8", "bom": False, "sort_keys": True, "separators": [",", ":"], "ensure_ascii": True, "allow_nan": False, "trailing_newline_count": 1, "duplicate_keys": "REJECT", "artifact_contains_own_sha256": False}
    bank(CONTRACTS / "f017-corrected-oracle-canonical-serialization-v8.json", serialization)

    interface = {"schema": "pulsarmlx.f017.corrected-oracle-authorization-consumer-interface/8.0.0", "status": STATUS, "active_live_generation": "NONE", "external_checkpoint_identity_path_permitted": False, "identity_producer_invoked_after_package_durable_start": True, "graph_path_reopen_permitted": False, "descriptor_transport": "SUBPROCESS_PASS_FDS_EXPLICIT", "lease_inception": "SUCCESSFUL_GRAPH_PAYLOAD_CHECKPOINT_ACCESS_EVENT_OPEN", "failure_terminalization": "SINGLE_CANONICAL_TEMP_WRITE_FSYNC_EXCLUSIVE_RENAME_DIRECTORY_FSYNC", "failure_terminalization_partial_authority": "NONE", "failure_terminalization_failure_recursion_terminator": "NO_NEW_DURABLE_PREFIX_AND_PROCESS_EXIT_DESCRIPTOR_CLOSE", "absent_capsule_after_process_exit": "UNBANKED_TERMINALIZATION_FAILURE_HUMAN_STOP_NO_RETRY", "attempts": 1, "retries": 0, "resume": False}
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
        "descriptor_scalars": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-descriptor-scalar-contract-v8.json",
        "lifecycle_model": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-lifecycle-semantic-model-v8.json",
        "outcomes": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-outcome-obligations-v8.json",
        "path_timing": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-path-timing-v8.json",
        "safety_invariants": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-safety-invariants-v8.json",
        "accounting": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event-accounting-v8.json",
        "serialization": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-canonical-serialization-v8.json",
        "interface": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-authorization-consumer-interface-v8.json",
        "finding_reproduction": "docs/architecture/reviews/evidence/f017-corrected-oracle-v7-cycle05-findings-reproduction-v1.json",
        "cycle07_type_safety_reproduction": "docs/architecture/reviews/evidence/f017-lifecycle-v8-cycle07-required-finding-reproduction-v1.json",
        "descriptor_type_safety_mutation_qualification": "docs/architecture/reviews/evidence/f017-lifecycle-v8-descriptor-type-safety-mutation-qualification-v1.json",
        "mechanical_qualification": "docs/architecture/reviews/evidence/f017-corrected-oracle-lifecycle-v8-mechanical-qualification-v1.json",
        "design_generator": "scripts/research/generate_f017_lifecycle_v8_design.py",
        "symbolic_constructor": "scripts/research/construct_f017_lifecycle_v8_symbolically.py",
        "transitive_closure_validator": "scripts/research/check_f017_transitive_artifact_closure_v8.py",
        "independent_type_safety_validator": "scripts/research/check_f017_descriptor_type_safety_v8.py",
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
