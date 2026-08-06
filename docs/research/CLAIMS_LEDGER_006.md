# Claims ledger — Feature 006 complete transformer layer

| Claim ID | Claim | Evidence | source_commit | Scope | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| F006-C01 | Layer-0 output `l_out-0` matches Feature 005 residual MoE block within frozen tolerances | [parity](raw/006-layer-out/f006-layer-out-parity-0001.json), [l_out](raw/006-layer-out/l_out-0.f32le), [ffn_moe_out](raw/006-layer-out/ffn_moe_out-0.f32le) | 1b1dca2 | checkpoint=Qwen3-30B-A3B-Q8_0; depth=layer_0_output | **rejected** | max_abs≈3.43e-3 vs llama `l_out-0` / `ffn_moe_out-0`; 182 mismatches @ 5e-4; cosine≈0.999990. Independent F004/F005 path remains self-consistent at ~1e-7. Do not claim complete layer llama parity. |
