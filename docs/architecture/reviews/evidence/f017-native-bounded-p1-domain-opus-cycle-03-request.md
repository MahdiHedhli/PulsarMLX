# F017 Native Bounded-P1 Domain — Opus Interim Final Review C3

You are Claude Opus 5, the temporary independent adversarial reviewer while Claude Fable 5 is quota-blocked. This interim review cannot authorize P1 and does not waive later Fable ratification.

Review committed bytes only in a detached, clean, non-authoritative worktree at exact target `ab236b924f7dd7a95d226c5bb528315a4a68d72c` on branch `feat/017-rust-native-inference-runtime`. Recompute all hashes. Inspect exact-head CI run `32574711605` directly. Do not run P1, open the original checkpoint, create a live authorization, or modify reviewed repository bytes. Put mutation state and build outputs outside the review worktree.

## Required authority

- C2 exact response: `docs/architecture/reviews/evidence/f017-native-bounded-p1-domain-opus-cycle-02-exact-cli-response.json`, SHA-256 `b89eb63d7ae372ae4f226ec0a60db3640b8740d01b130de33b058e4cfbaa4251`.
- C2 normalized result: `docs/architecture/reviews/evidence/f017-native-bounded-p1-domain-opus-cycle-02-normalized-result.json`, SHA-256 `4ade469de333f5c773a5707a557f019b0de8238fd6b3101a29d12284ded31d25`.
- C2 repair disposition is at the later evidence tip and will be supplied verbatim with this request.
- Repair implementation commit: `038cdbfdf707dc80d2a548650885922cfa5aeb9e`.
- Exact review target and authority-rebind commit: `ab236b924f7dd7a95d226c5bb528315a4a68d72c`.
- Admission contract: `specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-admission-contract-v2.json`, SHA-256 `cf07ccfdd1a85413268b530368c93ba07695c235dcc69afa096133d17e68b2fb`.
- Banked bounded-P1 executable: `specs/017-rust-native-inference-runtime/bin/f017-native-bounded-p1`, SHA-256 `6f0ad9370caf2582934a917029476f505e1a3792b46cbdfe046c7cda85cf31dc`.
- D0 v2: `specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-numeric-acceptance-contract-v2.json`, SHA-256 `cc62cdc7550e3a25f55de783e9eb7c68f6cf03d0eafb944a86dc8a2a60007fb9`.
- D1: `specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-counter-semantics-v1.json`, SHA-256 `f3aab3b065628f96bfe1fab1a045a9af3d2261e2b5d7ef69c1528fb0a7d88246`.
- D2: `specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-accounting-residency-v1.json`, SHA-256 `d2312004f05cafbfd1f1779ccfbbb9e1a0c8c5b4e916aa0601abb04dbefe9c84`.
- D3.5 grading result: `docs/architecture/reviews/evidence/f017-native-d3-5-numerical-grading-result-v1.json`, SHA-256 `472a3085111ed023c3fafafc97600edaba4e6b8dbc0f58d35020561b650fa7e4`.
- D3.5 acceptance: `docs/architecture/reviews/evidence/f017-native-d3-5-numerical-qualification-acceptance-v1.json`, SHA-256 `9d4d29870e8aa67d9ca9ed2702bddd4b9248930204e4f03f05c5f05f2727b163`.
- Historical master ledger remains 175; real P1 executions, original-checkpoint reads, and live authorizations remain zero.

## First required attack: rerun C2-F1

Attempt the exact previously successful mutations:

1. `attempt_id = "../../ESCAPED"`;
2. absolute `attempt_id` under a reviewer-owned temporary directory;
3. unsafe `authorization_id` using traversal, separator, or NUL;
4. safe but contract-wrong attempt ID;
5. attempt to make validation reach checkpoint planning/opening before rejecting an unsafe real authority.

Verify every unsafe identifier is rejected, no attempt state appears inside or outside the state root, no claim is consumed, and no math runs. Verify a real authority's attempt ID is fixed by the exact contract and operator approval mechanism. Try Unicode, backslash, overlength, dot, and empty edge cases as well.

## Whole-domain review

Repeat the entire temporary-policy attack surface, not merely the repair:

- D3.5 read grants, 89 receipt census, 34-stage vocabulary and serialization, OCB derivation, D0 frozen tolerance epistemics, routing membership/order/ties, metric implementation, and PASS classification without numerical re-execution.
- Native full bounded-P1 producer: no Python math fallback or cross-runtime stitching; all layers/experts/formats; correct KV/RoPE/final norm/logits/top-k; one token only; no retry/resume/continuation.
- Checkpoint loader and plan: exact six shards and 1,809 tensors; reject alternate roots, links, corruption, duplicates, missing tensors, and format fallback; plan-only does not open original payload bytes.
- F32_LE, Q5_K, Q6_K, Q8_0, IQ2_XXS, IQ3_XXS and every additional committed format: decoder binding, geometry, scaling, native path, and fallback behavior.
- All 22 D1 counters: live producer, strict type, coherent executor snapshots, logical/native independence, context/registration/teardown/in-flight/stale-generation meaning; all-zero and stale snapshots must not masquerade as real execution evidence.
- Receipt emitter: production executor path, exact key census and identities, prompt 9703, result 21615, mandatory stop, receipt/terminal ordering and consistency.
- RN1 one-shot state: exclusive owned claim, exception ownership, receipt-derived terminal accounting, replay/concurrency/alternate-root/symlink/stale-auth/retry/resume/second-token/terminal-replacement attacks.
- Machine/runtime: exact Apple M1 Ultra and arm64, MLX 0.31.2, MLX-C 0.6.0, dylibs/executable/head, 16 GiB fresh-memory gate, drift rejection.
- Historical ledger 175 remains unique and distinct from native event/residency accounting.
- Synthetic ten-fresh-process qualification traverses the production control path with math-only substitution and zero checkpoint reachability. Inspect CI directly and distinguish the source-built and banked synthetic executables.
- Re-run B1 missing-free and B2 source-first/no-eval/no-sync regressions, oracle policy/parity, and residual edges where practical.

Explicitly revisit every C2 defense-in-depth finding. Promote any item that now weakens the pre-authorization gate; otherwise give a precise non-weakening disposition and later bind point. In particular, assess the source-built versus banked synthetic executable gap, diagnostic-disclosure overlap wording, historical-ledger object binding, and pre-commit qualification head labels.

## Evidence and verdict

Report exact reviewer model/track, CLI identity, reviewed branch/head, request SHA, independently rerun tests, stable finding IDs, severity, evidence, repair requirement, CI impact, and final verdict. Use `BLOCKING`, `NON_BLOCKING_REQUIRED`, and `DEFENSE_IN_DEPTH`; the first two prevent acceptance.

Return exactly one terminal verdict:

`OPUS_INTERIM_ACCEPT_FOR_F017_NATIVE_BOUNDED_P1_DOMAIN`

or

`REJECT`

Always state:

`FABLE_RATIFICATION_PENDING: YES`

`REAL_M1_ULTRA_P1_EXECUTED_DURING_REVIEW: NO`

`ORIGINAL_CHECKPOINT_READS_DURING_REVIEW: 0`

`LIVE_P1_AUTHORIZATION_CREATED_DURING_REVIEW: NO`
