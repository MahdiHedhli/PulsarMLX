# GLM-5.2 Post-Golden-Eight Calculations

**Status**: passed; calculation-only analysis with no model inference

This report extends the authoritative `f016-golden8-derived-profile-0001.json`. It does not overwrite or reinterpret its existing metrics.

## Already-verified golden-eight metrics

| Metric | Value |
| --- | ---: |
| Complete evidence wall | 18522.659049 s |
| Cold prompt stack | 2569.173874 s |
| Warm stacks | 8 |
| Warm mean / median | 1916.364214 / 1921.882049 s |
| Warm sample SD / min / max | 12.887186 / 1892.661681 / 1928.536098 s |
| Watcher snapshots / valid intervals / resets | 8 / 7 / 0 |
| Shared-cache hits | 1824 |
| Decoded / compressed bytes avoided | 91804925952 / 16846159872 |
| CPU fallbacks / evictions / rejections | 0 / 0 / 0 |

All retained resource states were normal. The expert-cache-only per-quant ranking, warm residual, and storage/prefetch deferral remain authoritative in the earlier derived profile.

## Honest time through selection of token 8

| Boundary | Seconds |
| --- | ---: |
| Complete nine-stack evidence wall | 18522.659049 |
| Redundant terminal state-advance stack | 1928.536098 |
| Through token-8 selection, recorded components | 16593.771926 |
| Evidence wall minus terminal stack (upper bound) | 16594.122951 |
| Unassigned runner bookkeeping | 0.351025 |
| Time to first token, recorded components | 2646.649936 |

The subtraction is an upper bound because the source has no dedicated token-eight wall timestamp; it retains 0.351 seconds of unassigned runner bookkeeping. The component boundary follows the source order exactly: preceding transformer stack, logits selection, then the selected token's stack.

### Generated-token selection components

| Token # | ID | Preceding stack s | Logits s | Selection component s |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 21615 | 2569.173874 | 77.476062 | 2646.649936 |
| 2 | 220 | 1892.661681 | 75.760090 | 1968.421771 |
| 3 | 16 | 1899.710424 | 75.683191 | 1975.393615 |
| 4 | 13 | 1924.736348 | 79.464999 | 2004.201347 |
| 5 | 16 | 1919.125736 | 77.691854 | 1996.817590 |
| 6 | 16 | 1922.379329 | 78.108643 | 2000.487972 |
| 7 | 15 | 1921.407576 | 79.409445 | 2000.817021 |
| 8 | 15 | 1922.356523 | 78.626151 | 2000.982674 |

Tokens 2–8 inter-token components: n=7, mean 1992.445999 s, median 2000.487972 s, sample SD 14.334507 s, range 1968.421771–2004.201347 s.

## Per-layer uninstrumented residual

Residual means layer wall minus expert-cache storage, dequantization, contiguous-buffer, MLX-build, and MLX-matvec timers. It is not labeled trunk or cleanup cost.

### Layers 0–2

| Layer | Mean residual s | Median | Min | Max | Sample variance |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 72.271987 | 72.298039 | 71.677474 | 72.606813 | 0.095639 |
| 1 | 72.276800 | 72.232882 | 71.363194 | 73.254173 | 0.308934 |
| 2 | 72.472013 | 72.456566 | 71.812391 | 73.127612 | 0.210476 |

MoE layers 3–78 across 608 layer-token observations: mean 19.127703 s, median 18.581784 s, min 17.968606 s, max 60.613143 s, p95(Type 7) 18.987684 s.

### Top 10 layers by mean residual

| Rank | Layer | Group | Mean s | Median | Min | Max | Token variance |
| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 2 | leading_dense | 72.472013 | 72.456566 | 71.812391 | 73.127612 | 0.210476 |
| 2 | 1 | leading_dense | 72.276800 | 72.232882 | 71.363194 | 73.254173 | 0.308934 |
| 3 | 0 | leading_dense | 72.271987 | 72.298039 | 71.677474 | 72.606813 | 0.095639 |
| 4 | 8 | moe | 60.333970 | 60.316518 | 60.097056 | 60.613143 | 0.042449 |
| 5 | 56 | moe | 18.746819 | 18.715578 | 18.193598 | 19.401242 | 0.164911 |
| 6 | 59 | moe | 18.746449 | 18.683487 | 18.496772 | 19.021670 | 0.053469 |
| 7 | 71 | moe | 18.728585 | 18.734148 | 18.643696 | 18.855571 | 0.004897 |
| 8 | 45 | moe | 18.726457 | 18.633371 | 18.460055 | 19.288805 | 0.072206 |
| 9 | 57 | moe | 18.704145 | 18.788298 | 18.244783 | 18.977942 | 0.075072 |
| 10 | 51 | moe | 18.702674 | 18.645940 | 18.086680 | 19.314260 | 0.118142 |

## Cleanup hypothesis

