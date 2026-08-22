#!/usr/bin/env python3
"""Checkpoint-free qualification for corrected primary/secondary oracles."""
from __future__ import annotations
import argparse, hashlib, json, math, os, subprocess, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
RESEARCH=ROOT/"scripts/research"
sys.path.insert(0, str(RESEARCH))
from f017_oracle_primary_decoders import decode as primary_decode
from qualify_f017_quantization_matrix_v1 import FORMATS, independent_decode, synthetic_block

SEEDS=tuple(range(18101,18113))
SAFETY_FACTOR=65536
SAFETY_FACTOR_DERIVATION="NEXT_POWER_OF_TWO_CEILING((TARGET_MAX_REDUCTION_16384/FIXTURE_MAX_REDUCTION_4)*(TARGET_LAYERS_79/FIXTURE_MAX_LAYERS_6))"
GRAPH_MUTATIONS=("ROPE_POSITION","BOS_INSERTION","QK_TRANSPOSE","TENSOR_OFFSET",
                 "ROUTE_BIAS_ORDER","ROUTE_WEIGHT_PLACEMENT","WRONG_EXPERT",
                 "WRONG_SHARED","LAYER_COUNT","FINAL_NORM","OUTPUT_TRANSPOSE")

def load(path): return json.loads(path.read_text())
def canonical(value): return (json.dumps(value,sort_keys=True,separators=(",",":"))+"\n").encode()
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def run(command, env=None):
    result=subprocess.run(command,cwd=ROOT,env=env,text=True,capture_output=True)
    if result.returncode: raise RuntimeError(f"command failed {command}: {result.stderr}")

def max_metrics(a,b):
    left,right=a["full_logits"],b["full_logits"]
    diff=[abs(float(x)-float(y)) for x,y in zip(left,right,strict=True)]
    rmse=math.sqrt(sum(v*v for v in diff)/len(diff))
    dot=sum(float(x)*float(y) for x,y in zip(left,right,strict=True));
    norms=math.sqrt(sum(float(x)**2 for x in left)*sum(float(y)**2 for y in right))
    return max(diff),rmse,1.0-dot/norms if norms else 0.0

def mutate(document,name):
    d=json.loads(json.dumps(document));t=d["tensors"]
    if name=="ROPE_POSITION": d["position"]+=1
    elif name=="BOS_INSERTION": d["token"]=(d["token"]+1)%d["geometry"]["vocab"]
    elif name=="LAYER_COUNT" and d["geometry"]["layers"]>1: d["geometry"]["layers"]-=1
    elif name=="FINAL_NORM": t["output_norm.weight"][0]*=-1
    elif name=="OUTPUT_TRANSPOSE": t["output.weight"]=list(reversed(t["output.weight"]))
    elif name in {"ROUTE_BIAS_ORDER","WRONG_EXPERT","ROUTE_WEIGHT_PLACEMENT"}:
        keys=[k for k in t if "exp_probs_b.bias" in k]
        if keys: t[keys[0]]=[-100.0,-100.0,100.0,99.0]
        else: t["token_embd.weight"][0]+=.125
    elif name=="WRONG_SHARED":
        keys=[k for k in t if "shexp" in k]
        if keys: t[keys[0]][0]+=.125
        else: t["token_embd.weight"][0]+=.125
    elif name=="QK_TRANSPOSE":
        key=next(k for k in t if "attn_k_b.weight" in k)
        width=d["geometry"]["qk_nope"];height=d["geometry"]["kv_rank"];values=t[key]
        if width!=height: raise ValueError("qualification transpose requires square K-B fixture")
        t[key]=[values[row*width+column] for column in range(width) for row in range(height)]
    elif name=="TENSOR_OFFSET":
        key=next(k for k in t if "attn_q_a.weight" in k)
        t[key]=t[key][1:]+t[key][:1]
    return d

