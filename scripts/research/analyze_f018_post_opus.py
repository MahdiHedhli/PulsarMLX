#!/usr/bin/env python3
"""Generate/check the decisive Feature 018 post-Opus qualification result."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HISTORICAL = ROOT / "docs/research/glm52/raw/f018-iq2-xxs-gate-matrix-0001.json"
STRICT = ROOT / "docs/research/glm52/raw/f018-iq2-xxs-gate-matrix-strict-0001.json"
LOOKUP = ROOT / "docs/research/glm52/raw/f018-iq2-lookup-address-space-0001.json"
DISPATCH = ROOT / "docs/research/glm52/raw/f018-p1-reference-dispatch-inventory-0001.json"
OUTPUT = ROOT / "docs/research/glm52/raw/f018-post-opus-qualification-0001.json"
TABLE = ROOT / "docs/research/glm52/tables/f018-post-opus-qualification-0001.md"


def _load(path: Path) -> tuple[dict[str, Any], str]:
    data = path.read_bytes()
    return json.loads(data), hashlib.sha256(data).hexdigest()


def _variant(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_count": summary["sample_count"],
        "median_seconds": summary["median_seconds"],
        "mean_seconds": summary["mean_seconds"],
        "sample_standard_deviation_seconds": summary["standard_deviation_seconds"],
        "minimum_seconds": summary["minimum_seconds"],
        "maximum_seconds": summary["maximum_seconds"],
    }


def build() -> dict[str, Any]:
    historical, historical_sha = _load(HISTORICAL)
    strict, strict_sha = _load(STRICT)
    lookup, lookup_sha = _load(LOOKUP)
    dispatch, dispatch_sha = _load(DISPATCH)
    identity_fields = (
        "tensor_name",
        "layer",
        "expert_id",
        "projection",
        "shape",
        "packed_sha256",
        "activation_sha256",
        "reference_output_sha256",
    )
    if any(
        historical["binding"][field] != strict["binding"][field]
        for field in identity_fields
    ):
        raise ValueError("historical and strict matrix bindings differ")
    if strict["classification"] != "numerically_qualified_greedy_identical":
        raise ValueError("strict candidate did not retain its frozen classification")
    compiler = strict["kernel"]["compiler"]
    if compiler != {
        "fast_math_enabled": False,
        "language_version": "3.2",
        "math_floating_point_functions": "precise",
        "math_mode": "safe",
        "pipeline_identity": "iq2_xxs_sequential_scaffold_v1",
    }:
        raise ValueError("strict compiler settings changed")
    optimized = _variant(
        strict["optimized_reference"]["summaries"]["total_seconds"]
    )
    historical_direct = {
        "sample_count": historical["timing"]["sample_count"],
        "median_seconds": historical["timing"]["median_seconds"],
        "mean_seconds": historical["timing"]["mean_seconds"],
        "sample_standard_deviation_seconds": historical["timing"][
            "sample_standard_deviation_seconds"
        ],
        "minimum_seconds": historical["timing"]["minimum_seconds"],
        "maximum_seconds": historical["timing"]["maximum_seconds"],
    }
    strict_direct = {
        "sample_count": strict["timing"]["sample_count"],
        "median_seconds": strict["timing"]["median_seconds"],
        "mean_seconds": strict["timing"]["mean_seconds"],
        "sample_standard_deviation_seconds": strict["timing"][
            "sample_standard_deviation_seconds"
        ],
        "minimum_seconds": strict["timing"]["minimum_seconds"],
        "maximum_seconds": strict["timing"]["maximum_seconds"],
    }
    absolute = optimized["median_seconds"] - strict_direct["median_seconds"]
    ratio = optimized["median_seconds"] / strict_direct["median_seconds"]
    materially_faster = absolute > 0.05 and ratio > 2.0
    if not materially_faster:
        raise ValueError("strict direct candidate did not satisfy the frozen GO rule")
    return {
        "schema": "pulsarmlx.research.f018-post-opus-qualification",
        "schema_version": "1.0.0",
        "actual_status": "passed",
        "inputs": {
            "historical_default": {"path": str(HISTORICAL.relative_to(ROOT)), "sha256": historical_sha},
            "strict": {"path": str(STRICT.relative_to(ROOT)), "sha256": strict_sha},
            "lookup_experiment": {"path": str(LOOKUP.relative_to(ROOT)), "sha256": lookup_sha},
            "dispatch_inventory": {"path": str(DISPATCH.relative_to(ROOT)), "sha256": dispatch_sha},
        },
        "binding": {field: strict["binding"][field] for field in identity_fields},
        "variants": {
            "A_optimized_numpy_mlx": {
                **optimized,
                "source_commit": strict["source"]["commit"],
                "role": "authoritative optimized reference",
            },
            "B_historical_default_direct": {
                **historical_direct,
                "source_commit": historical["source"]["commit"],
                "role": "historical comparison only",
                "compiler_semantics": "unversioned defaults (options:nil)",
            },
            "C_strict_direct": {
                **strict_direct,
                "source_commit": strict["source"]["commit"],
                "role": "authoritative direct qualification candidate",
                "compiler": compiler,
            },
        },
        "strict_correctness": strict["correctness"],
        "strict_setup": strict["setup"],
        "strict_resource_before": strict["resource_before"],
        "strict_resource_after": strict["resource"],
        "performance": {
            "strict_over_optimized_ratio": ratio,
            "absolute_median_seconds_recovered": absolute,
            "materially_faster": materially_faster,
        },
        "safety": {
            "strict_compiler_committed": True,
            "validation_fails_closed": True,
            "native_in_flight_lifetime_committed": True,
            "cpu_fallback_count": strict["kernel"]["cpu_fallback_count"],
            "complete_f32_weight_materialized_bytes": strict["kernel"][
                "complete_f32_weight_materialized_bytes"
            ],
            "direct_error_count": 0,
            "resource_level_before": strict["resource_before"]["level"],
            "resource_level_after": strict["resource"]["level"],
        },
        "lookup_decision": lookup["decision"],
        "p1_dispatch_accounting": dispatch["full_run"],
        "verdict": "GO",
        "iq3_down_admission": "eligible_after_final_CI_and_review_closeout",
        "parallel_iq2_kernel_required_before_iq3": False,
        "claim_boundary": "One real IQ2_XXS gate matrix on one M1 Ultra. Historical/default compilation is contextual, not a controlled current-source population. No expert, layer, token, P2, or golden-eight result is inferred.",
    }


def markdown(record: dict[str, Any]) -> str:
    rows = []
    labels = {
        "A_optimized_numpy_mlx": "A. optimized NumPy + MLX",
        "B_historical_default_direct": "B. historical default direct",
        "C_strict_direct": "C. strict direct Metal scaffold",
    }
    for key, label in labels.items():
        row = record["variants"][key]
        rows.append(
            "| {} | {} | {:.9f} | {:.9f} | {:.9f} | {:.9f} | {:.9f} |".format(
                label,
                row["sample_count"],
                row["median_seconds"],
                row["mean_seconds"],
                row["sample_standard_deviation_seconds"],
                row["minimum_seconds"],
                row["maximum_seconds"],
            )
        )
    correctness = record["strict_correctness"]
    return "\n".join(
        [
            "# Feature 018 Post-Opus Three-Way Matrix Gate",
            "",
            "| Variant | Samples | Median (s) | Mean (s) | Std dev (s) | Min (s) | Max (s) |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            *rows,
            "",
            f"Strict direct/reference ratio: `{record['performance']['strict_over_optimized_ratio']:.2f}×`; absolute median recovered: `{record['performance']['absolute_median_seconds_recovered']:.9f}` s.",
            f"Classification: `{correctness['classification']}`; exact bits: `{str(correctness['exact_f32_bits']).lower()}`; bit mismatches: `{correctness['f32_bit_mismatch_count']}`; tolerance mismatches: `{correctness['elementwise_mismatch_count']}`; max abs: `{correctness['maximum_absolute_error']:.9g}`.",
            "",
            f"Final verdict: **{record['verdict']}**. IQ3-down is eligible only after final CI and review closeout; it was not started by this calculation.",
            "",
            record["claim_boundary"],
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    record = build()
    payload = json.dumps(record, indent=2, sort_keys=True) + "\n"
    table = markdown(record)
    if args.check:
        if OUTPUT.read_text() != payload or TABLE.read_text() != table:
            raise SystemExit("post-Opus qualification artifacts are stale")
    else:
        OUTPUT.write_text(payload)
        TABLE.write_text(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
