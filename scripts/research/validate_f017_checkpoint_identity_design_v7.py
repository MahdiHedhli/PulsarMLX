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
    model = load("f017-corrected-oracle-lifecycle-semantic-model-v7.json")
    accounting = load("f017-corrected-oracle-event-accounting-v7.json")
    interface = load("f017-corrected-oracle-authorization-consumer-interface-v7.json")
    outcomes = load("f017-corrected-oracle-outcome-obligations-v7.json")
    path_timing = load("f017-corrected-oracle-path-timing-v7.json")
    manifest = load("f017-corrected-oracle-v7-authority-manifest-draft.json")
    expected_order = ["COORDINATOR_HANDSHAKE_PASS", "PACKAGE_CLAIMED", "PACKAGE_DURABLE_STARTED", "CHECKPOINT_IDENTITY_DURABLE_STARTED", "CHECKPOINT_IDENTITY_PARTIAL", "CHECKPOINT_IDENTITY_COMPLETE", "DESCRIPTOR_LEASES_ACTIVE", "PRIMARY_DURABLE_STARTED"]
    if identity["ordering"] != expected_order or identity["shard_order"] != [1, 2, 3, 4, 5, 6]:
        raise ValueError("identity ordering")
    if identity["expected"] != {"graph_payload_descriptor_leases": 5, "identity_hash_bytes": 238458632928, "identity_hashes": 6, "identity_only_descriptors_retained": 0, "shard_opens": 6}:
        raise ValueError("identity census")
    if continuity["consumer_boundary"]["path_reopen_permitted"] is not False or continuity["consumer_boundary"]["graph_ordinals"] != [2, 3, 4, 5, 6]:
        raise ValueError("descriptor continuity")
    if interface["consumer_requirements"]["external_checkpoint_identity_path_permitted"] is not False:
        raise ValueError("external identity injection")
    states = model["states"]
    for required in ("PACKAGE_DURABLE_STARTED", "CHECKPOINT_IDENTITY_DURABLE_STARTED", "CHECKPOINT_IDENTITY_COMPLETE", "PRIMARY_DURABLE_STARTED", "DESCRIPTOR_LEASES_RELEASED"):
        if required not in states:
            raise ValueError(f"missing lifecycle state: {required}")
    if accounting["authorization_mint_delta"] != 0 or accounting["checkpoint_identity_stage"] != {"delta": 0, "ledger_entry_reference": "EXISTING_PACKAGE_LEDGER_ENTRY_ID", "new_ledger_entry_permitted": False} or accounting["historical_real_payload_ledger"]["delta"] != 0:
        raise ValueError("accounting")
    if set(outcomes["outcomes"]) != set(model["outcomes"]):
        raise ValueError("outcome coverage")
    for name, obligation in outcomes["outcomes"].items():
        if set(obligation) != {"forbidden", "live_descriptor_count_at_terminal", "package_delta", "primary_delta", "required", "secondary_delta"}:
            raise ValueError(f"outcome census: {name}")
        if obligation["live_descriptor_count_at_terminal"] != 0:
            raise ValueError(f"descriptor terminal census: {name}")
        if obligation["package_delta"] == 1 and "package_durable_start" not in obligation["required"]:
            raise ValueError(f"package start obligation: {name}")
        if name in {"PRIMARY_POST_START_FAILURE", "SECONDARY_PRE_START_FAILURE", "SECONDARY_POST_START_FAILURE", "COMPARISON_FAILURE", "COMPLETE_SUCCESS", "EVIDENCE_BANKING_FAILURE"}:
            if "descriptor_lease_manifest" not in obligation["required"] or "descriptor_lease_terminal" not in obligation["required"]:
                raise ValueError(f"lease evidence obligation: {name}")
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
    named_transitions = {item["name"] for item in model["transitions"]}
    for descriptor in path_timing["paths"].values():
        created = descriptor.get("created_by")
        if created and created not in named_transitions and created != "TERMINALIZE_CHECKPOINT_IDENTITY":
            raise ValueError(f"path transition: {created}")
    required_artifacts = {
        "checkpoint_descriptor_continuity_report", "checkpoint_descriptor_lease_manifest",
        "checkpoint_descriptor_lease_terminal", "checkpoint_identity_access_event",
        "checkpoint_identity_durable_start", "checkpoint_identity_manifest",
        "checkpoint_identity_receipt", "checkpoint_identity_shard_receipt",
        "checkpoint_identity_terminal",
    }
    if set(schemas["artifacts"]) != required_artifacts or schemas["strict_key_census"] is not True:
        raise ValueError("artifact schema coverage")
    if "nested" not in schemas["artifacts"]["checkpoint_descriptor_lease_manifest"] or "nested" not in schemas["artifacts"]["checkpoint_identity_shard_receipt"]:
        raise ValueError("nested artifact census")
    if continuity["secondary"].get("post_primary_recheck_artifact") != "secondary_continuity_report":
        raise ValueError("post-primary continuity evidence")
    for name, binding in manifest["authorities"].items():
        path = ROOT / binding["path"]
        if not path.is_file() or sha(path) != binding["sha256"]:
            raise ValueError(f"manifest binding: {name}")
    if set(manifest["authorities"]) != {"accounting", "artifact_schemas", "checkpoint_identity", "descriptor_continuity", "interface", "lifecycle_model", "numerical_contract", "outcome_obligations", "path_timing"}:
        raise ValueError("manifest authority census")
    return {"result": "PASS", "generation": 7, "expected_identity_hash_bytes": 238458632928, "outcome_count": len(outcomes["outcomes"]), "transition_count": len(model["transitions"]), "original_checkpoint_access": 0}


if __name__ == "__main__":
    print(json.dumps(validate(), sort_keys=True, separators=(",", ":")))
