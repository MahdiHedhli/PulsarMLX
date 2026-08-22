# F017 native bounded-P1 domain — cross-vendor disagreement search C2

You are the cross-vendor adversarial reviewer. This is a disagreement search, not a vote. Review only committed bytes from branch `feat/017-rust-native-inference-runtime` at exact head `aeca5b08ae96f6bd97f507c81ae373e4b86f9e90` in the detached worktree provided to you. Git is authoritative.

Do not execute M1 Ultra P1, open the original checkpoint, run full-model real-checkpoint inference, create a live authorization, or mutate repository bytes. Recompute SHA-256 values and inspect exact-head CI run `32560783265` directly.

The primary packet is `docs/architecture/reviews/evidence/f017-native-bounded-p1-domain-final-review-package-v1.json`; the exact P1 contract SHA is `44b9416ff2c4e14ae3005e8df931443f38adb4ab49d5c173dcdf103a222a7dda`; the banked executable SHA is `3894c4d12c93ac4c4f3584d2a9a41370c5074e7ef91402cfd8b16bf698c9c7ba`; and the execution-code head is `22a76e4c248434a1827e81501607f93b0779352e`.

Cycle 1 found `CI_OMITS_F017_NATIVE_TESTS` and `CI_OMITS_D3_5_VALIDATORS`. Attack the repairs directly:

1. Verify CI now executes `cargo test -p f017-native --release --no-fail-fast` under pinned native MLX and that it passes at the reviewed head.
2. Verify CI now explicitly runs the committed D3.5 comparison-grant structural validator, numerical-grading validator, and both mutation suites, with 89 bound reads, 34 stages, zero original-checkpoint reads, and no rerun of D3.5.
3. Confirm Python MLX 0.32.0 and the dedicated native C/Rust MLX 0.31.2 dylib domains are isolated without weakening either qualification.
4. Re-attack D0 post-hoc leakage, D1 live counter invariants, D2 ledger/residency semantics, the math-only mock boundary, RN1 ownership, exact six-shard/1809-tensor identity, retained consumer grants/read receipts/vocabulary, exact contract instantiability, one-shot authorization, and the representative-layer-only D3.5 scope.
5. Verify normal validation cannot create a live authorization and the real P1/original-checkpoint counters remain zero.

For every finding return a stable ID, severity (`BLOCKING`, `NON_BLOCKING_REQUIRED`, or `DEFENSE_IN_DEPTH`), exact path/symbol, evidence, failure mode, and required repair. State whether the cycle-1 blockers are closed and whether you materially disagree with acceptance. End with exactly one verdict: `NO_MATERIAL_DISAGREEMENT` or `MATERIAL_DISAGREEMENT_ESCALATE`.

Also state exactly:

`REAL_M1_ULTRA_P1_EXECUTED_DURING_REVIEW: NO`

`ORIGINAL_CHECKPOINT_READS_DURING_REVIEW: 0`

`LIVE_P1_AUTHORIZATION_CREATED_DURING_REVIEW: NO`
