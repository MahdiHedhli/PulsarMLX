#!/usr/bin/env python3
"""Generate the exact 2-D Q8_0 dense integration comparison table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs/research/glm52/raw/post-f016-trunk-q8-2d-integration-0001.json"
TABLE = ROOT / "docs/research/glm52/tables/post-f016-trunk-q8-2d-integration-0001.md"
BASELINE = "whole_matrix_numpy_q5"
CANDIDATE = "whole_matrix_numpy_q5_q8"


def _median(boundary, mode, field):
    return float(boundary["summaries"][mode][field]["median_seconds"])


def render(record: dict) -> str:
    matrix, mla = record["matrix"], record["representative_mla_layer"]
    matrix_ratio = _median(matrix, BASELINE, "total_seconds") / _median(matrix, CANDIDATE, "total_seconds")
    mla_ratio = _median(mla, BASELINE, "total_seconds") / _median(mla, CANDIDATE, "total_seconds")
    def row(boundary, label, mode):
        return f"| {label} | {_median(boundary, mode, 'storage_read_seconds'):.6f} | {_median(boundary, mode, 'dequant_seconds'):.6f} | {_median(boundary, mode, 'contiguous_buffer_seconds'):.6f} | {_median(boundary, mode, 'mlx_matrix_build_seconds'):.6f} | {_median(boundary, mode, 'mlx_matvec_seconds'):.6f} | {_median(boundary, mode, 'total_seconds'):.6f} |"
    return "\n".join([
        "# Post-Feature-016 2-D Q8_0 dense integration", "",
        "> Q5_K remains vectorized in both modes. The only captured decoder change is 2-D Q8_0. Per-head 3-D Q8_0 remains unchanged and inside the residual.", "",
        f"- Evidence source: `{record['source_commit']}` (clean: `{str(not record['source_dirty']).lower()}`)",
        f"- Checkpoint set SHA-256: `{record['checkpoint']['checkpoint_set_sha256']}`", "",
        "| Matrix mode | Storage (s) | Decode (s) | Buffer (s) | MLX build/eval (s) | Matvec (s) | Total (s) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        row(matrix, "Q5 vector; Q8 scalar", BASELINE), row(matrix, "Q5 + 2-D Q8 vector", CANDIDATE), "",
        f"Complete real matrix median ratio: **{matrix_ratio:.2f}x**, exact f32 bits.", "",
        "## Complete layer-3 MLA", "",
        "| MLA mode | Storage (s) | Decode (s) | Buffer (s) | MLX build/eval (s) | Matvec (s) | Total (s) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        row(mla, "Q5 vector; 2-D Q8 scalar", BASELINE), row(mla, "Q5 + 2-D Q8 vector", CANDIDATE), "",
        f"MLA median ratio: **{mla_ratio:.2f}x**, exact f32 bits. Candidate uninstrumented residual median: {_median(mla, CANDIDATE, 'uninstrumented_residual_seconds'):.6f} s ({_median(mla, CANDIDATE, 'uninstrumented_residual_seconds') / _median(mla, CANDIDATE, 'total_seconds'):.2%} of median wall; ratio of medians).", "",
        "This does not establish per-head 3-D Q8_0, complete transformer-layer, token, Rust, or Metal speedup.", "",
    ])


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
