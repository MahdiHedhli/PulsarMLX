# F017 Event 06 — V12 Checkpoint-Identity Authority Design, Arbiter Cycle 2

Reviewed exact committed bytes at HEAD `cffb1be47`, detached worktree clean, no files modified, zero checkpoint-root or shard access.

## Cycle-1 reconstruction

Cycle 1 recorded ACCEPT 11, REJECT 3 (`C-INTERFACE-001`, `C-VALIDATE-001`, `C-RUNTIME-002`), UNRESOLVED 2 (`C-SYN-001`, `C-CI-001`), blocking 2, non-blocking-required 5, and global `REJECT`. The blocking findings were the undefined validation triple and runtime-revalidation ordering contradiction.

## Append-only verification

The repair commit contains additions only. Both v1 designs are byte-identical to their prior commit, and each v2 carries an explicit `supersedes` pointer. V10/V11 implementation blobs remain unchanged.

## Direct verification

- `candidate_field_types` types all 28 candidate fields and both installed fields. Unknown fields, aliases, and coercions are rejected. Counts exclude booleans; attempts, retries, and resume are frozen to 1, 0, and false.
- Both scopes have exact disjoint operation domains: `SYNTHETIC` uses `CHECKPOINT_IDENTITY_QUALIFICATION`; `PRODUCTION` uses `CORRECTED_FULL_CHECKPOINT_ORACLE`.
- Candidate and installed triples explicitly enumerate `PRIMARY_CONSUMER`, `SECONDARY_CONSUMER`, and `CHECKPOINT_IDENTITY_PRODUCER`.
- Ordered transitions place all three candidate and all three installed validations before `PACKAGE_CLAIM`.
- Runtime revalidation occurs after `PACKAGE_DURABLE_START`, before `CHECKPOINT_IDENTITY_START`, and before the explicit `CHECKPOINT_SHARD_OPEN` transition.
- Every modeled outcome carries the exact five-field census. Deltas agree with phase, all consumer deltas are zero, and every modeled failure sets `generic_fallback` false.
- Challenge ledger v5 accounts for all 48 historical and current rows. Support ledger v5 accounts for all seven repairs.
- Validation-only counters are zero. Census values derive from committed shard records. Both designs remain non-live and Event 06 remains unexecuted.

## Per-claim verdicts

| Claim | Verdict |
|---|---|
| C-SCOPE-001 | ACCEPT |
| C-SCOPE-002 | ACCEPT |
| C-INTERFACE-001 | ACCEPT |
| C-VALIDATE-001 | ACCEPT |
| C-VALIDATE-002 | ACCEPT |
| C-VALIDATE-003 | ACCEPT |
| C-RUNTIME-001 | ACCEPT |
| C-RUNTIME-002 | ACCEPT |
| C-FAIL-001 | ACCEPT |
| C-FAIL-002 | ACCEPT |
| C-FAIL-003 | ACCEPT |
| C-HIST-001 | ACCEPT |
| C-SYN-001 | ACCEPT |
| C-NOACCESS-001 | ACCEPT |
| C-CI-001 | ACCEPT |
| C-GO-001 | ACCEPT |

Counts: ACCEPT 16, REJECT 0, UNRESOLVED 0. Blocking 0, non-blocking-required 0, unresolved 0.

## Non-blocking observations

1. Post-open `checkpoint_access` is `OBSERVED_PREFIX`, appropriately reflecting a variable durable prefix.
2. Runtime revalidation is one transition; its three-member coverage follows from the immutable installed authority object and required triple verdict.
3. Earlier claim and arbiter ledgers remain historical and are expected to be superseded by this result.

## Global verdict

`ACCEPT_F017_CHECKPOINT_IDENTITY_AUTHORITY_V12_FOR_IMPLEMENTATION`
