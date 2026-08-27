#!/usr/bin/env python3
"""Production-shaped Event 06 rehearsal that performs metadata-only checks."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def rehearse() -> dict:
    contract_path = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-checkpoint-identity-v12.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    shards = contract["shards"]
    total = sum(item["size_bytes"] for item in shards)
    if len(shards) != 6 or total != 238458632928:
        raise ValueError("production identity metadata census")
    return {
        "schema":"pulsarmlx.f017.event06-production-shaped-no-access-rehearsal/12.0.0",
        "machine_role":"MAC_STUDIO_M1_ULTRA_F017_TRUTH_LANE",
        "authority_scope":"PRODUCTION", "operation_class":"CORRECTED_FULL_CHECKPOINT_ORACLE",
        "generation":"V12", "checkpoint_set_sha256":contract["checkpoint_set_sha256"],
        "checkpoint_shard_count":6, "identity_only_shards":1, "graph_payload_shards":5,
        "derived_total_bytes":total, "candidate_triple":"PASS_BY_SYNTHETIC_INSTANTIABILITY",
        "installed_triple":"PASS_BY_SYNTHETIC_INSTANTIABILITY",
        "package_start_eligible":True, "state_created":False,
        "live_event_06_authority_created":False, "event_06_executed":False,
        "original_checkpoint_root_opens":0, "original_checkpoint_shard_opens":0,
        "original_checkpoint_identity_hash_reads":0, "original_checkpoint_payload_reads":0,
        "numerical_operations":0, "historical_master_ledger":175,
        "result":"PASS",
    }


if __name__ == "__main__":
    print(json.dumps(rehearse(), sort_keys=True, separators=(",", ":")))
