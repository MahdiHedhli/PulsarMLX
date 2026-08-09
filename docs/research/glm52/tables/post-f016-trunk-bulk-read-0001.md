# Post-Feature-016 trunk bulk-read experiment

> Phase A changes storage request granularity only. The scalar decoder, row order, f32 materialization, and synchronized MLX matvec are unchanged.

- Evidence source: `bf697033b2288f92f8659f0e8e2b10b04b3e17f6` (clean: `true`)
- Checkpoint set SHA-256: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`
- Warm-ups / measured samples per mode: 3 / 10
- OS page cache: uncontrolled; results are a counterbalanced warm-storage population.

## Real matrix boundaries

| Tensor | Quant | Shape | Encoded MiB | Reads row -> bulk | Read reduction | Storage median row -> bulk (s) | Decode median row -> bulk (s) | Total median row -> bulk (s) | Total change | Exact f32 bits |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `blk.3.attn_output.weight` | Q5_K | 6144x16384 | 66.000 | 6,144 -> 1 | 6,144x | 0.010110 -> 0.007270 | 9.828690 -> 9.862949 | 11.128198 -> 11.195878 | +0.608% | true |
| `blk.3.attn_q_b.weight` | Q8_0 | 16384x2048 | 34.000 | 16,384 -> 1 | 16,384x | 0.011971 -> 0.004851 | 2.299065 -> 2.304405 | 2.758256 -> 2.761927 | +0.133% | true |
| `blk.8.attn_output.weight` | Q6_K | 6144x16384 | 78.750 | 6,144 -> 1 | 6,144x | 0.012725 -> 0.008610 | 46.944773 -> 46.814615 | 48.312671 -> 48.097612 | -0.445% | true |

## Representative MLA boundary

Layer 8 complete single-position MLA attention produced exact f32-bit output across modes. The dense metrics cover the four 2-D projections; per-head 3-D Q8_0 work remains in the explicitly recorded uninstrumented residual.

| Metric | Row reference | Whole-matrix scalar | Change |
| --- | ---: | ---: | ---: |
| 2-D positional read requests | 25,152 | 4 | 6,288x reduction |
| Storage median (s) | 0.027867 | 0.007772 | -72.111% |
| Scalar decode median (s) | 55.219687 | 55.040355 | -0.325% |
| Total boundary median (s) | 59.777971 | 59.546396 | -0.387% |
| Uninstrumented residual median (s) | 2.382950 | 2.381650 | n/a |

## Decision

Whole-matrix reads satisfy the exactness and request-accounting gates but do not materially reduce these warm boundary totals. Scalar decode dominates the representative MLA boundary, so Phase B should qualify only the highest-value trunk decoder formats while retaining this one-read path.

This record does **not** establish a complete transformer-layer, full-stack, token-generation, process-cold storage, Rust, or direct-Metal speedup.
