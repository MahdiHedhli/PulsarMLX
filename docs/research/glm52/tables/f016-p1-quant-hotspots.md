# Feature 016 P1 mixed-quant hotspot ranking

Derived from [`f016-inference-p1-vectorized-0001.json`](../raw/f016-inference-p1-vectorized-0001.json) at source commit `2de160facac21c92e71401870b04fea9984f4839`.
The rank uses measured time in the exercised P1 trace, not global tensor count.

| Rank | Format | Measured components (s) | Share | Loads | Reads | Matvecs | Bytes read |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | IQ3_XXS | 1791.413883 | 61.78% | 1136 | 6979584 | 1136 | 5471993856 |
| 2 | Q6_K | 475.307709 | 16.39% | 77 | 464896 | 154 | 794787840 |
| 3 | Q5_K | 225.687310 | 7.78% | 150 | 307200 | 300 | 1297612800 |
| 4 | IQ2_XXS | 153.768739 | 5.30% | 2368 | 2368 | 2368 | 7681867776 |
| 5 | Q2_K | 73.042359 | 2.52% | 32 | 65536 | 32 | 132120576 |
| 6 | IQ4_XS | 69.862592 | 2.41% | 64 | 393216 | 64 | 427819008 |
| 7 | IQ2_S | 67.970314 | 2.34% | 32 | 65536 | 32 | 128974848 |
| 8 | Q3_K | 41.295006 | 1.42% | 16 | 98304 | 16 | 86507520 |
| 9 | Q8_0 | 1.151897 | 0.04% | 1 | 6144 | 2 | 13369344 |

Measured components are storage read, dequantization, contiguous-buffer construction, MLX matrix build, and MLX matvec. Their sum is an instrumented attribution and must not be substituted for independently timed P1 wall time.

**Next exact-bit decoder candidate:** `IQ3_XXS`.
