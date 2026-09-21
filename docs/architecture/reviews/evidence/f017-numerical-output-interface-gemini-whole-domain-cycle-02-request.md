# F017 V11 whole-domain CHALLENGE review — cycle 02

Use a fresh `gemini-3.1-pro-high` session at high effort. Work read-only from
exact committed head containing the cycle-01 support packet. Repository and Git
evidence outrank this request. The execution-byte boundary remains measured at
`53c114f7`; FULL_NATIVE ran at complete implementation/qualification head
`f6127f80`; later commits contain append-only evidence only.

Reassess `CHAL-DRIFT-001` and `CHAL-CI-001` against:

- `docs/architecture/reviews/evidence/f017-numerical-output-interface-support-ledger-v8.json`
- `docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v1.json`
- `docs/architecture/reviews/evidence/f017-v11-event05-full-native-ci-v1.json`
- `docs/architecture/reviews/evidence/f017-numerical-output-interface-claim-ledger-v8.json`

Independently inspect Git diffs and the measurement/authority checkers. Do not
assume an immutable implementation measurement head must equal later evidence
descendants. Do not assume an append-only EVIDENCE_ONLY descendant requires
another FULL_NATIVE run. If either descendant changes a measured execution,
contract, generator, workflow, test, qualification, or rehearsal byte, retain
the challenge and identify the exact path. Otherwise close it.

Return the same structured JSON shape as cycle 01, attack all 15 claims, and
include only still-supported or materially new challenge rows. Do not issue the
final Opus arbiter verdict. Do not modify files, access original checkpoint
shards, execute or authorize Event 05, retry Event 04, or execute P1 attempt 2.
