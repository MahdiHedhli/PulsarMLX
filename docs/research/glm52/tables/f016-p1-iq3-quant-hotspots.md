# Feature 016 P1 mixed-quant hotspot ranking

Derived from [`f016-inference-p1-iq3-0001.json`](../raw/f016-inference-p1-iq3-0001.json) at source commit `99751b9c3d8bf00a6b1af166f8f07adf9e90dd15`.
The rank uses measured time in the exercised P1 trace, not global tensor count.

| Rank | Format | Measured components (s) | Share | Loads | Reads | Matvecs | Bytes read |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | Q6_K | 468.856301 | 39.55% | 77 | 464896 | 154 | 794787840 |
| 2 | Q5_K | 225.731846 | 19.04% | 150 | 307200 | 300 | 1297612800 |
| 3 | IQ2_XXS | 137.908839 | 11.63% | 2368 | 2368 | 2368 | 7681867776 |
| 4 | IQ3_XXS | 101.107184 | 8.53% | 1136 | 1136 | 1136 | 5471993856 |
| 5 | Q2_K | 72.602034 | 6.12% | 32 | 65536 | 32 | 132120576 |
| 6 | IQ4_XS | 69.545278 | 5.87% | 64 | 393216 | 64 | 427819008 |
| 7 | IQ2_S | 67.549652 | 5.70% | 32 | 65536 | 32 | 128974848 |
| 8 | Q3_K | 41.028755 | 3.46% | 16 | 98304 | 16 | 86507520 |
| 9 | Q8_0 | 1.140167 | 0.10% | 1 | 6144 | 2 | 13369344 |

Measured components are storage read, dequantization, contiguous-buffer construction, MLX matrix build, and MLX matvec. Their sum is an instrumented attribution and must not be substituted for independently timed P1 wall time.

**Next exact-bit decoder candidate:** `Q6_K`.
