# Routed-expert residency economics

> Golden-eight route-history analysis only; reuse counts are not measured latency savings.

Across eight adjacent intervals, **1892** of 4864 routed selections repeat at the same layer (**38.90%**). Reuse rises from 9.38% in the first interval to 53.12% in the last.

## Adjacent stack reuse

| Interval | Repeated experts | Fraction | Reusable decoded GiB |
| --- | ---: | ---: | ---: |
| 0→1 | 57 | 9.38% | 8.016 |
| 1→2 | 188 | 30.92% | 26.438 |
| 2→3 | 234 | 38.49% | 32.906 |
| 3→4 | 230 | 37.83% | 32.344 |
| 4→5 | 253 | 41.61% | 35.578 |
| 5→6 | 288 | 47.37% | 40.500 |
| 6→7 | 319 | 52.47% | 44.859 |
| 7→8 | 323 | 53.12% | 45.422 |

## Bounded policies

| Policy | Resident experts | Compressed GiB | Decoded GiB | Later expert hits | Later matrix hits |
| --- | ---: | ---: | ---: | ---: | ---: |
| transient_current_path | 0 | 0.000 | 0.000 | 0 | 0 |
| decoded_single_expert_hot_pin | 1 | 0.011 | 0.141 | 8 | 24 |
| decoded_per_layer_top1 | 76 | 0.811 | 10.688 | 428 | 1284 |
| compressed_per_layer_top1 | 76 | 0.811 | 0.000 | 428 | 0 |
| compressed_top1_plus_decoded_global_top8 | 76 | 0.811 | 1.125 | 428 | 171 |

## Top 20 routed units

| Rank | Layer | Expert | Appearances | Adjacent reuses | Decoded GiB | Gate/up/down quantization |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 64 | 183 | 9 | 8 | 0.141 | IQ2_XXS,IQ2_XXS,IQ3_XXS |
| 2 | 19 | 134 | 8 | 7 | 0.141 | IQ2_XXS,IQ2_XXS,IQ3_XXS |
| 3 | 28 | 156 | 8 | 7 | 0.141 | IQ2_XXS,IQ2_XXS,IQ3_XXS |
| 4 | 30 | 80 | 8 | 7 | 0.141 | IQ2_XXS,IQ2_XXS,IQ3_XXS |
| 5 | 35 | 208 | 8 | 7 | 0.141 | IQ2_XXS,IQ2_XXS,IQ3_XXS |
| 6 | 35 | 227 | 8 | 7 | 0.141 | IQ2_XXS,IQ2_XXS,IQ3_XXS |
| 7 | 37 | 115 | 8 | 7 | 0.141 | IQ2_XXS,IQ2_XXS,IQ3_XXS |
| 8 | 38 | 98 | 8 | 7 | 0.141 | IQ2_XXS,IQ2_XXS,IQ3_XXS |
| 9 | 41 | 177 | 8 | 7 | 0.141 | IQ2_XXS,IQ2_XXS,IQ3_XXS |
| 10 | 45 | 45 | 8 | 7 | 0.141 | IQ2_XXS,IQ2_XXS,IQ3_XXS |
| 11 | 52 | 7 | 8 | 7 | 0.141 | IQ2_XXS,IQ2_XXS,IQ3_XXS |
| 12 | 54 | 47 | 8 | 7 | 0.141 | IQ2_XXS,IQ2_XXS,IQ3_XXS |
| 13 | 55 | 0 | 8 | 7 | 0.141 | IQ2_XXS,IQ2_XXS,IQ3_XXS |
| 14 | 56 | 103 | 8 | 7 | 0.141 | IQ2_XXS,IQ2_XXS,IQ3_XXS |
| 15 | 57 | 44 | 8 | 7 | 0.141 | IQ2_XXS,IQ2_XXS,IQ3_XXS |
| 16 | 57 | 237 | 8 | 7 | 0.141 | IQ2_XXS,IQ2_XXS,IQ3_XXS |
| 17 | 58 | 36 | 8 | 7 | 0.141 | IQ2_XXS,IQ2_XXS,IQ3_XXS |
| 18 | 60 | 246 | 8 | 7 | 0.141 | IQ2_XXS,IQ2_XXS,IQ3_XXS |
| 19 | 62 | 234 | 8 | 7 | 0.141 | IQ2_XXS,IQ2_XXS,IQ3_XXS |
| 20 | 67 | 182 | 8 | 7 | 0.141 | IQ2_XXS,IQ2_XXS,IQ3_XXS |

Decoded top-one-per-layer residency is only a logical candidate and requires a real RSS/ownership gate. Compressed residency avoids reads but not decode or MLX build. The next bounded experiment measures one real expert lifecycle; Feature 018 remains unselected.
