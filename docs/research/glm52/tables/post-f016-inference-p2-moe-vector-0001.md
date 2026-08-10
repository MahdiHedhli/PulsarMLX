# Post-MoE exact P2 profile

Exact `[9703,21615,220]` at clean source `c115c7f6f09fcdcfe13a11ca8d3b94940863b7ab`; no golden-eight rerun.

| Stack | Phase | Token | Stack (s) | Separate logits (s) | Expert storage (s) | Expert decode (s) | Expert build (s) | Expert matvec (s) | Uninstrumented residual (s) |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | prefill | 9703 | 921.235962 | 0.000000 | 10.649492 | 752.729661 | 11.190148 | 8.545507 | 80.166524 |
| 1 | decode | 21615 | 197.928826 | 89.246947 | 9.165052 | 103.146919 | 9.032754 | 8.096326 | 68.448357 |
| 2 | decode | 220 | 194.063845 | 76.430414 | 7.078381 | 103.904752 | 9.052198 | 6.768674 | 67.219210 |

Warm stack mean/median: **195.996335 / 195.996335 s** (two samples). Total evidence wall: **1479.009580 s**.

## Measured warm format opportunity

| Rank | Role | Quant | Matrix touches | Modeled decode (s) | Modeled build (s) | Modeled matvec (s) |
| ---: | --- | --- | ---: | ---: | ---: | ---: |
| 1 | routed gate/up | IQ2_XXS | 1184 | 55.750817 | 6.156314 | 3.462333 |
| 2 | routed down | IQ3_XXS | 568 | 43.125401 | 3.027591 | 2.408987 |
| 3 | routed gate/up | Q2_K | 16 | 2.377654 | 0.079576 | 0.058280 |
| 4 | routed down | IQ4_XS | 32 | 1.383195 | 0.163582 | 0.098976 |
| 5 | routed down | Q3_K | 8 | 1.101459 | 0.039709 | 0.029234 |
| 6 | routed gate/up | IQ2_S | 16 | 0.980619 | 0.083169 | 0.044533 |

The modeled decode sum is 104.719147 s versus 103.525836 s observed warm decode (1.15% relative difference). The model uses exact bounded per-format medians and catalog touches; it is not direct per-quant P2 telemetry.

Feature 018 can now use IQ2_XXS routed gate/up as its first candidate by largest measured absolute warm opportunity. This selects a candidate only; no Metal kernel was implemented. Feature 017 should prioritize exact whole-slab IQ2_XXS/IQ3_XXS decode, low-copy MLX handoff, and bounded route-aware residency.

Historical P2 wall ratio: 4.43x; historical warm-median ratio: 9.76x. Both are cross-commit observations.
