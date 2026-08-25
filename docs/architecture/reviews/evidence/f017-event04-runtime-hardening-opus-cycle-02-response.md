# F017 Event-04 Execution-Readiness Final Review — Opus Cycle 02 Response

Reviewer: `claude-opus-5`, high effort, fresh read-only detached worktree.

Reviewed head: `98692103288bae3544069894f710d318d53d63d4`

Session: `47a3e49a-be15-45f9-adc5-7fb4761ee494`

The reviewer independently reproduced generator check mode, runtime authority
validation, exact implementation measurement, 33 focused tests, byte-identical
qualification evidence, the deterministic rehearsal core, unchanged numerical
authorities, all 47 outcomes/201 executions, and the 41 coordinator plus six
authorizer realization split. It confirmed cycle-01 `B1`, `N1`, and `D1`–`D8`
closed, but rejected on the following successor findings.

## Blocking

- `B-01 NONCANONICAL_APPROVED_PATHS_PERMANENTLY_BRICK_EVENT_04_AFTER_IRREVERSIBLE_INSTALL`:
  operator-approved install, receipt, and emergency paths were only checked for
  absoluteness. On macOS a `/tmp` path resolves to `/private/tmp`, so rendering
  and no-replace installation could succeed and the installed handshake then
  reject its own unresolved path, with repair installation prohibited.

## Non-blocking required

- `N-01 TERMINALIZER_EVIDENCE_WRITE_IS_UNGUARDED_SO_ROOT_PREPARATION_FAILURES_ESCAPE_UNCAPSULATED`:
  collision, permission, file-instead-of-directory, and storage errors during
  failure-capsule banking could escape through raw exceptions.
- `N-02 EVENT_04_MINT_IS_NOT_BOUND_TO_THE_ACCEPTED_IMPLEMENTATION_HEAD_OR_AUTHORITY_MANIFEST`:
  readiness fields existed but were not compared with the measured
  implementation or runtime authority manifest.

## Defense in depth

- `D-01 IMMUTABLE_MINT_GATE_SCALARS_ARE_UNVALIDATED`.
- `D-02 CAPSULE_FAILURE_CLASS_IS_HARDCODED`.
- `D-03 QUALIFICATION_ASSERTS_UNMEASURED_LITERALS_AND_CI_NEVER_CHECKS_THE_DERIVED_SPLIT`.
- `D-04 SYMLINKED_SHARD_YIELDS_UNCONTROLLED_OSERROR`.
- `D-05 TERMINAL_EVIDENCE_IS_WRITTEN_THROUGH_A_REJECTED_SYMLINK`.

The reviewer verified original checkpoint access zero, Event-04 authority and
execution absent, P1 attempt 2 absent, attempts one, retries zero, resume false,
and historical ledger 175. It recorded material disagreement with Gemini's
earlier acceptance because that review predated the successor repairs.

Final verdict: `REJECT`
