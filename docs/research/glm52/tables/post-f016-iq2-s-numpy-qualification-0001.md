# Post-Feature-016 NumPy IQ2_S qualification

> Decoder boundary only. This checkpoint contains IQ2_S only in the layer-8 routed gate/up tensors.

- Evidence source: `fd98f89def72de69fcb45b834a4d349e6efc4af2` (clean: `true`)
- Checkpoint set SHA-256: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`

| Tensor | Expert | Shape | Encoded MiB | Scalar first decode (s) | Vector first decode (s) | Exact f32 bits |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `blk.8.ffn_gate_exps.weight` | 216 | 2048x6144 | 3.844 | 2.266049 | 0.069975 | true |
| `blk.8.ffn_up_exps.weight` | 244 | 2048x6144 | 3.844 | 2.138259 | 0.061492 | true |
| `blk.8.ffn_gate_exps.weight` | 206 | 2048x6144 | 3.844 | 2.133623 | 0.061680 | true |
| `blk.8.ffn_up_exps.weight` | 79 | 2048x6144 | 3.844 | 2.138238 | 0.061373 | true |

## Bounded decode population

| Mode | Samples | Median (s) | Mean (s) | Stddev (s) |
| --- | ---: | ---: | ---: | ---: |
| scalar reference | 10 | 2.128742 | 2.130125 | 0.005651 |
| NumPy vectorized | 10 | 0.067880 | 0.067415 | 0.001295 |

Layer-8 expert-216 gate median decode-only ratio: **31.36x**.

This is not complete expert, MoE, layer, stack, token, Rust, or Metal evidence.