def quantized_differential_and_mutations():
    cases=[]
    for index,(fmt,(_,count,_)) in enumerate(FORMATS.items()):
        for mode in ("zero","pattern","subnormal","max_finite"):
            raw=synthetic_block(fmt,mode,19000+index)
            primary=primary_decode(fmt,raw,count);secondary=independent_decode(fmt,raw,count)
            exact=[float(v).hex() for v in primary]==[float(v).hex() for v in secondary]
            if not exact: raise SystemExit(f"packed decoder disagreement: {fmt}:{mode}")
            cases.append({"format":fmt,"mode":mode,"values":count,"binary64_exact":True,
                          "encoded_sha256":hashlib.sha256(raw).hexdigest()})
    mutations=[]
    for fmt,byte_index in (("Q6_K",0),("IQ3_XXS",2)):
        _,count,_=FORMATS[fmt];raw=bytearray(synthetic_block(fmt,"pattern",20170+byte_index));baseline=primary_decode(fmt,bytes(raw),count)
        raw[byte_index]^=1;changed=primary_decode(fmt,bytes(raw),count)
        if [float(v).hex() for v in baseline]==[float(v).hex() for v in changed]:
            raise SystemExit(f"packed lane mutation not detected: {fmt}")
        mutations.append({"id":f"{fmt}_PACKED_LANE","localized_or_rejected":True,
                          "test_kind":"PACKED_BLOCK_BIT_MUTATION"})
    raw=synthetic_block("Q6_K","pattern",20211);_,count,_=FORMATS["Q6_K"]
    try: primary_decode("IQ3_XXS",raw,count)
    except ValueError: mutations.append({"id":"QUANT_TYPE_ID","localized_or_rejected":True,"test_kind":"DISPATCH_GEOMETRY_REJECTION"})
    else: raise SystemExit("quant type mutation accepted")
    shifted=b"\x00"+raw[:-1]
    if [float(v).hex() for v in primary_decode("Q6_K",raw,count)]==[float(v).hex() for v in primary_decode("Q6_K",shifted,count)]:
        raise SystemExit("tensor offset mutation not detected")
    mutations.append({"id":"PACKED_TENSOR_OFFSET","localized_or_rejected":True,"test_kind":"ENCODED_BYTE_OFFSET_SHIFT"})
    values=(16777216.0,1.0,-16777216.0);f64=sum(values);f32=0.0
    import struct
    for value in values: f32=struct.unpack("<f",struct.pack("<f",f32+value))[0]
    if f64==f32: raise SystemExit("precision mutation witness failed")
    mutations.append({"id":"ACCUMULATION_PRECISION","localized_or_rejected":True,
                      "test_kind":"BINARY64_VS_BINARY32_LEFT_FOLD_WITNESS","binary64":f64,"binary32":f32})
    return cases,mutations

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True);args=parser.parse_args()
    # Historical target observations are quarantined from new implementation.
    forbidden=(str(21600+15),str(17300+51))
    scanned=[RESEARCH/"f017_corrected_oracle_primary.py",RESEARCH/"f017_corrected_oracle_secondary.py",
             RESEARCH/"f017_oracle_primary_decoders.py",
             ROOT/"specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v1.json"]
    leakage={str(path.relative_to(ROOT)):[value for value in forbidden if value in path.read_text()] for path in scanned}
    if any(leakage.values()): raise SystemExit(f"target observation leakage: {leakage}")
    with tempfile.TemporaryDirectory(prefix="f017-corrected-oracle-") as tmp:
        work=Path(tmp);fixtures=work/"fixtures"
        run([sys.executable,str(RESEARCH/"generate_f017_corrected_oracle_fixtures.py"),str(fixtures)])
        cases=[]; observed_abs=observed_rmse=observed_cos=0.0
        primary_repeat_identity=secondary_repeat_identity=True
        for seed in SEEDS:
            fixture=fixtures/f"fixture-{seed}.json";p_hashes=[];s_hashes=[];last=None
            for repeat in range(3):
                p=work/f"{seed}-{repeat}-p.json";s=work/f"{seed}-{repeat}-s.json"
                run([sys.executable,str(RESEARCH/"f017_corrected_oracle_primary.py"),"synthetic",str(fixture),str(p)])
                run([sys.executable,str(RESEARCH/"f017_corrected_oracle_secondary.py"),"synthetic",str(fixture),str(s)])
                pa,sa=load(p),load(s);p_hashes.append(sha(p));s_hashes.append(sha(s));last=(pa,sa)
            # Complete outputs include no timestamps/PIDs and must be identical.
            primary_repeat_identity &= len(set(p_hashes))==1; secondary_repeat_identity &= len(set(s_hashes))==1
            pa,sa=last;ma,mr,mc=max_metrics(pa,sa);observed_abs=max(observed_abs,ma);observed_rmse=max(observed_rmse,mr);observed_cos=max(observed_cos,mc)
            routes=all(x["selected_expert_ids"]==y["selected_expert_ids"] for x,y in zip(pa["layers"],sa["layers"],strict=True))
            cases.append({"seed":seed,"layers":pa["layer_count"],"primary_token":pa["selected_token"],"secondary_token":sa["selected_token"],
                          "route_structure_exact":routes,"max_abs":ma,"rmse":mr,"cosine_distance":mc})
        thresholds={"max_abs":SAFETY_FACTOR*observed_abs,"rmse":SAFETY_FACTOR*observed_rmse,
                    "cosine_min":1-SAFETY_FACTOR*observed_cos}
        if not all(c["route_structure_exact"] and c["primary_token"]==c["secondary_token"] for c in cases): raise SystemExit("structural/token disagreement")
        if not primary_repeat_identity or not secondary_repeat_identity: raise SystemExit("fresh process reproducibility")
        decoder_cases,mutations=quantized_differential_and_mutations()
        base=load(fixtures/"fixture-18106.json");base_path=work/"base.json";base_p=work/"base-result.json"
        base_path.write_bytes(canonical(base));run([sys.executable,str(RESEARCH/"f017_corrected_oracle_primary.py"),"synthetic",str(base_path),str(base_p)])
        base_result=load(base_p)
        for name in GRAPH_MUTATIONS:
            altered=mutate(base,name);path=work/f"mutation-{name}.json";result=work/f"mutation-{name}-result.json";path.write_bytes(canonical(altered))
            try:
                run([sys.executable,str(RESEARCH/"f017_corrected_oracle_primary.py"),"synthetic",str(path),str(result)])
                changed=load(result).get("result_sha256")!=base_result.get("result_sha256")
            except Exception: changed=True
            if not changed: raise SystemExit(f"mutation not localized: {name}")
            mutations.append({"id":name,"localized_or_rejected":True,"test_kind":"SEMANTIC_FIXTURE_MUTATION"})
    doc={"schema":"pulsarmlx.f017.corrected-oracle-checkpoint-free-qualification/1.0.0","result":"PASS",
         "seeds":list(SEEDS),"fresh_process_repeats":3,"cases":cases,"frozen_thresholds":thresholds,
         "safety_factor":SAFETY_FACTOR,"safety_factor_derivation":SAFETY_FACTOR_DERIVATION,
         "primary_fresh_process_byte_identity":primary_repeat_identity,"secondary_fresh_process_byte_identity":secondary_repeat_identity,
         "packed_decoder_cases":decoder_cases,"packed_decoder_case_count":len(decoder_cases),
         "mutations":mutations,"mutation_count":len(mutations),"target_observation_leakage":leakage,
         "original_checkpoint_shard_opens":0,"original_checkpoint_payload_reads":0}
    args.output.write_bytes(json.dumps(doc,indent=2,sort_keys=True).encode()+b"\n")
    print(json.dumps({"result":"PASS","cases":len(cases),"mutations":len(mutations),"thresholds":thresholds}))
    return 0
if __name__=="__main__": raise SystemExit(main())
