#!/usr/bin/env python3
"""Generate the Feature 018 composed IQ2/IQ3 routed-expert table."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/research"))

from f018_evidence import load_unique_json, validate_record  # noqa: E402

DEFAULT_INPUT = ROOT / "docs/research/glm52/raw/f018-iq2-iq3-routed-expert-0001.json"
DEFAULT_OUTPUT = ROOT / "docs/research/glm52/tables/f018-iq2-iq3-routed-expert-0001.md"


def render(record: dict, raw_sha256: str) -> str:
    binding = record["binding"]
    numerical = record["numerical_qualification"]
    reference = record["optimized_reference"]["summaries"]
    direct = record["direct_summaries"]
    reference_total = float(reference["total_seconds"]["median_seconds"])
    direct_total = float(direct["total_seconds"]["median_seconds"])
    rows = [
        ("Optimized reference decode", reference["dequant_seconds"]["median_seconds"]),
        ("Optimized reference build/eval", reference["mlx_matrix_build_eval_seconds"]["median_seconds"]),
        ("Optimized reference matvec", reference["mlx_matvec_seconds"]["median_seconds"]),
        ("Optimized reference total", reference_total),
        ("Direct IQ2 gate synchronized", direct["gate.total_seconds"]["median_seconds"]),
        ("Direct IQ2 up synchronized", direct["up.total_seconds"]["median_seconds"]),
        ("Direct IQ3 down synchronized", direct["down.total_seconds"]["median_seconds"]),
        ("Direct three-projection kernel", direct["direct.kernel_seconds"]["median_seconds"]),
        ("SwiGLU activation", direct["activation_swiglu_seconds"]["median_seconds"]),
        ("Direct complete expert total", direct_total),
    ]
    return "\n".join(
        [
            "# Feature 018 direct IQ2/IQ3 routed-expert gate",
            "",
            "> One real layer-3 expert only: direct IQ2_XXS gate/up and direct IQ3_XXS down.",
            "",
            f"- Source: `{record['source']['commit']}` (clean)",
            f"- Raw SHA-256: `{raw_sha256}`",
            f"- Layer/expert: `{binding['layer']}` / `{binding['expert_id']}`",
            f"- Classification: `{record['classification']}`; mismatches: `{numerical['elementwise_mismatch_count']}`; max absolute error: `{numerical['maximum_absolute_error']:.9g}`",
            f"- Warm reuse: `3` stable packed slabs, `3` hits/sample, `0` evictions, `0` fallback, `0` complete-f32 Metal weight bytes.",
            "",
            "| Component | Median (s) |",
            "| --- | ---: |",
            *(f"| {name} | {float(value):.9f} |" for name, value in rows),
            "",
            f"The same-boundary optimized-reference median was `{reference_total:.9f}` s and the direct candidate median was `{direct_total:.9f}` s (ratio `{reference_total / direct_total:.2f}×`; absolute difference `{reference_total - direct_total:.9f}` s).",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    record = validate_record(load_unique_json(args.input))
    rendered = render(record, hashlib.sha256(args.input.read_bytes()).hexdigest())
    if args.check:
        if not args.output.is_file() or args.output.read_text() != rendered:
            raise SystemExit(f"generated table differs: {args.output}")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
