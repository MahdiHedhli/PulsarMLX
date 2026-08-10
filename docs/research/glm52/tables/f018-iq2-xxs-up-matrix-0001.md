# Feature 018 real IQ2_XXS up matrix gate

> One bound real matrix only; not complete-expert, MoE, layer, token, or production evidence.

- Source: `2d00f9d0d63a9dec24fb0330a59397209025e416` (clean)
- Raw SHA-256: `395c1ae2b962deac4f5fd16531b7041e5877a5cb3269e5a6634fa3ce2a60f43f`
- Checkpoint set: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee` at immutable revision `abc55e72527792c6e77069c99b4cb7de16fa9f23`
- Tensor: `blk.3.ffn_up_exps.weight`, layer `3`, expert `15`, shape `2048 × 6144`
- Packed matrix SHA-256: `261011f1f3f084b6db48583711c14f20a9ae4e4e588b877b99db1aee0c2117af`; activation SHA-256: `b286b0baea31b825002e1dd5d7aa41f6055e7ca94cb7e2d27c0e97a50a56e3c9`
- Classification: `numerically_qualified_greedy_identical` (greedy selection is not applicable at this boundary)
- Exact f32 bits: `false`; bit mismatches: `2009`
- Tolerance mismatches: `0`; signed-zero mismatches: `0`
- Max absolute error: `2.01165676e-07`; RMSE: `2.50896145e-08`
- Cosine: `0.999999999999`; norm ratio: `0.999999990410`
- Deterministic direct repetitions: `30`; CPU fallback: `0`; complete f32 weight materialization: `0` bytes

## Current optimized NumPy + MLX reference

| Stage | Median (s) |
| --- | ---: |
| Storage read | 0.000356563 |
| NumPy dequantization | 0.079831125 |
| Contiguous-buffer check | 0.000041958 |
| MLX matrix build/eval | 0.004988520 |
| MLX matvec | 0.003445312 |
| Total (without cleanup) | 0.089100605 |

## Direct packed Metal candidate

| Stage | Time (s) |
| --- | ---: |
| Checkpoint bounded read | 0.000581708 |
| Stable-slab copy | 0.000055250 |
| No-copy Metal registration | 0.000012666 |
| Shader compile (process setup) | 0.034298209 |
| First dispatch after setup | 0.003538042 |
| Steady dispatch | 0.000027938 |
| Steady GPU command interval | 0.000821083 |
| Steady synchronized call | 0.001155791 |
| Steady total | 0.001183417 |

At this bound warm matrix only, the current optimized-path median is `0.089100605` s and the direct packed-Metal median is `0.001183417` s (ratio `75.29×`; absolute difference `0.087917188` s).

Steady direct population: 30 samples after 3 warmups; min `0.000819333` s, max `0.001379208` s.

Synchronization includes the command wait and is not additive to the GPU command interval. The ratio is not a model-level speedup claim.
