# F017 Lifecycle-v5 Interface Review — Cycle 1

You are the required independent interface-design reviewer. Use `claude-opus-5` at high effort. Review committed bytes at exact target `d91528b646e8cea8ef6aff41fc304c0e84f8f67b` in a clean detached read-only worktree. Repository evidence outranks this request.

Do not modify the worktree, open/hash/mmap/pread original checkpoint shards, mint a live authorization, create Event 04 state, execute either real oracle, or execute P1 attempt 2. Synthetic/no-access validation is permitted.

Reconstruct the cycle-3 rejection from the closeout and normalized result. Then independently attack the new canonical source of truth and generated views:

- `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-lifecycle-semantic-model-v1.json`
- outcome obligations v5, event-accounting v5, path timing v1, canonical serialization v1;
- authorization-consumer interface v5, generated identity registry/matrix, artifact schemas;
- the semantic engine, generator, independent validator, tests, and v4-failure reproduction.

Required attacks:

1. Prove event-accounting is actually loaded and pinned, then mutate every transition-to-ledger mapping.
2. Prove outcome obligations come from reached durable-start transitions. Attempt fabricated unstarted-consumer receipts/terminals/ledger entries and missing started-consumer evidence.
3. Prove every representative trace is legal and every transition has a modeled failure outcome.
4. Attack path timing, absent-leaf handling, symlink ancestry semantics, and every explicit root-relation pair. Identify any unsatisfiable legal trace.
5. Attack canonical JSON bytes, duplicate keys, nonfinite values, self-SHA ambiguity, exact trailing newline, and readback hash domain.
6. Attack authorization top/nested key censuses and bidirectional artifact schema IDs/payload/binding channels.
7. Determine whether generated registry/matrix views can drift consistently with the generator while violating the compact semantic model or independent fixed invariants.
8. Attack implementation measurement-head semantics and identify any still-undefined pin needed before live authorization.
9. Verify Event 03 remains immutable, no Event 04 authority/state/access exists, numerical authorities are unchanged, and historical ledger is 175.
10. Identify any v2/v3 live-mint or target-execution surface that must be mechanically retired in the implementation phase; distinguish a known future implementation obligation from a defect in the interface model itself.

Use findings severities `BLOCKING`, `NON_BLOCKING_REQUIRED`, and `DEFENSE_IN_DEPTH`. Both BLOCKING and NON_BLOCKING_REQUIRED mean REJECT. Return exactly one terminal interface verdict: `ACCEPT_LIFECYCLE_V5_INTERFACE_FOR_IMPLEMENTATION` or `REJECT`. No conditional acceptance.
