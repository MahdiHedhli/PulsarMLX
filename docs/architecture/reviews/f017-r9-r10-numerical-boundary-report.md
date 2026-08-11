# PulsarMLX F017 R9/R10 Numerical Boundary Report

## Executive result

Checkpoint-free R9 and R10 pass their precommitted numerical and lifecycle
gates. R9 exercises the reduced one-token GLM-5.2 MLA path plus independent DSA
selection/state semantics. R10 composes that production attention result with
post-attention RMSNorm, GLM sigmoid+bias top-8 routing, eight routed experts,
one shared expert, deterministic aggregation, and the final residual.

The adversarial numerical review accepted the underlying evidence with one
required classification/applicability repair. The resulting R9/R10 change is
semantic tightening, not vocabulary-only: internal selection or routing
divergence now fails numerically. R9 and R10 remain numerically qualified with
model-token greedy selection not applicable.
No checkpoint was accessed, no M1 model-time boundary was admitted, and no
Feature 018 kernel or output-head residency path was included.

## Source and fixtures

- starting SHA: `cab7479bea4e6686b9dde48a093f1fba77e27d38`
- R9 production source: `43569b6920972e83155bfd1f1928d597ab7e9593`
- R10 production source: `c0354f954f2f92cb7c63f05dbb4c0a6332a555ad`
- R9 fixture: `f017-r9-mla-dsa-q8-0-v1`
- R10 fixture: `f017-r10-complete-layer-q8-0-v1`
- exact scaffolds: `f017-r9-mla-dsa-exact-v1`,
  `f017-r10-complete-layer-exact-v1`
- historical contracts: `f017-production-r9-tier-b-v1`,
  `f017-production-r10-tier-b-v1`
- current evidence contracts: `f017-production-r9-tier-b-v2`,
  `f017-production-r10-tier-b-v2`

Each independent Python/NumPy fixture was committed before production
execution and transports floating-point truth as canonical IEEE-754 bytes with
hashes. Neither generator imports Rust, MLX, candidate code, nor checkpoint
content.

## R9 MLA/DSA

The fixture covers input RMSNorm, q low-rank projection and normalization,
q nope/rope split, q and key rotary application, compact KV latent state,
attention scores, range-fill selection, softmax, value projection, attention
output projection, and residual add. Every exact-scaffold intermediate is
bit-identical to the independent oracle.

P1-sized short context uses DSA `range_fill` because the visible position count
is below the architecture's 2,048 indexer top-k. A separate independent DSA
fixture validates visible masking, stable lower-position tie order, selected
positions `[7, 8, 11, 4]`, and state append/update. This is not evidence that
the full long-context real-checkpoint indexer has run.

Production R9 completed ten bit-deterministic repeats:

| Measure | Result |
|---|---:|
| Native matvec dispatches | 60 |
| Unexpected fallback / backend errors | 0 / 0 |
| Maximum absolute error | 1.430511474609375e-6 |
| Maximum RMSE | 4.6239814120400004e-7 |
| Minimum cosine similarity | 0.9999999999999575 |
| Ten-repeat production wall | 0.028539541 s |

Lifecycle reconciled at 120/120 managed arrays, 60/60 derived arrays, 120
callbacks, 1/1 owned streams, no active context, and zero in-flight work.

## R10 complete layer

The independent R10 oracle freezes exact selected IDs
`[2, 4, 10, 7, 5, 1, 8, 6]`. The exact scaffold is bit-identical at the router,
each expert intermediate, aggregation, and final output. The production runner
executes R9 first and passes its candidate attention residual directly into the
R10 branch; the test does not substitute the frozen attention output after the
native branch begins.

Ten complete-layer production repeats classified
`numerically_qualified_greedy_not_applicable`. The exact expert routing IDs
remain separately recorded architecture evidence:

| Measure | Result |
|---|---:|
| Native matvec dispatches | 340 |
| Explicit-reference dispatches | 0 |
| Unexpected fallback / backend errors | 0 / 0 |
| Routing-weight maximum absolute error | 1.7861710055466773e-8 |
| R9 output maximum absolute error | 2.384185791015625e-7 |
| R10 f32 maximum absolute error | 2.384185791015625e-7 |
| R10 maximum RMSE | 9.872019290924072e-8 |
| R10 minimum cosine similarity | 0.9999999999999236 |
| Ten-repeat complete-layer wall | 0.188197084 s |

Bounded timing attribution for those ten repeats:

| Component | Seconds |
|---|---:|
| Attention/MLA | 0.039669918 |
| MoE branch | 0.148344500 |
| Import | 0.006393003 |
| Compute/synchronize | 0.160048345 |
| Router projection | 0.006864459 |
| Routed expert projections | 0.109587429 |
| Shared expert projections | 0.015469923 |
| CPU norm/activation/routing/aggregation/residual residual | 0.021755736 |

Storage and decoder time are zero by construction for this decoded,
checkpoint-free fixture. These small-fixture timings provide attribution only;
they are not model-performance claims.

Lifecycle reconciled at 680/680 managed arrays, 340/340 derived arrays, 680
callbacks, 1/1 owned streams, no active context, no stale generations, and zero
in-flight work.

## Dispatch and fail-closed behavior

Every MLX projection independently passed the existing operand-conditioned
matvec contract. Production mode cannot dispatch the exact scaffold or explicit
reference path. Changed expert IDs, missing operations, contract violations,
backend errors, fallback, and lifecycle imbalance are hard failures.

## Evidence

- R9: `docs/architecture/reviews/evidence/f017-r9-mla-dsa-production-v1.json`
- R10: `docs/architecture/reviews/evidence/f017-r10-complete-layer-production-v1.json`
- R9 result note: `docs/architecture/reviews/f017-r9-mla-dsa-result.md`
- frozen contracts under `specs/017-rust-native-inference-runtime/contracts/`

## Review and next gate

The R7/R8 adversarial numerical review accepted the numerical evidence with a
required machine-readable repair. R7 received an explicit vocabulary
amendment. R9/R10 moved to v2 because their divergence dispositions were
tightened from qualified-divergent to hard numerical failure under their
immutable-version policies. No threshold, metric, oracle value, fixture value,
or production output changed.

T017-132 is complete and its numerical inheritance cleared when remediation
head `bc5922626df9eaed8d1e843d021b268ecf50579d` passed both jobs in GitHub
Actions run `31521791761`. The exact next checkpoint-free gate is R11/R12:
independent final norm/logits/top-k followed by the tiny actual-runner
end-to-end fixture. No real checkpoint, P1 command, or M1 model time is admitted.
