# Feature 018 complete routed-expert gate

> One real routed expert only: direct IQ2_XXS gate/up plus the existing qualified IQ3_XXS reference down path.

- Source: `0435ab363431d5a11ef50f27818451ae93fbdd45` (clean)
- Raw SHA-256: `b8c9e5945783f6722530ef92426ac8dd5e7c9ae35fc6a66a84d522a1c6b2e3b4`
- Checkpoint set: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`
- Layer/expert: `3` / `15`; selected top-8 route: `[15, 177, 10, 233, 166, 41, 152, 26]`
- Classification: `numerically_qualified_greedy_identical`; elementwise mismatches: `0`
- Max absolute error: `3.52883944e-10`; RMSE: `7.30354771e-11`; cosine: `0.999999999998`
- Rust worker: two stable page-aligned resident slots; process-first reads `2` / `6488064` bytes; warm hits `2` per sample; evictions `0`.

| Component | Median (s) |
| --- | ---: |
| Current storage read | 0.000562291 |
| Current decode | 0.204827791 |
| Current contiguous buffer | 0.000090396 |
| Current MLX build/eval | 0.015234209 |
| Current MLX matvec | 0.011426396 |
| Current total | 0.241911167 |
| Direct IQ2 gate/up storage (warm) | 0.000000000 |
| Direct IQ2 gate/up registration | 0.000050500 |
| Direct IQ2 gate/up GPU interval | 0.002083604 |
| Direct IQ2 gate/up synchronized total | 0.003356770 |
| Reference IQ3 down decode | 0.113225291 |
| Reference IQ3 down MLX build | 0.004987292 |
| Reference IQ3 down matvec | 0.003187771 |
| SwiGLU activation | 0.000219917 |
| Direct candidate total | 0.137712729 |

For this bounded expert, the current optimized-reference median is `0.241911167` s and the direct-IQ2 candidate median is `0.137712729` s (ratio `1.76×`; absolute difference `0.104198438` s).

The largest retained candidate component is the reference IQ3_XXS down decode. This result does not select or implement a second kernel and is not a layer/model speedup claim.
