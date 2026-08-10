#!/usr/bin/env python3
"""Derive the post-IQ3 bounded hotspot profile from committed evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAYER_RAW = ROOT / "docs/research/glm52/raw/f018-iq2-iq3-complete-layer3-0001.json"
MOE_RAW = ROOT / "docs/research/glm52/raw/f018-iq2-iq3-moe-layer3-0001.json"
DEFAULT_JSON = ROOT / "docs/research/glm52/raw/f018-iq3-post-layer-hotspots-0001.json"
DEFAULT_TABLE = ROOT / "docs/research/glm52/tables/f018-iq3-post-layer-hotspots-0001.md"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def derive() -> dict:
    layer = json.loads(LAYER_RAW.read_text())
    moe = json.loads(MOE_RAW.read_text())
    layer_summary = layer["direct_summaries"]["layer"]
    moe_summary = moe["direct_summaries"]
    layer_total = float(layer_summary["total_seconds"]["median_seconds"])
    components = [
        ("dense_trunk_dequant", layer_summary["dense_dequant_seconds"]["median_seconds"], "complete_layer"),
        ("moe_boundary", layer_summary["moe_seconds"]["median_seconds"], "complete_layer"),
        ("direct_iq2_gate_up_synchronized", moe_summary["direct_iq2.total_seconds"]["median_seconds"], "moe"),
        ("direct_iq3_down_synchronized", moe_summary["direct_iq3.total_seconds"]["median_seconds"], "moe"),
        ("router", moe_summary["router_seconds"]["median_seconds"], "moe"),
        ("dense_trunk_matvec", layer_summary["dense_matvec_seconds"]["median_seconds"], "complete_layer"),
        ("dense_trunk_build", layer_summary["dense_build_seconds"]["median_seconds"], "complete_layer"),
        ("layer_boundary_overhead", layer_summary["boundary_overhead_seconds"]["median_seconds"], "complete_layer"),
        ("dense_trunk_storage", layer_summary["dense_storage_seconds"]["median_seconds"], "complete_layer"),
        ("shared_reference", moe_summary["shared_reference.total_seconds"]["median_seconds"], "moe"),
        ("routed_activation", moe_summary["routed_activation_seconds"]["median_seconds"], "moe"),
        ("routed_aggregation", moe_summary["routed_aggregation_seconds"]["median_seconds"], "moe"),
    ]
    ranking = [
        {
            "rank": rank,
            "component": name,
            "median_seconds": float(seconds),
            "fraction_of_complete_layer_median": float(seconds) / layer_total,
            "scope": scope,
        }
        for rank, (name, seconds, scope) in enumerate(
            sorted(components, key=lambda row: float(row[1]), reverse=True), start=1
        )
    ]
    return {
        "schema": "pulsarmlx.research.f018-iq3-post-layer-hotspots",
        "schema_version": "1.0.0",
        "actual_status": "passed",
        "inputs": [
            {"path": "docs/research/glm52/raw/f018-iq2-iq3-complete-layer3-0001.json", "sha256": _sha(LAYER_RAW)},
            {"path": "docs/research/glm52/raw/f018-iq2-iq3-moe-layer3-0001.json", "sha256": _sha(MOE_RAW)},
        ],
        "source_commit": layer["source"]["commit"],
        "complete_layer_median_seconds": layer_total,
        "attention_median_seconds": float(layer_summary["attention_seconds"]["median_seconds"]),
        "moe_median_seconds": float(layer_summary["moe_seconds"]["median_seconds"]),
        "ranking": ranking,
        "decision": {
            "third_kernel_selected": False,
            "reason": "Measured complete-layer dense/trunk dequantization is larger than either direct expert quantized component; no third Metal kernel is selected from one layer.",
            "optional_p1_admitted": True,
            "optional_p1_reason": "The complete-layer direct candidate passed numerically and reduced the same-boundary median from 2.677491229 to 0.950992354 seconds.",
        },
        "unsupported_interpretations": [
            "79-layer or token hotspot ranking",
            "general tokens per second",
            "third-kernel selection",
            "production performance",
        ],
    }


def render(record: dict) -> str:
    return "\n".join(
        [
            "# Feature 018 post-IQ3 bounded hotspot profile",
            "",
            "> Derived from one complete layer-3 and one layer-3 MoE population; not a full-stack profile.",
            "",
            f"- Complete-layer median: `{record['complete_layer_median_seconds']:.9f}` s",
            f"- Attention median: `{record['attention_median_seconds']:.9f}` s",
            f"- MoE median: `{record['moe_median_seconds']:.9f}` s",
            "",
            "| Rank | Component | Scope | Median (s) | Layer fraction |",
            "| ---: | --- | --- | ---: | ---: |",
            *(
                f"| {row['rank']} | {row['component']} | {row['scope']} | {row['median_seconds']:.9f} | {row['fraction_of_complete_layer_median']:.2%} |"
                for row in record["ranking"]
            ),
            "",
            "No third direct-quantized kernel is selected. The one-layer profile places dense/trunk dequantization above either direct expert quantized component, so the clean optional P1 is admitted to establish the next full-stack ranking.",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    record = derive()
    raw = json.dumps(record, indent=2, sort_keys=True) + "\n"
    table = render(record)
    if args.check:
        if args.json.read_text() != raw or args.table.read_text() != table:
            raise SystemExit("post-IQ3 hotspot artifacts differ")
    else:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.table.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(raw)
        args.table.write_text(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
