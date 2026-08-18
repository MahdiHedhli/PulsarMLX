#!/usr/bin/env python3
"""Checkpoint-free validator for the representative M1-F0 review package."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


EXPECTED_HEAD = "c5eb3c3efb0ab62f3b34006e769a14bd57ed3e76"
EXPECTED_BOUNDARY = "a9dc0d9effb3e52844203a34be587d12f0f7b011fb58d33c5dbdbe5b650deed3"
EXPECTED_GRAPH = "1585dad6b989fd0ac9b231f4e66e4d0129021868d027a3352a7b740707561558"
EXPECTED_EPSILON_ADJUDICATION = "fc92b11223ee174b5f206a45a6d2b50540b4c82ba5d2c2333010947d525646e4"
EXPECTED_FREEZE = "1f521d3e6a5adcd8cb30dfd013b54ee1f00b81c63d5d027e9128b37bb9f1ca5d"
EXPECTED_INPUT = "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11"
EXPECTED_CATALOG = "135500cc46b65a877027b597bf20e0c7bb613802e5137c48204e7ab6e7a7ff19"
EXPECTED_SHARD = "d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36"
EXPECTED_ORACLE = "ec9a679b78ccd5adb5353cb689cefe642307a07fdb9a266d65d99dab86c6e48d"
EXPECTED_ROUTER = {
    "blk.3.ffn_norm.weight": ("1d9228483902bf2ca1088589d25c1cbc116facd82454a117e7dafb2d48f83d8f", 24576),
    "blk.3.ffn_gate_inp.weight": ("da0263ba11f06e21532aff708b8677c76381c1165e11134c72d7039ebb64439a", 6291456),
    "blk.3.exp_probs_b.bias": ("eb6feeb8d7ab446e4e786aaac55c22cc7b98521dbd71cb0a57610d8da59b0491", 1024),
}
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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys)


def _catalog_tensors(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if isinstance(value.get("name"), str) and "data_offset_abs" in value:
            result.append(value)
        for child in value.values():
            result.extend(_catalog_tensors(child))
    elif isinstance(value, list):
        for child in value:
            result.extend(_catalog_tensors(child))
    return result


def packed_bytes(quantization: str, dimensions: list[int]) -> int:
    elements = math.prod(dimensions)
    if quantization == "F32":
        return elements * 4
    if quantization == "Q5_K":
        if elements % 256:
            raise ValueError("Q5_K block alignment")
        return elements // 256 * 176
    if quantization == "Q8_0":
        if elements % 32:
            raise ValueError("Q8_0 block alignment")
        return elements // 32 * 34
    raise ValueError(f"unsupported quantization {quantization}")


def validate_document(document: dict[str, Any], repository_root: Path | None = None) -> list[str]:
    errors: list[str] = []

    def require(condition: bool, code: str) -> None:
        if not condition:
            errors.append(code)

    require(document.get("status") == "PREPARED_REVIEW_REQUIRED", "STATUS")
    repo = document.get("authoritative_repository", {})
    require(repo.get("branch") == "feat/017-real-checkpoint-runner", "BRANCH")
    require(repo.get("commit_sha256") == EXPECTED_HEAD, "AUTHORITATIVE_HEAD")

    semantic = document.get("semantic_authority", {})
    require(semantic.get("representative_boundary_v3", {}).get("sha256") == EXPECTED_BOUNDARY, "BOUNDARY_HASH")
    require(semantic.get("semantic_graph_v2", {}).get("sha256") == EXPECTED_GRAPH, "SEMANTIC_GRAPH_HASH")
    require(semantic.get("epsilon_adjudication", {}).get("sha256") == EXPECTED_EPSILON_ADJUDICATION, "EPSILON_ADJUDICATION_HASH")
    require(semantic.get("boundary_v3_freeze", {}).get("sha256") == EXPECTED_FREEZE, "BOUNDARY_FREEZE_HASH")
    canonical = semantic.get("canonical_input", {})
    require(canonical.get("sha256") == EXPECTED_INPUT, "CANONICAL_INPUT_HASH")
    require(canonical.get("semantic_role") == "CANONICAL_LAYER3_ENTRY_PRE_ATTENTION", "CANONICAL_INPUT_ROLE")
    require("routed_expert_execution" in semantic.get("ends_before", []), "STOP_BEFORE_EXPERTS")

    checkpoint = document.get("checkpoint_binding", {})
    require(checkpoint.get("catalog_metadata", {}).get("sha256") == EXPECTED_CATALOG, "CATALOG_HASH")
    shard = checkpoint.get("shard", {})
    require(shard.get("ordinal") == 2 and shard.get("sha256") == EXPECTED_SHARD, "SHARD_IDENTITY")
    require(shard.get("maximum_opens") == 1, "MAXIMUM_SHARD_OPENS")

    inventory = document.get("attention_payload_inventory", [])
    require(len(inventory) == 9, "INVENTORY_COUNT")
    observed = [
        (item.get("ordinal"), item.get("key"), item.get("offset"), item.get("packed_bytes"), item.get("quantization"), item.get("logical_shape"))
        for item in inventory
    ]
    require(observed == EXPECTED_INVENTORY, "INVENTORY_ORDER_OR_RANGE")
    require(len({item.get("key") for item in inventory}) == 9, "INVENTORY_DUPLICATE_KEY")
    require(all(item.get("shard") == 2 for item in inventory), "INVENTORY_SHARD")

    read = document.get("read_contract", {})
    require(read.get("ordering") == "STRICT_ASCENDING_ORDINAL_0_THROUGH_8", "READ_ORDER")
    require(read.get("expected_reads") == 9, "READ_COUNT")
    require(read.get("expected_packed_bytes") == 132900864, "PACKED_BYTE_TOTAL")
    require(sum(item.get("packed_bytes", -1) for item in inventory) == 132900864, "INVENTORY_BYTE_SUM")
    require(read.get("maximum_shard_opens") == 1, "READ_MAXIMUM_OPENS")
    require(read.get("additional_reads") is False and read.get("fallback_reads") is False, "EXTRA_CHECKPOINT_READS")
    require(read.get("retries") is False and read.get("dynamic_key_discovery") is False, "DYNAMIC_OR_RETRY_READS")

    ledger = document.get("ledger_contract", {})
    require(ledger.get("before") == 166, "LEDGER_BEFORE")
    require(ledger.get("after_success") == 175, "LEDGER_AFTER")
    require(ledger.get("after_n_successful_reads") == "166+N", "LEDGER_PARTIAL_FORMULA")
    require("TERMINALIZE" in ledger.get("partial_failure", "") and "NO_RETRY" in ledger.get("partial_failure", ""), "LEDGER_PARTIAL_FAILURE")
    failure = document.get("failure_contract", {})
    require(failure.get("continue_after_partial_failure") is False, "CONTINUE_AFTER_PARTIAL_FAILURE")
    require(failure.get("second_attempt_authorized") is False and failure.get("automatic_retry") is False, "NO_RETRY")

    execution = document.get("execution_semantics", {})
    require(execution.get("device") == "CPU_ONLY" and execution.get("gpu_dispatches") == 0, "CPU_ONLY")
    require(execution.get("arithmetic") == "STRICT_IEEE754_BINARY32_FIXED_INCREASING_INDEX_PER_OPERATION_ROUNDING", "ARITHMETIC_CLASS")
    rms = execution.get("rmsnorm", {})
    require(rms.get("epsilon_source") == "f32(1e-5)", "RMSNORM_EPSILON")
    require(rms.get("epsilon_exact_decimal") == "9.999999747378752e-6" and rms.get("epsilon_bits_hex") == "0x3727c5ac", "RMSNORM_EPSILON_IDENTITY")
    require(rms.get("epsilon_dtype") == "IEEE-754 binary32", "RMSNORM_EPSILON_DTYPE")
    require(rms.get("accumulator_dtype") == "IEEE-754 binary32", "RMSNORM_ACCUMULATOR_DTYPE")
    require(rms.get("sites") == ["attention_input", "query_rank", "compressed_kv", "post_attention_ffn"], "RMSNORM_SITES")
    require(execution.get("oracle_source", {}).get("sha256") == EXPECTED_ORACLE, "ORACLE_SOURCE")

    reuse = document.get("router_reuse_authorization", {})
    require(reuse.get("status") == "PREPARED_REVIEW_REQUIRED", "ROUTER_REUSE_STATUS")
    require(reuse.get("artifact", {}).get("sha256") == "a0f067871c2a764058bc549fdd0739508cd2072e92bf1ce3e346687443012f68", "ROUTER_REUSE_ARTIFACT")
    require(reuse.get("allowed_purpose") == "REPRESENTATIVE_POST_ATTENTION_M1F0_ROUTING_ONLY", "ROUTER_REUSE_PURPOSE")
    artifacts = reuse.get("artifacts", [])
    require(len(artifacts) == 3, "ROUTER_REUSE_COUNT")
    by_key = {item.get("key"): item for item in artifacts}
    require(set(by_key) == set(EXPECTED_ROUTER), "ROUTER_REUSE_KEYS")
    for key, (digest, length) in EXPECTED_ROUTER.items():
        item = by_key.get(key, {})
        require(item.get("sha256") == digest and item.get("byte_length") == length, f"ROUTER_REUSE_IDENTITY:{key}")
    require(reuse.get("new_payload_reads") == 0, "ROUTER_REUSE_READS")
    require("NO_CHECKPOINT_FALLBACK" in reuse.get("execution_preflight_requirements", []), "ROUTER_REUSE_NO_FALLBACK")

    separation = document.get("surface_separation", {})
    require(separation.get("historical_direct_dprefix_route_and_outputs") == "VALID_BUT_DIFFERENT_SURFACE_PROHIBITED_AS_INPUT", "DIRECT_DPREFIX_REUSE")
    require(separation.get("representative_route_must_be_computed_from_new_S1") is True, "REPRESENTATIVE_ROUTE_SOURCE")

    auth = document.get("authorization", {})
    require(auth.get("real_event_authorized") is False and auth.get("checkpoint_access_authorized") is False, "REAL_EVENT_AUTHORIZATION")
    require(auth.get("independent_adversarial_review_required") is True, "REVIEW_REQUIRED")
    require(auth.get("expert_execution_authorized") is False and auth.get("shared_expert_execution_authorized") is False, "EXPERT_EXECUTION_AUTHORIZATION")
    isolation = document.get("preparation_isolation", {})
    require(isolation.get("checkpoint_reads") == 0 and isolation.get("shard_opens") == 0, "PREPARATION_CHECKPOINT_ACCESS")
    require(isolation.get("real_payload_ledger_before") == 166 and isolation.get("real_payload_ledger_after") == 166, "PREPARATION_LEDGER")
    require(isolation.get("representative_computations") == 0, "REPRESENTATIVE_COMPUTATION")

    if repository_root is not None:
        bindings = [
            semantic.get("representative_boundary_v3", {}), semantic.get("semantic_graph_v2", {}),
            semantic.get("epsilon_adjudication", {}), semantic.get("boundary_v3_freeze", {}),
            checkpoint.get("catalog_metadata", {}), checkpoint.get("decoded_tensor_planning_contract", {}),
            execution.get("oracle_source", {}), reuse.get("source_historical_attempt", {}),
            reuse.get("source_retention_manifest", {}), reuse.get("artifact", {}),
        ]
        for binding in bindings:
            path = repository_root / str(binding.get("path", ""))
            require(path.is_file() and sha256(path) == binding.get("sha256"), f"BOUND_FILE:{binding.get('path')}")

        catalog_path = repository_root / checkpoint.get("catalog_metadata", {}).get("path", "")
        if catalog_path.is_file():
            catalog = load_json(catalog_path)
            catalog_by_name = {item["name"]: item for item in _catalog_tensors(catalog)}
            for item in inventory:
                entry = catalog_by_name.get(item.get("key"))
                require(entry is not None, f"CATALOG_ENTRY:{item.get('key')}")
                if entry is None:
                    continue
                require(entry.get("data_offset_abs") == item.get("offset"), f"CATALOG_OFFSET:{item.get('key')}")
                require(entry.get("type") == item.get("quantization"), f"CATALOG_TYPE:{item.get('key')}")
                require(list(reversed(entry.get("dims", []))) == item.get("logical_shape"), f"CATALOG_SHAPE:{item.get('key')}")
                try:
                    derived = packed_bytes(entry.get("type"), entry.get("dims"))
                except ValueError:
                    derived = -1
                require(derived == item.get("packed_bytes"), f"CATALOG_PACKED_BYTES:{item.get('key')}")

        historical = load_json(repository_root / reuse["source_historical_attempt"]["path"])
        decoded = {item["symbolic_name"]: item["decoded_sha256"] for item in historical.get("decoded_tensors", [])}
        for key, (digest, _) in EXPECTED_ROUTER.items():
            require(decoded.get(key) == digest, f"HISTORICAL_ROUTER_AUTHORITY:{key}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository_root.resolve()
    document = load_json(args.contract)
    errors = validate_document(document, root)
    if errors:
        print(json.dumps({"result": "FAIL", "errors": errors}, sort_keys=True))
        return 1
    print(json.dumps({
        "result": "PASS",
        "inventory_reads": 9,
        "packed_bytes": 132900864,
        "ledger": [166, 175],
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "real_event_authorized": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
