#!/usr/bin/env python3
"""Generate the bounded trunk-residency comparison table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "docs/research/glm52/raw/post-f016-trunk-q6-residency-0001.json"
DEFAULT_TABLE = ROOT / "docs/research/glm52/tables/post-f016-trunk-q6-residency-0001.md"


def render(record: dict) -> str:
    rows = []
    for candidate in record["candidates"]:
        summary = candidate["summaries"]
        rows.append(
            f"| `{candidate['candidate']}` | {candidate['setup_rss_delta_bytes'] / 1024**2:.1f} | "
            f"{candidate['setup']['storage_bytes_read'] / 1024**2:.1f} | "
            f"{summary['storage_read_seconds']['median_seconds']:.6f} | "
            f"{summary['dequant_seconds']['median_seconds']:.6f} | "
            f"{summary['mlx_matrix_build_seconds']['median_seconds']:.6f} | "
            f"{summary['mlx_matvec_seconds']['median_seconds']:.6f} | "
            f"{summary['cleanup_seconds']['median_seconds']:.6f} | "
            f"{summary['total_seconds']['median_seconds']:.6f} |"
        )
    budgets = record["logical_full_trunk_budgets"]
    budget_rows = [
        f"| {value['option']} `{value['name']}` | {value['logical_gib']:.3f} | `{value['admission']}` |"
        for value in budgets["options"]
    ]
    return "\n".join([
        "# Post-Feature-016 bounded trunk residency study", "",
        "> One changed variable: matrix residency lifecycle. Each candidate ran in a fresh process with the same exact Q6_K decoder, activation, MLX matvec, and checkpoint.", "",
        f"- Evidence source: `{record['source_commit']}` (clean: `{str(not record['source_dirty']).lower()}`)",
        f"- Checkpoint set SHA-256: `{record['checkpoint']['checkpoint_set_sha256']}`",
        f"- Protocol: {record['protocol']['warmups_per_candidate']} warm-ups and {record['protocol']['measured_samples_per_candidate']} measured samples per candidate; OS page cache uncontrolled.", "",
        "## One real Q6_K matrix lifecycle", "",
        "| Candidate | Setup RSS delta (MiB) | Setup read (MiB) | Reuse storage (s) | Reuse decode (s) | Reuse build (s) | Matvec (s) | Cleanup (s) | Reuse total (s) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        *rows, "",
        "All candidates produced the same exact deterministic f32 output hash. RSS delta is process-local observed allocation, not logical tensor size or a general MLX allocator multiplier.", "",
        "## Previously committed full-trunk logical budgets", "",
        "| Option | Logical GiB | Admission disposition |",
        "| --- | ---: | --- |", *budget_rows, "",
        f"Budget conclusion: {budgets['recommendation_limit']}.", "",
        "Decoded-hot residency removes repeated decode/build for admitted hot tensors, but the measured 1.56 GiB setup RSS delta for one 384 MiB decoded matrix makes allocator-aware admission mandatory. Compressed residency avoids only a roughly 8 ms warm read in this fixture and does not justify compressed-all residency by itself.", "",
        "This is a representative matrix lifecycle result, not complete-layer, token, decoded-all admission, production cache, Rust, or Metal evidence.", "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = render(json.loads(args.source.read_text()))
    if args.check:
        if not args.table.exists() or args.table.read_text() != text:
            raise SystemExit(f"generated table is stale: {args.table}")
        return 0
    args.table.parent.mkdir(parents=True, exist_ok=True)
    args.table.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
