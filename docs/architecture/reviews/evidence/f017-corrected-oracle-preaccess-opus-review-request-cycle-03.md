# F017 Corrected Full-checkpoint Oracle Pre-access Final Review — Cycle 03

Reviewer must be `claude-opus-5`, high effort, fresh session. Review committed bytes only from a clean detached read-only worktree.

Authority:

- branch: `feat/017-rust-native-inference-runtime`
- implementation head: `e00811df76c480b53b1bcab35fcb01ea8475b089`
- bound package head: `4badbcc9f2f0c0221b2c1abf84ee26817229c792`
- controlling FULL_NATIVE CI run: `32604077031`, success
- historical master ledger: `175`
- scientific access contract: `fdff100fc91efc3ca337bd256dd290a6211f18eb6ce38255ed50f30da806b434`
- numerical contract: `7c22507f15c79713a0f81dcf14ea3472aafef3cf43c09d388a6c021b3f1069c4`
- synthetic qualification: `b9c2f7dcd9982120f804594e9e268b7d0d764190625789717d104f4e4829c052`
- inert authorization: `fb379d7ec2f32cd68a34631a0d6be33138ddde497eb51a48361c8cc6ea9f876e`
- IQ4_XS pinned known answer: `4564b86d28965c183202e5dc671fda5ed34ee4dff12aa591a814163aedb1d41d`

Recompute every load-bearing hash and inspect CI directly. Re-run the complete final attack surface from the phase request: durable serialized readback and fault injection; complete access producers; legacy-path retirement; attempt-1 non-retroactivity; primary/secondary independence; target-token quarantine; frozen uncertainty and token-stability rules; 79-layer graph; all 11 formats; metadata-only 1,809-tensor catalog authority; scientific access accounting and two consumer namespaces; authorization/replay/path/RN1 defenses; and attempt-2 fail-closed behavior.

Cycle 02 repair verification is mandatory:

1. Instantiate the real geometry contract through `Geometry.from_json`.
2. Independently derive 1,410 graph tensors, 399 declared non-access tensors, five graph-payload shards, and one identity-only shard. Determine whether the event remains scientifically complete and accounting-exact.
3. Attack identity-evidence reads before child event journals.
4. Recheck IQ4_XS lane order against pinned ggml revision `b06aa774c03dbbb624e726664b714a57d1f49815`, source SHA `07143d7068936ae46b3c528b2f3d4bbb666e74d88992165716174d243573965d`, and both Python and Rust known-answer tests. Look for common-mode errors in any other format.
5. Exercise synthetic multi-shard, expert-strided target readers end-to-end through the access census.
6. Verify the four formerly degenerate mutations now make distinct semantic changes and localize the earliest affected layer/field.
7. Reassess safety-factor derivation, fixture labeling, and memory geometry.

Safety invariants: zero original-checkpoint opens/reads, zero corrected oracle executions, zero P1 attempt-2 executions, zero live oracle/P1 authorizations, ledger 175. Do not execute the target event.

Use severities `BLOCKING`, `NON_BLOCKING_REQUIRED`, and `DEFENSE_IN_DEPTH`; both first two block acceptance. Return exactly `ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EXECUTION_AUTHORIZATION_PREPARATION` or `REJECT`.
