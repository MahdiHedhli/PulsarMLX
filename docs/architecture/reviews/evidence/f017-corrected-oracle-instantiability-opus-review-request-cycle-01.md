# F017 Corrected Oracle Authorization-to-Consumer Instantiability — Opus Final Review C1

You are the final independent adversarial reviewer. Use a fresh `claude-opus-5` high-effort session. Review committed bytes only in a clean detached read-only worktree. Repository bytes and direct CI evidence outrank this request. Do not modify files, mint an authorization, create Event 03 state, open/hash/mmap/pread original checkpoint payload, run either real oracle consumer, or execute P1 attempt 2.

Authority:

- branch: `feat/017-rust-native-inference-runtime`
- reviewed head: `a7a7b82f7fbfb894e3bd21a995bce481f12123f5`
- execution source commit: `546e7aa6cbdf03317c363f752e824868ca01d32f`
- controlling FULL_NATIVE CI: run `32624610787`
- Event 02 failure summary SHA: `617cb92605eb93cba3f24e7395a1a12ba0797ac2130213e2a72b5e83b87381eb`
- Event 02 postmortem: `docs/architecture/reviews/evidence/f017-corrected-oracle-event-02-instantiability-postmortem-v1.json`
- successor authorization interface: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-authorization-consumer-interface-v1.json`
- scientific-access v3: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v3.json`
- inert authorization v3: `specs/017-rust-native-inference-runtime/fixtures/f017-corrected-full-checkpoint-oracle-inert-authorization-v3.json`
- accounting v3: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event-accounting-v3.json`
- qualification: `docs/architecture/reviews/evidence/f017-corrected-oracle-authorization-consumer-instantiability-qualification-v1.json`
- authority manifest: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-instantiability-authority-manifest-v1.json`
- historical master ledger: `175`

Independently perform the complete required attack set:

1. Reconstruct Event 02, prove the exact authorizer-v2/consumer-v1 mismatch, identity-read order, zero numerical consumer starts, receipt/terminal, consumed/non-retryable disposition, and immutable evidence.
2. Inspect schema v3 and both successor consumers. Attack exact key/type census, superseded schema rejection, primary/secondary role checks, producer/decoder/catalog/contract/context/root/lifecycle/ledger bindings.
3. Attack live authorization and event identities: inert/test markers, duplicate/reused IDs, role swaps, same event ID, replay, and fixture-ID promotion.
4. Verify the shared parser is strictly nonnumerical and neither weakens role validation nor contaminates primary/secondary numerical independence.
5. Independently run both capability and validation-only modes and prove zero authorization/state creation, checkpoint opens/hashes/mmaps/reads, and numerical operations.
6. Inspect two-phase mint byte flow. Both exact consumers must validate the identical candidate before atomic install; both PASS reports and candidate/install equality must be load-bearing; any rejection or byte mutation must leave no live authority.
7. Inspect coordinator ordering and inject failure: installed auth, both capabilities, both validation reports, banked handshake, then package state/start, then checkpoint identity. Require opens/reads before handshake both zero.
8. Run the exact synthetic file-backed authorizer-to-consumer chain through both target readers and the real successor coordinator. Confirm six synthetic shards, dense and MoE layers, routing/shared expert/final projection, complete receipts/terminals, and original checkpoint unreachability.
9. Rerun 10+10 validation-only processes and 10 complete package processes. Attack wrong schema, keys/types, role swaps, SHAs, roots, IDs, candidate/install mismatch, capability mismatch, skipped validation, hash-before-handshake, primary failure, and unstarted-secondary accounting.
10. Audit event accounting and Event 02 disposition. Mint is not execution; package and consumer durable starts are distinct; an unstarted secondary contributes zero; v2 delta 2 is not rewritten into a numerical-event claim.
11. Recompute unchanged numerical-methodology, old primary/secondary numerical source, decoder, checkpoint-free qualification, context, and frozen threshold hashes. Promote any plumbing drift into scope failure.
12. Inspect FULL_NATIVE run `32624610787` directly: exact head/mode, workspace, pinned MLX, test commands/counts, accelerated-Python/runtime isolation, zero required native skips, and workflow success. Reconstruct predecessor run `32624054720` and verify its ABI collision was closed without numerical-source changes. Inspect the later review-packet EVIDENCE_ONLY run once banked and verify zero native jobs.
13. Verify Event 03 auth/execution zero, primary/secondary real executions zero, new original-checkpoint access zero, P1 attempt 2 zero, and historical ledger 175.

Use `BLOCKING`, `NON_BLOCKING_REQUIRED`, and `DEFENSE_IN_DEPTH`; both first categories prevent acceptance. Return exactly `ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EXECUTION_AUTHORIZATION_PREPARATION` or `REJECT`. No conditional acceptance.
