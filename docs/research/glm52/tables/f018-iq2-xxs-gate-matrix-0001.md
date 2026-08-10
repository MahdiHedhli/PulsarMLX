# Feature 018 real IQ2_XXS gate matrix gate

> One bound real matrix only; not complete-expert, MoE, layer, token, or production evidence.

- Source: `20612556ecd2a5830c75ac7710414977faf1bafd` (clean)
- Raw SHA-256: `ef4ebfe44fbf704d34d8dc382acd304334ceddb863f9766321489585e472e93d`
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
| Storage read | 0.000380125 |
| NumPy dequantization | 0.081165437 |
| Contiguous-buffer check | 0.000049084 |
| MLX matrix build/eval | 0.005141895 |
| MLX matvec | 0.003529667 |
| Total (without cleanup) | 0.091133791 |

## Direct packed Metal candidate

| Stage | Time (s) |
| --- | ---: |
| Checkpoint bounded read | 0.000604250 |
| Stable-slab copy | 0.000108208 |
| No-copy Metal registration | 0.000017042 |
| Shader compile (process setup) | 0.090975875 |
| First dispatch after setup | 0.004690625 |
| Steady dispatch | 0.000044208 |
| Steady GPU command interval | 0.001086583 |
| Steady synchronized call | 0.001342563 |
| Steady total | 0.001387167 |

At this bound warm matrix only, the current optimized-path median is `0.091133791` s and the direct packed-Metal median is `0.001387167` s (ratio `65.70×`; absolute difference `0.089746624` s).

Steady direct population: 30 samples after 3 warmups; min `0.001320834` s, max `0.001495916` s.

Synchronization includes the command wait and is not additive to the GPU command interval. The ratio is not a model-level speedup claim.
