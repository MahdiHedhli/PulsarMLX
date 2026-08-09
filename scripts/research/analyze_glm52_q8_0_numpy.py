#!/usr/bin/env python3
"""Generate the post-Feature-016 Q8_0 qualification table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs/research/glm52/raw/post-f016-q8-0-numpy-qualification-0001.json"
TABLE = ROOT / "docs/research/glm52/tables/post-f016-q8-0-numpy-qualification-0001.md"


def render(record: dict) -> str:
    scalar = record["benchmark"]["scalar_reference"]["summary"]
    vector = record["benchmark"]["numpy_vectorized"]["summary"]
    lines = [
        "# Post-Feature-016 NumPy Q8_0 qualification", "",
        "> Two-dimensional decoder boundary only; per-head 3-D Q8_0 remains excluded.", "",
        f"- Evidence source: `{record['source_commit']}` (clean: `{str(not record['source_dirty']).lower()}`)",
        f"- Checkpoint set SHA-256: `{record['checkpoint']['checkpoint_set_sha256']}`",
        f"- Protocol: {record['protocol']['warmups_per_mode']} warm-ups and {record['protocol']['measured_samples_per_mode']} measured samples per mode; OS page cache uncontrolled.", "",
        "| Tensor | Shard | Shape | Scalar first decode (s) | Vector first decode (s) | Exact f32 bits | Deterministic | Signed zero exact |",
        "| --- | --- | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for case in record["cases"]:
        rows, cols = case["shape_rows_cols"]
        lines.append(f"| `{case['tensor']}` | `{case['shard']}` | {rows}x{cols} | {case['scalar_decode_seconds']:.6f} | {case['vector_decode_seconds']:.6f} | {str(case['exact_f32_bits']).lower()} | {str(case['deterministic_repeat']).lower()} | {str(case['signed_zero_exact']).lower()} |")
    lines.extend([
        "", "## Decode-only benchmark", "",
        "| Mode | Samples | Median (s) | Mean (s) | Stddev (s) | Min (s) | Max (s) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| scalar reference | {scalar['sample_count']} | {scalar['median_seconds']:.6f} | {scalar['mean_seconds']:.6f} | {scalar['standard_deviation_seconds']:.6f} | {scalar['minimum_seconds']:.6f} | {scalar['maximum_seconds']:.6f} |",
        f"| NumPy vectorized | {vector['sample_count']} | {vector['median_seconds']:.6f} | {vector['mean_seconds']:.6f} | {vector['standard_deviation_seconds']:.6f} | {vector['minimum_seconds']:.6f} | {vector['maximum_seconds']:.6f} |",
        "", f"Median decode-only ratio: **{record['benchmark']['median_decode_speedup']:.2f}x**.", "",
        "This does not establish complete MLA/layer, per-head 3-D Q8_0, token, Rust, or Metal speedup.", "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--table", type=Path, default=TABLE)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = render(json.loads(args.source.read_text()))
    if args.check:
        if not args.table.exists() or args.table.read_text() != rendered:
            raise SystemExit(f"generated table is stale: {args.table}")
        return 0
    args.table.parent.mkdir(parents=True, exist_ok=True)
    args.table.write_text(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
