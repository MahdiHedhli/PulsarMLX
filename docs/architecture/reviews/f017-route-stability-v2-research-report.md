# PulsarMLX F017 Route-Stability v2 Research Report

## Outcome

`BLOCKED — ROUTE-STABILITY V2 RESEARCH`

The pairwise v2 candidate is conservative on the executed checkpoint-free test
surface, but the accepted M1-F0 evidence omitted the antecedents needed to apply
the tightened theorem to fixture 1 or to run a genuine v2 planning estimator.
No real checkpoint access occurred, and v1 remains authoritative.

## Identity and binding

- Starting SHA: `f70763efeabb38bfb9c1551d5a99470bc16a3466`
- Final SHA: the evidence-banking commit containing this report
- Estimator binding repair: immutable generator/ladder/environment/estimator
  amendment plus stale/mixed-binding negatives
- Extensible retention: arbitrary declared fields, including
  `rank_boundary_pairwise_bound`, `top1_top2_margin`, and
  `runner_up_token_margin`, must be retained for PASS
- v2 candidate contract SHA-256:
  `fd300f061307442c56af9ca3183f7485544ecb11752755074a330bb7b5f5f68c`

## v1 diagnosis

The random-normal support analysis is `MONTE_CARLO_ONLY`; elementary bounded
sigmoid and bias envelopes are too loose for a support theorem. Existing
checkpoint-free evidence shows realized/worst-case ratios:

| Boundary | Median | Maximum |
|---|---:|---:|
| R9 | 0.000091552734375 | 0.0003662109375 |
| R10 | 0.0000095367431640625 | 0.0000152587890625 |
| R11 | 0.00010415055433332724 | 0.0005736269220467603 |

These values diagnose pessimism only; they did not fit v2.

For expert 177, `B8=0.0033056307117125656` consists of inferred aggregate
router-logit error `0.013222522846819074` propagated by the global sigmoid
quarter bound (`0.0033056307117047684`) plus approximately
`7.797148343646754e-15` materialization/serialization. For expert 41,
`B9=0.0033937161438668565` analogously comes from logit error
`0.013574864575436241`, sigmoid contribution `0.0033937161438590603`, and
approximately `7.796280981908765e-15`. Bias contributes zero. The accepted
evidence did not retain the upstream attention-residual, RMSNorm radial,
RMSNorm non-radial, row-difference, and independent reduction split.

## Pairwise candidate

For `d_ij = score_i-score_j`, exact common bias cancels. The candidate decomposes
normalized-input error as `delta_y=lambda*y+r`, so the shared radial logit term
is bounded by `|lambda|*|l_i-l_j|`, while the non-radial term is bounded directly
with `(w_i-w_j) dot r`. Independent row reduction/materialization errors remain
additive. Each row's sigmoid uses the maximum derivative over a pre-candidate
logit interval. Outward binary64 rounding is required throughout.

Exact selected-set stability requires every selected/unselected oracle margin to
exceed its pairwise bound. Checking only rank 8/rank 9 is insufficient unless all
other pairs are formally dominated. Internal order among selected experts is not
required for set identity, but canonical ordered routing evidence may impose an
additional ordering contract later.

The candidate uses two classifications:

- mathematical stability: strict `S_pair > 1`;
- engineering headroom: `S_pair >= 2`, representing one additional complete
  modeled envelope for implementation/library drift.

This headroom policy is a review candidate, not an authorization rule.

## Independent validation

- Primary implementation SHA-256:
  `ab19c2a7f67a255d7489cc0526f0a2b2de56978c741ccf8651e69410a3f28a7c`
- Independent scalar implementation SHA-256:
  `b6af1097d3def7bc238f6cb6c89466fd0eb49df68742a108b74c931a102eb850`
- Randomized cases: `100000`
- Under-bound count: `0`
- Independent implementation mismatches: `0`
- Maximum observed actual/bound ratio: `0.9286201064709434`
- High-precision validator: 80-digit Decimal sampled checks, `0` failures

The suite includes exact/one-ULP/near ties, common radial and non-radial error,
identical/opposite rows, saturation, maximum sigmoid derivative, signed zero,
non-finite rejection, and a rank-10 crossing that defeats a rank-9-only check.

## Retrospective and planning

Because the necessary antecedents are absent, fixture 1 uses the fail-closed
fallback `B_pair=B8+B9=0.006699346855579422`. Tightening factor is `1.0`; its
v2-fallback safety factor remains `0.5609105150995247`. Its historical status is
unchanged: `UNSUITABLE UNDER V1`.

The 1,000,000-sample planning run is explicitly
`PAIRWISE_ANTECEDENTS_UNAVAILABLE_FALLBACK_V1`:

- mathematical rate: `0.012091`, Wilson 95% CI
  `[0.011878657507313808, 0.012307091042949784]`, P(any of 8)
  `0.09273212067172087`;
- engineering rate: `0.000148`, Wilson 95% CI
  `[0.0001260007770864396, 0.00017383952991006246]`, P(any of 8)
  `0.0011833868695070304`;
- median S: `0.15906717904159257`; p99 `1.042689744718181`; maximum
  `3.465878680226494`.

This does not establish random-normal viability under a fully instantiated v2.
The family remains numerical stress only and the frozen ladder was not executed.

## Fixture and policy research

Recommended checkpoint-free research candidate:
`correlated_low_rank_spectral_v1`, deterministic SHA-256
`d3c756f1d8c2b068ead3e91da2cf66927a6a86e08a6fa9b19d55e9618a0df1aa`.
Alternative: `block_ar1_rho_0_85_v1`, SHA-256
`48ccb5347c1de21c7542d46cf76a6a90ed3fb533a27a618c48a4081505f2d631`.
Neither is authorized or selected for real access.

The dual-fixture policy separates `REPRESENTATIVE_QUALIFICATION` from
`ADVERSARIAL_STRESS`. Fixture 1 remains a canonical tight-margin stress case.
Pre-admission stability is a `COST_AND_MEANINGFULNESS_GATE`; M1-F must still run
the candidate router and require exact selected-set equality.

## Route-independent tooling

Generic dispatch instrumentation now reconciles attention projections, router,
routed expert triplets, and shared expert triplets with native dispatch counts,
while tracking scaffold/reference/fallback/backend-error activity separately.
It does not freeze a route-specific M1-F budget. Metadata-only expert-166
gate/up/down slice derivation matches the banked catalog exactly.

## Review and stop state

- Internal review verdict: `NO-GO`
- Adversarial packet:
  `docs/architecture/reviews/f017-route-stability-v2-adversarial-packet.md`
- Adversarial packet SHA-256:
  `cd16683a35bfcaa388840b139e3dac1b265476991f98c4f9e3343b43aaf4dc9e`
- Final-head CI: required after evidence banking
- Real checkpoint access: `0`
- Frozen ladder execution: `false`
- Q6_K qualification: `false`
- M1-F execution: `false`
- P1: `blocked`

Exact next action: independent adversarial review of the mathematical candidate
and the antecedent-retention blocker. A future reviewed contract must retain the
pairwise antecedents before any new route evidence is evaluated; historical v1
evidence must not be reclassified.
