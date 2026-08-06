# Feature Specification: Complete MoE FFN Sublayer / Residual Block

**Created**: 2026-08-06  
**Status**: Blocked pending residual stream capture  
**Depends on**: Feature 004 top-8 aggregation

## Goal

Complete the layer-0 **MoE block** as used in the transformer FFN residual
slot: residual add of routed MoE output onto the pre-norm residual stream.

## Current verified boundary

Feature 004 already verifies:

`ffn_norm-0 → top-8 expert MLPs → weighted aggregate`

That is the **post-norm MoE FFN sublayer output**.

## Blocker

The residual form `x + MoE(ffn_norm(x))` requires the **pre-norm residual
activation `x`** for the same token positions. Feature 002 capture only retains
`ffn_norm-0` (post-norm) activations, not the residual stream entering the FFN
block.

## Required next evidence

1. Extend capture orchestration to record residual (pre-`ffn_norm`) and
   `ffn_norm` for the same tokens.  
2. Recompute aggregate from Feature 004 path.  
3. CPU: `y = residual + aggregate`.  
4. MLX parity on `y`.  
5. Publish F005 claim only for residual MoE block depth.

## Until then

Do **not** claim “complete MoE block” or “transformer layer.” Feature 004 claim
stands for top-8 aggregation only.

## Out of scope until residual exists

Attention, multi-layer, logits, generation.
