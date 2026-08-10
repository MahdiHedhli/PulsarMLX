# Layer-8 combined IQ2_S/IQ4_XS MoE integration

> One bounded layer-local MoE boundary; not P1/P2 or token latency.

- Exact f32 bits against scalar-reference MoE: `true`
- Baseline-to-candidate median ratio: **25.08x**
- IQ2_S-only-to-candidate median ratio: **5.84x**

| Stage | Baseline (s) | IQ2_S only (s) | IQ2_S + IQ4_XS (s) |
| --- | ---: | ---: | ---: |
| MoE boundary | 42.965916 | 10.004603 | 1.713339 |
| Storage | 0.064724 | 0.041952 | 0.004716 |
| Decode | 36.423419 | 7.599570 | 1.364327 |
| Buffer | 5.974086 | 1.990244 | 0.000546 |
| MLX construct | 0.130329 | 0.139862 | 0.122553 |
| MLX eval | 0.003060 | 0.003001 | 0.002950 |
| MLX matvec | 0.163564 | 0.071304 | 0.071072 |
| Cleanup | 0.086394 | 0.076885 | 0.078595 |
| SwiGLU | 0.002236 | 0.002214 | 0.002221 |
| Residual | 0.030153 | 0.015654 | 0.003297 |

## Candidate expert quantization medians

| Quant | Attributed (s) | Decode (s) | Build/eval (s) | Matvec (s) |
| --- | ---: | ---: | ---: | ---: |
| IQ2_S | 1.193168 | 1.009087 | 0.083381 | 0.045827 |
| IQ4_XS | 0.450508 | 0.354383 | 0.041724 | 0.025438 |
| Q6_K | 0.005098 | 0.000000 | 0.000000 | 0.005098 |
| Q8_0 | 0.001762 | 0.000000 | 0.000000 | 0.001762 |

The exceptional layer-8 scalar decoder hotspot has collapsed. The next gate is a bounded multi-layer reprofile before residency or P2; no Metal kernel is selected.
