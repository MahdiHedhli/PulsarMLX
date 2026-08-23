# F017 Corrected Oracle Authorization-to-Consumer Instantiability — Gemini Review C1

Use a fresh `gemini-3.1-pro-high` high-effort AGY session. Review committed bytes only in a clean detached read-only worktree. Repository bytes and direct CI evidence outrank this request. Do not modify files, mint an authorization, create Event 03 state, open/hash/mmap/pread original checkpoint payload, run either real oracle consumer, or execute P1 attempt 2.

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

Independently attack the whole focused boundary:

1. Reconstruct Event 02 and prove v2 authorizer output met only v1 consumer parsers, all six identity hashes preceded rejection, neither numerical consumer started, and history remains immutable/non-retryable.
2. Recompute load-bearing hashes and decide whether schema v3 is required by the explicit per-consumer IDs, roots, and actual-start accounting.
3. Attack exact key census, strict types including bool-as-int, unknown/missing fields, v1/v2 rejection, live/inert state, and role-specific primary/secondary validation.
4. Attack live ID and consumer-event ID generation: inert/fixture/test/synthetic markers, duplicate/reused IDs, mutable-filename derivation, replay, swapped roles, wrong producer/decoder/contract/catalog/root bindings.
5. Inspect shared parser scope for numerical/graph/decoder/checkpoint contamination and verify each consumer still applies independent role checks.
6. Verify capability and `validate-live-authorization` reports perform zero state creation, shard opens, identity hashes, mmaps, tensor reads, or numerical operations.
7. Attack two-phase mint: exact candidate bytes must reach both real validation-only boundaries; either rejection prevents install; installed bytes equal candidate; O_EXCL/fsync/dir-fsync/readback/revalidation; no inert ID promotion.
8. Attack coordinator order: both capability and authorization handshakes before package root/start and before checkpoint identity opens/hashes. Inject capability/schema/role/producer/event/root/unknown-field/candidate mismatch.
9. Audit accounting: mint delta zero; package starts separately; each consumer delta only on its durable start; a primary precompletion failure cannot start/count secondary; Event 02 delta remains its historical v2 reservation meaning.
10. Run the file-backed synthetic chain using the real builder, exact parsers, target readers, access producers, coordinator, receipts, terminals, and comparison. Verify six tiny shards, dense+MoE layers, routed/shared experts, and no path to the original checkpoint.
11. Rerun 10 fresh primary validation processes, 10 secondary, 10 complete packages, and all mutation/failure tests. Look for mocked construction or hand-authored final authority.
12. Recompute unchanged numerical-methodology, old primary/secondary numerical implementations, decoder, context, threshold, and qualification SHAs. No numerical semantic drift is allowed.
13. Inspect CI `32624610787`: exact head/mode, workspace and pinned-native jobs, new tests actually invoked, accelerated-Python/runtime isolation, required native skips, and aggregate result. Reconstruct failed predecessor run `32624054720` and verify the ABI collision was repaired without numerical-source changes.
14. Verify no Event 03 authorization/execution, no original-checkpoint access in this phase, no P1 attempt 2, and ledger 175.

Use `BLOCKING`, `NON_BLOCKING_REQUIRED`, and `DEFENSE_IN_DEPTH`; the first two prevent acceptance. Return exactly `ACCEPT` or `REJECT`, with stable finding IDs, independently rerun commands/tests, and any material disagreement.
