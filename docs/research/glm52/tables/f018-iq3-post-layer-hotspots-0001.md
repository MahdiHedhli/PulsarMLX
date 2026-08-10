# Feature 018 post-IQ3 bounded hotspot profile

> Derived from one complete layer-3 and one layer-3 MoE population; not a full-stack profile.

- Complete-layer median: `0.950992354` s
- Attention median: `0.715570771` s
- MoE median: `0.207311958` s

| Rank | Component | Scope | Median (s) | Layer fraction |
| ---: | --- | --- | ---: | ---: |
| 1 | dense_trunk_dequant | complete_layer | 0.651695598 | 68.53% |
| 2 | moe_boundary | complete_layer | 0.207311958 | 21.80% |
| 3 | router | moe | 0.056043729 | 5.89% |
| 4 | dense_trunk_matvec | complete_layer | 0.041801989 | 4.40% |
| 5 | dense_trunk_build | complete_layer | 0.038241864 | 4.02% |
| 6 | layer_boundary_overhead | complete_layer | 0.028142167 | 2.96% |
| 7 | direct_iq2_gate_up_synchronized | moe | 0.027583458 | 2.90% |
| 8 | dense_trunk_storage | complete_layer | 0.013610856 | 1.43% |
| 9 | direct_iq3_down_synchronized | moe | 0.008303854 | 0.87% |
| 10 | shared_reference | moe | 0.002712333 | 0.29% |
| 11 | routed_aggregation | moe | 0.001902895 | 0.20% |
| 12 | routed_activation | moe | 0.001868980 | 0.20% |

No third direct-quantized kernel is selected. The one-layer profile places dense/trunk dequantization above either direct expert quantized component, so the clean optional P1 is admitted to establish the next full-stack ranking.
