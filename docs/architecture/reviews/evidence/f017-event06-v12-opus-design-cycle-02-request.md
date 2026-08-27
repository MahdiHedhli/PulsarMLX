# F017 Event 06 V12 checkpoint-identity authority design ARBITER cycle 2

Use `claude-opus-5`, effort high, in this fresh detached read-only worktree. Review exact committed bytes only. Do not modify files or access checkpoint shards.

Reconstruct cycle-1 findings from `docs/architecture/reviews/evidence/f017-event06-v12-opus-design-cycle-01-normalized-result.json`, then inspect the append-only repairs:

- `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-checkpoint-identity-authority-design-v12-v2.json`
- `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-checkpoint-identity-lifecycle-design-v12-v2.json`
- `docs/architecture/reviews/evidence/f017-event06-identity-producer-challenge-ledger-v5.json`
- `docs/architecture/reviews/evidence/f017-event06-identity-producer-support-ledger-v5.json`

Directly verify: exact field types and coercion rejection; operation-class domains for both scopes; the explicit primary, secondary, and identity-producer candidate and installed triples; all six triple validations before package claim; runtime revalidation after durable package start and before checkpoint identity start or any shard open; explicit shard-open transition; uniform failure-outcome census; exact deltas and generic-fallback prohibition; corrected ledger accounting.

Issue one design-stage verdict for all 16 exact claims. For C-SYN-001, C-CI-001, and other implementation-stage claims, decide whether the design is implementable and sufficient; do not require future implementation evidence as a condition of design authorization.

Return exactly `ACCEPT_F017_CHECKPOINT_IDENTITY_AUTHORITY_V12_FOR_IMPLEMENTATION` or `REJECT`. No conditional acceptance. State per-claim verdicts plus blocking, non-blocking-required, and unresolved counts.
