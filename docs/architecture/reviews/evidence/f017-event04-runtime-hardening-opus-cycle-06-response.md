# F017 Event-04 execution-readiness final review — Opus cycle 06

Reviewer: `claude-opus-5`, high effort, fresh read-only session. Reviewed measurement head `5869bb436acc7fca4c1a4c1e2d5a774eb8d91f45`, tree `66d40a03e8f134034896e3f339b2e345e6dd7987`, and evidence head `918f9e863db2a31234a228c6ff3c86166252e9ff` from a byte-identical Git-backed scratch clone.

## Reconstructed evidence

The generator check, runtime authority validator, 38-binding/30-module measurement, 45 tests, full qualification, rehearsal, and FULL_NATIVE run `32826372881` all passed. Qualification reproduced 50 packages, 47 outcomes over 201 executions, zero generic fallbacks, zero accounting mismatches, zero uncontrolled modeled failures, all five graph shards for both consumers, 1,410 graph tensors, 399 non-access denials, and all 11 formats. Numerical authorities were unchanged. Original checkpoint access, Event-04 authorization and execution, and P1 attempt 2 were absent. Active generation remained `NONE`; historical ledger remained 175.

The cycle-05 real permission-denied repair was confirmed: true absence returns false, unreadable or unsearchable durable evidence raises `PermissionError`, redirected or wrongly typed evidence raises `ValueError`, malformed bytes raise a controlled value error, and both committed permission tests use real `chmod(0)` roots without replacing `derive`, `_valid`, or the banker. The success boundary also rejects completion unless package, primary, and secondary starts each derive delta one. The measurement head contains its matching generated manifest.

## Findings

### BLOCKING

- `B-01-C06 ACCOUNTING_ROOT_SUBSTITUTION_OR_UNUSABLE_ROOT_CAN_STILL_DENY_EXISTING_DURABLE_STARTS`

  `_terminalize` derives accounting from whichever root remains selectable after `_safe_evidence_root` evaluation. If the original state root is replaced by a symlink, recreated, or otherwise becomes unusable, selection can fall back to a different safe root containing no durable-start artifacts. `derive` then reports a successful zero observation, `package_terminal_evidence` is false, and no package terminal is banked even though package or consumer durable starts remain on disk at the original identity. The existing `last_completed_transition_id` can contradict the zero observation but is not used to conservatively preserve the package-terminal obligation.

### NON_BLOCKING_REQUIRED

- `N-01-C06 RECURSION_ERROR_FROM_A_MALFORMED_DURABLE_START_ARTIFACT_ESCAPES_TERMINALIZATION_WITH_NO_CAPSULE_IN_EITHER_BOUND_ROOT`

  A deeply nested JSON durable-start artifact makes `json.loads` raise `RecursionError`. `_valid` normalizes Unicode and value errors but not this decode failure; `_terminalize` catches only value and OS errors around accounting derivation. The recursion exception can therefore escape without a capsule in either bound root.

### DEFENSE_IN_DEPTH

- `D-01-C05` was closed by measuring the implementation and matching generated manifest at `5869bb43`.
- `D-01-C04` remains: implementation-head provenance is constrained by exact bytes rather than review-history ancestry.
- `D-02-C04` remains: six authorizer-phase outcomes use direct harness terminalization with literal result fields; their accounting remains runtime-derived.
- `D-03-C04` remains: per-target unusable-root labels repeat the authority status while top-level status remains unambiguous.
- `D-01-C06`: the twelve DID closure values are a generated literal census rather than independently derived per-DID proofs.

No defense-in-depth finding was promoted to blocking or required.

## Material disagreement

The reviewer rejected the cycle-05 disposition's claim that package terminalization is conservatively required in every degraded-root case. The repair covered read failure at the selected root, but not substitution or loss of the original evidence-root identity. The reviewer also found the malformed-recursion path outside the claimed controlled exception boundary.

Verdict: `REJECT`
