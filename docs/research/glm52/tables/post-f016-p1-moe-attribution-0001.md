# Post-trunk P1 MoE attribution

Derived without model access from clean execution source `9b6ab666c9dc89eda9b2ddf284a9a2767516d87e`.

## Warm stack boundary

- Stack wall: 316.758671 s
- MoE-layer wall total: 310.185261 s
- Expert-cache attributed total: 248.615785 s
- Uninstrumented all-layer residual: 68.137373 s
- Routed loads per MoE layer: 24
- Shared decoded hits per MoE layer: 3

All warm read, decode, materialization, and matrix-build time belongs to routed matrices because all shared matrices hit the decoded cache. MLX matvec time combines routed and shared work and cannot be split from this schema.

## Top 20 routed expert sets

These are complete layer top-8 sets ranked by expert-cache attributed time. They are **not individual-expert hotspots**.

| Rank | Layer | Routed expert IDs | Gate/up/down quantization | Expert-cache attributed (s) | Complete layer wall (s) |
| ---: | ---: | --- | --- | ---: | ---: |
| 1 | 78 | `[211, 135, 221, 54, 224, 75, 230, 48]` | `{'gate': 'Q2_K', 'up': 'Q2_K', 'down': 'Q3_K'}` | 56.495180 | 57.323287 |
| 2 | 8 | `[31, 146, 203, 140, 204, 123, 88, 190]` | `{'gate': 'IQ2_S', 'up': 'IQ2_S', 'down': 'IQ4_XS'}` | 43.364126 | 45.141342 |
| 3 | 77 | `[191, 24, 190, 0, 90, 63, 148, 112]` | `{'gate': 'IQ2_XXS', 'up': 'IQ2_XXS', 'down': 'IQ4_XS'}` | 9.699788 | 10.507192 |
| 4 | 75 | `[246, 119, 196, 35, 125, 62, 252, 215]` | `{'gate': 'IQ2_XXS', 'up': 'IQ2_XXS', 'down': 'IQ4_XS'}` | 9.685278 | 10.468177 |
| 5 | 76 | `[178, 88, 220, 3, 12, 5, 102, 106]` | `{'gate': 'IQ2_XXS', 'up': 'IQ2_XXS', 'down': 'IQ4_XS'}` | 9.672812 | 10.533229 |
| 6 | 30 | `[188, 80, 208, 32, 230, 198, 90, 218]` | `{'gate': 'IQ2_XXS', 'up': 'IQ2_XXS', 'down': 'IQ3_XXS'}` | 1.747421 | 2.514091 |
| 7 | 68 | `[3, 243, 45, 203, 19, 218, 154, 254]` | `{'gate': 'IQ2_XXS', 'up': 'IQ2_XXS', 'down': 'IQ3_XXS'}` | 1.733349 | 2.662804 |
| 8 | 19 | `[134, 162, 120, 9, 253, 217, 35, 7]` | `{'gate': 'IQ2_XXS', 'up': 'IQ2_XXS', 'down': 'IQ3_XXS'}` | 1.732248 | 2.493027 |
| 9 | 36 | `[101, 38, 105, 187, 121, 63, 241, 224]` | `{'gate': 'IQ2_XXS', 'up': 'IQ2_XXS', 'down': 'IQ3_XXS'}` | 1.730613 | 2.497746 |
| 10 | 41 | `[25, 100, 109, 57, 84, 215, 177, 139]` | `{'gate': 'IQ2_XXS', 'up': 'IQ2_XXS', 'down': 'IQ3_XXS'}` | 1.727097 | 2.492595 |
| 11 | 47 | `[60, 184, 143, 75, 179, 16, 40, 246]` | `{'gate': 'IQ2_XXS', 'up': 'IQ2_XXS', 'down': 'IQ3_XXS'}` | 1.724652 | 2.487678 |
| 12 | 14 | `[106, 172, 91, 239, 168, 146, 253, 185]` | `{'gate': 'IQ2_XXS', 'up': 'IQ2_XXS', 'down': 'IQ3_XXS'}` | 1.723253 | 2.490847 |
| 13 | 46 | `[253, 179, 8, 96, 154, 173, 16, 124]` | `{'gate': 'IQ2_XXS', 'up': 'IQ2_XXS', 'down': 'IQ3_XXS'}` | 1.721390 | 2.488970 |
| 14 | 40 | `[226, 145, 146, 174, 220, 44, 234, 158]` | `{'gate': 'IQ2_XXS', 'up': 'IQ2_XXS', 'down': 'IQ3_XXS'}` | 1.720266 | 2.484870 |
| 15 | 24 | `[98, 161, 81, 195, 244, 241, 36, 252]` | `{'gate': 'IQ2_XXS', 'up': 'IQ2_XXS', 'down': 'IQ3_XXS'}` | 1.718767 | 2.473715 |
| 16 | 67 | `[182, 160, 210, 16, 101, 200, 242, 126]` | `{'gate': 'IQ2_XXS', 'up': 'IQ2_XXS', 'down': 'IQ3_XXS'}` | 1.717478 | 2.490602 |
| 17 | 26 | `[207, 57, 107, 177, 213, 50, 116, 82]` | `{'gate': 'IQ2_XXS', 'up': 'IQ2_XXS', 'down': 'IQ3_XXS'}` | 1.717478 | 2.475500 |
| 18 | 62 | `[52, 234, 140, 4, 45, 116, 213, 209]` | `{'gate': 'IQ2_XXS', 'up': 'IQ2_XXS', 'down': 'IQ3_XXS'}` | 1.717329 | 2.667294 |
| 19 | 63 | `[143, 130, 99, 147, 141, 181, 68, 248]` | `{'gate': 'IQ2_XXS', 'up': 'IQ2_XXS', 'down': 'IQ3_XXS'}` | 1.712799 | 2.683453 |
| 20 | 54 | `[47, 67, 168, 69, 60, 167, 79, 230]` | `{'gate': 'IQ2_XXS', 'up': 'IQ2_XXS', 'down': 'IQ3_XXS'}` | 1.711160 | 2.490669 |

## Run-total expert quantization

This table combines cold and warm expert-cache work. It is not a warm-only ranking.

| Rank | Quant | Components (s) | Decode (s) | Build (s) | Matvec (s) |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | Q6_K | 472.156732 | 447.481919 | 0.601880 | 1.457158 |
| 2 | Q5_K | 226.858603 | 184.639474 | 1.160630 | 2.432204 |
| 3 | IQ2_XXS | 136.516260 | 107.782914 | 11.620231 | 7.462467 |
| 4 | IQ3_XXS | 103.763433 | 86.478956 | 5.859061 | 4.676295 |
| 5 | Q2_K | 72.002142 | 63.373037 | 0.244767 | 0.281241 |
| 6 | IQ4_XS | 69.879037 | 52.693914 | 0.495386 | 0.249123 |
| 7 | IQ2_S | 68.690984 | 59.501310 | 0.220822 | 0.284012 |
| 8 | Q3_K | 40.775159 | 36.359746 | 0.131512 | 0.142352 |
| 9 | Q8_0 | 1.193782 | 0.890977 | 0.004910 | 0.030394 |

## Visibility limit

P1 does not time MLA versus MoE, individual experts, gate/up/down projections, shared versus routed matvec, SwiGLU, router, aggregation, or cleanup separately. The next bounded harness must add those timers before an individual hotspot or Feature 018 kernel can be selected.
