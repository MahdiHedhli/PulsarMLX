#!/usr/bin/env python3
"""Derive the exact post-MoE P2 profile and measured format opportunity."""

from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs/research/glm52/raw/post-f016-inference-p2-moe-vector-0001.json"
MULTI = ROOT / "docs/research/glm52/raw/post-f016-moe-multilayer-all-vector-analysis-0001.json"
OLD_P2 = ROOT / "docs/research/glm52/raw/f016-inference-p2-iq3-0001.json"
JSON_OUT = ROOT / "docs/research/glm52/raw/post-f016-inference-p2-moe-vector-analysis-0001.json"
TABLE_OUT = ROOT / "docs/research/glm52/tables/post-f016-inference-p2-moe-vector-0001.md"
COMPONENTS = ("storage_read_seconds", "dequant_seconds", "contiguous_buffer_seconds", "mlx_matrix_build_seconds", "mlx_matvec_seconds")
QUANT_COMPONENTS = ("storage_read_seconds", "dequant_seconds", "contiguous_buffer_seconds", "mlx_matrix_construct_seconds", "mlx_matrix_eval_seconds", "mlx_matvec_seconds", "cleanup_seconds")


def _mean(values): return sum(values) / len(values)
def _median(values):
    ordered = sorted(values); middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
def _stdev(values):
    mean = _mean(values); return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1)) if len(values) > 1 else 0.0


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate key: {key}")
        out[key] = value
    return out


def _load(path):
    raw = path.read_bytes(); return raw, json.loads(raw, object_pairs_hook=_unique)


def _stack(stack):
    cache = stack["cache_delta"]
    expert = {field: float(cache[field]) for field in COMPONENTS}
    attributed = sum(expert.values())
    return {"phase": stack["phase"], "token": stack["token"], "stack_seconds": float(stack["stack_seconds"]), "logits_seconds_separate": float(stack.get("logits_seconds", 0.0)), "expert_cache_components": expert, "expert_cache_attributed_seconds": attributed, "uninstrumented_residual_seconds": float(stack["stack_seconds"]) - attributed, "decoded_cache_hits": cache["decoded_cache_hits"], "decoded_cache_misses": cache["decoded_cache_misses"], "storage_bytes_avoided": cache["storage_bytes_avoided"], "decoded_bytes_avoided": cache["decoded_bytes_avoided"], "layer_count": len(stack["layers"]), "resource_level": stack["resource_after"]["level"]}


def _quant_map(layer):
    return {row["quantization"]: row["median_components"] for row in layer["quantization_ranking"]}


