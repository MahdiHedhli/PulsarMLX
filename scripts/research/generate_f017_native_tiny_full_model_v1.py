#!/usr/bin/env python3
"""Generate a public-safe complete tiny GLM-style model and independent token.

No Rust, FFI, MLX, checkpoint, subprocess, or production helper is imported.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path

def identity(rows:int, cols:int)->dict:
    values=[0.0]*(rows*cols)
    for i in range(min(rows,cols)): values[i*cols+i]=1.0
    return {"rows":rows,"columns":cols,"values":values}
def mv(matrix:dict,x:list[float])->list[float]:
    return [sum(matrix["values"][r*matrix["columns"]+c]*x[c] for c in range(matrix["columns"])) for r in range(matrix["rows"])]
def rms(x:list[float],s:list[float],eps:float)->list[float]:
    inv=1.0/math.sqrt(sum(v*v for v in x)/len(x)+eps);return [v*inv*w for v,w in zip(x,s,strict=True)]
def silu(x:float)->float:return x/(1.0+math.exp(-x))
def swiglu(m:dict[str,dict],prefix:str,x:list[float])->list[float]:
    g=mv(m[prefix+"gate.weight"],x);u=mv(m[prefix+"up.weight"],x)
    return mv(m[prefix+"down.weight"],[silu(a)*b for a,b in zip(g,u,strict=True)])

def build()->dict:
    # Use the frozen P1 token pair so this independent fixture can traverse
    # the exact receipt-producing executor path without special token rules.
    vocab=21616
    embedding=[0.0]*(vocab*2);embedding[9703*2:9703*2+2]=[1.0,0.0]
    output=[0.0]*(vocab*2);output[21615*2:21615*2+2]=[8.0,8.0]
    config={"layer_count":2,"hidden":2,"vocab":vocab,"leading_dense_layers":1,"expert_count":2,"expert_top_k":1,"dense_ffn":2,"expert_ffn":2,"heads":1,"q_rank":2,"kv_rank":2,"qk_nope":2,"qk_rope":2,"value_dim":2,"rms_epsilon":1e-5,"rope_base":8000000.0,"expert_weight_scale":1.0}
    matrices={"token_embd.weight":{"rows":vocab,"columns":2,"values":embedding},"output.weight":{"rows":vocab,"columns":2,"values":output}}
    vectors={"output_norm.weight":[1.,1.]};experts=[]
    for layer in range(2):
        for name,shape in {"attn_q_a.weight":(2,2),"attn_q_b.weight":(4,2),"attn_kv_a_mqa.weight":(4,2),"attn_output.weight":(2,2)}.items():matrices[f"blk.{layer}.{name}"]=identity(*shape)
        experts += [{"name":f"blk.{layer}.attn_k_b.weight","expert":0,"matrix":identity(2,2)},{"name":f"blk.{layer}.attn_v_b.weight","expert":0,"matrix":identity(2,2)}]
        for name in ["attn_norm.weight","attn_q_a_norm.weight","attn_kv_a_norm.weight","ffn_norm.weight"]:vectors[f"blk.{layer}.{name}"]=[1.,1.]
    for name in ["gate","up","down"]:matrices[f"blk.0.ffn_{name}.weight"]=identity(2,2)
    matrices["blk.1.ffn_gate_inp.weight"]=identity(2,2);vectors["blk.1.exp_probs_b.bias"]=[0.,0.]
    for expert in range(2):
        for name in ["gate","up","down"]:experts.append({"name":f"blk.1.ffn_{name}_exps.weight","expert":expert,"matrix":identity(2,2)})
    for name in ["gate","up","down"]:matrices[f"blk.1.ffn_{name}_shexp.weight"]=identity(2,2)
    # Independent whole-graph oracle. Position zero makes RoPE identity and a
    # one-key softmax exactly one; Q/K are still evaluated for finiteness.
    x=matrices["token_embd.weight"]["values"][9703*2:9703*2+2]
    em={(e["name"],e["expert"]):e["matrix"] for e in experts}
    for layer in range(2):
        xn=rms(x,vectors[f"blk.{layer}.attn_norm.weight"],config["rms_epsilon"])
        qa=mv(matrices[f"blk.{layer}.attn_q_a.weight"],xn);qan=rms(qa,vectors[f"blk.{layer}.attn_q_a_norm.weight"],config["rms_epsilon"])
        q=mv(matrices[f"blk.{layer}.attn_q_b.weight"],qan);kv=mv(matrices[f"blk.{layer}.attn_kv_a_mqa.weight"],xn);kvn=rms(kv[:2],vectors[f"blk.{layer}.attn_kv_a_norm.weight"],config["rms_epsilon"])
        key=mv(em[(f"blk.{layer}.attn_k_b.weight",0)],q[:2]);assert math.isfinite(sum(a*b for a,b in zip(key,kvn,strict=True)))
        value=mv(em[(f"blk.{layer}.attn_v_b.weight",0)],kvn);attn=mv(matrices[f"blk.{layer}.attn_output.weight"],value);x=[a+b for a,b in zip(x,attn,strict=True)]
        fx=rms(x,vectors[f"blk.{layer}.ffn_norm.weight"],config["rms_epsilon"])
        if layer==0:ffn=swiglu(matrices,"blk.0.ffn_",fx)
        else:
            logits=mv(matrices["blk.1.ffn_gate_inp.weight"],fx);probs=[1/(1+math.exp(-v)) for v in logits];chosen=max(range(2),key=lambda i:(probs[i],-i));weight=1.0
            routed={f"blk.1.ffn_{n}.weight":em[(f"blk.1.ffn_{n}_exps.weight",chosen)] for n in ["gate","up","down"]}
            rout=swiglu(routed,"blk.1.ffn_",fx);shared={f"blk.1.ffn_{n}.weight":matrices[f"blk.1.ffn_{n}_shexp.weight"] for n in ["gate","up","down"]};shr=swiglu(shared,"blk.1.ffn_",fx);ffn=[weight*a+b for a,b in zip(rout,shr,strict=True)]
        x=[a+b for a,b in zip(x,ffn,strict=True)]
    logits=mv(matrices["output.weight"],rms(x,vectors["output_norm.weight"],config["rms_epsilon"]));expected=max(range(len(logits)),key=lambda i:(logits[i],-i))
    assert expected==21615
    return {"schema":"pulsarmlx.f017.native-tiny-full-model-fixture/1.0.0","seed":17017,"config":config,"prompt_token":9703,"expected_token":expected,"vectors":vectors,"matrices":matrices,"expert_matrices":experts}

def main()->None:
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True);a=p.parse_args();raw=(json.dumps(build(),sort_keys=True,separators=(",",":"))+"\n").encode();a.output.write_bytes(raw);print(hashlib.sha256(raw).hexdigest())
if __name__=="__main__":main()
