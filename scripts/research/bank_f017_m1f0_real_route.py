#!/usr/bin/env python3
"""Validate and bank one accepted real M1-F0 oracle-only route."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path
from typing import Any


HISTORICAL_ROUTE = [15, 177, 233, 41, 166, 26, 10, 152]
SYNTHETIC_ROUTE = [188, 57, 158, 117, 87, 16, 218, 46]


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise ValueError(f"duplicate key: {key}")
        value[key] = child
    return value


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates)


def load_admission(root: Path):
    path = root / "scripts/research/f017_m1f0_admission.py"
    spec = importlib.util.spec_from_file_location("f017_m1f0_admission_banker", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_atomic(path: Path, value: object, *, exclusive: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive and path.exists():
        raise ValueError(f"refusing to overwrite {path.name}")
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary.write(canonical_json(value))
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, path)
    path.chmod(0o444)


def _repeat_key(record: dict[str, Any]) -> bytes:
    return canonical_json({key: value for key, value in record.items() if key != "ordinal"})


def bank(
    root: Path,
    config_path: Path,
    config_sha: str,
    authorization_path: Path,
    authorization_sha: str,
    oracle_path: Path,
    route_path: Path,
    evidence_path: Path,
    ledger_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    admission = load_admission(root)
    config_raw = config_path.read_bytes()
    authorization_raw = authorization_path.read_bytes()
    oracle_raw = oracle_path.read_bytes()
    if sha256(config_raw) != config_sha or sha256(authorization_raw) != authorization_sha:
        raise ValueError("config/authorization identity")
    config = json.loads(config_raw, object_pairs_hook=reject_duplicates)
    authorization = json.loads(authorization_raw, object_pairs_hook=reject_duplicates)
    admission.validate_config(root, config)
    admission.validate_authorization(
        root, config, config_sha, authorization_path, authorization_sha
    )
    oracle = json.loads(oracle_raw, object_pairs_hook=reject_duplicates)
    if (
        oracle.get("schema") != "pulsarmlx.f017.m1f0-oracle-package"
        or oracle.get("attempt") != 1
        or oracle.get("attempt_state") != "COMPLETED"
        or oracle.get("execution_config_sha256") != config_sha
        or oracle.get("authorization_sha256") != authorization_sha
        or oracle.get("expert_computation") is not False
    ):
        raise ValueError("oracle package identity")
    allowlist = config["tensor_allowlist"]
    names = [binding["name"] for binding in allowlist]
    if set(oracle["tensor_payload_sha256"]) != set(names) or set(oracle["decoded_tensor_sha256"]) != set(names):
        raise ValueError("oracle tensor inventory")
    repeat = oracle["repeat_integrity"]
    records = repeat.get("records", [])
    if (
        repeat.get("required") != 10
        or repeat.get("observed") != 10
        or repeat.get("all_equal") is not True
        or [record.get("ordinal") for record in records] != list(range(10))
        or not records
        or any(_repeat_key(record) != _repeat_key(records[0]) for record in records[1:])
    ):
        raise ValueError("oracle repeat integrity")
    selected = oracle["oracle"]["top8_ids"]
    if selected in (HISTORICAL_ROUTE, SYNTHETIC_ROUTE) or len(selected) != 8 or len(set(selected)) != 8:
        raise ValueError("forbidden or malformed real route")
    if oracle["numerical_qualification"] != {
        "attention_router_contract": "PASS",
        "selection_exact": True,
        "signed_zero_policy": "PASS",
        "non_finite_count": 0,
        "repeat_max_abs": 0.0,
        "repeat_rmse": 0.0,
        "repeat_cosine": 1.0,
        "classification": "independent_oracle_route_exact_and_deterministic",
        "post_observation_retuning": False,
    }:
        raise ValueError("oracle numerical qualification")
    expected_access = {
        "shard_opens": 1,
        "positional_reads": 12,
        "tensor_payloads": 12,
        "compressed_bytes": 139_217_920,
        "decoded_bytes": 666_430_464,
        "expert_payloads": 0,
    }
    if oracle["access"] != expected_access:
        raise ValueError("oracle access accounting")

    oracle_sha = sha256(oracle_raw)
    stages = oracle["oracle"]["stage_hashes"]
    route = {
        "schema": "pulsarmlx.f017.m1f0-layer3-route",
        "schema_version": "1.0.0",
        "evidence_kind": "real_checkpoint_oracle",
        "accepted_attempt": 1,
        "execution_config_sha256": config_sha,
        "authorization_sha256": authorization_sha,
        "oracle_package_sha256": oracle_sha,
        "layer": 3,
        "input_fixture_sha256": config["input_state"]["artifact_sha256"],
        "input_package_sha256": config["input_state"]["package_sha256"],
        "checkpoint_bindings": config["checkpoint_bindings"],
        "tensor_payload_sha256": oracle["tensor_payload_sha256"],
        "decoded_tensor_sha256": oracle["decoded_tensor_sha256"],
        "attention_normalized_input_sha256": stages["attention_normalized"],
        "attention_output_sha256": stages["attention_output"],
        "attention_residual_sha256": stages["attention_residual"],
        "router_normalized_input_sha256": stages["router_normalized"],
        "router_score_sha256": oracle["oracle"]["router_scores_sha256"],
        "top8_ids": selected,
        "top8_ids_sha256": oracle["oracle"]["top8_ids_sha256"],
        "routing_weights": oracle["oracle"]["routing_weights"],
        "routing_weights_sha256": oracle["oracle"]["routing_weights_sha256"],
        "repeat_integrity": repeat,
        "access": expected_access,
        "oracle_preparer_sha256": config["contracts"]["oracle_preparer"]["content_sha256"],
        "decoder_contract_sha256s": {
            "set": config["contracts"]["decoder"]["content_sha256"],
            "q5_k_real_byte": config["contracts"]["q5_k_real_byte"]["content_sha256"],
        },
        "selection_contract_sha256": config["contracts"]["selection"]["content_sha256"],
        "numerical_contract_sha256": config["contracts"]["numerical"]["content_sha256"],
        "m1f_recomputation_contract": {
            "exact_m1f0_attention_residual_is_input": True,
            "recomputed_attention_must_qualify_against_m1f0": True,
            "route_ids_remain_frozen": True,
            "route_divergence_fails": True,
        },
        "expert_computation": False,
    }
    admission.validate_route_artifact(root, route, config["input_state"]["package_sha256"])
    route_sha = sha256(canonical_json(route))
    payload_records = [
        {
            "ordinal": ordinal,
            "symbolic_name": binding["name"],
            "quantization": binding["quantization"],
            "logical_shape": binding["logical_shape"],
            "packed_length": binding["packed_length"],
            "packed_sha256": oracle["tensor_payload_sha256"][binding["name"]],
        }
        for ordinal, binding in enumerate(allowlist)
    ]
    decoded_records = [
        {
            "ordinal": ordinal,
            "symbolic_name": binding["name"],
            "decoded_sha256": oracle["decoded_tensor_sha256"][binding["name"]],
        }
        for ordinal, binding in enumerate(allowlist)
    ]
    evidence = {
        "schema": "pulsarmlx.f017.m1f0-evidence",
        "schema_version": "1.0.0",
        "attempt": 1,
        "attempt_state": "COMPLETED",
        "execution_config_sha256": config_sha,
        "authorization_sha256": authorization_sha,
        "oracle_package_sha256": oracle_sha,
        "route_artifact_sha256": route_sha,
        "input_state": oracle["input_state"],
        "tensor_payloads": payload_records,
        "decoded_tensors": decoded_records,
        "oracle": oracle["oracle"],
        "selection": {
            "top8_ids": selected,
            "top8_ids_sha256": oracle["oracle"]["top8_ids_sha256"],
            "routing_weights": oracle["oracle"]["routing_weights"],
            "routing_weights_sha256": oracle["oracle"]["routing_weights_sha256"],
            "exact": True,
        },
        "repeat_integrity": repeat,
        "numerical_qualification": oracle["numerical_qualification"],
        "access": expected_access,
        "isolation": oracle["isolation"],
        "timings": oracle["timing"],
        "first_failure": None,
        "verdict": "M1-F0 ACCEPTED",
    }
    evidence_sha = sha256(canonical_json(evidence))
    if ledger_path.exists():
        ledger = load(ledger_path)
        if ledger.get("schema") != "pulsarmlx.f017.m1f0-attempt-ledger":
            raise ValueError("attempt ledger identity")
        if any(record.get("attempt") == 1 for record in ledger.get("attempts", [])):
            raise ValueError("attempt ledger reuse")
    else:
        ledger = {
            "schema": "pulsarmlx.f017.m1f0-attempt-ledger",
            "schema_version": "1.0.0",
            "decoder_qualification_access": {
                "tensor_payloads": 1,
                "packed_sha256": config["q5_k_real_byte_qualification"]["packed_sha256"],
                "counted_as_route_discovery": False,
            },
            "attempts": [],
        }
    ledger["attempts"].append(
        {
            "attempt": 1,
            "authorization_sha256": authorization_sha,
            "execution_config_sha256": config_sha,
            "tooling_config_sha": config["source_identities"]["tooling_config_sha"],
            "tooling_tree_oid": config["source_identities"]["tooling_tree_oid"],
            "final_head_at_execution": authorization["reviewed_head_sha"],
            "verdict": "M1-F0 ACCEPTED",
            "consumed": True,
            "checkpoint_accesses": 12,
            "payload_count": 12,
            "failure_class": None,
            "first_failure": None,
            "route_produced": True,
            "route_artifact_sha256": route_sha,
            "evidence_sha256": evidence_sha,
            "next_remediation_sha": None,
        }
    )
    ledger["cumulative_checkpoint_access"] = {
        "decoder_qualification_payloads": 1,
        "route_discovery_payloads": 12,
        "total_payloads": 13,
    }

    write_atomic(route_path, route, exclusive=True)
    write_atomic(evidence_path, evidence, exclusive=True)
    if ledger_path.exists():
        ledger_path.chmod(0o644)
    write_atomic(ledger_path, ledger, exclusive=False)
    return route, evidence, ledger


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--execution-config", type=Path, required=True)
    parser.add_argument("--execution-config-sha256", required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--authorization-sha256", required=True)
    parser.add_argument("--oracle-package", type=Path, required=True)
    parser.add_argument("--route-output", type=Path, required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    args = parser.parse_args()
    route, evidence, _ = bank(
        args.repository_root.resolve(strict=True),
        args.execution_config,
        args.execution_config_sha256,
        args.authorization,
        args.authorization_sha256,
        args.oracle_package,
        args.route_output,
        args.evidence_output,
        args.ledger,
    )
    print(json.dumps({"route_sha256": sha256(canonical_json(route)), "verdict": evidence["verdict"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
