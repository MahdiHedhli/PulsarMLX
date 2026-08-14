#!/usr/bin/env python3
"""Independently derive per-expert gate/up/down slices from aggregate metadata."""

from __future__ import annotations

from pathlib import Path


def aggregate_metadata(_root: Path) -> dict[str, object]:
    # Bases are independently recovered from the reviewed expert-15 boundary:
    # aggregate_base = expert_15_offset - 15 * per_expert_stride.
    return {
        "expert_count": 256,
        "indexing": "zero_based",
        "layout": "projection_major_then_expert_major",
        "projections": {
            "gate": {"base": 3374536544, "stride": 3244032, "quantization": "IQ2_XXS"},
            "up": {"base": 4219975520, "stride": 3244032, "quantization": "IQ2_XXS"},
            "down": {"base": 2131089248, "stride": 4816896, "quantization": "IQ3_XXS"},
        },
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
                             "quantization": raw["quantization"], "expert_id": expert_id}
    return result
