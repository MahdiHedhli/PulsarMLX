# Feature Specification: Complete MoE FFN Sublayer / Residual Block

**Created**: 2026-08-06  
**Status**: Complete (verified) for independent Q8_0 MoE path  
**Depends on**: Feature 004 top-8 aggregation; Feature 007 pre-FFN residual capture

## Goal

Complete the layer-0 **MoE block** as used in the transformer FFN residual
slot: residual add of routed MoE output onto the pre-norm residual stream.

## Verified form

```
ffn_inp-0 = post-attention residual (pre-FFN)   # Feature 007 capture
ffn_norm-0 = RMSNorm(ffn_inp-0)                 # Feature 002 freeze (linked)
aggregate  = top-8 MoE(ffn_norm-0)              # Feature 004 independent path
y          = ffn_inp-0 + aggregate              # Feature 005
```

## Oracle policy

- Residual activation: independent reference capture (`ffn_inp-0`), not MLX.
- Final block oracle for F005-C01: **independent CPU** recomputation
  `y = residual + F004_aggregate` (no MLX imports on oracle path).
- Cross-check vs llama fused `l_out-0` / `ffn_moe_out-0` is **Feature 006** and
  remains **rejected** (max abs ~3.4e-3) despite matching top-8 expert IDs.

## Capture strategy

Formalized as Feature 007. Single-target `ffn_inp-0` capture; dual-ask of
`ffn_inp`+`ffn_norm` is rejected (scheduler leaf truncation).

## Success evidence (F005-C01)

- Residual + F007 RMSNorm link to F002 freeze  
- CPU oracle `y = residual + aggregate`  
- MLX parity max abs error ~6.2e-8, 0 mismatches  
- Evidence: `docs/research/raw/005-moe-block/` + `docs/research/raw/007-pre-ffn-residual/`

## Out of scope

Attention re-implementation, llama fused MoE bit-parity (F006), multi-layer,
logits, generation.
