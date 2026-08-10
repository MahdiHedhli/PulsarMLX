#!/usr/bin/env python3
"""Derive the exact layer-78 Q2_K integration comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "docs/research/glm52/raw/post-f016-moe-stage-profile-0001.json"
CANDIDATE = ROOT / "docs/research/glm52/raw/post-f016-moe-layer78-q2-0001.json"
JSON_OUT = ROOT / "docs/research/glm52/raw/post-f016-moe-layer78-q2-analysis-0001.json"
TABLE_OUT = ROOT / "docs/research/glm52/tables/post-f016-moe-layer78-q2-0001.md"
FIELDS = (
    "storage_read_seconds", "dequant_seconds", "contiguous_buffer_seconds",
    "mlx_matrix_construct_seconds", "mlx_matrix_eval_seconds",
    "mlx_matvec_seconds", "cleanup_seconds",
)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def _median(values) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("empty median population")
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def _layer(record: dict) -> dict:
    matches = [layer for layer in record["layers"] if layer["layer"] == 78]
    if len(matches) != 1:
        raise ValueError("record must contain exactly one layer-78 boundary")
    return matches[0]


def _medians(layer: dict) -> dict:
    summary = layer["summaries"]
    result = {"total_seconds": summary["total_seconds"]["median_seconds"]}
    for field in FIELDS:
        result[field] = summary[f"routed_matrix_stages.{field}"]["median_seconds"]
    result["activation_swiglu_seconds"] = summary["activation_swiglu_seconds"]["median_seconds"]
    result["weighting_seconds"] = summary["weighting_seconds"]["median_seconds"]
    result["uninstrumented_residual_seconds"] = summary["uninstrumented_residual_seconds"]["median_seconds"]
    return result


def _quant_medians(layer: dict) -> list[dict]:
    populations: dict[str, dict[str, list[float]]] = {}
    for sample in layer["measured"]:
        per_sample: dict[str, dict[str, float]] = {}
        experts = sample["detail"]["routed_experts"] + [sample["detail"]["shared_expert"]]
        for expert in experts:
            for event in expert["matrix_events"]:
                bucket = per_sample.setdefault(event["quantization"], {field: 0.0 for field in FIELDS})
                for field in FIELDS:
                    bucket[field] += float(event[field])
        for quant, values in per_sample.items():
            population = populations.setdefault(quant, {field: [] for field in FIELDS})
            for field in FIELDS:
                population[field].append(values[field])
    rows = []
    for quant, population in populations.items():
        medians = {field: _median(values) for field, values in population.items()}
        rows.append({"quantization": quant, "median_attributed_seconds": sum(medians.values()), "median_components": medians})
    rows.sort(key=lambda row: (-row["median_attributed_seconds"], row["quantization"]))
    return rows


def build(baseline_bytes: bytes, baseline: dict, candidate_bytes: bytes, candidate: dict) -> dict:
    for label, record in (("baseline", baseline), ("candidate", candidate)):
        if record["actual_status"] != "passed" or record["source_dirty"]:
            raise ValueError(f"{label} is not a clean passing record")
    if candidate["protocol"]["layers"] != [78] or candidate["protocol"]["untimed_reference_decoder_mode"] != "scalar_reference":
        raise ValueError("candidate protocol changed")
    candidate_layer = _layer(candidate)
    if not candidate_layer["process_first_comparison"]["exact_f32_bits"]:
        raise ValueError("process-first output differs from scalar reference")
    if any(sample["output_f32_sha256"] != candidate_layer["reference_output_f32_sha256"] for sample in candidate_layer["measured"]):
        raise ValueError("retained output differs from scalar reference")
    baseline_medians = _medians(_layer(baseline))
    candidate_medians = _medians(candidate_layer)
    quant = _quant_medians(candidate_layer)
    return {
        "schema": "pulsarmlx.research.glm52-moe-q2-integration-analysis",
        "schema_version": "1.0.0",
        "actual_status": "passed",
        "baseline": {
            "record": "docs/research/glm52/raw/post-f016-moe-stage-profile-0001.json",
            "sha256": hashlib.sha256(baseline_bytes).hexdigest(),
            "source_commit": baseline["source_commit"],
            "medians": baseline_medians,
        },
        "candidate": {
            "record": "docs/research/glm52/raw/post-f016-moe-layer78-q2-0001.json",
            "sha256": hashlib.sha256(candidate_bytes).hexdigest(),
            "source_commit": candidate["source_commit"],
            "medians": candidate_medians,
            "quantization_ranking": quant,
            "exact_f32_bits_against_scalar_reference": True,
            "retained_samples": len(candidate_layer["measured"]),
            "cpu_fallbacks": candidate_layer["cache_end"]["cpu_fallbacks"],
            "evictions": candidate_layer["cache_end"]["evictions"],
            "resource_levels": sorted({sample[side]["level"] for sample in candidate_layer["measured"] for side in ("resource_before", "resource_after")}),
        },
        "boundary_speedup": baseline_medians["total_seconds"] / candidate_medians["total_seconds"],
        "absolute_seconds_reduced": baseline_medians["total_seconds"] - candidate_medians["total_seconds"],
        "next_measured_gate": "exact whole-matrix Q3_K decoder qualification and layer-78 integration",
        "feature_018_kernel_selected": False,
        "claim_boundary": "One bounded layer-78 MoE boundary; not a sequential full-stack layer activation, P1/P2, token latency, Rust, or Metal result.",
    }


def render(record: dict) -> str:
    baseline, candidate = record["baseline"]["medians"], record["candidate"]["medians"]
    fields = (
        ("MoE boundary", "total_seconds"), ("Storage", "storage_read_seconds"),
        ("Decode", "dequant_seconds"), ("Contiguous buffer", "contiguous_buffer_seconds"),
        ("MLX construct", "mlx_matrix_construct_seconds"), ("MLX eval", "mlx_matrix_eval_seconds"),
        ("MLX matvec", "mlx_matvec_seconds"), ("Cleanup", "cleanup_seconds"),
        ("SwiGLU", "activation_swiglu_seconds"), ("Uninstrumented residual", "uninstrumented_residual_seconds"),
    )
    component_lines = [f"| {label} | {baseline[key]:.6f} | {candidate[key]:.6f} |" for label, key in fields]
    quant_lines = [
        f"| {row['quantization']} | {row['median_attributed_seconds']:.6f} | {row['median_components']['dequant_seconds']:.6f} | {row['median_components']['contiguous_buffer_seconds']:.6f} | {row['median_components']['mlx_matvec_seconds']:.6f} |"
        for row in record["candidate"]["quantization_ranking"]
    ]
    return "\n".join(
        [
            "# Layer-78 Q2_K MoE integration", "",
            "> One bounded layer-local MoE boundary; not P1/P2 or token latency.", "",
            f"- Baseline source: `{record['baseline']['source_commit']}`",
            f"- Candidate source: `{record['candidate']['source_commit']}`",
            "- Exact f32 bits against scalar-reference MoE: `true`",
            f"- Median boundary ratio: **{record['boundary_speedup']:.2f}x**", "",
            "| Stage | Baseline median (s) | Q2_K candidate median (s) |",
            "| --- | ---: | ---: |", *component_lines, "",
            "## Candidate expert quantization medians", "",
            "| Quant | Attributed (s) | Decode (s) | Buffer (s) | Matvec (s) |",
            "| --- | ---: | ---: | ---: | ---: |", *quant_lines, "",
            "Q3_K is now the dominant measured routed-expert cost. The next bounded gate is exact Q3_K whole-matrix qualification and integration; no Metal kernel is selected.", "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    baseline_bytes, candidate_bytes = BASELINE.read_bytes(), CANDIDATE.read_bytes()
    record = build(
        baseline_bytes, json.loads(baseline_bytes, object_pairs_hook=_unique),
        candidate_bytes, json.loads(candidate_bytes, object_pairs_hook=_unique),
    )
    json_text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    table_text = render(record)
    if args.check:
        if not JSON_OUT.exists() or JSON_OUT.read_text() != json_text:
            raise SystemExit("generated Q2_K integration analysis is stale")
        if not TABLE_OUT.exists() or TABLE_OUT.read_text() != table_text:
            raise SystemExit("generated Q2_K integration table is stale")
    else:
        JSON_OUT.write_text(json_text)
        TABLE_OUT.write_text(table_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
