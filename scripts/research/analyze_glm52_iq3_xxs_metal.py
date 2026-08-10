#!/usr/bin/env python3
"""Validate IQ3_XXS Metal evidence and generate its review table."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/research"))

from f018_evidence import load_unique_json, validate_record  # noqa: E402

DEFAULT_INPUT = ROOT / "docs/research/glm52/raw/f018-iq3-xxs-synthetic-0001.json"
DEFAULT_OUTPUT = ROOT / "docs/research/glm52/tables/f018-iq3-xxs-synthetic-0001.md"


def _render_synthetic(record: dict, raw_sha256: str) -> str:
    binding = record["binding"]
    correctness = record["correctness"]
    timing = record["timing"]
    compiler = record["kernel"]["compiler"]
    return "\n".join(
        [
            "# Feature 018 synthetic IQ3_XXS qualification",
            "",
            "> Checkpoint-free packed-weight Metal GEMV evidence only; not a real matrix, expert, layer, token, or production result.",
            "",
            f"- Source: `{record['source']['commit']}` (clean)",
            f"- Raw SHA-256: `{raw_sha256}`",
            f"- Fixture: `{binding['fixture']}`; shape: `{binding['rows']} × {binding['columns']}`; packed bytes: `{binding['packed_bytes']}`",
            f"- Classification: `{record['classification']}`; exact f32 bits: `{str(correctness['exact_f32_bits']).lower()}`",
            f"- Deterministic repetitions: `{correctness['deterministic_repetitions']}`; unique output hashes: `{correctness['unique_output_hashes']}`",
            f"- Strict Metal: fast math `{str(compiler['fast_math_enabled']).lower()}`, language `{compiler['language_version']}`, `{compiler['math_mode']}` / `{compiler['math_floating_point_functions']}`",
            f"- CPU fallbacks: `{record['kernel']['cpu_fallback_count']}`; complete f32 weight materialization: `{record['kernel']['complete_f32_weight_materialized_bytes']}` bytes",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Median synchronized call (s) | {float(timing['median_seconds']):.9f} |",
            f"| Mean synchronized call (s) | {float(timing['mean_seconds']):.9f} |",
            f"| Minimum synchronized call (s) | {float(timing['minimum_seconds']):.9f} |",
            f"| Maximum synchronized call (s) | {float(timing['maximum_seconds']):.9f} |",
            f"| Maximum absolute error | {float(correctness['maximum_absolute_error']):.9g} |",
            f"| Mean absolute error | {float(correctness['mean_absolute_error']):.9g} |",
            f"| RMSE | {float(correctness['rmse']):.9g} |",
            f"| Cosine similarity | {float(correctness['cosine_similarity']):.12f} |",
            f"| Norm ratio | {float(correctness['norm_ratio']):.12f} |",
            f"| Signed-zero mismatches | {correctness['signed_zero_mismatch_count']} |",
            "",
        ]
    )


def _render_real(record: dict, raw_sha256: str) -> str:
    binding = record["binding"]
    correctness = record["correctness"]
    direct = record["timing"]
    reference = record["optimized_reference"]["summaries"]
    return "\n".join(
        [
            "# Feature 018 real IQ3_XXS routed-down matrix qualification",
            "",
            "> One real selected-expert down matrix on one M1 Ultra; not a complete expert, layer, token, or production result.",
            "",
            f"- Source: `{record['source']['commit']}` (clean)",
            f"- Raw SHA-256: `{raw_sha256}`",
            f"- Tensor: `{binding['tensor_name']}`; layer/expert: `{binding['layer']}` / `{binding['expert_id']}`",
            f"- Shape: `{binding['shape']}`; packed bytes: `{binding['packed_bytes']}`; quantization: `{binding['quantization']}`",
            f"- Classification: `{record['classification']}`; exact f32 bits: `{str(correctness['exact_f32_bits']).lower()}`",
            f"- Elementwise/signed-zero mismatches: `{correctness['elementwise_mismatch_count']}` / `{correctness['signed_zero_mismatch_count']}`",
            f"- CPU fallbacks: `{record['kernel']['cpu_fallback_count']}`; complete f32 Metal weight materialization: `{record['kernel']['complete_f32_weight_materialized_bytes']}` bytes",
            "",
            "| Boundary/component | Median (s) |",
            "| --- | ---: |",
            f"| Optimized reference storage | {float(reference['storage_read_seconds']['median_seconds']):.9f} |",
            f"| Optimized reference decode | {float(reference['dequant_seconds']['median_seconds']):.9f} |",
            f"| Optimized reference contiguous buffer | {float(reference['contiguous_buffer_seconds']['median_seconds']):.9f} |",
            f"| Optimized reference MLX build/eval | {float(reference['mlx_matrix_build_eval_seconds']['median_seconds']):.9f} |",
            f"| Optimized reference MLX matvec | {float(reference['mlx_matvec_seconds']['median_seconds']):.9f} |",
            f"| Optimized reference total | {float(reference['total_seconds']['median_seconds']):.9f} |",
            f"| Strict direct Metal synchronized total | {float(direct['median_seconds']):.9f} |",
            f"| Strict direct Metal kernel | {float(direct['kernel']['median_seconds']):.9f} |",
            f"| Strict direct Metal synchronization | {float(direct['synchronization']['median_seconds']):.9f} |",
            "",
            f"The same-boundary median ratio is `{float(reference['total_seconds']['median_seconds']) / float(direct['median_seconds']):.3f}×` in favor of the strict direct candidate. This does not predict complete-expert or token performance.",
            "",
        ]
    )


def render(record: dict, raw_sha256: str) -> str:
    if "tensor_name" in record.get("binding", {}):
        return _render_real(record, raw_sha256)
    return _render_synthetic(record, raw_sha256)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    record = validate_record(load_unique_json(args.input))
    raw_sha256 = hashlib.sha256(args.input.read_bytes()).hexdigest()
    rendered = render(record, raw_sha256)
    if args.check:
        if not args.output.is_file() or args.output.read_text() != rendered:
            raise SystemExit(f"generated table differs: {args.output}")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
