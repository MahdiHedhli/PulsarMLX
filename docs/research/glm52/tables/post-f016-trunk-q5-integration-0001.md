# Post-Feature-016 Q5_K dense integration

> One changed variable: exact scalar Q5_K decode versus exact-bit NumPy Q5_K decode. Both modes use one complete matrix read; non-Q5 formats remain scalar.

- Evidence source: `f6446a07d62118672d6d593d536f834786ad2b54` (clean: `true`)
- Checkpoint set SHA-256: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`
- Protocol: 3 warm-ups and 10 counterbalanced measured samples per mode; OS page cache uncontrolled.

## Complete Q5_K matrix

`blk.3.attn_output.weight` (6144x16384), exact f32 bits across modes.

| Mode | Storage (s) | Decode (s) | Buffer (s) | MLX build/eval (s) | Matvec (s) | Total (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| whole-matrix scalar | 0.006922 | 9.600126 | 0.178575 | 1.253201 | 0.021836 | 11.080288 |
| whole-matrix NumPy Q5_K | 0.007207 | 0.487073 | 0.000002 | 0.035034 | 0.013088 | 0.547885 |

Median total ratio: **20.22x**.

## Complete layer-3 MLA boundary

The captured 2-D path contains 2 Q5_K projections and 2 non-Q5 scalar projections. Per-head 3-D Q8_0 work remains in the uninstrumented residual. Output matched exact f32 bits.

| Mode | Storage (s) | Decode (s) | Buffer (s) | MLX build/eval (s) | Matvec (s) | Total (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| whole-matrix scalar | 0.007006 | 13.369694 | 0.302360 | 1.842312 | 0.048760 | 17.983298 |
| Q5_K NumPy; other scalar | 0.009253 | 3.091203 | 0.091108 | 0.490447 | 0.035999 | 5.317590 |

Median total ratio: **3.38x**. Median uninstrumented residual changed from 2.403758 s to 1.577387 s and is not attributed to a specific cause.

This does not establish a complete transformer-layer, stack, token-generation, Q8_0/Q6_K, Rust, or Metal speedup.