def build(source_raw, source, multi_raw, multi, old_raw, old):
    if source["actual_status"] != "passed" or source["source_dirty"] or source["generated_token_ids"] != [9703, 21615, 220] or not source["matches_golden_prefix"]:
        raise ValueError("current P2 exact gate failed")
    if source["source_commit"] != "c115c7f6f09fcdcfe13a11ca8d3b94940863b7ab":
        raise ValueError("unexpected P2 source commit")
    if len(source["timings"]) != 3 or len(source["routing"]) != 3:
        raise ValueError("P2 requires three stacks")
    if any(len(stack["layers"]) != 79 for stack in source["timings"]):
        raise ValueError("incomplete transformer stack")
    if any(len(stack["layers"]) != 76 or any(len(layer["expert_ids"]) != 8 for layer in stack["layers"]) for stack in source["routing"]):
        raise ValueError("incomplete routes")
    cache = source["expert_cache"]
    if any(cache[key] for key in ("cpu_fallbacks", "evictions", "admission_rejections")) or cache["decoded_cache_hits"] != 456 or cache["resident_entries"] != 228:
        raise ValueError("P2 cache/fallback contract failed")
    stacks = [_stack(stack) for stack in source["timings"]]
    warm = stacks[1:]
    warm_stats = {}
    for field in ("stack_seconds", "logits_seconds_separate", "expert_cache_attributed_seconds", "uninstrumented_residual_seconds"):
        values = [row[field] for row in warm]
        warm_stats[field] = {"sample_count": 2, "mean_seconds": _mean(values), "median_seconds": _median(values), "sample_standard_deviation_seconds": _stdev(values), "minimum_seconds": min(values), "maximum_seconds": max(values)}
    layers = {row["layer"]: _quant_map(row) for row in multi["layers"]}
    opportunities = {}
    def add(quant, components, layer_count, matrix_touches, role, shape):
        row = opportunities.setdefault(quant, {field: 0.0 for field in QUANT_COMPONENTS})
        for field in QUANT_COMPONENTS: row[field] += float(components[field]) * layer_count
        row.update({"quantization": quant, "layer_count": row.get("layer_count", 0) + layer_count, "matrix_touches_per_warm_stack": row.get("matrix_touches_per_warm_stack", 0) + matrix_touches, "tensor_role": role, "shape_rows_cols": shape})
    add("IQ2_XXS", layers[40]["IQ2_XXS"], 71, 71 * 16, "routed gate/up", [2048, 6144])
    add("IQ3_XXS", layers[40]["IQ3_XXS"], 71, 71 * 8, "routed down", [6144, 2048])
    special_iq2 = {field: _median([layers[layer]["IQ2_XXS"][field] for layer in (75, 76, 77)]) for field in QUANT_COMPONENTS}
    add("IQ2_XXS", special_iq2, 3, 3 * 16, "routed gate/up", [2048, 6144])
    add("IQ2_S", layers[8]["IQ2_S"], 1, 16, "routed gate/up", [2048, 6144])
    for layer in (8, 75, 76, 77): add("IQ4_XS", layers[layer]["IQ4_XS"], 1, 8, "routed down", [6144, 2048])
    add("Q2_K", layers[78]["Q2_K"], 1, 16, "routed gate/up", [2048, 6144])
    add("Q3_K", layers[78]["Q3_K"], 1, 8, "routed down", [6144, 2048])
    ranking = sorted(opportunities.values(), key=lambda row: -row["dequant_seconds"])
    for rank, row in enumerate(ranking, 1):
        row["rank_by_modeled_warm_decode"] = rank
        row["mlx_matrix_build_seconds"] = row["mlx_matrix_construct_seconds"] + row["mlx_matrix_eval_seconds"]
        row["attributed_seconds"] = sum(row[field] for field in QUANT_COMPONENTS)
    modeled_decode = sum(row["dequant_seconds"] for row in ranking)
    observed_warm_decode = _mean([row["expert_cache_components"]["dequant_seconds"] for row in warm])
    historical = {"prior_p2_source_commit": old["source_commit"], "prior_p2_wall_seconds": float(old["seconds"]), "current_p2_wall_seconds": float(source["seconds"]), "cross_commit_wall_ratio": float(old["seconds"]) / float(source["seconds"]), "prior_warm_stack_seconds": [float(old["timings"][1]["stack_seconds"]), float(old["timings"][2]["stack_seconds"])], "current_warm_stack_seconds": [row["stack_seconds"] for row in warm], "cross_commit_warm_median_ratio": _median([old["timings"][1]["stack_seconds"], old["timings"][2]["stack_seconds"]]) / warm_stats["stack_seconds"]["median_seconds"]}
    return {"schema": "pulsarmlx.research.glm52-post-moe-p2-analysis", "schema_version": "1.0.0", "actual_status": "passed", "source": {"record": str(SOURCE.relative_to(ROOT)), "sha256": hashlib.sha256(source_raw).hexdigest(), "source_commit": source["source_commit"]}, "bounded_profile_source": {"record": str(MULTI.relative_to(ROOT)), "sha256": hashlib.sha256(multi_raw).hexdigest(), "source_commit": multi["source"]["source_commit"]}, "correctness": {"generated_token_ids": source["generated_token_ids"], "matches_golden_prefix": source["matches_golden_prefix"], "checkpoint_set_sha256": source["checkpoint"]["checkpoint_set_sha256"], "mlx_device": cache["device"], "cpu_fallbacks": cache["cpu_fallbacks"], "cache_evictions": cache["evictions"], "admission_rejections": cache["admission_rejections"], "complete_stack_count": 3, "complete_route_stack_count": 3}, "timing": {"total_evidence_wall_seconds": float(source["seconds"]), "stacks": stacks, "warm_population": warm_stats}, "cache": {"decoded_cache_hits": cache["decoded_cache_hits"], "decoded_cache_misses": cache["decoded_cache_misses"], "resident_entries": cache["resident_entries"], "bytes_resident": cache["bytes_resident"], "storage_bytes_avoided": cache["storage_bytes_avoided"], "decoded_bytes_avoided": cache["decoded_bytes_avoided"]}, "modeled_warm_quantization_opportunity": {"method": "catalog touch counts multiplied by retained per-quant medians from exact bounded layers; validated against observed P2 warm total decode, not direct per-quant P2 counters", "ranking": ranking, "modeled_decode_seconds": modeled_decode, "observed_warm_decode_mean_seconds": observed_warm_decode, "absolute_error_seconds": abs(modeled_decode - observed_warm_decode), "relative_error_fraction": abs(modeled_decode - observed_warm_decode) / observed_warm_decode}, "historical_cross_commit_observation": historical, "decision": {"largest_remaining_measured_warm_stage": "routed expert decode", "feature_018_first_kernel_candidate": {"tensor_role": "routed gate/up", "quantization": "IQ2_XXS", "shape_rows_cols": [2048, 6144], "matrix_touches_per_warm_stack": ranking[0]["matrix_touches_per_warm_stack"], "modeled_decode_seconds_per_warm_stack": ranking[0]["dequant_seconds"], "status": "selected_candidate_not_implemented"}, "feature_018_scope_sufficient": True, "feature_017_native_primitive": "whole-slab exact IQ2_XXS/IQ3_XXS decode with low-copy evaluated-matrix handoff and bounded route-aware residency", "another_full_model_run_required": False}, "limitations": ["Two warm stacks are an exact correctness gate, not a general throughput population.", "Per-quant warm opportunity is a catalog-weighted model from bounded exact medians; P2 retained only top-level per-stack cache deltas.", "Historical ratios are cross-commit observations, not same-binary populations.", "Kernel candidate selection is not kernel implementation or a direct-Metal performance claim.", "No golden-eight rerun was performed."]}


