# Feature 018 synthetic IQ3_XXS qualification

> Checkpoint-free packed-weight Metal GEMV evidence only; not a real matrix, expert, layer, token, or production result.

- Source: `9b4ca2849d2d8f507d76bb5e0ac48c073f27a390` (clean)
- Raw SHA-256: `4c22695cbd7e1380e2f1a237968ff995df2f2be1eb39d325e27e29ab320520e5`
- Fixture: `deterministic_synthetic_iq3_xxs_v1`; shape: `64 × 2048`; packed bytes: `50176`
- Classification: `numerically_qualified_greedy_identical`; exact f32 bits: `false`
- Deterministic repetitions: `100`; unique output hashes: `1`
- Strict Metal: fast math `false`, language `3.2`, `safe` / `precise`
- CPU fallbacks: `0`; complete f32 weight materialization: `0` bytes

| Metric | Value |
| --- | ---: |
| Median synchronized call (s) | 0.000454979 |
| Mean synchronized call (s) | 0.000471755 |
| Minimum synchronized call (s) | 0.000407166 |
| Maximum synchronized call (s) | 0.001061000 |
| Maximum absolute error | 0.0029296875 |
| Mean absolute error | 0.000443458557 |
| RMSE | 0.000710005232 |
| Cosine similarity | 1.000000000000 |
| Norm ratio | 0.999999967710 |
| Signed-zero mismatches | 0 |
