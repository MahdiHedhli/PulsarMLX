#!/usr/bin/env python3
"""Derive the post-IQ3 bottleneck and reuse decision from committed records."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "docs/research/glm52/raw"
DEFAULT_JSON = RAW / "post-f018-bottleneck-ranking-0001.json"
DEFAULT_TABLE = ROOT / "docs/research/glm52/tables/post-f018-bottleneck-ranking-0001.md"
INPUTS = {
    "layer3": RAW / "post-f018-iq2-iq3-complete-layer3-profile-0001.json",
    "dense": RAW / "post-f018-dense-multilayer-profile-0001.json",
    "output": RAW / "post-f018-output-head-profile-0001.json",
    "q4_reuse": RAW / "post-f018-output-q4-residency-0001.json",
    "q5_reuse": RAW / "post-f018-late-attention-q5-residency-0001.json",
    "q6_reuse": RAW / "post-f016-trunk-q6-residency-0001.json",
    "p1": RAW / "f018-inference-p1-direct-iq2-iq3-0001.json",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _median(summary: dict) -> float:
    return float(summary["median_seconds"])


def _candidate(record: dict, name: str) -> dict:
    return next(candidate for candidate in record["candidates"] if candidate["candidate"] == name)


def derive() -> dict:
    records = {name: json.loads(path.read_text()) for name, path in INPUTS.items()}
    if any(record["actual_status"] != "passed" for record in records.values()):
        raise ValueError("every source record must have passed")
    layer = records["layer3"]["direct_summaries"]
    dense = records["dense"]
    output = records["output"]
    q4 = records["q4_reuse"]
    q5 = records["q5_reuse"]
    q6 = records["q6_reuse"]
    p1 = records["p1"]
    warm = p1["timings"][1]

    dense_layers = []
    tensor_hotspots = []
    for layer_record in dense["layers"]:
        dense_layers.append(
            {
                "layer": int(layer_record["layer"]),
                "mla_wall_median_seconds": _median(layer_record["candidate_summaries"]["wall_seconds"]),
                "dense_attributed_median_seconds": _median(layer_record["candidate_summaries"]["dense_attributed_seconds"]),
                "orchestration_other_median_seconds": _median(layer_record["candidate_summaries"]["orchestration_other_seconds"]),
            }
        )
        for tensor in layer_record["tensor_summaries"]:
            tensor_hotspots.append(
                {
                    "layer": int(layer_record["layer"]),
                    "tensor": tensor["tensor"],
                    "quantization": tensor["quantization"],
                    "shape_rows_cols_per_slice": tensor["shape_rows_cols_per_slice"],
                    "slice_count": int(tensor["slice_count"]),
                    "compressed_bytes": int(tensor["encoded_bytes_per_use"]),
                    "total_median_seconds": _median(tensor["summaries"]["total_seconds"]),
                    "dequant_median_seconds": _median(tensor["summaries"]["dequant_seconds"]),
                    "build_median_seconds": _median(tensor["summaries"]["mlx_matrix_build_seconds"]),
                    "matvec_median_seconds": _median(tensor["summaries"]["mlx_matvec_seconds"]),
                    "storage_median_seconds": _median(tensor["summaries"]["storage_read_seconds"]),
                }
            )
    tensor_hotspots.sort(key=lambda row: row["total_median_seconds"], reverse=True)

    p1_layers = sorted(
        (
            {
                "layer": int(item["layer"]),
                "seconds": float(item["seconds"]),
                "cache_hits": int(item["cache_delta"]["decoded_cache_hits"]),
                "cache_misses": int(item["cache_delta"]["decoded_cache_misses"]),
            }
            for item in warm["layers"]
        ),
        key=lambda row: row["seconds"],
        reverse=True,
    )

    q4_host = _candidate(q4, "decoded_host_rebuild")
    q4_ready = _candidate(q4, "mlx_ready")
    q5_transient = _candidate(q5, "transient")
    q5_host = _candidate(q5, "decoded_host_rebuild")
    q5_ready = _candidate(q5, "mlx_ready")
    q6_transient = _candidate(q6, "transient")
    q6_ready = _candidate(q6, "decoded_hot")
    reuse = [
        {
            "tensor": "output.weight",
            "quantization": "Q4_K",
            "decoded_f32_bytes": int(output["binding"]["decoded_f32_bytes"]),
            "transient_median_seconds": _median(output["summaries"]["total_seconds"]),
            "host_rebuild_median_seconds": _median(q4_host["summaries"]["total_seconds"]),
            "native_ready_median_seconds": _median(q4_ready["summaries"]["total_seconds"]),
            "native_ready_setup_seconds": float(q4_ready["setup"]["total_seconds"]),
            "native_ready_rss_delta_bytes": int(q4_ready["setup_rss_delta_bytes"]),
            "peak_rss_bytes": int(q4_ready["resource_after_setup"]["peak_rss_bytes"]),
            "pressure": q4_ready["resource_after_setup"]["level"],
        },
        {
            "tensor": "blk.78.attn_output.weight",
            "quantization": "Q5_K",
            "decoded_f32_bytes": 402_653_184,
            "transient_median_seconds": _median(q5_transient["summaries"]["total_seconds"]),
            "host_rebuild_median_seconds": _median(q5_host["summaries"]["total_seconds"]),
            "native_ready_median_seconds": _median(q5_ready["summaries"]["total_seconds"]),
            "native_ready_setup_seconds": float(q5_ready["setup"]["total_seconds"]),
            "native_ready_rss_delta_bytes": int(q5_ready["setup_rss_delta_bytes"]),
            "peak_rss_bytes": int(q5_ready["resource_after_setup"]["peak_rss_bytes"]),
            "pressure": q5_ready["resource_after_setup"]["level"],
        },
        {
            "tensor": "blk.8.attn_output.weight",
            "quantization": "Q6_K",
            "decoded_f32_bytes": int(q6_transient["tensor"]["decoded_f32_bytes"]),
            "transient_median_seconds": _median(q6_transient["summaries"]["total_seconds"]),
            "host_rebuild_median_seconds": None,
            "native_ready_median_seconds": _median(q6_ready["summaries"]["total_seconds"]),
            "native_ready_setup_seconds": sum(
                float(q6_ready["setup"][field])
                for field in ("storage_read_seconds", "dequant_seconds", "mlx_matrix_build_seconds")
            ),
            "native_ready_rss_delta_bytes": int(q6_ready["setup_rss_delta_bytes"]),
            "peak_rss_bytes": int(q6_ready["pressure_after_setup"]["peak_rss_bytes"]),
            "pressure": q6_ready["pressure_after_setup"]["level"],
        },
    ]

    layer_summary = layer["layer"]
    moe_summary = layer["moe"]
    ranking = [
        {
            "rank": 1,
            "operation": "full-vocabulary output.weight",
            "scope": "one logits matrix boundary",
            "absolute_seconds": _median(output["summaries"]["total_seconds"]),
            "current_path": "Q4_K scalar decode -> f32 materialization -> MLX import -> matvec",
            "likely_optimization_class": "reuse/residency",
        },
        {
            "rank": 2,
            "operation": "complete layer 78",
            "scope": "one exact P1 warm-stack layer",
            "absolute_seconds": p1_layers[0]["seconds"],
            "current_path": "dense MLA plus intentional reference experts",
            "likely_optimization_class": "distributed; profile format-specific references before a kernel",
        },
        {
            "rank": 3,
            "operation": "complete layer 8",
            "scope": "one exact P1 warm-stack layer",
            "absolute_seconds": next(row["seconds"] for row in p1_layers if row["layer"] == 8),
            "current_path": "Q6_K dense MLA plus IQ2_S/IQ4_XS reference experts",
            "likely_optimization_class": "mixed dense reuse and explicit-reference formats",
        },
        {
            "rank": 4,
            "operation": "blk.8.attn_output.weight",
            "scope": "one dense matrix boundary",
            "absolute_seconds": next(row["total_median_seconds"] for row in tensor_hotspots if row["tensor"] == "blk.8.attn_output.weight"),
            "current_path": "Q6_K NumPy decode -> f32 MLX",
            "likely_optimization_class": "reuse/residency, subject to bounded hot-set admission",
        },
        {
            "rank": 5,
            "operation": "layer 3 attention/MLA",
            "scope": "one complete-layer sub-boundary",
            "absolute_seconds": _median(layer_summary["attention_seconds"]),
            "current_path": "vectorized dense decode -> f32 MLX",
            "likely_optimization_class": "vectorized decode or bounded reuse",
        },
        {
            "rank": 6,
            "operation": "blk.78.attn_output.weight",
            "scope": "one dense matrix boundary",
            "absolute_seconds": _median(q5_transient["summaries"]["total_seconds"]),
            "current_path": "Q5_K NumPy decode -> f32 MLX",
            "likely_optimization_class": "reuse/residency, but all-layer retention is unsafe",
        },
    ]
    return {
        "schema": "pulsarmlx.research.post-f018-bottleneck-ranking",
        "schema_version": "1.0.0",
        "actual_status": "passed",
        "inputs": [
            {"name": name, "path": str(path.relative_to(ROOT)), "sha256": _sha(path)}
            for name, path in INPUTS.items()
        ],
        "complete_layer3": {
            "total_median_seconds": _median(layer_summary["total_seconds"]),
            "total_standard_deviation_seconds": float(layer_summary["total_seconds"]["standard_deviation_seconds"]),
            "attention_median_seconds": _median(layer_summary["attention_seconds"]),
            "moe_median_seconds": _median(layer_summary["moe_seconds"]),
            "boundary_overhead_median_seconds": _median(layer_summary["boundary_overhead_seconds"]),
            "dense_nested": {
                field: _median(layer_summary[field])
                for field in (
                    "dense_storage_seconds",
                    "dense_dequant_seconds",
                    "dense_buffer_seconds",
                    "dense_build_seconds",
                    "dense_matvec_seconds",
                )
            },
            "moe_nested": {
                "router_seconds": _median(moe_summary["router_seconds"]),
                "iq2_total_seconds": _median(moe_summary["direct_iq2.total_seconds"]),
                "iq3_total_seconds": _median(moe_summary["direct_iq3.total_seconds"]),
                "shared_seconds": _median(moe_summary["shared_reference.total_seconds"]),
                "activation_seconds": _median(moe_summary["routed_activation_seconds"]),
                "aggregation_seconds": _median(moe_summary["routed_aggregation_seconds"]),
            },
            "classification": records["layer3"]["classification"],
        },
        "dense_layers": dense_layers,
        "top_dense_tensors": tensor_hotspots[:12],
        "p1_warm": {
            "stack_seconds": float(warm["stack_seconds"]),
            "logits_seconds": float(warm["logits_seconds"]),
            "top_layers": p1_layers[:10],
            "direct_routed_expert_count": int(p1["direct_quantized_metal"]["selection"]["direct_routed_expert_count"]),
            "explicit_reference_routed_expert_count": int(p1["direct_quantized_metal"]["selection"]["explicit_reference_routed_expert_count"]),
            "fallback_count": int(p1["direct_quantized_metal"]["selection"]["fallback_count"]),
        },
        "reuse": reuse,
        "ranking": ranking,
        "decision": {
            "outcome": "B",
            "selected_target": "decoded/native-ready output-head residency with bounded admission",
            "third_kernel_admitted": False,
            "fresh_p1_run": False,
            "reason": "The exact output boundary is token-scale and setup-dominated, while measured MLX-ready reuse preserves the output hash and reduces repeated use to milliseconds under normal pressure. This measured lower-risk target precedes a Q4_K direct kernel.",
            "next_experiment": "Host output.weight as one identity-bound native-ready resident entry, run exact final-logits fixtures, then one clean P1 only if the bounded runtime integration passes.",
        },
        "caveats": [
            "Ranked scopes overlap and must not be summed.",
            "The P1 warm stack and logits are single exact-run observations; matrix populations use ten measured samples.",
            "MLX-ready output residency has a large one-time scalar-decode setup and measured RSS above logical f32 bytes.",
            "All-layer decoded attention residency remains unsafe; individual matrix reuse does not admit that policy.",
            "No third direct-quantized kernel, P2, or golden-eight run was executed.",
        ],
    }


def render(record: dict) -> str:
    layer = record["complete_layer3"]
    lines = [
        "# Post-IQ3 bottleneck ranking",
        "",
        "> Scopes overlap and are not additive. Matrix and bounded-layer medians are separated from the single exact P1 warm-stack observation.",
        "",
        "## Complete layer 3",
        "",
        f"Median `{layer['total_median_seconds']:.6f}` s (sample stddev `{layer['total_standard_deviation_seconds']:.6f}` s): attention/MLA `{layer['attention_median_seconds']:.6f}` s, MoE `{layer['moe_median_seconds']:.6f}` s, and boundary/orchestration `{layer['boundary_overhead_median_seconds']:.6f}` s.",
        "",
        "## Ranked measured boundaries",
        "",
        "| Rank | Operation | Scope | Seconds | Current path | Likely class |",
        "| ---: | --- | --- | ---: | --- | --- |",
    ]
    lines.extend(
        f"| {row['rank']} | `{row['operation']}` | {row['scope']} | {row['absolute_seconds']:.6f} | {row['current_path']} | {row['likely_optimization_class']} |"
        for row in record["ranking"]
    )
    lines.extend(
        [
            "",
            "## Dense residency/reuse",
            "",
            "| Tensor | Quant | Decoded GiB | Transient (s) | Host rebuild (s) | MLX-ready (s) | RSS delta GiB | Pressure |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in record["reuse"]:
        host = "—" if row["host_rebuild_median_seconds"] is None else f"{row['host_rebuild_median_seconds']:.6f}"
        lines.append(
            f"| `{row['tensor']}` | {row['quantization']} | {row['decoded_f32_bytes'] / 2**30:.3f} | "
            f"{row['transient_median_seconds']:.6f} | {host} | {row['native_ready_median_seconds']:.6f} | "
            f"{row['native_ready_rss_delta_bytes'] / 2**30:.3f} | {row['pressure']} |"
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"Outcome **{record['decision']['outcome']}**: {record['decision']['selected_target']}.",
            "",
            record["decision"]["reason"],
            "",
            f"Next experiment: {record['decision']['next_experiment']}",
            "",
            "No fresh P1, P2, golden-eight run, or third kernel was started.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    record = derive()
    raw = json.dumps(record, indent=2, sort_keys=True) + "\n"
    table = render(record)
    if args.check:
        if args.json.read_text() != raw or args.table.read_text() != table:
            raise SystemExit("post-IQ3 bottleneck artifacts differ")
    else:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.table.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(raw)
        args.table.write_text(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
