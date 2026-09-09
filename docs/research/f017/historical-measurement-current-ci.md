# Historical measurement and current CI

**Work in progress; not CI-complete.** Local qualification passed the original
51 primary-prefix cases, separation/fresh-root controls, and 13 data-only scope
mutations. The unchanged historical generator's Git child terminated with SIGABRT
before its comparison in three bounded attempts. The current-context original
failure reproduction and historical-context original-generator PASS therefore
remain **NOT_QUALIFIED**. That tooling limit stops further same-issue execution;
it does not make either leg optional. The mandatory runner returns failure.

Measurement-v8 remains an immutable record of source head
`f35d341110c67377200ad353ab56a3cf38615a73`, tree
`08864e7d529c91c0ec8f4bf9661006503e6d7dc9`. Its 36 rows are not a claim that
today's source has those bytes. Its original generator and record are unchanged.

The original generator's `--check` combines historical record recomputation
with equality to the active working tree. At source
`6f59d9db93e92afed142b543a0e2fc19e0362bb4` eight paths differ:

| Paths under scripts/research | First relevant published change |
|---|---|
| primary and secondary V11 wrappers | 5b39a21aa8369ea2e53ea8e406002cc74250cec3 |
| primary V11 target source | 1f49d767de96a6cc716fa074580dc2ac73733e3d |
| V11 result envelope and bundle builder | 5b39a21aa8369ea2e53ea8e406002cc74250cec3 |
| V11 full-geometry and failure-campaign qualifiers | 5b39a21aa8369ea2e53ea8e406002cc74250cec3 |
| V11 execution-authority validator | 5b39a21aa8369ea2e53ea8e406002cc74250cec3 |

The minimum-gate change intentionally made prior effectful entry points refuse
execution; current tests assert those refusals. The observation publication and
its subsequent exact relocation preserve a separately measured current primary
path. Restoring all eight old files or refreshing the old measurement would
destroy one of these distinct claims.

## Check locations

The finite workflow inventory contains 97 F017 script references. One invocation
is split; the other 96 retain their exact invocations and existing contexts.
The V6 worktree remains the workflow's already explicit historical context.

| Claim | Mandatory location |
|---|---|
| Original measurement record, exact generator identity, all 36 historical Git objects | scripts/ci/f017_measurement_scope_v1.py --check |
| Original generator itself: current-context refusal and historical-context PASS | Fixed confined CI_ORIGINAL_CURRENT and CI_ORIGINAL_HISTORICAL cases |
| Current wrappers, numerical pins, historical V10 pins, one-execution and terminal gates | Unchanged validate_f017_v11_execution_authority_v1.py invocation |
| Current result authority and bundle behavior | Existing result validators, tests, full-geometry and failure qualifiers, unchanged |
| Current primary source bindings, original prefix matrix and separation controls | scripts/research/tests/f017_primary_confined_ci_v1.py |
| Remaining scientific, readiness, bridge and lifecycle checks | Existing workflow invocations, unchanged and mandatory |

The adapter validates the exact generator's closed output-expression grammar as
data, using actual historical Git blobs and the exact later record commit. The
confined historical control is designed to execute that unchanged generator against
a newly materialized historical source view plus its explicitly later record;
this execution remains unqualified as described above.
It does not execute a historical numerical oracle. It does not overlay the
active checkout or create an authority document.

The current runner reuses fixed synthetic primary cases. Its source-free prefix
is admitted separately, then each owned process seals and proves read, write and
network denial against independent positive controls before importing research
code. Optimization must be disabled. Source views are readonly and hash-checked.
Git execution is permitted only in the two fixed original-generator controls;
other case children cannot execute a process. Artifacts remain in fresh temporary
roots on success or failure. This is scoped fixture confinement, not production
confinement or a universal tooling qualification.

## Limits and finish line

This CI integration does not qualify new scientific or live execution authority.
The tiny result refusal remains `ResultEnvelopeError: numerical output payload
binding`, independently of the old generator's measurement mismatch.

- Primary Python observations describe API-boundary requests, returns and durable
  prefixes, not physical disk traffic or kernel syscall counts.
- Secondary integration still requires explicit dispositions for four source
  bindings and nine helper bindings; none is resolved by this CI change.
- Native loader, positional read and actual unmap observation remain pending.
- Integrated full-forward executor-to-receipt-to-terminal composition remains
  pending. Tiny fixtures are not full-result or representative workload proof.
- Per-shard physical I/O and faults remain unsupported by the current method.
- Historical missing counts remain UNKNOWN_NO_BACKFILL. Ledger remains 175.

No checkpoint or retained event data, GO, replay, P1 authority, local native build,
other-machine activity or historical authority update is part of these checks.
Actual local tests, independent review and hosted CI outcomes must be reported
separately; source publication alone is not acceptance or main readiness.
