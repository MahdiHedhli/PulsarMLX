#!/usr/bin/env python3
"""Generate the checkpoint-free representative expert recovery package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
SELECTED_IDS = [250, 10, 237, 62, 73, 177, 218, 28]
WEIGHTS = [
    0.7487501576296707, 0.3348627106807668, 0.23863270273063697,
    0.23688715675086147, 0.2514906203405492, 0.23059957299763345,
    0.22915341148588297, 0.22962366738399842,
]
ROLES = ["gate", "up", "down"]


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    assert isinstance(value, dict)
    return value


def write(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value) + b"\n")
    return digest(path)


def build_inventory() -> list[dict[str, Any]]:
    source = load(EVIDENCE / "f017-canonical-expert-output-recovery-evidence-review-v1.json")
    by_pair = {(x["expert_id"], x["role"]): x for x in source["payloads"]}
    historical_sequence = {(x["expert_id"], x["role"]): x["sequence"] for x in source["payloads"]}
    result = []
    for ordinal, (expert, role) in enumerate((e, r) for e in SELECTED_IDS for r in ROLES):
        item = by_pair[(expert, role)]
        source_sequence = historical_sequence[(expert, role)]
        result.append({
            "ordinal": ordinal,
            "expert_id": expert,
            "role": role,
            "checkpoint_key": item["checkpoint_key"],
            "shard_ordinal": 2,
            "shard_sha256": source["checkpoint_access"]["shard_sha256"],
            "offset": item["offset"],
            "packed_bytes": item["packed_bytes"],
            "quantization": item["quantization"],
            "logical_shape": item["logical_shape"],
            "packed_sha256": item["packed_sha256"],
            "decoded_sha256": item["decoded_sha256"],
            "decoder_a_identity": item["decoder_a_identity"],
            "decoder_b_identity": item["decoder_b_identity"],
            "source_event_sequence": source_sequence,
            "source_relative_path": f"{source_sequence:02d}-expert-{expert}-{role}.bin",
            "availability": "PERSISTED_PACKED_AUTHORITY",
            "new_checkpoint_read_required": False,
        })
    assert len(result) == 24
    assert sum(x["packed_bytes"] for x in result) == 90_439_680
    return result


def build_base(input_manifest_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    inventory = build_inventory()
    route_path = EVIDENCE / "f017-representative-m1f0-concrete-route-values-v1.json"
    execution_path = EVIDENCE / "f017-representative-m1f0-real-execution-result-v1.json"
    source_review_path = EVIDENCE / "f017-canonical-expert-output-recovery-evidence-review-v1.json"
    source_result_path = EVIDENCE / "f017-canonical-expert-recovery-result-v1.json"
    executor_path = ROOT / "scripts/research/f017_representative_expert_recovery_executor_v1.py"
    materializer_path = ROOT / "scripts/research/f017_materialize_representative_expert_input_v1.py"
    computation_source = ROOT / "scripts/research/f017_canonical_expert_output_production.py"
    input_manifest_sha = digest(input_manifest_path)
    route_pairs = [
        {"ordinal": ordinal, "expert_id": expert, "routing_weight": weight,
         "binding": "ATOMIC_ID_WEIGHT_PAIR"}
        for ordinal, (expert, weight) in enumerate(zip(SELECTED_IDS, WEIGHTS, strict=True))
    ]
    reuse = {
        "schema": "pulsarmlx.f017.representative-expert-packed-weight-reuse-authorization",
        "schema_version": "1.0.0",
        "authorization_id": "F017-REPRESENTATIVE-EXPERT-PACKED-WEIGHT-REUSE-1",
        "consumer_id": "F017-REPRESENTATIVE-M1F0-EXPERT-OUTPUT-RECOVERY-1",
        "status": "PREPARED_REVIEW_REQUIRED",
        "source_event": "F017-CANONICAL-EXPERT-OUTPUT-RECOVERY-1",
        "source_result_sha256": digest(source_result_path),
        "source_evidence_review_sha256": digest(source_review_path),
        "source_private_manifest_sha256": "86d577020ad3e5bf6480b774536416145a154104eac643b21df644044a55e99e",
        "retained_payload_inventory": inventory,
        "surface_independence_proof": {
            "basis": "checkpoint keys identify immutable layer-3 expert parameter slices indexed only by expert id; input activations are not encoded in model-weight bytes",
            "same_model_parameter_required_for_any_input": True,
            "historical_expert_outputs_reusable": False,
            "historical_normalized_input_reusable": False,
        },
        "allowed_purpose": "DECODE_RETAINED_MODEL_WEIGHTS_AND_COMPUTE_INDIVIDUAL_OUTPUTS_FOR_CANONICAL_REPRESENTATIVE_INPUT_ONLY",
        "checkpoint_fallback": False,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "real_payload_ledger_delta": 0,
    }
    computation = {
        "schema": "pulsarmlx.f017.representative-expert-computation-contract",
        "schema_version": "1.0.0",
        "input": {"semantic_role": "POST_ATTENTION_FFN_RMSNORM_OUTPUT_ROUTER_AND_EXPERT_INPUT",
                  "dtype": "little-endian-f32", "shape": [6144]},
        "per_expert_formula": "down(strict_f32_silu(gate(input)) * up(input))",
        "gate_up_shape": [2048, 6144],
        "down_shape": [6144, 2048],
        "matrix_orientation": "row_major_[out,in]_times_[in]",
        "accumulation": "strict_increasing_column_f32_multiply_then_f32_add",
        "activation": "strict_binary32_SiLU_then_binary32_multiply",
        "output": {"dtype": "little-endian-f32", "shape": [6144], "byte_length": 24576},
        "computation_source_path": "scripts/research/f017_canonical_expert_output_production.py",
        "computation_source_sha256": digest(computation_source),
        "symbols": ["strict_f32_matvec", "strict_f32_silu"],
        "decoder_lineage_sha256": "9a92bacda92e999a9062c154acd1b52c86e1d644f0d4d697defb2db40a85ce84",
        "decoder_exact_agreement_required": True,
        "blas_permitted": False,
        "gpu_permitted": False,
        "aggregate_permitted": False,
    }
    reuse_path = CONTRACTS / "f017-representative-expert-packed-weight-reuse-authorization-v1.json"
    computation_path = CONTRACTS / "f017-representative-expert-computation-v1.json"
    reuse_sha = write(reuse_path, reuse)
    computation_sha = write(computation_path, computation)
    base = {
        "schema": "pulsarmlx.f017.representative-expert-recovery-authorization",
        "schema_version": "1.0.0",
        "authorization_id": "F017-REPRESENTATIVE-M1F0-EXPERT-OUTPUT-RECOVERY-AUTHORIZATION-1",
        "event_id": "F017-REPRESENTATIVE-M1F0-EXPERT-OUTPUT-RECOVERY-1",
        "status": "PREPARED_REVIEW_REQUIRED",
        "real_event_authorized": False,
        "preparation_base_head": "461617c83986af30b1bb5c93981fa2c5caf29545",
        "execution_evidence_sha256": digest(execution_path),
        "route_value_evidence_sha256": digest(route_path),
        "selected_expert_ids": SELECTED_IDS,
        "routing_weights": WEIGHTS,
        "route_pairs": route_pairs,
        "selected_ids_sha256": "a0f2e2b59ebc606c43e17eab8f76a5b14c26b678bef2a9b0207c3f7dd15f164f",
        "routing_weights_sha256": "ff1a7127b418b80dce4e4361e314c16ad50e86484cb1861ad27f6f9ee70b8587",
        "representative_route_sha256": "03dc2dfbed65848fdcb649f41f98793ca0f8cdd702c76b55d71c762fc5338103",
        "representative_expert_input": {
            "sha256": "687a692a452e30860c34055942061f4ff368ec0e1c815439c71e457a444fe62c",
            "private_manifest_sha256": input_manifest_sha,
            "materializer_path": "scripts/research/f017_materialize_representative_expert_input_v1.py",
            "materializer_sha256": digest(materializer_path),
            "dtype": "little-endian-f32", "shape": [6144], "byte_length": 24576,
            "semantic_role": "CANONICAL_REPRESENTATIVE_POST_ATTENTION_FFN_NORMALIZED_EXPERT_INPUT",
            "expected_equals_before_equals_after": True,
            "checkpoint_fallback": False,
        },
        "retained_weight_reuse": {"path": str(reuse_path.relative_to(ROOT)), "sha256": reuse_sha,
                                  "consumer_id": reuse["consumer_id"]},
        "retained_payload_inventory": inventory,
        "computation_contract": {"path": str(computation_path.relative_to(ROOT)), "sha256": computation_sha},
        "executor": {"path": str(executor_path.relative_to(ROOT)), "sha256": digest(executor_path),
                     "checkpoint_capability": False, "shard_capability": False},
        "access_accounting": {
            "starting_real_payload_ledger": 175,
            "successful_terminal_ledger": 175,
            "new_checkpoint_payload_reads": 0,
            "new_checkpoint_packed_bytes": 0,
            "shard_opens": 0,
            "retained_packed_payloads": 24,
            "retained_packed_bytes": 90_439_680,
        },
        "failure_semantics": {
            "preflight_all_inputs_before_expert_execution": True,
            "partial_output_failure_is_terminal": True,
            "retry": False, "resume": False, "second_attempt": False,
            "ledger_change_on_any_outcome": 0,
        },
        "output_contract": {
            "individual_outputs": 8, "bytes_each": 24576, "dtype": "little-endian-f32",
            "shape_each": [6144], "canonical_order": SELECTED_IDS,
            "two_fresh_process_reproductions_required": 2,
            "all_eight_output_sha256_exact": True,
        },
        "prohibitions": {
            "checkpoint_access": True, "shard_open": True,
            "historical_direct_dprefix_input": True, "historical_direct_dprefix_outputs": True,
            "routed_aggregate": True, "shared_expert": True, "ffn_completion": True,
            "candidate_dispatch": True, "gpu": True,
        },
        "stop_boundary": "AFTER_EIGHT_INDIVIDUAL_REPRESENTATIVE_EXPERT_OUTPUTS_ARE_BANKED_BEFORE_WEIGHTED_AGGREGATE",
        "future_release_token_requirements": {
            "authorization_sha256_policy": "EXACT_FINAL_AUTHORIZATION_FILE_SHA256",
            "event_id": "F017-REPRESENTATIVE-M1F0-EXPERT-OUTPUT-RECOVERY-1",
            "disposition": "GO_EXECUTE_ONCE_NO_RETRY",
            "real_event_authorized": True,
        },
        "authorization_file_sha256": None,
    }
    return base, reuse, computation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--rehearsal")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base, _, _ = build_base(args.input_manifest)
    base["candidate_semantic_sha256"] = digest_bytes(canonical(base))
    if args.rehearsal:
        rehearsal_path = Path(args.rehearsal).resolve()
        base["synthetic_rehearsal"] = {"path": str(rehearsal_path.relative_to(ROOT)), "sha256": digest(rehearsal_path)}
    else:
        base["synthetic_rehearsal"] = None
    identity = write(args.output, base)
    print(identity)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
