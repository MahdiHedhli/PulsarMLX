# Post-Feature-016 NumPy Q5_K qualification

> Decoder boundary only. This table does not claim a complete MLA, transformer-layer, stack, token, Rust, or Metal speedup.

- Evidence source: `b5ad0059eae9f989c3f24fe7f6208e798fb66a4a` (clean: `true`)
- Checkpoint set SHA-256: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`
- Machine: Apple M1 Ultra, arm64
- Protocol: 3 warm-ups and 10 measured samples per mode; OS page cache uncontrolled.

## Complete real matrices

| Tensor | Shard | Shape | Encoded MiB | Scalar first decode (s) | Vector first decode (s) | Exact f32 bits | Deterministic | Signed zero exact |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| `blk.3.attn_output.weight` | `GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf` | 6144x16384 | 66.000 | 12.345869 | 0.504877 | true | true | true |
| `blk.20.attn_output.weight` | `GLM-5.2-UD-IQ2_XXS-00003-of-00006.gguf` | 6144x16384 | 66.000 | 12.248099 | 0.398000 | true | true | true |
| `blk.40.attn_output.weight` | `GLM-5.2-UD-IQ2_XXS-00004-of-00006.gguf` | 6144x16384 | 66.000 | 12.229869 | 0.398003 | true | true | true |
| `blk.60.attn_output.weight` | `GLM-5.2-UD-IQ2_XXS-00005-of-00006.gguf` | 6144x16384 | 66.000 | 12.520513 | 0.412517 | true | true | true |

## Decode-only benchmark

| Mode | Samples | Median (s) | Mean (s) | Stddev (s) | Min (s) | Max (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| scalar reference | 10 | 12.232673 | 12.249377 | 0.075195 | 12.159053 | 12.398374 |
| NumPy vectorized | 10 | 0.391463 | 0.394774 | 0.010133 | 0.389870 | 0.423228 |

Median decode-only ratio: **31.25x**.

The instrumented vector allocation observation reported 792.1 MiB Python-traced peak and a 8.537 GiB process peak-RSS high-water mark. Tracemalloc does not cover every NumPy native allocation, and peak RSS is process-lifetime cumulative.
