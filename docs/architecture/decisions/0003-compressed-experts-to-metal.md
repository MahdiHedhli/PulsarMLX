# ADR 0003: Keep experts compressed through Metal residency

- **Status**: Target architecture; pending measured kernel qualification
- **Date**: 2026-08-09

## Decision

The target expert path keeps checkpoint weights compressed through stable
page-aligned unified-memory residency and performs quantized decode plus matvec
inside Metal compute. Qualified kernels should fuse gate, up, SwiGLU, down,
routing-weight application, and deterministic aggregation where measured
benefit and correctness permit.

## Consequences

Complete decoded f32 matrices should not be the production representation when
a qualified quantized kernel exists. The current NumPy decode plus f32 MLX path
remains the transitional implementation, correctness reference, and fallback
for unsupported formats. This ADR does not claim that PulsarMLX currently has a
direct quantized Metal expert kernel.
