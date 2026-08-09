#!/usr/bin/env python3
"""Derive the post-trunk P1 timing and bottleneck profile."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "docs/research/glm52/raw/post-f016-inference-p1-trunk-q6-0001.json"
DEFAULT_RANKING = ROOT / "docs/research/glm52/raw/post-f016-p1-trunk-q6-expert-hotspots-0001.json"
DEFAULT_JSON = ROOT / "docs/research/glm52/raw/post-f016-p1-trunk-profile-0001.json"
DEFAULT_TABLE = ROOT / "docs/research/glm52/tables/post-f016-p1-trunk-profile-0001.md"
COMPONENTS = (
    "storage_read_seconds",
    "dequant_seconds",
    "contiguous_buffer_seconds",
    "mlx_matrix_build_seconds",
    "mlx_matvec_seconds",
)


def _stack_profile(stack: dict) -> dict:
    cache = stack["cache_delta"]
    expert = {field: float(cache[field]) for field in COMPONENTS}
    expert["attributed_component_seconds"] = sum(expert.values())
    return {
        "phase": stack["phase"],
        "stack_seconds": float(stack["stack_seconds"]),
        "logits_seconds_separate": float(stack.get("logits_seconds", 0.0)),
        "expert_cache_components": expert,
        "uninstrumented_residual_seconds": float(stack["stack_seconds"]) - expert["attributed_component_seconds"],
        "decoded_cache_hits": int(cache["decoded_cache_hits"]),
        "decoded_cache_misses": int(cache["decoded_cache_misses"]),
        "storage_bytes_avoided": int(cache["storage_bytes_avoided"]),
        "decoded_bytes_avoided": int(cache["decoded_bytes_avoided"]),
        "cpu_fallbacks": int(cache["cpu_fallbacks"]),
        "peak_rss_bytes": int(stack["resource_after"]["peak_rss_bytes"]),
        "resource_level": stack["resource_after"]["level"],
    }


def build(source_bytes: bytes, source: dict, ranking: dict) -> dict:
    if source["actual_status"] != "passed" or source["source_dirty"]:
        raise ValueError("P1 source must be passed and clean")
    if source["generated_token_ids"] != [9703, 21615] or not source["matches_golden_prefix"]:
        raise ValueError("P1 golden prefix failed")
    if source["dense_read_mode"] != "whole_matrix_numpy_q5_q8_q6_head_numpy":
        raise ValueError("qualified dense mode missing")
    if len(source["timings"]) != 2:
        raise ValueError("P1 must contain prompt and generated-token stacks")
    cold, warm = map(_stack_profile, source["timings"])
    terminal_state_advance = warm["stack_seconds"]
    selection_upper_bound = float(source["seconds"]) - terminal_state_advance
    selected_component_boundary = cold["stack_seconds"] + warm["logits_seconds_separate"]
    history_paths = {
        "research_c11": ROOT / "docs/research/glm52/raw/f016-c11-generation-0001.json",
        "legacy_p1": ROOT / "docs/research/glm52/raw/f016-inference-p1-token1.json",
        "vectorized_expert_p1": ROOT / "docs/research/glm52/raw/f016-inference-p1-vectorized-0001.json",
        "iq3_vectorized_expert_p1": ROOT / "docs/research/glm52/raw/f016-inference-p1-iq3-0001.json",
    }
    historical = {
        key: {
            "record": path.relative_to(ROOT).as_posix(),
            "seconds": float(json.loads(path.read_text())["seconds"]),
        }
        for key, path in history_paths.items()
    }
    for value in historical.values():
        value["cross_commit_reduction_vs_current_fraction"] = 1.0 - float(source["seconds"]) / value["seconds"]
    warm_ranking = [
        {"component": "expert_cache_attributed", "seconds": warm["expert_cache_components"]["attributed_component_seconds"]},
        {"component": "full_vocabulary_logits_separate", "seconds": warm["logits_seconds_separate"]},
        {"component": "uninstrumented_residual", "seconds": warm["uninstrumented_residual_seconds"]},
    ]
    warm_ranking.sort(key=lambda item: -item["seconds"])
    for index, item in enumerate(warm_ranking, 1):
        item["rank"] = index
    return {
        "schema": "pulsarmlx.research.glm52-post-trunk-p1-profile",
        "schema_version": "1.0.0",
        "feature_id": "post-f016-trunk-optimization",
        "actual_status": "passed",
        "source": {
            "record": "docs/research/glm52/raw/post-f016-inference-p1-trunk-q6-0001.json",
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
            "source_commit": source["source_commit"],
            "source_dirty": source["source_dirty"],
        },
        "correctness": {
            "generated_token_ids": source["generated_token_ids"],
            "matches_golden_prefix": source["matches_golden_prefix"],
            "dense_read_mode": source["dense_read_mode"],
            "expert_decoder_mode": source["decoder_mode"],
            "mlx_device": source["expert_cache"]["device"],
            "cpu_fallbacks": source["expert_cache"]["cpu_fallbacks"],
            "cache_evictions": source["expert_cache"]["evictions"],
            "admission_rejections": source["expert_cache"]["admission_rejections"],
        },
        "timing": {
            "total_evidence_wall_seconds": float(source["seconds"]),
            "cold_prompt_stack": cold,
            "warm_generated_token_stack": warm,
            "terminal_state_advance_stack_seconds": terminal_state_advance,
            "first_token_selection_component_boundary_seconds": selected_component_boundary,
            "first_token_selection_wall_minus_terminal_upper_bound_seconds": selection_upper_bound,
            "selection_boundary_runner_remainder_seconds": selection_upper_bound - selected_component_boundary,
        },
        "cache": {
            "decoded_cache_hits": source["expert_cache"]["decoded_cache_hits"],
            "decoded_cache_misses": source["expert_cache"]["decoded_cache_misses"],
            "resident_entries": source["expert_cache"]["resident_entries"],
            "bytes_resident": source["expert_cache"]["bytes_resident"],
            "storage_bytes_avoided": source["expert_cache"]["storage_bytes_avoided"],
            "decoded_bytes_avoided": source["expert_cache"]["decoded_bytes_avoided"],
        },
        "warm_top_level_ranking": warm_ranking,
        "expert_quantization_ranking": {
            "source_record": ranking["source"]["record"],
            "scope": "cold plus warm expert-cache path combined; not a warm-only format ranking",
            "quantified_component_seconds": ranking["quantified_component_seconds"],
            "ranking": ranking["ranking"],
        },
        "historical_cross_commit_observations": historical,
        "decision": {
            "another_full_model_run_required_in_this_sprint": False,
            "storage_prefetch_priority": "deferred; warm expert storage was 9.656 seconds versus 203.329 seconds expert dequant and 316.759 seconds stack wall",
            "next_recoverable_boundary": "expert-cache decode dominates the measured warm top-level attribution; full-vocabulary logits and the uninstrumented residual are also material",
            "feature_018_first_kernel_selected": False,
            "feature_018_reason": "the new exact P1 lacks warm per-quant deltas; combined cold-plus-warm Q6_K rank must not be treated as a warm kernel selection",
        },
        "limitations": [
            "One clean-process P1 on one M1 Ultra; no timing population or general tokens/second claim.",
            "Historical reductions are cross-commit observations, not controlled same-binary comparisons.",
            "The final warm stack advances model state after token 21615 was selected; it is not user-visible selection latency.",
            "Dense/trunk components were not captured in the P1 schema; stack remainder is uninstrumented and is not labeled trunk.",
            "Expert per-quant metrics cover cold and warm combined, so they do not select a warm-path Metal kernel.",
        ],
    }


def render_table(record: dict) -> str:
    timing = record["timing"]
    cold = timing["cold_prompt_stack"]
    warm = timing["warm_generated_token_stack"]
    history = record["historical_cross_commit_observations"]
    rank_lines = [
        f"| {item['rank']} | `{item['component']}` | {item['seconds']:.6f} |"
        for item in record["warm_top_level_ranking"]
    ]
    history_lines = [
        f"| `{key}` | {value['seconds']:.6f} | {value['cross_commit_reduction_vs_current_fraction']:.2%} |"
        for key, value in history.items()
    ]
    return "\n".join([
        "# Post-Feature-016 optimized P1 profile", "",
        f"Derived from the exact P1 record at clean source `{record['source']['source_commit']}`.", "",
        "## Correctness and user-visible boundary", "",
        f"- Exact generated prefix: `{record['correctness']['generated_token_ids']}`",
        f"- Total evidence wall: {timing['total_evidence_wall_seconds']:.6f} s",
        f"- Cold prompt stack: {cold['stack_seconds']:.6f} s",
        f"- Full-vocabulary logits: {warm['logits_seconds_separate']:.6f} s",
        f"- First-token selection component boundary: {timing['first_token_selection_component_boundary_seconds']:.6f} s",
        f"- Wall-minus-terminal selection upper bound: {timing['first_token_selection_wall_minus_terminal_upper_bound_seconds']:.6f} s",
        f"- Redundant retained terminal state-advance stack: {timing['terminal_state_advance_stack_seconds']:.6f} s", "",
        "## Warm stack attribution", "",
        "| Rank | Component | Seconds |", "| ---: | --- | ---: |", *rank_lines, "",
        f"Within expert-cache attribution: storage {warm['expert_cache_components']['storage_read_seconds']:.6f} s, decode {warm['expert_cache_components']['dequant_seconds']:.6f} s, buffer {warm['expert_cache_components']['contiguous_buffer_seconds']:.6f} s, build {warm['expert_cache_components']['mlx_matrix_build_seconds']:.6f} s, and matvec {warm['expert_cache_components']['mlx_matvec_seconds']:.6f} s.", "",
        "The separate expert per-quant table covers cold plus warm combined. Its Q6_K rank is not a warm-only kernel decision.", "",
        "## Historical cross-commit observations", "",
        "| Record | Wall (s) | Reduction versus current |", "| --- | ---: | ---: |", *history_lines, "",
        "These are cross-commit observations, not controlled same-binary benchmark populations.", "",
        "No additional full-model run is required for this sprint. Storage prefetch remains deferred, and Feature 018 remains profile-neutral because this exact P1 did not retain per-quant warm deltas.", "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--ranking", type=Path, default=DEFAULT_RANKING)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--table-out", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source_bytes = args.source.read_bytes()
    record = build(source_bytes, json.loads(source_bytes), json.loads(args.ranking.read_text()))
    json_text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    table_text = render_table(record)
    if args.check:
        if not args.json_out.exists() or args.json_out.read_text() != json_text:
            raise SystemExit(f"generated profile is stale: {args.json_out}")
        if not args.table_out.exists() or args.table_out.read_text() != table_text:
            raise SystemExit(f"generated table is stale: {args.table_out}")
        return 0
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.table_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json_text)
    args.table_out.write_text(table_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
