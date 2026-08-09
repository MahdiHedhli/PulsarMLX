# Post-Feature-016 Q8_0 head-slab NumPy integration

> One changed variable: complete head-slab scalar Q8_0 decode versus exact-bit NumPy Q8_0 decode; one read in both modes.

- Evidence source: `a6f233822dade6096209a165d5085c4234063960` (clean: `true`)
- Checkpoint set SHA-256: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`
- Protocol: 3 warm-ups and 10 measured samples per mode; OS page cache uncontrolled.

## One real head slab

| Mode | Storage (s) | Decode (s) | Buffer (s) | MLX build/eval (s) | Matvec (s) | Total (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `whole_matrix_numpy_q5_q8_head_bulk_scalar` | 0.000018 | 0.006908 | 0.000264 | 0.001183 | 0.000777 | 0.009862 |
| `whole_matrix_numpy_q5_q8_head_numpy` | 0.000018 | 0.000348 | 0.000001 | 0.000278 | 0.000805 | 0.001535 |

Head median total ratio: **6.425x**, exact f32 bits.

## Complete layer-3 MLA

| Mode | Head reads | Head storage (s) | Head decode (s) | Head build (s) | Head total (s) | 2-D total (s) | Residual (s) | MLA total (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `whole_matrix_numpy_q5_q8_head_bulk_scalar` | 128 | 0.000775 | 0.980048 | 0.144586 | 1.233001 | 0.708334 | 0.093966 | 2.037030 |
| `whole_matrix_numpy_q5_q8_head_numpy` | 128 | 0.000535 | 0.017462 | 0.005972 | 0.057372 | 0.705703 | 0.007187 | 0.769746 |

MLA median total ratio: **2.646x**, exact f32 bits.

This is a bounded head/MLA result, not a complete transformer-layer, stack, token, Rust, or Metal claim.
