# F017 native bounded-P1 execution domain — final Claude Fable 5 review C2

Perform a fresh final independent correctness, authority, and execution-safety review of committed branch `feat/017-rust-native-inference-runtime` at exact pushed head `aeca5b08ae96f6bd97f507c81ae373e4b86f9e90`. Work only from the detached worktree provided. Git and exact-head CI are authoritative.

This is verification-only. Do not execute M1 Ultra P1, open/read the original checkpoint, run full-model real-checkpoint inference, create a live P1 authorization, rerun retained D3.5, or modify repository bytes.

Recompute all load-bearing hashes. Inspect exact-head CI run `32560783265`. Primary review packet: `docs/architecture/reviews/evidence/f017-native-bounded-p1-domain-final-review-package-v1.json`. Exact P1 contract SHA: `44b9416ff2c4e14ae3005e8df931443f38adb4ab49d5c173dcdf103a222a7dda`. Banked native executable SHA: `3894c4d12c93ac4c4f3584d2a9a41370c5074e7ef91402cfd8b16bf698c9c7ba`. Execution-code head: `22a76e4c248434a1827e81501607f93b0779352e`.

Cross-vendor evidence is committed on the branch tip outside the reviewed implementation tree. AGY Gemini 3.1 Pro High cycle 1 found two blocking CI omissions. Both were repaired at the reviewed head. Cycle 2 was a policy refusal and has no acceptance weight. Cycle 3 returned `NO_MATERIAL_DISAGREEMENT`, but the AGY wrapper recorded an internal find-timeout status after emitting its complete substantive verdict. Independently adjudicate the repaired implementation and do not treat cross-vendor agreement as a substitute for your own review.

Attack the entire authority graph:

## Numerical/D0

- tolerance derivations, empirical leakage, native self-output as correctness oracle, GPU nondeterminism, structural routing gates, stage mapping/serialization;
- D3.5 may falsify but cannot select or tune a threshold; any repair would require a fresh D0 revision and fresh corpus with triggering output quarantined;
- D3.5 scope is representative layer-3 only, with the remaining 79 layers dependent on F016 structural lineage plus generalized D0 semantics pending real P1.

## Counters/lifecycle/RN1

- live producer and meaningful invariant for every D1 field; all-zero/stale/wrong-scope/missing in-flight/stale-generation cases;
- B1 missing/duplicate native free and exact B2 source-first/no-eval/no-sync where safely verifiable;
- exclusive owned claim, durable ownership, exception cleanup limited to the attempt this invocation started, receipt-derived terminal counts, mismatch fail-closed.

## Mock/producer/receipt

- accounting/registration/teardown/snapshots/receipt/terminalization remain real while only tensor math is mocked;
- original checkpoint is structurally unreachable from inert execution;
- one Rust/MLX ownership domain, exact receipt emitter, exactly one bounded token, mandatory stop.

## Retention/D3.5

- exact native consumer grants; exact SHAs/sizes and per-read receipts; 89-read census; 34-stage vocabulary and serialization; zero original-checkpoint reads; no proof/reference relabeling;
- result SHA `472a3085111ed023c3fafafc97600edaba4e6b8dbc0f58d35020561b650fa7e4`, acceptance SHA `9d4d29870e8aa67d9ca9ed2702bddd4b9248930204e4f03f05c5f05f2727b163`, retained class `MIXED_D0_V2_CLASS/PASS`.

## Accounting/authority

- historical master ledger 175 and SHA binding; no duplicate master/manual delta/page-fault conflation;
- six-shard/1809-tensor identity, exact MLX 0.31.2/MLX-C 0.6.0/dylib/rpath/M1 Ultra/thread/toolchain bindings; runtime drift rejected before attempt-start.

## Exact-head CI repair

- verify `cargo test -p f017-native --release --no-fail-fast` actually ran and passed;
- verify explicit D3.5 comparison-grant structural validation, numerical grading, and both mutation suites ran and passed;
- verify Python MLX 0.32.0 is isolated from native C/Rust MLX 0.31.2 without weakening either runtime qualification;
- verify no native qualification skip.

## P1/human boundary

- exact contract instantiability; no placeholder producer; replay/concurrent claim/retry/resume/continuation/second token; mandatory stop; normal validation cannot mint live authorization; human decision is one future yes/no gate.

Classify every finding using only `BLOCKING`, `NON_BLOCKING_REQUIRED`, or `DEFENSE_IN_DEPTH`, with stable ID, exact path/symbol, evidence, failure mode, required repair, and disposition. Both BLOCKING and NON_BLOCKING_REQUIRED prevent acceptance. Defense-in-depth may remain only with a precise non-weakening disposition and future bind point.

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
