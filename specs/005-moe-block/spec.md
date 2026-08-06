# Feature Specification: Complete MoE FFN Sublayer / Residual Block

**Created**: 2026-08-06  
**Status**: Complete (verified)  
**Depends on**: Feature 004 top-8 aggregation

## Goal

Complete the layer-0 **MoE block** as used in the transformer FFN residual
slot: residual add of routed MoE output onto the pre-norm residual stream.

## Verified form

```
ffn_inp-0 = post-attention residual (pre-FFN)
ffn_norm-0 = RMSNorm(ffn_inp-0)   # Feature 002 freeze
aggregate  = top-8 MoE(ffn_norm-0) # Feature 004
y          = ffn_inp-0 + aggregate
```

## Capture strategy

Single-target CPU capture of `ffn_inp-0` (pinned llama.cpp revision
`b06aa774…`) with the same tokens/positions as Feature 002. Dual-ask capture
of `ffn_inp` + `ffn_norm` is **not** used: returning true for `ffn_inp` as a
scheduler leaf truncates the graph before `ffn_norm`.

`ffn_norm-0` identity is the Feature 002 freeze
(`978205a61fb31d03a8627fd5b9c9319e4c32ef7af0d3d934ccaddda9defc68a7`).

Cross-check: independent RMSNorm(`ffn_inp-0`, `blk.0.ffn_norm.weight`,
eps=1e-6) matches F002 row-0 within ~8.5e-8 max abs error.

## Success evidence

- Independent residual captures match (sha256
  `673441ded7cd24b304b7c3b9472fabce2419c9f6b53c8c7d25a96baf3c09832d`)
- CPU oracle `y = residual + aggregate`
- MLX parity max abs error ~6.2e-8, 0 mismatches
- Evidence: `docs/research/raw/005-moe-block/`

## Out of scope

Attention, complete transformer layer output, multi-layer, logits, generation.
