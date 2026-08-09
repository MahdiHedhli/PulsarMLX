#!/usr/bin/env python3
"""Generate the bounded Phase-A trunk bulk-read comparison table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = (
    ROOT / "docs/research/glm52/raw/post-f016-trunk-bulk-read-0001.json"
)
DEFAULT_TABLE = (
    ROOT / "docs/research/glm52/tables/post-f016-trunk-bulk-read-0001.md"
)


def _change(reference: float, candidate: float) -> float:
    return (candidate / reference - 1.0) * 100.0


def _median(boundary: dict, mode: str, field: str) -> float:
    return float(boundary["summaries"][mode][field]["median_seconds"])


def render(record: dict) -> str:
    lines = [
        "# Post-Feature-016 trunk bulk-read experiment",
        "",
        "> Phase A changes storage request granularity only. The scalar decoder, row order, f32 materialization, and synchronized MLX matvec are unchanged.",
        "",
        f"- Evidence source: `{record['source_commit']}` (clean: `{str(not record['source_dirty']).lower()}`)",
        f"- Checkpoint set SHA-256: `{record['checkpoint']['checkpoint_set_sha256']}`",
        f"- Warm-ups / measured samples per mode: {record['protocol']['warmups_per_mode']} / {record['protocol']['measured_samples_per_mode']}",
        "- OS page cache: uncontrolled; results are a counterbalanced warm-storage population.",
        "",
        "## Real matrix boundaries",
        "",
        "| Tensor | Quant | Shape | Encoded MiB | Reads row -> bulk | Read reduction | Storage median row -> bulk (s) | Decode median row -> bulk (s) | Total median row -> bulk (s) | Total change | Exact f32 bits |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for matrix in record["matrices"]:
        identity = matrix["identity"]
        contract = matrix["read_contract"]
        row_storage = _median(matrix, "row_reference", "storage_read_seconds")
        bulk_storage = _median(matrix, "whole_matrix_scalar", "storage_read_seconds")
        row_decode = _median(matrix, "row_reference", "dequant_seconds")
        bulk_decode = _median(matrix, "whole_matrix_scalar", "dequant_seconds")
        row_total = _median(matrix, "row_reference", "total_seconds")
        bulk_total = _median(matrix, "whole_matrix_scalar", "total_seconds")
        rows, cols = identity["shape_rows_cols"]
        lines.append(
            "| "
            f"`{identity['tensor']}` | {identity['quantization']} | {rows}x{cols} | "
            f"{identity['encoded_bytes'] / 2**20:.3f} | "
            f"{contract['row_reference']:,} -> {contract['whole_matrix_scalar']:,} | "
            f"{contract['request_reduction_factor']:,.0f}x | "
            f"{row_storage:.6f} -> {bulk_storage:.6f} | "
            f"{row_decode:.6f} -> {bulk_decode:.6f} | "
            f"{row_total:.6f} -> {bulk_total:.6f} | "
            f"{_change(row_total, bulk_total):+.3f}% | "
            f"{str(matrix['comparison']['exact_f32_bits']).lower()} |"
        )

    mla = record["representative_mla_layer"]
    row_reads = mla["dense_2d_read_counts"]["row_reference"][0]
    bulk_reads = mla["dense_2d_read_counts"]["whole_matrix_scalar"][0]
    row_total = _median(mla, "row_reference", "total_seconds")
    bulk_total = _median(mla, "whole_matrix_scalar", "total_seconds")
    row_storage = _median(mla, "row_reference", "storage_read_seconds")
    bulk_storage = _median(mla, "whole_matrix_scalar", "storage_read_seconds")
    row_decode = _median(mla, "row_reference", "dequant_seconds")
    bulk_decode = _median(mla, "whole_matrix_scalar", "dequant_seconds")
    lines.extend(
        [
            "",
            "## Representative MLA boundary",
            "",
            f"Layer {mla['layer']} complete single-position MLA attention produced exact f32-bit output across modes. The dense metrics cover the four 2-D projections; per-head 3-D Q8_0 work remains in the explicitly recorded uninstrumented residual.",
            "",
            "| Metric | Row reference | Whole-matrix scalar | Change |",
            "| --- | ---: | ---: | ---: |",
            f"| 2-D positional read requests | {row_reads:,} | {bulk_reads:,} | {row_reads / bulk_reads:,.0f}x reduction |",
            f"| Storage median (s) | {row_storage:.6f} | {bulk_storage:.6f} | {_change(row_storage, bulk_storage):+.3f}% |",
            f"| Scalar decode median (s) | {row_decode:.6f} | {bulk_decode:.6f} | {_change(row_decode, bulk_decode):+.3f}% |",
            f"| Total boundary median (s) | {row_total:.6f} | {bulk_total:.6f} | {_change(row_total, bulk_total):+.3f}% |",
            f"| Uninstrumented residual median (s) | {_median(mla, 'row_reference', 'uninstrumented_residual_seconds'):.6f} | {_median(mla, 'whole_matrix_scalar', 'uninstrumented_residual_seconds'):.6f} | n/a |",
            "",
            "## Decision",
            "",
            "Whole-matrix reads satisfy the exactness and request-accounting gates but do not materially reduce these warm boundary totals. Scalar decode dominates the representative MLA boundary, so Phase B should qualify only the highest-value trunk decoder formats while retaining this one-read path.",
            "",
            "This record does **not** establish a complete transformer-layer, full-stack, token-generation, process-cold storage, Rust, or direct-Metal speedup.",
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
