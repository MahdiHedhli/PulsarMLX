# Claims ledger — Feature 009 layer-0 attention

| Claim ID | Claim | Evidence | source_commit | Scope | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| F009-C01 | Architecture-level layer-0 attention residual `ffn_inp = embd + Attn(RMSNorm(embd))` matches independent CPU oracle on MLX at ~1e-7; NeoX RoPE, GQA 32/4, per-head q/k RMSNorm verified against qwen3moe.cpp | [parity](raw/009-layer0-attention/f009-layer0-attention-parity-0001.json), [oracle](raw/009-layer0-attention/f009-layer0-attention-oracle-0001.json) | cca6b99 (runtime; re-stamp on commit) | checkpoint=Qwen3-30B-A3B-Q8_0; tokens=[0,1]; positions=[0,1] | verified | MLX vs CPU max_abs ≈ 3.8e-8 / 1.1e-7; 0 mismatches; cos ≈ 1.0; CPU double-run SHA match. |
| F009-C02 | Frozen llama `ffn_inp-0` remains a secondary reference only; observed max_abs ≈ 2.4e-3 / 7.2e-4 with cos ≥ 0.99998 is consistent with Q8_0 activation requant on attention matmuls (F008 contract B), not a structural failure | same as F009-C01 capture_geometry | cca6b99 | secondary llama fused reference | verified | Llama bit-parity not claimed. Architecture path is ground truth. |
