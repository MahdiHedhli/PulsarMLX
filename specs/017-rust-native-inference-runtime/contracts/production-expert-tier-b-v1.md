# Feature 017 production expert Tier-B contract v1

## Status and scope

This contract is frozen before any production candidate is run on the Tier-B
stress fixtures. It applies only to the checkpoint-free Q8_0 complete-expert
boundary used by R7 and, if R7 qualifies, to each equivalent expert boundary
inside R8. It does not change the independent exact-f32 oracle or the
`f017-exact-f32-sequential-v1` qualification scaffold.

The production path is MLX C matmul. The exact oracle performs a separately
rounded f32 multiply followed by a separately rounded f32 add in strict
increasing-column order. A production reduction may use another valid f32
reduction order; only the down projection receives a numerical allowance in
this version of the contract.

## Mandatory exact boundaries

Gate, up, and the activated hidden vector must match the oracle's f32 bit
patterns exactly. Their decoded matrices and inputs must also match their
frozen hashes. Any mismatch at those boundaries is `numerically_failed`, even
if the final output would satisfy the down-projection error budget.

## Down-projection bound

For row `r` with dot width `n`, exact f32 matrix operands `w[r,c]`, and the
exact activated-hidden vector `x[c]`, define:

```text
u        = 2^-24
eta      = 2^-149
gamma(k) = (k*u) / (1-k*u)
L1[r]    = sum(c=0..n-1, abs(f64(w[r,c]) * f64(x[c])))
B[r]     = 2*gamma(2*n)*L1[r] + 4*n*eta
```

For the R7 width `n = 32`, `2*gamma(64)` is
`7.629423635191479e-6`. The factor of two compares two executions that can
each incur the standard separately-rounded multiply/add dot-product forward
error. The subnormal term is an additive floor for underflow-adjacent cases.
The formula is deliberately derived from operation count and operand
conditioning; it is not fitted to the observed `0.5` difference.

Every finite candidate element must satisfy `abs(actual[r] - expected[r]) <=
B[r]`. For a nonzero expected value, the corresponding relative bound is
`B[r] / abs(expected[r])`. The vector RMSE must not exceed
`sqrt(mean(B[r]^2))`.

Let `B2 = sqrt(sum(B[r]^2))` and `Y2 = ||expected||2`. When `Y2 > B2`, cosine
similarity must be at least `(Y2 - B2) / (Y2 + B2)`. When `Y2 <= B2`, cosine
is recorded but is not a meaningful qualification gate; the element and RMSE
bounds remain mandatory.

## Non-negotiable gates

- Candidate and oracle values must all be finite; NaN or infinity fails.
- Signed zero must match exactly.
- At least 10 identical executions must produce identical candidate f32 bits.
- No fallback, reference recovery, backend error, or unrecorded disposition is
  permitted.
- Shape, dtype, quantization, fixture identity, oracle-generator identity,
  scaffold version, backend version, and contract version must be recorded.
- A candidate may not partially write an output on malformed input.

## Behavioral classification

The repository classification names remain:

- `golden_identical`: every retained f32 boundary is bit-identical.
- `numerically_qualified_greedy_not_applicable`: Tier B passes at a boundary
  that defines no model-level greedy, top-k, or argmax decision.
- `numerically_qualified_greedy_identical`: Tier B passes and every applicable
  model-level top-k and argmax decision matches exactly.
- `numerically_qualified_greedy_divergent`: numerical bounds pass but an
  applicable behavioral decision differs. `golden_strict` rejects this;
  teacher-forced validation records the divergence and continues.
- `numerically_failed`: any exact, numerical, finite, signed-zero,
  determinism, identity, dispatch, or lifecycle gate fails.

R7 has no greedy decision, so it records greedy applicability as
`not_applicable` and uses `numerically_qualified_greedy_not_applicable` when
its Tier-B gates pass. R8 must additionally retain exact router IDs,
tie-breaking, routing weights, and aggregate behavior, but those internal
routing selections do not make model-token greedy selection applicable.
`numerically_qualified_greedy_identical` is reserved for a later boundary
that records exact model-level top-k and argmax identity evidence.

## Freeze boundary

This contract was authored from the exact-scaffold proof and the bounded
production attribution available at source `239bbca9`, before production MLX
was run on any new stress or expert fixture. Thresholds must not be edited in
response to candidate results. A future shape, quantization, activation, or
parallel backend requires a separately versioned contract.
