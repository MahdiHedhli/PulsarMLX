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


def render(record: dict, raw_sha256: str) -> str:
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
