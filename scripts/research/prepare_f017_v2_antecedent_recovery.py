#!/usr/bin/env python3
"""Build the immutable, unexecuted F017 v2 antecedent-recovery config."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


ACCEPTED = {
    "route": "docs/architecture/reviews/evidence/f017-m1-f0-layer3-route-v1.json",
    "attempt_2_evidence": "docs/architecture/reviews/evidence/f017-m1-f0-real-route-attempt-2-v1.json",
    "accepted_execution_config": "docs/architecture/reviews/evidence/f017-m1-f0-attempt-2-execution-config-v1.json",
    "accepted_analytical_recovery": "docs/architecture/reviews/evidence/f017-m1-f0-router-analytical-recovery-v1.json",
    "real_payload_ledger": "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json",
}
CONTRACTS = {
    "route_stability_v2": "specs/017-rust-native-inference-runtime/contracts/f017-m1f-route-stability-v2.json",
    "retention_manifest": "specs/017-rust-native-inference-runtime/contracts/f017-v2-antecedent-retention-manifest-v1.json",
    "result_schema": "specs/017-rust-native-inference-runtime/contracts/f017-v2-antecedent-recovery-result-v1.schema.json",
    "accepted_decoder": "specs/017-rust-native-inference-runtime/contracts/m1f0-decoder-contract-v1.json",
    "accepted_scaffold": "specs/017-rust-native-inference-runtime/contracts/m1f0-exact-scaffold-v1.json",
    "accepted_selection": "specs/017-rust-native-inference-runtime/contracts/m1f0-selection-v1.json",
    "accepted_numerical": "specs/017-rust-native-inference-runtime/contracts/production-m1f0-tier-b-v1.json",
    "recovery_validator": "scripts/research/f017_v2_antecedent_recovery.py",
    "accepted_oracle_executor": "scripts/research/recover_f017_m1f0_analytics.py",
    "accepted_oracle_preparer": "scripts/research/prepare_f017_m1f0_real_reference.py",
}


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binding(root: Path, relative: str) -> dict[str, str]:
    return {"symbolic_path": relative, "path_kind": "repository_relative", "sha256": file_sha256(root / relative)}


def build_config(root: Path, tooling_commit: str) -> dict[str, Any]:
    accepted_config = json.loads((root / ACCEPTED["accepted_execution_config"]).read_text())
    attempt = json.loads((root / ACCEPTED["attempt_2_evidence"]).read_text())
    route = json.loads((root / ACCEPTED["route"]).read_text())
    analytical = json.loads((root / ACCEPTED["accepted_analytical_recovery"]).read_text())
    ledger = json.loads((root / ACCEPTED["real_payload_ledger"]).read_text())
    tree = subprocess.check_output(["git", "rev-parse", f"{tooling_commit}^{{tree}}"], cwd=root, text=True).strip()
    packed = {item["symbolic_name"]: item["packed_sha256"] for item in attempt["tensor_payloads"]}
    decoded = {item["symbolic_name"]: item["decoded_sha256"] for item in attempt["decoded_tensors"]}
    allowlist = []
    for item in accepted_config["tensor_allowlist"]:
        enriched = dict(item)
        enriched["packed_sha256"] = packed[item["name"]]
        enriched["decoded_sha256"] = decoded[item["name"]]
        allowlist.append(enriched)
    if sum(item["packed_length"] for item in allowlist) != 139217920:
        raise ValueError("packed access total")
    if sum(item["decoded_length"] for item in allowlist) != 666430464:
        raise ValueError("decoded access total")
    reproduced = analytical["reproduced_identities"]
    expected = {
        "input_fixture_sha256": route["input_fixture_sha256"],
        "input_package_sha256": route["input_package_sha256"],
        "hidden_sha256": accepted_config["input_state"]["hidden_sha256"],
        "position_sha256": accepted_config["input_state"]["component_sha256"]["query_position"],
        "mla_cache_sha256": accepted_config["input_state"]["component_sha256"]["mla_cache"],
        "dsa_state_sha256": accepted_config["input_state"]["component_sha256"]["dsa"],
        "mask_sha256": accepted_config["input_state"]["component_sha256"]["mask"],
        "attention_output_sha256": reproduced["attention_output_sha256"],
        "attention_residual_sha256": reproduced["attention_residual_sha256"],
        "router_normalized_input_sha256": reproduced["router_normalized_input_sha256"],
        "router_logits_sha256": attempt["oracle"]["stage_hashes"]["router_logits"],
        "router_probabilities_sha256": analytical["canonical_analytics"]["artifacts"]["router_probabilities"]["sha256"],
        "router_scores_sha256": reproduced["router_scores_sha256"],
        "ranking_sha256": reproduced["ranking_sha256"],
        "top8_ids": reproduced["top8_ids"],
        "top8_ids_sha256": reproduced["top8_ids_sha256"],
        "routing_weights_sha256": reproduced["routing_weights_sha256"],
    }
    if ledger["cumulative_tensor_payloads"] != 45:
        raise ValueError("current ledger is not 45")
    return {
        "schema": "pulsarmlx.f017.v2-antecedent-recovery-config",
        "schema_version": "1.0.0",
        "status": "NOT_AUTHORIZED_NOT_EXECUTED",
        "source_identities": {
            "tooling_commit_sha": tooling_commit,
            "tooling_tree_oid": tree,
            "preparation_base_head": "ab3d991260d9f262430731e762282a7b9cd8995b",
            "authorization_head": None,
            "authorization_issued": False,
            "python": "3.13.13",
            "numpy": "2.4.5",
        },
        "accepted_bindings": {name: binding(root, path) for name, path in ACCEPTED.items()},
        "contracts": {name: binding(root, path) for name, path in CONTRACTS.items()},
        "input_state": accepted_config["input_state"],
        "checkpoint_bindings": accepted_config["checkpoint_bindings"],
        "tensor_allowlist": allowlist,
        "access_budget": {
            "shard_opens": 1,
            "positional_reads": 12,
            "tensor_payloads": 12,
            "compressed_bytes": 139217920,
            "decoded_bytes": 666430464,
            "expert_payloads": 0,
            "expert_computation": 0,
            "mlx_candidate_dispatches": 0,
            "m1_f_execution": 0,
        },
        "expected_identities": expected,
        "retention": {
            "manifest_sha256": file_sha256(root / CONTRACTS["retention_manifest"]),
            "pre_sigmoid_policy": "retain_direct_canonical_little_endian_f64_logits",
            "selected_unselected_pair_count": 1984,
            "adjacent_selected_pair_count": 7,
            "private_package_immutable": True,
        },
        "ledger_transition": {
            "before": 45,
            "successful_recovery_delta": 12,
            "after": 57,
            "increment_during_preparation": False,
        },
        "semantics": {
            "purpose": "analytical_antecedent_recovery_for_retrospective_v2",
            "new_route_discovery": False,
            "route_selection_authority": "accepted_m1f0_attempt_2",
            "route_attempt_consumed": False,
            "accepted_route_reclassification": False,
            "historical_v1_reclassification": False,
            "q6_k_qualification": False,
            "m1_f_execution": False,
        },
        "output_schemas": {
            "public_result": binding(root, CONTRACTS["result_schema"]),
            "private_manifest": binding(root, CONTRACTS["retention_manifest"]),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--tooling-commit", required=True)
    parser.add_argument("--output-config", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository_root.resolve(strict=True)
    raw = canonical_json(build_config(root, args.tooling_commit))
    args.output_config.write_bytes(raw)
    print(hashlib.sha256(raw).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
