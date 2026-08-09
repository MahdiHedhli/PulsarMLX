#!/usr/bin/env python3
"""Derive the Feature 016 golden-eight closeout profile from committed evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "docs/research/glm52/raw/f016-inference-golden8-iq3-0001.json"
DEFAULT_JSON = ROOT / "docs/research/glm52/raw/f016-golden8-derived-profile-0001.json"
DEFAULT_TABLE = ROOT / "docs/research/glm52/tables/f016-golden8-derived-profile.md"
COMPONENT_FIELDS = (
    "storage_read_seconds",
    "dequant_seconds",
    "contiguous_buffer_seconds",
    "mlx_matrix_build_seconds",
    "mlx_matvec_seconds",
)
QUANT_FIELDS = (
    "matrix_load_count",
    "storage_bytes_read",
    "storage_read_count",
    *COMPONENT_FIELDS,
    "mlx_matvec_count",
)


def load_json(path: Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key: {key}")
            result[key] = value
        return result

    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates)


def stats(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    count = len(ordered)
    mean = sum(ordered) / count
    middle = count // 2
    median = (
        ordered[middle]
        if count % 2
        else (ordered[middle - 1] + ordered[middle]) / 2.0
    )
    sample_standard_deviation = (
        math.sqrt(sum((value - mean) ** 2 for value in ordered) / (count - 1))
        if count > 1
        else 0.0
    )
    return {
        "sample_count": count,
        "median": median,
        "mean": mean,
        "sample_standard_deviation": sample_standard_deviation,
        "minimum": ordered[0],
        "maximum": ordered[-1],
    }


def cache_component_sum(delta: dict[str, Any]) -> float:
    return sum(float(delta[field]) for field in COMPONENT_FIELDS)


def validate_record(record: dict[str, Any]) -> None:
    golden = [9703, 21615, 220, 16, 13, 16, 16, 15, 15]
    if record.get("actual_status") != "passed":
        raise ValueError("golden-eight source did not pass")
    if record.get("generated_token_ids") != golden or record.get("golden") != golden:
        raise ValueError("golden-eight token identity changed")
    if not record.get("matches_golden_full") or record.get("source_dirty"):
        raise ValueError("golden-eight source identity is not admissible")
    if len(record.get("timings", [])) != 9 or len(record.get("routing", [])) != 9:
        raise ValueError("golden-eight source must contain nine complete stacks")


def watcher_witness_from_summary(
    summary_path: Path, record: dict[str, Any]
) -> dict[str, Any]:
    summary = load_json(summary_path)
    if summary.get("snapshot_count") != 8 or summary.get("counter_reset_interval_count") != 0:
        raise ValueError("unexpected watcher coverage or cumulative reset")
    if summary.get("terminal_reason") != "canonical_terminal_status":
        raise ValueError("watcher did not observe a terminal canonical snapshot")
    if summary.get("earlier_overwritten_snapshots_reconstructed"):
        raise ValueError("watcher claims reconstructed history")
    snapshots = summary["snapshots"]
    if snapshots[0]["observed_new_token_count"] != 1:
        raise ValueError("watcher did not begin at the retained 1/8 snapshot")
    if snapshots[-1]["observed_new_token_count"] != 8:
        raise ValueError("watcher did not retain the terminal 8/8 snapshot")
    original_terminal = summary_path.parent / snapshots[-1]["filename"]
    if load_json(original_terminal) != record:
        raise ValueError("compact committed record differs semantically from watcher terminal bytes")
    intervals = []
    for interval in summary["intervals"]:
        if not interval["cumulative_counters_monotonic"]:
            raise ValueError("watcher interval contains a cumulative counter reset")
        if interval["stack_count_delta"] != 1 or "delta" not in interval or "stack" not in interval:
            raise ValueError("watcher interval is not one complete stack")
        intervals.append(
            {
                "from_snapshot_sha256": interval["from_sha256"],
                "to_snapshot_sha256": interval["to_sha256"],
                "from_completed_stack_count": interval["from_completed_stack_count"],
                "to_completed_stack_count": interval["to_completed_stack_count"],
                "cumulative_counters_monotonic": True,
                "expert_cache_delta": interval["delta"],
                "stack": interval["stack"],
            }
        )
    return {
        "archive_scope": "external_uncommitted_observational_archive",
        "poll_seconds": summary["poll_seconds"],
        "snapshot_count": summary["snapshot_count"],
        "first_observed_new_token_count": snapshots[0]["observed_new_token_count"],
        "last_observed_new_token_count": snapshots[-1]["observed_new_token_count"],
        "first_snapshot_sha256": snapshots[0]["sha256"],
        "original_terminal_snapshot_sha256": snapshots[-1]["sha256"],
        "original_terminal_semantically_equals_committed_compact_record": True,
        "counter_reset_interval_count": 0,
        "earlier_overwritten_snapshots_reconstructed": False,
        "cold_only_snapshot_available": False,
        "first_warm_only_interval_available": False,
        "valid_one_stack_interval_count": len(intervals),
        "valid_one_stack_intervals": intervals,
    }


def validate_witness(witness: dict[str, Any], record: dict[str, Any]) -> None:
    if witness["snapshot_count"] != 8 or witness["counter_reset_interval_count"] != 0:
        raise ValueError("committed watcher witness identity changed")
    if witness["first_observed_new_token_count"] != 1:
        raise ValueError("committed witness fabricates an earlier snapshot")
    intervals = witness["valid_one_stack_intervals"]
    if len(intervals) != 7:
        raise ValueError("expected seven retained one-stack intervals")
    for index, interval in enumerate(intervals, start=3):
        if not interval["cumulative_counters_monotonic"]:
            raise ValueError("counter reset in committed watcher witness")
        if interval["to_completed_stack_count"] != index:
            raise ValueError("non-contiguous watcher interval")
        stack = record["timings"][index - 1]
        retained = interval["stack"]
        if retained["token_id"] != stack["token"] or retained["stack_wall_seconds"] != stack["stack_seconds"]:
            raise ValueError("watcher stack does not join to committed evidence")
        for field in COMPONENT_FIELDS:
            quant_total = sum(
                float(metrics[field])
                for metrics in interval["expert_cache_delta"]["quantization_metrics"].values()
            )
            if abs(quant_total - float(stack["cache_delta"][field])) > 1e-9:
                raise ValueError(f"watcher quant delta does not reconcile: {field}")


def rank(entries: dict[str, float]) -> list[dict[str, Any]]:
    return [
        {"rank": position, "component": name, "seconds": seconds}
        for position, (name, seconds) in enumerate(
            sorted(entries.items(), key=lambda item: (-item[1], item[0])), start=1
        )
    ]


def build_profile(
    record: dict[str, Any], source_path: Path, witness: dict[str, Any]
) -> dict[str, Any]:
    validate_record(record)
    validate_witness(witness, record)
    timings = record["timings"]
    cold = timings[0]
    warm = timings[1:]
    cold_components = {field: float(cold["cache_delta"][field]) for field in COMPONENT_FIELDS}
    cold_attributed = sum(cold_components.values())
    cold_residual = float(cold["stack_seconds"]) - cold_attributed

    warm_residuals = []
    for stack in warm:
        warm_residuals.append(float(stack["stack_seconds"]) - cache_component_sum(stack["cache_delta"]))

    interval_quant: dict[str, dict[str, list[float]]] = {}
    for interval in witness["valid_one_stack_intervals"]:
        for quant, metrics in interval["expert_cache_delta"]["quantization_metrics"].items():
            fields = interval_quant.setdefault(quant, {field: [] for field in QUANT_FIELDS})
            for field in QUANT_FIELDS:
                fields[field].append(float(metrics[field]))

    per_quant = []
    for quant, fields in interval_quant.items():
        component_samples = [
            sum(fields[field][sample] for field in COMPONENT_FIELDS)
            for sample in range(len(fields[COMPONENT_FIELDS[0]]))
        ]
        per_quant.append(
            {
                "quantization": quant,
                "scope": "EXPERT-CACHE PATH ONLY",
                "sample_count": len(component_samples),
                "component_seconds": stats(component_samples),
                "metrics": {field: stats(values) for field, values in fields.items()},
            }
        )
    per_quant.sort(key=lambda item: (-float(item["component_seconds"]["mean"]), item["quantization"]))
    for position, item in enumerate(per_quant, start=1):
        item["rank_by_mean_component_seconds"] = position

    warm_component_means = {
        field: sum(float(stack["cache_delta"][field]) for stack in warm) / len(warm)
        for field in COMPONENT_FIELDS
    }
    warm_residual_mean = sum(warm_residuals) / len(warm_residuals)
    warm_logits = [float(stack["logits_seconds"]) for stack in warm]
    warm_stack_seconds = [float(stack["stack_seconds"]) for stack in warm]
    warm_top_level = {
        "uninstrumented_trunk_residual": warm_residual_mean,
        "full_vocabulary_logits_separate": sum(warm_logits) / len(warm_logits),
        **{f"expert_cache_{field}": value for field, value in warm_component_means.items()},
    }
    cold_top_level = {
        "uninstrumented_trunk_residual": cold_residual,
        **{f"expert_cache_{field}": value for field, value in cold_components.items()},
    }

    first_token_components = float(cold["stack_seconds"]) + float(warm[0]["logits_seconds"])
    inter_token_components = [
        float(timings[index]["stack_seconds"]) + float(timings[index + 1]["logits_seconds"])
        for index in range(1, 8)
    ]
    eighth_selection_components = (
        sum(float(item["stack_seconds"]) for item in timings[:8])
        + sum(float(item["logits_seconds"]) for item in warm)
    )
    cache = record["expert_cache"]
    return {
        "schema": "pulsarmlx.research.glm52-golden8-derived-profile",
        "schema_version": "1.0.0",
        "feature_id": "016-glm52-full-execution",
        "actual_status": "passed",
        "source_evidence": source_path.relative_to(ROOT).as_posix(),
        "source_evidence_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "source_commit": record["source_commit"],
        "generated_token_ids": record["generated_token_ids"],
        "watcher": witness,
        "total": {
            "evidence_wall_seconds": record["seconds"],
            "stack_count": len(timings),
            "stack_wall_seconds_sum": sum(float(item["stack_seconds"]) for item in timings),
            "logits_seconds_sum": sum(warm_logits),
            "storage_bytes_read": cache["storage_bytes_read"],
            "storage_bytes_avoided": cache["storage_bytes_avoided"],
            "decoded_bytes_avoided": cache["decoded_bytes_avoided"],
            "dequant_seconds": cache["dequant_seconds"],
            "contiguous_buffer_seconds": cache["contiguous_buffer_seconds"],
            "mlx_matrix_build_seconds": cache["mlx_matrix_build_seconds"],
            "mlx_matvec_seconds": cache["mlx_matvec_seconds"],
            "decoded_cache_hits": cache["decoded_cache_hits"],
            "decoded_cache_misses": cache["decoded_cache_misses"],
        },
        "cold": {
            "sample_count": 1,
            "stack_wall_seconds": cold["stack_seconds"],
            "expert_cache_components": cold_components,
            "expert_cache_attributed_component_seconds": cold_attributed,
            "uninstrumented_residual_seconds": cold_residual,
            "uninstrumented_residual_fraction": cold_residual / float(cold["stack_seconds"]),
            "cache_admissions": cold["cache_delta"]["admissions"],
            "storage_bytes_read": cold["cache_delta"]["storage_bytes_read"],
            "resource_after": cold["resource_after"],
            "top_level_ranking": rank(cold_top_level),
            "per_quant_status": "unavailable_watcher_began_after_cold_and_first_warm",
        },
        "warm": {
            "sample_count": len(warm),
            "stack_wall_seconds": stats(warm_stack_seconds),
            "logits_seconds_separate": stats(warm_logits),
            "expert_cache_components": {
                field: stats([float(stack["cache_delta"][field]) for stack in warm])
                for field in COMPONENT_FIELDS
            },
            "expert_cache_attributed_component_seconds": stats(
                [cache_component_sum(stack["cache_delta"]) for stack in warm]
            ),
            "uninstrumented_residual_seconds": stats(warm_residuals),
            "uninstrumented_residual_fraction": stats(
                [residual / float(stack["stack_seconds"]) for residual, stack in zip(warm_residuals, warm, strict=True)]
            ),
            "decoded_cache_hits_per_stack": [stack["cache_delta"]["decoded_cache_hits"] for stack in warm],
            "storage_bytes_read_per_stack": [stack["cache_delta"]["storage_bytes_read"] for stack in warm],
            "rss_bytes": stats([float(stack["resource_after"]["rss_bytes"]) for stack in warm]),
            "peak_rss_bytes": stats([float(stack["resource_after"]["peak_rss_bytes"]) for stack in warm]),
            "resource_levels": [stack["resource_after"]["level"] for stack in warm],
            "top_level_ranking": rank(warm_top_level),
            "per_quant_scope": "EXPERT-CACHE PATH ONLY",
            "per_quant_interval_coverage": "tokens_2_through_8_only",
            "per_quant_ranked": per_quant,
        },
        "user_visible_latency": {
            "time_to_first_token_recorded_component_seconds": first_token_components,
            "inter_token_recorded_component_seconds": stats(inter_token_components),
            "eighth_token_selection_recorded_component_seconds": eighth_selection_components,
            "terminal_state_advance_seconds_after_eighth_selection": timings[-1]["stack_seconds"],
            "total_evidence_wall_seconds": record["seconds"],
            "caveat": "component sums exclude small runner bookkeeping; final stack advances state after token eight is selected",
        },
        "historical_cross_commit_observations": [
            {"name": "research_C11", "wall_seconds": 48_730.7},
            {"name": "legacy_P1", "wall_seconds": 15_146.448245750013},
            {"name": "vectorized_P1", "wall_seconds": 4_582.511032},
            {"name": "P2", "wall_seconds": 6_552.475384208003},
            {"name": "golden_eight", "wall_seconds": record["seconds"]},
        ],
        "decisions": {
            "prefetch_storage": "deferred_no_measured_warm_storage_dominance",
            "warm_storage_seconds_mean": warm_component_means["storage_read_seconds"],
            "warm_storage_fraction_of_stack_mean": warm_component_means["storage_read_seconds"] / (sum(warm_stack_seconds) / len(warm_stack_seconds)),
            "feature_018_title": "018-direct-quantized-metal-runtime",
            "feature_018_first_kernel_selected": False,
            "selection_blocker": "material uninstrumented warm trunk residual",
            "required_m2_max_fixture_boundaries": [
                "MLA and attention projection matrices",
                "dense pre-attention and post-attention transforms",
                "embeddings if measured material",
                "final norm and full-vocabulary output projection",
                "Q6_K tensors present in those trunk paths",
            ],
        },
    }


def render_table(profile: dict[str, Any]) -> str:
    cold = profile["cold"]
    warm = profile["warm"]
    lines = [
        "# Feature 016 golden-eight derived profile",
        "",
        "Generated from committed raw evidence; no benchmark values are hard-coded in this table.",
        "",
        "## Total and user-visible boundaries",
        "",
        "| Metric | Seconds |",
        "| --- | ---: |",
        f"| Complete evidence wall | {profile['total']['evidence_wall_seconds']:.6f} |",
        f"| Time to first token (recorded components) | {profile['user_visible_latency']['time_to_first_token_recorded_component_seconds']:.6f} |",
        f"| Warm stack median | {warm['stack_wall_seconds']['median']:.6f} |",
        f"| Warm logits median (separate) | {warm['logits_seconds_separate']['median']:.6f} |",
        f"| Terminal state advance after token eight selection | {profile['user_visible_latency']['terminal_state_advance_seconds_after_eighth_selection']:.6f} |",
        "",
        "## Cold stack",
        "",
        "| Component | Seconds |",
        "| --- | ---: |",
    ]
    for item in cold["top_level_ranking"]:
        lines.append(f"| {item['component']} | {item['seconds']:.6f} |")
    lines.extend(
        [
            "",
            "Cold per-quant attribution is unavailable: the passive watcher began after the cold and first warm stacks. No earlier snapshot was reconstructed.",
            "",
            "## Warm top-level ranking",
            "",
            "| Rank | Component | Mean seconds |",
            "| ---: | --- | ---: |",
        ]
    )
    for item in warm["top_level_ranking"]:
        lines.append(f"| {item['rank']} | {item['component']} | {item['seconds']:.6f} |")
    lines.extend(
        [
            "",
            "## Warm per-quant ranking — EXPERT-CACHE PATH ONLY",
            "",
            "Seven one-stack intervals cover generated tokens 2 through 8. This is not whole-token quantization cost.",
            "",
            "| Rank | Quantization | Mean component seconds | Median |",
            "| ---: | --- | ---: | ---: |",
        ]
    )
    for item in warm["per_quant_ranked"]:
        component = item["component_seconds"]
        lines.append(
            f"| {item['rank_by_mean_component_seconds']} | {item['quantization']} | "
            f"{component['mean']:.6f} | {component['median']:.6f} |"
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"- Warm residual median: {warm['uninstrumented_residual_seconds']['median']:.6f} seconds "
            f"({warm['uninstrumented_residual_fraction']['median']:.2%} of stack wall).",
            f"- Warm storage mean: {profile['decisions']['warm_storage_seconds_mean']:.6f} seconds "
            f"({profile['decisions']['warm_storage_fraction_of_stack_mean']:.2%} of mean stack wall).",
            "- Prefetch/storage implementation is deferred because measured warm storage time is not material.",
            "- Feature 018 remains profile-neutral; its first kernel is not selected until M2 Max trunk fixtures close the residual.",
            "",
        ]
    )
    return "\n".join(lines)


def serialize(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--watcher-summary", type=Path)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--table-out", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    record = load_json(args.source)
    if args.watcher_summary is not None:
        witness = watcher_witness_from_summary(args.watcher_summary, record)
    elif args.check and args.json_out.is_file():
        witness = load_json(args.json_out)["watcher"]
    else:
        raise SystemExit("--watcher-summary is required when generating a new profile")
    profile = build_profile(record, args.source.resolve(), witness)
    json_text = serialize(profile)
    table_text = render_table(profile)
    if args.check:
        if args.json_out.read_text() != json_text or args.table_out.read_text() != table_text:
            raise SystemExit("golden-eight derived outputs are stale")
        print("golden-eight derived profile: passed")
        return 0
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.table_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json_text)
    args.table_out.write_text(table_text)
    print("golden-eight derived profile: generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
