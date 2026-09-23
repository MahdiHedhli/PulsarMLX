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

### 2026-09-21 amendment — required steps bounded by two frozen lineages

Nothing above this heading is changed.

Adversarial review showed the invocation inventory described above was still too
weak. It compared individual script-bearing lines, so it could not see step-level
execution gating, and it returned PASS after each of: `if: false` on a required
step, `continue-on-error: true`, deleting a result assertion, weakening
`unexpected_passes == 0`, and appending `|| true` to a *continuation* line, which
carries no script reference and was therefore never inventoried. Requiring only
that the expected lines still be present, in order, would additionally have
admitted an *inserted* line — `set +e`, `exit 0`, or a re-assignment placed
before an assertion.

A **required step** is now bounded from both sides. Required steps are the steps
in `expected` whose block references a script whose basename contains `f017`,
plus the confined primary leg. For each of them:

* every line of the `expected` block must appear byte-identical and in order —
  so nothing mandatory can be dropped, rewritten, masked or reordered;
* **every line actually present must come from one of two frozen lineages** —
  the qualify workflow at `6f59d9db` or the native workflow at `44c1b34e` — so
  no invented line can live inside a mandatory step, which is what closes the
  inserted-line hole;
* the gating keys `if:`, `continue-on-error:`, `timeout-minutes:`, `shell:` and a
  step-level `env:` must be byte-identical to `expected` and may not be acquired;
* the enclosing job must be the same, its `runs-on:` and job-level `env:` must be
  byte-identical, and required steps must keep their relative order.

Both lineage workflows are pinned by sha256 (`WORKFLOW_ORIGINAL_IDENTITY`,
`WORKFLOW_NATIVE_IDENTITY`). Both are historical commits already in this
history, so neither can drift. Steps that are not required, and steps added
anywhere, remain unconstrained by this doctor.

The two lineages are why the consolidated tree passes at all: exactly one
required step, *Qualify corrected oracle historical and active authority split*,
differs from the qualify lineage, because the native lineage **appended** F017
qualification to it — extra `cargo build` binaries, `cargo test --test temporal
--test session`, the native CLI and temporal differential qualifications each
compared against banked evidence, one further pytest file, and two `--check`
invocations. Nothing was removed, masked or reordered, and the tests assert that
the native block contains every expected line in order, so the two lineages are
consistent rather than merely both allowed.

**Consequence for future work:** a required F017 step can no longer be changed by
editing the workflow alone. Any such change must advance a lineage constant
(`SOURCE_BASE`/`WORKFLOW_BASE_SHA` or `NATIVE_BASE`/`NATIVE_WORKFLOW_SHA256`)
deliberately, which is exactly the review point a change to a mandatory
qualification step should require.

### 2026-09-21 amendment 2 — required steps frozen at the consolidation resolution

Nothing above this heading is changed.

The two-lineage line bound recorded above was still bypassable, and the reason is
structural: any rule expressed over *allowed lines* can be defeated by
**composing** them. Adversarial review demonstrated it — the existing
`cleanup_v6_historical_worktree() {` and its `}` were relocated to wrap a required
step's entire body in a function that is never called. Every required line was
present, in order, from a frozen lineage; the YAML parsed; the shell exited 0; and
none of the enclosed checks ran. Execution could also be redirected from *outside*
the step, where no line-level rule looks at all: a job- or workflow-level
`defaults.run.shell: /usr/bin/true {0}`, a job `if: false`, a job
`continue-on-error: true`, or an injected workflow `env:`.

Line-level rules are therefore abandoned in favour of a **scoped byte-freeze**.
Required F017 steps are frozen at `RESOLUTION_BASE` = `9e145b09`, the merge
commit where the qualify and native lineages were reconciled, pinned by
`RESOLUTION_WORKFLOW_SHA256` and asserted as `WORKFLOW_RESOLUTION_IDENTITY`:

* each required step's **entire block is byte-identical** to that commit, in the
  same job, with required-step order preserved, and its name may not occur twice
  in the workflow — a duplicate elsewhere cannot stand in for it;
* for every job containing a required step, `runs-on`, `env`, `if`,
  `continue-on-error`, `defaults`, `timeout-minutes`, `strategy`, `container` and
  `services` are byte-identical, and a key absent in the resolution must stay
  absent;
* the workflow's own top-level `defaults:` and `env:` are byte-identical or
  absent as in the resolution.

The qualify (`6f59d9db`) and native (`44c1b34e`) identities are retained as
lineage provenance, and the tests still verify that the resolution's required
blocks contain the qualify lineage in order, so the freeze is anchored to a
reconciliation rather than to an arbitrary snapshot.

**Consequence, deliberately stronger than before:** a required F017 step can no
longer be edited *at all* — not even additively — without advancing
`RESOLUTION_BASE` and `RESOLUTION_WORKFLOW_SHA256` in the same commit. That is
the review point a change to a mandatory qualification step should have. Steps
that are not required, and steps added anywhere, remain unconstrained.

### 2026-09-21 amendment 3 — canonical form and residual byte-freeze

Nothing above this heading is changed.

The step-level byte-freeze recorded above was still bypassable, and the reason is
that it compared *key spellings*. Adversarial review installed
`run.shell: /usr/bin/true {0}` under the required job by writing the key as
`"defaults"` — quoted. YAML resolves it identically, every required step inherits
the no-op shell, a script containing `exit 73` returns 0 without running, and the
doctor and all 38 controls passed. Anchored quoted defaults reused through an
alias, an explicit `? defaults`, a tab after `defaults:`, a flow-style
`needs: [classify, documentation]`, and quoted `"continue-on-error"` or
`"strategy"` all did the same.

Enumerating keys is therefore abandoned. Two rules replace it.

