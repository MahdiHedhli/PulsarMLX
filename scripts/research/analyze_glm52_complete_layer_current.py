#!/usr/bin/env python3
"""Generate the exact post-MoE complete layer-8 comparison."""

from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]; SOURCE=ROOT/"docs/research/glm52/raw/post-f016-complete-layer8-all-vector-0001.json"; PRIOR=ROOT/"docs/research/glm52/raw/post-f016-trunk-complete-layer8-q6-audit-0001.json"; JSON_OUT=ROOT/"docs/research/glm52/raw/post-f016-complete-layer8-all-vector-analysis-0001.json"; TABLE_OUT=ROOT/"docs/research/glm52/tables/post-f016-complete-layer8-all-vector-0001.md"


def _unique(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError(f"duplicate key: {key}")
        result[key]=value
    return result


def build(source_bytes,source,prior_bytes,prior):
    if source["actual_status"]!="passed" or source["source_dirty"] or len(source["measured"])!=10: raise ValueError("current record is not a clean ten-sample pass")
    if prior["actual_status"]!="passed": raise ValueError("prior audit is not passed")
    expected_output=prior["comparison"]["output_hashes"]["whole_matrix_numpy_q5_q8_q6_head_numpy"][0]; expected_mid=prior["comparison"]["mid_hashes"]["whole_matrix_numpy_q5_q8_q6_head_numpy"][0]; expected_route=prior["comparison"]["route_expert_ids"]["whole_matrix_numpy_q5_q8_q6_head_numpy"][0]
    if source["reference"]["output_f32_sha256"]!=expected_output or source["reference"]["midpoint_f32_sha256"]!=expected_mid or source["reference"]["route"]["expert_ids"]!=expected_route: raise ValueError("current reference differs from prior exact complete-layer boundary")
    if not source["process_first_comparison"]["exact_f32_bits"] or any(sample["output_f32_sha256"]!=expected_output or sample["midpoint_f32_sha256"]!=expected_mid or sample["route"]["expert_ids"]!=expected_route for sample in source["measured"]): raise ValueError("retained current output differs")
    summary=source["summaries"]; current={key:value["median_seconds"] for key,value in summary.items()}; prior_metrics=prior["metrics"]
    return {"schema":"pulsarmlx.research.glm52-complete-layer-current-analysis","schema_version":"1.0.0","actual_status":"passed","source":{"record":str(SOURCE.relative_to(ROOT)),"sha256":hashlib.sha256(source_bytes).hexdigest(),"source_commit":source["source_commit"]},"prior":{"record":str(PRIOR.relative_to(ROOT)),"sha256":hashlib.sha256(prior_bytes).hexdigest(),"source_commit":prior["measurement_source_commit"],"complete_layer_median_seconds":prior_metrics["candidate_total_median_seconds"],"attention_median_seconds":prior_metrics["candidate_attention_median_seconds"],"moe_median_seconds":prior_metrics["candidate_moe_median_seconds"]},"current":{"medians":current,"retained_samples":len(source["measured"]),"output_f32_sha256":expected_output,"midpoint_f32_sha256":expected_mid,"route_expert_ids":expected_route,"cpu_fallbacks":source["cache_end"]["cpu_fallbacks"],"evictions":source["cache_end"]["evictions"],"resource_levels":sorted({sample[side]["level"] for sample in source["measured"] for side in ("resource_before","resource_after")})},"cross_commit_complete_layer_ratio":prior_metrics["candidate_total_median_seconds"]/current["total_seconds"],"cross_commit_moe_ratio":prior_metrics["candidate_moe_median_seconds"]/current["moe_seconds"],"exact_boundary_identity_preserved":True,"next_gate":"route-history residency economics and matrix reuse study; P2 only if they do not require unsafe memory","feature_018_kernel_selected":False,"claim_boundary":"One complete single-position layer-8 boundary. The before/after ratios are cross-commit observations, not a counterbalanced same-binary population."}


def render(record):
    prior=record["prior"]; current=record["current"]["medians"]
    rows=[("Complete layer",prior["complete_layer_median_seconds"],current["total_seconds"]),("Attention/MLA",prior["attention_median_seconds"],current["attention_seconds"]),("MoE",prior["moe_median_seconds"],current["moe_seconds"]),("Dense attributed",None,current["dense_total_seconds"]),("MoE decode",None,current["moe.routed_matrix_stages.dequant_seconds"]),("MoE build/eval",None,current["moe.routed_matrix_stages.mlx_matrix_construct_seconds"]+current["moe.routed_matrix_stages.mlx_matrix_eval_seconds"]),("MoE matvec",None,current["moe.routed_matrix_stages.mlx_matvec_seconds"]),("MoE cleanup",None,current["moe.routed_matrix_stages.cleanup_seconds"])]
    lines=[f"| {label} | {'n/a' if old is None else f'{old:.6f}'} | {new:.6f} |" for label,old,new in rows]
    return "\n".join(["# Current complete layer-8 result","","> Exact single-position layer boundary; not P1/P2 or token latency.","",f"- Current source: `{record['source']['source_commit']}`",f"- Exact midpoint/output/route preserved across commits: `{str(record['exact_boundary_identity_preserved']).lower()}`",f"- Cross-commit complete-layer ratio: **{record['cross_commit_complete_layer_ratio']:.2f}x**",f"- Cross-commit MoE ratio: **{record['cross_commit_moe_ratio']:.2f}x**","","| Boundary | Prior median (s) | Current median (s) |","| --- | ---: | ---: |",*lines,"","The current complete layer median is 3.511617 s, with 1.787092 s attention and 1.728566 s MoE. Ratios are cross-commit observations, not a counterbalanced same-binary population.",""])


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--check",action="store_true"); args=parser.parse_args(); source_bytes=SOURCE.read_bytes(); prior_bytes=PRIOR.read_bytes(); record=build(source_bytes,json.loads(source_bytes,object_pairs_hook=_unique),prior_bytes,json.loads(prior_bytes,object_pairs_hook=_unique)); json_text=json.dumps(record,indent=2,sort_keys=True)+"\n"; table_text=render(record)
    if args.check:
        if not JSON_OUT.exists() or JSON_OUT.read_text()!=json_text: raise SystemExit("generated complete-layer analysis is stale")
        if not TABLE_OUT.exists() or TABLE_OUT.read_text()!=table_text: raise SystemExit("generated complete-layer table is stale")
    else: JSON_OUT.write_text(json_text); TABLE_OUT.write_text(table_text)
    return 0
if __name__=="__main__": raise SystemExit(main())
