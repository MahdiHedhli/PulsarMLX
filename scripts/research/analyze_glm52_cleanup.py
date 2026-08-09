#!/usr/bin/env python3
"""Generate the bounded cleanup-cadence comparison table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "docs/research/glm52/raw/post-f016-trunk-cleanup-0001.json"
DEFAULT_TABLE = ROOT / "docs/research/glm52/tables/post-f016-trunk-cleanup-0001.md"


def render(record: dict) -> str:
    cleanup_only = record["cleanup_only"]["summary"]
    current = record["current_cleanup_each_operation"]["summaries"]
    batched = record["batched_cleanup"]
    return "\n".join([
        "# Post-Feature-016 cleanup cadence study", "",
        "> One changed variable: cleanup cadence. A decoded Q6_K MLX matrix, activation, matvec, and synchronized output remained fixed.", "",
        f"- Evidence source: `{record['source_commit']}` (clean: `{str(not record['source_dirty']).lower()}`)",
        f"- Checkpoint set SHA-256: `{record['checkpoint']['checkpoint_set_sha256']}`",
        f"- Protocol: {record['protocol']['warmups']} warm-ups and {record['protocol']['measured_operations_per_mode']} measured matvecs; batch interval {record['protocol']['batched_cleanup_interval']}.", "",
        "| Mode | Matvec median (s) | Cleanup median/event (s) | Amortized cleanup/op (s) | Operation total median (s) |",
        "| --- | ---: | ---: | ---: | ---: |",
        f"| cleanup only | n/a | {cleanup_only['median_seconds']:.6f} | {cleanup_only['mean_seconds']:.6f} | n/a |",
        f"| cleanup every operation | {current['matvec_seconds']['median_seconds']:.6f} | {current['cleanup_seconds']['median_seconds']:.6f} | {current['cleanup_seconds']['mean_seconds']:.6f} | {current['total_seconds']['median_seconds']:.6f} |",
        f"| cleanup every five operations | {batched['summaries']['matvec_seconds']['median_seconds']:.6f} | {batched['cleanup_event_summary']['median_seconds']:.6f} | {batched['amortized_cleanup_seconds_per_operation']:.6f} | {batched['summaries']['total_seconds']['median_seconds']:.6f} |", "",
        "Both matvec modes produced the same exact deterministic output and retained normal memory pressure. Batching reduced cleanup frequency in this retained-matrix fixture; it does not authorize cleanup removal or establish that a layer-wide lifetime is safe.", "",
        "Per-operation totals exclude the subsequent resource-sampling call. The separately retained batch population wall includes that instrumentation and is not used as an optimization result.", "",
        "This is a cleanup microbenchmark, not complete-layer, P1, token, production cadence, Rust, or Metal evidence.", "",
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
