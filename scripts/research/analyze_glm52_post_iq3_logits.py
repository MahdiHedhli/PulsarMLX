#!/usr/bin/env python3
"""Generate the post-IQ3 output-head profile table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_INPUT = Path("docs/research/glm52/raw/post-f018-output-head-profile-0001.json")
DEFAULT_OUTPUT = Path("docs/research/glm52/tables/post-f018-output-head-profile-0001.md")


def render(record: dict) -> str:
    if record.get("actual_status") != "passed":
        raise ValueError("output-head profile did not pass")
    rows = []
    for key, label in (
        ("storage_read_seconds", "Storage read"),
        ("dequant_seconds", "Scalar Q4_K decode/materialization"),
        ("contiguous_buffer_seconds", "Contiguous buffer"),
        ("mlx_matrix_build_seconds", "MLX build/eval"),
        ("mlx_matvec_seconds", "MLX matvec"),
        ("total_seconds", "Synchronized boundary total"),
        ("cleanup_seconds", "Cleanup"),
    ):
        summary = record["summaries"][key]
        rows.append(
            f"| {label} | {summary['median_seconds']:.6f} | "
            f"{summary['mean_seconds']:.6f} | {summary['standard_deviation_seconds']:.6f} | "
            f"{summary['minimum_seconds']:.6f} | {summary['maximum_seconds']:.6f} |"
        )
    return "\n".join(
        [
            "# Post-IQ3 full-vocabulary output-head profile",
            "",
            "> One real Q4_K matrix with a deterministic normalized activation; not a greedy-token or complete-stack result.",
            "",
            f"- Source: `{record['source']['commit']}` (clean)",
            f"- Tensor: `{record['binding']['tensor']}`; shape: `{record['binding']['shape']}`",
            f"- Compressed/decoded bytes: `{record['binding']['compressed_bytes']}` / `{record['binding']['decoded_f32_bytes']}`",
            f"- Samples: `{record['protocol']['measured_samples']}` after `{record['protocol']['warmups']}` warmups",
            f"- Deterministic output hashes: `{record['determinism']['unique_output_hashes']}`",
            "",
            "| Component | Median (s) | Mean (s) | Stddev (s) | Min (s) | Max (s) |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
            *rows,
            "",
            "The current mode still uses scalar Q4_K decode and complete f32 materialization before MLX import. The profile measures that path; it does not qualify a replacement.",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = render(json.loads(args.input.read_text()))
    if args.check:
        if args.output.read_text() != rendered:
            raise SystemExit(f"generated table differs: {args.output}")
        print(f"post-IQ3 output-head table matches: {args.output}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
