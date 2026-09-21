#!/usr/bin/env python3
"""Checkpoint-free production tensor plan for the F017 V9 execution release."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from f017_oracle_primary_decoders import LAYOUT


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "docs/research/glm52/raw/f016-c01-catalog-0001.json"
CHECKPOINT_METADATA = ROOT / "docs/validation/glm52-checkpoint.json"
SHARD_ORDINAL = {
    f"GLM-5.2-UD-IQ2_XXS-{ordinal:05d}-of-00006.gguf": ordinal
    for ordinal in range(1, 7)
}
GRAPH = re.compile(
    r"^(?:token_embd\.weight|output_norm\.weight|output\.weight|"
    r"blk\.\d+\.(?:attn_norm|attn_q_a|attn_q_a_norm|attn_q_b|"
    r"attn_kv_a_mqa|attn_kv_a_norm|attn_k_b|attn_v_b|attn_output|"
    r"ffn_norm|ffn_gate|ffn_up|ffn_down|ffn_gate_inp|exp_probs_b|"
    r"ffn_gate_exps|ffn_up_exps|ffn_down_exps|ffn_gate_shexp|"
    r"ffn_up_shexp|ffn_down_shexp)\.(?:weight|bias))$"
)


def _byte_length(record: dict) -> int:
    count = 1
    for dimension in record["dims"]:
        if type(dimension) is not int or dimension <= 0:
            raise ValueError("tensor dimension")
        count *= dimension
    block_values, block_bytes = LAYOUT[record["type"]]
    if count % block_values:
        raise ValueError("tensor block divisibility")
    return count // block_values * block_bytes


def build_plan(catalog_path: Path = CATALOG) -> dict:
    document = json.loads(catalog_path.read_bytes())
    metadata = json.loads(CHECKPOINT_METADATA.read_bytes())
    shard_sizes = {SHARD_ORDINAL[item["filename"]]: item["size_bytes"] for item in metadata["files"]}
    if set(shard_sizes) != set(range(1, 7)):
        raise ValueError("production shard-size census")
    tensors = document.get("tensors")
    if type(tensors) is not list or len(tensors) != 1809:
        raise ValueError("production catalog census")
    graph: list[dict] = []
    non_access: list[dict] = []
    intervals: dict[int, list[tuple[int, int, str]]] = {ordinal: [] for ordinal in range(2, 7)}
    for source in tensors:
        if type(source) is not dict:
            raise ValueError("catalog tensor type")
        ordinal = SHARD_ORDINAL.get(source.get("file"))
        length = _byte_length(source)
        offset = source.get("data_offset_abs")
        record = {
            "name": source.get("name"), "semantic_role": "GRAPH" if GRAPH.fullmatch(source.get("name", "")) else "NON_ACCESS",
            "layer": int(source["name"].split(".")[1]) if source["name"].startswith("blk.") else None,
            "expert_axis": source["dims"][2] if len(source["dims"]) > 2 else None,
            "format": source.get("type"), "shape": source.get("dims"), "shard_ordinal": ordinal,
            "byte_offset": offset, "byte_length": length, "decoder": source.get("type"),
            "primary_consumer_use": bool(GRAPH.fullmatch(source.get("name", ""))),
            "secondary_consumer_use": bool(GRAPH.fullmatch(source.get("name", ""))),
        }
        if record["semantic_role"] == "GRAPH":
            if ordinal not in range(2, 7) or type(offset) is not int or offset < 0:
                raise ValueError("graph tensor shard or offset")
            if offset + length > shard_sizes[ordinal]:
                raise ValueError("graph tensor exceeds production shard")
            intervals[ordinal].append((offset, offset + length, source["name"]))
            graph.append(record)
        else:
            non_access.append(record)
    if len(graph) != 1410 or len(non_access) != 399:
        raise ValueError("graph/non-access census")
    for ordinal, values in intervals.items():
        if not values:
            raise ValueError("unexercised graph shard")
        values.sort()
        for left, right in zip(values, values[1:]):
            if left[1] > right[0]:
                raise ValueError(f"tensor overlap: {ordinal}:{left[2]}:{right[2]}")
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-production-tensor-plan/9.0.0",
        "catalog_path": str(catalog_path.relative_to(ROOT)),
        "catalog_sha256": hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
        "checkpoint_metadata_path": str(CHECKPOINT_METADATA.relative_to(ROOT)),
        "checkpoint_metadata_sha256": hashlib.sha256(CHECKPOINT_METADATA.read_bytes()).hexdigest(),
        "graph_shard_size_bytes": {str(ordinal): shard_sizes[ordinal] for ordinal in range(2, 7)},
        "graph_tensors": graph,
        "non_access_tensors": non_access,
        "graph_tensor_count": len(graph), "non_access_tensor_count": len(non_access),
        "graph_shards": sorted(ordinal for ordinal, values in intervals.items() if values),
        "formats": sorted({item["format"] for item in graph}), "overlap_count": 0,
        "result": "PASS",
    }


def validate_plan(plan: dict) -> dict:
    if type(plan) is not dict or plan.get("result") != "PASS":
        raise ValueError("tensor plan")
    if plan.get("graph_tensor_count") != 1410 or len(plan.get("graph_tensors", [])) != 1410:
        raise ValueError("graph tensor plan census")
    if plan.get("non_access_tensor_count") != 399 or len(plan.get("non_access_tensors", [])) != 399:
        raise ValueError("non-access tensor plan census")
    if plan.get("graph_shards") != [2, 3, 4, 5, 6] or plan.get("overlap_count") != 0:
        raise ValueError("tensor plan shard coverage")
    sizes = plan.get("graph_shard_size_bytes")
    if type(sizes) is not dict or set(sizes) != {"2", "3", "4", "5", "6"} or any(type(value) is not int or value <= 0 for value in sizes.values()):
        raise ValueError("tensor plan shard-size authority")
    if any(item["semantic_role"] != "GRAPH" or item["shard_ordinal"] not in range(2, 7) for item in plan["graph_tensors"]):
        raise ValueError("graph plan role")
    if any(item["byte_offset"] + item["byte_length"] > sizes[str(item["shard_ordinal"])] for item in plan["graph_tensors"]):
        raise ValueError("graph plan bounds")
    if any(item["semantic_role"] != "NON_ACCESS" or item["primary_consumer_use"] or item["secondary_consumer_use"] for item in plan["non_access_tensors"]):
        raise ValueError("non-access plan role")
    return plan


if __name__ == "__main__":
    print(json.dumps(validate_plan(build_plan()), sort_keys=True, separators=(",", ":")))
