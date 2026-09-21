# F017 Event-04 execution-readiness final review — Opus cycle 05

Reviewer: `claude-opus-5`, high effort, fresh read-only session. Reviewed implementation `a2a8d3bc06ecf142f2ed0c7727662516e6429ebd`, tree `3d7c5b36098abda8486b31c7361aae8574770e1f`, and evidence head `c0bed564bb8e500e178d81e395e6e60602ef6219` from a byte-identical Git-backed scratch clone.

## Reconstructed evidence

Generator check, runtime authority validation, 38-binding/30-closure measurement, 45 tests, full qualification, production-shaped rehearsal, and FULL_NATIVE run `32823480546` passed. Qualification reproduced 50 packages, 47 outcomes over 201 executions, zero generic fallbacks, zero accounting mismatches, zero uncontrolled modeled failures, 30 release faults, and two declared terminal-root cases. Numerical authorities remained unchanged. Original checkpoint access, Event-04 authorization and execution, and P1 attempt 2 were all absent.

## Findings

### BLOCKING

- `B-01-C05 ACCOUNTING_FILESYSTEM_GUARD_CONVERTS_UNREADABLE_DURABLE_START_EVIDENCE_INTO_A_FALSE_ZERO_WHILE_REPORTING_DERIVATION_SUCCESS`

  The accounting guard converted an unreadable durable-start artifact into `False`. A real unsearchable root containing `package-durable-start.json` therefore produced `accounting.package = 0`, `accounting_derivation.result = PASS`, no package-terminal obligation, and no `package-terminal.json`. This silently denied evidence of a possible durable start.

### NON_BLOCKING_REQUIRED

- `N-01-C05 MANDATED_TERMINAL_ROOT_FAULT_REGRESSIONS_STUB_OUT_THE_REPAIRED_DERIVATION_AND_CERTIFY_AN_UNREACHABLE_PATH`

  Both pytest and qualification replaced `coordinator.derive` and `coordinator.bank_runtime_artifact` with stubs. They did not create a real unsearchable root, so the asserted `UNAVAILABLE` path was unreachable from the repaired implementation.

- `N-02-C05 DEGRADED_ACCOUNTING_OBSERVATION_ESCAPES_TERMINALIZATION_THROUGH_UNGUARDED_VALIDATE_AGAINST_OUTCOME`

  A modeled failure with nonzero expected accounting and a degraded zero observation reached `validate_against_outcome`, whose mismatch `ValueError` escaped `_terminalize` without a terminal capsule.

### DEFENSE_IN_DEPTH

- `D-01-C05`: the nominated implementation commit predated the regenerated manifest, although its implementation bytes matched the later contract-head manifest.
- `D-01-C04`: byte identity was enforced but review-history provenance remained underconstrained.
- `D-02-C04`: six authorizer-phase outcomes retained direct harness terminalization and literal result fields; accounting remained runtime-derived.
- `D-03-C04`: per-target unusable-root labeling repeated the authority status while the top-level status remained distinguishable.

## Material disagreement

The reviewer rejected the cycle-04 repair disposition because suppressing the filesystem error converted an observable failure into false accounting, and the four cited regression cases stubbed the function under test.

## Recommended repair

Distinguish true absence from inaccessibility. Propagate or explicitly return `UNKNOWN` for filesystem faults, allow `_terminalize` to bind `accounting_derivation = UNAVAILABLE`, and never use that observation to deny package-terminal obligations. Guard modeled outcome validation under degraded accounting. Require success accounting to prove all durable starts. Replace stubs with real permission-denied roots.

Verdict: `REJECT`
