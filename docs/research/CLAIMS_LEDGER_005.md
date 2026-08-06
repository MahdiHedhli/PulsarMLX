# Claims ledger — Feature 005 complete MoE residual block

| Claim ID | Claim | Evidence | source_commit | Scope | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| F005-C01 | Layer-0 MoE residual block `y = ffn_inp + top-8 MoE(ffn_norm)` matches independent CPU oracle on Apple MLX GPU | [capture](raw/005-moe-block/capture-summary.json), [oracle](raw/005-moe-block/f005-moe-block-oracle-0001.json), [parity](raw/005-moe-block/f005-moe-block-parity-0001.json) | 371ef664935079be4568a86ed6cf08750d2e8e38 | checkpoint=Qwen3-30B-A3B-Q8_0; residual=ffn_inp-0; experts=[114,45,99,46,98,74,102,65]; depth=layer_0_moe_block_residual_add | verified | max_abs≈6.2e-8; 0 mismatches; ffn_norm freeze identity retained; RMS-norm(residual) vs F002 freeze max_abs≈8.5e-8; no attention/generation. |