**1. Canonical form (`WORKFLOW_NONCANONICAL`).** The whole file must be written
in one spelling, checked over structural lines only — `run:` bodies are shell and
Python, where `!=`, `&&` and `{` are not YAML. Rejected: tabs, anchors, aliases,
merge keys, tags, explicit `? ` keys, quoted mapping keys, flow collections,
duplicate keys within a mapping, duplicate job ids, duplicate step names within a
job, and step items that are not `- name:`, `- uses:` or `- id:` — the three
forms the resolution itself uses.

**2. Residual byte-freeze.** The *residual* of a workflow is the file with every
non-required step block removed, a block carrying the comments written directly
above it. `residual(current)` must equal `residual(resolution)` byte for byte.
That freezes, in one comparison and with no key list to miss: the workflow header
and its `on`, `concurrency`, `permissions`, `defaults` and `env`; every job
header and every job-level key **of every job, including the jobs that contain no
required step** (`classify`, `aggregate`, `evidence-integrity`, `documentation`,
`closed-branch-guard`); and every required step block.

The rule is uniform and applies to every job equally: **everything is frozen
except non-required step blocks.** Those blocks are removed before the comparison
wherever they occur — in the native job, and equally in `classify` and
`aggregate`, whose step bodies are themselves non-required and therefore free.
An earlier wording said the jobs without required steps were frozen "in full";
that was inaccurate, because their step bodies are removed by the same rule as
any other non-required step. What is frozen in those jobs is their header and
job-level keys, not their steps.

**NOTE — what a static inventory cannot promise.** Non-required steps are free
by design, and their *runtime* effects are outside this guarantee. A free step
running earlier in the same job can write `GITHUB_ENV` or `GITHUB_PATH` and so
change the environment or executable lookup of a later required step; can modify
scripts, fixtures, evidence, dependencies or `.venv/bin/python` before a required
step uses them; can fail early and cause later steps to be skipped; and can change
routing outputs that gate dependent jobs. This workflow already relies on exactly
that kind of preparation — the native-MLX step populates `GITHUB_ENV` and a later
step creates the virtual environment. Byte preservation of the frozen regions
therefore does not promise an unchanged execution *outcome*; it promises that the
frozen text has not changed. Extending the guarantee to runtime effects would mean
constraining non-required steps, which is the opposite of the accepted contract.

**Consequence, stronger again:** *any* change to this workflow outside a
non-required step now requires advancing `RESOLUTION_BASE` and
`RESOLUTION_WORKFLOW_SHA256` deliberately in the same commit. That includes the
workflow header, concurrency, permissions, any job-level key, and any job that
runs no required step — not just the required steps themselves.

### 2026-09-22 — the resolution advances for the F020 required steps

The freeze's own mechanism was used, once, deliberately, and this line records
it. `RESOLUTION_BASE` moves from `9e145b09` to
`4f0ed191bd3944550cfa14076109643a15827875` and `RESOLUTION_WORKFLOW_SHA256`
from `4e132d2c…` to `185c2183…`, in the commit immediately after the one that
added two required steps to `apple-mlx-small-fixtures`: `Qualify MLX affine
compatibility (synthetic, pinned MLX wheel)` and `Test MLX affine
representation`. The doctor fails at the first of those two commits and passes
at the second, which is the review point the amendment above was written to
create.

Two things are worth stating plainly.

First, **advancing the base adds required steps; it does not rewrite or drop
one.** All ten required blocks frozen at `9e145b09` are present in
`4f0ed191` byte for byte, in the same jobs and in the same order; the only
difference is the two new blocks. That was verified before the constants moved,
and the doctor's own `resolution contains the qualify lineage in order`
construction check still holds, because the new steps are not part of the
qualify lineage and are skipped by it.

Second, **the required-step selector gained a second rule.** Until now a step
was required exactly when it named a script whose basename contains `f017`.
That was always a proxy for "this step is mandatory", and it stops being one as
soon as a successor feature owns a mandatory gate: F020's native affine
qualification must run, and naming its script `f017_…` to inherit the rule
would have been a lie about what the script is. So
`scripts/ci/f017_measurement_scope_v1.py` now also carries
`REQUIRED_EXTRA_STEP_NAMES`, an explicit list of step names. A name on that
list is frozen exactly like an F017 step, which is why the list is short,
spelled in full, and can only change together with another deliberate advance
of these two constants. The doctor's tests assert the list's contents, the job
the named steps sit in, and the new required-step count of twelve.

The required-step census is therefore 10 → 12 and the free-step census is 39.

### 2026-09-23 — the resolution advances for mixed-range evidence integrity

`RESOLUTION_BASE` moves from `4f0ed191` to
`85b8a002fe8d2955848fe8469f4f7fab077a9e05` and `RESOLUTION_WORKFLOW_SHA256`
from `185c2183…` to `f9f72b1e…`, in the commit immediately after the one that
made the evidence-integrity job also run for ranges that change code and
evidence together. The doctor fails at that commit and passes at this one.

That commit changed exactly two frozen residual lines and no required step:
the classify job gained the output `evidence_touched`, and the
evidence-integrity job's `if:` became `mode == 'EVIDENCE_ONLY' ||
evidence_touched == 'true'`. All twelve required blocks frozen at `4f0ed191`
are present at `85b8a002` byte for byte, in the same jobs and in the same order,
and `REQUIRED_EXTRA_STEP_NAMES` is unchanged. That was verified before the
constants moved. The aggregate job's decision moved out of its inline step
into `scripts/ci/aggregate_status_v1.py`, and a checkout step was added before
it; both are non-required steps, so they are free and not part of the freeze.

The required-step census stays 12 and the free-step census is 40.
