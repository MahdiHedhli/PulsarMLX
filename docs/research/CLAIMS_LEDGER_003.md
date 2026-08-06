# Feature 003 Claims Ledger

**Status**: One real routed expert (index 114) full MLP weighted contribution
parity is published for Feature 003.

| Claim | Evidence files | Commit | Scope | Status | Caveat |
| --- | --- | --- | --- | --- | --- |
| F003-C01 Full layer-0 expert-114 MLP (gate/up/SiLU-SwiGLU/down) scaled by Feature 002 routing weight matches independent CPU oracle on Apple MLX GPU | [oracle freeze](raw/003-expert-mlp/f003-expert-oracle-114-freeze-0001.json), [parity](raw/003-expert-mlp/f003-expert-114-parity-0001.json) | 9855a523805d0c9499ac1bb929bb413a6cdd6fb9 | checkpoint=Qwen/Qwen3-30B-A3B-GGUF@e4d4bafdfb96a411a163846265362aceb0b9c63a;tensor=blk.0.ffn_{gate,up,down}_exps.weight;expert=114;depth=layer_0_single_expert_mlp_weighted | verified | Max abs error on weighted output 7.38e-08 under 5e-4 abs/rel; single expert only; no aggregation, layer, logits, or generation. |
