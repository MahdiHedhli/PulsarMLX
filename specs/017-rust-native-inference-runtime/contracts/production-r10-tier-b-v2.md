# Feature 017 production R10 Tier-B contract v2

Status: **reviewed semantic tightening of immutable v1**. This contract
supersedes `f017-production-r10-tier-b-v1` and inherits
`f017-production-r9-tier-b-v2`. Both historical v1 contracts remain
byte-for-byte preserved.

The scope, oracle, exact scaffold, required repeats, router thresholds,
intermediate/final numerical thresholds, exact requirements, and retuning
policy are unchanged from v1. The banked R10 candidate output and metrics
satisfy both versions, so no numerical rerun is required.

## Semantic tightening

- A passing production result is
  `numerically_qualified_greedy_not_applicable` because R10 defines no
  model-token top-k or argmax decision.
- Exact routed expert IDs remain separate architecture evidence.
- Any `routing_divergence` is `numerically_failed`; it is not a qualified
  greedy divergence.
- `golden_identical` remains available for a bit-identical production result.

This is a failure-semantics tightening, not numerical retuning. Every numeric
bound and every observed output remains unchanged.
