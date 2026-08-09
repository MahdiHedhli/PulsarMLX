# Post-Feature-016 complete layer-8 trunk comparison

> The original attempt is retained with `actual_status: failed` because its harness incorrectly required zero routed-matrix misses. This deterministic audit corrects only that semantic gate; it does not alter or rerun the samples.

- Measurement source: `7abcce2a3448c63df1226a2594734db630c42d9a` (clean: `true`)
- Retained record SHA-256: `6cafe067a907b45549c086265c9018a9ae4db4870efa85fd1e8748802dcd1d00`
- Correct cache contract: three protected shared-matrix hits and 24 transient routed-matrix misses per warm layer.

| Mode | Attention (s) | MoE (s) | Dense attributed (s) | Uninstrumented residual (s) | Cleanup (s) | Complete layer (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| scalar Q6_K; Q5/Q8 vector | 54.700836 | 42.436827 | 53.958375 | 0.909455 | 0.003428 | 97.071291 |
| NumPy Q6_K; Q5/Q8 vector | 1.758870 | 42.475366 | 1.796464 | 0.132351 | 0.003427 | 44.266072 |

Median complete-layer ratio: **2.19x**. Attention midpoint, top-8 route, and complete-layer f32 output were exact and deterministic across modes.

This is one complete single-position layer-8 boundary, not a stack, P1, token-generation, Rust, or Metal claim.
