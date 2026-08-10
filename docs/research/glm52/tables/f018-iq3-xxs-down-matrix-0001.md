# Feature 018 real IQ3_XXS routed-down matrix qualification

> One real selected-expert down matrix on one M1 Ultra; not a complete expert, layer, token, or production result.

- Source: `20c2be417d2e1a0c5b8877fee796b3a2551aaac3` (clean)
- Raw SHA-256: `153a737a83befda96a909331803c184373c909eb3fc4c40f900384c60d79b682`
- Tensor: `blk.3.ffn_down_exps.weight`; layer/expert: `3` / `15`
- Shape: `[6144, 2048]`; packed bytes: `4816896`; quantization: `IQ3_XXS`
- Classification: `numerically_qualified_greedy_identical`; exact f32 bits: `false`
- Elementwise/signed-zero mismatches: `0` / `0`
- CPU fallbacks: `0`; complete f32 Metal weight materialization: `0` bytes

| Boundary/component | Median (s) |
| --- | ---: |
| Optimized reference storage | 0.000531396 |
| Optimized reference decode | 0.115301125 |
| Optimized reference contiguous buffer | 0.000046792 |
| Optimized reference MLX build/eval | 0.004864813 |
| Optimized reference MLX matvec | 0.001963688 |
| Optimized reference total | 0.123234876 |
| Strict direct Metal synchronized total | 0.000610605 |
| Strict direct Metal kernel | 0.000355083 |
| Strict direct Metal synchronization | 0.000583084 |

The same-boundary median ratio is `201.824×` in favor of the strict direct candidate. This does not predict complete-expert or token performance.
