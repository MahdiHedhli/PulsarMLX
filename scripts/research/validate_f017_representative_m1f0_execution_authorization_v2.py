#!/usr/bin/env python3
"""Independent semantic validator for representative M1-F0 authorization v2."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
AUTH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-execution-authorization-v2.json"
REJECTED_V1 = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-execution-authorization-v1.json"
EXPECTED_V1 = "e46874b05d2f5946f5b6c0dc9ac4beeb50628a2ebc28f16d0b8a2fc1284627dc"
EXPECTED_HEAD = "2a657bdf41267817ff03cc5d233ec2507c87dbf2"
EXPECTED_BOUNDARY = "a9dc0d9effb3e52844203a34be587d12f0f7b011fb58d33c5dbdbe5b650deed3"
EXPECTED_GRAPH = "1585dad6b989fd0ac9b231f4e66e4d0129021868d027a3352a7b740707561558"
EXPECTED_EPSILON = "fc92b11223ee174b5f206a45a6d2b50540b4c82ba5d2c2333010947d525646e4"
EXPECTED_STAGE_NAMES = [
    "input_hidden", "attention_normalized", "query_rank", "query_rank_normalized",
    "query_heads", "kv_raw", "kv_normalized", "key_nope", "attention_scores",
    "attention_weights", "value_heads", "attention_output", "post_attention_residual",
    "router_normalized", "router_logits", "router_scores", "ranking", "selected_ids",
    "routing_weights",
]
EXPECTED_INVENTORY = [
    (0, "blk.3.attn_norm.weight", 2008634208, 24576, "F32", [6144]),
    (1, "blk.3.attn_q_a.weight", 2077864800, 8650752, "Q5_K", [2048, 6144]),
    (2, "blk.3.attn_q_a_norm.weight", 2086515552, 8192, "F32", [2048]),
    (3, "blk.3.attn_q_b.weight", 2086523744, 35651584, "Q8_0", [16384, 2048]),
    (4, "blk.3.attn_kv_a_mqa.weight", 2004872032, 3760128, "Q8_0", [576, 6144]),
    (5, "blk.3.attn_kv_a_norm.weight", 2008632160, 2048, "F32", [512]),
    (6, "blk.3.attn_k_b.weight", 1998187360, 6684672, "Q8_0", [64, 512, 192]),
    (7, "blk.3.attn_v_b.weight", 2122175328, 8912896, "Q8_0", [64, 256, 512]),
    (8, "blk.3.attn_output.weight", 2008658784, 69206016, "Q5_K", [6144, 16384]),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key}")
        result[key] = value
    return result


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates)


def validate_document(wrapper: dict[str, Any], candidate: dict[str, Any], rehearsal: dict[str, Any],
                      stage: dict[str, Any], historical: dict[str, Any], repository_root: Path | None = None) -> list[str]:
    errors: list[str] = []

    def require(condition: bool, code: str) -> None:
        if not condition:
            errors.append(code)

    require(wrapper.get("schema") == "pulsarmlx.f017.representative-m1f0-execution-authorization", "SCHEMA")
    require(wrapper.get("schema_version") == "2.0.0" and wrapper.get("status") == "PREPARED_REVIEW_REQUIRED", "STATUS")
    require(wrapper.get("authoritative_repository") == {"branch": "feat/017-real-checkpoint-runner", "base_commit_sha256": EXPECTED_HEAD}, "AUTHORITATIVE_HEAD")
    require(candidate.get("authoritative_repository", {}).get("commit_sha256") == EXPECTED_HEAD, "CANDIDATE_HEAD")
    semantic = candidate.get("semantic_authority", {})
    require(semantic.get("representative_boundary_v3", {}).get("sha256") == EXPECTED_BOUNDARY, "BOUNDARY_HASH")
    require(semantic.get("semantic_graph_v2", {}).get("sha256") == EXPECTED_GRAPH, "SEMANTIC_GRAPH_HASH")
    require(semantic.get("epsilon_adjudication", {}).get("sha256") == EXPECTED_EPSILON, "EPSILON_ADJUDICATION")

    executor = wrapper.get("executor", {})
    require(executor.get("event_shape") == "9_CHECKPOINT_READS_PLUS_3_RETAINED_ROUTER_AUTHORITIES_PLUS_1_RETAINED_S0", "EXECUTOR_EVENT_SHAPE")
    require(executor.get("legacy_12_read_executor_prohibited") is True, "LEGACY_EXECUTOR")
    synthetic = wrapper.get("synthetic_rehearsal", {})
    require(isinstance(synthetic.get("sha256"), str) and len(synthetic.get("sha256", "")) == 64, "REHEARSAL_SHA")
    require(synthetic.get("real_geometry") is True and synthetic.get("fresh_process_successes") == 2 and synthetic.get("failure_paths_passed", 0) >= 15, "REHEARSAL_BINDING")
    require(rehearsal.get("executor_sha256") == executor.get("sha256"), "REHEARSAL_EXECUTOR_SHA")
    require(rehearsal.get("fresh_process_exact_stage_identity") is True and rehearsal.get("all_failure_rehearsals_pass") is True, "REHEARSAL_RESULT")
    require(rehearsal.get("real_geometry") == {"payload_reads": 9, "packed_bytes": 132900864, "retained_router_inputs": 3, "canonical_s0_inputs": 1}, "REHEARSAL_GEOMETRY")
    require(rehearsal.get("real_checkpoint_reads") == 0 and rehearsal.get("real_shard_opens") == 0 and rehearsal.get("real_ledger_after") == 166, "REHEARSAL_REAL_ACCESS")
    require(rehearsal.get("success_accounting") == {"canonical_retained_s0_inputs": 1, "checkpoint_payload_reads": 9, "expert_payload_reads": 0, "retained_router_injections": 3, "shard_opens": 1}, "SUCCESS_ACCOUNTING")
    terminal = rehearsal.get("success_terminal", {})
    require(terminal.get("consumed_reads") == 9 and terminal.get("packed_bytes") == 132900864 and terminal.get("ledger") == 175 and isinstance(terminal.get("journal_sha256"), str), "BANKER_JOURNAL")

    event_shape = candidate.get("event_shape", {})
    require(event_shape == {"checkpoint_payload_reads": 9, "retained_router_injections": 3, "canonical_retained_s0_inputs": 1, "expert_payload_reads": 0}, "EVENT_SHAPE")
    inventory = candidate.get("attention_payload_inventory", [])
    require(len(inventory) == 9 and [item.get("ordinal") for item in inventory] == list(range(9)), "INVENTORY_ORDER")
    observed_inventory = [(item.get("ordinal"), item.get("key"), item.get("offset"), item.get("packed_bytes"), item.get("quantization"), item.get("logical_shape")) for item in inventory]
    require(observed_inventory == EXPECTED_INVENTORY, "INVENTORY_RANGE_GEOMETRY")
    require(sum(item.get("packed_bytes", -1) for item in inventory) == 132900864, "PACKED_TOTAL")
    require(len({item.get("key") for item in inventory}) == 9, "INVENTORY_KEYS")
    packed_anchor = {item["symbolic_name"]: item["packed_sha256"] for item in historical.get("tensor_payloads", [])}
    decoded_anchor = {item["symbolic_name"]: item["decoded_sha256"] for item in historical.get("decoded_tensors", [])}
    for item in inventory:
        key = item.get("key")
        require(item.get("packed_sha256") == packed_anchor.get(key), f"PACKED_SHA:{key}")
        require(item.get("decoded_sha256") == decoded_anchor.get(key), f"DECODED_SHA:{key}")
        if item.get("quantization") == "F32":
            require(item.get("packed_sha256") == item.get("decoded_sha256"), f"F32_IDENTITY:{key}")
    read = candidate.get("read_contract", {})
    require(read.get("retain_at_creation_before_decode") is True, "RETAIN_BEFORE_DECODE")
    require(read.get("durable_receipt_before_next_read") is True, "DURABLE_RECEIPT")
    require(read.get("ordering") == "STRICT_ASCENDING_ORDINAL_0_THROUGH_8", "READ_ORDER")
    require(read.get("expected_reads") == 9 and read.get("expected_packed_bytes") == 132900864, "READ_TOTALS")
    require(read.get("maximum_shard_opens") == 1, "MAX_OPENS")
    require(all(read.get(name) is False for name in ("fallback_reads", "additional_reads", "retries", "dynamic_discovery")), "EXTRA_READS")

    retained = candidate.get("retained_inputs", [])
    require([item.get("role") for item in retained] == ["canonical_s0", "ffn_norm", "router_matrix", "correction_bias"], "RETAINED_ROLES")
    s0 = retained[0] if retained else {}
    require(s0.get("sha256") == "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11", "S0_SHA")
    require(s0.get("private_manifest_sha256") == "a68316207957bc8f804c167b627c208f068d086aed85506c89d87569b992bc60", "S0_MANIFEST")
    require(s0.get("semantic_role") == "CANONICAL_LAYER3_ENTRY_PRE_ATTENTION", "S0_ROLE")
    require(all(item.get("checkpoint_fallback") is False for item in retained), "RETAINED_CHECKPOINT_FALLBACK")
    preflight = candidate.get("retained_preflight", {})
    require(preflight == {"identity_rule": "EXPECTED_SHA_EQUALS_BEFORE_SHA_EQUALS_AFTER_SHA", "regular_file": True, "non_symlink": True, "read_only": True, "no_writable_alias": True, "single_link": True, "checkpoint_fallback": False}, "RETAINED_PREFLIGHT")
    decoders = candidate.get("decoder_bindings", {})
    require(decoders.get("F32", {}).get("required_identity") == "PACKED_SHA256_EQUALS_DECODED_SHA256", "F32_DECODER_BINDING")
    for kind in ("Q5_K", "Q8_0"):
        binding = decoders.get(kind, {})
        require(binding.get("same_retained_bytes") is True and binding.get("exact_canonical_f32_agreement") is True and binding.get("independent_kernels") is True, f"DECODER_INDEPENDENCE:{kind}")
        require(binding.get("decoder_a", {}).get("kernel") != binding.get("decoder_b", {}).get("kernel"), f"DECODER_KERNELS:{kind}")

    ledger = candidate.get("ledger_contract", {})
    require(ledger.get("before") == 166 and ledger.get("after_success") == 175, "LEDGER_RANGE")
    require(ledger.get("after_n_durable_receipts") == "166+N" and ledger.get("partial_failure") == "TERMINAL_NO_RESUME_NO_RETRY_NO_SECOND_ATTEMPT", "PARTIAL_FAILURE")
    rms = candidate.get("execution_semantics", {}).get("rmsnorm", {})
    require(rms == {"epsilon_source": "f32(1e-5)", "epsilon_exact_decimal": "9.999999747378752e-6", "epsilon_bits_hex": "0x3727c5ac", "epsilon_dtype": "IEEE-754 binary32", "accumulator_dtype": "IEEE-754 binary32"}, "RMSNORM")
    require(candidate.get("execution_semantics", {}).get("stop_boundary") == "AFTER_REPRESENTATIVE_ROUTE_BEFORE_ANY_ROUTED_OR_SHARED_EXPERT_EXECUTION", "STOP_BOUNDARY")

    names = [item.get("name") for item in stage.get("stages", [])]
    require(names == EXPECTED_STAGE_NAMES, "STAGE_VOCABULARY")
    require(candidate.get("stage_vocabulary", {}).get("sha256") == rehearsal.get("stage_vocabulary_sha256"), "STAGE_BINDING")
    require(candidate.get("surface_separation") == {"historical_direct_dprefix_outputs": "PROHIBITED_AS_INPUT", "representative_route_derived_from_new_post_attention_residual": True}, "DIRECT_DPREFIX_REUSE")
    authorization = wrapper.get("authorization", {})
    require(authorization.get("real_event_authorized") is False and authorization.get("checkpoint_access_authorized") is False, "REAL_AUTHORIZATION")
    require(authorization.get("expert_execution_authorized") is False and authorization.get("shared_expert_execution_authorized") is False, "EXPERT_AUTHORIZATION")
    invariants = wrapper.get("preparation_invariants", {})
    require(invariants.get("real_payload_ledger_before") == invariants.get("real_payload_ledger_after") == 166, "PREPARATION_LEDGER")
    require(invariants.get("checkpoint_reads") == invariants.get("shard_opens") == 0, "PREPARATION_ACCESS")

    if repository_root is not None:
        for binding, code in ((wrapper.get("authorization_candidate", {}), "CANDIDATE_FILE"),
                              (executor, "EXECUTOR_FILE"), (synthetic, "REHEARSAL_FILE"),
                              (candidate.get("stage_vocabulary", {}), "STAGE_FILE")):
            path = repository_root / str(binding.get("path", ""))
            require(path.is_file() and sha(path) == binding.get("sha256"), code)
        require(sha(REJECTED_V1) == EXPECTED_V1, "REJECTED_V1_IMMUTABILITY")
        validator_binding = wrapper.get("validator", {})
        validator_path = repository_root / str(validator_binding.get("path", ""))
        schema_path = repository_root / str(validator_binding.get("schema_path", ""))
        require(validator_path.is_file() and sha(validator_path) == validator_binding.get("sha256"), "VALIDATOR_FILE")
        require(schema_path.is_file() and sha(schema_path) == validator_binding.get("schema_sha256"), "SCHEMA_FILE")
        for binding, code in ((semantic.get("representative_boundary_v3", {}), "BOUNDARY_FILE"),
                              (semantic.get("semantic_graph_v2", {}), "GRAPH_FILE"),
                              (semantic.get("epsilon_adjudication", {}), "EPSILON_FILE"),
                              (candidate.get("historical_hash_anchor", {}), "HISTORICAL_FILE"),
                              (candidate.get("router_reuse_authorization", {}), "ROUTER_REUSE_FILE")):
            path = repository_root / str(binding.get("path", ""))
            require(path.is_file() and sha(path) == binding.get("sha256"), code)
        for kind in ("Q5_K", "Q8_0"):
            for lane in ("decoder_a", "decoder_b"):
                binding = decoders[kind][lane]
                path = repository_root / binding["source_path"]
                require(path.is_file() and sha(path) == binding["source_sha256"], f"DECODER_SOURCE:{kind}:{lane}")
    return errors


def validate_paths(root: Path = ROOT, auth_path: Path = AUTH) -> list[str]:
    wrapper = load(auth_path)
    candidate_path = root / wrapper["authorization_candidate"]["path"]
    rehearsal_path = root / wrapper["synthetic_rehearsal"]["path"]
    candidate = load(candidate_path)
    rehearsal = load(rehearsal_path)
    stage = load(root / candidate["stage_vocabulary"]["path"])
    historical = load(root / candidate["historical_hash_anchor"]["path"])
    return validate_document(wrapper, candidate, rehearsal, stage, historical, root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--authorization", type=Path, default=AUTH)
    args = parser.parse_args()
    errors = validate_paths(args.repository_root.resolve(), args.authorization.resolve())
    result = {"result": "FAIL" if errors else "PASS", "errors": errors, "checkpoint_reads": 0,
              "shard_opens": 0, "ledger": 166, "real_event_authorized": False}
    print(json.dumps(result, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