Warm MoE observations always recorded [24] transient releases and [24] routed matrix misses. Residual per release had mean 0.796988 s and range 0.748692–2.525548 s.

Pearson correlation is undefined because both candidate predictors are constant within the relevant warm MoE population. Including layers 0–2 would confound different architectures. Existing data therefore cannot isolate cleanup cost or support a causal cleanup claim; layer 8 has the same release count but a much larger residual.

## GGUF trunk inventory

The catalog contains 1353 trunk tensors and excludes 456 routed/shared expert matrices. Total logical trunk storage is 12.549 GiB compressed and 61.675 GiB decoded f32.

### By trunk group

| Group | Tensors | Compressed GiB | Decoded f32 GiB | Row preads/token | Bulk reads/token |
| --- | ---: | ---: | ---: | ---: | ---: |
| attention_mla | 1027 | 10.565 | 51.324 | 5870016 | 632 |
| embedding | 1 | 0.499 | 3.545 | 1 | 1 |
| other_trunk | 13 | 0.538 | 2.813 | 92160 | 9 |
| output_head | 2 | 0.499 | 3.545 | 154880 | 2 |
| router_norms | 310 | 0.449 | 0.449 | 19456 | 310 |

### By quantization

| Quantization | Tensors | Compressed GiB | Decoded f32 GiB | Requested GiB/token | Row preads/token |
| --- | ---: | ---: | ---: | ---: | ---: |
| F32 | 709 | 0.508 | 0.508 | 0.450 | 19456 |
| Q4_K | 2 | 0.997 | 7.090 | 0.499 | 154881 |
| Q5_K | 162 | 5.946 | 34.594 | 5.946 | 712704 |
| Q6_K | 5 | 0.260 | 1.266 | 0.260 | 26624 |
| Q8_0 | 475 | 4.839 | 18.218 | 4.047 | 5222848 |

Every tensor's layer, semantic role, name, quantization, dimensions, bytes, touch contract, and residency classification is retained in the dedicated machine-readable inventory JSON. Indexer tensors are untouched in the frozen short context; nextn tensors are outside the runner.

## Logical trunk residency budgets

The observed peak RSS already includes actual shared-expert residency. Projections add each option to that peak, retain a 24 GiB safety reserve, and require another 4 GiB margin before calling an option a safe fixture candidate. They do not model MLX allocator overhead or fragmentation.

| Option | Logical GiB | Projected headroom GiB | Margin after 24 GiB reserve | Disposition |
| --- | ---: | ---: | ---: | --- |
| A compressed_all_trunk_residency | 12.549 | 25.852 | 1.852 | nominal_only_not_recommended_without_allocator_measurement |
| B decoded_f32_all_trunk_residency | 61.675 | -23.274 | -47.274 | unsafe_exceeds_24_gib_reserve |
| C decoded_attention_mla_only_residency | 51.324 | -12.922 | -36.922 | unsafe_exceeds_24_gib_reserve |
| D decoded_output_head_only_residency | 3.545 | 34.856 | 10.856 | fits_logical_budget_with_conservative_margin |
| E decoded_hot_subset_candidate_output_head_plus_router_norms | 3.994 | 34.407 | 10.407 | fits_logical_budget_with_conservative_margin |
| F compressed_all_trunk_plus_decoded_hot_subset | 16.543 | 21.858 | -2.142 | unsafe_exceeds_24_gib_reserve |

## Row-read request amplification

A normal short-context token plus next-token selection issues 6,136,513 row-level preads and 393 direct tensor reads for the trunk. A bulk path would use 954 total reads, a 6432.82× request-count reduction, while requesting the same 11.201 GiB of exercised checkpoint bytes. This is request arithmetic, not a speedup claim.

## Next two cheap experiments

1. **A — whole-matrix read only.** Use `blk.8.attn_output.weight` and complete MLA layer 8, retain scalar decoder order, require exact f32/output equality, and split storage, decode, buffer, build, matvec, total, RSS, and read-call counts.
2. **B — vectorized trunk decode.** Only after A passes. Select from the catalog touch-weighted order and A's measured boundary result; retain the scalar oracle and exact-bit gates. Do not assume Q6_K or Q8_0 wins before measurement.

M2 Max should own hash-bound local fixtures where permitted. M1 Ultra is required only for exact-checkpoint extraction or a later full correctness gate.

## Residency decision

The machine-readable decision table compares streaming, bulk scalar, bulk vector, compressed residency, decoded hot subset, decoded all-trunk, and hybrid options. Catalog arithmetic does not select a production strategy. Options D/E are safe logical fixture candidates; compressed-all is too close to the reserve to recommend without allocator measurements, and decoded-all/hybrid are unsafe.

## Feature 018 and next full run

Feature 018 remains provisionally `018-direct-quantized-metal-runtime`; no first kernel is selected. Another full M1 Ultra run is **not required now**. Run A and B at bounded boundaries first; a full-model run becomes justified only after a candidate optimization passes its exact/numerical fixture gates.
