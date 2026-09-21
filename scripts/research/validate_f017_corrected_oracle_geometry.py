#!/usr/bin/env python3
"""Mechanically bind corrected-oracle geometry to the Rust executable source."""
from __future__ import annotations
import argparse,json,re
from pathlib import Path

EXPECTED={"layer_count":"layers","hidden":"hidden","vocab":"vocab","leading_dense_layers":"dense_layers",
          "expert_count":"experts","expert_top_k":"top_k","dense_ffn":"dense_ffn","expert_ffn":"expert_ffn",
          "heads":"heads","q_rank":"q_rank","kv_rank":"kv_rank","qk_nope":"qk_nope","qk_rope":"qk_rope",
          "value_dim":"value_dim","rms_epsilon":"rms_epsilon","rope_base":"rope_base","expert_weight_scale":"route_scale"}
def strict(path):
 def hook(items):
  out={}
  for key,value in items:
   if key in out: raise ValueError("duplicate JSON key")
   out[key]=value
  return out
 return json.loads(path.read_text(),object_pairs_hook=hook)
def parse_number(text): return float(text.replace("_","")) if any(c in text for c in ".eE") else int(text.replace("_",""))
def main():
 parser=argparse.ArgumentParser();parser.add_argument("geometry",type=Path);parser.add_argument("rust",type=Path);args=parser.parse_args()
 geometry=strict(args.geometry);source=args.rust.read_text();body=source.split("pub fn glm52() -> Self",1)[1].split("pub fn validate",1)[0]
 for rust,json_key in EXPECTED.items():
  match=re.search(rf"\b{re.escape(rust)}:\s*([0-9_]+(?:\.[0-9_]+)?(?:e[+-]?[0-9]+)?)",body,re.I)
  if not match: raise SystemExit(f"missing executable geometry {rust}")
  actual=parse_number(match.group(1));expected=geometry[json_key]
  if float(actual)!=float(expected): raise SystemExit(f"geometry mismatch {rust}: {actual} != {expected}")
 print(f"PASS executable_numeric_bindings={len(EXPECTED)}")
 return 0
if __name__=="__main__": raise SystemExit(main())
