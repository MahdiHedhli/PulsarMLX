# Feature 016 P1 mixed-quant hotspot ranking

Derived from [`post-f016-inference-p1-trunk-q6-0001.json`](../raw/post-f016-inference-p1-trunk-q6-0001.json) at source commit `9b6ab666c9dc89eda9b2ddf284a9a2767516d87e`.
The rank uses measured time in the exercised P1 trace, not global tensor count.

| Rank | Format | Measured components (s) | Share | Loads | Reads | Matvecs | Bytes read |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | Q6_K | 472.156732 | 39.62% | 77 | 464896 | 154 | 794787840 |
| 2 | Q5_K | 226.858603 | 19.03% | 150 | 307200 | 300 | 1297612800 |
| 3 | IQ2_XXS | 136.516260 | 11.45% | 2368 | 2368 | 2368 | 7681867776 |
| 4 | IQ3_XXS | 103.763433 | 8.71% | 1136 | 1136 | 1136 | 5471993856 |
| 5 | Q2_K | 72.002142 | 6.04% | 32 | 65536 | 32 | 132120576 |
| 6 | IQ4_XS | 69.879037 | 5.86% | 64 | 393216 | 64 | 427819008 |
| 7 | IQ2_S | 68.690984 | 5.76% | 32 | 65536 | 32 | 128974848 |
| 8 | Q3_K | 40.775159 | 3.42% | 16 | 98304 | 16 | 86507520 |
| 9 | Q8_0 | 1.193782 | 0.10% | 1 | 6144 | 2 | 13369344 |

Measured components are storage read, dequantization, contiguous-buffer construction, MLX matrix build, and MLX matvec. Their sum is an instrumented attribution and must not be substituted for independently timed P1 wall time.

**Next exact-bit decoder candidate:** `Q6_K`.
