# F017 Event 05 readiness interface IMPLEMENTATION ARBITER cycle 01

Use a fresh detached read-only session and inspect committed bytes only. Begin by reporting `git rev-parse HEAD` and require it to equal the detached checkout. Model must be `claude-opus-5`, high effort.

Reconstruct the historical E0 readiness mismatch and arbitrate all twelve readiness-critical claims independently:

- C-SCHEMA-001, C-SCHEMA-002
- C-VALIDATOR-001, C-AUTHORIZER-001
- C-INSTANT-001, C-INSTANT-002
- C-BIND-001, C-SAFETY-001, C-LEGACY-001
- C-CI-001, C-REVIEW-001, C-GO-001

Primary evidence is the repository at this HEAD, especially:

- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-whole-domain-review-manifest-v2.json`
- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-full-native-ci-v2.json`
- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-gemini-whole-domain-cycle-03-normalized-result.json`
- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-support-ledger-v7.json`
- `docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v5.json`
- `specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v11-v5.json`

Independently reproduce the old failure; inspect the canonical validator and refactored authorizer; search for duplicate readiness logic; mutate every safety field, uppercase/conflicting aliases, authority substitutions, and candidate bytes; test validation-only side effects; compare validation-only and live candidate construction; and verify historical supersession, exact-head FULL_NATIVE run 33038039750, zero checkpoint access, and absence of Event 05 live authority.

Directly retest the Gemini cycle-02 repair: live installation must re-read approval/readiness, rederive the exact candidate through the shared builder and fixed production authority, compare canonical bytes/digest, and reject critical mutation before exclusive install. Independently verify why candidate `live:false` is required until installation receipt authority, rather than demanding an invalid `live:true` candidate.

For each claim return `ACCEPT`, `REJECT`, or `UNRESOLVED`, with evidence and earliest invalidated node. Report blocking, non-blocking-required, and unresolved counts. Finish with exactly one global token: `ACCEPT_F017_EVENT05_READINESS_INTERFACE_IMPLEMENTATION` or `REJECT`. No conditional acceptance.
