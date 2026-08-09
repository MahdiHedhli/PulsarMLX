# Post-Feature-016 NumPy Q6_K qualification

> Decoder boundary only; all five exercised Q6_K trunk tensors are covered.

- Evidence source: `06f0ff8ace8b3c38fbb2d344b76ba0d110f28fd9` (clean: `true`)
- Checkpoint set SHA-256: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`

| Tensor | Shape | Encoded MiB | Scalar first decode (s) | Vector first decode (s) | Exact f32 bits |
| --- | ---: | ---: | ---: | ---: | --- |
| `blk.0.ffn_down.weight` | 6144x12288 | 59.062 | 36.995476 | 0.985127 | true |
| `blk.1.ffn_down.weight` | 6144x12288 | 59.062 | 36.729216 | 0.932976 | true |
| `blk.2.ffn_down.weight` | 6144x12288 | 59.062 | 36.805070 | 0.954861 | true |
| `blk.8.attn_output.weight` | 6144x16384 | 78.750 | 49.118090 | 1.351459 | true |
| `blk.8.attn_q_a.weight` | 2048x6144 | 9.844 | 6.160629 | 0.150986 | true |

## Bounded decode population

| Mode | Samples | Median (s) | Mean (s) | Stddev (s) |
| --- | ---: | ---: | ---: | ---: |
| scalar reference | 10 | 6.181737 | 6.185721 | 0.017484 |
| NumPy vectorized | 10 | 0.143820 | 0.144403 | 0.001898 |

Layer-8 Q-A median decode-only ratio: **42.98x**.

This is not complete MLA/layer, stack, token, Rust, or Metal evidence.
