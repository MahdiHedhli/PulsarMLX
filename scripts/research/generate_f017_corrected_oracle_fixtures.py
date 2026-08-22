#!/usr/bin/env python3
"""Predeclared checkpoint-free fixture family for both corrected oracles."""
from __future__ import annotations
import argparse, json, random
from pathlib import Path

SEEDS = (18101, 18102, 18103, 18104, 18105, 18106, 18107, 18108, 18109, 18110, 18111, 18112)


def matrix(rng, rows, columns, scale=.12):
    return [rng.uniform(-scale, scale) for _ in range(rows * columns)]


def fixture(seed):
    rng = random.Random(seed)
    layers = 1 + (seed - SEEDS[0]) % 6
    g = {"layers":layers,"hidden":4,"vocab":9,"dense_layers":min(1,layers),"experts":4,
         "top_k":2,"dense_ffn":6,"expert_ffn":4,"heads":1,"q_rank":4,"kv_rank":4,
         "qk_nope":4,"qk_rope":2,"value_dim":4,"rms_epsilon":1e-5,
         "rope_base":8000000.0,"route_scale":2.5}
    t = {"token_embd.weight":matrix(rng,g["vocab"],4),"output_norm.weight":[1+rng.uniform(-.1,.1) for _ in range(4)],
         "output.weight":matrix(rng,g["vocab"],4,.25)}
    for layer in range(layers):
        for name,n in (("attn_norm",4),("attn_q_a_norm",4),("attn_kv_a_norm",4),("ffn_norm",4)):
            t[f"blk.{layer}.{name}.weight"]=[1+rng.uniform(-.1,.1) for _ in range(n)]
        t[f"blk.{layer}.attn_q_a.weight"]=matrix(rng,4,4)
        t[f"blk.{layer}.attn_q_b.weight"]=matrix(rng,6,4)
        t[f"blk.{layer}.attn_kv_a_mqa.weight"]=matrix(rng,6,4)
        t[f"blk.{layer}.attn_k_b.weight#0"]=matrix(rng,4,4)
        t[f"blk.{layer}.attn_v_b.weight#0"]=matrix(rng,4,4)
        t[f"blk.{layer}.attn_output.weight"]=matrix(rng,4,4)
        if layer == 0:
            for suffix,rows,cols in (("gate",6,4),("up",6,4),("down",4,6)):
                t[f"blk.{layer}.ffn_{suffix}.weight"]=matrix(rng,rows,cols)
        else:
            # Seeds 18103/18104 deliberately create exact/near route ties.
            t[f"blk.{layer}.ffn_gate_inp.weight"]=matrix(rng,4,4)
            bias=[rng.uniform(-.03,.03) for _ in range(4)]
            if seed == 18103: bias[0]=bias[1]=0.0
            if seed == 18104: bias[1]=bias[0]+2**-20
            t[f"blk.{layer}.exp_probs_b.bias"]=bias
            for expert in range(4):
                for suffix,rows,cols in (("gate",4,4),("up",4,4),("down",4,4)):
                    t[f"blk.{layer}.ffn_{suffix}_exps.weight#{expert}"]=matrix(rng,rows,cols,.08*(expert+1))
            for suffix in ("gate","up","down"):
                t[f"blk.{layer}.ffn_{suffix}_shexp.weight"]=matrix(rng,4,4,.06 if seed%2 else .2)
    return {"schema":"pulsarmlx.f017.corrected-oracle-synthetic-fixture/1.0.0","seed":seed,
            "coverage":{"position":"ZERO" if seed%3==0 else "NONZERO","route":"EXACT_TIE" if seed==18103 else "NEAR_TIE" if seed==18104 else "VARIED",
                        "context":"ONE_TOKEN" if seed%2 else "PREFIX_POSITION_SURROGATE",
                        "quant_format":("F32","Q2_K","Q3_K","Q4_K","Q5_K","Q6_K","Q8_0","IQ2_S","IQ2_XXS","IQ3_XXS","IQ4_XS")[seed%11]},
            "geometry":g,"token":seed%g["vocab"],"position":0 if seed%3==0 else seed%7+1,"tensors":t}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("output",type=Path);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    for seed in SEEDS:
        (args.output/f"fixture-{seed}.json").write_text(json.dumps(fixture(seed),sort_keys=True,separators=(",",":"))+"\n")
    return 0
if __name__=="__main__": raise SystemExit(main())
