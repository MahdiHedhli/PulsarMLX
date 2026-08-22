#!/usr/bin/env python3
"""Metadata-only F017 checkpoint-plan audit.

This command reads only committed JSON authority. It never accepts or opens a
checkpoint root and therefore cannot consume original checkpoint payload.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


FORMAT = {
    "F32": (0, 1, 4),
    "Q2_K": (10, 256, 84),
    "Q3_K": (11, 256, 110),
    "Q4_K": (12, 256, 144),
    "Q5_K": (13, 256, 176),
    "Q6_K": (14, 256, 210),
    "Q8_0": (8, 32, 34),
    "IQ2_S": (22, 256, 82),
    "IQ2_XXS": (16, 256, 66),
    "IQ3_XXS": (18, 256, 98),
    "IQ4_XS": (23, 256, 136),
}


def strict_json(path: Path) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            if key in out:
                raise ValueError(f"duplicate JSON key {key!r} in {path}")
            out[key] = value
        return out

    value = json.loads(path.read_text(), object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise ValueError(f"top-level JSON object required: {path}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tensor_bytes(tensor: dict[str, Any]) -> int:
    name = tensor["name"]
    dims = tensor["dims"]
    fmt = tensor["type"]
    if fmt not in FORMAT:
        raise ValueError(f"{name}: unsupported format {fmt}")
    expected_id, block_values, block_bytes = FORMAT[fmt]
    if tensor["type_id"] != expected_id:
        raise ValueError(f"{name}: {fmt} type-ID mismatch")
    if not dims or any(type(value) is not int or isinstance(value, bool) or value <= 0 for value in dims):
        raise ValueError(f"{name}: invalid dimensions")
    columns = dims[0]
    if columns % block_values:
        raise ValueError(f"{name}: dimension 0 is not a complete {fmt} block census")
    rows = 1
    for value in dims[1:]:
        rows *= value
    return columns // block_values * block_bytes * rows


def audit(manifest: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    files = manifest["files"]
    tensors = catalog["tensors"]
    if manifest["file_count"] != 6 or len(files) != 6:
        raise ValueError("manifest must bind exactly six shards")
    if catalog["tensor_count"] != 1809 or len(tensors) != 1809:
        raise ValueError("catalog must bind exactly 1,809 tensors")
    if catalog["shard_count"] != 6 or catalog["architecture"] != "glm-dsa":
        raise ValueError("catalog architecture/shard census mismatch")
    file_sizes = {item["filename"]: item["size_bytes"] for item in files}
    if len(file_sizes) != 6 or any(len(item["sha256"]) != 64 for item in files):
        raise ValueError("duplicate or invalid shard identity")
    if sum(file_sizes.values()) != manifest["total_bytes"]:
        raise ValueError("manifest total byte census mismatch")

    names: set[str] = set()
    intervals: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    formats: Counter[str] = Counter()
    layers: set[int] = set()
    expert_tensor_count = 0
    for tensor in tensors:
        name = tensor["name"]
        if name in names:
            raise ValueError(f"duplicate logical tensor {name}")
        names.add(name)
        if tensor["file"] not in file_sizes:
            raise ValueError(f"{name}: unknown shard")
        offset = tensor["data_offset_abs"]
        if type(offset) is not int or isinstance(offset, bool) or offset < 0 or offset % 32:
            raise ValueError(f"{name}: invalid absolute offset/alignment")
        size = tensor_bytes(tensor)
        end = offset + size
        if end > file_sizes[tensor["file"]]:
            raise ValueError(f"{name}: tensor range exceeds shard")
        intervals[tensor["file"]].append((offset, end, name))
        formats[tensor["type"]] += 1
        if name.startswith("blk."):
            parts = name.split(".")
            if len(parts) < 3 or not parts[1].isdigit():
                raise ValueError(f"{name}: malformed layer name")
            layers.add(int(parts[1]))
        if "_exps.weight" in name:
            if len(tensor["dims"]) != 3 or tensor["dims"][2] != 256:
                raise ValueError(f"{name}: expert-axis census mismatch")
            expert_tensor_count += 1

    for filename, ranges in intervals.items():
        prior_end = 0
        prior_name = ""
        for start, end, name in sorted(ranges):
            if start < prior_end:
                raise ValueError(
                    f"{filename}: overlapping tensors {prior_name!r} and {name!r}"
                )
            prior_end, prior_name = end, name
    if layers != set(range(79)):
        raise ValueError("layer census is not exactly 0..78")
    for required in ("token_embd.weight", "output_norm.weight", "output.weight"):
        if required not in names:
            raise ValueError(f"missing terminal tensor {required}")
    if set(formats) != set(FORMAT):
        raise ValueError("11-format census mismatch")

    selected = catalog["kv_selected"]
    first_expert_layer = min(
        int(name.split(".")[1]) for name in names if "_exps.weight" in name
    )
    architecture = {
        "hidden_size": selected["embedding_length"],
        "vocabulary_size": selected["vocab_size"],
        "leading_dense_layers": first_expert_layer,
        "expert_top_k": selected["expert_used_count"],
        "dense_intermediate_size": selected["feed_forward_length"],
        "expert_intermediate_size": selected["expert_feed_forward_length"],
        "attention_head_count": selected["attention.head_count"],
        "query_rank": selected["attention.q_lora_rank"],
        "kv_rank": selected["attention.kv_lora_rank"],
        "qk_nope_dimension": selected["attention.key_length_mla"]
        - selected["rope.dimension_count"],
        "qk_rope_dimension": selected["rope.dimension_count"],
        "value_dimension": selected["attention.value_length_mla"],
    }
    expected_architecture = {
        "hidden_size": 6144,
        "vocabulary_size": 154880,
        "leading_dense_layers": 3,
        "expert_top_k": 8,
        "dense_intermediate_size": 12288,
        "expert_intermediate_size": 2048,
        "attention_head_count": 64,
        "query_rank": 2048,
        "kv_rank": 512,
        "qk_nope_dimension": 192,
        "qk_rope_dimension": 64,
        "value_dimension": 256,
    }
    if architecture != expected_architecture:
        raise ValueError("model architecture differs from native graph constants")

    return {
        "schema": "pulsarmlx.f017.native-bounded-p1-metadata-plan-audit/1.0.0",
        "status": "PASS",
        "tensor_count": len(tensors),
        "layer_count": len(layers),
        "expert_count": 256,
        "expert_tensor_count": expert_tensor_count,
        "shard_count": len(files),
        "model_architecture": architecture,
        "model_architecture_derivation": "catalog.kv_selected plus first _exps.weight layer",
        "quant_formats": dict(sorted(formats.items())),
        "alignment_bytes": 32,
        "overlap_count": 0,
        "duplicate_tensor_count": 0,
        "unknown_format_count": 0,
        "checkpoint_shard_opens": 0,
        "checkpoint_payload_reads": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest = strict_json(args.manifest)
    catalog = strict_json(args.catalog)
    result = audit(manifest, catalog)
    result["manifest"] = {"path": str(args.manifest), "sha256": sha256(args.manifest)}
    result["catalog"] = {"path": str(args.catalog), "sha256": sha256(args.catalog)}
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
