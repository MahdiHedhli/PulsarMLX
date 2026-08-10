# Feature 018 complete layer-3 gate

> One real layer-3 MLA plus top-8/shared MoE boundary; not a 79-layer stack or token-generation result.

- Source: `f8108fa19c0725e4afa653a917060d66d0619904` (clean)
- Raw SHA-256: `34a87b9c8ce232d6bbf9d43453f78057e83ff7bdca968c9a0c6bee420e91c0ca`
- Checkpoint set: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`
- Input token: `9703`; midpoint SHA-256: `7a19b425ae8bdf0009c84daa61c80fb054bffdf5fa0f3f2291d5af87cc7832aa`
- Top-8 route: `[15, 177, 233, 41, 166, 26, 10, 152]`
- Current reference matches committed layer-3 evidence: `true`
- Classification: `numerically_qualified_greedy_identical`; tolerance mismatches: `0`; max absolute error: `9.31322575e-09`

| Boundary/component | Median (s) |
| --- | ---: |
| Current attention/MLA | 0.759479604 |
| Current MoE | 1.666744542 |
| Current complete layer | 2.430633396 |
| Candidate attention/MLA | 0.757741958 |
| Candidate MoE | 0.902940687 |
| Candidate direct routed IQ2 | 0.027259063 |
| Candidate routed IQ3 down decode | 0.642490292 |
| Candidate complete layer | 1.688661895 |

The candidate reduces this bounded complete-layer median by `0.741971501` s (`30.5%`), from `2.430633396` s to `1.688661895` s. This is material for the frozen Feature 018 P1 admission decision.

Attention/MLA and IQ3 down remain reference paths. The result does not establish full-stack or user-visible latency improvement.
