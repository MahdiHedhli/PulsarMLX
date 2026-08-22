# F017 native bounded-P1 domain — cross-vendor disagreement search C1

You are the cross-vendor adversarial reviewer. This is a disagreement search, not a vote. Review only committed bytes from branch `feat/017-rust-native-inference-runtime` at exact head `d2d8c9af75e03f49d03f89dd6e3501b501d33be2` in the detached worktree provided to you. Git is authoritative.

Do not execute M1 Ultra P1, open the original checkpoint, run full-model real-checkpoint inference, create a live authorization, or mutate repository bytes. Synthetic/inert and already-banked retained evidence may be inspected. Recompute SHA-256 values and inspect exact-head CI run `32559658103` directly.

The primary packet is `docs/architecture/reviews/evidence/f017-native-bounded-p1-domain-final-review-package-v1.json`; the exact P1 contract is `specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-admission-contract-v2.json` (expected SHA `44b9416ff2c4e14ae3005e8df931443f38adb4ab49d5c173dcdf103a222a7dda`). The execution-code head is `22a76e4c248434a1827e81501607f93b0779352e`; the banked executable SHA is `3894c4d12c93ac4c4f3584d2a9a41370c5074e7ef91402cfd8b16bf698c9c7ba`.

Attack the complete domain, especially:

1. D0 tolerance methodology, post-hoc leakage, use of native output as an oracle, GPU nondeterminism, routing structural gates, and the rule that D3.5 results may falsify but never set a tolerance.
2. Whether every D1 counter has a live producer and meaningful invariant; try all-zero, stale, wrong-scope, missing in-flight, and stale-generation cases.
3. Whether the math-only mock leaves claim/context/streams/ownership/native-free observation/snapshots/receipt/terminalization real and makes the original checkpoint structurally unreachable.
4. Whether D2 correctly binds historical ledger v2 SHA `aa98f5...`, separates logical access from mmap/residency, and avoids a competing master count or manual delta.
5. Whether the native executor is genuinely instantiable and performs exactly token 9703 -> one result token 21615, then mandatory stop, with no retry/resume/continuation.
6. Whether exact six-shard checkpoint identity, 1809-tensor census, code manifest, executable, M1 Ultra, MLX 0.31.2, MLX-C 0.6.0, dylibs, Metal/toolchain, and thread environment are revalidated before attempt-start.
7. Whether RN1 exclusive ownership prevents one invocation terminalizing another; whether terminal accounting is receipt-derived and cross-checked.
8. Whether retained qualification had exact native consumer grants, exact read sizes/SHAs, per-read receipts, canonical stage vocabulary/serialization, and zero original-checkpoint reads.
9. Whether D3.5 scope is honestly limited to representative layer-3 S0-to-S2 rather than claiming direct qualification of the remaining 79-layer full forward.
10. Whether normal validation can create a live authorization; whether future human authorization is exact-head/executor/contract/checkpoint/machine/attempt bound and non-replayable.
11. Whether exact-head CI really runs the pinned native tests without native skips, including B1/B2, oracle, D0/D1/D2, executor, inert producer, D3.5 validators, exact contract, and authorization fixture rejection.

Run any additional verification-only tests useful for disagreement discovery. For each finding return a stable ID, severity (`BLOCKING`, `NON_BLOCKING_REQUIRED`, or `DEFENSE_IN_DEPTH`), exact path/symbol, evidence, failure mode, and required repair. State whether you materially disagree with the package's proposed acceptance and why. End with exactly one verdict: `NO_MATERIAL_DISAGREEMENT` or `MATERIAL_DISAGREEMENT_ESCALATE`.

Also state exactly:

`REAL_M1_ULTRA_P1_EXECUTED_DURING_REVIEW: NO`

`ORIGINAL_CHECKPOINT_READS_DURING_REVIEW: 0`

`LIVE_P1_AUTHORIZATION_CREATED_DURING_REVIEW: NO`
