# Feature 017 R7 adversarial numerical review packet

> Review closeout addendum: the reviewer returned **GO WITH REQUIRED FIXES**.
> The numerical evidence, exact scaffold, attribution, Tier-B derivation,
> stress suite, R7/R8 results, lifecycle, and provenance were accepted. The
> required fix was a machine-readable classification/applicability mismatch;
> no numerical rerun or threshold change was requested. R7 records the fix in
> `production-expert-tier-b-v1-amendment-001.json`. R9/R10 moved to v2 because
> internal selection/routing divergence was semantically tightened to a hard
> numerical failure under their immutable-version policies. See
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

- R7: `numerically_qualified_greedy_not_applicable`; greedy applicability is
  `not_applicable` at the standalone expert boundary.
- R8: `numerically_qualified_greedy_not_applicable`; router IDs agree exactly,
  routing weights satisfy the frozen `1e-12` bound, all nine experts qualify,
  and routed/shared aggregation remains inside propagated bounds. Router IDs
  are internal architecture selections, not model-token greedy identity.
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

## Required-fix closeout

The reviewer found that the former
`numerically_qualified_greedy_identical` label contradicted
`greedy_applicability: not_applicable`. Schema version `1.2.0` adds
`numerically_qualified_greedy_not_applicable` and fails closed on inconsistent
classification, applicability, or missing top-k/argmax identity evidence.
R7/R8 were mechanically reclassified. R9/R10 preserve their original v1
contracts and bind current evidence to v2 contracts whose internal
selection/routing divergence is `numerically_failed`. The reconciliation
manifest proves that metrics, thresholds, fixtures, oracle data, output data,
fallback counts, and lifecycle counters are unchanged.

The authoritative audit artifacts are repository-relative:

- `specs/017-rust-native-inference-runtime/contracts/production-expert-tier-b-v1-amendment-001.json`
- `specs/017-rust-native-inference-runtime/contracts/production-r9-tier-b-v2.json`
- `specs/017-rust-native-inference-runtime/contracts/production-r10-tier-b-v2.json`
- `docs/architecture/reviews/evidence/f017-contract-version-reconciliation-v2.json`

GitHub Actions run
[`31528221838`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31528221838)
passed at versioning implementation head
`96783168026f70867999c975d3adb9536821bef9`. Both the workspace baseline and
pinned Apple-native job passed; the native adapter and exact/Tier-B R7-R10
ladder executed without an invalidating skip. This closes the R9/R10
contract-version audit item.

GitHub Actions run
[`31521791761`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31521791761)
passed both jobs at remediation head
`bc5922626df9eaed8d1e843d021b268ecf50579d`, including native R7-R10 tests
with no invalidating skip. The review blocker is resolved. This clears R9/R10
inheritance and R11/R12 checkpoint-free work only; it does not admit a real
checkpoint or P1.
