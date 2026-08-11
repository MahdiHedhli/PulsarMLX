# Feature 017 production R9 Tier-B contract v2

Status: **reviewed semantic tightening of immutable v1**. This contract
supersedes `f017-production-r9-tier-b-v1` for current evidence bindings. The
historical v1 remains byte-for-byte preserved.

The scope, oracle, exact scaffold, required repeats, numerical thresholds,
operand-conditioned matvec rule, exact requirements, and retuning policy are
unchanged from v1. The observed R9 result also remains unchanged and satisfies
both versions, so no numerical rerun is required.

## Semantic tightening

- A passing production result is
  `numerically_qualified_greedy_not_applicable` because R9 defines no
  model-token top-k or argmax decision.
- Exact DSA/indexer selections remain separate architecture evidence.
- Any `selection_divergence` is `numerically_failed`; it is not a qualified
  greedy divergence.
- `golden_identical` remains available for a bit-identical production result.

This is a failure-semantics tightening, not numerical retuning. The fixed
intermediate and final error envelopes, deterministic-repeat requirement,
signed-zero rule, fallback/error gates, and lifecycle requirements are exactly
the v1 values.
