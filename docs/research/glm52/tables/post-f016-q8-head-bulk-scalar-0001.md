# Post-Feature-016 Q8_0 head-slab bulk-read scalar experiment

> One changed variable: per-row positional reads versus one complete head-slab read; scalar Q8_0 decoder unchanged.

- Evidence source: `0f38f1d4448789b5a938ed9db3baa659c797ecf0` (clean: `true`)
- Checkpoint set SHA-256: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`
- Protocol: 3 warm-ups and 10 measured samples per mode; OS page cache uncontrolled.

## One real head slab

| Mode | Storage (s) | Decode (s) | Buffer (s) | MLX build/eval (s) | Matvec (s) | Total (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `whole_matrix_numpy_q5_q8` | 0.000249 | 0.007627 | 0.000242 | 0.001416 | 0.000892 | 0.011338 |
| `whole_matrix_numpy_q5_q8_head_bulk_scalar` | 0.000024 | 0.007564 | 0.000312 | 0.001362 | 0.000987 | 0.011343 |

Head median total ratio: **1.000x**, exact f32 bits.

## Complete layer-3 MLA

| Mode | Head reads | Head storage (s) | Head decode (s) | Head build (s) | Head total (s) | 2-D total (s) | Residual (s) | MLA total (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `whole_matrix_numpy_q5_q8` | 49,152 | 0.025127 | 0.985940 | 0.145362 | 1.264112 | 0.714308 | 0.094780 | 2.073939 |
| `whole_matrix_numpy_q5_q8_head_bulk_scalar` | 128 | 0.000754 | 0.985381 | 0.145708 | 1.237768 | 0.722269 | 0.094692 | 2.062230 |

MLA median total ratio: **1.006x**, exact f32 bits.

This is a bounded head/MLA result, not a complete transformer-layer, stack, token, Rust, or Metal claim.
