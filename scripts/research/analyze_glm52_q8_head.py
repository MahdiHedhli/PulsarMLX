#!/usr/bin/env python3
"""Generate comparison tables for bounded Q8_0 head-slab experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _median(boundary, mode, field):
    return float(boundary["summaries"][mode][field]["median_seconds"])


def render(record: dict) -> str:
    baseline, candidate = record["protocol"]["modes"]
    head, mla = record["head_boundary"], record["representative_mla_layer"]
    head_ratio = _median(head, baseline, "total_seconds") / _median(head, candidate, "total_seconds")
    mla_ratio = _median(mla, baseline, "total_seconds") / _median(mla, candidate, "total_seconds")
    title = "Q8_0 head-slab bulk-read scalar experiment" if "bulk-scalar" in record["schema"] else "Q8_0 head-slab NumPy integration"
    return "\n".join([
        f"# Post-Feature-016 {title}", "",
        f"> One changed variable: {record['protocol']['changed_variable']}.", "",
        f"- Evidence source: `{record['source_commit']}` (clean: `{str(not record['source_dirty']).lower()}`)",
        f"- Checkpoint set SHA-256: `{record['checkpoint']['checkpoint_set_sha256']}`",
        f"- Protocol: {record['protocol']['warmups_per_mode']} warm-ups and {record['protocol']['measured_samples_per_mode']} measured samples per mode; OS page cache uncontrolled.", "",
        "## One real head slab", "",
        "| Mode | Storage (s) | Decode (s) | Buffer (s) | MLX build/eval (s) | Matvec (s) | Total (s) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| `{baseline}` | {_median(head, baseline, 'storage_read_seconds'):.6f} | {_median(head, baseline, 'dequant_seconds'):.6f} | {_median(head, baseline, 'contiguous_buffer_seconds'):.6f} | {_median(head, baseline, 'mlx_matrix_build_seconds'):.6f} | {_median(head, baseline, 'mlx_matvec_seconds'):.6f} | {_median(head, baseline, 'total_seconds'):.6f} |",
        f"| `{candidate}` | {_median(head, candidate, 'storage_read_seconds'):.6f} | {_median(head, candidate, 'dequant_seconds'):.6f} | {_median(head, candidate, 'contiguous_buffer_seconds'):.6f} | {_median(head, candidate, 'mlx_matrix_build_seconds'):.6f} | {_median(head, candidate, 'mlx_matvec_seconds'):.6f} | {_median(head, candidate, 'total_seconds'):.6f} |",
        "", f"Head median total ratio: **{head_ratio:.3f}x**, exact f32 bits.", "",
        "## Complete layer-3 MLA", "",
        "| Mode | Head reads | Head storage (s) | Head decode (s) | Head build (s) | Head total (s) | 2-D total (s) | Residual (s) | MLA total (s) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| `{baseline}` | {int(mla['samples'][baseline][0]['head_storage_read_count']):,} | {_median(mla, baseline, 'head_storage_read_seconds'):.6f} | {_median(mla, baseline, 'head_dequant_seconds'):.6f} | {_median(mla, baseline, 'head_mlx_matrix_build_seconds'):.6f} | {_median(mla, baseline, 'head_total_seconds'):.6f} | {_median(mla, baseline, 'matrix_total_seconds'):.6f} | {_median(mla, baseline, 'uninstrumented_residual_seconds'):.6f} | {_median(mla, baseline, 'total_seconds'):.6f} |",
        f"| `{candidate}` | {int(mla['samples'][candidate][0]['head_storage_read_count']):,} | {_median(mla, candidate, 'head_storage_read_seconds'):.6f} | {_median(mla, candidate, 'head_dequant_seconds'):.6f} | {_median(mla, candidate, 'head_mlx_matrix_build_seconds'):.6f} | {_median(mla, candidate, 'head_total_seconds'):.6f} | {_median(mla, candidate, 'matrix_total_seconds'):.6f} | {_median(mla, candidate, 'uninstrumented_residual_seconds'):.6f} | {_median(mla, candidate, 'total_seconds'):.6f} |",
        "", f"MLA median total ratio: **{mla_ratio:.3f}x**, exact f32 bits.", "",
        "This is a bounded head/MLA result, not a complete transformer-layer, stack, token, Rust, or Metal claim.", "",
    ])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--table", type=Path, required=True)
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
