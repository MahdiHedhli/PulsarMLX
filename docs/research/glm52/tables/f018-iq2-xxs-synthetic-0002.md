# Feature 018 synthetic direct-IQ2_XXS Metal gate

> Synthetic packed matrix only; not real checkpoint, expert, layer, token, or production evidence.

- Source: `da8f6b1a9712350b93953c94077ccfe5c9deffa9` (clean)
- Raw SHA-256: `6d94cffadf63928d14d46819d44a7dddfe3d2aea046457d4894212fb93431b4c`
- Device: `Apple M1 Ultra`
- Matrix: `64 × 6144`; `101376` packed bytes
- Classification: `numerically_qualified_greedy_identical`
- Deterministic repetitions: `100`; unique hashes: `1`
- Exact f32 bits: `false`; bit mismatches: `62`
- Tolerance mismatches: `0`; signed-zero mismatches: `0`
- Max absolute error: `0.000619888306`; RMSE: `0.000317373371`
- Cosine: `1.000000000000`; norm ratio: `0.999999904401`
- CPU fallback: `0`; complete f32 weight materialization: `0` bytes

| Stage | Median (s) | Mean (s) |
| --- | ---: | ---: |
| Storage read | 0.000000000 | — |
| No-copy registration | 0.000010125 | — |
| Shader compilation | 0.037631375 | — |
| Dispatch | 0.000025896 | 0.000027362 |
| GPU command interval | 0.000708917 | 0.000710015 |
| Synchronization | 0.000934813 | 0.000938441 |
| Steady-state total | 0.000962292 | 0.000965804 |

Steady-state population: 100 samples after 5 warmups; min `0.000926541` s, max `0.001022500` s.

The result proves a true packed-weight Metal GEMV boundary with numerical qualification. It does not establish a real-matrix or model speedup.
