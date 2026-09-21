# F017 V11 whole-domain ARBITER review — cycle 01

Use a fresh `claude-opus-5` session at high effort. Review committed bytes in
the supplied detached read-only clone. Repository and Git evidence outrank this
request. Do not modify files, access original checkpoint shard payloads,
execute or authorize Event 05, retry/resume Event 04, or execute P1 attempt 2.

Issue an independent verdict for every readiness-critical claim:

`C-OUT-001`, `C-OUT-002`, `C-FORM-001`, `C-FORM-002`, `C-LEGACY-001`,
`C-LEGACY-002`, `C-BITS-001`, `C-BITS-002`, `C-PURITY-001`,
`C-ONEEXEC-001`, `C-INDEP-001`, `C-QUAL-001`, `C-V11-001`, `C-V11-002`,
and `C-CI-001`.

Independently reconstruct the R11 instantiability blocker; V2-to-V3 formula
preservation; one-execution output capture; exact legacy compatibility; payload
bit/hash binding; immutable ownership; lack of I/O/reflection/callback
capability; source-read equivalence; primary/secondary independence; numerical
V4 requalification; exact six-payload V11 banking; control-JSON exclusion;
primary-terminal-to-secondary gate; result/package closure; full-size primary
and secondary bundles; independent comparison; output/identity/filesystem and
causal-order mutations; Event 04 diagnostic isolation; production-shaped
zero-access rehearsal; generated-authority checks; exact implementation
measurement; and FULL_NATIVE run `32981760971` with required native skips zero.

Also inspect the Gemini cycle-01 challenges and cycle-02 closure. Verify no
measured execution path changed after the implementation measurement, and that
only evidence JSON separates the FULL_NATIVE head from its reviewed descendant.
Verify original-checkpoint access zero, Event 05 authority absent, Event 05 not
executed, Event 04 nonretry/nonresume, P1 attempt 2 absent, and ledger 175.

Primary packet:

- `docs/architecture/reviews/evidence/f017-numerical-output-interface-claim-ledger-v8.json`
- `docs/architecture/reviews/evidence/f017-numerical-output-interface-challenge-ledger-v7.json`
- `docs/architecture/reviews/evidence/f017-numerical-output-interface-support-ledger-v9.json`
- `docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v1.json`
- `docs/architecture/reviews/evidence/f017-v11-full-geometry-qualification-v1.json`
- `docs/architecture/reviews/evidence/f017-v11-result-failure-qualification-v1.json`
- `docs/architecture/reviews/evidence/f017-event05-production-shaped-no-access-rehearsal-v11-v1.json`
- `docs/architecture/reviews/evidence/f017-v11-event05-full-native-ci-v1.json`
- `docs/architecture/reviews/evidence/f017-corrected-oracle-numerical-requalification-v4.json`
- `specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v11.json`

Return one JSON object with `reviewed_head`, `reviewer_model`, `claim_verdicts`
(one row per claim containing `claim_id`, `verdict` as `ACCEPT`, `REJECT`, or
`UNRESOLVED`, `evidence`, and `invalidation_disposition`), `findings` (each
graded `BLOCKING`, `NON_BLOCKING_REQUIRED`, or `DEFENSE_IN_DEPTH`),
`blocking_count`, `non_blocking_required_count`, `unresolved_count`,
`original_checkpoint_access_observed`, and `global_verdict`.

Required global verdict is exactly
`ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_05_EXECUTION_AUTHORIZATION`
or `REJECT`. No conditional acceptance.
