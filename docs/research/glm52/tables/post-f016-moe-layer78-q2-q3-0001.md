# Layer-78 combined Q2_K/Q3_K MoE integration

> One bounded layer-local MoE boundary; not P1/P2 or token latency.

- Exact f32 bits against scalar-reference MoE: `true`
- Baseline-to-candidate median ratio: **14.72x**
- Q2-only-to-candidate median ratio: **5.98x**

| Stage | Baseline (s) | Q2_K only (s) | Q2_K + Q3_K (s) |
| --- | ---: | ---: | ---: |
| MoE boundary | 56.373736 | 22.898163 | 3.828766 |
| Storage | 0.065990 | 0.041685 | 0.002994 |
| Decode | 49.811814 | 20.424514 | 3.471512 |
| Contiguous buffer | 5.960594 | 2.002285 | 0.000549 |
| MLX construct | 0.122089 | 0.139630 | 0.117376 |
| MLX eval | 0.003124 | 0.003147 | 0.002978 |
| MLX matvec | 0.213515 | 0.131529 | 0.087634 |
| Cleanup | 0.087068 | 0.076882 | 0.076701 |
| SwiGLU | 0.002268 | 0.002240 | 0.002216 |
| Uninstrumented residual | 0.031714 | 0.013998 | 0.003052 |

## Candidate expert quantization medians

| Quant | Attributed (s) | Decode (s) | Build/eval (s) | Matvec (s) |
| --- | ---: | ---: | ---: | ---: |
| Q2_K | 2.566307 | 2.374828 | 0.080355 | 0.058318 |
| Q3_K | 1.188954 | 1.091631 | 0.040055 | 0.030107 |
| Q5_K | 0.005161 | 0.000000 | 0.000000 | 0.005161 |
| Q6_K | 0.001679 | 0.000000 | 0.000000 | 0.001679 |

Layer 8's scalar IQ2_S/IQ4_XS path is now the largest measured bounded MoE opportunity. The next gate is IQ2_S exact qualification; no Metal kernel is selected.
