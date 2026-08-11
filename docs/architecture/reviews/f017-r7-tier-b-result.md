# Feature 017 R7 Tier-B result

The original frozen R7 complete-expert fixture qualifies under the unchanged
`f017-production-expert-tier-b-v1` contract. Gate, up, and activated hidden
remain bit-identical. The production MLX down projection has 24 bit-different
elements, maximum absolute error `1.375`, RMSE `0.693598660294626`, and cosine
similarity `0.9999999999999881`.

The condition-aware contract's maximum row budget is `549.9749723910232`, its
vector RMSE bound is `517.7241872969238`, and its cosine minimum is
`0.999756577997848`. These comparatively broad theoretical bounds reflect the
large sum of absolute products in this synthetic expert, not a fitted
tolerance. The independent stress suite was already frozen before this run
and passed bit-exactly.

The stable repository classification is
`numerically_qualified_greedy_not_applicable`; greedy applicability at
standalone R7 is explicitly `not_applicable`. The run was deterministic across 10
executions, used no fallback or checkpoint, and reconciled all adapter
ownership and stream counters.

The machine-readable result is
`specs/017-rust-native-inference-runtime/fixtures/f017-r7-tier-b-result-v1.json`.
The production run used clean source
`5b701d16ce93964419380f4505c52e220584ec4d`.
