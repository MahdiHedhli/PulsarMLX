# Layer-8 IQ2_S MoE integration

> One bounded layer-local MoE boundary; not P1/P2 or token latency.

- Exact f32 bits against scalar-reference MoE: `true`
- Median boundary ratio: **4.29x**

| Stage | Baseline median (s) | IQ2_S candidate median (s) |
| --- | ---: | ---: |
| MoE boundary | 42.965916 | 10.004603 |
| Storage | 0.064724 | 0.041952 |
| Decode | 36.423419 | 7.599570 |
| Buffer | 5.974086 | 1.990244 |
| MLX construct | 0.130329 | 0.139862 |
| MLX eval | 0.003060 | 0.003001 |
| MLX matvec | 0.163564 | 0.071304 |
| Cleanup | 0.086394 | 0.076885 |
| SwiGLU | 0.002236 | 0.002214 |
| Residual | 0.030153 | 0.015654 |

## Candidate expert quantization medians

| Quant | Attributed (s) | Decode (s) | Buffer (s) | Matvec (s) |
| --- | ---: | ---: | ---: | ---: |
| IQ4_XS | 8.722821 | 6.585108 | 1.989881 | 0.028187 |
| IQ2_S | 1.200566 | 1.013902 | 0.000362 | 0.043358 |
| Q6_K | 0.005169 | 0.000000 | 0.000000 | 0.005169 |
| Q8_0 | 0.001681 | 0.000000 | 0.000000 | 0.001681 |

IQ4_XS is now the dominant measured layer-8 routed-expert cost. The next gate is exact IQ4_XS qualification; no Metal kernel is selected.
