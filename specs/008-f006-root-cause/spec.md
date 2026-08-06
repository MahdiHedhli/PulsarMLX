# Feature Specification: F006 MoE Discrepancy Root Cause

**Created**: 2026-08-06  
**Status**: Resolved by contract (choice B)  
**Depends on**: F003–F005, F007; frozen F006 rejection evidence  

## Goal

Root-cause the ~3.4e-3 max_abs gap between independent PulsarMLX/CPU MoE and
llama fused MoE without loosening tolerances or rewriting closed features.

## Pairwise result (frozen case)

| Pair | max_abs | mismatches @ 5e-4 | Note |
| --- | --- | --- | --- |
| A MLX vs B independent CPU | ~6.2e-8 | 0 | F004 published |
| B independent CPU vs C llama fused | ~3.43e-3 | 148 | F006 rejection |
| A vs C | same order as B vs C | — | follows from A≈B |

## First divergent intermediate

1. `ffn_norm` — **exact match** to F002 freeze (max_abs 0)  
2. top-8 IDs — **exact match**  
3. normalized routing weights — **agree** (~3.5e-7)  
4. **expert gate/up Q8_0 matvec** — **first material divergence** (~4e-3)  
5. SwiGLU form `silu(gate)*up` — correct on both sides  
6. accumulation order — not primary (llama weighted sum ≡ llama moe ~1e-7)

## Root cause (source + reproduction)

llama.cpp / ggml for `GGML_TYPE_Q8_0` weights sets:

`type_traits_cpu[Q8_0].vec_dot_type = Q8_0`

`ggml_compute_forward_mul_mat` therefore **requantizes F32 activations to Q8_0**
and runs **Q8_0×Q8_0** integer dots.

PulsarMLX F003–F005 and the independent CPU oracle use **full weight dequant to
f32 × f32 activation** (no activation requantization).

Reproduction: implementing Q8_0×Q8_0 for expert 114 matches llama gate/up/down
within ~2e-7; f32-dequant path differs by ~4e-3 (same as observed).

## Contract decision

**B** — llama fused output has implementation-specific numerical semantics
(Q8_0×Q8_0). PulsarMLX matches the architecture-level independent oracle.

- Do **not** change F003–F005 oracles to match llama bit-for-bit.  
- Do **not** claim bit-identical llama MoE parity.  
- Optional future: a separate “llama-parity” mode using Q8_0 activation quant.

## Evidence

`docs/research/raw/008-f006-root-cause/`
