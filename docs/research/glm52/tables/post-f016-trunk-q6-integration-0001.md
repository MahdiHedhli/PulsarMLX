# Post-Feature-016 Q6_K dense integration

> One changed variable: Q6_K scalar row decode versus exact-bit whole-matrix NumPy Q6_K decode; Q5_K and all Q8_0 paths remain vectorized.

- Evidence source: `42c38d3ef61a251fc9823bdca0c35afdcdc171c8` (clean: `true`)
- Checkpoint set SHA-256: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`
- Protocol: 3 warm-ups and 10 counterbalanced measured samples per mode; OS page cache uncontrolled.

## Complete Q6_K matrix

`blk.8.attn_output.weight` (6144x16384), exact f32 output bits across modes.

| Mode | Storage (s) | Decode (s) | Buffer (s) | MLX build/eval (s) | Matvec (s) | Total (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| scalar Q6_K; Q5/Q8 vector | 0.008298 | 46.722426 | 0.181014 | 1.173033 | 0.021862 | 48.092368 |
| NumPy Q6_K; Q5/Q8 vector | 0.008401 | 1.365344 | 0.000002 | 0.034056 | 0.019603 | 1.426283 |

Median total ratio: **33.72x**.

## Complete layer-8 MLA boundary

The retained operation list contains 132 dense operations: 130 Q8_0 and 2 Q6_K vector operations, with 0 scalar operations. The raw record's legacy `captured_operation_contract` omits the Q6 count and its legacy scope label says four 2-D operations; validation derives this corrected audit from the immutable nested samples rather than rewriting them.

| Mode | Storage (s) | Decode (s) | Buffer (s) | MLX build/eval (s) | Matvec (s) | Uninstrumented residual (s) | Total (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| scalar Q6_K; Q5/Q8 vector | 0.009072 | 52.784314 | 0.202918 | 1.287702 | 0.069455 | 0.780079 | 55.137022 |
| NumPy Q6_K; Q5/Q8 vector | 0.012992 | 1.616308 | 0.000046 | 0.060972 | 0.064996 | 0.007253 | 1.762948 |

Median total ratio: **31.28x**, with exact f32 output bits.

This is a bounded single-position MLA result, not a complete transformer layer, stack, token, Rust, or Metal claim.
