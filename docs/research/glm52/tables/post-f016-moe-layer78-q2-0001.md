# Layer-78 Q2_K MoE integration

> One bounded layer-local MoE boundary; not P1/P2 or token latency.

- Baseline source: `4879c38b43f396c13038b78fa9114a5e496823e8`
- Candidate source: `ec2a981de58957e17ebf7c9b539ec9c71522218f`
- Exact f32 bits against scalar-reference MoE: `true`
- Median boundary ratio: **2.46x**

| Stage | Baseline median (s) | Q2_K candidate median (s) |
| --- | ---: | ---: |
| MoE boundary | 56.373736 | 22.898163 |
| Storage | 0.065990 | 0.041685 |
| Decode | 49.811814 | 20.424514 |
| Contiguous buffer | 5.960594 | 2.002285 |
| MLX construct | 0.122089 | 0.139630 |
| MLX eval | 0.003124 | 0.003147 |
| MLX matvec | 0.213515 | 0.131529 |
| Cleanup | 0.087068 | 0.076882 |
| SwiGLU | 0.002268 | 0.002240 |
| Uninstrumented residual | 0.031714 | 0.013998 |

## Candidate expert quantization medians

| Quant | Attributed (s) | Decode (s) | Buffer (s) | Matvec (s) |
| --- | ---: | ---: | ---: | ---: |
| Q3_K | 20.166532 | 17.969160 | 2.001865 | 0.070587 |
| Q2_K | 2.656544 | 2.459286 | 0.000425 | 0.060568 |
| Q5_K | 0.005183 | 0.000000 | 0.000000 | 0.005183 |
| Q6_K | 0.001684 | 0.000000 | 0.000000 | 0.001684 |

Q3_K is now the dominant measured routed-expert cost. The next bounded gate is exact Q3_K whole-matrix qualification and integration; no Metal kernel is selected.
