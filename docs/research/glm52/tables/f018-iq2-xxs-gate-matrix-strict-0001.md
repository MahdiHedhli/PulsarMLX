# Feature 018 real IQ2_XXS gate matrix gate

> One bound real matrix only; not complete-expert, MoE, layer, token, or production evidence.

- Source: `5e4056cb3fe5ba9ce0a2279b1f543b29349e2aa1` (clean)
- Raw SHA-256: `24f70f5ca30a9b0f774510df0fd8ac63b27447a41c5e2e55869a3c9d0016d6bf`
- Checkpoint set: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee` at immutable revision `abc55e72527792c6e77069c99b4cb7de16fa9f23`
- Tensor: `blk.3.ffn_gate_exps.weight`, layer `3`, expert `15`, shape `2048 × 6144`
- Packed matrix SHA-256: `3822822b98505bb0c0447174b1f53d984ca3b78e95e9e118d61e5de84fa2fdc3`; activation SHA-256: `b286b0baea31b825002e1dd5d7aa41f6055e7ca94cb7e2d27c0e97a50a56e3c9`
- Classification: `numerically_qualified_greedy_identical` (greedy selection is not applicable at this boundary)
- Exact f32 bits: `false`; bit mismatches: `2008`
- Tolerance mismatches: `0`; signed-zero mismatches: `0`
- Max absolute error: `2.30967999e-07`; RMSE: `2.55223236e-08`
- Cosine: `0.999999999999`; norm ratio: `1.000000012417`
- Deterministic direct repetitions: `30`; CPU fallback: `0`; complete f32 weight materialization: `0` bytes

## Current optimized NumPy + MLX reference

| Stage | Median (s) |
| --- | ---: |
| Storage read | 0.000392145 |
| NumPy dequantization | 0.083478063 |
| Contiguous-buffer check | 0.000046022 |
| MLX matrix build/eval | 0.004950187 |
| MLX matvec | 0.002701625 |
| Total (without cleanup) | 0.091565000 |

## Direct packed Metal candidate

| Stage | Time (s) |
| --- | ---: |
| Checkpoint bounded read | 0.003825292 |
| Stable-slab copy | 0.000139417 |
| No-copy Metal registration | 0.000029083 |
| Shader compile (process setup) | 0.000707792 |
| Pipeline creation (process setup) | 0.047232625 |
| First dispatch after setup | 0.003205834 |
| Steady dispatch preparation | 0.000041459 |
| Steady dispatch | 0.000041459 |
| Steady GPU command interval | 0.001013792 |
| Steady synchronized call | 0.001308625 |
| Steady total | 0.001352563 |

At this bound warm matrix only, the current optimized-path median is `0.091565000` s and the direct packed-Metal median is `0.001352563` s (ratio `67.70×`; absolute difference `0.090212437` s).

Steady direct population: 30 samples after 3 warmups; min `0.001252666` s, max `0.002702625` s.

Synchronization includes the command wait and is not additive to the GPU command interval. The ratio is not a model-level speedup claim.
