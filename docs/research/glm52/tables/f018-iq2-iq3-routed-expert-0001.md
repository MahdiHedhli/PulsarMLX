# Feature 018 direct IQ2/IQ3 routed-expert gate

> One real layer-3 expert only: direct IQ2_XXS gate/up and direct IQ3_XXS down.

- Source: `feeb222ebfcfd1c6f2d3049f300e02658e67d57e` (clean)
- Raw SHA-256: `a8dd1115c23a709c0ade0991c67c859618682469f3c07e46399587e03a82108a`
- Layer/expert: `3` / `15`
- Classification: `numerically_qualified_greedy_identical`; mismatches: `0`; max absolute error: `3.63797881e-10`
- Warm reuse: `3` stable packed slabs, `3` hits/sample, `0` evictions, `0` fallback, `0` complete-f32 Metal weight bytes.

| Component | Median (s) |
| --- | ---: |
| Optimized reference decode | 0.231327999 |
| Optimized reference build/eval | 0.016051043 |
| Optimized reference matvec | 0.009651417 |
| Optimized reference total | 0.269965292 |
| Direct IQ2 gate synchronized | 0.001791479 |
| Direct IQ2 up synchronized | 0.001696521 |
| Direct IQ3 down synchronized | 0.000994083 |
| Direct three-projection kernel | 0.002462854 |
| SwiGLU activation | 0.000235021 |
| Direct complete expert total | 0.018807751 |

The same-boundary optimized-reference median was `0.269965292` s and the direct candidate median was `0.018807751` s (ratio `14.35×`; absolute difference `0.251157541` s).
