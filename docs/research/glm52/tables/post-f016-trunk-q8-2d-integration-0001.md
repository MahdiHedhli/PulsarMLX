# Post-Feature-016 2-D Q8_0 dense integration

> Q5_K remains vectorized in both modes. The only captured decoder change is 2-D Q8_0. Per-head 3-D Q8_0 remains unchanged and inside the residual.

- Evidence source: `15a358de4a48387e9c0d9d1b1da1d781be1a3c08` (clean: `true`)
- Checkpoint set SHA-256: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`

| Matrix mode | Storage (s) | Decode (s) | Buffer (s) | MLX build/eval (s) | Matvec (s) | Total (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Q5 vector; Q8 scalar | 0.003587 | 2.294140 | 0.072148 | 0.367079 | 0.016629 | 2.754374 |
| Q5 + 2-D Q8 vector | 0.003870 | 0.114811 | 0.000002 | 0.011999 | 0.005230 | 0.137694 |

Complete real matrix median ratio: **20.00x**, exact f32 bits.

## Complete layer-3 MLA

| MLA mode | Storage (s) | Decode (s) | Buffer (s) | MLX build/eval (s) | Matvec (s) | Total (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Q5 vector; 2-D Q8 scalar | 0.008205 | 3.069295 | 0.084032 | 0.469789 | 0.037085 | 5.253066 |
| Q5 + 2-D Q8 vector | 0.012121 | 0.639537 | 0.000005 | 0.053026 | 0.025944 | 2.057474 |

MLA median ratio: **2.55x**, exact f32 bits. Candidate uninstrumented residual median: 1.326647 s (64.48% of median wall; ratio of medians).

This does not establish per-head 3-D Q8_0, complete transformer-layer, token, Rust, or Metal speedup.
