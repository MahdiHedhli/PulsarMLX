#!/usr/bin/env python3
"""Derive combined layer-8 IQ2_S/IQ4_XS integration evidence."""

from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from analyze_glm52_moe_iq2_s_integration import _layer8
from analyze_glm52_moe_q2_integration import _medians, _quant_medians, _unique

ROOT=Path(__file__).resolve().parents[2]; BASELINE=ROOT/"docs/research/glm52/raw/post-f016-moe-stage-profile-0001.json"; IQ2_ONLY=ROOT/"docs/research/glm52/raw/post-f016-moe-layer8-iq2-s-0001.json"; CANDIDATE=ROOT/"docs/research/glm52/raw/post-f016-moe-layer8-iq2-s-iq4-xs-0001.json"; JSON_OUT=ROOT/"docs/research/glm52/raw/post-f016-moe-layer8-iq2-s-iq4-xs-analysis-0001.json"; TABLE_OUT=ROOT/"docs/research/glm52/tables/post-f016-moe-layer8-iq2-s-iq4-xs-0001.md"


def _source(path):
    payload=path.read_bytes(); return payload,json.loads(payload,object_pairs_hook=_unique)


def build():
    baseline_bytes,baseline=_source(BASELINE); iq2_bytes,iq2=_source(IQ2_ONLY); candidate_bytes,candidate=_source(CANDIDATE)
    for label,record in (("baseline",baseline),("iq2",iq2),("candidate",candidate)):
        if record["actual_status"]!="passed" or record["source_dirty"]: raise ValueError(f"{label} is not a clean passing record")
    if candidate["protocol"]["layers"]!=[8] or candidate["protocol"]["untimed_reference_decoder_mode"]!="scalar_reference": raise ValueError("candidate protocol changed")
    layer=_layer8(candidate)
    if not layer["process_first_comparison"]["exact_f32_bits"] or any(sample["output_f32_sha256"]!=layer["reference_output_f32_sha256"] for sample in layer["measured"]): raise ValueError("candidate differs from scalar reference")
    stages={"baseline":_medians(_layer8(baseline)),"iq2_s_only":_medians(_layer8(iq2)),"iq2_s_iq4_xs":_medians(layer)}
    return {"schema":"pulsarmlx.research.glm52-moe-iq2-s-iq4-xs-integration-analysis","schema_version":"1.0.0","actual_status":"passed","sources":{"baseline":{"record":str(BASELINE.relative_to(ROOT)),"sha256":hashlib.sha256(baseline_bytes).hexdigest(),"source_commit":baseline["source_commit"]},"iq2_s_only":{"record":str(IQ2_ONLY.relative_to(ROOT)),"sha256":hashlib.sha256(iq2_bytes).hexdigest(),"source_commit":iq2["source_commit"]},"iq2_s_iq4_xs":{"record":str(CANDIDATE.relative_to(ROOT)),"sha256":hashlib.sha256(candidate_bytes).hexdigest(),"source_commit":candidate["source_commit"]}},"stage_medians":stages,"candidate_quantization_ranking":_quant_medians(layer),"baseline_to_candidate_speedup":stages["baseline"]["total_seconds"]/stages["iq2_s_iq4_xs"]["total_seconds"],"iq2_s_to_candidate_speedup":stages["iq2_s_only"]["total_seconds"]/stages["iq2_s_iq4_xs"]["total_seconds"],"exact_f32_bits_against_scalar_reference":True,"retained_samples":len(layer["measured"]),"cpu_fallbacks":layer["cache_end"]["cpu_fallbacks"],"evictions":layer["cache_end"]["evictions"],"resource_levels":sorted({sample[side]["level"] for sample in layer["measured"] for side in ("resource_before","resource_after")}),"next_measured_gate":"representative layers 8, 40, 75, 76, 77, and 78 reprofile with all qualified expert decoders","feature_018_kernel_selected":False,"claim_boundary":"One bounded layer-8 MoE boundary; not sequential full-stack activation, P1/P2, token latency, Rust, or Metal."}


def render(record):
    stages=record["stage_medians"]; fields=(("MoE boundary","total_seconds"),("Storage","storage_read_seconds"),("Decode","dequant_seconds"),("Buffer","contiguous_buffer_seconds"),("MLX construct","mlx_matrix_construct_seconds"),("MLX eval","mlx_matrix_eval_seconds"),("MLX matvec","mlx_matvec_seconds"),("Cleanup","cleanup_seconds"),("SwiGLU","activation_swiglu_seconds"),("Residual","uninstrumented_residual_seconds")); stage_lines=[f"| {label} | {stages['baseline'][key]:.6f} | {stages['iq2_s_only'][key]:.6f} | {stages['iq2_s_iq4_xs'][key]:.6f} |" for label,key in fields]; quant_lines=[f"| {row['quantization']} | {row['median_attributed_seconds']:.6f} | {row['median_components']['dequant_seconds']:.6f} | {row['median_components']['mlx_matrix_construct_seconds']+row['median_components']['mlx_matrix_eval_seconds']:.6f} | {row['median_components']['mlx_matvec_seconds']:.6f} |" for row in record["candidate_quantization_ranking"]]
    return "\n".join(["# Layer-8 combined IQ2_S/IQ4_XS MoE integration","","> One bounded layer-local MoE boundary; not P1/P2 or token latency.","",f"- Exact f32 bits against scalar-reference MoE: `{str(record['exact_f32_bits_against_scalar_reference']).lower()}`",f"- Baseline-to-candidate median ratio: **{record['baseline_to_candidate_speedup']:.2f}x**",f"- IQ2_S-only-to-candidate median ratio: **{record['iq2_s_to_candidate_speedup']:.2f}x**","","| Stage | Baseline (s) | IQ2_S only (s) | IQ2_S + IQ4_XS (s) |","| --- | ---: | ---: | ---: |",*stage_lines,"","## Candidate expert quantization medians","","| Quant | Attributed (s) | Decode (s) | Build/eval (s) | Matvec (s) |","| --- | ---: | ---: | ---: | ---: |",*quant_lines,"","The exceptional layer-8 scalar decoder hotspot has collapsed. The next gate is a bounded multi-layer reprofile before residency or P2; no Metal kernel is selected.",""])


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--check",action="store_true"); args=parser.parse_args(); record=build(); json_text=json.dumps(record,indent=2,sort_keys=True)+"\n"; table_text=render(record)
    if args.check:
        if not JSON_OUT.exists() or JSON_OUT.read_text()!=json_text: raise SystemExit("generated combined IQ2_S/IQ4_XS analysis is stale")
        if not TABLE_OUT.exists() or TABLE_OUT.read_text()!=table_text: raise SystemExit("generated combined IQ2_S/IQ4_XS table is stale")
    else: JSON_OUT.write_text(json_text); TABLE_OUT.write_text(table_text)
    return 0


if __name__=="__main__": raise SystemExit(main())
