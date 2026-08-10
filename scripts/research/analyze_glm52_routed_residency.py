#!/usr/bin/env python3
"""Derive routed-expert residency economics from committed route histories."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from glm52_cache_simulator import build_accesses, load_catalog

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "docs/research/glm52/raw/f016-c01-catalog-0001.json"
P1 = ROOT / "docs/research/glm52/raw/post-f016-inference-p1-trunk-q6-0001.json"
P2 = ROOT / "docs/research/glm52/raw/f016-inference-p2-iq3-0001.json"
GOLDEN = ROOT / "docs/research/glm52/raw/f016-inference-golden8-iq3-0001.json"
JSON_OUT = ROOT / "docs/research/glm52/raw/post-f016-routed-residency-economics-0001.json"
TABLE_OUT = ROOT / "docs/research/glm52/tables/post-f016-routed-residency-economics-0001.md"
GIB = 1024**3


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def _load(path: Path):
    raw = path.read_bytes()
    return raw, json.loads(raw, object_pairs_hook=_unique)


def _route_stacks(document):
    stacks = []
    for stack in document["routing"]:
        layers = stack["layers"]
        if [row["layer"] for row in layers] != list(range(3, 79)):
            raise ValueError("route stack must contain layers 3..78")
        if any(len(row["expert_ids"]) != 8 or len(set(row["expert_ids"])) != 8 for row in layers):
            raise ValueError("every MoE layer must contain eight distinct experts")
        stacks.append({row["layer"]: tuple(row["expert_ids"]) for row in layers})
    return stacks


def _unit_metadata(catalog, stacks):
    units = {}
    for stack in stacks:
        route_layers = [{"layer": layer, "expert_ids": list(experts)} for layer, experts in stack.items()]
        for access in build_accesses(catalog, route_layers):
            if access.shared:
                continue
            key = (access.layer, access.expert)
            unit = units.setdefault(key, {"layer": access.layer, "expert_id": access.expert, "compressed_bytes": 0, "decoded_f32_bytes": 0, "projections": {}})
            if access.kind not in unit["projections"]:
                unit["compressed_bytes"] += access.compressed_bytes
                unit["decoded_f32_bytes"] += access.decoded_bytes
                unit["projections"][access.kind] = {"quantization": access.quantization, "compressed_bytes": access.compressed_bytes, "decoded_f32_bytes": access.decoded_bytes}
    return units


def _policy(name, selected, counts, units, *, decoded, notes):
    selected = list(dict.fromkeys(selected))
    first_use = sum(1 for key in selected if counts[key])
    later_hits = sum(max(0, counts[key] - 1) for key in selected)
    return {
        "policy": name,
        "resident_experts": len(selected),
        "logical_compressed_bytes": sum(units[key]["compressed_bytes"] for key in selected),
        "logical_decoded_f32_bytes": sum(units[key]["decoded_f32_bytes"] for key in selected) if decoded else 0,
        "expert_accesses": sum(counts[key] for key in selected),
        "first_use_setups": first_use,
        "later_expert_hits": later_hits,
        "later_matrix_hits": later_hits * 3 if decoded else 0,
        "later_storage_hits": later_hits * 3,
        "decode_avoided_on_hit": decoded,
        "observed_rss_delta_bytes": None,
        "observed_memory_pressure": "not_executed_catalog_analysis",
        "notes": notes,
    }


def build():
    catalog_bytes, catalog_doc = _load(CATALOG)
    p1_bytes, p1 = _load(P1)
    p2_bytes, p2 = _load(P2)
    golden_bytes, golden = _load(GOLDEN)
    p1_stacks, p2_stacks, stacks = map(_route_stacks, (p1, p2, golden))
    if p1_stacks != stacks[:2] or p2_stacks != stacks[:3]:
        raise ValueError("P1/P2 routes do not match golden-eight prefixes")
    catalog = load_catalog(CATALOG)
    units = _unit_metadata(catalog, stacks)
    counts = Counter((layer, expert) for stack in stacks for layer, experts in stack.items() for expert in experts)
    adjacent_counts = Counter()
    intervals = []
    for index in range(1, len(stacks)):
        keys = []
        for layer in range(3, 79):
            keys.extend((layer, expert) for expert in set(stacks[index - 1][layer]) & set(stacks[index][layer]))
        adjacent_counts.update(keys)
        intervals.append({
            "from_stack": index - 1,
            "to_stack": index,
            "repeated_experts": len(keys),
            "selected_experts": 76 * 8,
            "repeat_fraction": len(keys) / (76 * 8),
            "logical_compressed_bytes_reusable": sum(units[key]["compressed_bytes"] for key in keys),
            "logical_decoded_f32_bytes_reusable": sum(units[key]["decoded_f32_bytes"] for key in keys),
        })
    ranked = sorted(counts, key=lambda key: (-counts[key], -adjacent_counts[key], key))
    per_layer_top1 = [max(((layer, expert) for expert in range(256)), key=lambda key: (counts[key], adjacent_counts[key], -key[1])) for layer in range(3, 79)]
    global_top8 = ranked[:8]
    policies = [
        {"policy": "transient_current_path", "resident_experts": 0, "logical_compressed_bytes": 0, "logical_decoded_f32_bytes": 0, "expert_accesses": 9 * 76 * 8, "first_use_setups": 9 * 76 * 8, "later_expert_hits": 0, "later_matrix_hits": 0, "later_storage_hits": 0, "decode_avoided_on_hit": False, "observed_rss_delta_bytes": None, "observed_memory_pressure": "existing_runs_only_not_isolated", "notes": "Measured current lifecycle releases all routed matrices."},
        _policy("decoded_single_expert_hot_pin", ranked[:1], counts, units, decoded=True, notes="One globally hottest (layer, expert) unit; bounded but benefits only one layer."),
        _policy("decoded_per_layer_top1", per_layer_top1, counts, units, decoded=True, notes="One static hottest routed expert in each MoE layer; logical bytes exclude allocator overhead."),
        _policy("compressed_per_layer_top1", per_layer_top1, counts, units, decoded=False, notes="Avoids reads on reuse but not decode/build; golden warm storage was already secondary."),
        _policy("compressed_top1_plus_decoded_global_top8", per_layer_top1, counts, units, decoded=False, notes="Compressed top-one-per-layer tier plus a separately counted eight-expert decoded tier."),
    ]
    hybrid = policies[-1]
    hybrid_decoded = _policy("decoded_global_top8_component", global_top8, counts, units, decoded=True, notes="Decoded component of hybrid policy")
    hybrid["decoded_tier"] = hybrid_decoded
    hybrid["logical_decoded_f32_bytes"] = hybrid_decoded["logical_decoded_f32_bytes"]
    hybrid["later_matrix_hits"] = hybrid_decoded["later_matrix_hits"]
    hybrid["decode_avoided_on_hit"] = True
    peak_rss = max(value for value in _walk_values(p1, "rss_bytes"))
    top = []
    for rank, key in enumerate(ranked[:20], 1):
        unit = units[key]
        top.append({"rank": rank, "layer": key[0], "expert_id": key[1], "appearances": counts[key], "adjacent_reuses": adjacent_counts[key], "compressed_bytes": unit["compressed_bytes"], "decoded_f32_bytes": unit["decoded_f32_bytes"], "quantizations": {name: item["quantization"] for name, item in unit["projections"].items()}})
    return {
        "schema": "pulsarmlx.research.glm52-routed-residency-economics",
        "schema_version": "1.0.0",
        "actual_status": "passed",
        "inputs": {
            "catalog": {"path": str(CATALOG.relative_to(ROOT)), "sha256": hashlib.sha256(catalog_bytes).hexdigest()},
            "p1": {"path": str(P1.relative_to(ROOT)), "sha256": hashlib.sha256(p1_bytes).hexdigest(), "source_commit": p1["source_commit"], "stacks": len(p1_stacks)},
            "p2": {"path": str(P2.relative_to(ROOT)), "sha256": hashlib.sha256(p2_bytes).hexdigest(), "source_commit": p2["source_commit"], "stacks": len(p2_stacks)},
            "golden8": {"path": str(GOLDEN.relative_to(ROOT)), "sha256": hashlib.sha256(golden_bytes).hexdigest(), "source_commit": golden["source_commit"], "stacks": len(stacks)},
        },
        "prefix_routes_identical": True,
        "golden_route_population": {"stacks": 9, "moe_layers_per_stack": 76, "experts_per_layer": 8, "expert_selections": 9 * 76 * 8, "unique_layer_expert_units": len(counts)},
        "adjacent_stack_reuse": intervals,
        "adjacent_repeated_experts_total": sum(row["repeated_experts"] for row in intervals),
        "adjacent_repeat_fraction_overall": sum(row["repeated_experts"] for row in intervals) / (8 * 76 * 8),
        "top_20_routed_units_by_history_frequency": top,
        "policies": policies,
        "memory_context": {"unified_memory_bytes": 128 * GIB, "protected_shared_cache_budget_bytes": 16 * GIB, "observed_post_trunk_p1_peak_rss_bytes": peak_rss, "conservative_reserve_bytes": 24 * GIB, "logical_budget_only": True},
        "decision": {"decoded_all_observed_routed_units_safe": False, "static_decoded_top1_per_layer_requires_real_rss_gate": True, "compressed_residency_avoids_decode": False, "next_experiment": "one real expert lifecycle: transient, decoded-host rebuild, and retained MLX-ready matrices", "feature_018_kernel_selected": False},
        "limitations": ["Nine stacks from one frozen short-context continuation do not establish general prompt reuse.", "Logical f32 bytes exclude NumPy/MLX allocator overhead and fragmentation.", "Reuse counts measure opportunity; they are not latency savings.", "The route histories predate the current decoder commit, but their P1/P2 prefixes are exactly identical across the committed runs."],
    }


def _walk_values(value, key):
    if isinstance(value, dict):
        for name, item in value.items():
            if name == key and isinstance(item, (int, float)):
                yield item
            yield from _walk_values(item, key)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_values(item, key)


def render(record):
    interval_rows = [f"| {row['from_stack']}→{row['to_stack']} | {row['repeated_experts']} | {100*row['repeat_fraction']:.2f}% | {row['logical_decoded_f32_bytes_reusable']/GIB:.3f} |" for row in record["adjacent_stack_reuse"]]
    policy_rows = [f"| {row['policy']} | {row['resident_experts']} | {row['logical_compressed_bytes']/GIB:.3f} | {row['logical_decoded_f32_bytes']/GIB:.3f} | {row['later_expert_hits']} | {row['later_matrix_hits']} |" for row in record["policies"]]
    top_rows = [f"| {row['rank']} | {row['layer']} | {row['expert_id']} | {row['appearances']} | {row['adjacent_reuses']} | {row['decoded_f32_bytes']/GIB:.3f} | {','.join(row['quantizations'].values())} |" for row in record["top_20_routed_units_by_history_frequency"]]
    return "\n".join(["# Routed-expert residency economics", "", "> Golden-eight route-history analysis only; reuse counts are not measured latency savings.", "", f"Across eight adjacent intervals, **{record['adjacent_repeated_experts_total']}** of {8*76*8} routed selections repeat at the same layer (**{100*record['adjacent_repeat_fraction_overall']:.2f}%**). Reuse rises from 9.38% in the first interval to 53.12% in the last.", "", "## Adjacent stack reuse", "", "| Interval | Repeated experts | Fraction | Reusable decoded GiB |", "| --- | ---: | ---: | ---: |", *interval_rows, "", "## Bounded policies", "", "| Policy | Resident experts | Compressed GiB | Decoded GiB | Later expert hits | Later matrix hits |", "| --- | ---: | ---: | ---: | ---: | ---: |", *policy_rows, "", "## Top 20 routed units", "", "| Rank | Layer | Expert | Appearances | Adjacent reuses | Decoded GiB | Gate/up/down quantization |", "| ---: | ---: | ---: | ---: | ---: | ---: | --- |", *top_rows, "", "Decoded top-one-per-layer residency is only a logical candidate and requires a real RSS/ownership gate. Compressed residency avoids reads but not decode or MLX build. The next bounded experiment measures one real expert lifecycle; Feature 018 remains unselected.", ""])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    record = build()
    json_text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    table_text = render(record)
    if args.check:
        if JSON_OUT.read_text() != json_text or TABLE_OUT.read_text() != table_text:
            raise SystemExit("routed residency outputs are stale")
    else:
        JSON_OUT.write_text(json_text)
        TABLE_OUT.write_text(table_text)


if __name__ == "__main__":
    main()
