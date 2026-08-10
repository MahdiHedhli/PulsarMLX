#!/usr/bin/env python3
"""Generate deterministic review tables from Feature 018 raw evidence."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/research"))

from f018_evidence import load_unique_json, validate_record  # noqa: E402

DEFAULT_INPUT = ROOT / "docs/research/glm52/raw/f018-iq2-xxs-synthetic-0002.json"
DEFAULT_OUTPUT = ROOT / "docs/research/glm52/tables/f018-iq2-xxs-synthetic-0002.md"


def _render_routed_expert(record: dict, raw_sha256: str) -> str:
    binding = record["binding"]
    numerical = record["numerical_qualification"]
    reference = record["optimized_reference"]["summaries"]
    direct = record["direct_summaries"]
    process_first = record["process_first_direct"]["direct_iq2"]
    reference_total = reference["total_seconds"]["median_seconds"]
    direct_total = direct["total_seconds"]["median_seconds"]
    rows = [
        ("Current storage read", reference["storage_read_seconds"]["median_seconds"]),
        ("Current decode", reference["dequant_seconds"]["median_seconds"]),
        ("Current contiguous buffer", reference["contiguous_buffer_seconds"]["median_seconds"]),
        ("Current MLX build/eval", reference["mlx_matrix_build_eval_seconds"]["median_seconds"]),
        ("Current MLX matvec", reference["mlx_matvec_seconds"]["median_seconds"]),
        ("Current total", reference_total),
        ("Direct IQ2 gate/up storage (warm)", direct["direct_iq2.storage_read_seconds"]["median_seconds"]),
        ("Direct IQ2 gate/up registration", direct["direct_iq2.registration_seconds"]["median_seconds"]),
        ("Direct IQ2 gate/up GPU interval", direct["direct_iq2.kernel_seconds"]["median_seconds"]),
        ("Direct IQ2 gate/up synchronized total", direct["direct_iq2.total_seconds"]["median_seconds"]),
        ("Reference IQ3 down decode", direct["reference_down.dequant_seconds"]["median_seconds"]),
        ("Reference IQ3 down MLX build", direct["reference_down.mlx_matrix_build_seconds"]["median_seconds"]),
        ("Reference IQ3 down matvec", direct["reference_down.mlx_matvec_seconds"]["median_seconds"]),
        ("SwiGLU activation", direct["activation_swiglu_seconds"]["median_seconds"]),
        ("Direct candidate total", direct_total),
    ]
    return "\n".join(
        [
            "# Feature 018 complete routed-expert gate",
            "",
            "> One real routed expert only: direct IQ2_XXS gate/up plus the existing qualified IQ3_XXS reference down path.",
            "",
            f"- Source: `{record['source']['commit']}` (clean)",
            f"- Raw SHA-256: `{raw_sha256}`",
            f"- Checkpoint set: `{record['checkpoint']['checkpoint_set_sha256']}`",
            f"- Layer/expert: `{binding['layer']}` / `{binding['expert_id']}`; selected top-8 route: `{binding['route_expert_ids']}`",
            f"- Classification: `{record['classification']}`; elementwise mismatches: `{numerical['elementwise_mismatch_count']}`",
            f"- Max absolute error: `{numerical['maximum_absolute_error']:.9g}`; RMSE: `{numerical['rmse']:.9g}`; cosine: `{numerical['cosine_similarity']:.12f}`",
            f"- Rust worker: two stable page-aligned resident slots; process-first reads `{process_first['storage_read_count']}` / `{process_first['storage_bytes_read']}` bytes; warm hits `2` per sample; evictions `0`.",
            "",
            "| Component | Median (s) |",
            "| --- | ---: |",
            *(f"| {name} | {value:.9f} |" for name, value in rows),
            "",
            f"For this bounded expert, the current optimized-reference median is `{reference_total:.9f}` s and the direct-IQ2 candidate median is `{direct_total:.9f}` s (ratio `{reference_total / direct_total:.2f}×`; absolute difference `{reference_total - direct_total:.9f}` s).",
            "",
            "The largest retained candidate component is the reference IQ3_XXS down decode. This result does not select or implement a second kernel and is not a layer/model speedup claim.",
            "",
        ]
    )


def _render_moe(record: dict, raw_sha256: str) -> str:
    binding = record["binding"]
    numerical = record["numerical_qualification"]
    reference = record["optimized_reference"]["summaries"]
    direct = record["direct_summaries"]
    process_first = record["process_first_direct"]["direct_iq2"]
    reference_total = reference["total_seconds"]["median_seconds"]
    direct_total = direct["total_seconds"]["median_seconds"]
    rows = [
        ("Current decode", reference["dequant_seconds"]["median_seconds"]),
        ("Current MLX build/eval", reference["mlx_matrix_build_eval_seconds"]["median_seconds"]),
        ("Current MLX matvec", reference["mlx_matvec_seconds"]["median_seconds"]),
        ("Current total", reference_total),
        ("Direct routed IQ2 storage", direct["direct_iq2.storage_read_seconds"]["median_seconds"]),
        ("Direct routed IQ2 GPU interval", direct["direct_iq2.kernel_seconds"]["median_seconds"]),
        ("Direct routed IQ2 synchronized total", direct["direct_iq2.total_seconds"]["median_seconds"]),
        ("Reference routed IQ3 down decode", direct["routed_down_reference.dequant_seconds"]["median_seconds"]),
        ("Reference routed IQ3 down MLX build", direct["routed_down_reference.mlx_matrix_build_seconds"]["median_seconds"]),
        ("Reference routed IQ3 down matvec", direct["routed_down_reference.mlx_matvec_seconds"]["median_seconds"]),
        ("Router", direct["router_seconds"]["median_seconds"]),
        ("Shared reference expert", direct["shared_reference.total_seconds"]["median_seconds"]),
        ("Direct candidate total", direct_total),
    ]
    return "\n".join(
        [
            "# Feature 018 top-8 plus shared MoE gate",
            "",
            "> One real layer-3 MoE boundary only; routed IQ2_XXS gate/up is direct Metal while routed down and all shared-expert projections remain on qualified reference paths.",
            "",
            f"- Source: `{record['source']['commit']}` (clean)",
            f"- Raw SHA-256: `{raw_sha256}`",
            f"- Checkpoint set: `{record['checkpoint']['checkpoint_set_sha256']}`",
            f"- Top-8 route: `{binding['expert_ids']}`; shared expert: `{binding['shared_expert']}`",
            f"- Current reference hash matches committed Feature 016 evidence: `{str(binding['historical_reference_hash_match']).lower()}`",
            f"- Classification: `{record['classification']}`; tolerance mismatches: `{numerical['elementwise_mismatch_count']}`; max absolute error: `{numerical['maximum_absolute_error']:.9g}`",
            f"- Direct worker process-first: `{process_first['matrix_count']}` matrices, `{process_first['storage_read_count']}` reads, `{process_first['storage_bytes_read']}` bytes, `{process_first['evictions_cumulative_end']}` bounded slot evictions.",
            "",
            "| Component | Median (s) |",
            "| --- | ---: |",
            *(f"| {name} | {value:.9f} |" for name, value in rows),
            "",
            f"For this bounded top-8 plus shared block, the optimized-reference median is `{reference_total:.9f}` s and the candidate median is `{direct_total:.9f}` s (ratio `{reference_total / direct_total:.2f}×`; absolute difference `{reference_total - direct_total:.9f}` s).",
            "",
            "The two-slot worker intentionally rereads routed gate/up slabs at this rung; it proves bounded lifecycle behavior, not a routed-residency policy. This is not a complete-layer or model speedup claim.",
            "",
        ]
    )


def _render_complete_layer(record: dict, raw_sha256: str) -> str:
    binding = record["binding"]
    numerical = record["numerical_qualification"]
    reference = record["optimized_reference"]["summaries"]
    direct_layer = record["direct_summaries"]["layer"]
    direct_moe = record["direct_summaries"]["moe"]
    reference_total = reference["total_seconds"]["median_seconds"]
    direct_total = direct_layer["total_seconds"]["median_seconds"]
    absolute = reference_total - direct_total
    reduction = absolute / reference_total
    rows = [
        ("Current attention/MLA", reference["attention_seconds"]["median_seconds"]),
        ("Current MoE", reference["moe_seconds"]["median_seconds"]),
        ("Current complete layer", reference_total),
        ("Candidate attention/MLA", direct_layer["attention_seconds"]["median_seconds"]),
        ("Candidate MoE", direct_layer["moe_seconds"]["median_seconds"]),
        ("Candidate direct routed IQ2", direct_moe["direct_iq2.total_seconds"]["median_seconds"]),
        ("Candidate routed IQ3 down decode", direct_moe["routed_down_reference.dequant_seconds"]["median_seconds"]),
        ("Candidate complete layer", direct_total),
    ]
    return "\n".join(
        [
            "# Feature 018 complete layer-3 gate",
            "",
            "> One real layer-3 MLA plus top-8/shared MoE boundary; not a 79-layer stack or token-generation result.",
            "",
            f"- Source: `{record['source']['commit']}` (clean)",
            f"- Raw SHA-256: `{raw_sha256}`",
            f"- Checkpoint set: `{record['checkpoint']['checkpoint_set_sha256']}`",
            f"- Input token: `{binding['input_token_id']}`; midpoint SHA-256: `{binding['midpoint_sha256']}`",
            f"- Top-8 route: `{binding['expert_ids']}`",
            f"- Current reference matches committed layer-3 evidence: `{str(binding['historical_reference_hash_match']).lower()}`",
            f"- Classification: `{record['classification']}`; tolerance mismatches: `{numerical['elementwise_mismatch_count']}`; max absolute error: `{numerical['maximum_absolute_error']:.9g}`",
            "",
            "| Boundary/component | Median (s) |",
            "| --- | ---: |",
            *(f"| {name} | {value:.9f} |" for name, value in rows),
            "",
            f"The candidate reduces this bounded complete-layer median by `{absolute:.9f}` s (`{reduction:.1%}`), from `{reference_total:.9f}` s to `{direct_total:.9f}` s. This is material for the frozen Feature 018 P1 admission decision.",
            "",
            "Attention/MLA and IQ3 down remain reference paths. The result does not establish full-stack or user-visible latency improvement.",
            "",
        ]
    )


def _render_real_matrix(record: dict, raw_sha256: str) -> str:
    binding = record["binding"]
    correctness = record["correctness"]
    timing = record["timing"]
    setup = record["setup"]
    optimized = record["optimized_reference"]["summaries"]
    optimized_rows = [
        ("Storage read", optimized["storage_read_seconds"]["median_seconds"]),
        ("NumPy dequantization", optimized["dequant_seconds"]["median_seconds"]),
        ("Contiguous-buffer check", optimized["contiguous_buffer_seconds"]["median_seconds"]),
        ("MLX matrix build/eval", optimized["mlx_matrix_build_eval_seconds"]["median_seconds"]),
        ("MLX matvec", optimized["mlx_matvec_seconds"]["median_seconds"]),
        ("Total (without cleanup)", optimized["total_seconds"]["median_seconds"]),
    ]
    direct_rows = [
        ("Checkpoint bounded read", setup["checkpoint_storage_seconds"]),
        ("Stable-slab copy", setup["slab_copy_seconds"]),
        ("No-copy Metal registration", setup["registration_seconds"]),
        ("Shader compile (process setup)", setup["compilation_seconds"]),
        ("First dispatch after setup", setup["process_first"]["total_seconds"]),
        ("Steady dispatch", timing["dispatch"]["median_seconds"]),
        ("Steady GPU command interval", timing["kernel"]["median_seconds"]),
        ("Steady synchronized call", timing["synchronization"]["median_seconds"]),
        ("Steady total", timing["median_seconds"]),
    ]
    optimized_total = optimized["total_seconds"]["median_seconds"]
    direct_total = timing["median_seconds"]
    return "\n".join(
        [
            f"# Feature 018 real IQ2_XXS {binding['projection']} matrix gate",
            "",
            "> One bound real matrix only; not complete-expert, MoE, layer, token, or production evidence.",
            "",
            f"- Source: `{record['source']['commit']}` (clean)",
            f"- Raw SHA-256: `{raw_sha256}`",
            f"- Checkpoint set: `{record['checkpoint']['checkpoint_set_sha256']}` at immutable revision `{record['checkpoint']['revision']}`",
            f"- Tensor: `{binding['tensor_name']}`, layer `{binding['layer']}`, expert `{binding['expert_id']}`, shape `{binding['shape'][0]} × {binding['shape'][1]}`",
            f"- Packed matrix SHA-256: `{binding['packed_sha256']}`; activation SHA-256: `{binding['activation_sha256']}`",
            f"- Classification: `{record['classification']}` (greedy selection is not applicable at this boundary)",
            f"- Exact f32 bits: `{str(correctness['exact_f32_bits']).lower()}`; bit mismatches: `{correctness['f32_bit_mismatch_count']}`",
            f"- Tolerance mismatches: `{correctness['elementwise_mismatch_count']}`; signed-zero mismatches: `{correctness['signed_zero_mismatch_count']}`",
            f"- Max absolute error: `{correctness['maximum_absolute_error']:.9g}`; RMSE: `{correctness['rmse']:.9g}`",
            f"- Cosine: `{correctness['cosine_similarity']:.12f}`; norm ratio: `{correctness['norm_ratio']:.12f}`",
            f"- Deterministic direct repetitions: `{correctness['deterministic_repetitions']}`; CPU fallback: `{record['kernel']['cpu_fallback_count']}`; complete f32 weight materialization: `{record['kernel']['complete_f32_weight_materialized_bytes']}` bytes",
            "",
            "## Current optimized NumPy + MLX reference",
            "",
            "| Stage | Median (s) |",
            "| --- | ---: |",
            *(f"| {name} | {value:.9f} |" for name, value in optimized_rows),
            "",
            "## Direct packed Metal candidate",
            "",
            "| Stage | Time (s) |",
            "| --- | ---: |",
            *(f"| {name} | {value:.9f} |" for name, value in direct_rows),
            "",
            f"At this bound warm matrix only, the current optimized-path median is `{optimized_total:.9f}` s and the direct packed-Metal median is `{direct_total:.9f}` s (ratio `{optimized_total / direct_total:.2f}×`; absolute difference `{optimized_total - direct_total:.9f}` s).",
            "",
            f"Steady direct population: {timing['sample_count']} samples after {record['protocol']['direct_metal_warmups']} warmups; min `{timing['minimum_seconds']:.9f}` s, max `{timing['maximum_seconds']:.9f}` s.",
            "",
            "Synchronization includes the command wait and is not additive to the GPU command interval. The ratio is not a model-level speedup claim.",
            "",
        ]
    )


def render(record: dict, raw_sha256: str) -> str:
    if record.get("schema") == "pulsarmlx.research.f018-direct-iq2-complete-layer":
        return _render_complete_layer(record, raw_sha256)
    if record.get("schema") == "pulsarmlx.research.f018-direct-iq2-moe":
        return _render_moe(record, raw_sha256)
    if record.get("schema") == "pulsarmlx.research.f018-direct-iq2-routed-expert":
        return _render_routed_expert(record, raw_sha256)
    if "tensor_name" in record.get("binding", {}):
        return _render_real_matrix(record, raw_sha256)
    timing = record["timing"]
    correctness = record["correctness"]
    setup = record["setup"]
    kernel = timing["kernel"]
    rows = [
        ("Storage read", timing["storage_read_seconds"], None),
        ("No-copy registration", setup["registration_seconds"], None),
        ("Shader compilation", setup["compilation_seconds"], None),
        ("Dispatch", timing["dispatch"]["median_seconds"], timing["dispatch"]["mean_seconds"]),
        ("GPU command interval", kernel["median_seconds"], kernel["mean_seconds"]),
        ("Synchronization", timing["synchronization"]["median_seconds"], timing["synchronization"]["mean_seconds"]),
        ("Steady-state total", timing["median_seconds"], timing["mean_seconds"]),
    ]
    stage_lines = [
        f"| {name} | {median:.9f} | {'—' if mean is None else f'{mean:.9f}'} |"
        for name, median, mean in rows
    ]
    return "\n".join(
        [
            "# Feature 018 synthetic direct-IQ2_XXS Metal gate",
            "",
            "> Synthetic packed matrix only; not real checkpoint, expert, layer, token, or production evidence.",
            "",
            f"- Source: `{record['source']['commit']}` (clean)",
            f"- Raw SHA-256: `{raw_sha256}`",
            f"- Device: `{record['environment']['metal_device']}`",
            f"- Matrix: `{record['binding']['rows']} × {record['binding']['columns']}`; `{record['binding']['packed_bytes']}` packed bytes",
            f"- Classification: `{record['classification']}`",
            f"- Deterministic repetitions: `{correctness['deterministic_repetitions']}`; unique hashes: `{correctness['unique_output_hashes']}`",
            f"- Exact f32 bits: `{str(correctness['exact_f32_bits']).lower()}`; bit mismatches: `{correctness['f32_bit_mismatch_count']}`",
            f"- Tolerance mismatches: `{correctness['elementwise_mismatch_count']}`; signed-zero mismatches: `{correctness['signed_zero_mismatch_count']}`",
            f"- Max absolute error: `{correctness['maximum_absolute_error']:.9g}`; RMSE: `{correctness['rmse']:.9g}`",
            f"- Cosine: `{correctness['cosine_similarity']:.12f}`; norm ratio: `{correctness['norm_ratio']:.12f}`",
            f"- CPU fallback: `{record['kernel']['cpu_fallback_count']}`; complete f32 weight materialization: `{record['kernel']['complete_f32_weight_materialized_bytes']}` bytes",
            "",
            "| Stage | Median (s) | Mean (s) |",
            "| --- | ---: | ---: |",
            *stage_lines,
            "",
            f"Steady-state population: {timing['sample_count']} samples after {timing['warmup_count']} warmups; min `{timing['minimum_seconds']:.9f}` s, max `{timing['maximum_seconds']:.9f}` s.",
            "",
            "The result proves a true packed-weight Metal GEMV boundary with numerical qualification. It does not establish a real-matrix or model speedup.",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    raw = args.input.read_bytes()
    record = validate_record(load_unique_json(args.input))
    rendered = render(record, hashlib.sha256(raw).hexdigest())
    if args.check:
        if args.output.read_text() != rendered:
            raise SystemExit(f"generated table differs: {args.output}")
        print(f"Feature 018 table matches: {args.output}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
