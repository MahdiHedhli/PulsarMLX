#!/usr/bin/env python3
"""Generate the exact Q6_K dense-integration comparison table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "docs/research/glm52/raw/post-f016-trunk-q6-integration-0001.json"
DEFAULT_TABLE = ROOT / "docs/research/glm52/tables/post-f016-trunk-q6-integration-0001.md"
BASELINE = "whole_matrix_numpy_q5_q8_head_numpy"
CANDIDATE = "whole_matrix_numpy_q5_q8_q6_head_numpy"


def _median(boundary: dict, mode: str, field: str) -> float:
    return float(boundary["summaries"][mode][field]["median_seconds"])


def _row(boundary: dict, label: str, mode: str) -> str:
    return (
        f"| {label} | {_median(boundary, mode, 'storage_read_seconds'):.6f} | "
        f"{_median(boundary, mode, 'dequant_seconds'):.6f} | "
        f"{_median(boundary, mode, 'contiguous_buffer_seconds'):.6f} | "
        f"{_median(boundary, mode, 'mlx_matrix_build_seconds'):.6f} | "
        f"{_median(boundary, mode, 'mlx_matvec_seconds'):.6f} | "
        f"{_median(boundary, mode, 'uninstrumented_residual_seconds'):.6f} | "
        f"{_median(boundary, mode, 'total_seconds'):.6f} |"
    )


def _candidate_counts(record: dict) -> dict[str, int]:
    operations = record["representative_mla_layer"]["samples"][CANDIDATE][0]["dense_2d"]["operations"]
    return {
        "operation_count": len(operations),
        "q5_vectorized_count": sum(op["decoder_mode"] == "numpy_vectorized_q5_k" for op in operations),
        "q8_vectorized_count": sum(op["decoder_mode"] == "numpy_vectorized_q8_0" for op in operations),
        "q6_vectorized_count": sum(op["decoder_mode"] == "numpy_vectorized_q6_k" for op in operations),
        "other_scalar_count": sum(op["decoder_mode"] == "scalar_reference" for op in operations),
    }


def render(record: dict) -> str:
    baseline, candidate = BASELINE, CANDIDATE
    matrix = record["matrix"]
    mla = record["representative_mla_layer"]
    counts = _candidate_counts(record)
    matrix_ratio = _median(matrix, baseline, "total_seconds") / _median(matrix, candidate, "total_seconds")
    mla_ratio = _median(mla, baseline, "total_seconds") / _median(mla, candidate, "total_seconds")
    return "\n".join([
        "# Post-Feature-016 Q6_K dense integration", "",
        f"> One changed variable: {record['protocol']['changed_variable']}.", "",
        f"- Evidence source: `{record['source_commit']}` (clean: `{str(not record['source_dirty']).lower()}`)",
        f"- Checkpoint set SHA-256: `{record['checkpoint']['checkpoint_set_sha256']}`",
        f"- Protocol: {record['protocol']['warmups_per_mode']} warm-ups and {record['protocol']['measured_samples_per_mode']} counterbalanced measured samples per mode; OS page cache uncontrolled.", "",
        "## Complete Q6_K matrix", "",
        f"`{matrix['identity']['tensor']}` ({matrix['identity']['shape_rows_cols'][0]}x{matrix['identity']['shape_rows_cols'][1]}), exact f32 output bits across modes.", "",
        "| Mode | Storage (s) | Decode (s) | Buffer (s) | MLX build/eval (s) | Matvec (s) | Total (s) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| scalar Q6_K; Q5/Q8 vector | {_median(matrix, baseline, 'storage_read_seconds'):.6f} | {_median(matrix, baseline, 'dequant_seconds'):.6f} | {_median(matrix, baseline, 'contiguous_buffer_seconds'):.6f} | {_median(matrix, baseline, 'mlx_matrix_build_seconds'):.6f} | {_median(matrix, baseline, 'mlx_matvec_seconds'):.6f} | {_median(matrix, baseline, 'total_seconds'):.6f} |",
        f"| NumPy Q6_K; Q5/Q8 vector | {_median(matrix, candidate, 'storage_read_seconds'):.6f} | {_median(matrix, candidate, 'dequant_seconds'):.6f} | {_median(matrix, candidate, 'contiguous_buffer_seconds'):.6f} | {_median(matrix, candidate, 'mlx_matrix_build_seconds'):.6f} | {_median(matrix, candidate, 'mlx_matvec_seconds'):.6f} | {_median(matrix, candidate, 'total_seconds'):.6f} |",
        "", f"Median total ratio: **{matrix_ratio:.2f}x**.", "",
        "## Complete layer-8 MLA boundary", "",
        f"The retained operation list contains {counts['operation_count']} dense operations: {counts['q8_vectorized_count']} Q8_0 and {counts['q6_vectorized_count']} Q6_K vector operations, with {counts['other_scalar_count']} scalar operations. The raw record's legacy `captured_operation_contract` omits the Q6 count and its legacy scope label says four 2-D operations; validation derives this corrected audit from the immutable nested samples rather than rewriting them.", "",
        "| Mode | Storage (s) | Decode (s) | Buffer (s) | MLX build/eval (s) | Matvec (s) | Uninstrumented residual (s) | Total (s) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        _row(mla, "scalar Q6_K; Q5/Q8 vector", baseline),
        _row(mla, "NumPy Q6_K; Q5/Q8 vector", candidate),
        "", f"Median total ratio: **{mla_ratio:.2f}x**, with exact f32 output bits.", "",
        "This is a bounded single-position MLA result, not a complete transformer layer, stack, token, Rust, or Metal claim.", "",
    ])


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
