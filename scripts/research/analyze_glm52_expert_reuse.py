#!/usr/bin/env python3
"""Generate the bounded routed-expert lifecycle comparison."""

from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs/research/glm52/raw/post-f016-routed-expert-reuse-0001.json"
JSON_OUT = ROOT / "docs/research/glm52/raw/post-f016-routed-expert-reuse-analysis-0001.json"
TABLE_OUT = ROOT / "docs/research/glm52/tables/post-f016-routed-expert-reuse-0001.md"


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def build(raw, source):
    if source["actual_status"] != "passed" or source["source_dirty"]:
        raise ValueError("reuse record is not a clean pass")
    if not source["comparison"]["exact_output_hash_across_all_candidates"]:
        raise ValueError("candidate outputs differ")
    candidates = {row["candidate"]: row for row in source["candidates"]}
    if set(candidates) != {"transient", "decoded_host_rebuild", "mlx_ready_reuse"}:
        raise ValueError("unexpected candidate set")
    values = {}
    for name, row in candidates.items():
        if len(row["samples"]) != 10 or row["pressure_after_setup"]["level"] != "normal" or row["pressure_after_teardown"]["level"] != "normal":
            raise ValueError(f"{name} failed its sample/resource contract")
        values[name] = {"setup": row["setup"], "setup_rss_delta_bytes": row["setup_rss_delta_bytes"], "medians": {key: summary["median_seconds"] for key, summary in row["summaries"].items()}}
    transient = values["transient"]["medians"]["total_with_cleanup_seconds"]
    host = values["decoded_host_rebuild"]["medians"]["total_with_cleanup_seconds"]
    ready = values["mlx_ready_reuse"]["medians"]["total_with_cleanup_seconds"]
    return {"schema": "pulsarmlx.research.glm52-routed-expert-reuse-analysis", "schema_version": "1.0.0", "actual_status": "passed", "source": {"record": str(SOURCE.relative_to(ROOT)), "sha256": hashlib.sha256(raw).hexdigest(), "source_commit": source["source_commit"]}, "boundary": {"layer": 64, "expert_id": 183, "route_history": "selected in all nine frozen golden-eight stacks", "logical_decoded_f32_bytes": 150994944}, "candidates": values, "exact_output_f32_sha256": source["comparison"]["output_f32_sha256"], "reuse_ratios": {"transient_to_decoded_host_rebuild": transient / host, "transient_to_mlx_ready_reuse": transient / ready, "decoded_host_rebuild_to_mlx_ready_reuse": host / ready}, "decision": {"decode_remains_largest_transient_stage": values["transient"]["medians"]["dequant_seconds"] > values["transient"]["medians"]["mlx_matrix_build_seconds"], "mlx_build_import_dominant": False, "retained_mlx_matrix_has_material_reuse_benefit": transient / ready > 50, "safe_static_per_layer_cache_proven": False, "next_gate": "P2 admission after clean-source evidence commit", "feature_018_kernel_selected": False}, "claim_boundary": "One recurrent routed expert on one M1 Ultra; setup and reuse are process-isolated and do not establish a full MoE/layer/token speedup."}


def render(record):
    rows = []
    for name, row in record["candidates"].items():
        med = row["medians"]
        rows.append(f"| {name} | {row['setup']['dequant_seconds']:.6f} | {row['setup']['mlx_matrix_build_seconds']:.6f} | {row['setup_rss_delta_bytes']/1024**2:.1f} | {med['dequant_seconds']:.6f} | {med['mlx_matrix_build_seconds']:.6f} | {med['mlx_matvec_seconds']:.6f} | {med['cleanup_seconds']:.6f} | {med['total_with_cleanup_seconds']:.6f} |")
    ratios = record["reuse_ratios"]
    return "\n".join(["# Bounded routed-expert lifecycle reuse", "", "> One recurrent real expert (layer 64, expert 183); not a full MoE, layer, stack, or token benchmark.", "", "All candidates retained the exact same f32 output hash across ten measured uses, with normal resource pressure.", "", "| Candidate | Setup decode (s) | Setup MLX build (s) | Setup RSS delta (MiB) | Reuse decode (s) | Reuse MLX build (s) | Reuse matvec (s) | Cleanup (s) | Reuse total (s) |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |", *rows, "", f"Transient-to-host-rebuild reuse ratio: **{ratios['transient_to_decoded_host_rebuild']:.2f}x**. Transient-to-retained-MLX reuse ratio: **{ratios['transient_to_mlx_ready_reuse']:.2f}x**.", "", "Decode remains the largest transient stage. MLX build/import is measurable but not dominant; a safely retained evaluated matrix removes both decode and rebuild. The observed ~251 MiB MLX-ready setup RSS delta for one 144 MiB logical expert makes a 76-expert policy ineligible without a separate allocator-aware admission gate.", ""])


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args(); raw = SOURCE.read_bytes(); source = json.loads(raw, object_pairs_hook=_unique); record = build(raw, source); json_text = json.dumps(record, indent=2, sort_keys=True) + "\n"; table_text = render(record)
    if args.check:
        if JSON_OUT.read_text() != json_text or TABLE_OUT.read_text() != table_text:
            raise SystemExit("expert reuse generated outputs are stale")
    else:
        JSON_OUT.write_text(json_text); TABLE_OUT.write_text(table_text)


if __name__ == "__main__":
    main()
