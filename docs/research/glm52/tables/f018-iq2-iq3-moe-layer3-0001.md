# Feature 018 direct IQ2/IQ3 top-8 plus shared MoE

> One real layer-3 MoE boundary; routed IQ2 gate/up and IQ3 down are direct, while the shared expert remains the explicit protected MLX reference path.

- Source: `39397d4870da6efab703354f88084c070065c523` (clean)
- Raw SHA-256: `513cfaaa3fe13d731cd477229f6e92acf1ce8c45d9236bf38ac9f90836b8b53d`
- Route: `[15, 177, 10, 233, 166, 41, 152, 26]`; shared expert: `0`
- Classification: `numerically_qualified_greedy_identical`; mismatches: `0`; max absolute error: `7.82165444e-09`

| Component | Median (s) |
| --- | ---: |
| Optimized reference total | 1.705199125 |
| Direct IQ2 gate/up synchronized | 0.027583458 |
| Direct IQ3 down synchronized | 0.008303854 |
| Routed SwiGLU activation | 0.001868980 |
| Shared reference | 0.002712333 |
| Complete top-8 plus shared | 0.226394771 |

Same-boundary ratio: `7.53×`; absolute difference: `1.478804355` s. This is not a complete-layer or token claim.
