#!/usr/bin/env python3
"""Derive the exact layer-8 IQ2_S integration comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from analyze_glm52_moe_q2_integration import _medians, _quant_medians, _unique

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "docs/research/glm52/raw/post-f016-moe-stage-profile-0001.json"
CANDIDATE = ROOT / "docs/research/glm52/raw/post-f016-moe-layer8-iq2-s-0001.json"
JSON_OUT = ROOT / "docs/research/glm52/raw/post-f016-moe-layer8-iq2-s-analysis-0001.json"
TABLE_OUT = ROOT / "docs/research/glm52/tables/post-f016-moe-layer8-iq2-s-0001.md"


def _layer8(record: dict) -> dict:
    matches = [layer for layer in record["layers"] if layer["layer"] == 8]
    if len(matches) != 1:
        raise ValueError("record must contain exactly one layer-8 boundary")
    return matches[0]


def build() -> dict:
    baseline_bytes, candidate_bytes = BASELINE.read_bytes(), CANDIDATE.read_bytes()
    baseline = json.loads(baseline_bytes, object_pairs_hook=_unique)
    candidate = json.loads(candidate_bytes, object_pairs_hook=_unique)
    for label, record in (("baseline", baseline), ("candidate", candidate)):
        if record["actual_status"] != "passed" or record["source_dirty"]:
            raise ValueError(f"{label} is not a clean passing record")
    if candidate["protocol"]["layers"] != [8] or candidate["protocol"]["untimed_reference_decoder_mode"] != "scalar_reference":
        raise ValueError("candidate protocol changed")
    layer = _layer8(candidate)
    if not layer["process_first_comparison"]["exact_f32_bits"] or any(sample["output_f32_sha256"] != layer["reference_output_f32_sha256"] for sample in layer["measured"]):
        raise ValueError("candidate differs from scalar reference")
    baseline_medians, candidate_medians = _medians(_layer8(baseline)), _medians(layer)
    return {
        "schema": "pulsarmlx.research.glm52-moe-iq2-s-integration-analysis",
        "schema_version": "1.0.0",
        "actual_status": "passed",
        "baseline": {"record": str(BASELINE.relative_to(ROOT)), "sha256": hashlib.sha256(baseline_bytes).hexdigest(), "source_commit": baseline["source_commit"], "medians": baseline_medians},
        "candidate": {"record": str(CANDIDATE.relative_to(ROOT)), "sha256": hashlib.sha256(candidate_bytes).hexdigest(), "source_commit": candidate["source_commit"], "medians": candidate_medians, "quantization_ranking": _quant_medians(layer)},
        "boundary_speedup": baseline_medians["total_seconds"] / candidate_medians["total_seconds"],
        "exact_f32_bits_against_scalar_reference": True,
        "retained_samples": len(layer["measured"]),
        "cpu_fallbacks": layer["cache_end"]["cpu_fallbacks"],
        "evictions": layer["cache_end"]["evictions"],
        "resource_levels": sorted({sample[side]["level"] for sample in layer["measured"] for side in ("resource_before", "resource_after")}),
        "next_measured_gate": "exact whole-matrix IQ4_XS decoder qualification and layer-8 integration",
        "feature_018_kernel_selected": False,
        "claim_boundary": "One bounded layer-8 MoE boundary; not sequential full-stack activation, P1/P2, token latency, Rust, or Metal.",
    }


def render(record: dict) -> str:
    baseline, candidate = record["baseline"]["medians"], record["candidate"]["medians"]
    fields = (("MoE boundary", "total_seconds"), ("Storage", "storage_read_seconds"), ("Decode", "dequant_seconds"), ("Buffer", "contiguous_buffer_seconds"), ("MLX construct", "mlx_matrix_construct_seconds"), ("MLX eval", "mlx_matrix_eval_seconds"), ("MLX matvec", "mlx_matvec_seconds"), ("Cleanup", "cleanup_seconds"), ("SwiGLU", "activation_swiglu_seconds"), ("Residual", "uninstrumented_residual_seconds"))
    stage_lines = [f"| {label} | {baseline[key]:.6f} | {candidate[key]:.6f} |" for label, key in fields]
    quant_lines = [f"| {row['quantization']} | {row['median_attributed_seconds']:.6f} | {row['median_components']['dequant_seconds']:.6f} | {row['median_components']['contiguous_buffer_seconds']:.6f} | {row['median_components']['mlx_matvec_seconds']:.6f} |" for row in record["candidate"]["quantization_ranking"]]
    return "\n".join([
        "# Layer-8 IQ2_S MoE integration", "", "> One bounded layer-local MoE boundary; not P1/P2 or token latency.", "",
        f"- Exact f32 bits against scalar-reference MoE: `{str(record['exact_f32_bits_against_scalar_reference']).lower()}`",
        f"- Median boundary ratio: **{record['boundary_speedup']:.2f}x**", "",
        "| Stage | Baseline median (s) | IQ2_S candidate median (s) |", "| --- | ---: | ---: |", *stage_lines, "",
        "## Candidate expert quantization medians", "", "| Quant | Attributed (s) | Decode (s) | Buffer (s) | Matvec (s) |", "| --- | ---: | ---: | ---: | ---: |", *quant_lines, "",
        "IQ4_XS is now the dominant measured layer-8 routed-expert cost. The next gate is exact IQ4_XS qualification; no Metal kernel is selected.", "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args()
    record = build(); json_text = json.dumps(record, indent=2, sort_keys=True) + "\n"; table_text = render(record)
    if args.check:
        if not JSON_OUT.exists() or JSON_OUT.read_text() != json_text: raise SystemExit("generated IQ2_S integration analysis is stale")
        if not TABLE_OUT.exists() or TABLE_OUT.read_text() != table_text: raise SystemExit("generated IQ2_S integration table is stale")
    else:
        JSON_OUT.write_text(json_text); TABLE_OUT.write_text(table_text)
    return 0


if __name__ == "__main__": raise SystemExit(main())
