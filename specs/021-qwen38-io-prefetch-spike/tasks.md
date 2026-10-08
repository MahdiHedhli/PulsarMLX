# Tasks: Qwen adapter contract steps 1–3

## Authorized bounded-wait continuation, 2026-10-08

The [resumable objective](bounded-wait-objective.md) preserves the full current task and separate publication/CI gates. It explicitly authorizes the previously deferred scheduler contract change; no real/backend execution follows.

- [X] T012 Record checkpoint, graph and authority in specs/021-qwen38-io-prefetch-spike/bounded-wait-objective.md.
- [X] T013 [US1] Write transient-demand, impossible-page, expiry/cancel, priority, identity and generated verified-file acceptance in scripts/research/tests/test_qwen38_bounded_wait.py.
- [X] T014 [US1] Implement bounded monotonic wait and original ticket/lease identity in scripts/research/qwen38_bounded_pager.py; update superseded contention assertions in scripts/research/tests/test_qwen38_bounded_pager.py.
- [X] T015 Run focused and applicable Qwen regression tests; retain exact source/result evidence in specs/021-qwen38-io-prefetch-spike/evidence/.
- [X] T016 Obtain permitted Gemini/Grok static review, triage/repair and preserve packet/report/disposition in specs/021-qwen38-io-prefetch-spike/evidence/.
- [ ] T017 Validate and checkpoint, recognize current push authority, normal-push and verify exact-commit CI in specs/021-qwen38-io-prefetch-spike/bounded-wait-objective.md.

Dependencies: T012 → T013 → T014 → T015 → T016 → T017. Complete every authorized node; historical tasks below remain complete.

Input: `spec.md`, `plan.md`, `production-adapter-next-gate.md`. Scope is the 2026-10-06 generated-fixture continuation, not the full runtime roadmap. Tests and local review were required for that initial slice. A later [independent static review and repair](evidence/adapter-contract-independent-review-2026-10-07.md) covers the additive code; real/backend execution remains separately gated.

## Setup and foundation

- [X] T001 Record authorized stories and additive module design in specs/021-qwen38-io-prefetch-spike/spec.md and plan.md; preserve shared feature selection and reviewed source.
- [X] T002 Create tiny generated bound fixture support in scripts/research/tests/qwen38_adapter_fixture.py, including cross-file and fixed text spans, immutable operation tables and independent injected observations.

## US1 — Bound session and owning lifetime (P1)

Independent test: verify fixed/expert/PLE bytes, binding changes, partial/failing reads, original-object completions, cancellation and cleanup on tiny files only.

- [X] T003 [US1] Write failing session/lifetime acceptance cases in scripts/research/tests/test_qwen38_adapter_contract.py.
- [X] T004 [US1] Implement bound synthetic session, fixed reads, ticket/borrow/completion identity, cancellation and cleanup in scripts/research/qwen38_adapter_session.py.

## US2 — Reservation and observation (P1)

Independent test: no allocation after budget/freshness failure; exported children stay counted; all explicit duplicate and scratch owners reserve before allocation.

- [X] T005 [US2] Write malformed, stale/replayed/future, pressure/swap, 48/40/16 boundary, fixed allowance, duplicate and retained-view cases in scripts/research/tests/test_qwen38_adapter_contract.py.
- [X] T006 [US2] Implement budget, owning ledger and independent injected observation contract in scripts/research/qwen38_adapter_memory.py; integrate into scripts/research/qwen38_adapter_session.py.

## US3 — Operation-bound trace (P1)

Independent test: replay actual synthetic route/PLE operations and exact spans; useful + late + wasted equals every admitted hint after use, eviction, cancellation or failure.

- [X] T007 [US3] Write interleaving, promotion/priority, forged operation/bytes/completion and waste-reconciliation cases in scripts/research/tests/test_qwen38_adapter_contract.py.
- [X] T008 [US3] Implement bounded operation tape and replay validator in scripts/research/qwen38_adapter_trace.py; bind emission in scripts/research/qwen38_adapter_session.py.

## Review and evidence

- [X] T009 Inspect final source against US1–US3 and review findings, repair concrete issues, and retain a hash-bound local source review in specs/021-qwen38-io-prefetch-spike/evidence/adapter-contract-source-review-2026-10-06.md.
- [X] T010 Run focused new acceptance and unchanged Qwen regression tests, retain exact commands/results and source hashes in specs/021-qwen38-io-prefetch-spike/evidence/adapter-contract-validation-2026-10-06.json.
- [X] T011 Update scope/status and remaining execution/review/publication gates in specs/021-qwen38-io-prefetch-spike/production-adapter-next-gate.md and plan.md; review diff, secrets and large files without pushing.

Dependencies: T001 → T002 → test tasks T003/T005/T007 → T006 → T008 → T004 integration → T009 → T010 → T011. US2 and US3 can be unit-tested independently but integrated acceptance requires US1. No parallel implementation workers are planned; the three module interfaces can be read in parallel. Implement the complete authorized slice, not only the US1 MVP. All tasks belong to the three stated stories or their foundation/evidence gates. Deferred steps 4–7 are not unchecked tasks in this slice.
