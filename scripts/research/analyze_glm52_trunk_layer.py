#!/usr/bin/env python3
"""Audit and summarize the retained complete layer-8 trunk experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "docs/research/glm52/raw/post-f016-trunk-complete-layer8-q6-attempt-0001.json"
DEFAULT_AUDIT = ROOT / "docs/research/glm52/raw/post-f016-trunk-complete-layer8-q6-audit-0001.json"
DEFAULT_TABLE = ROOT / "docs/research/glm52/tables/post-f016-trunk-complete-layer8-q6-0001.md"
BASELINE = "whole_matrix_numpy_q5_q8_head_numpy"
CANDIDATE = "whole_matrix_numpy_q5_q8_q6_head_numpy"


def _median(record: dict, mode: str, field: str) -> float:
    return float(record["summaries"][mode][field]["median_seconds"])


def derive(record: dict, source_bytes: bytes) -> dict:
    modes = record["protocol"]["dense_modes"]
    if modes != [BASELINE, CANDIDATE]:
        raise ValueError("unexpected dense modes")
    if record["source_dirty"] or record["source_commit"] != "7abcce2a3448c63df1226a2594734db630c42d9a":
        raise ValueError("measurement source identity mismatch")
    if record["actual_status"] != "failed" or not record["comparison"]["exact_f32_bits"]:
        raise ValueError("expected the retained gate-only rejection with exact output")
    mode_audits = {}
    for mode in modes:
        samples = record["samples"][mode]
        if len(samples) != 10:
            raise ValueError("expected ten retained samples per mode")
        checks = {
            "shared_cache_hits_are_three": all(s["shared_cache_hits"] == 3 for s in samples),
            "transient_routed_matrix_misses_are_twenty_four": all(s["shared_cache_misses"] == 24 for s in samples),
            "three_shared_entries_resident": all(s["resident_entries_end"] == 3 for s in samples),
            "expert_decoder_fixed_vectorized": all(s["expert_decoder_mode"] == "numpy_vectorized" for s in samples),
            "resource_pressure_normal": all(s["resource_after"]["level"] == "normal" for s in samples),
            "one_deterministic_midpoint": len({s["mid_f32_sha256"] for s in samples}) == 1,
            "one_deterministic_output": len({s["output_f32_sha256"] for s in samples}) == 1,
            "one_deterministic_route": len({tuple(s["route"]["expert_ids"]) for s in samples}) == 1,
        }
        if not all(checks.values()):
            raise ValueError(f"semantic audit failed for {mode}")
        mode_audits[mode] = checks
    if record["comparison"]["mid_hashes"][BASELINE] != record["comparison"]["mid_hashes"][CANDIDATE]:
        raise ValueError("attention midpoint differs across modes")
    if record["comparison"]["output_hashes"][BASELINE] != record["comparison"]["output_hashes"][CANDIDATE]:
        raise ValueError("complete-layer output differs across modes")
    if record["comparison"]["route_expert_ids"][BASELINE] != record["comparison"]["route_expert_ids"][CANDIDATE]:
        raise ValueError("route differs across modes")
    baseline_total = _median(record, BASELINE, "total_seconds")
    candidate_total = _median(record, CANDIDATE, "total_seconds")
    return {
        "schema": "pulsarmlx.research.glm52-trunk-complete-layer-audit",
        "schema_version": "1.0.0",
        "actual_status": "passed",
        "measurement_record": "docs/research/glm52/raw/post-f016-trunk-complete-layer8-q6-attempt-0001.json",
        "measurement_record_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "measurement_source_commit": record["source_commit"],
        "measurement_source_clean": not record["source_dirty"],
        "gate_correction": {
            "rejected_condition": "shared_cache_misses == 0",
            "correct_condition": "shared_cache_misses == 24",
            "reason": "eight routed experts use three transient matrices each; the three protected shared matrices are hits",
            "measurement_rerun_required": False,
        },
        "comparison": record["comparison"],
        "mode_audits": mode_audits,
        "metrics": {
            "baseline_total_median_seconds": baseline_total,
            "candidate_total_median_seconds": candidate_total,
            "median_total_ratio": baseline_total / candidate_total,
            "baseline_attention_median_seconds": _median(record, BASELINE, "attention_seconds"),
            "candidate_attention_median_seconds": _median(record, CANDIDATE, "attention_seconds"),
            "baseline_moe_median_seconds": _median(record, BASELINE, "moe_seconds"),
            "candidate_moe_median_seconds": _median(record, CANDIDATE, "moe_seconds"),
            "baseline_dense_attributed_median_seconds": _median(record, BASELINE, "dense_attributed_seconds"),
            "candidate_dense_attributed_median_seconds": _median(record, CANDIDATE, "dense_attributed_seconds"),
            "baseline_uninstrumented_residual_median_seconds": _median(record, BASELINE, "uninstrumented_residual_seconds"),
            "candidate_uninstrumented_residual_median_seconds": _median(record, CANDIDATE, "uninstrumented_residual_seconds"),
            "baseline_cleanup_median_seconds": _median(record, BASELINE, "cleanup_seconds"),
            "candidate_cleanup_median_seconds": _median(record, CANDIDATE, "cleanup_seconds"),
        },
        "scope": "one complete single-position layer-8 MLA plus top-8/shared MoE boundary",
        "unsupported_interpretations": [
            "stack, P1, token-generation, or steady-state throughput",
            "Rust or direct quantized Metal evidence",
        ],
    }


def render_table(audit: dict) -> str:
    m = audit["metrics"]
    return "\n".join([
        "# Post-Feature-016 complete layer-8 trunk comparison", "",
        "> The original attempt is retained with `actual_status: failed` because its harness incorrectly required zero routed-matrix misses. This deterministic audit corrects only that semantic gate; it does not alter or rerun the samples.", "",
        f"- Measurement source: `{audit['measurement_source_commit']}` (clean: `{str(audit['measurement_source_clean']).lower()}`)",
        f"- Retained record SHA-256: `{audit['measurement_record_sha256']}`",
        "- Correct cache contract: three protected shared-matrix hits and 24 transient routed-matrix misses per warm layer.", "",
        "| Mode | Attention (s) | MoE (s) | Dense attributed (s) | Uninstrumented residual (s) | Cleanup (s) | Complete layer (s) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| scalar Q6_K; Q5/Q8 vector | {m['baseline_attention_median_seconds']:.6f} | {m['baseline_moe_median_seconds']:.6f} | {m['baseline_dense_attributed_median_seconds']:.6f} | {m['baseline_uninstrumented_residual_median_seconds']:.6f} | {m['baseline_cleanup_median_seconds']:.6f} | {m['baseline_total_median_seconds']:.6f} |",
        f"| NumPy Q6_K; Q5/Q8 vector | {m['candidate_attention_median_seconds']:.6f} | {m['candidate_moe_median_seconds']:.6f} | {m['candidate_dense_attributed_median_seconds']:.6f} | {m['candidate_uninstrumented_residual_median_seconds']:.6f} | {m['candidate_cleanup_median_seconds']:.6f} | {m['candidate_total_median_seconds']:.6f} |",
        "", f"Median complete-layer ratio: **{m['median_total_ratio']:.2f}x**. Attention midpoint, top-8 route, and complete-layer f32 output were exact and deterministic across modes.", "",
        "This is one complete single-position layer-8 boundary, not a stack, P1, token-generation, Rust, or Metal claim.", "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source_bytes = args.source.read_bytes()
    audit = derive(json.loads(source_bytes), source_bytes)
    audit_text = json.dumps(audit, indent=2, sort_keys=True) + "\n"
    table_text = render_table(audit)
    if args.check:
        if not args.audit.exists() or args.audit.read_text() != audit_text:
            raise SystemExit(f"generated audit is stale: {args.audit}")
        if not args.table.exists() or args.table.read_text() != table_text:
            raise SystemExit(f"generated table is stale: {args.table}")
        return 0
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.table.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(audit_text)
    args.table.write_text(table_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
