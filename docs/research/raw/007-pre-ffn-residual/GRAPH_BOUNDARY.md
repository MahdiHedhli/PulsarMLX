# Layer-0 FFN residual graph boundary

## Source of truth

- Repository: ggml-org/llama.cpp  
- Revision: `b06aa774c03dbbb624e726664b714a57d1f49815`  
- File: `src/models/qwen3moe.cpp` (`llama_model_qwen3moe::graph`)

## Exact sequence for layer `il = 0`

1. `inpSA` = residual stream entering the layer (token embeddings for layer 0).
2. Attention sub-block on `RMSNorm(inpSA, attn_norm)` with Q/K norms and RoPE.
3. **`ffn_inp = ggml_add(attn_out, inpSA)`** → callback name `ffn_inp` → tensor **`ffn_inp-0`**.
4. **`ffn_norm = build_norm(ffn_inp, ffn_norm.weight, NULL, LLM_NORM_RMS)`** → **`ffn_norm-0`**.
5. `moe_out = build_moe_ffn(ffn_norm, …)` → `ffn_moe_out-0`.
6. **`l_out = ggml_add(moe_out, ffn_inp)`** → `l_out-0`.

## Relationship

```
ffn_norm-0 = RMSNorm(ffn_inp-0; weight=blk.0.ffn_norm.weight; eps=1e-6)
l_out-0    = ffn_inp-0 + MoE(ffn_norm-0)
```

There is **no** residual scaling, bias, or architecture-specific transform between
`ffn_inp` and `ffn_norm`. The second residual add uses the same `ffn_inp`
(pre-norm residual), not the normalized tensor.

## Checkpoint linkage

- Model: `Qwen3-30B-A3B-Q8_0.gguf`
- SHA-256: `4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c`
- Norm weight: `blk.0.ffn_norm.weight` f32 `[2048]`
- Epsilon KV: `qwen3moe.attention.layer_norm_rms_epsilon` = 1e-6
