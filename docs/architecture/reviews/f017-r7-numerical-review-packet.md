# Feature 017 R7 adversarial numerical review packet

> Downstream review addendum: checkpoint-free R9 MLA/DSA and R10 complete-layer
> evidence now also pass their separately frozen contracts. They remain pending
> this same adversarial numerical review and must be treated as exploratory if
> the reviewer rejects the R7/R8 foundation. See
> `docs/architecture/reviews/f017-r9-r10-numerical-boundary-report.md` and its
> linked machine-readable evidence. No contract threshold was changed.

## Review question

Is `f017-production-expert-tier-b-v1` principled, frozen independently, and
narrow enough that production R7 can qualify without weakening the exact
semantic oracle?

## Frozen original failure

The retained R7 fixture expected `427908.5` (`0x48d0f090`). Production MLX
returned `427909.0` (`0x48d0f0a0`): absolute delta `0.5`, relative delta
`1.1684741013557804e-6`, and the original classification
`FAIL_NUMERICAL_BEHAVIORAL`. The fixture was not regenerated.

## Exact semantic proof

`f017-exact-f32-sequential-v1` performs separate f32 multiply and add in
strict increasing-column order, with no FMA, reassociation, fast math,
vectorized/tiled reduction, parallel reduction, or MLX call. Across 10 repeats
it matches independent gate, up, SwiGLU, down, and complete-expert bits.

## Attribution

The production path is bit-identical through gate, up, and activated hidden.
The first divergence occurs in the MLX down matmul: 24/32 outputs differ,
maximum absolute error is `1.375`, RMSE is `0.693598660294626`, and cosine
similarity is `0.9999999999999881`. Five plausible CPU reduction orders did
not reproduce MLX exactly. The supported attribution is MLX down-matmul
arithmetic/reduction semantics; its undocumented reduction tree is not
claimed.

## Frozen Tier-B contract

The contract was committed at `8bfeb98c` before additional production expert
outputs. Gate, up, and activated hidden remain exact. For down row width `n`,
the absolute budget is:

`2 * gamma(2n) * sum(abs(weight_i * input_i)) + 4n * 2^-149`

It also requires condition-aware relative bounds, an RMSE bound derived from
row budgets, a conditional cosine minimum, no NaN/Inf, exact signed zero, at
least 10 deterministic repeats, no partial write, and fail-closed unexpected
fallback. The broad R7 maximum row budget (`549.9749723910232`) follows from
the synthetic fixture's sum of absolute products and was not fitted to the
observed `1.375` error.

## Independent stress

Nine independent public-safe fixtures were frozen before production runs.
They cover cancellation, alternating signs, dynamic range, large partial sums
with small residuals, near-zero and large outputs, denormal-adjacent values,
sign changes, shapes 1/2/4/8/32, and a near tie. All were bit-identical across
10 production repeats; the near-tie argmax agreed.

## Production classifications

- R7: `numerically_qualified_greedy_identical`; greedy applicability is
  `not_applicable` at the standalone expert boundary.
- R8: `numerically_qualified_greedy_identical`; router IDs agree exactly,
  routing weights satisfy the frozen `1e-12` bound, all nine experts qualify,
  and routed/shared aggregation remains inside propagated bounds.
- Both runs record zero fallback, deterministic repeats, reconciled lifecycle,
  and no checkpoint access.

## Transport incident retained for review

R8 oracle v1 encoded exact Python f64 values only as JSON decimals. Before
candidate execution, Rust reconstructed two routing weights one ULP higher.
The v1 fixture is retained as rejected evidence. V2 adds canonical
little-endian IEEE-754 bytes and hashes without changing the independent
mathematics. This is an evidence-transport correction, not threshold tuning.

## Source material

- `docs/architecture/reviews/f017-r7-original-mismatch.md`
- `docs/architecture/reviews/f017-r7-exact-scaffold.md`
- `docs/architecture/reviews/f017-r7-production-attribution.md`
- `specs/017-rust-native-inference-runtime/contracts/production-expert-tier-b-v1.json`
- `docs/architecture/reviews/f017-tier-b-stress-qualification.md`
- `docs/architecture/reviews/f017-r7-tier-b-result.md`
- `docs/architecture/reviews/f017-r8-top8-shared-result.md`

Independent adversarial review of this packet remains pending; its existence
must not be described as reviewer approval.
