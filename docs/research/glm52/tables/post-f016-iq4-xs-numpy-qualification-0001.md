# Post-Feature-016 NumPy IQ4_XS qualification

> Decoder boundary only; complete real matrices cover all four IQ4_XS layers.

- Evidence source: `bf44192a3893720c001eb02d4488935989030b0b` (clean: `true`)
- Checkpoint set SHA-256: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`

| Tensor | Expert | Shard | Shape | Scalar first decode (s) | Vector first decode (s) | Exact f32 bits |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| `blk.8.ffn_down_exps.weight` | 216 | `GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf` | 6144x2048 | 1.070705 | 0.052325 | true |
| `blk.75.ffn_down_exps.weight` | 246 | `GLM-5.2-UD-IQ2_XXS-00006-of-00006.gguf` | 6144x2048 | 1.073297 | 0.044211 | true |
| `blk.76.ffn_down_exps.weight` | 178 | `GLM-5.2-UD-IQ2_XXS-00006-of-00006.gguf` | 6144x2048 | 1.062868 | 0.044272 | true |
| `blk.77.ffn_down_exps.weight` | 191 | `GLM-5.2-UD-IQ2_XXS-00006-of-00006.gguf` | 6144x2048 | 1.062979 | 0.043196 | true |

## Bounded decode population

| Mode | Samples | Median (s) | Mean (s) | Stddev (s) |
| --- | ---: | ---: | ---: | ---: |
| scalar reference | 10 | 1.052149 | 1.061626 | 0.018764 |
| NumPy vectorized | 10 | 0.042700 | 0.042719 | 0.000635 |

Layer-8 expert-216 down median decode-only ratio: **24.64x**.

This is not complete expert, MoE, layer, stack, token, Rust, or Metal evidence.
