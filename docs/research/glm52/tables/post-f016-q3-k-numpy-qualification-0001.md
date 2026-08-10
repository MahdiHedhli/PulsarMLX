# Post-Feature-016 NumPy Q3_K qualification

> Decoder boundary only. This checkpoint contains Q3_K only in the layer-78 routed down tensor.

- Evidence source: `0a7e2c61dc8181abb6f200a9f7b1fef1641c87ea` (clean: `true`)
- Checkpoint set SHA-256: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`

| Tensor | Expert | Shape | Encoded MiB | Scalar first decode (s) | Vector first decode (s) | Exact f32 bits |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `blk.78.ffn_down_exps.weight` | 242 | 6144x2048 | 5.156 | 2.621411 | 0.145567 | true |
| `blk.78.ffn_down_exps.weight` | 246 | 6144x2048 | 5.156 | 2.545562 | 0.141721 | true |
| `blk.78.ffn_down_exps.weight` | 28 | 6144x2048 | 5.156 | 2.583307 | 0.148315 | true |
| `blk.78.ffn_down_exps.weight` | 48 | 6144x2048 | 5.156 | 2.653568 | 0.137936 | true |

## Bounded decode population

| Mode | Samples | Median (s) | Mean (s) | Stddev (s) |
| --- | ---: | ---: | ---: | ---: |
| scalar reference | 10 | 2.550016 | 2.552841 | 0.009417 |
| NumPy vectorized | 10 | 0.135837 | 0.138943 | 0.006747 |

Layer-78 expert-242 down median decode-only ratio: **18.77x**.

This is not complete expert, MoE, layer, stack, token, Rust, or Metal evidence.
