# Feature 004 Claims Ledger

| Claim | Evidence files | Commit | Scope | Status | Caveat |
| --- | --- | --- | --- | --- | --- |
| F004-C01 Layer-0 top-8 routed expert MLP aggregation matches independent CPU oracle on Apple MLX GPU | [oracle](raw/004-top8-moe/f004-top8-oracle-0001.json), [parity](raw/004-top8-moe/f004-top8-aggregate-parity-0001.json) | 54454f410b1e79a27835c4ceda78c58a1fce31fd | checkpoint=Qwen3-30B-A3B-Q8_0;experts=[114, 45, 99, 46, 98, 74, 102, 65];depth=layer_0_top8_routed_aggregation | verified | max_abs=6.19571565163568e-08; 0 mismatches; I/O gauges retained; no residual/attention/generation. |
