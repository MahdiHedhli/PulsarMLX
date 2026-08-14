# F017 Routing-Contract v3 Internal Semantic/Numerical Review

## Scope and identities

- Starting head: `b3b0ca39961fbe9d770b58fd23c6e06b21265f8d`
- Formula freeze commit: `e603a84ae78cbc9d3b8b2943d7d0ddf91e31d983`
- Final contract freeze commit: `9d133286c727db33fe716055dc9d48d77e8453ce`
- Contract SHA-256: `befbf30f85e12b779e7d5c778f337a5f7d6019a15805e04805a24e4903ea3969`
- Real checkpoint payload access: `0`
- Real-payload ledger: `57` (unchanged)

## Review

1. Runtime semantics: GO. IDs, weights, and expert pointers retain selected-slot association. Rank controls the current serial f32 reduction order but no rank-indexed model coefficient, cache rule, capacity rule, shared-expert rule, or residual rule was found.
2. Permutation proof: GO. Joint permutation of unique atomic `(expert_id, weight)` records preserves the exact finite weighted sum. Independent ID/weight permutation is rejected.
3. Equivalence taxonomy: GO. Mathematical and reference-model semantic equivalence are separated from bounded f32 equivalence and non-required bit identity.
4. Atomic representation and serialization: GO. Eight unique records serialize by expert ID as LE `u16` plus LE binary64; rank bytes remain a separate diagnostic.
5. Per-expert weight contract: GO after required fix. The implementation now enforces both the outward propagated interval and inherited R10 caps (`1e-5` mathematical, `5e-6` H=2).
6. Accumulation: GO. Production rank-order reduction remains unchanged. Any alternative observed order must be disclosed and bounded by `2*gamma_7*sum(abs(term))+14*min_subnormal`, then satisfy inherited R10 complete-layer gates.
7. Pre-observation independence: GO. Formulas, thresholds, serialization, H=2, and PASS conjunction were frozen in commit `e603a84a` before the retrospective artifact. Later amendments only made tests CI-portable and aligned code to the already-frozen R10 cap.
8. Fixture-1 falsifier: GO. Membership is mathematically stable (`S=1.2497550469932908`) but lacks H=2; rank remains an unstable diagnostic; no candidate layer execution is claimed.
9. Historical immutability: GO. v1 and v2 hashes and conclusions are unchanged.
10. Representative target: GO. A future fixture must satisfy exact membership, all ID-keyed weights, H=2, deterministic repeats, and the full-layer numerical contract. Fixture 1 remains stress evidence.
11. Dense-prefix fallback: GO. Layers 0-2 are explicitly characterized as a future three-layer capture boundary, not disguised as fixture generation.
12. False-pass suite: GO. Duplicate/missing experts, misassociated/out-of-bound weights, non-finites, hidden rank policy, accumulation failure, and semantic/rank serialization confusion fail closed.

No unresolved model-semantic rank dependency, unbounded reduction-order effect, historical false-PASS, or real-access dependency was found.

## Verdict

`GO FOR ROUTING-CONTRACT V3 ADVERSARIAL REVIEW`

This verdict authorizes review only. Q6_K, M1-F, and P1 remain blocked.
