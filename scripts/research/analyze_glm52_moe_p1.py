#!/usr/bin/env python3
"""Derive the maximum honest MoE attribution from the exact post-trunk P1."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

from glm52_tensor_store import nbytes_for_tensor

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs/research/glm52/raw/post-f016-inference-p1-trunk-q6-0001.json"
CATALOG = ROOT / "docs/research/glm52/raw/f016-c01-catalog-0001.json"
JSON_OUT = ROOT / "docs/research/glm52/raw/post-f016-p1-moe-attribution-0001.json"
TABLE_OUT = ROOT / "docs/research/glm52/tables/post-f016-p1-moe-attribution-0001.md"
COMPONENT_FIELDS = (
    "storage_read_seconds",
    "dequant_seconds",
    "contiguous_buffer_seconds",
    "mlx_matrix_build_seconds",
    "mlx_matvec_seconds",
)


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def _summary(values: Iterable[float]) -> dict[str, float | int]:
    samples = [float(value) for value in values]
    if not samples:
        raise ValueError("empty timing population")
    ordered = sorted(samples)
    count = len(ordered)
    middle = count // 2
    mean = sum(ordered) / count
    median = (
        ordered[middle]
        if count % 2
        else (ordered[middle - 1] + ordered[middle]) / 2.0
    )
    sample_variance = (
        sum((value - mean) ** 2 for value in ordered) / (count - 1)
        if count > 1
        else 0.0
    )
    return {
        "sample_count": count,
        "mean": mean,
        "median": median,
        "sample_standard_deviation": math.sqrt(sample_variance),
        "minimum": ordered[0],
        "maximum": ordered[-1],
        "p95_type7": _percentile_type7(ordered, 0.95),
    }


def _percentile_type7(ordered: list[float], probability: float) -> float:
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (position - low) * (ordered[high] - ordered[low])


def _layer_record(layer: dict[str, Any], route: dict[str, Any] | None) -> dict[str, Any]:
    delta = layer["cache_delta"]
    components = {field: float(delta[field]) for field in COMPONENT_FIELDS}
    attributed = sum(components.values())
    wall = float(layer["seconds"])
    residual = wall - attributed
    if residual < -1e-8:
        raise ValueError(f"layer {layer['layer']}: component sum exceeds wall")
    result: dict[str, Any] = {
        "layer": int(layer["layer"]),
        "layer_wall_seconds": wall,
        "expert_cache_components": components,
        "expert_cache_attributed_seconds": attributed,
        "uninstrumented_residual_seconds": max(0.0, residual),
        "decoded_cache_hits": int(delta["decoded_cache_hits"]),
        "decoded_cache_misses": int(delta["decoded_cache_misses"]),
        "transient_releases": int(delta["transient_releases"]),
        "storage_bytes_read": int(delta["storage_bytes_read"]),
        "decoded_bytes_materialized": int(delta["decoded_bytes_materialized"]),
        "storage_bytes_avoided": int(delta["storage_bytes_avoided"]),
        "decoded_bytes_avoided": int(delta["decoded_bytes_avoided"]),
        "mlx_matvec_count": int(delta["mlx_matvec_count"]),
    }
    if route is not None:
        result["routed_expert_ids"] = [int(value) for value in route["expert_ids"]]
        result["route_weights"] = [float(value) for value in route["weights"]]
        result["shared_expert_id"] = int(route["shared_expert"])
    return result


def _projection_inventory(layer: int, catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    inventory: dict[str, Any] = {"routed": {}, "shared": {}}
    for scope, suffix in (("routed", "exps"), ("shared", "shexp")):
        for projection in ("gate", "up", "down"):
            name = f"blk.{layer}.ffn_{projection}_{suffix}.weight"
            tensor = catalog.get(name)
            if tensor is None:
                raise ValueError(f"catalog is missing {name}")
            cols, rows = int(tensor["dims"][0]), int(tensor["dims"][1])
            inventory[scope][projection] = {
                "tensor_name": name,
                "quantization": tensor["type"],
                "shape": [rows, cols],
                "compressed_bytes_per_expert_matrix": nbytes_for_tensor(int(tensor["type_id"]), cols) * rows,
                "decoded_f32_bytes_per_expert_matrix": rows * cols * 4,
            }
    return inventory


def build(
    source_bytes: bytes,
    source: dict[str, Any],
    catalog_bytes: bytes,
    catalog_document: dict[str, Any],
) -> dict[str, Any]:
    if source.get("actual_status") != "passed" or source.get("source_dirty"):
        raise ValueError("P1 source is not a clean passing record")
    if source.get("source_commit") != "9b6ab666c9dc89eda9b2ddf284a9a2767516d87e":
        raise ValueError("P1 source commit changed")
    if source.get("generated_token_ids") != [9703, 21615]:
        raise ValueError("P1 exact prefix changed")
    timings = source.get("timings", [])
    routing = source.get("routing", [])
    if len(timings) != 2 or len(routing) != 2:
        raise ValueError("P1 must retain exactly two stacks")
    if any(len(stack["layers"]) != 79 for stack in timings):
        raise ValueError("P1 stack depth changed")
    if any(len(stack["layers"]) != 76 for stack in routing):
        raise ValueError("P1 MoE routing depth changed")
    if catalog_document.get("actual_status") != "passed" or catalog_document.get("tensor_count") != 1809:
        raise ValueError("catalog identity changed")
    catalog = {tensor["name"]: tensor for tensor in catalog_document["tensors"]}

    stacks: dict[str, Any] = {}
    for timing, route_stack, label in zip(timings, routing, ("cold", "warm"), strict=True):
        route_by_layer = {int(route["layer"]): route for route in route_stack["layers"]}
        layers = [
            _layer_record(layer, route_by_layer.get(int(layer["layer"])))
            for layer in timing["layers"]
        ]
        for layer in layers:
            if layer["layer"] >= 3:
                layer["projection_inventory"] = _projection_inventory(layer["layer"], catalog)
        moe = [layer for layer in layers if layer["layer"] >= 3]
        stacks[label] = {
            "stack_wall_seconds": float(timing["stack_seconds"]),
            "resource_level": timing["resource_after"]["level"],
            "all_layers": layers,
            "moe_layer_wall_summary": _summary(layer["layer_wall_seconds"] for layer in moe),
            "moe_expert_cache_attributed_summary": _summary(
                layer["expert_cache_attributed_seconds"] for layer in moe
            ),
            "moe_layer_wall_total_seconds": sum(layer["layer_wall_seconds"] for layer in moe),
            "expert_cache_attributed_total_seconds": sum(
                layer["expert_cache_attributed_seconds"] for layer in moe
            ),
            "uninstrumented_residual_total_seconds": sum(
                layer["uninstrumented_residual_seconds"] for layer in layers
            ),
        }

    warm_moe = [layer for layer in stacks["warm"]["all_layers"] if layer["layer"] >= 3]
    if any(
        layer["decoded_cache_hits"] != 3
        or layer["decoded_cache_misses"] != 24
        or layer["transient_releases"] != 24
        or layer["mlx_matvec_count"] != 27
        for layer in warm_moe
    ):
        raise ValueError("warm shared/routed lifecycle contract changed")

    top_sets = sorted(
        warm_moe,
        key=lambda layer: (-layer["expert_cache_attributed_seconds"], layer["layer"]),
    )[:20]
    top_sets = [
        {
            "rank": rank,
            "layer": layer["layer"],
            "routed_expert_ids": layer["routed_expert_ids"],
            "expert_cache_attributed_seconds": layer["expert_cache_attributed_seconds"],
            "layer_wall_seconds": layer["layer_wall_seconds"],
            "components": layer["expert_cache_components"],
            "routed_projection_quantization": {
                projection: details["quantization"]
                for projection, details in layer["projection_inventory"]["routed"].items()
            },
        }
        for rank, layer in enumerate(top_sets, 1)
    ]

    quant_rows = []
    for quantization, metrics in source["expert_cache"]["quantization_metrics"].items():
        component_seconds = sum(float(metrics[field]) for field in COMPONENT_FIELDS)
        quant_rows.append(
            {
                "quantization": quantization,
                "component_seconds": component_seconds,
                **{field: metrics[field] for field in metrics},
            }
        )
    quant_rows.sort(key=lambda row: (-row["component_seconds"], row["quantization"]))
    for rank, row in enumerate(quant_rows, 1):
        row["rank"] = rank

    warm_components = {
        field: sum(layer["expert_cache_components"][field] for layer in warm_moe)
        for field in COMPONENT_FIELDS
    }
    warm_components["attributed_total_seconds"] = sum(warm_components.values())
    return {
        "schema": "pulsarmlx.research.glm52-p1-moe-attribution",
        "schema_version": "1.0.0",
        "actual_status": "passed",
        "source": {
            "record": "docs/research/glm52/raw/post-f016-inference-p1-trunk-q6-0001.json",
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
            "source_commit": source["source_commit"],
            "source_dirty": source["source_dirty"],
            "catalog_record": "docs/research/glm52/raw/f016-c01-catalog-0001.json",
            "catalog_sha256": hashlib.sha256(catalog_bytes).hexdigest(),
        },
        "stacks": stacks,
        "warm_routed_shared_decomposition": {
            "routed_matrix_loads_per_moe_layer": 24,
            "shared_matrix_hits_per_moe_layer": 3,
            "routed_load_path_components": {
                key: warm_components[key]
                for key in (
                    "storage_read_seconds",
                    "dequant_seconds",
                    "contiguous_buffer_seconds",
                    "mlx_matrix_build_seconds",
                )
            },
            "combined_routed_and_shared_mlx_matvec_seconds": warm_components["mlx_matvec_seconds"],
            "combined_routed_and_shared_mlx_matvec_count": sum(
                layer["mlx_matvec_count"] for layer in warm_moe
            ),
            "expert_cache_attributed_total_seconds": warm_components["attributed_total_seconds"],
            "shared_decode_read_build_seconds": 0.0,
            "shared_decode_read_build_reason": "all three shared matrices per MoE layer were decoded-cache hits",
            "shared_vs_routed_matvec_split_available": False,
        },
        "top_20_routed_expert_sets_by_attributed_seconds": top_sets,
        "individual_expert_hotspot_status": {
            "available": False,
            "reason": "the P1 schema snapshots cache counters once per layer, after all eight routed experts and the shared expert",
            "safe_interpretation": "each ranked row is one complete layer's routed top-8 set plus shared matvec, not an individual expert ranking",
        },
        "run_total_quantization_ranking": {
            "scope": "cold plus warm expert-cache path combined; not a warm-only or per-expert ranking",
            "rows": quant_rows,
        },
        "unavailable_attribution": {
            "mla_trunk_vs_moe_wall": "not timed separately in the P1 schema",
            "per_expert": "not timed",
            "projection_gate_up_down": "not timed",
            "shared_vs_routed_matvec": "not timed",
            "activation_swiglu": "not timed",
            "route_weighting_aggregation": "not timed",
            "cleanup_sync": "not timed separately",
            "router": "not timed separately",
        },
        "next_bounded_timer_gate": [
            "one routed expert: gate/up/down read, decode, materialization, build, eval, matvec, activation, weighting, cleanup",
            "one shared expert in cold and retained-warm states",
            "one top-8 plus shared MoE block with router and aggregation timers",
            "one representative complete layer with MLA and MoE separated",
        ],
        "claim_boundary": (
            "This record decomposes only counters already committed by the exact P1. "
            "It performs no checkpoint access or model execution and does not select a Metal kernel."
        ),
    }


def render(record: dict[str, Any]) -> str:
    warm = record["stacks"]["warm"]
    split = record["warm_routed_shared_decomposition"]
    rows = record["top_20_routed_expert_sets_by_attributed_seconds"]
    quant = record["run_total_quantization_ranking"]["rows"]
    top_lines = [
        f"| {row['rank']} | {row['layer']} | `{row['routed_expert_ids']}` | `{row['routed_projection_quantization']}` | {row['expert_cache_attributed_seconds']:.6f} | {row['layer_wall_seconds']:.6f} |"
        for row in rows
    ]
    quant_lines = [
        f"| {row['rank']} | {row['quantization']} | {row['component_seconds']:.6f} | {row['dequant_seconds']:.6f} | {row['mlx_matrix_build_seconds']:.6f} | {row['mlx_matvec_seconds']:.6f} |"
        for row in quant
    ]
    return "\n".join(
        [
            "# Post-trunk P1 MoE attribution", "",
            f"Derived without model access from clean execution source `{record['source']['source_commit']}`.", "",
            "## Warm stack boundary", "",
            f"- Stack wall: {warm['stack_wall_seconds']:.6f} s",
            f"- MoE-layer wall total: {warm['moe_layer_wall_total_seconds']:.6f} s",
            f"- Expert-cache attributed total: {split['expert_cache_attributed_total_seconds']:.6f} s",
            f"- Uninstrumented all-layer residual: {warm['uninstrumented_residual_total_seconds']:.6f} s",
            f"- Routed loads per MoE layer: {split['routed_matrix_loads_per_moe_layer']}",
            f"- Shared decoded hits per MoE layer: {split['shared_matrix_hits_per_moe_layer']}", "",
            "All warm read, decode, materialization, and matrix-build time belongs to routed matrices because all shared matrices hit the decoded cache. MLX matvec time combines routed and shared work and cannot be split from this schema.", "",
            "## Top 20 routed expert sets", "",
            "These are complete layer top-8 sets ranked by expert-cache attributed time. They are **not individual-expert hotspots**.", "",
            "| Rank | Layer | Routed expert IDs | Gate/up/down quantization | Expert-cache attributed (s) | Complete layer wall (s) |",
            "| ---: | ---: | --- | --- | ---: | ---: |", *top_lines, "",
            "## Run-total expert quantization", "",
            "This table combines cold and warm expert-cache work. It is not a warm-only ranking.", "",
            "| Rank | Quant | Components (s) | Decode (s) | Build (s) | Matvec (s) |",
            "| ---: | --- | ---: | ---: | ---: | ---: |", *quant_lines, "",
            "## Visibility limit", "",
            "P1 does not time MLA versus MoE, individual experts, gate/up/down projections, shared versus routed matvec, SwiGLU, router, aggregation, or cleanup separately. The next bounded harness must add those timers before an individual hotspot or Feature 018 kernel can be selected.", "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--json-out", type=Path, default=JSON_OUT)
    parser.add_argument("--table-out", type=Path, default=TABLE_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source_bytes = args.source.read_bytes()
    source = json.loads(source_bytes, object_pairs_hook=_unique)
    catalog_bytes = args.catalog.read_bytes()
    catalog = json.loads(catalog_bytes, object_pairs_hook=_unique)
    record = build(source_bytes, source, catalog_bytes, catalog)
    json_text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    table_text = render(record)
    if args.check:
        if not args.json_out.exists() or args.json_out.read_text() != json_text:
            raise SystemExit(f"generated JSON is stale: {args.json_out}")
        if not args.table_out.exists() or args.table_out.read_text() != table_text:
            raise SystemExit(f"generated table is stale: {args.table_out}")
        print("P1 MoE attribution: passed")
        return 0
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.table_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json_text)
    args.table_out.write_text(table_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
