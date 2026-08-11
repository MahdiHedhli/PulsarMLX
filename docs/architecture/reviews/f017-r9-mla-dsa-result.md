# Feature 017 R9 MLA/DSA result

Status: **checkpoint-free R9 passed; numerical inheritance cleared by the
R7/R8 vocabulary remediation**.

## Frozen inputs

- production source: `43569b6920972e83155bfd1f1928d597ab7e9593`
- independent fixture: `f017-r9-mla-dsa-q8-0-v1`
- exact scaffold: `f017-r9-mla-dsa-exact-v1`
- production contract: `f017-production-r9-tier-b-v1`
- backend: MLX native 0.31.2 / MLX C 0.6.0 through the production adapter
- checkpoint access: none

The independent Python/NumPy fixture was committed before native candidate
execution and retains canonical little-endian f32 bytes and hashes for every
recorded boundary. The exact scaffold matches every MLA intermediate bit for
bit. Its separate DSA record verifies visible masking, stable lower-position
tie-breaking, selected order `[7, 8, 11, 4]`, and the append/state transition.

For the P1-sized short-context boundary, DSA is correctly `range_fill` with
positions `[0, 1, 2]`: visible positions remain below the architecture's 2,048
indexer top-k. This does not claim that the full long-context real-checkpoint
indexer has executed.

## Production qualification

Ten identical production repetitions completed with 60 native MLX matvec
dispatches, zero explicit-reference dispatches, zero unexpected fallbacks, and
zero backend errors. Each matvec independently passed the frozen
operand-conditioned Tier-B rule. The composed boundary classified
`numerically_qualified_greedy_not_applicable`:

| Metric | Observed |
|---|---:|
| Maximum absolute error over recorded boundaries | 1.430511474609375e-6 |
| Maximum RMSE | 4.6239814120400004e-7 |
| Minimum cosine similarity | 0.9999999999999575 |
| Deterministic repeats | 10 |
| Native dispatches | 60 |

The retained run recorded 0.000923126 seconds of import time,
0.023806165 seconds of compute/synchronization time, and 0.028539541 seconds
for the ten-repeat production population. These are bounded fixture timings,
not model-performance evidence.

Lifecycle accounting reconciled: 120/120 managed arrays, 60/60 derived arrays,
120 callbacks, 1/1 owned streams, no active context, and zero retained
in-flight work after teardown.

## Promotion boundary

The adversarial reviewer accepted the numerical evidence with a required
classification-vocabulary fix. That mechanical remediation is applied and
passed final-head CI; no numerical value, threshold, fixture, or production
output changed. R9/R10 inheritance is cleared.

Machine-readable evidence:
`docs/architecture/reviews/evidence/f017-r9-mla-dsa-production-v1.json`.
