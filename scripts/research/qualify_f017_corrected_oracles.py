#!/usr/bin/env python3
"""Checkpoint-free qualification for corrected primary/secondary oracles."""
from __future__ import annotations
import argparse, hashlib, json, math, os, struct, subprocess, sys, tempfile
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
RESEARCH=ROOT/"scripts/research"
sys.path.insert(0, str(RESEARCH))
from f017_oracle_primary_decoders import decode as primary_decode
from qualify_f017_quantization_matrix_v1 import FORMATS, independent_decode, synthetic_block
import f017_corrected_oracle_primary_numerics_v2 as primary_module
from generate_f017_corrected_oracle_fixtures import fixture as make_fixture

SEEDS=tuple(range(18101,18113))
SAFETY_FACTOR=65536
SAFETY_FACTOR_DERIVATION="NEXT_POWER_OF_TWO_CEILING((TARGET_MAX_REDUCTION_16384/FIXTURE_MAX_REDUCTION_6)*(TARGET_LAYERS_79/FIXTURE_MAX_LAYERS_6)); ABSOLUTE_LOGIT_SCALE_TRANSFER_IS_CONSERVATIVE_FAIL_CLOSED_NOT_A_TARGET_ERROR_MODEL"
GRAPH_MUTATIONS=("ROPE_POSITION","BOS_INSERTION","QK_TRANSPOSE","TENSOR_OFFSET",
                 "ROUTE_BIAS_ORDER","ROUTE_WEIGHT_PLACEMENT","WRONG_EXPERT",
                 "WRONG_SHARED","LAYER_COUNT","FINAL_NORM","OUTPUT_TRANSPOSE","ACCUMULATION_PRECISION")

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
    elif name in {"ROUTE_BIAS_ORDER","WRONG_EXPERT","ROUTE_WEIGHT_PLACEMENT","ACCUMULATION_PRECISION"}: pass
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
    return cases,mutations

class ShiftedExpertSource:
    def __init__(self,source,expert_count): self.source,self.expert_count=source,expert_count
    def vector(self,*args): return self.source.vector(*args)
    def matrix(self,*args): return self.source.matrix(*args)
    def expert(self,name,expert,rows,columns):
        selected=(expert+1)%self.expert_count if "_exps.weight" in name else expert
        return self.source.expert(name,selected,rows,columns)

def f32(value): return struct.unpack("<f",struct.pack("<f",float(value)))[0]

def f32_left_fold_matvec(matrix,rows,columns,vector):
    if len(matrix)!=rows*columns or len(vector)!=columns: raise ValueError("mutated matvec geometry")
    output=[]
    for row in range(rows):
        total=0.0
        for column in range(columns): total=f32(total+f32(f32(matrix[row*columns+column])*f32(vector[column])))
        output.append(total)
    return output

def candidate_result(document,name):
    geometry=primary_module.Geometry.from_json(document["geometry"]);source=primary_module.JsonSource(document["tensors"])
    if name=="WRONG_EXPERT": source=ShiftedExpertSource(source,geometry.experts)
    if name=="ROUTE_BIAS_ORDER":
        def route_without_bias(logits,bias,count,scale):
            probabilities=[1.0/(1.0+math.exp(-value)) for value in logits]
            order=sorted(range(len(logits)),key=lambda index:(-probabilities[index],index))[:count]
            denominator=max(sum(probabilities[index] for index in order),2.0**-14)
            return order,[probabilities[index]/denominator*scale for index in order]
        context=mock.patch.object(primary_module,"_route",route_without_bias)
    elif name=="ROUTE_WEIGHT_PLACEMENT":
        original=primary_module._swiglu
        def unweighted(*args,**kwargs):
            if kwargs.get("expert") is not None: kwargs["weight"]=1.0
            return original(*args,**kwargs)
        context=mock.patch.object(primary_module,"_swiglu",unweighted)
    elif name=="ACCUMULATION_PRECISION": context=mock.patch.object(primary_module,"_matvec",f32_left_fold_matvec)
    else: context=mock.patch.object(primary_module,"_matvec",primary_module._matvec)
    with context: return primary_module.execute(source,geometry,document["token"],document["position"])

def localization(before,after):
    for left,right in zip(before["layers"],after["layers"]):
        fields=sorted(key for key in left if left.get(key)!=right.get(key))
        if fields: return {"earliest_layer":left["layer"],"changed_fields":fields}
    fields=sorted(key for key in before if key not in {"layers","result_sha256"} and before.get(key)!=after.get(key))
    return {"earliest_layer":None,"changed_fields":fields}

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True);args=parser.parse_args()
    # Historical target observations are quarantined from new implementation.
    forbidden=(str(21600+15),str(17300+51))
    scanned=[RESEARCH/"f017_corrected_oracle_primary_numerics_v2.py",RESEARCH/"f017_corrected_oracle_secondary_numerics_v2.py",
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
                run([sys.executable,str(RESEARCH/"f017_corrected_oracle_checkpoint_free_runner_v2.py"),"primary",str(fixture),str(p)])
                run([sys.executable,str(RESEARCH/"f017_corrected_oracle_checkpoint_free_runner_v2.py"),"secondary",str(fixture),str(s)])
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
        base_path.write_bytes(canonical(base));run([sys.executable,str(RESEARCH/"f017_corrected_oracle_checkpoint_free_runner_v2.py"),"primary",str(base_path),str(base_p)])
        base_result=load(base_p)
        for name in GRAPH_MUTATIONS:
            candidate_base=json.loads(json.dumps(base))
            if name=="ROUTE_BIAS_ORDER":
                gate=next(key for key in candidate_base["tensors"] if "ffn_gate_inp.weight" in key)
                bias=next(key for key in candidate_base["tensors"] if "exp_probs_b.bias" in key)
                candidate_base["tensors"][gate]=[0.0]*len(candidate_base["tensors"][gate]);candidate_base["tensors"][bias]=[-0.3,-0.1,0.3,0.1]
            expected=primary_module.execute(primary_module.JsonSource(candidate_base["tensors"]),primary_module.Geometry.from_json(candidate_base["geometry"]),candidate_base["token"],candidate_base["position"])
            if name in {"ROUTE_BIAS_ORDER","ROUTE_WEIGHT_PLACEMENT","WRONG_EXPERT","ACCUMULATION_PRECISION"}:
                observed=candidate_result(candidate_base,name);kind="EXECUTED_GRAPH_SEMANTIC_MUTATION"
            else:
                altered=mutate(candidate_base,name);observed=primary_module.execute(primary_module.JsonSource(altered["tensors"]),primary_module.Geometry.from_json(altered["geometry"]),altered["token"],altered["position"]);kind="SEMANTIC_FIXTURE_MUTATION"
            changed=observed.get("result_sha256")!=expected.get("result_sha256")
            if not changed: raise SystemExit(f"mutation not localized: {name}")
            location=localization(expected,observed)
            if not location["changed_fields"]: raise SystemExit(f"mutation lacks localized capture: {name}")
            mutations.append({"id":name,"localized_or_rejected":True,"test_kind":kind,**location})
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
