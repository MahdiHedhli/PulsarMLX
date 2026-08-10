# Feature 018 top-8 plus shared MoE gate

> One real layer-3 MoE boundary only; routed IQ2_XXS gate/up is direct Metal while routed down and all shared-expert projections remain on qualified reference paths.

- Source: `687c82ad06e981bba81f95bf2e48684f08654efa` (clean)
- Raw SHA-256: `b9da7d3804b7ce42fd458c9c8d161eca4aaf218a0d93aff90a98fd5ba98d2516`
- Checkpoint set: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`
- Top-8 route: `[15, 177, 10, 233, 166, 41, 152, 26]`; shared expert: `0`
- Current reference hash matches committed Feature 016 evidence: `true`
- Classification: `numerically_qualified_greedy_identical`; tolerance mismatches: `0`; max absolute error: `5.58793545e-09`
- Direct worker process-first: `16` matrices, `16` reads, `51904512` bytes, `14` bounded slot evictions.

| Component | Median (s) |
| --- | ---: |
| Current decode | 1.363795207 |
| Current MLX build/eval | 0.119387416 |
| Current MLX matvec | 0.086335207 |
| Current total | 1.701675000 |
| Direct routed IQ2 storage | 0.005596478 |
| Direct routed IQ2 GPU interval | 0.016610750 |
| Direct routed IQ2 synchronized total | 0.026925001 |
| Reference routed IQ3 down decode | 0.641837730 |
| Reference routed IQ3 down MLX build | 0.041121603 |
| Reference routed IQ3 down matvec | 0.029870938 |
| Router | 0.049063291 |
| Shared reference expert | 0.003776188 |
| Direct candidate total | 0.895944979 |

For this bounded top-8 plus shared block, the optimized-reference median is `1.701675000` s and the candidate median is `0.895944979` s (ratio `1.90×`; absolute difference `0.805730022` s).

The two-slot worker intentionally rereads routed gate/up slabs at this rung; it proves bounded lifecycle behavior, not a routed-residency policy. This is not a complete-layer or model speedup claim.
