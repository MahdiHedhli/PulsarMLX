# PulsarMLX F017 Post-Recovery Summary-Integrity Closure Report

## Outcome

`READY FOR CHECKPOINT-FREE ROUTING-CONTRACT V3 RESEARCH`

Starting SHA: `7fa00341754a98ad10926c97695ec40070130a28`

Final implementation SHA: `36bff713e935ca466c3c32156ecaf164f180aa12`

Final documentation/evidence head: the commit containing this report; its
exact full SHA and final Apple CI run-to-SHA binding are recorded in the final
operator handoff to avoid a self-referential commit identity.

## Immutable recovery evidence

The historical raw recovery evidence remains unchanged:

- SHA-256: `f9422287cb98322d1412a6dd2397bb0f4a0d6538778aa587dddff7c5154acf2a`
- Immutable raw executor summary: preserved with the known defect.
- Authoritative summary: `derived_detail_summary`, recomputed from the retained
  1,984 membership plus 7 ordered-selected detail records.
- Ledger: unchanged at `57`.

## Reproduced defects

The old executor stopped its summary at the first failing ordered pair,
`166 → 78`, with safety factor approximately `0.6435667308079595`. The complete
surface’s true ordered minimum is `233 → 177`, with safety factor
`0.22551544432236478`.

The old executor also derived `route_set_stable` from the broader exact-order
classification, reporting `false` even though every membership pair passed.

## Corrected executor and validator

The executor now follows a store-then-derive flow:

1. retain all canonical pair records;
2. validate surface completeness, partition, relation, order, uniqueness,
   finiteness, positive bounds, and safety-factor arithmetic;
3. derive membership summary from all 1,984 membership records;
4. derive selected-order summary from all 7 adjacent records;
5. derive overall classifications from those independent summaries;
6. serialize and exact-assert the stored summary against a fresh derivation.

`route_set_stable` is now strictly membership-derived. The required mixed state
is represented exactly:

- Membership worst pair: `177 → 98`
- Membership minimum S: `1.2497550469932908`
- Membership stable: `true`
- Membership H=2: `false`
- Ordered worst pair: `233 → 177`
- Ordered minimum S: `0.22551544432236478`
- Ordered engineering S: `0.11275772216118239`
- Ordered stable: `false`
- Overall mathematical: `NOT_MATHEMATICALLY_STABLE`
- Overall engineering: `NO_ENGINEERING_HEADROOM`
- Route set stable: `true`
- Route order stable: `false`

## Negative mutation coverage

All six required fields fail independently when mutated:

1. minimum pair;
2. minimum mathematical factor;
3. minimum engineering factor;
4. route-set/membership stable boolean;
5. ordered stable boolean;
6. overall classification.

Eight additional cases also fail closed: wrong ordered minimum, wrong
engineering classification, wrong membership classification, stale count,
duplicate pair, missing pair, swapped surfaces, and first-failure substitution.

## Historical audit

The audit found no historical false PASS. M1-D and M1-E require complete repeat
equality and independent numerical qualification; M1-F0 requires complete
ten-repeat stage-and-selection identity. The v2 math helper’s related early
return was conservative for its boolean verdict and has been corrected to
return the true global minimum. The raw recovery’s overall failed
classification was never changed by the correction.

## Validation

- 41 targeted F017 v2/recovery/banker tests: passed.
- 524 full Python research/evidence tests: passed.
- 442 Rust tests discovered: all runnable tests passed; only previously
  declared environment-gated tests were ignored locally.
- Workspace check and full workspace test: passed.
- Summary validator, evidence/ledger validation, duplicate-key and privacy/path
  coverage, generated-artifact coverage, Spec Kit prerequisite checks,
  repository check script, and `git diff --check`: passed.
- Final-head Apple-native CI: required on the commit containing this report;
  exact run and head are supplied in the final operator handoff.

## Internal review

`GO FOR CHECKPOINT-FREE POST-RECOVERY RESEARCH`

## Scope accounting

- Real checkpoint access: `0`
- Ledger: `57`
- Q6_K: blocked
- M1-F: blocked
- P1: blocked

Exact next action: begin separately scoped, checkpoint-free routing-contract v3
research. No real-access or downstream execution authority is implied.
