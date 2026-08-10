#!/usr/bin/env python3
"""Generate Feature 018 composed IQ2/IQ3 MoE and layer review tables."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/research"))

from f018_evidence import load_unique_json, validate_record  # noqa: E402


def _render_moe(record: dict, raw_sha256: str) -> str:
    direct = record["direct_summaries"]
    reference = record["optimized_reference"]["summaries"]
    numerical = record["numerical_qualification"]
    reference_total = float(reference["total_seconds"]["median_seconds"])
    direct_total = float(direct["total_seconds"]["median_seconds"])
    rows = [
        ("Optimized reference total", reference_total),
        ("Direct IQ2 gate/up synchronized", direct["direct_iq2.total_seconds"]["median_seconds"]),
        ("Direct IQ3 down synchronized", direct["direct_iq3.total_seconds"]["median_seconds"]),
        ("Routed SwiGLU activation", direct["routed_activation_seconds"]["median_seconds"]),
        ("Shared reference", direct["shared_reference.total_seconds"]["median_seconds"]),
        ("Complete top-8 plus shared", direct_total),
    ]
    return "\n".join(
        [
            "# Feature 018 direct IQ2/IQ3 top-8 plus shared MoE",
            "",
            "> One real layer-3 MoE boundary; routed IQ2 gate/up and IQ3 down are direct, while the shared expert remains the explicit protected MLX reference path.",
            "",
            f"- Source: `{record['source']['commit']}` (clean)",
            f"- Raw SHA-256: `{raw_sha256}`",
            f"- Route: `{record['binding']['expert_ids']}`; shared expert: `0`",
            f"- Classification: `{record['classification']}`; mismatches: `{numerical['elementwise_mismatch_count']}`; max absolute error: `{numerical['maximum_absolute_error']:.9g}`",
            "",
            "| Component | Median (s) |",
            "| --- | ---: |",
            *(f"| {name} | {float(value):.9f} |" for name, value in rows),
            "",
            f"Same-boundary ratio: `{reference_total / direct_total:.2f}×`; absolute difference: `{reference_total - direct_total:.9f}` s. This is not a complete-layer or token claim.",
            "",
        ]
    )


def _render_layer(record: dict, raw_sha256: str) -> str:
    direct = record["direct_summaries"]["layer"]
    reference = record["optimized_reference"]["summaries"]
    numerical = record["numerical_qualification"]
    reference_total = float(reference["total_seconds"]["median_seconds"])
    direct_total = float(direct["total_seconds"]["median_seconds"])
    rows = [
        ("Optimized reference total", reference_total),
        ("Direct candidate attention", direct["attention_seconds"]["median_seconds"]),
        ("Direct candidate MoE", direct["moe_seconds"]["median_seconds"]),
        ("Direct candidate dense total", direct["dense_total_seconds"]["median_seconds"]),
        ("Complete layer", direct_total),
    ]
    return "\n".join(
        [
            "# Feature 018 direct IQ2/IQ3 complete layer-3 gate",
            "",
            "> One complete layer-3 MLA plus top-8/shared MoE boundary; not a 79-layer stack or token result.",
            "",
            f"- Source: `{record['source']['commit']}` (clean)",
            f"- Raw SHA-256: `{raw_sha256}`",
            f"- Classification: `{record['classification']}`; mismatches: `{numerical['elementwise_mismatch_count']}`; max absolute error: `{numerical['maximum_absolute_error']:.9g}`",
            "",
            "| Component | Median (s) |",
            "| --- | ---: |",
            *(f"| {name} | {float(value):.9f} |" for name, value in rows),
            "",
            f"Same-boundary ratio: `{reference_total / direct_total:.2f}×`; absolute difference: `{reference_total - direct_total:.9f}` s.",
            "",
        ]
    )


def render(record: dict, raw_sha256: str) -> str:
    if record["schema"].endswith("-moe"):
        return _render_moe(record, raw_sha256)
    if record["schema"].endswith("-complete-layer"):
        return _render_layer(record, raw_sha256)
    raise ValueError("unsupported composed IQ3 evidence schema")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
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
