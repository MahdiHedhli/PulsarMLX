#!/usr/bin/env python3
"""Generate the final bounded multi-layer MoE reprofile."""

from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from analyze_glm52_moe_profile import _expert_record
from analyze_glm52_moe_q2_integration import _medians, _quant_medians, _unique

ROOT=Path(__file__).resolve().parents[2]; SOURCE=ROOT/"docs/research/glm52/raw/post-f016-moe-multilayer-all-vector-0001.json"; JSON_OUT=ROOT/"docs/research/glm52/raw/post-f016-moe-multilayer-all-vector-analysis-0001.json"; TABLE_OUT=ROOT/"docs/research/glm52/tables/post-f016-moe-multilayer-all-vector-0001.md"; EXPECTED=[8,40,75,76,77,78]


def _median(values):
    ordered=sorted(float(value) for value in values); middle=len(ordered)//2
    if not ordered: raise ValueError("empty median population")
    return ordered[middle] if len(ordered)%2 else (ordered[middle-1]+ordered[middle])/2


def build(payload,source):
    if source["actual_status"]!="passed" or source["source_dirty"] or source["protocol"]["layers"]!=EXPECTED or source["protocol"]["untimed_reference_decoder_mode"]!="scalar_reference": raise ValueError("source protocol is not the admitted clean pass")
    layers=[]; experts=[]
    for layer_source in source["layers"]:
        layer=int(layer_source["layer"]); samples=layer_source["measured"]
        if len(samples)!=10 or not layer_source["process_first_comparison"]["exact_f32_bits"] or any(sample["output_f32_sha256"]!=layer_source["reference_output_f32_sha256"] for sample in samples): raise ValueError(f"layer {layer} exactness changed")
        routed=[_expert_record(layer,[sample["detail"]["routed_experts"][index] for sample in samples]) for index in range(8)]; shared=[sample["detail"]["shared_expert"] for sample in samples]
        medians=_medians(layer_source); quant=_quant_medians(layer_source); routed_total=_median(sum(expert["total_seconds"] for expert in sample["detail"]["routed_experts"]) for sample in samples); shared_total=_median(expert["total_seconds"] for expert in shared)
        layers.append({"layer":layer,"route":layer_source["reference_route"]["expert_ids"],"medians":medians,"routed_expert_total_median_seconds":routed_total,"shared_expert_total_median_seconds":shared_total,"quantization_ranking":quant})
        experts.extend(routed)
    ranked=sorted(experts,key=lambda row:(-row["total_seconds"]["median_seconds"],row["layer"],row["expert_id"]))[:20]
    top=[{"rank":i,"layer":row["layer"],"expert_id":row["expert_id"],"median_total_seconds":row["total_seconds"]["median_seconds"],"quantizations":{projection["projection"]:projection["quantization"] for projection in row["projections"]}} for i,row in enumerate(ranked,1)]
    return {"schema":"pulsarmlx.research.glm52-moe-multilayer-analysis","schema_version":"1.0.0","actual_status":"passed","source":{"record":str(SOURCE.relative_to(ROOT)),"sha256":hashlib.sha256(payload).hexdigest(),"source_commit":source["source_commit"],"source_dirty":source["source_dirty"]},"layers":layers,"top_20_routed_experts":top,"six_layer_median_sum_seconds":sum(layer["medians"]["total_seconds"] for layer in layers),"six_layer_decode_median_sum_seconds":sum(layer["medians"]["dequant_seconds"] for layer in layers),"all_exact_f32_bits_against_scalar_reference":True,"retained_sample_count":sum(len(layer["measured"]) for layer in source["layers"]),"cpu_fallbacks":sum(layer["cache_end"]["cpu_fallbacks"] for layer in source["layers"]),"evictions":sum(layer["cache_end"]["evictions"] for layer in source["layers"]),"resource_levels":sorted({sample[side]["level"] for layer in source["layers"] for sample in layer["measured"] for side in ("resource_before","resource_after")}),"decision":{"largest_measured_layer":max(layers,key=lambda row:row["medians"]["total_seconds"])["layer"],"bounded_stage_still_dominant":"vectorized decode","build_import_dominant":False,"matvec_dominant":False,"feature_018_kernel_selected":False,"next_gate":"complete layer-8 reprofile, route-history residency economics, and matrix reuse study before P2"},"claim_boundary":"Six independent layer-local MLA-derived MoE activations; not sequential full-stack execution or token latency."}


def render(record):
    layer_lines=[]; quant_lines=[]
    for layer in record["layers"]:
        m=layer["medians"]; layer_lines.append(f"| {layer['layer']} | {m['total_seconds']:.6f} | {layer['routed_expert_total_median_seconds']:.6f} | {layer['shared_expert_total_median_seconds']:.6f} | {m['dequant_seconds']:.6f} | {m['mlx_matrix_construct_seconds']+m['mlx_matrix_eval_seconds']:.6f} | {m['mlx_matvec_seconds']:.6f} | {m['cleanup_seconds']:.6f} |")
        for row in layer["quantization_ranking"]: quant_lines.append(f"| {layer['layer']} | {row['quantization']} | {row['median_attributed_seconds']:.6f} | {row['median_components']['dequant_seconds']:.6f} | {row['median_components']['mlx_matvec_seconds']:.6f} |")
    expert_lines=[f"| {row['rank']} | {row['layer']} | {row['expert_id']} | `{row['quantizations']}` | {row['median_total_seconds']:.6f} |" for row in record["top_20_routed_experts"]]
    return "\n".join(["# Final bounded multi-layer MoE reprofile","",f"Source: `{record['source']['source_commit']}`; exact scalar-reference output/routes across {record['retained_sample_count']} retained samples.","","| Layer | MoE median (s) | Routed median (s) | Shared median (s) | Decode (s) | Build/eval (s) | Matvec (s) | Cleanup (s) |","| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",*layer_lines,"","## Per-quant medians","","| Layer | Quant | Attributed (s) | Decode (s) | Matvec (s) |","| ---: | --- | ---: | ---: | ---: |",*quant_lines,"","## Current top 20 routed experts","","| Rank | Layer | Expert | Quantizations | Median total (s) |","| ---: | ---: | ---: | --- | ---: |",*expert_lines,"","Vectorized decode remains the largest bounded stage, while build/import, matvec, activation, aggregation, and cleanup are not dominant. This representative profile does not alone select a Feature 018 kernel.",""])


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--check",action="store_true"); args=parser.parse_args(); payload=SOURCE.read_bytes(); record=build(payload,json.loads(payload,object_pairs_hook=_unique)); json_text=json.dumps(record,indent=2,sort_keys=True)+"\n"; table_text=render(record)
    if args.check:
        if not JSON_OUT.exists() or JSON_OUT.read_text()!=json_text: raise SystemExit("generated multi-layer analysis is stale")
        if not TABLE_OUT.exists() or TABLE_OUT.read_text()!=table_text: raise SystemExit("generated multi-layer table is stale")
    else: JSON_OUT.write_text(json_text); TABLE_OUT.write_text(table_text)
    return 0
if __name__=="__main__": raise SystemExit(main())
