# F017 Route-Stability v2 Internal Numerical Review

## Scope

This review covers only checkpoint-free route-stability research. It does not
authorize a real M1-F0 ladder, Q6_K qualification, M1-F, or P1.

## Findings

1. The estimator is now cryptographically bound to the exact ladder generator,
   ladder artifact, environment, schema, and estimator implementation. Negative
   tests reject stale or mixed identities.
2. Arbitrary `required_analytical_retention` declarations fail PASS validation
   when omitted, including M1-G-like and P1-like fields.
3. The random-normal support analysis is correctly classified
   `MONTE_CARLO_ONLY`; the elementary sigmoid/bias envelope is too loose to be a
   support theorem.
4. Existing R9/R10/R11 data show large descriptive slack in prior worst-case
   bounds, but those observations were not used to fit v2.
5. The v1 B8/B9 final terms were decomposed exactly as far as retained evidence
   permits. The upstream radial, non-radial, row-difference, and reduction terms
   were not retained.
6. The candidate pairwise derivation correctly cancels exact bias, treats shared
   normalized-input error with `(w_i-w_j)`, isolates RMSNorm radial error, retains
   independent reduction errors, and uses interval-local sigmoid derivatives.
7. The full-set theorem checks every selected/unselected pair. It does not assume
   rank 8 versus rank 9 alone is sufficient.
8. Mathematical stability is separated from engineering headroom. The candidate
   requires strict `S_pair > 1` for the theorem and labels `S_pair >= 2` as
   engineering headroom covering one additional modeled envelope. Neither level
   is authoritative pending independent review.
9. Primary NumPy and separately structured scalar implementations agree on all
   executed cases. One hundred thousand randomized cases and deterministic edge
   cases produced zero under-bounds; sampled 80-digit Decimal checks passed.
10. Fixture 1 cannot be instantiated under the tightened formula from retained
    evidence. The fail-closed fallback exactly reproduces v1 and therefore does
    not change its historical disposition.
11. The one-million-sample v2 planning run consequently used the documented v1
    fallback. It does not establish random-normal viability under actual v2.
12. The correlated low-rank candidate and block-AR(1) alternative are
    deterministic, checkpoint-free research fixtures only. Neither is selected
    or authorized for real use.
13. Generic dispatch instrumentation reconciles conceptual operations with
    native dispatches without freezing a route-specific budget.
14. The expert-166 catalog-only gate/up/down slice cross-check matches the generic
    validator and performs no payload access.

## Blocking defect

The accepted M1-F0 evidence does not contain the router rows or exact row-pair
summaries, the RMSNorm radial/non-radial bounds, or independent router reduction
terms needed to evaluate the pairwise candidate for the real historical fixture.
Recovering those terms would require prohibited real checkpoint access. Inferring
them from final B8/B9 would not be a proof.

## Verdict

`NO-GO`

The v2 candidate is suitable for independent mathematical review, but it cannot
replace v1 or justify a real representative-fixture phase from the evidence
available in this sprint.
