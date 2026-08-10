# Current complete layer-8 result

> Exact single-position layer boundary; not P1/P2 or token latency.

- Current source: `29c33ba6604425a20ecb46858561fd3d5ae06424`
- Exact midpoint/output/route preserved across commits: `true`
- Cross-commit complete-layer ratio: **12.61x**
- Cross-commit MoE ratio: **24.57x**

| Boundary | Prior median (s) | Current median (s) |
| --- | ---: | ---: |
| Complete layer | 44.266072 | 3.511617 |
| Attention/MLA | 1.758870 | 1.787092 |
| MoE | 42.475366 | 1.728566 |
| Dense attributed | n/a | 1.821354 |
| MoE decode | n/a | 1.366600 |
| MoE build/eval | n/a | 0.122907 |
| MoE matvec | n/a | 0.076787 |
| MoE cleanup | n/a | 0.085132 |

The current complete layer median is 3.511617 s, with 1.787092 s attention and 1.728566 s MoE. Ratios are cross-commit observations, not a counterbalanced same-binary population.
