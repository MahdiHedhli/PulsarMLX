# F017 Event-04 execution-readiness final review — Opus cycle 04

Reviewer: `claude-opus-5`, high effort, fresh read-only session. Reviewed implementation head `74159013e968dcd592a1b2a099c4976606c1aa0e`, tree `a77e0fcb2a0c622a8c3ce96abce4cbcebb619417`; evidence head `4fa6d127` (docs-only delta, implementation bytes identical). Executed from a byte-identical git-backed scratch clone; the reviewed worktree and clone were byte-clean at the end.

## Reconstructed evidence

Independent AST derivation and live `sys.modules` ground truth produced the same 30 repository-local runtime modules. All were a strict subset of the 38 manifest-bound implementation paths and matched their working bytes. The generator check, runtime authority validator, exact-head measurement, 43 tests, qualification, rehearsal, and FULL_NATIVE run `32817885238` passed. The qualification reproduced 47 outcomes over 201 executions with zero accounting mismatches, generic fallbacks, or uncontrolled modeled failures. Numerical authorities were unchanged and original checkpoint access was zero.

The reviewer ran 111 independent attacks. Complete runtime binding, render/install gate replay, `/tmp` alias rejection, ancestor and leaf symlink rejection, dual-root fallback, no-root five-lease release, durable accounting derivation, controlled-status derivation, root and Git error normalization, partial-root cleanup, and installation-receipt failure banking all otherwise passed.

## Findings

### BLOCKING

- `B-01-C04 UNGUARDED_ACCOUNTING_DERIVATION_LEAKS_RAW_OSERROR_FROM_THE_PRODUCTION_TERMINALIZATION_PATH_AND_DESTROYS_MANDATORY_TERMINAL_EVIDENCE`

  `f017_corrected_oracle_event_accounting_v9.py` called `Path.is_file()` and `Path.is_symlink()` outside its filesystem exception boundary. `execute_f017_corrected_oracle_event_v9.py` called `derive(root)` unguarded from `_terminalize`. On the pinned CPython 3.13.13 runtime, an unsearchable emergency or state root raised `PermissionError`, no failure-terminal capsule was written, and the separately bound fallback root was not attempted.

### NON_BLOCKING_REQUIRED

None.

### DEFENSE_IN_DEPTH

- `D-01-C04`: an unreferenced commit containing byte-identical bound files can serve as the accepted implementation head. Executed bytes remain fully pinned, but review-history provenance is not independently constrained.
- `D-02-C04`: the six authorizer-phase outcomes still use direct qualification-harness terminalization and literals for result/generic-fallback state. Their accounting is runtime-derived.
- `D-03-C04`: an authorized-but-unusable root's per-target error label repeats the authority status. The top-level status still distinguishes the three envelope classes.

## Material disagreement

The reviewer disagreed with the cycle-03 disposition of `D-05-C03` as PASS because the accounting-derivation filesystem surface remained unguarded inside `_terminalize`.

## Recommended repair

Protect all `is_file()` and `is_symlink()` operations with the accounting module's controlled filesystem boundary. Guard `derive(root)` in `_terminalize` so unavailable accounting evidence degrades to a zeroed observation and cannot abort fallback terminalization. Add unsearchable emergency-root and state-root cases to pytest and the full qualification.

Verdict: `REJECT`
