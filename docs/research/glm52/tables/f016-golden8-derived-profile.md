# Feature 016 golden-eight derived profile

Generated from committed raw evidence; no benchmark values are hard-coded in this table.

## Total and user-visible boundaries

| Metric | Seconds |
| --- | ---: |
| Complete evidence wall | 18522.659049 |
| Time to first token (recorded components) | 2646.649936 |
| Warm stack median | 1921.882049 |
| Warm logits median (separate) | 77.900249 |
| Terminal state advance after token eight selection | 1928.536098 |

## Cold stack

| Component | Seconds |
| --- | ---: |
| uninstrumented_trunk_residual | 1636.635724 |
| expert_cache_dequant_seconds | 836.065616 |
| expert_cache_contiguous_buffer_seconds | 74.588111 |
| expert_cache_mlx_matrix_build_seconds | 11.018476 |
| expert_cache_mlx_matvec_seconds | 8.909328 |
| expert_cache_storage_read_seconds | 1.956619 |

Cold per-quant attribution is unavailable: the passive watcher began after the cold and first warm stacks. No earlier snapshot was reconstructed.

## Warm top-level ranking

| Rank | Component | Mean seconds |
| ---: | --- | ---: |
| 1 | uninstrumented_trunk_residual | 1670.729513 |
| 2 | expert_cache_dequant_seconds | 206.003257 |
| 3 | full_vocabulary_logits_separate | 77.777555 |
| 4 | expert_cache_contiguous_buffer_seconds | 18.172826 |
| 5 | expert_cache_mlx_matrix_build_seconds | 9.615147 |
| 6 | expert_cache_mlx_matvec_seconds | 7.971767 |
| 7 | expert_cache_storage_read_seconds | 3.871705 |

## Warm per-quant ranking — EXPERT-CACHE PATH ONLY

Seven one-stack intervals cover generated tokens 2 through 8. This is not whole-token quantization cost.

| Rank | Quantization | Mean component seconds | Median |
| ---: | --- | ---: | ---: |
| 1 | IQ2_XXS | 69.672359 | 69.535227 |
| 2 | IQ3_XXS | 50.304118 | 50.430273 |
| 3 | Q2_K | 36.152508 | 36.084819 |
| 4 | IQ4_XS | 34.653586 | 34.594023 |
| 5 | IQ2_S | 33.963691 | 33.949984 |
| 6 | Q3_K | 20.390936 | 20.369295 |
| 7 | Q5_K | 0.812546 | 0.886867 |
| 8 | Q6_K | 0.378152 | 0.423408 |
| 9 | Q8_0 | 0.013596 | 0.017558 |

## Decision

- Warm residual median: 1675.491540 seconds (87.18% of stack wall).
- Warm storage mean: 3.871705 seconds (0.20% of mean stack wall).
- Prefetch/storage implementation is deferred because measured warm storage time is not material.
- Feature 018 remains profile-neutral; its first kernel is not selected until M2 Max trunk fixtures close the residual.
