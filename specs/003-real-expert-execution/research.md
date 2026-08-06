# Research: Real Expert Execution

**Feature**: 003-real-expert-execution  
**Date**: 2026-08-06

## Decisions

### D1: Expert selection

**Decision**: Expert index **114** — Feature 002 single-row top-8 rank-0.  
**Rationale**: Exact routed selection from verified router parity.  
**Alternatives**: Expert 0 (Feature 001 prefix only; not rank-0 for this input).

### D2: Input

**Decision**: Feature 002 frozen row-0 of genuine `ffn_norm-0` activation
(`[1,2048]` from the two-token capture).  
**Rationale**: Same activation the router saw.  
**Alternatives**: Synthetic hidden; Feature 001 prompt probe (rejected).

### D3: Weight scaling

**Decision**: Multiply down-projection output by Feature 002 frozen normalized
routing weight for expert 114 on row-0.  
**Rationale**: Required weighted expert contribution for later aggregation.  
**Alternatives**: Unweighted MLP only (insufficient for Feature 004).

### D4: Activation

**Decision**: SwiGLU as `silu(gate) * up` with SiLU = `x * sigmoid(x)`, matching
Qwen3MoE expert FFN.  
**Rationale**: Standard Qwen3 MoE expert pattern; Feature 001 inventory width
768.  
**Alternatives**: GELU/ReLU (wrong architecture).

### D5: Quantization path

**Decision**: Decode Q8_0 expert slices via existing host Q8_0 path then MLX
f32 matvecs (same class as Feature 001 slice), unless packed layout forces a
documented extension.  
**Rationale**: Proven path; avoid new Metal kernels.  
**Alternatives**: Custom Metal Q8 kernels (out of scope).

### D6: Tolerances

**Decision**: Start with absolute 5e-4 and relative 5e-4 absolute-plus-relative
(Feature 001/002). Amend only with committed research note if Q8_0 full-width
requires it **before** any Apple pass is published.  
**Rationale**: Continuity; no silent loosening.

### D7: Evidence root

**Decision**: `docs/research/raw/003-expert-mlp/` with feature id
`003-real-expert-execution`.  
**Rationale**: Parallel to Feature 002 package layout.

## Open risks

- GGUF packing of all experts into `*_exps.weight` tensors may require careful
  byte-range math per expert index.  
- Full intermediate width 768 × 2048 Q8_0 decode memory must stay within
  admission bounds.  
- Load average quiet-window may block real runs (same as Feature 002).
