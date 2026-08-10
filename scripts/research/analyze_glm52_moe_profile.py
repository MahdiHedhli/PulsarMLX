#!/usr/bin/env python3
"""Derive deterministic individual-expert attribution from the bounded MoE profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs/research/glm52/raw/post-f016-moe-stage-profile-0001.json"
JSON_OUT = ROOT / "docs/research/glm52/raw/post-f016-moe-stage-analysis-0001.json"
TABLE_OUT = ROOT / "docs/research/glm52/tables/post-f016-moe-stage-analysis-0001.md"
MATRIX_FIELDS = (
    "storage_read_seconds",
    "dequant_seconds",
    "contiguous_buffer_seconds",
    "mlx_matrix_construct_seconds",
    "mlx_matrix_eval_seconds",
    "mlx_matvec_seconds",
    "cleanup_seconds",
)


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def _percentile_type7(ordered: list[float], probability: float) -> float:
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (position - low) * (ordered[high] - ordered[low])


def _summary(values: Iterable[float]) -> dict[str, float | int]:
    ordered = sorted(float(value) for value in values)
    if not ordered or any(not math.isfinite(value) or value < 0 for value in ordered):
        raise ValueError("timing population must be finite and non-negative")
    count = len(ordered)
    mean = sum(ordered) / count
    middle = count // 2
    median = ordered[middle] if count % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    variance = sum((value - mean) ** 2 for value in ordered) / (count - 1) if count > 1 else 0.0
    return {
        "sample_count": count,
        "mean_seconds": mean,
        "median_seconds": median,
        "sample_standard_deviation_seconds": math.sqrt(variance),
        "minimum_seconds": ordered[0],
        "maximum_seconds": ordered[-1],
        "p95_type7_seconds": _percentile_type7(ordered, 0.95),
    }


def _matrix_components(events: list[dict[str, Any]]) -> dict[str, float]:
    return {field: sum(float(event[field]) for event in events) for field in MATRIX_FIELDS}


def _expert_key(expert: dict[str, Any]) -> tuple[int, bool]:
    return int(expert["expert_id"]), bool(expert["shared"])


def _expert_record(layer: int, experts: list[dict[str, Any]]) -> dict[str, Any]:
    first = experts[0]
    key = _expert_key(first)
    if any(_expert_key(expert) != key for expert in experts):
        raise ValueError(f"layer {layer}: expert identity changed across samples")
    event_sets = [expert["matrix_events"] for expert in experts]
    if any([event["projection"] for event in events] != ["gate", "up", "down"] for events in event_sets):
        raise ValueError(f"layer {layer} expert {key[0]}: projection sequence changed")
    projections = []
    for index, projection in enumerate(("gate", "up", "down")):
        events = [event_set[index] for event_set in event_sets]
        identity = {
            field: events[0][field]
            for field in (
                "tensor_name", "projection", "quantization", "rows", "cols",
                "compressed_bytes", "decoded_f32_bytes", "decoder_mode", "cache_hit",
            )
        }
        if any(any(event[field] != value for field, value in identity.items()) for event in events):
            raise ValueError(f"layer {layer} expert {key[0]} {projection}: identity changed")
        projections.append(
            {
                **identity,
                "timings": {field: _summary(event[field] for event in events) for field in MATRIX_FIELDS},
                "storage_read_count": int(events[0]["storage_read_count"]),
            }
        )
    return {
        "layer": layer,
        "expert_id": key[0],
        "shared": key[1],
        "total_seconds": _summary(expert["total_seconds"] for expert in experts),
        "activation_swiglu_seconds": _summary(expert["activation_swiglu_seconds"] for expert in experts),
        "weighting_seconds": _summary(expert["weighting_seconds"] for expert in experts),
        "projections": projections,
    }


def _quant_sample(sample: dict[str, Any]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    experts = sample["detail"]["routed_experts"] + [sample["detail"]["shared_expert"]]
    for expert in experts:
        for event in expert["matrix_events"]:
            quant = event["quantization"]
            bucket = result.setdefault(quant, {field: 0.0 for field in MATRIX_FIELDS})
            for field in MATRIX_FIELDS:
                bucket[field] += float(event[field])
    return result


def build(source_bytes: bytes, source: dict[str, Any]) -> dict[str, Any]:
    if source.get("actual_status") != "passed" or source.get("source_dirty"):
        raise ValueError("source is not a clean passing record")
    if source.get("schema") != "pulsarmlx.research.glm52-moe-stage-profile":
        raise ValueError("unexpected source schema")
    if source.get("protocol", {}).get("layers") != [3, 8, 40, 78]:
        raise ValueError("bounded layer set changed")

    layers: list[dict[str, Any]] = []
    all_routed: list[dict[str, Any]] = []
    all_projections: list[dict[str, Any]] = []
    for layer_source in source["layers"]:
        samples = layer_source["measured"]
        if len(samples) != 10:
            raise ValueError("each layer must retain ten samples")
        layer = int(layer_source["layer"])
        routed_ids = [int(value) for value in layer_source["reference_route"]["expert_ids"]]
        routed = [
            _expert_record(layer, [sample["detail"]["routed_experts"][index] for sample in samples])
            for index in range(8)
        ]
        if [expert["expert_id"] for expert in routed] != routed_ids:
            raise ValueError(f"layer {layer}: timed expert order differs from route")
        shared = _expert_record(layer, [sample["detail"]["shared_expert"] for sample in samples])
        quant_samples = [_quant_sample(sample) for sample in samples]
        quantizations = sorted({quant for sample in quant_samples for quant in sample})
        quantization_rows = []
        for quant in quantizations:
            timings = {
                field: _summary(sample.get(quant, {}).get(field, 0.0) for sample in quant_samples)
                for field in MATRIX_FIELDS
            }
            attributed = [sum(sample.get(quant, {}).get(field, 0.0) for field in MATRIX_FIELDS) for sample in quant_samples]
            quantization_rows.append({"quantization": quant, "attributed_seconds": _summary(attributed), "timings": timings})
        quantization_rows.sort(key=lambda row: (-row["attributed_seconds"]["median_seconds"], row["quantization"]))
        routed_totals = [sum(expert["total_seconds"] for expert in sample["detail"]["routed_experts"]) for sample in samples]
        shared_totals = [float(sample["detail"]["shared_expert"]["total_seconds"]) for sample in samples]
        layer_record = {
            "layer": layer,
            "route": routed_ids,
            "boundary_total_seconds": _summary(sample["total_seconds"] for sample in samples),
            "routed_expert_total_seconds": _summary(routed_totals),
            "shared_expert_total_seconds": _summary(shared_totals),
            "activation_swiglu_seconds": _summary(sample["stage_totals"]["activation_swiglu_seconds"] for sample in samples),
            "weighting_seconds": _summary(sample["stage_totals"]["weighting_seconds"] for sample in samples),
            "router_projection_seconds": _summary(sample["stage_totals"]["router_projection_seconds"] for sample in samples),
            "router_selection_seconds": _summary(sample["stage_totals"]["router_selection_seconds"] for sample in samples),
            "routed_aggregation_seconds": _summary(sample["stage_totals"]["routed_aggregation_seconds"] for sample in samples),
            "shared_aggregation_seconds": _summary(sample["stage_totals"]["shared_aggregation_seconds"] for sample in samples),
            "uninstrumented_residual_seconds": _summary(sample["stage_totals"]["uninstrumented_residual_seconds"] for sample in samples),
            "routed_experts": routed,
            "shared_expert": shared,
            "quantization_ranking": quantization_rows,
        }
        layers.append(layer_record)
        all_routed.extend(routed)
        for expert in routed + [shared]:
            for projection in expert["projections"]:
                all_projections.append({"layer": layer, "expert_id": expert["expert_id"], "shared": expert["shared"], **projection})

    ranked_experts = sorted(all_routed, key=lambda item: (-item["total_seconds"]["median_seconds"], item["layer"], item["expert_id"]))
    top_experts = [
        {
            "rank": rank,
            "layer": expert["layer"],
            "expert_id": expert["expert_id"],
            "median_total_seconds": expert["total_seconds"]["median_seconds"],
            "quantizations": {projection["projection"]: projection["quantization"] for projection in expert["projections"]},
        }
        for rank, expert in enumerate(ranked_experts[:20], 1)
    ]
    ranked_projections = sorted(
        all_projections,
        key=lambda item: (-sum(item["timings"][field]["median_seconds"] for field in MATRIX_FIELDS), item["layer"], item["expert_id"], item["projection"]),
    )
    top_projections = []
    for rank, projection in enumerate(ranked_projections[:20], 1):
        components = {field: projection["timings"][field]["median_seconds"] for field in MATRIX_FIELDS}
        top_projections.append(
            {
                "rank": rank,
                "layer": projection["layer"],
                "expert_id": projection["expert_id"],
                "shared": projection["shared"],
                "projection": projection["projection"],
                "quantization": projection["quantization"],
                "shape": [projection["rows"], projection["cols"]],
                "median_attributed_seconds": sum(components.values()),
                "components": components,
            }
        )

    return {
        "schema": "pulsarmlx.research.glm52-moe-stage-analysis",
        "schema_version": "1.0.0",
        "actual_status": "passed",
        "source": {
            "record": "docs/research/glm52/raw/post-f016-moe-stage-profile-0001.json",
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
            "source_commit": source["source_commit"],
            "source_dirty": source["source_dirty"],
        },
        "scope": "four independent real-checkpoint MoE boundaries from layer-local MLA(token_embedding[9703], position=0); not sequential full-stack inference",
        "layers": layers,
        "top_20_routed_experts": top_experts,
        "top_20_matrix_projections": top_projections,
        "decision": {
            "dominant_stage": "scalar-reference dequantization for unsupported expert quantizations",
            "first_measured_candidates": ["Q2_K", "IQ2_S", "Q3_K", "IQ4_XS"],
            "first_candidate_reason": "layer 78 Q2_K gate/up has the largest measured per-layer decode opportunity; layer 8 IQ2_S is the next comparable boundary",
            "matrix_build_import_dominant": False,
            "matvec_dominant": False,
            "feature_018_kernel_selected": False,
        },
        "claim_boundary": "The profile establishes bounded per-expert and per-projection stage costs only. It is not P1/P2, token latency, or Metal evidence.",
    }


def render(record: dict[str, Any]) -> str:
    layer_lines = []
    quant_lines = []
    for layer in record["layers"]:
        layer_lines.append(
            f"| {layer['layer']} | {layer['boundary_total_seconds']['median_seconds']:.6f} | {layer['routed_expert_total_seconds']['median_seconds']:.6f} | {layer['shared_expert_total_seconds']['median_seconds']:.6f} | {layer['activation_swiglu_seconds']['median_seconds']:.6f} | {layer['uninstrumented_residual_seconds']['median_seconds']:.6f} |"
        )
        for row in layer["quantization_ranking"]:
            timings = row["timings"]
            quant_lines.append(
                f"| {layer['layer']} | {row['quantization']} | {row['attributed_seconds']['median_seconds']:.6f} | {timings['storage_read_seconds']['median_seconds']:.6f} | {timings['dequant_seconds']['median_seconds']:.6f} | {timings['contiguous_buffer_seconds']['median_seconds']:.6f} | {timings['mlx_matrix_construct_seconds']['median_seconds'] + timings['mlx_matrix_eval_seconds']['median_seconds']:.6f} | {timings['mlx_matvec_seconds']['median_seconds']:.6f} |"
            )
    expert_lines = [
        f"| {row['rank']} | {row['layer']} | {row['expert_id']} | `{row['quantizations']}` | {row['median_total_seconds']:.6f} |"
        for row in record["top_20_routed_experts"]
    ]
    projection_lines = [
        f"| {row['rank']} | {row['layer']} | {row['expert_id']} | {row['projection']} | {row['quantization']} | `{row['shape']}` | {row['median_attributed_seconds']:.6f} | {row['components']['dequant_seconds']:.6f} | {row['components']['contiguous_buffer_seconds']:.6f} | {row['components']['mlx_matvec_seconds']:.6f} |"
        for row in record["top_20_matrix_projections"]
    ]
    return "\n".join(
        [
            "# Bounded GLM-5.2 MoE stage analysis", "",
            f"Source execution commit: `{record['source']['source_commit']}`. Scope: {record['scope']}.", "",
            "## Layer decomposition", "",
            "| Layer | MoE boundary median (s) | Routed experts median (s) | Shared expert median (s) | SwiGLU median (s) | Uninstrumented residual median (s) |",
            "| ---: | ---: | ---: | ---: | ---: | ---: |", *layer_lines, "",
            "## Quantization stage medians", "",
            "| Layer | Quant | Attributed (s) | Read (s) | Decode (s) | Buffer (s) | MLX build/eval (s) | MLX matvec (s) |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |", *quant_lines, "",
            "## Top 20 routed experts", "",
            "| Rank | Layer | Expert | Gate/up/down quantization | Median total (s) |",
            "| ---: | ---: | ---: | --- | ---: |", *expert_lines, "",
            "## Top 20 matrix projections", "",
            "| Rank | Layer | Expert | Projection | Quant | Shape | Attributed (s) | Decode (s) | Buffer (s) | Matvec (s) |",
            "| ---: | ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: |", *projection_lines, "",
            "## Decision", "",
            "Scalar-reference dequantization for the unsupported expert formats dominates layers 8 and 78. MLX matrix build/import, matvec, SwiGLU, weighting, aggregation, and cleanup are not the dominant bounded costs. Q2_K is the first measured decoder candidate; this result does not select a direct-quantized Metal kernel.", "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--json-out", type=Path, default=JSON_OUT)
    parser.add_argument("--table-out", type=Path, default=TABLE_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source_bytes = args.source.read_bytes()
    source = json.loads(source_bytes, object_pairs_hook=_unique)
    record = build(source_bytes, source)
    json_text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    table_text = render(record)
    if args.check:
        if not args.json_out.exists() or args.json_out.read_text() != json_text:
            raise SystemExit(f"generated JSON is stale: {args.json_out}")
        if not args.table_out.exists() or args.table_out.read_text() != table_text:
            raise SystemExit(f"generated table is stale: {args.table_out}")
        print("bounded MoE stage analysis: passed")
        return 0
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.table_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json_text)
    args.table_out.write_text(table_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
