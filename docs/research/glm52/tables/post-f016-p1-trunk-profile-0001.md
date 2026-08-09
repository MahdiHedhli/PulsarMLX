# Post-Feature-016 optimized P1 profile

Derived from the exact P1 record at clean source `9b6ab666c9dc89eda9b2ddf284a9a2767516d87e`.

## Correctness and user-visible boundary

- Exact generated prefix: `[9703, 21615]`
- Total evidence wall: 1425.756125 s
- Cold prompt stack: 1021.931135 s
- Full-vocabulary logits: 87.007223 s
- First-token selection component boundary: 1108.938358 s
- Wall-minus-terminal selection upper bound: 1108.997454 s
- Redundant retained terminal state-advance stack: 316.758671 s

## Warm stack attribution

| Rank | Component | Seconds |
| ---: | --- | ---: |
| 1 | `expert_cache_attributed` | 248.615785 |
| 2 | `full_vocabulary_logits_separate` | 87.007223 |
| 3 | `uninstrumented_residual` | 68.142886 |

Within expert-cache attribution: storage 9.655801 s, decode 203.329484 s, buffer 18.102678 s, build 9.215110 s, and matvec 8.312711 s.

The separate expert per-quant table covers cold plus warm combined. Its Q6_K rank is not a warm-only kernel decision.

## Historical cross-commit observations

| Record | Wall (s) | Reduction versus current |
| --- | ---: | ---: |
| `research_c11` | 48730.706509 | 97.07% |
| `legacy_p1` | 15146.448246 | 90.59% |
| `vectorized_expert_p1` | 6294.014912 | 77.35% |
| `iq3_vectorized_expert_p1` | 4582.511032 | 68.89% |

These are cross-commit observations, not controlled same-binary benchmark populations.

No additional full-model run is required for this sprint. Storage prefetch remains deferred, and Feature 018 remains profile-neutral because this exact P1 did not retain per-quant warm deltas.
