# Post-Feature-016 bounded trunk residency study

> One changed variable: matrix residency lifecycle. Each candidate ran in a fresh process with the same exact Q6_K decoder, activation, MLX matvec, and checkpoint.

- Evidence source: `bb6c9994199757f495d5545acbc849437f7eeb24` (clean: `true`)
- Checkpoint set SHA-256: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`
- Protocol: 3 warm-ups and 10 measured samples per candidate; OS page cache uncontrolled.

## One real Q6_K matrix lifecycle

| Candidate | Setup RSS delta (MiB) | Setup read (MiB) | Reuse storage (s) | Reuse decode (s) | Reuse build (s) | Matvec (s) | Cleanup (s) | Reuse total (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `transient` | 1.5 | 0.0 | 0.008247 | 1.327633 | 0.034896 | 0.018016 | 0.003401 | 1.389852 |
| `compressed_resident` | 159.1 | 78.8 | 0.000001 | 1.374997 | 0.034026 | 0.018143 | 0.003360 | 1.427976 |
| `decoded_hot` | 1557.2 | 78.8 | 0.000001 | 0.000000 | 0.000000 | 0.002872 | 0.003257 | 0.002910 |
| `hybrid_compressed_decoded_hot` | 1557.2 | 78.8 | 0.000001 | 0.000000 | 0.000000 | 0.002932 | 0.003248 | 0.002970 |

All candidates produced the same exact deterministic f32 output hash. RSS delta is process-local observed allocation, not logical tensor size or a general MLX allocator multiplier.

## Previously committed full-trunk logical budgets

| Option | Logical GiB | Admission disposition |
| --- | ---: | --- |
| A `compressed_all_trunk_residency` | 12.549 | `nominal_only_not_recommended_without_allocator_measurement` |
| B `decoded_f32_all_trunk_residency` | 61.675 | `unsafe_exceeds_24_gib_reserve` |
| C `decoded_attention_mla_only_residency` | 51.324 | `unsafe_exceeds_24_gib_reserve` |
| D `decoded_output_head_only_residency` | 3.545 | `fits_logical_budget_with_conservative_margin` |
| E `decoded_hot_subset_candidate_output_head_plus_router_norms` | 3.994 | `fits_logical_budget_with_conservative_margin` |
| F `compressed_all_trunk_plus_decoded_hot_subset` | 16.543 | `unsafe_exceeds_24_gib_reserve` |

Budget conclusion: only D and E are safe logical fixture candidates; this arithmetic does not choose a production residency strategy or account for MLX allocator fragmentation.

Decoded-hot residency removes repeated decode/build for admitted hot tensors, but the measured 1.56 GiB setup RSS delta for one 384 MiB decoded matrix makes allocator-aware admission mandatory. Compressed residency avoids only a roughly 8 ms warm read in this fixture and does not justify compressed-all residency by itself.

This is a representative matrix lifecycle result, not complete-layer, token, decoded-all admission, production cache, Rust, or Metal evidence.
