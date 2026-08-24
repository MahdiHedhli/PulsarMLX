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
    model = load("f017-corrected-oracle-lifecycle-semantic-model-v7.json")
    accounting = load("f017-corrected-oracle-event-accounting-v7.json")
    interface = load("f017-corrected-oracle-authorization-consumer-interface-v7.json")
    manifest = load("f017-corrected-oracle-v7-authority-manifest-draft.json")
    expected_order = ["COORDINATOR_HANDSHAKE_PASS", "PACKAGE_CLAIMED", "PACKAGE_DURABLE_STARTED", "CHECKPOINT_IDENTITY_DURABLE_STARTED", "CHECKPOINT_IDENTITY_PARTIAL", "CHECKPOINT_IDENTITY_COMPLETE", "PRIMARY_DURABLE_STARTED"]
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
    if accounting["authorization_mint_delta"] != 0 or accounting["historical_real_payload_ledger"]["delta"] != 0:
        raise ValueError("accounting")
    for name, binding in manifest["authorities"].items():
        path = ROOT / binding["path"]
        if not path.is_file() or sha(path) != binding["sha256"]:
            raise ValueError(f"manifest binding: {name}")
    return {"result": "PASS", "generation": 7, "expected_identity_hash_bytes": 238458632928, "original_checkpoint_access": 0}


if __name__ == "__main__":
    print(json.dumps(validate(), sort_keys=True, separators=(",", ":")))
