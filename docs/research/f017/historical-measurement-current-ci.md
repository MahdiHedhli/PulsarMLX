# Historical measurement and current CI

**Scoped tooling integration; outcomes are bound by external exact-head receipts.**
The closed predecessor's local qualification passed the original
51 primary-prefix cases, separation/fresh-root controls, and 13 data-only scope
mutations. The unchanged historical generator's Git child terminated with SIGABRT
before its comparison in three bounded attempts. The current-context original
failure reproduction and historical-context original-generator PASS therefore
remained **NOT_QUALIFIED** there. Its cause and inner executing Git image remain
unknown. Those three confined attempts are closed and are not retried here.
The new path explicitly treats only the exact stdlib-only source measurement
generator as trusted preparation outside the numerical sandbox. This is not
confinement qualification or a diagnosis of the earlier abort. Neither original
check becomes optional; any preparation failure stops the aggregate.

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
| Original generator itself: exact current-wrapper ValueError and historical PASS | Fixed CURRENT_ORIGINAL_CHECK and HISTORICAL_ORIGINAL_CHECK trusted preparation roles before numerical sealing |
| Current wrappers, numerical pins, historical V10 pins, one-execution and terminal gates | Unchanged validate_f017_v11_execution_authority_v1.py invocation |
| Current result authority and bundle behavior | Existing result validators, tests, full-geometry and failure qualifiers, unchanged |
| Current primary source bindings, original prefix matrix and separation controls | scripts/research/tests/f017_primary_confined_ci_v1.py |
| Remaining scientific, readiness, bridge and lifecycle checks | Existing workflow invocations, unchanged and mandatory |

The adapter validates the exact generator's closed output-expression grammar as
data, using actual historical Git blobs and the exact later record commit. The
trusted historical control executes that unchanged generator against
a newly materialized historical source view plus its explicitly later record;
the outcome must be reported separately from the data-only adapter.
It does not execute a historical numerical oracle. It does not overlay the
active checkout or create an authority document.

The current runner reuses fixed synthetic primary cases. Its source-free prefix
is admitted separately, then each owned process seals and proves read, write and
network denial against independent positive controls before importing research
code. Optimization must be disabled. Source views are readonly and hash-checked.
Git is never permitted in sealed fixture children. Both original controls are
relocated one-to-one to trusted preparation, with a source-free doctor, exact
closed input/command contracts, fresh independent Git stores, literal `--check`,
readonly current/historical views, and separately retained actual capture/trace
evidence. Historical source cannot satisfy active runtime input gates; current
source cannot masquerade as the historical record. The four named preparation
controllers import no numerical modules. Git Trace2 is self-reported descendant
evidence, not independent OS executing-image attestation. Artifacts remain in fresh temporary
roots on success or failure. This is scoped fixture confinement, not production
confinement or a universal tooling qualification.

The input policy retains protected runtime/fixture content pins from `6f59d9db`.
Controller identity instead binds the actual enclosing committed head and exact
bodies through an external qualification receipt; no self-containing future
commit/hash is embedded in policy. Workflow census totals derive from the frozen
invocation inventory, and all unrelated invocations/order remain unchanged.

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

## 2026-09-20 consolidation note — inventory by invocation, not whole-file bytes

Nothing above this heading is changed.

`verify_workflow_inventory` in `scripts/ci/f017_measurement_scope_v1.py` used to
require the whole of `.github/workflows/macos.yml` to equal its frozen base
(`6f59d9db`) byte for byte, modulo the one substitution that relocated the old
`generate_f017_v11_measurement_v1.py --check` invocation. That was an over-broad
way to enforce this document's actual guarantee — that **every F017 check remains
a separate, mandatory, unaltered invocation in its existing context** — because it
also forbade any unrelated addition anywhere in the file. It therefore could not
survive integration with another track's CI: consolidating the GLM-5.3-Flash and
F017 lines adds steps that have nothing to do with the measurement scope, and the
byte comparison failed on all of them at once with a single opaque label.

The check is now an **ordered invocation inventory**. An invocation is the entire
whitespace-stripped workflow line that references a `scripts/research/...` or
`scripts/ci/...` Python check — interpreter, flags, arguments and any trailing
shell included. The expected invocations, derived from the frozen base exactly as
before, must appear in the current workflow with identical text, in the same
relative order, the same number of times, and under the same `jobs.<name>` key.
Anything else in the file may be added.

The guarantee is therefore unchanged and still exact for every listed invocation:

- a dropped check is a missing expected invocation → rejected;
- an edited check, including a masked one (`|| true`), a redirect, or a changed
  path, is a different line → rejected;
- a check moved to another job — that is, another environment — fails the job
  comparison → rejected;
- a check reordered relative to another expected check breaks the ordered
  subsequence → rejected.

All four continue to raise `WORKFLOW_CHECK_INVENTORY_OR_CONTEXT`, and
`WORKFLOW_ORIGINAL_IDENTITY`, `WORKFLOW_OLD_CHECK_CENSUS` and
`F017_ORIGINAL_CHECK_PRESENT` are unchanged. The returned inventory now also
reports `required_invocations` and `additive_invocations`, the latter being the
number of current invocation lines beyond the required set.

One normalisation is applied: a trailing backslash is line-joining punctuation
rather than part of a command, so it is stripped before comparison. Appending an
argument to a multi-line command gives the previously final argument a `\` without
otherwise changing it; that addition is then inventoried as its own line when it
references a check. This is exactly what the consolidated workflow does — the
`pytest` invocation that ran `test_f017_result_envelope_v11.py` and
`test_f017_result_bundle_builder_v11.py` now also runs
`test_f017_v11_measurement_v2.py` — and it is why that addition is additive rather
than an alteration. No other trailing text is normalised.

The mutation controls in `scripts/ci/f017_measurement_scope_tests_v1.py` cover all
of the above: the five pre-existing rejections keep their labels, and four cases
were added — an unrelated added check is accepted as additive, a duplicated
expected invocation is accepted, a relocated invocation is rejected, and a
reordered pair is rejected.
