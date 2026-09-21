# F017 V11 whole-domain ARBITER review — cycle 02

Use a fresh `claude-opus-5` session at high effort. Review committed bytes in
the supplied detached read-only clone. Repository and Git evidence outrank
this request. Do not modify files, access original checkpoint shard payloads,
execute or authorize Event 05, retry or resume Event 04, or execute P1
attempt 2.

Issue an independent verdict for every readiness-critical claim:

`C-OUT-001`, `C-OUT-002`, `C-FORM-001`, `C-FORM-002`, `C-LEGACY-001`,
`C-LEGACY-002`, `C-BITS-001`, `C-BITS-002`, `C-PURITY-001`,
`C-ONEEXEC-001`, `C-INDEP-001`, `C-QUAL-001`, `C-V11-001`, `C-V11-002`,
and `C-CI-001`.

First reconstruct cycle 01 and independently verify closure of every finding:

- `F-01` — secondary binary32 margin is derived with binary32 subtraction;
- `F-02` — real V3 outputs cross the production summary and bundle boundary;
- `F-03` — wrapper censuses derive from routing, descriptor, and store state;
- `F-04` — evidence-descendant claims use exact scope.

Then reconstruct the CI-discovered historical split defect and its repair.
Verify that the two V10 target-source files are restored byte-for-byte, the
new path-reopen telemetry exists only in distinct V11 successors, V11 wrappers
import those successors, the V10 generator check passes, and V11 measurement
v3 plus scientific-access v11-v3 bind every changed Git byte. Search for any
active V11 bypass that still imports the V10 source directly.

Independently reconstruct the original R11 blocker; V2-to-V3 formula
preservation; one-execution output capture; exact legacy compatibility;
payload bit/hash binding; immutable ownership; lack of I/O, reflection, or
callback capability; source-read equivalence; primary/secondary independence;
numerical V4 requalification; exact six-payload V11 banking; control-JSON
exclusion; primary-terminal-to-secondary gate; result and package closure;
full-size bundles; independent comparison; failure and filesystem mutations;
Event-04 diagnostic isolation; production-shaped zero-access rehearsal;
generated-authority checks; and exact-head FULL_NATIVE run `33008441584` with
required native skips zero.

Inspect Gemini whole-domain cycle 03. It attacked all 15 claims after the
repairs and returned zero challenge rows and zero unresolved material items.

Primary packet:

- `docs/architecture/reviews/evidence/f017-numerical-output-interface-claim-ledger-v9.json`
- `docs/architecture/reviews/evidence/f017-numerical-output-interface-challenge-ledger-v9.json`
- `docs/architecture/reviews/evidence/f017-numerical-output-interface-support-ledger-v11.json`
- `docs/architecture/reviews/evidence/f017-numerical-output-interface-opus-whole-domain-cycle-01-normalized-result.json`
- `docs/architecture/reviews/evidence/f017-numerical-output-interface-opus-whole-domain-cycle-01-repair-v1.json`
- `docs/architecture/reviews/evidence/f017-numerical-output-interface-ci-historical-split-repair-v1.json`
- `docs/architecture/reviews/evidence/f017-numerical-output-interface-gemini-whole-domain-cycle-03-normalized-result.json`
- `docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v3.json`
- `specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v11-v3.json`
- `docs/architecture/reviews/evidence/f017-corrected-oracle-numerical-requalification-v4.json`
- `docs/architecture/reviews/evidence/f017-v11-full-geometry-qualification-v2.json`
- `docs/architecture/reviews/evidence/f017-v11-result-failure-qualification-v2.json`
- `docs/architecture/reviews/evidence/f017-event05-production-shaped-no-access-rehearsal-v11-v2.json`
- `docs/architecture/reviews/evidence/f017-v11-event05-full-native-ci-v2.json`

Return one JSON object with `reviewed_head`, `reviewer_model`,
`claim_verdicts` (one row per claim containing `claim_id`, `verdict` as
`ACCEPT`, `REJECT`, or `UNRESOLVED`, `evidence`, and
`invalidation_disposition`), `findings` (graded `BLOCKING`,
`NON_BLOCKING_REQUIRED`, or `DEFENSE_IN_DEPTH`), `blocking_count`,
`non_blocking_required_count`, `unresolved_count`,
`original_checkpoint_access_observed`, and `global_verdict`.

The required global verdict is exactly
`ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_05_EXECUTION_AUTHORIZATION`
or `REJECT`. No conditional acceptance.
