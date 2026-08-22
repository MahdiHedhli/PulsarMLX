# F017 native bounded-P1 execution domain — final Claude Fable 5 review C1

Perform a fresh final independent adversarial review of committed branch `feat/017-rust-native-inference-runtime` at exact pushed head `d2d8c9af75e03f49d03f89dd6e3501b501d33be2`. Work only from the detached worktree provided. Git and exact-head CI are authoritative.

This is verification-only. Do not execute M1 Ultra P1, open/read the original checkpoint, run full-model real-checkpoint inference, create a live P1 authorization, or modify repository bytes. Retained D3.5 has already executed once under its reviewed consumer grants and must not be rerun.

Recompute all load-bearing hashes. Inspect exact-head CI run `32559658103`. Primary review packet: `docs/architecture/reviews/evidence/f017-native-bounded-p1-domain-final-review-package-v1.json`. Exact P1 admission contract expected SHA: `44b9416ff2c4e14ae3005e8df931443f38adb4ab49d5c173dcdf103a222a7dda`. Banked native executable expected SHA: `3894c4d12c93ac4c4f3584d2a9a41370c5074e7ef91402cfd8b16bf698c9c7ba`. Execution-code head: `22a76e4c248434a1827e81501607f93b0779352e`.

Attack the entire authority graph:

## Numerical/D0

- unjustified tolerance derivations, empirical data leakage, invalid prior-contract reuse, native self-output as correctness oracle, GPU nondeterminism hidden by grading, route structural exactness weakened to numeric similarity, stage mapping or serialization ambiguity;
- ensure D3.5 could only falsify a derivation, never set its tolerance; any tolerance repair must be a fresh D0 revision/fresh synthetic or pinned-fixture corpus/new review with triggering D3.5 output quarantined;
- confirm the D0v2 result was graded under predeclared rules and scope remains representative layer-3 only.

## Counters/lifecycle/RN1

- producer exists but invariant is meaningless, all-zero snapshot, stale snapshot, wrong scope, missing in-flight work, stale native-ready generation, logical/native free cancellation, foreign-attempt terminalization;
- rerun B1 missing-native-free and duplicate-free attacks and exact B2 source-first/no-eval/no-sync sequence where safe;
- ensure exclusive owned claim, durable ownership, exception cleanup only for this invocation's attempt, receipt-derived terminal counts, and mismatch fail-closed.

## Mock/producer/receipt

- mocked accounting, fake registration/teardown, fixture-authored receipt, cross-runtime evidence stitching, structurally different mock and real control paths, original checkpoint reachable from inert path;
- verify the committed producer is instantiable, owns one Rust/MLX process domain, emits the exact receipt itself, and stops after exactly one bounded token.

## Retention/D3.5

- native reuse without exact consumer-scoped grant, wrong artifact or SHA/size, missing per-read receipt, wrong stage vocabulary/serialization, proof/reference artifact relabeled as production, hidden checkpoint fallback;
- verify 89 authorized comparison reads, 34 canonical stages, result SHA `472a3085...`, acceptance SHA `9d4d2987...`, zero original-checkpoint reads, zero historical ledger delta;
- ensure D3.5 qualifies only representative layer-3 S0-to-S2 and does not directly qualify the remaining 79-layer full forward. The remainder relies on F016 structural lineage plus D0 generalized per-stage semantics pending the one real P1.

## Accounting/authority

- historical master ledger 175 ignored, duplicate native master, page fault confused with tensor-authority consumption, manually entered delta, incomplete six-shard/1809-tensor identity, alternate checkpoint, unbound runtime/binary, stale remote parity;
- verify exact MLX 0.31.2/MLX-C 0.6.0/dylib/rpath/M1 Ultra/thread/toolchain bindings and runtime drift rejection before attempt-start.

## P1 contract/human boundary

- non-instantiable binding, placeholder executable, absent counter producer, replay, concurrent claim, retry/resume/continuation/second token, missing mandatory stop, validation-generated live authorization, human choices beyond one yes/no authorization decision.

Run verification-only mutations/tests as useful. Classify each finding using only `BLOCKING`, `NON_BLOCKING_REQUIRED`, or `DEFENSE_IN_DEPTH`, with stable ID, exact path/symbol, evidence, failure mode, required repair, and disposition. Both BLOCKING and NON_BLOCKING_REQUIRED prevent acceptance. Defense-in-depth may remain only with a precise non-weakening disposition and future bind point.

Return exactly one final verdict:

`F017_NATIVE_BOUNDED_P1_EXECUTION_DOMAIN: ACCEPTED`

or

`REJECT`

Also state exactly:

`RETAINED_QUALIFICATION: MIXED_D0_V2_CLASS/PASS` or the evidenced correction;

`REAL_M1_ULTRA_P1_EXECUTED_DURING_REVIEW: NO`;

`FULL_MODEL_REAL_CHECKPOINT_INFERENCE_EXECUTED_DURING_REVIEW: NO`;

`ORIGINAL_CHECKPOINT_READS_DURING_REVIEW: 0`;

`LIVE_P1_AUTHORIZATION_CREATED_DURING_REVIEW: NO`.
