# Post-Feature-016 NumPy Q8_0 qualification

> Two-dimensional decoder boundary only; per-head 3-D Q8_0 remains excluded.

- Evidence source: `d24549193e3f9718c34e34b70904a5273af5978c` (clean: `true`)
- Checkpoint set SHA-256: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`
- Protocol: 3 warm-ups and 10 measured samples per mode; OS page cache uncontrolled.

| Tensor | Shard | Shape | Scalar first decode (s) | Vector first decode (s) | Exact f32 bits | Deterministic | Signed zero exact |
| --- | --- | ---: | ---: | ---: | --- | --- | --- |
| `blk.3.attn_q_b.weight` | `GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf` | 16384x2048 | 3.043840 | 0.072542 | true | true | true |
| `blk.20.attn_q_b.weight` | `GLM-5.2-UD-IQ2_XXS-00003-of-00006.gguf` | 16384x2048 | 3.269088 | 0.042444 | true | true | true |
| `blk.40.attn_q_b.weight` | `GLM-5.2-UD-IQ2_XXS-00004-of-00006.gguf` | 16384x2048 | 3.080504 | 0.039435 | true | true | true |
| `blk.60.attn_q_b.weight` | `GLM-5.2-UD-IQ2_XXS-00005-of-00006.gguf` | 16384x2048 | 3.122111 | 0.042135 | true | true | true |

## Decode-only benchmark

| Mode | Samples | Median (s) | Mean (s) | Stddev (s) | Min (s) | Max (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| scalar reference | 10 | 3.056227 | 3.064462 | 0.042456 | 3.018259 | 3.152984 |
| NumPy vectorized | 10 | 0.040342 | 0.040856 | 0.001304 | 0.040004 | 0.044316 |

Median decode-only ratio: **75.76x**.

This does not establish complete MLA/layer, per-head 3-D Q8_0, token, Rust, or Metal speedup.
