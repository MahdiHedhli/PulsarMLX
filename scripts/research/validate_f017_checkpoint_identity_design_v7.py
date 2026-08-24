#!/usr/bin/env python3
"""Independent structural validation for the F017 V7 identity design."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"


def load(name: str) -> dict:
    path = CONTRACTS / name
    raw = path.read_bytes()
    value = json.loads(raw)
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode() + b"\n"
    if raw != canonical:
        raise ValueError(f"noncanonical authority: {name}")
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate() -> dict:
    identity = load("f017-corrected-oracle-checkpoint-identity-v7.json")
    continuity = load("f017-corrected-oracle-descriptor-continuity-v7.json")
    schemas = load("f017-corrected-oracle-checkpoint-identity-artifact-schemas-v7.json")
    lifecycle_schemas = load("f017-corrected-oracle-lifecycle-artifact-schemas-v7.json")
    model = load("f017-corrected-oracle-lifecycle-semantic-model-v7.json")
    accounting = load("f017-corrected-oracle-event-accounting-v7.json")
    interface = load("f017-corrected-oracle-authorization-consumer-interface-v7.json")
    outcomes = load("f017-corrected-oracle-outcome-obligations-v7.json")
    path_timing = load("f017-corrected-oracle-path-timing-v7.json")
    active = load("f017-corrected-oracle-active-generation-v1.json")
    manifest = load("f017-corrected-oracle-v7-authority-manifest.json")
    expected_order = ["COORDINATOR_HANDSHAKE_PASS", "PACKAGE_CLAIMED", "PACKAGE_DURABLE_STARTED", "CHECKPOINT_IDENTITY_DURABLE_STARTED", "CHECKPOINT_IDENTITY_PARTIAL", "CHECKPOINT_IDENTITY_TERMINAL_SUCCESS", "DESCRIPTOR_LEASES_ACTIVE", "PRIMARY_DURABLE_STARTED"]
    if identity["ordering"] != expected_order or identity["shard_order"] != [1, 2, 3, 4, 5, 6]:
        raise ValueError("identity ordering")
    if identity["expected"] != {"graph_payload_descriptor_leases": 5, "identity_hash_bytes": 238458632928, "identity_hashes": 6, "identity_only_descriptors_retained": 0, "shard_opens": 6}:
        raise ValueError("identity census")
    if continuity["consumer_boundary"]["path_reopen_permitted"] is not False or continuity["consumer_boundary"]["graph_ordinals"] != [2, 3, 4, 5, 6]:
        raise ValueError("descriptor continuity")
    if interface["consumer_requirements"]["external_checkpoint_identity_path_permitted"] is not False:
        raise ValueError("external identity injection")
    states = model["states"]
    for required in ("PACKAGE_DURABLE_STARTED", "CHECKPOINT_IDENTITY_DURABLE_STARTED", "CHECKPOINT_IDENTITY_TERMINAL_SUCCESS", "PRIMARY_DURABLE_STARTED", "DESCRIPTOR_LEASES_RELEASED_SUCCESS_PATH", "DESCRIPTOR_LEASES_RELEASED_FAILURE_PATH"):
        if required not in states:
            raise ValueError(f"missing lifecycle state: {required}")
    if accounting["authorization_mint_delta"] != 0 or accounting["checkpoint_identity_stage"] != {"delta": 0, "ledger_entry_reference": "EXISTING_PACKAGE_LEDGER_ENTRY_ID", "new_ledger_entry_permitted": False} or accounting["historical_real_payload_ledger"]["delta"] != 0:
        raise ValueError("accounting")
    ledger_binding = accounting["historical_real_payload_ledger"]
    ledger_path = ROOT / ledger_binding["path"]
    ledger = json.loads(ledger_path.read_bytes())
    if sha(ledger_path) != ledger_binding["sha256"] or ledger["receipt_chain"]["terminal_count"] != 175 or ledger_binding["before"] != 175 or ledger_binding["after"] != 175:
        raise ValueError("historical ledger authority")
    if set(outcomes["outcomes"]) != set(model["outcomes"]):
        raise ValueError("outcome coverage")
    required_outcomes = {"PRE_MINT_FAILURE", "AUTHORIZATION_INSTALLATION_FAILURE", "COORDINATOR_HANDSHAKE_FAILURE", "PACKAGE_PRE_START_FAILURE", "PACKAGE_POST_CLAIM_PRE_START_FAILURE", "CHECKPOINT_IDENTITY_PRE_START_FAILURE", "CHECKPOINT_IDENTITY_FAILURE", "DESCRIPTOR_LEASE_ACTIVATION_FAILURE", "PRIMARY_PRE_START_FAILURE", "PRIMARY_POST_START_FAILURE", "SECONDARY_PRE_START_FAILURE", "SECONDARY_POST_START_FAILURE", "COMPARISON_FAILURE", "EVIDENCE_BANKING_FAILURE", "COMPLETE_SUCCESS"}
    if set(model["outcomes"]) != required_outcomes:
        raise ValueError("exact outcome census")
    for name, obligation in outcomes["outcomes"].items():
        if set(obligation) != {"forbidden", "live_descriptor_count_at_terminal", "package_delta", "primary_delta", "required", "secondary_delta"}:
            raise ValueError(f"outcome census: {name}")
        if obligation["live_descriptor_count_at_terminal"] != 0:
            raise ValueError(f"descriptor terminal census: {name}")
        if obligation["package_delta"] == 1 and "package_durable_start" not in obligation["required"]:
            raise ValueError(f"package start obligation: {name}")
        if name in {"PRIMARY_PRE_START_FAILURE", "PRIMARY_POST_START_FAILURE", "SECONDARY_PRE_START_FAILURE", "SECONDARY_POST_START_FAILURE", "COMPARISON_FAILURE", "COMPLETE_SUCCESS", "EVIDENCE_BANKING_FAILURE"}:
            if "checkpoint_descriptor_lease_manifest" not in obligation["required"] or "checkpoint_descriptor_lease_terminal" not in obligation["required"]:
                raise ValueError(f"lease evidence obligation: {name}")
        if name == "CHECKPOINT_IDENTITY_FAILURE" and not {"checkpoint_identity_failure_receipt", "checkpoint_descriptor_cleanup_terminal"}.issubset(obligation["required"]):
            raise ValueError("identity failure cleanup evidence")
        if name == "DESCRIPTOR_LEASE_ACTIVATION_FAILURE" and "checkpoint_descriptor_cleanup_terminal" not in obligation["required"]:
            raise ValueError("activation failure cleanup evidence")
        if obligation["primary_delta"] == 1 and not {"primary_receipt", "primary_terminal"}.issubset(obligation["required"]):
            raise ValueError(f"primary back-reference closure: {name}")
        if obligation["secondary_delta"] == 1 and not {"secondary_receipt", "secondary_terminal"}.issubset(obligation["required"]):
            raise ValueError(f"secondary back-reference closure: {name}")
        if obligation["primary_delta"] == 1 and not {"primary_durable_start", "primary_ledger_entry"}.issubset(obligation["required"]):
            raise ValueError(f"primary accounting evidence: {name}")
        if obligation["secondary_delta"] == 1 and not {"secondary_durable_start", "secondary_ledger_entry"}.issubset(obligation["required"]):
            raise ValueError(f"secondary accounting evidence: {name}")
    transition_keys = {"actor", "from", "name", "to"}
    actors = set(model["actors"])
    reached = {"DESIGN_ONLY"}
    for transition in model["transitions"]:
        if set(transition) not in (transition_keys, transition_keys | {"failure_outcome"}):
            raise ValueError("transition census")
        if transition["actor"] not in actors or transition["from"] not in states or transition["to"] not in states:
            raise ValueError("transition authority")
        if "failure_outcome" in transition and transition["failure_outcome"] not in model["outcomes"]:
            raise ValueError("transition outcome")
        reached.add(transition["from"]); reached.add(transition["to"])
    if set(states) != reached:
        raise ValueError("isolated lifecycle state")
    edges: dict[str, list[str]] = {}
    for transition in model["transitions"]:
        edges.setdefault(transition["from"], []).append(transition["to"])
    for transition in model["transitions"]:
        if "failure_outcome" not in transition:
            continue
        pending = [transition["to"]]; visited: set[str] = set()
        while pending:
            node = pending.pop()
            if node in visited: continue
            visited.add(node); pending.extend(edges.get(node, ()))
        if "PACKAGE_TERMINAL_SUCCESS" in visited or (transition["failure_outcome"] not in {"PRE_MINT_FAILURE", "AUTHORIZATION_INSTALLATION_FAILURE", "COORDINATOR_HANDSHAKE_FAILURE", "PACKAGE_PRE_START_FAILURE"} and "PACKAGE_TERMINAL_FAILURE" not in visited):
            raise ValueError(f"failure terminal routing: {transition['failure_outcome']}")
    if not any(item.get("failure_outcome") == "PRIMARY_PRE_START_FAILURE" and item["from"] == "DESCRIPTOR_LEASES_ACTIVE" for item in model["transitions"]):
        raise ValueError("primary pre-start failure route")
    for state in ("CHECKPOINT_IDENTITY_DURABLE_STARTED", "CHECKPOINT_IDENTITY_PARTIAL"):
        if not any(item.get("failure_outcome") == "CHECKPOINT_IDENTITY_FAILURE" and item["from"] == state for item in model["transitions"]):
            raise ValueError(f"identity failure route: {state}")
    pre_mint_states = {"OPERATOR_APPROVED", "PREFLIGHT_PASS", "CANDIDATE_RENDERED", "PRIMARY_CANDIDATE_VALIDATED"}
    if {item["from"] for item in model["transitions"] if item.get("failure_outcome") == "PRE_MINT_FAILURE"} != pre_mint_states:
        raise ValueError("pre-mint failure boundary coverage")
    if not any(item.get("failure_outcome") == "PACKAGE_POST_CLAIM_PRE_START_FAILURE" and item["from"] == "PACKAGE_CLAIMED" for item in model["transitions"]):
        raise ValueError("post-claim pre-start failure route")
    if not any(item.get("failure_outcome") == "DESCRIPTOR_LEASE_ACTIVATION_FAILURE" and item["from"] == "CHECKPOINT_IDENTITY_TERMINAL_SUCCESS" for item in model["transitions"]):
        raise ValueError("lease activation failure route")
    if not any(item.get("failure_outcome") == "COORDINATOR_HANDSHAKE_FAILURE" and item["from"] == "INSTALLATION_RECEIPT_BANKED" for item in model["transitions"]):
        raise ValueError("coordinator handshake failure route")
    if not any(item.get("failure_outcome") == "CHECKPOINT_IDENTITY_PRE_START_FAILURE" and item["from"] == "PACKAGE_DURABLE_STARTED" for item in model["transitions"]):
        raise ValueError("identity pre-start failure route")
    if model["package_terminal_semantics"] != {"PACKAGE_TERMINAL_FAILURE": "PACKAGE_EVIDENCE_COMPLETE_WITH_DECLARED_FAILURE_OUTCOME", "PACKAGE_TERMINAL_SUCCESS": "PACKAGE_EVIDENCE_COMPLETE_AND_ORACLE_COMPLETE_SUCCESS", "terminal_state_must_match_declared_outcome": True}:
        raise ValueError("package terminal semantics")
    iteration = model.get("identity_hash_iteration")
    if iteration != {"exact_iterations": 6, "first_transition": "HASH_FIRST_ORDERED_SHARD", "next_transition": "HASH_NEXT_ORDERED_SHARD", "success_transition": "TERMINALIZE_CHECKPOINT_IDENTITY_SUCCESS", "success_guard": {"completed_shard_count": 6, "ordered_ordinals": [1, 2, 3, 4, 5, 6]}}:
        raise ValueError("identity hash iteration")
    named_transitions = {item["name"] for item in model["transitions"]}
    for descriptor in path_timing["paths"].values():
        created = descriptor.get("created_by")
        creators = created if type(created) is list else [created]
        if any(item and item not in named_transitions for item in creators):
            raise ValueError(f"path transition: {created}")
    required_artifacts = {
        "checkpoint_descriptor_cleanup_terminal",
        "checkpoint_descriptor_continuity_report", "checkpoint_descriptor_lease_manifest",
        "checkpoint_descriptor_lease_terminal", "checkpoint_identity_access_event", "checkpoint_identity_access_journal_terminal",
        "checkpoint_identity_durable_start", "checkpoint_identity_manifest",
        "checkpoint_identity_failure_receipt", "checkpoint_identity_receipt", "checkpoint_identity_shard_receipt",
        "checkpoint_identity_terminal",
    }
    if set(schemas["artifacts"]) != required_artifacts or schemas["strict_key_census"] is not True:
        raise ValueError("artifact schema coverage")
    if "nested" not in schemas["artifacts"]["checkpoint_descriptor_lease_manifest"] or "nested" not in schemas["artifacts"]["checkpoint_identity_shard_receipt"]:
        raise ValueError("nested artifact census")
    if continuity["secondary"].get("post_primary_recheck_artifact") != "secondary_descriptor_continuity_report" or continuity["secondary"].get("primary_report_back_reference_required") is not True:
        raise ValueError("post-primary continuity evidence")
    artifact_namespace = set(schemas["artifacts"]) | set(lifecycle_schemas["artifacts"])
    ignored_path_artifacts = {"checkpoint_identity_access_journal", "checkpoint_identity_state_root", "candidate", "package_state_root", "primary_state_root", "secondary_state_root"}
    if not set(path_timing["paths"]).issubset(artifact_namespace | ignored_path_artifacts):
        raise ValueError("path timing artifact namespace")
    for outcome_name, obligation in outcomes["outcomes"].items():
        required_set = set(obligation["required"])
        for artifact_name in obligation["required"] + obligation["forbidden"]:
            if artifact_name not in artifact_namespace and artifact_name not in ignored_path_artifacts:
                raise ValueError(f"undefined obligation artifact: {outcome_name}:{artifact_name}")
        for artifact_name in required_set:
            descriptor = schemas["artifacts"].get(artifact_name) or lifecycle_schemas["artifacts"].get(artifact_name) or {}
            for field_name, alternatives in descriptor.get("back_references", {}).items():
                if field_name.startswith("primary_") and obligation["primary_delta"] == 0:
                    continue
                if field_name.startswith("secondary_") and obligation["secondary_delta"] == 0:
                    continue
                if not required_set.intersection(alternatives):
                    raise ValueError(f"artifact back-reference closure: {outcome_name}:{artifact_name}")
    if active.get("active_live_generation") != "NONE" or active.get("frozen_design_generations") != ["V7"]:
        raise ValueError("active generation design state")
    if continuity["package_ownership"]["owner"] != "COORDINATOR" or continuity["package_ownership"]["owner"] not in actors:
        raise ValueError("lease owner actor")
    activation = [item for item in model["transitions"] if item["name"] == "ACTIVATE_GRAPH_DESCRIPTOR_LEASES"]
    if len(activation) != 1 or activation[0]["actor"] != "COORDINATOR":
        raise ValueError("lease activation actor")
    release = [item for item in model["transitions"] if item["name"] == "RELEASE_DESCRIPTOR_LEASES"]
    if not release or any(item["actor"] != "COORDINATOR" for item in release):
        raise ValueError("lease release actor")
    required_checks = {"FSTAT_MATCHES_IDENTITY_MANIFEST", "LEASE_ID_MATCH", "PACKAGE_ATTEMPT_MATCH", "READ_ONLY_ACCESS_MODE", "NO_DUPLICATE_FILE_IDENTITY", "NO_UNDECLARED_DESCRIPTOR"}
    boundary = continuity["consumer_boundary"]
    if boundary["descriptor_transport"] != "SUBPROCESS_PASS_FDS_EXPLICIT" or boundary["durable_identity_uses_raw_fd_number"] is not False or boundary["identity_only_descriptor_permitted"] is not False or set(boundary["required_checks"]) != required_checks:
        raise ValueError("descriptor transport security surface")
    if continuity["failure"]["close_all_live_descriptors"] is not True or continuity["terminal"] != {"duplicate_closures": 0, "expected_closures": 5, "live_leases_after_close": 0, "unknown_leases": 0}:
        raise ValueError("descriptor terminal security surface")
    historical_binding = identity["historical_master_ledger"]
    if identity["identity_only"]["graph_access_permitted"] is not False or identity["hash"]["complete_file_required"] is not True or identity["hash"]["descriptor_pre_post_stability_required"] is not True or identity["hash"]["exact_byte_count_required"] is not True or {key: historical_binding[key] for key in ("after", "before", "delta")} != {"after": 175, "before": 175, "delta": 0}:
        raise ValueError("checkpoint identity security surface")
    if accounting["unstarted_consumer_delta"] != 0:
        raise ValueError("unstarted consumer accounting")
    if lifecycle_schemas.get("strict_key_census") is not True or lifecycle_schemas.get("unknown_fields") != "REJECT":
        raise ValueError("lifecycle artifact schema posture")
    for registry in (schemas, lifecycle_schemas):
        global_bindings = registry.get("sha256_field_bindings", {})
        for artifact_name, descriptor in registry["artifacts"].items():
            local_bindings = descriptor.get("back_references", {})
            for key in descriptor.get("keys", ()):
                if key.endswith("_sha256") and key not in local_bindings and key not in global_bindings:
                    raise ValueError(f"unbound sha256 field: {artifact_name}:{key}")
    lease_count = schemas["artifacts"]["checkpoint_descriptor_lease_manifest"]["nested"]["leases"]["count"]
    ordered_count = schemas["artifacts"]["checkpoint_identity_manifest"]["nested"]["ordered_shards"]["count"]
    receipt_count = schemas["artifacts"]["checkpoint_identity_manifest"]["nested"]["shard_receipt_sha256s"]["count"]
    if lease_count != identity["expected"]["graph_payload_descriptor_leases"] or ordered_count != identity["expected"]["identity_hashes"] or receipt_count != identity["expected"]["identity_hashes"]:
        raise ValueError("nested count authority binding")
    continuity_count = schemas["artifacts"]["checkpoint_descriptor_continuity_report"]["nested"]["descriptor_identities"]["count"]
    if continuity_count != identity["expected"]["graph_payload_descriptor_leases"]:
        raise ValueError("continuity descriptor count")
    if "secondary_descriptor_continuity_failure" not in outcomes["outcomes"]["SECONDARY_PRE_START_FAILURE"]["required"]:
        raise ValueError("secondary continuity failure evidence")
    secondary_failure_schema = lifecycle_schemas["artifacts"]["secondary_descriptor_continuity_failure"]
    if secondary_failure_schema.get("conditional_nullability", {}).get("failed_check") != "NULL_IFF_FAILURE_DOMAIN_IS_NOT_CONTINUITY" or secondary_failure_schema.get("nested", {}).get("descriptor_identities", {}).get("maximum_count") != 5:
        raise ValueError("secondary continuity failure schema")
    for name, binding in manifest["authorities"].items():
        path = ROOT / binding["path"]
        if not path.is_file() or sha(path) != binding["sha256"]:
            raise ValueError(f"manifest binding: {name}")
    if set(manifest["authorities"]) != {"accounting", "active_generation", "artifact_schemas", "checkpoint_identity", "descriptor_continuity", "historical_master_ledger", "interface", "lifecycle_artifact_schemas", "lifecycle_model", "numerical_contract", "outcome_obligations", "path_timing", "v6_defect_reproduction", "v6_live_revocation"}:
        raise ValueError("manifest authority census")
    if manifest.get("status") != "DESIGN_FROZEN_NOT_LIVE" or manifest.get("implementation_phase_entered") is not False:
        raise ValueError("design freeze posture")
    for document in (identity, continuity, schemas, model, accounting, interface, outcomes, path_timing, lifecycle_schemas, active):
        if document.get("status") != "DESIGN_FROZEN_NOT_LIVE":
            raise ValueError("contract freeze posture")
    if model["numerical_contract"] != manifest["authorities"]["numerical_contract"]:
        raise ValueError("numerical contract double binding")
    return {"result": "PASS", "generation": 7, "expected_identity_hash_bytes": 238458632928, "outcome_count": len(outcomes["outcomes"]), "transition_count": len(model["transitions"]), "original_checkpoint_access": 0}


if __name__ == "__main__":
    print(json.dumps(validate(), sort_keys=True, separators=(",", ":")))
