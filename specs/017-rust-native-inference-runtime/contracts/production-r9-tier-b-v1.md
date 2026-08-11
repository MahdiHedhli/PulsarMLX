# Feature 017 production R9 Tier-B contract v1

Status: **frozen before production R9 execution**. This contract does not
modify or supersede `f017-production-expert-tier-b-v1`.

## Scope

This contract applies only to the committed checkpoint-free, reduced-dimension
one-token GLM-5.2 MLA `range_fill` fixture and its separate deterministic DSA
selection/state fixture. It does not admit a real checkpoint, long-context DSA,
R10, R11, or P1.

The independent Python/NumPy oracle and
`f017-r9-mla-dsa-exact-v1` scaffold remain the semantic truth. The scaffold
must be bit-identical at every recorded f32 boundary.

## Production rules

Every production MLX projection is also checked at its own same-input boundary
with the already-frozen operand-conditioned formula from
`f017-production-expert-tier-b-v1`. This prevents a composed result from hiding
an excessive native matvec error.

The production composition then has these fixed envelopes:

| Boundary | Maximum absolute error | RMSE | Minimum cosine |
|---|---:|---:|---:|
| Recorded intermediate | 2^-8 (0.00390625) | 2^-9 (0.001953125) | 0.999999 |
| Final attention residual | 2^-7 (0.0078125) | 2^-8 (0.00390625) | 0.99999 |

The binary power-of-two envelopes were frozen from the six width-32
projection/reduction stages and the existing forward-error model before any
production R9 output was observed. They are deliberately wider than a single
matvec bound to cover composed normalization, RoPE, attention normalization,
and residual arithmetic, but remain narrow for this bounded fixture. A failure
does not authorize widening this version.

## Exact and fail-closed requirements

- DSA mode and selected positions are exact.
- The independent DSA mask, stable lower-position tie-break, and state update
  are exact.
- Signed-zero mismatches and non-finite values fail.
- Ten production repeats must have identical candidate f32 bits.
- Unexpected reference/scaffold fallback and backend errors are zero.
- Ownership, streams, singleton, and in-flight work reconcile after teardown.

Passing production R9 is classified
`numerically_qualified_greedy_not_applicable`; a bit-identical production
result may be `golden_identical`. R9 has no model-token greedy decision. DSA
and indexer selections remain separate exact architecture evidence, and their
drift is `numerically_failed`. Any numerical or lifecycle gate failure is also
`numerically_failed`.

The R7/R8 adversarial review accepted the numerical contract with a required
classification-vocabulary repair. That repair changes no threshold or
numerical value. Its fail-closed schema validation and CI passed, clearing this
contract for inheritance.
