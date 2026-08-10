# Post-Feature-016 NumPy Q2_K qualification

> Decoder boundary only. This checkpoint contains Q2_K only in layer-78 routed gate/up tensors.

- Evidence source: `296e88688b536b7acc964fbf09137aa45b0ca4ac` (clean: `true`)
- Checkpoint set SHA-256: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`

| Tensor | Expert | Shape | Encoded MiB | Scalar first decode (s) | Vector first decode (s) | Exact f32 bits |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `blk.78.ffn_gate_exps.weight` | 242 | 2048x6144 | 3.938 | 2.272694 | 0.156887 | true |
| `blk.78.ffn_up_exps.weight` | 246 | 2048x6144 | 3.938 | 2.248328 | 0.147564 | true |
| `blk.78.ffn_gate_exps.weight` | 28 | 2048x6144 | 3.938 | 2.334703 | 0.164356 | true |
| `blk.78.ffn_up_exps.weight` | 48 | 2048x6144 | 3.938 | 2.313109 | 0.147089 | true |

## Bounded decode population

| Mode | Samples | Median (s) | Mean (s) | Stddev (s) |
| --- | ---: | ---: | ---: | ---: |
| scalar reference | 10 | 2.265407 | 2.266040 | 0.008562 |
| NumPy vectorized | 10 | 0.147176 | 0.150326 | 0.009577 |

Layer-78 expert-242 gate median decode-only ratio: **15.39x**.

This is not complete expert, MoE, layer, stack, token, Rust, or Metal evidence.
