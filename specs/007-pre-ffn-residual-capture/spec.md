# Feature Specification: Qwen3MoE Layer-0 Pre-FFN Residual Capture

**Created**: 2026-08-06  
**Status**: Complete (verified)  
**Depends on**: Feature 002 `ffn_norm-0` freeze  
**Enables**: Feature 005 residual MoE block

## Goal

Capture the genuine layer-0 tensor **immediately before** `ffn_norm` from the
trusted pinned llama.cpp reference path, freeze its identity, and prove that
independent CPU RMSNorm of that tensor reproduces the existing Feature 002
`ffn_norm-0` freeze.

## Graph boundary (proved from implementation)

Pinned reference: llama.cpp `b06aa774c03dbbb624e726664b714a57d1f49815`,
`src/models/qwen3moe.cpp` graph for each layer `il`:

```
inpSA = residual stream into the layer
attn_out = Attention(RMSNorm(inpSA, attn_norm), ...)
ffn_inp = ggml_add(attn_out, inpSA)     // cb name: "ffn_inp"  → ffn_inp-0
cur     = RMSNorm(ffn_inp, ffn_norm)    // cb name: "ffn_norm" → ffn_norm-0
moe_out = MoE(cur, ...)                 // cb name: "ffn_moe_out"
l_out   = ggml_add(moe_out, ffn_inp)    // cb name: "l_out"
```

### Facts established from source + checkpoint (not names alone)

| Item | Value |
| --- | --- |
| Pre-norm tensor | `ffn_inp-0` = post-attention residual add |
| Post-norm tensor | `ffn_norm-0` = RMSNorm of `ffn_inp-0` |
| Norm weight | `blk.0.ffn_norm.weight` (f32, shape `[2048]`) |
| Norm bias | none (`NULL` in `build_norm`) |
| Epsilon | `qwen3moe.attention.layer_norm_rms_epsilon` = **1e-6** |
| Residual scale before norm | none |
| Gate before norm | none |
| Shared expert | none in this arch branch |

## Capture protocol

- Single-target CPU capture of `ffn_inp-0` only (dual-ask of `ffn_inp`+`ffn_norm`
  makes `ffn_inp` a scheduler leaf and drops `ffn_norm` from the graph).
- Same immutable checkpoint, tokens `[0,1]`, positions `[0,1]`, context/batch/ubatch 2,
  1 thread, as Feature 002.
- Helper: `scripts/research/llama_capture/residual_inp_capture.cpp`
- Orchestration: `scripts/research/capture_residual_oracle.sh`

## Mandatory validation

```
CPU_RMSNorm(captured_ffn_inp, blk.0.ffn_norm.weight, eps=1e-6)
  ~= existing_frozen_ffn_norm_0
```

The Feature 002 `ffn_norm-0` fixture is **not** regenerated. The capture links to it.

## Success evidence

- Residual sha256 `673441ded7cd24b304b7c3b9472fabce2419c9f6b53c8c7d25a96baf3c09832d`
  (two independent captures identical)
- RMSNorm vs F002 freeze: max abs ≈ **8.5e-8** (row0), **9.5e-8** (row1); 0 mismatches
- Evidence: `docs/research/raw/007-pre-ffn-residual/`

## Out of scope

MoE execution, attention re-implementation, logits, generation.