def render(record):
    timing = record["timing"]; rows = []
    for index, stack in enumerate(timing["stacks"]):
        expert = stack["expert_cache_components"]
        rows.append(f"| {index} | {stack['phase']} | {stack['token']} | {stack['stack_seconds']:.6f} | {stack['logits_seconds_separate']:.6f} | {expert['storage_read_seconds']:.6f} | {expert['dequant_seconds']:.6f} | {expert['mlx_matrix_build_seconds']:.6f} | {expert['mlx_matvec_seconds']:.6f} | {stack['uninstrumented_residual_seconds']:.6f} |")
    quant_rows = [f"| {row['rank_by_modeled_warm_decode']} | {row['tensor_role']} | {row['quantization']} | {row['matrix_touches_per_warm_stack']} | {row['dequant_seconds']:.6f} | {row['mlx_matrix_build_seconds']:.6f} | {row['mlx_matvec_seconds']:.6f} |" for row in record["modeled_warm_quantization_opportunity"]["ranking"]]
    warm = timing["warm_population"]; history = record["historical_cross_commit_observation"]
    return "\n".join(["# Post-MoE exact P2 profile", "", f"Exact `[9703,21615,220]` at clean source `{record['source']['source_commit']}`; no golden-eight rerun.", "", "| Stack | Phase | Token | Stack (s) | Separate logits (s) | Expert storage (s) | Expert decode (s) | Expert build (s) | Expert matvec (s) | Uninstrumented residual (s) |", "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |", *rows, "", f"Warm stack mean/median: **{warm['stack_seconds']['mean_seconds']:.6f} / {warm['stack_seconds']['median_seconds']:.6f} s** (two samples). Total evidence wall: **{timing['total_evidence_wall_seconds']:.6f} s**.", "", "## Measured warm format opportunity", "", "| Rank | Role | Quant | Matrix touches | Modeled decode (s) | Modeled build (s) | Modeled matvec (s) |", "| ---: | --- | --- | ---: | ---: | ---: | ---: |", *quant_rows, "", f"The modeled decode sum is {record['modeled_warm_quantization_opportunity']['modeled_decode_seconds']:.6f} s versus {record['modeled_warm_quantization_opportunity']['observed_warm_decode_mean_seconds']:.6f} s observed warm decode ({record['modeled_warm_quantization_opportunity']['relative_error_fraction']:.2%} relative difference). The model uses exact bounded per-format medians and catalog touches; it is not direct per-quant P2 telemetry.", "", "Feature 018 can now use IQ2_XXS routed gate/up as its first candidate by largest measured absolute warm opportunity. This selects a candidate only; no Metal kernel was implemented. Feature 017 should prioritize exact whole-slab IQ2_XXS/IQ3_XXS decode, low-copy MLX handoff, and bounded route-aware residency.", "", f"Historical P2 wall ratio: {history['cross_commit_wall_ratio']:.2f}x; historical warm-median ratio: {history['cross_commit_warm_median_ratio']:.2f}x. Both are cross-commit observations.", ""])


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args(); source_raw, source = _load(SOURCE); multi_raw, multi = _load(MULTI); old_raw, old = _load(OLD_P2); record = build(source_raw, source, multi_raw, multi, old_raw, old); json_text = json.dumps(record, indent=2, sort_keys=True) + "\n"; table_text = render(record)
    if args.check:
        if JSON_OUT.read_text() != json_text or TABLE_OUT.read_text() != table_text: raise SystemExit("post-MoE P2 generated outputs are stale")
    else: JSON_OUT.write_text(json_text); TABLE_OUT.write_text(table_text)


if __name__ == "__main__": main()
