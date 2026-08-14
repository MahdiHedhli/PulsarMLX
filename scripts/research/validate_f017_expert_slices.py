#!/usr/bin/env python3
"""Independently derive per-expert gate/up/down slices from aggregate metadata."""

from __future__ import annotations

import json
from pathlib import Path


CATALOG = "docs/research/glm52/raw/f016-c01-catalog-0001.json"
BLOCK_LAYOUT = {"IQ2_XXS": (256, 66), "IQ3_XXS": (256, 98)}


def aggregate_metadata(root: Path) -> dict[str, object]:
    catalog = json.loads((root / CATALOG).read_text())
    by_name = {item["name"]: item for item in catalog["tensors"]}
    projections = {}
    for role in ("gate", "up", "down"):
        name = f"blk.3.ffn_{role}_exps.weight"
        item = by_name[name]
        block_elements, block_bytes = BLOCK_LAYOUT[item["type"]]
        elements_per_expert = int(item["dims"][0]) * int(item["dims"][1])
        if elements_per_expert % block_elements:
            raise ValueError("quant block alignment")
        projections[role] = {
            "name": name,
            "base": int(item["data_offset_abs"]),
            "stride": elements_per_expert // block_elements * block_bytes,
            "quantization": item["type"],
            "dims": item["dims"],
            "shard": item["file"],
            "quant_block_elements": block_elements,
            "quant_block_bytes": block_bytes,
        }
    return {
        "expert_count": 256,
        "indexing": "zero_based",
        "layout": "projection_major_then_expert_major",
        "catalog": CATALOG,
        "projections": projections,
    }


def derive_triplet(metadata: dict[str, object], expert_id: int) -> dict[str, dict[str, object]]:
    count = int(metadata["expert_count"])
    if not 0 <= expert_id < count:
        raise ValueError(f"expert id {expert_id} outside [0,{count})")
    projections = metadata["projections"]
    assert isinstance(projections, dict)
    result = {}
    for role, raw in projections.items():
        assert isinstance(raw, dict)
        base, stride = int(raw["base"]), int(raw["stride"])
        start = base + expert_id * stride
        end = start + stride
        if start < base or end <= start:
            raise ValueError("expert slice arithmetic overflow")
        result[str(role)] = {"start": start, "end": end, "packed_length": stride,
                             "quantization": raw["quantization"], "expert_id": expert_id,
                             "aggregate_name": raw["name"], "shard": raw["shard"],
                             "quant_block_aligned": stride % int(raw["quant_block_bytes"]) == 0}
    return result
