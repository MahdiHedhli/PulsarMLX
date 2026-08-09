#!/usr/bin/env python3
"""Generate the exact Q5_K dense integration comparison table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "docs/research/glm52/raw/post-f016-trunk-q5-integration-0001.json"
DEFAULT_TABLE = ROOT / "docs/research/glm52/tables/post-f016-trunk-q5-integration-0001.md"


def _median(boundary: dict, mode: str, field: str) -> float:
    return float(boundary["summaries"][mode][field]["median_seconds"])


def _row(boundary: dict, label: str, mode: str) -> str:
    return (
        f"| {label} | {_median(boundary, mode, 'storage_read_seconds'):.6f} | "
        f"{_median(boundary, mode, 'dequant_seconds'):.6f} | "
        f"{_median(boundary, mode, 'contiguous_buffer_seconds'):.6f} | "
        f"{_median(boundary, mode, 'mlx_matrix_build_seconds'):.6f} | "
        f"{_median(boundary, mode, 'mlx_matvec_seconds'):.6f} | "
        f"{_median(boundary, mode, 'total_seconds'):.6f} |"
    )


def render(record: dict) -> str:
    matrix = record["matrix"]
    mla = record["representative_mla_layer"]
    matrix_ratio = _median(matrix, "whole_matrix_scalar", "total_seconds") / _median(matrix, "whole_matrix_numpy_q5", "total_seconds")
    mla_ratio = _median(mla, "whole_matrix_scalar", "total_seconds") / _median(mla, "whole_matrix_numpy_q5", "total_seconds")
    return "\n".join(
        [
            "# Post-Feature-016 Q5_K dense integration",
            "",
            "> One changed variable: exact scalar Q5_K decode versus exact-bit NumPy Q5_K decode. Both modes use one complete matrix read; non-Q5 formats remain scalar.",
            "",
            f"- Evidence source: `{record['source_commit']}` (clean: `{str(not record['source_dirty']).lower()}`)",
            f"- Checkpoint set SHA-256: `{record['checkpoint']['checkpoint_set_sha256']}`",
            f"- Protocol: {record['protocol']['warmups_per_mode']} warm-ups and {record['protocol']['measured_samples_per_mode']} counterbalanced measured samples per mode; OS page cache uncontrolled.",
            "",
            "## Complete Q5_K matrix",
            "",
            f"`{matrix['identity']['tensor']}` ({matrix['identity']['shape_rows_cols'][0]}x{matrix['identity']['shape_rows_cols'][1]}), exact f32 bits across modes.",
            "",
            "| Mode | Storage (s) | Decode (s) | Buffer (s) | MLX build/eval (s) | Matvec (s) | Total (s) |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            _row(matrix, "whole-matrix scalar", "whole_matrix_scalar"),
            _row(matrix, "whole-matrix NumPy Q5_K", "whole_matrix_numpy_q5"),
            "",
            f"Median total ratio: **{matrix_ratio:.2f}x**.",
            "",
            "## Complete layer-3 MLA boundary",
            "",
            f"The captured 2-D path contains {mla['captured_operation_contract']['q5_vectorized_count']} Q5_K projections and {mla['captured_operation_contract']['other_scalar_count']} non-Q5 scalar projections. Per-head 3-D Q8_0 work remains in the uninstrumented residual. Output matched exact f32 bits.",
            "",
            "| Mode | Storage (s) | Decode (s) | Buffer (s) | MLX build/eval (s) | Matvec (s) | Total (s) |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            _row(mla, "whole-matrix scalar", "whole_matrix_scalar"),
            _row(mla, "Q5_K NumPy; other scalar", "whole_matrix_numpy_q5"),
            "",
            f"Median total ratio: **{mla_ratio:.2f}x**. Median uninstrumented residual changed from {_median(mla, 'whole_matrix_scalar', 'uninstrumented_residual_seconds'):.6f} s to {_median(mla, 'whole_matrix_numpy_q5', 'uninstrumented_residual_seconds'):.6f} s and is not attributed to a specific cause.",
            "",
            "This does not establish a complete transformer-layer, stack, token-generation, Q8_0/Q6_K, Rust, or Metal speedup.",
            "",
        ]
    )


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
