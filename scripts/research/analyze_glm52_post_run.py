#!/usr/bin/env python3
"""Derive post-golden-eight calculations without checkpoint access or inference."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from glm52_tensor_store import nbytes_for_tensor

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = ROOT / "docs/research/glm52/raw/f016-inference-golden8-iq3-0001.json"
PROFILE_PATH = ROOT / "docs/research/glm52/raw/f016-golden8-derived-profile-0001.json"
CATALOG_PATH = ROOT / "docs/research/glm52/raw/f016-c01-catalog-0001.json"
JSON_OUT = ROOT / "docs/research/glm52/raw/f016-golden8-post-run-calculations-0001.json"
INVENTORY_OUT = ROOT / "docs/research/glm52/raw/f016-gguf-trunk-inventory-0001.json"
REPORT_OUT = ROOT / "docs/research/glm52/POST_GOLDEN8_CALCULATIONS.md"

COMPONENT_FIELDS = (
    "storage_read_seconds",
    "dequant_seconds",
    "contiguous_buffer_seconds",
    "mlx_matrix_build_seconds",
    "mlx_matvec_seconds",
)
EXPERT_RE = re.compile(r"\.ffn_(?:down|gate|up)_(?:exps|shexp)\.weight$")
LAYER_RE = re.compile(r"^blk\.(\d+)\.")
GIB = 1024**3


def load_json(path: Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key: {key}")
            result[key] = value
        return result

    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile_type7(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("empty population")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def summarize(values: Iterable[float]) -> dict[str, float | int]:
    samples = [float(value) for value in values]
    if not samples:
        raise ValueError("empty population")
    ordered = sorted(samples)
    count = len(ordered)
    mean = sum(ordered) / count
    middle = count // 2
    median = (
        ordered[middle]
        if count % 2
        else (ordered[middle - 1] + ordered[middle]) / 2.0
    )
    sample_variance = (
        sum((value - mean) ** 2 for value in ordered) / (count - 1)
        if count > 1
        else 0.0
    )
    return {
        "sample_count": count,
        "mean": mean,
        "median": median,
        "sample_variance": sample_variance,
        "sample_standard_deviation": math.sqrt(sample_variance),
        "minimum": ordered[0],
        "maximum": ordered[-1],
        "p95_type7": percentile_type7(ordered, 0.95),
    }


def component_sum(delta: dict[str, Any]) -> float:
    return sum(float(delta[field]) for field in COMPONENT_FIELDS)


def assert_close(actual: float, expected: float, label: str, tolerance: float = 1e-9) -> None:
    if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance):
        raise ValueError(f"{label} changed")


def validate_sources(golden: dict[str, Any], profile: dict[str, Any], catalog: dict[str, Any]) -> None:
    if golden.get("actual_status") != "passed" or golden.get("source_dirty"):
        raise ValueError("golden source is not an admitted passing clean run")
    if golden.get("source_commit") != "1a2ca76ee2df0f518bfc9ddbaafd31500a5e6a26":
        raise ValueError("golden source commit changed")
    if golden.get("generated_token_ids") != [9703, 21615, 220, 16, 13, 16, 16, 15, 15]:
        raise ValueError("golden sequence changed")
    if len(golden.get("timings", [])) != 9:
        raise ValueError("golden timing stack count changed")
    if profile.get("actual_status") != "passed" or profile.get("source_commit") != golden["source_commit"]:
        raise ValueError("derived profile does not bind the golden run")
    if profile.get("source_evidence_sha256") != sha256(GOLDEN_PATH):
        raise ValueError("derived profile source hash changed")
    watcher = profile.get("watcher", {})
    if (
        watcher.get("snapshot_count") != 8
        or watcher.get("valid_one_stack_interval_count") != 7
        or watcher.get("counter_reset_interval_count") != 0
        or watcher.get("earlier_overwritten_snapshots_reconstructed") is not False
    ):
        raise ValueError("watcher coverage changed")
    if catalog.get("actual_status") != "passed" or catalog.get("tensor_count") != 1809:
        raise ValueError("catalog identity changed")


def preserved_metrics(golden: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    warm = profile["warm"]
    total = profile["total"]
    cache = golden["expert_cache"]
    assert_close(float(total["evidence_wall_seconds"]), float(golden["seconds"]), "wall")
    assert_close(float(profile["cold"]["stack_wall_seconds"]), float(golden["timings"][0]["stack_seconds"]), "cold")
    if warm["sample_count"] != 8 or total["stack_count"] != 9:
        raise ValueError("warm/total stack population changed")
    if cache["decoded_cache_hits"] != 1824 or cache["evictions"] != 0 or cache["cpu_fallbacks"] != 0:
        raise ValueError("cache/fallback identity changed")
    if any(level != "normal" for level in warm["resource_levels"]):
        raise ValueError("resource status changed")
    return {
        "authoritative_profile": PROFILE_PATH.relative_to(ROOT).as_posix(),
        "golden_evidence_wall_seconds": total["evidence_wall_seconds"],
        "cold_prompt_stack_seconds": profile["cold"]["stack_wall_seconds"],
        "warm_stack_seconds": warm["stack_wall_seconds"],
        "expert_cache_totals": {
            field: total[field]
            for field in (
                "storage_bytes_read",
                "dequant_seconds",
                "contiguous_buffer_seconds",
                "mlx_matrix_build_seconds",
                "mlx_matvec_seconds",
            )
        },
        "watcher_snapshot_count": profile["watcher"]["snapshot_count"],
        "watcher_valid_one_stack_interval_count": profile["watcher"]["valid_one_stack_interval_count"],
        "watcher_counter_reset_interval_count": profile["watcher"]["counter_reset_interval_count"],
        "expert_cache_per_quant_scope": warm["per_quant_scope"],
        "expert_cache_per_quant_ranked": warm["per_quant_ranked"],
        "warm_uninstrumented_residual_seconds": warm["uninstrumented_residual_seconds"],
        "warm_uninstrumented_residual_fraction": warm["uninstrumented_residual_fraction"],
        "decoded_cache_hits": cache["decoded_cache_hits"],
        "decoded_bytes_avoided": cache["decoded_bytes_avoided"],
        "storage_bytes_avoided": cache["storage_bytes_avoided"],
        "cpu_fallbacks": cache["cpu_fallbacks"],
        "evictions": cache["evictions"],
        "admission_rejections": cache["admission_rejections"],
        "resource_levels": warm["resource_levels"],
        "prefetch_storage_decision": profile["decisions"]["prefetch_storage"],
    }


def user_visible_timing(golden: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    timings = golden["timings"]
    terminal = float(timings[-1]["stack_seconds"])
    evidence_wall = float(golden["seconds"])
    all_stack = sum(float(row["stack_seconds"]) for row in timings)
    all_logits = sum(float(row["logits_seconds"]) for row in timings[1:])
    unassigned = evidence_wall - all_stack - all_logits
    if unassigned < 0.0:
        raise ValueError("negative unassigned runner time")

    tokens = []
    for token_number in range(1, 9):
        selection_row = timings[token_number]
        preceding_stack = timings[token_number - 1]
        logits_seconds = float(selection_row["logits_seconds"])
        transformer_seconds = float(preceding_stack["stack_seconds"])
        tokens.append(
            {
                "generated_token_number": token_number,
                "token_id": selection_row["token"],
                "transformer_stack_before_selection_seconds": transformer_seconds,
                "selection_logits_seconds": logits_seconds,
                "recorded_selection_latency_seconds": transformer_seconds + logits_seconds,
            }
        )
    recorded_through_eight = sum(row["recorded_selection_latency_seconds"] for row in tokens)
    subtractive_upper_bound = evidence_wall - terminal
    assert_close(
        recorded_through_eight,
        float(profile["user_visible_latency"]["eighth_token_selection_recorded_component_seconds"]),
        "recorded token-eight selection boundary",
    )
    assert_close(
        terminal,
        float(profile["user_visible_latency"]["terminal_state_advance_seconds_after_eighth_selection"]),
        "terminal stack boundary",
    )
    return {
        "timing_contract": (
            "logits select each generated token before that token's decode stack; "
            "the final decode stack begins after token eight selection"
        ),
        "total_evidence_wall_seconds": evidence_wall,
        "terminal_state_advance_stack_seconds": terminal,
        "time_through_token_eight_selection_recorded_components_seconds": recorded_through_eight,
        "time_through_token_eight_selection_wall_minus_terminal_seconds": subtractive_upper_bound,
        "wall_minus_terminal_is_upper_bound": True,
        "unassigned_runner_bookkeeping_seconds": unassigned,
        "subtractive_minus_recorded_components_seconds": subtractive_upper_bound - recorded_through_eight,
        "time_to_first_token_recorded_components_seconds": tokens[0]["recorded_selection_latency_seconds"],
        "tokens_2_through_8_inter_token_latency_seconds": summarize(
            row["recorded_selection_latency_seconds"] for row in tokens[1:]
        ),
        "generated_token_selection_records": tokens,
        "generated_token_logits_seconds": summarize(row["selection_logits_seconds"] for row in tokens),
        "generated_token_preceding_transformer_stack_seconds": summarize(
            row["transformer_stack_before_selection_seconds"] for row in tokens
        ),
        "caveat": (
            "the source records component timers, not a dedicated token-eight wall timestamp; "
            "wall-minus-terminal retains small unassigned runner bookkeeping"
        ),
    }


def layer_row(layer: dict[str, Any]) -> dict[str, Any]:
    attributed = component_sum(layer["cache_delta"])
    wall = float(layer["seconds"])
    residual = wall - attributed
    if residual < -1e-9:
        raise ValueError("negative layer residual")
    residual = max(0.0, residual)
    delta = layer["cache_delta"]
    return {
        "layer": int(layer["layer"]),
        "layer_wall_seconds": wall,
        "expert_cache_attributed_seconds": attributed,
        "uninstrumented_residual_seconds": residual,
        "uninstrumented_residual_fraction": residual / wall,
        "decoded_cache_hits": int(delta["decoded_cache_hits"]),
        "decoded_cache_misses": int(delta["decoded_cache_misses"]),
        "transient_releases": int(delta["transient_releases"]),
    }


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    xmean = sum(xs) / len(xs)
    ymean = sum(ys) / len(ys)
    xvar = sum((value - xmean) ** 2 for value in xs)
    yvar = sum((value - ymean) ** 2 for value in ys)
    if xvar == 0.0 or yvar == 0.0:
        return None
    return sum((x - xmean) * (y - ymean) for x, y in zip(xs, ys, strict=True)) / math.sqrt(xvar * yvar)


def per_layer_analysis(golden: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    cold = [layer_row(layer) for layer in golden["timings"][0]["layers"]]
    warm_stacks = [[layer_row(layer) for layer in timing["layers"]] for timing in golden["timings"][1:]]
    if any(len(stack) != 79 for stack in warm_stacks):
        raise ValueError("incomplete warm layer stack")

    by_layer = []
    for layer_id in range(79):
        rows = [stack[layer_id] for stack in warm_stacks]
        entry = {
            "layer": layer_id,
            "architecture_group": "leading_dense" if layer_id < 3 else "moe",
            "warm_samples": rows,
            "warm_uninstrumented_residual_samples_seconds": [
                row["uninstrumented_residual_seconds"] for row in rows
            ],
            "layer_wall_seconds": summarize(row["layer_wall_seconds"] for row in rows),
            "expert_cache_attributed_seconds": summarize(
                row["expert_cache_attributed_seconds"] for row in rows
            ),
            "uninstrumented_residual_seconds": summarize(
                row["uninstrumented_residual_seconds"] for row in rows
            ),
            "uninstrumented_residual_fraction": summarize(
                row["uninstrumented_residual_fraction"] for row in rows
            ),
            "decoded_cache_hits": summarize(row["decoded_cache_hits"] for row in rows),
            "decoded_cache_misses": summarize(row["decoded_cache_misses"] for row in rows),
            "transient_releases": summarize(row["transient_releases"] for row in rows),
        }
        by_layer.append(entry)

    dense_rows = [row for stack in warm_stacks for row in stack[:3]]
    moe_rows = [row for stack in warm_stacks for row in stack[3:]]
    warm_stack_reconciliation = []
    for timing, rows in zip(golden["timings"][1:], warm_stacks, strict=True):
        layer_residual_sum = sum(row["uninstrumented_residual_seconds"] for row in rows)
        stack_residual = float(timing["stack_seconds"]) - component_sum(timing["cache_delta"])
        warm_stack_reconciliation.append(
            {
                "position": timing["position"],
                "token_id": timing["token"],
                "stack_uninstrumented_residual_seconds": stack_residual,
                "layer_uninstrumented_residual_sum_seconds": layer_residual_sum,
                "outside_layer_timer_residual_seconds": stack_residual - layer_residual_sum,
            }
        )

    top10 = sorted(
        by_layer,
        key=lambda item: (-float(item["uninstrumented_residual_seconds"]["mean"]), item["layer"]),
    )[:10]
    top10_public = [
        {
            "rank": rank,
            "layer": item["layer"],
            "architecture_group": item["architecture_group"],
            "mean_residual_seconds": item["uninstrumented_residual_seconds"]["mean"],
            "median_residual_seconds": item["uninstrumented_residual_seconds"]["median"],
            "minimum_residual_seconds": item["uninstrumented_residual_seconds"]["minimum"],
            "maximum_residual_seconds": item["uninstrumented_residual_seconds"]["maximum"],
            "sample_variance_across_tokens": item["uninstrumented_residual_seconds"]["sample_variance"],
        }
        for rank, item in enumerate(top10, start=1)
    ]

    releases = [float(row["transient_releases"]) for row in moe_rows]
    misses = [float(row["decoded_cache_misses"]) for row in moe_rows]
    residuals = [float(row["uninstrumented_residual_seconds"]) for row in moe_rows]
    per_release = [residual / release for residual, release in zip(residuals, releases, strict=True) if release > 0]
    cleanup = {
        "scope": "warm MoE layer-token observations only",
        "observation_count": len(moe_rows),
        "transient_releases_unique": sorted(set(int(value) for value in releases)),
        "routed_matrix_misses_unique": sorted(set(int(value) for value in misses)),
        "residual_seconds_per_transient_release": summarize(per_release),
        "pearson_residual_vs_transient_releases": pearson(releases, residuals),
        "pearson_residual_vs_routed_matrix_misses": pearson(misses, residuals),
        "correlation_is_meaningful": False,
        "reason": (
            "transient releases and routed matrix misses are constant across the warm MoE population; "
            "including layers 0-2 would confound different architectures rather than isolate cleanup"
        ),
        "causal_cleanup_cost_isolated": False,
        "conclusion": (
            "existing evidence cannot isolate cleanup cost; layer 8 has the same release/miss count "
            "as other MoE layers but a much larger residual, so release count alone does not explain it"
        ),
    }
    analysis = {
        "residual_definition": (
            "layer wall minus expert-cache storage, dequantization, contiguous-buffer, "
            "MLX matrix-build, and MLX matvec seconds"
        ),
        "residual_label": "uninstrumented residual",
        "cold_by_layer": cold,
        "warm_by_layer": by_layer,
        "layers_0_through_2": {
            "individual": [by_layer[index] for index in range(3)],
            "across_layer_token_observations": summarize(
                row["uninstrumented_residual_seconds"] for row in dense_rows
            ),
        },
        "moe_layers_3_through_78": {
            "layer_count": 76,
            "across_layer_token_observations": summarize(
                row["uninstrumented_residual_seconds"] for row in moe_rows
            ),
            "mean_residual_by_layer_distribution": summarize(
                item["uninstrumented_residual_seconds"]["mean"] for item in by_layer[3:]
            ),
        },
        "top_10_layers_by_mean_absolute_residual_seconds": top10_public,
        "warm_stack_reconciliation": warm_stack_reconciliation,
        "limitation": (
            "residual contains all work outside expert-cache component timers; it is not a direct trunk "
            "or cleanup measurement"
        ),
    }
    return analysis, cleanup


def semantic_role(name: str) -> tuple[str, str]:
    if name == "token_embd.weight":
        return "token_embedding", "embedding"
    if name == "output.weight":
        return "full_vocabulary_output_projection", "output_head"
    if name == "output_norm.weight":
        return "final_output_norm", "output_head"
    if ".nextn." in name:
        return "next_token_prediction_auxiliary", "other_trunk"
    if ".indexer." in name:
        return "dsa_indexer", "attention_mla"
    if ".attn_k_b." in name or ".attn_v_b." in name:
        return "mla_per_head_projection", "attention_mla"
    if ".attn_q_a." in name:
        return "mla_query_a_projection", "attention_mla"
    if ".attn_q_b." in name:
        return "mla_query_b_projection", "attention_mla"
    if ".attn_kv_a_mqa." in name:
        return "mla_kv_a_projection", "attention_mla"
    if ".attn_output." in name:
        return "attention_output_projection", "attention_mla"
    if ".attn_q_a_norm." in name or ".attn_kv_a_norm." in name:
        return "mla_low_rank_norm", "attention_mla"
    if ".attn_norm." in name:
        return "layer_attention_norm", "router_norms"
    if ".ffn_gate_inp." in name:
        return "moe_router_projection", "router_norms"
    if ".exp_probs_b." in name:
        return "moe_router_bias", "router_norms"
    if ".ffn_norm." in name:
        return "layer_ffn_norm", "router_norms"
    if re.search(r"\.ffn_(?:down|gate|up)\.weight$", name):
        return "leading_dense_ffn_projection", "other_trunk"
    return "other_trunk", "other_trunk"


def is_exercised_short_context(name: str) -> bool:
    return ".indexer." not in name and ".nextn." not in name


def read_behavior(name: str, dims: list[int], type_id: int, exercised: bool) -> dict[str, int]:
    if not exercised:
        return {
            "row_pread_calls": 0,
            "direct_tensor_read_calls": 0,
            "bulk_path_read_calls": 0,
            "encoded_bytes_requested": 0,
        }
    if name == "token_embd.weight":
        return {
            "row_pread_calls": 1,
            "direct_tensor_read_calls": 0,
            "bulk_path_read_calls": 1,
            "encoded_bytes_requested": nbytes_for_tensor(type_id, int(dims[0])),
        }
    if len(dims) == 1:
        encoded = nbytes_for_tensor(type_id, int(dims[0]))
        return {
            "row_pread_calls": 0,
            "direct_tensor_read_calls": 1,
            "bulk_path_read_calls": 1,
            "encoded_bytes_requested": encoded,
        }
    elements = math.prod(int(value) for value in dims)
    row_calls = int(dims[1]) if len(dims) == 2 else int(dims[1]) * int(dims[2])
    return {
        "row_pread_calls": row_calls,
        "direct_tensor_read_calls": 0,
        "bulk_path_read_calls": 1,
        "encoded_bytes_requested": nbytes_for_tensor(type_id, elements),
    }


def residency_class(name: str, group: str, decoded_bytes: int, exercised: bool) -> str:
    if not exercised:
        return "not_exercised"
    if group == "output_head":
        return "hot_subset_candidate"
    if group == "router_norms" and decoded_bytes <= 8 * 1024**2:
        return "small_decoded_candidate"
    if name == "token_embd.weight":
        return "row_access_only"
    return "conditional_requires_measurement"


def aggregate_inventory(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = str(row[key])
        entry = groups.setdefault(
            value,
            {
                key: row[key],
                "tensor_count": 0,
                "compressed_bytes": 0,
                "decoded_f32_bytes": 0,
                "prompt_row_pread_calls": 0,
                "prompt_bulk_path_read_calls": 0,
                "prompt_encoded_bytes_requested": 0,
            },
        )
        entry["tensor_count"] += 1
        entry["compressed_bytes"] += row["compressed_bytes"]
        entry["decoded_f32_bytes"] += row["decoded_f32_bytes"]
        behavior = row["short_context_read_behavior"]
        entry["prompt_row_pread_calls"] += behavior["row_pread_calls"]
        entry["prompt_bulk_path_read_calls"] += behavior["bulk_path_read_calls"]
        entry["prompt_encoded_bytes_requested"] += behavior["encoded_bytes_requested"]
    return sorted(groups.values(), key=lambda item: str(item[key]))


def build_inventory(catalog: dict[str, Any]) -> dict[str, Any]:
    rows = []
    excluded = []
    for tensor in catalog["tensors"]:
        name = tensor["name"]
        if EXPERT_RE.search(name):
            excluded.append(name)
            continue
        dims = [int(value) for value in tensor["dims"]]
        elements = math.prod(dims)
        compressed = nbytes_for_tensor(int(tensor["type_id"]), elements)
        decoded = elements * 4
        layer_match = LAYER_RE.match(name)
        layer = int(layer_match.group(1)) if layer_match else None
        role, group = semantic_role(name)
        exercised = is_exercised_short_context(name)
        behavior = read_behavior(name, dims, int(tensor["type_id"]), exercised)
        logical_touches = 1 if exercised else 0
        rows.append(
            {
                "name": name,
                "layer": layer,
                "semantic_role": role,
                "trunk_group": group,
                "quantization": tensor["type"],
                "type_id": tensor["type_id"],
                "dimensions": dims,
                "compressed_bytes": compressed,
                "decoded_f32_bytes": decoded,
                "expected_touches_per_prompt_token": logical_touches,
                "expected_touches_per_decode_token": logical_touches,
                "token_invariant": True,
                "layer_specific": layer is not None,
                "golden_short_context_exercised": exercised,
                "natural_residency_candidate": residency_class(name, group, decoded, exercised),
                "short_context_read_behavior": behavior,
            }
        )
    if len(rows) + len(excluded) != catalog["tensor_count"] or len(excluded) != 456:
        raise ValueError("expert exclusion partition changed")
    if any(EXPERT_RE.search(row["name"]) for row in rows):
        raise ValueError("expert tensor leaked into trunk inventory")
    total_compressed = sum(row["compressed_bytes"] for row in rows)
    total_decoded = sum(row["decoded_f32_bytes"] for row in rows)
    return {
        "scope": "all catalog tensors excluding routed and shared expert matrices",
        "tensor_count": len(rows),
        "excluded_expert_matrix_count": len(excluded),
        "excluded_expert_name_patterns": [
            "*.ffn_{down,gate,up}_exps.weight",
            "*.ffn_{down,gate,up}_shexp.weight",
        ],
        "total_compressed_bytes": total_compressed,
        "total_decoded_f32_bytes": total_decoded,
        "tensors": rows,
        "by_quantization": aggregate_inventory(rows, "quantization"),
        "by_semantic_role": aggregate_inventory(rows, "semantic_role"),
        "by_trunk_group": aggregate_inventory(rows, "trunk_group"),
        "by_layer": aggregate_inventory(rows, "layer"),
        "touch_contract": (
            "one logical short-context use per processed token for exercised tensors; "
            "output/head use selects the next token, and the terminal stack has no later logits use"
        ),
        "conditional_exclusions": (
            "DSA indexer tensors are not touched while visible context is <=2048; nextn tensors "
            "are outside the committed runner"
        ),
        "residency_candidate_legend": {
            "not_exercised": "not exercised by the frozen short-context run",
            "hot_subset_candidate": "measured repeated boundary; requires residency experiment",
            "small_decoded_candidate": "small repeated control tensor; requires residency experiment",
            "row_access_only": "embedding row lookup does not justify full decode from catalog arithmetic",
            "conditional_requires_measurement": "measure a representative boundary before residency",
        },
    }


def inventory_total(inventory: dict[str, Any], *, groups: set[str], field: str) -> int:
    return sum(
        int(row[field]) for row in inventory["tensors"] if row["trunk_group"] in groups
    )


def memory_budgets(inventory: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    capacity = 128 * GIB
    shared_budget = 16 * GIB
    shared_resident = 11_475_615_744
    peak_rss = int(profile["warm"]["peak_rss_bytes"]["maximum"])
    safety_reserve = 24 * GIB
    extra_recommendation_margin = 4 * GIB
    output_decoded = inventory_total(inventory, groups={"output_head"}, field="decoded_f32_bytes")
    hot_decoded = inventory_total(
        inventory, groups={"output_head", "router_norms"}, field="decoded_f32_bytes"
    )
    options = [
        ("A", "compressed_all_trunk_residency", inventory["total_compressed_bytes"]),
        ("B", "decoded_f32_all_trunk_residency", inventory["total_decoded_f32_bytes"]),
        (
            "C",
            "decoded_attention_mla_only_residency",
            inventory_total(inventory, groups={"attention_mla"}, field="decoded_f32_bytes"),
        ),
        ("D", "decoded_output_head_only_residency", output_decoded),
        (
            "E",
            "decoded_hot_subset_candidate_output_head_plus_router_norms",
            hot_decoded,
        ),
        (
            "F",
            "compressed_all_trunk_plus_decoded_hot_subset",
            inventory["total_compressed_bytes"] + hot_decoded,
        ),
    ]
    rows = []
    for key, name, logical_bytes in options:
        projected_peak = peak_rss + logical_bytes
        headroom = capacity - projected_peak
        reserve_margin = headroom - safety_reserve
        if reserve_margin < 0:
            admission = "unsafe_exceeds_24_gib_reserve"
        elif reserve_margin < extra_recommendation_margin:
            admission = "nominal_only_not_recommended_without_allocator_measurement"
        else:
            admission = "fits_logical_budget_with_conservative_margin"
        rows.append(
            {
                "option": key,
                "name": name,
                "logical_bytes": logical_bytes,
                "logical_gib": logical_bytes / GIB,
                "ratio_to_128_gib": logical_bytes / capacity,
                "ratio_to_16_gib_shared_cache_budget": logical_bytes / shared_budget,
                "projected_peak_rss_bytes_if_incremental": projected_peak,
                "projected_headroom_bytes": headroom,
                "margin_after_24_gib_safety_reserve_bytes": reserve_margin,
                "admission": admission,
            }
        )
    return {
        "analysis_kind": "logical budget arithmetic, not measured MLX allocator overhead",
        "m1_ultra_capacity_bytes": capacity,
        "protected_shared_cache_budget_bytes": shared_budget,
        "observed_decoded_shared_resident_bytes": shared_resident,
        "observed_peak_rss_bytes": peak_rss,
        "observed_peak_already_includes_shared_residency": True,
        "conservative_safety_reserve_bytes": safety_reserve,
        "additional_recommendation_margin_bytes": extra_recommendation_margin,
        "available_incremental_bytes_after_peak_and_safety_reserve": capacity - peak_rss - safety_reserve,
        "options": rows,
        "recommendation_limit": (
            "only D and E are safe logical fixture candidates; this arithmetic does not choose a "
            "production residency strategy or account for MLX allocator fragmentation"
        ),
    }


def sum_behavior(rows: list[dict[str, Any]]) -> dict[str, int | float]:
    row_calls = sum(row["short_context_read_behavior"]["row_pread_calls"] for row in rows)
    direct = sum(row["short_context_read_behavior"]["direct_tensor_read_calls"] for row in rows)
    bulk = sum(row["short_context_read_behavior"]["bulk_path_read_calls"] for row in rows)
    encoded = sum(row["short_context_read_behavior"]["encoded_bytes_requested"] for row in rows)
    current_total = row_calls + direct
    return {
        "current_row_level_pread_calls": row_calls,
        "current_direct_tensor_read_calls": direct,
        "current_total_read_operations": current_total,
        "whole_matrix_path_total_read_operations": bulk,
        "request_count_reduction_factor": current_total / bulk if bulk else 0.0,
        "encoded_checkpoint_bytes_requested": encoded,
    }


def row_read_amplification(inventory: dict[str, Any]) -> dict[str, Any]:
    rows = inventory["tensors"]
    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_quant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_group[row["trunk_group"]].append(row)
        by_quant[row["quantization"]].append(row)
    return {
        "scope": "golden short-context trunk only; routed/shared experts excluded",
        "prompt_token": sum_behavior(rows),
        "decode_token_with_next_token_selection": sum_behavior(rows),
        "by_trunk_group": [
            {"trunk_group": name, **sum_behavior(group)}
            for name, group in sorted(by_group.items())
        ],
        "by_quantization": [
            {"quantization": name, **sum_behavior(group)}
            for name, group in sorted(by_quant.items())
        ],
        "interpretation": (
            "request-count arithmetic only; equal encoded bytes are expected for full matrix use, "
            "and no latency or speedup is inferred"
        ),
    }


def experiments_and_decisions(inventory: dict[str, Any], budgets: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    impact = sorted(
        inventory["by_quantization"],
        key=lambda row: (-int(row["prompt_encoded_bytes_requested"]), row["quantization"]),
    )
    format_order = [row["quantization"] for row in impact if row["prompt_encoded_bytes_requested"] > 0]
    experiments = [
        {
            "id": "A",
            "name": "whole-matrix-read-only",
            "runtime_change_allowed": "bounded fixture implementation only",
            "representative_matrix": "blk.8.attn_output.weight",
            "representative_mla_layer": 8,
            "reason": "layer 8 is the largest warm MoE-layer residual and includes real Q6_K attention matrices",
            "decoder_math": "unchanged scalar reference",
            "required_gates": [
                "one bounded whole-matrix positional read",
                "exact decoded f32 bits and exact MLX output against current row-read path",
                "storage bytes and read-call count",
                "storage, decode, buffer, MLX build, matvec, and total boundary wall",
                "RSS and peak RSS",
            ],
            "preferred_machine_class": "M2 Max with hash-bound local fixture where permitted; M1 Ultra only for exact-checkpoint extraction or gate",
        },
        {
            "id": "B",
            "name": "vectorized-trunk-decode",
            "dependency": "Experiment A exact-output gate",
            "format_priority_from_catalog_touch_weighted_bytes": format_order,
            "selection_rule": (
                "choose the largest measured boundary opportunity after A; catalog order alone does not authorize implementation"
            ),
            "required_gates": [
                "scalar decoder remains the independent oracle",
                "exact decoded f32 bits including signed zero",
                "decode, buffer, MLX build, matvec, and total measured separately",
                "real hash-bound fixture identity without committed weight bytes",
                "deterministic repeats and malformed/truncated input failures",
            ],
            "preferred_machine_class": "M2 Max for fixtures; M1 Ultra only when the immutable full checkpoint is necessary",
        },
    ]
    budget_map = {row["option"]: row for row in budgets["options"]}
    decisions = [
        {
            "strategy": "stream_plus_scalar_decode",
            "memory_cost": "no new steady residency; current transient decoded matrix materialization remains",
            "repeated_work_avoided": "none",
            "implementation_complexity": "existing reference",
            "numerical_risk": "lowest",
            "validation": "retained scalar/golden oracle",
        },
        {
            "strategy": "bulk_read_plus_scalar_decode",
            "memory_cost": "up to one compressed matrix-sized transient buffer; no new steady residency",
            "repeated_work_avoided": "row-level read requests only",
            "implementation_complexity": "low",
            "numerical_risk": "low if decoder iteration order is unchanged",
            "validation": "Experiment A exact-bit and exact-output gate",
        },
        {
            "strategy": "bulk_read_plus_vector_decode",
            "memory_cost": "compressed transient plus existing contiguous decoded matrix",
            "repeated_work_avoided": "row requests and scalar Python decoder loops",
            "implementation_complexity": "medium per format",
            "numerical_risk": "exact-bit risk at decoder boundary",
            "validation": "Experiment B scalar-oracle differential gate",
        },
        {
            "strategy": "compressed_all_trunk_residency_plus_vector_decode",
            "memory_cost": f"{budget_map['A']['logical_gib']:.3f} GiB steady logical",
            "repeated_work_avoided": "checkpoint reads after admission; decode remains",
            "implementation_complexity": "high residency and pressure policy",
            "numerical_risk": "decoder risk unchanged",
            "validation": "memory-pressure/allocator measurement plus A/B correctness",
            "budget_disposition": budget_map["A"]["admission"],
        },
        {
            "strategy": "decoded_hot_subset_residency",
            "memory_cost": f"{budget_map['E']['logical_gib']:.3f} GiB steady logical candidate",
            "repeated_work_avoided": "decode/build for selected output and small control tensors",
            "implementation_complexity": "medium; explicit protected subset",
            "numerical_risk": "low after exact decode; lifetime/pressure risk remains",
            "validation": "boundary measurements and cache lifetime/pressure gates",
            "budget_disposition": budget_map["E"]["admission"],
        },
        {
            "strategy": "decoded_all_trunk_residency",
            "memory_cost": f"{budget_map['B']['logical_gib']:.3f} GiB steady logical",
            "repeated_work_avoided": "most trunk reads/decode/build",
            "implementation_complexity": "high",
            "numerical_risk": "low arithmetic risk; high memory/recovery risk",
            "validation": "not admitted under current memory budget",
            "budget_disposition": budget_map["B"]["admission"],
        },
        {
            "strategy": "hybrid_compressed_all_plus_decoded_hot",
            "memory_cost": f"{budget_map['F']['logical_gib']:.3f} GiB steady logical",
            "repeated_work_avoided": "reads for all trunk and decode/build for hot subset",
            "implementation_complexity": "highest of listed options",
            "numerical_risk": "decoder and residency lifetime risks",
            "validation": "not admitted under current memory budget",
            "budget_disposition": budget_map["F"]["admission"],
        },
    ]
    return experiments, decisions


def build_document() -> dict[str, Any]:
    golden = load_json(GOLDEN_PATH)
    profile = load_json(PROFILE_PATH)
    catalog = load_json(CATALOG_PATH)
    validate_sources(golden, profile, catalog)
    preserved = preserved_metrics(golden, profile)
    timing = user_visible_timing(golden, profile)
    layers, cleanup = per_layer_analysis(golden)
    inventory = build_inventory(catalog)
    budgets = memory_budgets(inventory, profile)
    amplification = row_read_amplification(inventory)
    experiments, decisions = experiments_and_decisions(inventory, budgets)
    return {
        "schema": "pulsarmlx.research.glm52-post-golden8-calculations",
        "schema_version": "1.0.0",
        "feature_id": "016-glm52-full-execution",
        "actual_status": "passed",
        "calculation_only": True,
        "model_inference_executed": False,
        "sources": {
            "golden_evidence": GOLDEN_PATH.relative_to(ROOT).as_posix(),
            "golden_evidence_sha256": sha256(GOLDEN_PATH),
            "golden_source_commit": golden["source_commit"],
            "authoritative_derived_profile": PROFILE_PATH.relative_to(ROOT).as_posix(),
            "authoritative_derived_profile_sha256": sha256(PROFILE_PATH),
            "catalog": CATALOG_PATH.relative_to(ROOT).as_posix(),
            "catalog_sha256": sha256(CATALOG_PATH),
            "catalog_source_commit": catalog["source_commit"],
        },
        "already_verified_metrics": preserved,
        "user_visible_timing": timing,
        "per_layer_analysis": layers,
        "cleanup_hypothesis": cleanup,
        "trunk_inventory": inventory,
        "trunk_residency_memory_budgets": budgets,
        "row_read_request_amplification": amplification,
        "next_cheap_experiments": experiments,
        "trunk_residency_decision_table": decisions,
        "feature_018": {
            "provisional_title": "018-direct-quantized-metal-runtime",
            "first_kernel_selected": False,
            "selection_requires": [
                "golden-eight expert-path cost",
                "catalog-derived trunk composition",
                "representative trunk bulk-read and vectorized boundary measurements",
                "post-trunk-optimization profile",
            ],
        },
        "another_full_m1_ultra_run_required_now": False,
        "next_full_run_gate": (
            "only after a bounded trunk optimization passes exact/numerical fixtures and requires "
            "full-model correctness confirmation"
        ),
    }


def split_inventory(document: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    inventory = document["trunk_inventory"]
    inventory_record = {
        "schema": "pulsarmlx.research.glm52-gguf-trunk-inventory",
        "schema_version": "1.0.0",
        "feature_id": document["feature_id"],
        "actual_status": "passed",
        "calculation_only": True,
        "model_inference_executed": False,
        "source_catalog": document["sources"]["catalog"],
        "source_catalog_sha256": document["sources"]["catalog_sha256"],
        "source_catalog_commit": document["sources"]["catalog_source_commit"],
        **inventory,
    }
    inventory_text = serialize(inventory_record)
    summary = {key: value for key, value in inventory.items() if key != "tensors"}
    summary.update(
        {
            "machine_readable_inventory": INVENTORY_OUT.relative_to(ROOT).as_posix(),
            "machine_readable_inventory_sha256": hashlib.sha256(inventory_text.encode()).hexdigest(),
        }
    )
    document["trunk_inventory"] = summary
    return document, inventory_record


def fmt_gib(value: int | float) -> str:
    return f"{float(value) / GIB:.3f}"


def render_report(document: dict[str, Any]) -> str:
    preserved = document["already_verified_metrics"]
    timing = document["user_visible_timing"]
    layers = document["per_layer_analysis"]
    cleanup = document["cleanup_hypothesis"]
    inventory = document["trunk_inventory"]
    budgets = document["trunk_residency_memory_budgets"]
    amplification = document["row_read_request_amplification"]
    warm = preserved["warm_stack_seconds"]
    lines = [
        "# GLM-5.2 Post-Golden-Eight Calculations",
        "",
        "**Status**: passed; calculation-only analysis with no model inference",
        "",
        "This report extends the authoritative `f016-golden8-derived-profile-0001.json`. It does not overwrite or reinterpret its existing metrics.",
        "",
        "## Already-verified golden-eight metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Complete evidence wall | {preserved['golden_evidence_wall_seconds']:.6f} s |",
        f"| Cold prompt stack | {preserved['cold_prompt_stack_seconds']:.6f} s |",
        f"| Warm stacks | {warm['sample_count']} |",
        f"| Warm mean / median | {warm['mean']:.6f} / {warm['median']:.6f} s |",
        f"| Warm sample SD / min / max | {warm['sample_standard_deviation']:.6f} / {warm['minimum']:.6f} / {warm['maximum']:.6f} s |",
        f"| Watcher snapshots / valid intervals / resets | {preserved['watcher_snapshot_count']} / {preserved['watcher_valid_one_stack_interval_count']} / {preserved['watcher_counter_reset_interval_count']} |",
        f"| Shared-cache hits | {preserved['decoded_cache_hits']} |",
        f"| Decoded / compressed bytes avoided | {preserved['decoded_bytes_avoided']} / {preserved['storage_bytes_avoided']} |",
        f"| CPU fallbacks / evictions / rejections | {preserved['cpu_fallbacks']} / {preserved['evictions']} / {preserved['admission_rejections']} |",
        "",
        "All retained resource states were normal. The expert-cache-only per-quant ranking, warm residual, and storage/prefetch deferral remain authoritative in the earlier derived profile.",
        "",
        "## Honest time through selection of token 8",
        "",
        "| Boundary | Seconds |",
        "| --- | ---: |",
        f"| Complete nine-stack evidence wall | {timing['total_evidence_wall_seconds']:.6f} |",
        f"| Redundant terminal state-advance stack | {timing['terminal_state_advance_stack_seconds']:.6f} |",
        f"| Through token-8 selection, recorded components | {timing['time_through_token_eight_selection_recorded_components_seconds']:.6f} |",
        f"| Evidence wall minus terminal stack (upper bound) | {timing['time_through_token_eight_selection_wall_minus_terminal_seconds']:.6f} |",
        f"| Unassigned runner bookkeeping | {timing['unassigned_runner_bookkeeping_seconds']:.6f} |",
        f"| Time to first token, recorded components | {timing['time_to_first_token_recorded_components_seconds']:.6f} |",
        "",
        "The subtraction is an upper bound because the source has no dedicated token-eight wall timestamp; it retains 0.351 seconds of unassigned runner bookkeeping. The component boundary follows the source order exactly: preceding transformer stack, logits selection, then the selected token's stack.",
        "",
        "### Generated-token selection components",
        "",
        "| Token # | ID | Preceding stack s | Logits s | Selection component s |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in timing["generated_token_selection_records"]:
        lines.append(
            f"| {row['generated_token_number']} | {row['token_id']} | "
            f"{row['transformer_stack_before_selection_seconds']:.6f} | "
            f"{row['selection_logits_seconds']:.6f} | {row['recorded_selection_latency_seconds']:.6f} |"
        )
    inter = timing["tokens_2_through_8_inter_token_latency_seconds"]
    lines.extend(
        [
            "",
            f"Tokens 2–8 inter-token components: n={inter['sample_count']}, mean {inter['mean']:.6f} s, median {inter['median']:.6f} s, sample SD {inter['sample_standard_deviation']:.6f} s, range {inter['minimum']:.6f}–{inter['maximum']:.6f} s.",
            "",
            "## Per-layer uninstrumented residual",
            "",
            "Residual means layer wall minus expert-cache storage, dequantization, contiguous-buffer, MLX-build, and MLX-matvec timers. It is not labeled trunk or cleanup cost.",
            "",
            "### Layers 0–2",
            "",
            "| Layer | Mean residual s | Median | Min | Max | Sample variance |",
            "| ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for entry in layers["layers_0_through_2"]["individual"]:
        stats = entry["uninstrumented_residual_seconds"]
        lines.append(
            f"| {entry['layer']} | {stats['mean']:.6f} | {stats['median']:.6f} | "
            f"{stats['minimum']:.6f} | {stats['maximum']:.6f} | {stats['sample_variance']:.6f} |"
        )
    moe = layers["moe_layers_3_through_78"]["across_layer_token_observations"]
    lines.extend(
        [
            "",
            f"MoE layers 3–78 across {moe['sample_count']} layer-token observations: mean {moe['mean']:.6f} s, median {moe['median']:.6f} s, min {moe['minimum']:.6f} s, max {moe['maximum']:.6f} s, p95(Type 7) {moe['p95_type7']:.6f} s.",
            "",
            "### Top 10 layers by mean residual",
            "",
            "| Rank | Layer | Group | Mean s | Median | Min | Max | Token variance |",
            "| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in layers["top_10_layers_by_mean_absolute_residual_seconds"]:
        lines.append(
            f"| {row['rank']} | {row['layer']} | {row['architecture_group']} | "
            f"{row['mean_residual_seconds']:.6f} | {row['median_residual_seconds']:.6f} | "
            f"{row['minimum_residual_seconds']:.6f} | {row['maximum_residual_seconds']:.6f} | "
            f"{row['sample_variance_across_tokens']:.6f} |"
        )
    release = cleanup["residual_seconds_per_transient_release"]
    lines.extend(
        [
            "",
            "## Cleanup hypothesis",
            "",
            f"Warm MoE observations always recorded {cleanup['transient_releases_unique']} transient releases and {cleanup['routed_matrix_misses_unique']} routed matrix misses. Residual per release had mean {release['mean']:.6f} s and range {release['minimum']:.6f}–{release['maximum']:.6f} s.",
            "",
            "Pearson correlation is undefined because both candidate predictors are constant within the relevant warm MoE population. Including layers 0–2 would confound different architectures. Existing data therefore cannot isolate cleanup cost or support a causal cleanup claim; layer 8 has the same release count but a much larger residual.",
            "",
            "## GGUF trunk inventory",
            "",
            f"The catalog contains {inventory['tensor_count']} trunk tensors and excludes {inventory['excluded_expert_matrix_count']} routed/shared expert matrices. Total logical trunk storage is {fmt_gib(inventory['total_compressed_bytes'])} GiB compressed and {fmt_gib(inventory['total_decoded_f32_bytes'])} GiB decoded f32.",
            "",
            "### By trunk group",
            "",
            "| Group | Tensors | Compressed GiB | Decoded f32 GiB | Row preads/token | Bulk reads/token |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in inventory["by_trunk_group"]:
        lines.append(
            f"| {row['trunk_group']} | {row['tensor_count']} | {fmt_gib(row['compressed_bytes'])} | "
            f"{fmt_gib(row['decoded_f32_bytes'])} | {row['prompt_row_pread_calls']} | "
            f"{row['prompt_bulk_path_read_calls']} |"
        )
    lines.extend(
        [
            "",
            "### By quantization",
            "",
            "| Quantization | Tensors | Compressed GiB | Decoded f32 GiB | Requested GiB/token | Row preads/token |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in inventory["by_quantization"]:
        lines.append(
            f"| {row['quantization']} | {row['tensor_count']} | {fmt_gib(row['compressed_bytes'])} | "
            f"{fmt_gib(row['decoded_f32_bytes'])} | {fmt_gib(row['prompt_encoded_bytes_requested'])} | "
            f"{row['prompt_row_pread_calls']} |"
        )
    lines.extend(
        [
            "",
        "Every tensor's layer, semantic role, name, quantization, dimensions, bytes, touch contract, and residency classification is retained in the dedicated machine-readable inventory JSON. Indexer tensors are untouched in the frozen short context; nextn tensors are outside the runner.",
            "",
            "## Logical trunk residency budgets",
            "",
            "The observed peak RSS already includes actual shared-expert residency. Projections add each option to that peak, retain a 24 GiB safety reserve, and require another 4 GiB margin before calling an option a safe fixture candidate. They do not model MLX allocator overhead or fragmentation.",
            "",
            "| Option | Logical GiB | Projected headroom GiB | Margin after 24 GiB reserve | Disposition |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for row in budgets["options"]:
        lines.append(
            f"| {row['option']} {row['name']} | {row['logical_gib']:.3f} | "
            f"{fmt_gib(row['projected_headroom_bytes'])} | "
            f"{fmt_gib(row['margin_after_24_gib_safety_reserve_bytes'])} | {row['admission']} |"
        )
    prompt = amplification["prompt_token"]
    lines.extend(
        [
            "",
            "## Row-read request amplification",
            "",
            f"A normal short-context token plus next-token selection issues {prompt['current_row_level_pread_calls']:,} row-level preads and {prompt['current_direct_tensor_read_calls']:,} direct tensor reads for the trunk. A bulk path would use {prompt['whole_matrix_path_total_read_operations']:,} total reads, a {prompt['request_count_reduction_factor']:.2f}× request-count reduction, while requesting the same {fmt_gib(prompt['encoded_checkpoint_bytes_requested'])} GiB of exercised checkpoint bytes. This is request arithmetic, not a speedup claim.",
            "",
            "## Next two cheap experiments",
            "",
            "1. **A — whole-matrix read only.** Use `blk.8.attn_output.weight` and complete MLA layer 8, retain scalar decoder order, require exact f32/output equality, and split storage, decode, buffer, build, matvec, total, RSS, and read-call counts.",
            "2. **B — vectorized trunk decode.** Only after A passes. Select from the catalog touch-weighted order and A's measured boundary result; retain the scalar oracle and exact-bit gates. Do not assume Q6_K or Q8_0 wins before measurement.",
            "",
            "M2 Max should own hash-bound local fixtures where permitted. M1 Ultra is required only for exact-checkpoint extraction or a later full correctness gate.",
            "",
            "## Residency decision",
            "",
            "The machine-readable decision table compares streaming, bulk scalar, bulk vector, compressed residency, decoded hot subset, decoded all-trunk, and hybrid options. Catalog arithmetic does not select a production strategy. Options D/E are safe logical fixture candidates; compressed-all is too close to the reserve to recommend without allocator measurements, and decoded-all/hybrid are unsafe.",
            "",
            "## Feature 018 and next full run",
            "",
            "Feature 018 remains provisionally `018-direct-quantized-metal-runtime`; no first kernel is selected. Another full M1 Ultra run is **not required now**. Run A and B at bounded boundaries first; a full-model run becomes justified only after a candidate optimization passes its exact/numerical fixture gates.",
            "",
        ]
    )
    return "\n".join(lines)


def serialize(document: dict[str, Any]) -> str:
    return json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path, default=JSON_OUT)
    parser.add_argument("--inventory-out", type=Path, default=INVENTORY_OUT)
    parser.add_argument("--report-out", type=Path, default=REPORT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    document, inventory = split_inventory(build_document())
    json_text = serialize(document)
    inventory_text = serialize(inventory)
    report_text = render_report(document)
    if args.check:
        if (
            args.json_out.read_text() != json_text
            or args.inventory_out.read_text() != inventory_text
            or args.report_out.read_text() != report_text
        ):
            raise SystemExit("post-golden-eight outputs are stale")
        print("post-golden-eight calculations: passed")
        return 0
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.inventory_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json_text)
    args.inventory_out.write_text(inventory_text)
    args.report_out.write_text(report_text)
    print("post-golden-eight calculations: generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
