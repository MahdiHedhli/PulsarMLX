# Production R11 Tier-B contract v1

This contract is frozen before the first production-MLX R11 output is
observed. It covers checkpoint-free final RMSNorm, the real-path Q4_K
output-head quantization, full logits, stable top-k ordering, and argmax.

The exact scaffold uses strict increasing-column f32 accumulation. Production
logits use the operand-conditioned forward-error evaluator inherited from
`f017-production-expert-tier-b-v1`; its row bounds are calculated only from
the frozen decoded matrix and normalized hidden state, never from candidate
output. Non-finite values, signed-zero mismatches, a row-bound violation, an
RMSE/cosine violation, nondeterministic repeats, fallback, backend error, or
lifecycle mismatch is `numerically_failed`.

R11 is the first model-token boundary where greedy selection is applicable.
Numerical qualification is therefore insufficient on its own: top-k IDs and
their order plus argmax must match exactly. A successful non-bit-identical
production result is `numerically_qualified_greedy_identical`; any top-k or
argmax divergence is `numerically_failed`. Ties use descending IEEE-754 total
order followed by lower vocabulary index.

The thresholds and classification rules in this version are immutable.
