# Feature 017 production R10 Tier-B contract v1

Status: **frozen before production R10 execution**.

This contract composes the already-frozen R9 and expert contracts for the
checkpoint-free complete MoE layer fixture. The independent oracle and
`f017-r10-complete-layer-exact-v1` scaffold remain exact semantic truth.

Production must preserve the exact selected expert IDs and lower-ID tie-break.
Routing weights may differ by at most `1e-5`. Every native projection must pass
the existing operand-conditioned per-matvec rule. Composed intermediates have
fixed maximum absolute/RMSE envelopes of `2^-6`/`2^-7` with cosine at least
`0.9999`; the final layer output has fixed `2^-4`/`2^-5` envelopes with cosine
at least `0.999`.

These power-of-two limits were frozen before candidate execution for one R9
attention residual, post-attention RMSNorm, one router projection, 27 expert
projections, f32 SwiGLU, f64 routing/aggregation, and the final f32 residual.
They are not inferred from candidate output and may not be widened in place.

Ten candidate repetitions must be bit-deterministic. Signed-zero and non-finite
violations, any routing-ID change, fallback/reference dispatch, backend error,
or lifecycle mismatch fail closed. The contract is pending independent
adversarial numerical review and admits no checkpoint or downstream gate.
