# Feature Specification: Complete Transformer Layer-0 Output

**Created**: 2026-08-06  
**Status**: Blocked / rejected against llama fused MoE  
**Depends on**: Feature 005 MoE residual block

## Goal

Verify layer-0 **complete output** `l_out-0` equals the Feature 005 residual
MoE block under frozen tolerances.

## Result

**Rejected.** Captured llama.cpp `l_out-0` and `ffn_moe_out-0` differ from the
independent Q8_0 top-8 MoE path (Feature 004/005) by:

- max abs error ≈ **3.43e-3**
- 182 / 2048 elements exceed absolute+relative 5e-4
- cosine similarity ≈ **0.999990** (directionally aligned)

Feature 005 residual composition (`y = ffn_inp + independent_MoE`) remains
verified self-consistently (CPU↔MLX ~1e-7). The gap is between the independent
expert Q8_0 path and llama fused MoE, not residual add.

## Deepest verified boundary

Feature 005: residual MoE block with independent expert execution.

## Required to unblock F006+

Align independent expert MoE kernels with llama fused `ffn_moe_out` (layout,
accumulation, gating scale, or Q8_0 matmul), or define a new admitted oracle
boundary without silently loosening tolerances.

## Out of scope until unblocked

Multi-layer replay, logits, generation.
