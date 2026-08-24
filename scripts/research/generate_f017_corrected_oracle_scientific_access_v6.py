#!/usr/bin/env python3
"""Generate the pre-authority V6 scientific-access contract."""
from __future__ import annotations

from pathlib import Path

from f017_corrected_oracle_authorization_v6 import ROOT, canonical_bytes, sha256_path, strict_bytes

CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
OUTPUT = CONTRACTS / "f017-corrected-full-checkpoint-oracle-scientific-access-v6.json"
V3 = CONTRACTS / "f017-corrected-full-checkpoint-oracle-scientific-access-v3.json"


def _binding(relative: str) -> dict[str, str]:
    return {"path": relative, "sha256": sha256_path(ROOT / relative)}


def generate() -> dict:
    prior = strict_bytes(V3.read_bytes(), require_canonical=False)
    bindings = {
        "accounting": _binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event-accounting-v6.json"),
        "authorizer": _binding("scripts/research/validate_f017_corrected_oracle_access_v6.py"),
        "coordinator": _binding("scripts/research/execute_f017_corrected_oracle_event_v6.py"),
        "interface": _binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-authorization-consumer-interface-v6.json"),
        "lifecycle_manifest": _binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-lifecycle-v6-authority-manifest.json"),
        "lifecycle_model": _binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-lifecycle-semantic-model-v6.json"),
        "numerical_contract": _binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v3.json"),
        "parser": _binding("scripts/research/f017_corrected_oracle_authorization_v6.py"),
        "path_timing": _binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-path-timing-v6.json"),
        "primary": _binding("scripts/research/f017_corrected_oracle_primary_v6.py"),
        "primary_capability": _binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-primary-capability-v6.json"),
        "secondary": _binding("scripts/research/f017_corrected_oracle_secondary_v6.py"),
        "secondary_capability": _binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-secondary-capability-v6.json"),
        "serialization": _binding("specs/017-rust-native-inference-runtime/contracts/f017-canonical-json-bytes-v6.json"),
    }
    return {
        "schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-scientific-access-contract/6.0.0",
        "authority_generation": 6, "status": "PREPARED_NOT_AUTHORIZED_NOT_EXECUTED",
        "branch": "feat/017-rust-native-inference-runtime", "active_generation_required": "V6",
        "event_class": "F017_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT", "bindings": bindings,
        "context": {"prompt_token": 9703, "position": 0, "kv_state": "EMPTY", "mask": "ONE_VISIBLE_KEY_CAUSAL", "sampling": "NONE_GREEDY_ARGMAX", "top_n": 32},
        "execution": {"attempts": 1, "retries": 0, "resume": False, "consumer_timeout_seconds": None, "secondary_after_primary_prestart_failure": False},
        "accounting": {"authorization_mint_delta": 0, "package_start_delta": 1, "primary_start_delta": 1, "secondary_start_delta": 1, "unstarted_consumer_delta": 0, "historical_master_ledger": 175},
        "frozen_thresholds": {"max_abs": 0.0065169706285814755, "rmse": 0.003463567697419031, "cosine_min": 0.9999999985448085, "top_n": 32},
        "production_checkpoint": {"checkpoint_set_sha256": "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee", "shards": prior["production_checkpoint"]["shards"]},
        "measurement": {"implementation_head_semantics": "EXACT_COMMITTED_IMPLEMENTATION_HEAD_BOUND_BY_SEPARATE_MEASUREMENT_MANIFEST", "evidence_descendant_may_not_change_load_bearing_bytes": True},
        "safety": {"event_04_authorization_created": False, "event_04_executed": False, "original_checkpoint_access": 0, "p1_attempt_2_executed": False},
        "supersedes": {"v3_path": str(V3.relative_to(ROOT)), "v4_design": "REJECTED", "v5_design": "REJECTED", "reason": "LIFECYCLE_SEMANTIC_AUTHORITY_AND_NUMERICAL_CAPABILITY_REBIND"},
    }


if __name__ == "__main__":
    value = generate()
    if len(value["production_checkpoint"]["shards"]) != 6:
        raise ValueError("production checkpoint metadata census")
    OUTPUT.write_bytes(canonical_bytes(value))
    print(sha256_path(OUTPUT))
