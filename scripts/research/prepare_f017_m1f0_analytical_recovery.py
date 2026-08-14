#!/usr/bin/env python3
"""Build the immutable one-shot M1-F0 analytical-recovery config."""

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
    "execution_config": "docs/architecture/reviews/evidence/f017-m1-f0-attempt-2-execution-config-v1.json",
    "authorization": "docs/architecture/reviews/evidence/f017-m1-f0-attempt-2-authorization-v1.json",
    "attempt_ledger": "docs/architecture/reviews/evidence/f017-m1-f0-attempt-ledger.json",
    "router_margin_blocker": "docs/architecture/reviews/evidence/f017-post-m1f0-router-margin-blocker-v1.json",
    "post_m1f0_report": "docs/architecture/reviews/f017-post-m1f0-fix-remediation.md",
    "q5_k_qualification": "docs/architecture/reviews/evidence/f017-m1-f0-q5-k-real-byte-qualification-v1.json",
}
CONTRACTS = {
    "analytical_retention": "specs/017-rust-native-inference-runtime/contracts/f017-analytical-evidence-retention-v1.json",
    "route_stability": "specs/017-rust-native-inference-runtime/contracts/m1f-route-stability-v1.json",
    "recovery_schema": "specs/017-rust-native-inference-runtime/contracts/m1f0-analytical-recovery-v1.schema.json",
    "accepted_decoder": "specs/017-rust-native-inference-runtime/contracts/m1f0-decoder-contract-v1.json",
    "accepted_scaffold": "specs/017-rust-native-inference-runtime/contracts/m1f0-exact-scaffold-v1.json",
    "accepted_selection": "specs/017-rust-native-inference-runtime/contracts/m1f0-selection-v1.json",
    "accepted_numerical": "specs/017-rust-native-inference-runtime/contracts/production-m1f0-tier-b-v1.json",
    "recovery_tool": "scripts/research/recover_f017_m1f0_analytics.py",
}


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binding(root: Path, relative: str) -> dict[str, str]:
    return {"symbolic_path": relative, "path_kind": "repository_relative", "sha256": file_sha256(root / relative)}


def build_config(root: Path, tooling_commit: str) -> dict[str, Any]:
    accepted_config = json.loads((root / ACCEPTED["execution_config"]).read_text())
    evidence = json.loads((root / ACCEPTED["attempt_2_evidence"]).read_text())
    tree = subprocess.check_output(
        ["git", "rev-parse", f"{tooling_commit}^{{tree}}"], cwd=root, text=True
    ).strip()
    oracle = evidence["oracle"]
    stages = oracle["stage_hashes"]
    payload_hashes = {
        item["symbolic_name"]: item["packed_sha256"] for item in evidence["tensor_payloads"]
    }
    decoded_hashes = {
        item["symbolic_name"]: item["decoded_sha256"] for item in evidence["decoded_tensors"]
    }
    expected_names = [item["name"] for item in accepted_config["tensor_allowlist"]]
    if list(payload_hashes) != expected_names or list(decoded_hashes) != expected_names:
        raise ValueError("accepted evidence tensor ordering")
    return {
        "schema": "pulsarmlx.f017.m1f0-analytical-recovery-config",
        "schema_version": "1.0.0",
        "status": "AUTHORIZED_FOR_EXACTLY_ONE_ANALYTICAL_RECOVERY_NOT_EXECUTED",
        "source_identities": {
            "tooling_commit_sha": tooling_commit,
            "tooling_tree_oid": tree,
            "accepted_m1f0_final_head": "df0f3a91244d944f0fe5a0f569b709ccfe631cc0",
            "recovery_preparation_base_head": "fe4d486f39099db3aa80b214e3434d1565cc50d9",
            "python": "3.13.13",
            "numpy": "2.4.5",
            "permitted_post_tooling_paths": [
                "docs/architecture/reviews/evidence/f017-m1-f0-analytical-recovery-authorization-v1.json",
                "docs/architecture/reviews/evidence/f017-m1-f0-analytical-recovery-execution-config-v1.json"
            ],
        },
        "accepted_bindings": {name: binding(root, path) for name, path in ACCEPTED.items()},
        "contracts": {name: binding(root, path) for name, path in CONTRACTS.items()},
        "input_state": accepted_config["input_state"],
        "tensor_allowlist": accepted_config["tensor_allowlist"],
        "access_budget": {
            "shard_opens": 1,
            "positional_reads": 12,
            "tensor_payloads": 12,
            "compressed_bytes": 139_217_920,
            "decoded_bytes": 666_430_464,
            "expert_payloads": 0,
        },
        "expected_identities": {
            "tensor_payload_sha256": payload_hashes,
            "decoded_tensor_sha256": decoded_hashes,
            "router_scores_sha256": oracle["router_scores_sha256"],
            "ranking_sha256": oracle["ranking_sha256"],
            "top8_ids_sha256": oracle["top8_ids_sha256"],
            "routing_weights_sha256": oracle["routing_weights_sha256"],
            "attention_output_sha256": stages["attention_output"],
            "attention_residual_sha256": stages["attention_residual"],
            "router_normalized_input_sha256": stages["router_normalized"],
            "top8_ids": oracle["top8_ids"],
        },
        "scope": {
            "new_route": False,
            "expert_computation": False,
            "shared_expert_computation": False,
            "mlx_candidate_dispatches": 0,
            "m1_f_execution": False,
            "q6_k_qualification": False,
        },
    }


def build_authorization(config: dict[str, Any], config_sha256: str) -> dict[str, Any]:
    return {
        "schema": "pulsarmlx.f017.m1f0-analytical-recovery-authorization",
        "schema_version": "1.0.0",
        "status": "AUTHORIZED FOR EXACTLY ONE ACCEPTED-BOUNDARY EVIDENCE RECOVERY / NOT EXECUTED",
        "execution_config_sha256": config_sha256,
        "tooling_commit_sha": config["source_identities"]["tooling_commit_sha"],
        "tooling_tree_oid": config["source_identities"]["tooling_tree_oid"],
        "accepted_route_sha256": config["accepted_bindings"]["route"]["sha256"],
        "payload_budget": config["access_budget"],
        "route_discovery_attempt_consumed": False,
        "new_route_authorized": False,
        "m1_f_authorized": False,
        "q6_k_qualification_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--tooling-commit", required=True)
    parser.add_argument("--output-config", type=Path, required=True)
    parser.add_argument("--output-authorization", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository_root.resolve(strict=True)
    config = build_config(root, args.tooling_commit)
    config_bytes = canonical_json(config)
    args.output_config.write_bytes(config_bytes)
    config_sha = hashlib.sha256(config_bytes).hexdigest()
    args.output_authorization.write_bytes(canonical_json(build_authorization(config, config_sha)))
    print(config_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
