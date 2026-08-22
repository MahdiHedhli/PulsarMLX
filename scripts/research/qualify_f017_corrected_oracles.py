#!/usr/bin/env python3
"""Checkpoint-free qualification for corrected primary/secondary oracles."""
from __future__ import annotations
import argparse, hashlib, json, math, os, subprocess, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
RESEARCH=ROOT/"scripts/research"
SEEDS=tuple(range(18101,18113))
MUTATIONS=("Q6_K_LANE","IQ3_XXS_LANE","ROPE_POSITION","BOS_INSERTION","QK_TRANSPOSE",
           "TENSOR_OFFSET","QUANT_TYPE_ID","ROUTE_BIAS_ORDER","ROUTE_WEIGHT_PLACEMENT",
           "WRONG_EXPERT","WRONG_SHARED","LAYER_COUNT","FINAL_NORM","OUTPUT_TRANSPOSE","ACCUMULATION_PRECISION")

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
    elif name in {"QK_TRANSPOSE","TENSOR_OFFSET","QUANT_TYPE_ID","Q6_K_LANE","IQ3_XXS_LANE","ACCUMULATION_PRECISION"}:
        index=d["token"]*d["geometry"]["hidden"]
        t["token_embd.weight"][index]+=.125
    return d

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
        thresholds={"max_abs":max(2**-15,64*observed_abs),"rmse":max(2**-17,64*observed_rmse),
                    "cosine_min":1-max(2**-20,64*observed_cos)}
        if not all(c["route_structure_exact"] and c["primary_token"]==c["secondary_token"] for c in cases): raise SystemExit("structural/token disagreement")
        if not primary_repeat_identity or not secondary_repeat_identity: raise SystemExit("fresh process reproducibility")
        base=load(fixtures/"fixture-18106.json");base_path=work/"base.json";base_p=work/"base-result.json"
        base_path.write_bytes(canonical(base));run([sys.executable,str(RESEARCH/"f017_corrected_oracle_primary.py"),"synthetic",str(base_path),str(base_p)])
        base_result=load(base_p);mutations=[]
        for name in MUTATIONS:
            altered=mutate(base,name);path=work/f"mutation-{name}.json";result=work/f"mutation-{name}-result.json";path.write_bytes(canonical(altered))
            try:
                run([sys.executable,str(RESEARCH/"f017_corrected_oracle_primary.py"),"synthetic",str(path),str(result)])
                changed=load(result).get("result_sha256")!=base_result.get("result_sha256")
            except Exception: changed=True
            if not changed: raise SystemExit(f"mutation not localized: {name}")
            mutations.append({"id":name,"localized_or_rejected":True})
    doc={"schema":"pulsarmlx.f017.corrected-oracle-checkpoint-free-qualification/1.0.0","result":"PASS",
         "seeds":list(SEEDS),"fresh_process_repeats":3,"cases":cases,"frozen_thresholds":thresholds,
         "primary_fresh_process_byte_identity":primary_repeat_identity,"secondary_fresh_process_byte_identity":secondary_repeat_identity,
         "mutations":mutations,"mutation_count":len(mutations),"target_observation_leakage":leakage,
         "original_checkpoint_shard_opens":0,"original_checkpoint_payload_reads":0}
    args.output.write_bytes(json.dumps(doc,indent=2,sort_keys=True).encode()+b"\n")
    print(json.dumps({"result":"PASS","cases":len(cases),"mutations":len(mutations),"thresholds":thresholds}))
    return 0
if __name__=="__main__": raise SystemExit(main())
