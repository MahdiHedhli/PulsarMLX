#!/usr/bin/env python3
"""Derive the combined layer-78 Q2_K/Q3_K integration comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from analyze_glm52_moe_q2_integration import _layer, _medians, _quant_medians, _unique

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "docs/research/glm52/raw/post-f016-moe-stage-profile-0001.json"
Q2_ONLY = ROOT / "docs/research/glm52/raw/post-f016-moe-layer78-q2-0001.json"
CANDIDATE = ROOT / "docs/research/glm52/raw/post-f016-moe-layer78-q2-q3-0001.json"
JSON_OUT = ROOT / "docs/research/glm52/raw/post-f016-moe-layer78-q2-q3-analysis-0001.json"
TABLE_OUT = ROOT / "docs/research/glm52/tables/post-f016-moe-layer78-q2-q3-0001.md"


def _source(path: Path):
    payload = path.read_bytes()
    return payload, json.loads(payload, object_pairs_hook=_unique)


def build() -> dict:
    baseline_bytes, baseline = _source(BASELINE)
    q2_bytes, q2 = _source(Q2_ONLY)
    candidate_bytes, candidate = _source(CANDIDATE)
    for label, record in (("baseline", baseline), ("q2", q2), ("candidate", candidate)):
        if record["actual_status"] != "passed" or record["source_dirty"]:
            raise ValueError(f"{label} is not a clean passing record")
    if candidate["protocol"]["layers"] != [78] or candidate["protocol"]["untimed_reference_decoder_mode"] != "scalar_reference":
        raise ValueError("candidate protocol changed")
    candidate_layer = _layer(candidate)
    if not candidate_layer["process_first_comparison"]["exact_f32_bits"]:
        raise ValueError("candidate differs from scalar reference")
    if any(sample["output_f32_sha256"] != candidate_layer["reference_output_f32_sha256"] for sample in candidate_layer["measured"]):
        raise ValueError("retained candidate differs from scalar reference")
    stages = {
        "baseline": _medians(_layer(baseline)),
        "q2_only": _medians(_layer(q2)),
        "q2_q3": _medians(candidate_layer),
    }
    return {
        "schema": "pulsarmlx.research.glm52-moe-q2-q3-integration-analysis",
        "schema_version": "1.0.0",
        "actual_status": "passed",
        "sources": {
            "baseline": {"record": str(BASELINE.relative_to(ROOT)), "sha256": hashlib.sha256(baseline_bytes).hexdigest(), "source_commit": baseline["source_commit"]},
            "q2_only": {"record": str(Q2_ONLY.relative_to(ROOT)), "sha256": hashlib.sha256(q2_bytes).hexdigest(), "source_commit": q2["source_commit"]},
            "q2_q3": {"record": str(CANDIDATE.relative_to(ROOT)), "sha256": hashlib.sha256(candidate_bytes).hexdigest(), "source_commit": candidate["source_commit"]},
        },
        "stage_medians": stages,
        "candidate_quantization_ranking": _quant_medians(candidate_layer),
        "baseline_to_candidate_speedup": stages["baseline"]["total_seconds"] / stages["q2_q3"]["total_seconds"],
        "q2_to_q2_q3_speedup": stages["q2_only"]["total_seconds"] / stages["q2_q3"]["total_seconds"],
        "exact_f32_bits_against_scalar_reference": True,
        "retained_samples": len(candidate_layer["measured"]),
        "cpu_fallbacks": candidate_layer["cache_end"]["cpu_fallbacks"],
        "evictions": candidate_layer["cache_end"]["evictions"],
        "resource_levels": sorted({sample[side]["level"] for sample in candidate_layer["measured"] for side in ("resource_before", "resource_after")}),
        "next_measured_gate": "exact whole-matrix IQ2_S decoder qualification and layer-8 integration",
        "feature_018_kernel_selected": False,
        "claim_boundary": "One bounded layer-78 MoE boundary; not a sequential full-stack layer activation, P1/P2, token latency, Rust, or Metal result.",
    }


def render(record: dict) -> str:
    stages = record["stage_medians"]
    fields = (
        ("MoE boundary", "total_seconds"), ("Storage", "storage_read_seconds"),
        ("Decode", "dequant_seconds"), ("Contiguous buffer", "contiguous_buffer_seconds"),
        ("MLX construct", "mlx_matrix_construct_seconds"), ("MLX eval", "mlx_matrix_eval_seconds"),
        ("MLX matvec", "mlx_matvec_seconds"), ("Cleanup", "cleanup_seconds"),
        ("SwiGLU", "activation_swiglu_seconds"), ("Uninstrumented residual", "uninstrumented_residual_seconds"),
    )
    stage_lines = [f"| {label} | {stages['baseline'][key]:.6f} | {stages['q2_only'][key]:.6f} | {stages['q2_q3'][key]:.6f} |" for label, key in fields]
    quant_lines = [
        f"| {row['quantization']} | {row['median_attributed_seconds']:.6f} | {row['median_components']['dequant_seconds']:.6f} | {row['median_components']['mlx_matrix_construct_seconds'] + row['median_components']['mlx_matrix_eval_seconds']:.6f} | {row['median_components']['mlx_matvec_seconds']:.6f} |"
        for row in record["candidate_quantization_ranking"]
    ]
    return "\n".join(
        [
            "# Layer-78 combined Q2_K/Q3_K MoE integration", "",
            "> One bounded layer-local MoE boundary; not P1/P2 or token latency.", "",
            f"- Exact f32 bits against scalar-reference MoE: `{str(record['exact_f32_bits_against_scalar_reference']).lower()}`",
            f"- Baseline-to-candidate median ratio: **{record['baseline_to_candidate_speedup']:.2f}x**",
            f"- Q2-only-to-candidate median ratio: **{record['q2_to_q2_q3_speedup']:.2f}x**", "",
            "| Stage | Baseline (s) | Q2_K only (s) | Q2_K + Q3_K (s) |",
            "| --- | ---: | ---: | ---: |", *stage_lines, "",
            "## Candidate expert quantization medians", "",
            "| Quant | Attributed (s) | Decode (s) | Build/eval (s) | Matvec (s) |",
            "| --- | ---: | ---: | ---: | ---: |", *quant_lines, "",
            "Layer 8's scalar IQ2_S/IQ4_XS path is now the largest measured bounded MoE opportunity. The next gate is IQ2_S exact qualification; no Metal kernel is selected.", "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    record = build()
    json_text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    table_text = render(record)
    if args.check:
        if not JSON_OUT.exists() or JSON_OUT.read_text() != json_text:
            raise SystemExit("generated combined Q2_K/Q3_K analysis is stale")
        if not TABLE_OUT.exists() or TABLE_OUT.read_text() != table_text:
            raise SystemExit("generated combined Q2_K/Q3_K table is stale")
    else:
        JSON_OUT.write_text(json_text)
        TABLE_OUT.write_text(table_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
