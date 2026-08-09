#!/usr/bin/env python3
"""Generate the post-Feature-016 Q5_K qualification table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "docs/research/glm52/raw/post-f016-q5-k-numpy-qualification-0001.json"
DEFAULT_TABLE = ROOT / "docs/research/glm52/tables/post-f016-q5-k-numpy-qualification-0001.md"


def render(record: dict) -> str:
    benchmark = record["benchmark"]
    scalar = benchmark["scalar_reference"]["summary"]
    vector = benchmark["numpy_vectorized"]["summary"]
    lines = [
        "# Post-Feature-016 NumPy Q5_K qualification",
        "",
        "> Decoder boundary only. This table does not claim a complete MLA, transformer-layer, stack, token, Rust, or Metal speedup.",
        "",
        f"- Evidence source: `{record['source_commit']}` (clean: `{str(not record['source_dirty']).lower()}`)",
        f"- Checkpoint set SHA-256: `{record['checkpoint']['checkpoint_set_sha256']}`",
        f"- Machine: {record['machine']['chip']}, {record['machine']['architecture']}",
        f"- Protocol: {record['protocol']['warmups_per_mode']} warm-ups and {record['protocol']['measured_samples_per_mode']} measured samples per mode; OS page cache uncontrolled.",
        "",
        "## Complete real matrices",
        "",
        "| Tensor | Shard | Shape | Encoded MiB | Scalar first decode (s) | Vector first decode (s) | Exact f32 bits | Deterministic | Signed zero exact |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for case in record["cases"]:
        rows, cols = case["shape_rows_cols"]
        lines.append(
            f"| `{case['tensor']}` | `{case['shard']}` | {rows}x{cols} | "
            f"{case['encoded_bytes'] / 2**20:.3f} | {case['scalar_decode_seconds']:.6f} | "
            f"{case['vector_decode_seconds']:.6f} | {str(case['exact_f32_bits']).lower()} | "
            f"{str(case['deterministic_repeat']).lower()} | {str(case['signed_zero_exact']).lower()} |"
        )
    lines.extend(
        [
            "",
            "## Decode-only benchmark",
            "",
            "| Mode | Samples | Median (s) | Mean (s) | Stddev (s) | Min (s) | Max (s) |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            f"| scalar reference | {scalar['sample_count']} | {scalar['median_seconds']:.6f} | {scalar['mean_seconds']:.6f} | {scalar['standard_deviation_seconds']:.6f} | {scalar['minimum_seconds']:.6f} | {scalar['maximum_seconds']:.6f} |",
            f"| NumPy vectorized | {vector['sample_count']} | {vector['median_seconds']:.6f} | {vector['mean_seconds']:.6f} | {vector['standard_deviation_seconds']:.6f} | {vector['minimum_seconds']:.6f} | {vector['maximum_seconds']:.6f} |",
            "",
            f"Median decode-only ratio: **{benchmark['median_decode_speedup']:.2f}x**.",
            "",
            f"The instrumented vector allocation observation reported {record['allocation_observation']['traced_peak_bytes'] / 2**20:.1f} MiB Python-traced peak and a {record['resource_after']['peak_rss_bytes'] / 2**30:.3f} GiB process peak-RSS high-water mark. Tracemalloc does not cover every NumPy native allocation, and peak RSS is process-lifetime cumulative.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
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
