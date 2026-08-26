# F017 V11 whole-domain CHALLENGE review — cycle 03

Use `gemini-3.1-pro-high` at high effort. Review committed bytes only. This is
a read-only CHALLENGE review after Opus cycle-01 repairs and the exact-head CI
historical/active-authority split repair. Repository and Git evidence outrank
this request.

Do not modify files, access original checkpoint shard payloads, execute or
authorize Event 05, retry or resume Event 04, or execute P1 attempt 2.

Attack every readiness-critical claim: `C-OUT-001`, `C-OUT-002`,
`C-FORM-001`, `C-FORM-002`, `C-LEGACY-001`, `C-LEGACY-002`, `C-BITS-001`,
`C-BITS-002`, `C-PURITY-001`, `C-ONEEXEC-001`, `C-INDEP-001`, `C-QUAL-001`,
`C-V11-001`, `C-V11-002`, and `C-CI-001`.

Directly attack the four Opus cycle-01 repairs:

1. role-specific binary32 secondary top-1 margin derivation;
2. the real V3 core-to-summary-to-binary-bundle seam;
3. runtime-derived layer, descriptor, and path-reopen censuses;
4. exact evidence-descendant semantics.

Also attack the CI-discovered historical split repair. Verify that the V10
primary and secondary target sources are byte-exact historical authority,
that distinct V11 successors exclusively carry the new path-reopen telemetry,
that V11 wrappers import those successors, and that measurement v3 plus
scientific-access v11-v3 bind the exact Git bytes. Attempt to find any V11
runtime path still importing the V10 sources directly or any V10 generator
whose committed output now drifts.

Reconstruct formula preservation, exact legacy compatibility, one-execution
three-output capture, immutable payload ownership, source-read equivalence,
primary/secondary independence, full-geometry bundles, result closure,
primary-terminal gating, comparator independence, Event-04 diagnostic
nonpromotion, the 360-case failure campaign, no-access rehearsal, generator
checks, and FULL_NATIVE run `33008441584` with required native skips zero.

Primary packet:

- `docs/architecture/reviews/evidence/f017-numerical-output-interface-claim-ledger-v8.json`
- `docs/architecture/reviews/evidence/f017-numerical-output-interface-challenge-ledger-v7.json`
- `docs/architecture/reviews/evidence/f017-numerical-output-interface-support-ledger-v10.json`
- `docs/architecture/reviews/evidence/f017-numerical-output-interface-opus-whole-domain-cycle-01-normalized-result.json`
- `docs/architecture/reviews/evidence/f017-numerical-output-interface-opus-whole-domain-cycle-01-repair-v1.json`
- `docs/architecture/reviews/evidence/f017-numerical-output-interface-ci-historical-split-repair-v1.json`
- `docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v3.json`
- `specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v11-v3.json`
- `docs/architecture/reviews/evidence/f017-v11-full-geometry-qualification-v2.json`
- `docs/architecture/reviews/evidence/f017-v11-result-failure-qualification-v2.json`
- `docs/architecture/reviews/evidence/f017-event05-production-shaped-no-access-rehearsal-v11-v2.json`
- `docs/architecture/reviews/evidence/f017-v11-event05-full-native-ci-v2.json`

Return one JSON object containing `reviewed_head`, `reviewer_model`,
`claims_attacked`, and `challenges`. Every challenge must include
`challenge_id`, `claim_id`, `attack`, `mutation_or_trace`,
`expected_behavior`, `observed_behavior`, `severity`, `affected_artifacts`,
and `status`. Also return `material_challenge_count`, `unresolved_count`,
`original_checkpoint_access_observed`, and `challenge_verdict`.

Do not issue the final acceptance decision. If no material challenge survives,
set `challenge_verdict` to `NO_UNRESOLVED_MATERIAL_CHALLENGE`.
