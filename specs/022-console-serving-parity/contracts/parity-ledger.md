# Parity Ledger Contract

- **Status**: Normative, version 1, dated 2026-11-14. The ledger file exists as a skeleton
  with every row `pending`; the checker and the evidence it reads are planned work.
- **Feature**: `specs/022-console-serving-parity`
- **Written by**: GOV-06 (this contract and the ledger skeleton). The checker, baseline and
  inventories are built by CNF-12; HTTP-level rows are maintained with the test kit of
  API-19; every work package updates the rows it resolves.
- **Ledger file**: `console/parity/ledger.json`
- **Row listing tool**: `console/tools/list_donor_tests.py`
- **Deviation register**: [deviations.md](deviations.md)
- **Donor**: project-maya at commit `7e68a30f2f208056195352129188661fb6b94445` (v1.1.63)
- **Terms**: "Decision B1" to "decision B13" are the binding cross-cutting decisions
  restated in [`../tasks.md`](../tasks.md), section "Binding cross-cutting decisions".

## 1. What "full parity" means

This section restates section 4 of the approved plan. It is the definition the ledger
measures; nothing here widens or narrows it.

Driven by equivalent fake engines, the Rust implementation shows the same externally
observable behavior as project-maya `serve/` at `7e68a30f` for every route, stream format,
error, configuration key, environment variable and persisted file. project-maya is the
reference even where it differs from the OpenAI or Anthropic specifications, because the
adapted dashboard and maya-compatible clients depend on it. Every intended difference is
an entry in the deviation register with a reason and the owner's approval.

Parity is measured by a parity ledger with one row per donor test method. At the pinned
commit there are 913 such methods in 44 files. Each row resolves to exactly one
disposition (section 3). A checker fails the build on a dangling row (section 5).

Every parity claim in this increment is a claim about synthetic backends. A resolved row
means the behavior was shown against fake engines; it says nothing about a real model.

### 1.1 What counts as observable

Decided by the lead on 2026-11-14. Everything the server sends is observable unless it is
on the volatile list, which is normalized before comparison. The volatile list is:

- generated ids;
- timestamps and `created` fields;
- the `Date` header;
- the value of the `Server` header, until the owner decides proposal P-1 in
  [deviations.md](deviations.md);
- timing and rate figures;
- uptime;
- process ids;
- ports;
- temporary paths.

The HTTP version token, the status line, header names, header order where the donor's
order is deterministic, JSON key order and stream framing are observable. The normalizer
and comparator of package CNF-04 implement this rule; each volatile field it normalizes is
listed in `contracts/volatile-fields.json` with a donor citation.

## 2. Four sources of evidence, and where each runs

| Evidence | What it is | Where it runs |
| --- | --- | --- |
| A. Reference corpus | Requests, responses, streams and rendered-prompt probes captured from project-maya's own server in fake-engine mode at the pinned commit, normalized (ids, timestamps) and committed as text with a provenance header | Capture: the manual reference job (`workflow_dispatch` in `.github/workflows/console.yml`), once per pin. Replay of the committed references against the Rust server: every CI run, offline, in the blocking Rust on Linux job |
| B. Re-expressed donor tests | Donor test methods translated to Rust unit tests, black-box HTTP tests or Node web logic tests, each citing the donor method it re-expresses | Blocking jobs: Rust on Linux, Rust on macOS arm64, and web logic tests under Node with no packages |
| C. Independent tests | Tests written from PulsarMLX Console's own contracts by a different agent from the one that ported the behavior, as ADR 0004 requires; includes the security tests salvaged from the archived serving crate | Blocking jobs |
| D. Client SDK tests | The official `openai` and `anthropic` Python clients parse the server's output | Manual job, pinned by hash |

Further manual jobs feed specific dispositions: the live differential against project-maya
at the pinned commit, the shim runs of donor test files, and the vendor-template render
checks, which record hashes, never template text (decision B4). project-maya code runs only
in the manual GitHub Actions reference job, never on a developer machine and never in a
blocking job (decision B9, plan section 9).

**Adjustment to the earlier conformance design.** The conformance design proposal written
before the plan was approved (a planning record outside the repository) placed the live
differential, golden freshness and the shim tier in a CI job that runs on every push. The
approved plan keeps reference capture and the live differential manual (decision B12)
and keeps third-party code out of blocking jobs. This contract follows the plan: **the
blocking gate replays committed references**; it never runs the donor. A committed
reference can therefore go stale only between manual runs, and the manual job reports
staleness as its own failure class.

The lead decided on 2026-11-14, refining the plan's evidence table (which lists the two
shim files under blocking CI), that two kinds of run happen only in the manual reference
job: the two donor test files that run as-is against the Rust artifacts through a shim
(`serve/test_engine_contract.py` and `serve/test_stop.py`), and the vendor-template
renders. Blocking CI checks their committed records (dispositions `shim` and
`vendor-render` in section 3.2).

## 3. Ledger schema

`console/parity/ledger.json` is one JSON object, written by the listing tool and then
edited row by row by the packages. Top-level fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `ledger` | string | The fixed title "PulsarMLX Console parity ledger" |
| `donor` | object | `project`, `repository`, `commit` (full 40-character SHA), `scope` (`serve/test_*.py`) |
| `listing_tool` | string | `console/tools/list_donor_tests.py` |
| `count` | integer | Number of rows; 913 at the current pin |
| `rows` | array | One object per donor test method, sorted by `id` |

### 3.1 Common row fields

Every row has these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | The key `file::Class::method`, for example `serve/test_attach.py::ApiParts::test_anthropic_documents`; a module-level test function is keyed `file::function` |
| `file` | string | Donor file, relative to the donor root |
| `class` | string or null | Donor class; null for a module-level function |
| `method` | string | Donor method or function name |
| `subsystem` | string | The console subsystem responsible, as a short label |
| `disposition` | string | One of the eight values in section 3.2 |

Optional on every row:

| Field | Type | Meaning |
| --- | --- | --- |
| `package` | string | The work package id that resolved the row, for example `ENG-09` |
| `upstream_skipped` | string | Present when the donor's own CI skips the method (for example for lack of the OpenAI SDK, poppler, a pack tokenizer or `MAYA_TEST_ENGINE`), with the reason. It does not change the disposition: the row still needs one, and nobody may assume the method was ever green upstream |
| `notes` | string | Free text for the reviewer |

No other fields are allowed. The checker rejects an unknown field, so a misspelled field
cannot silently carry evidence.

### 3.2 Dispositions and the fields each requires

| Disposition | Meaning | Required fields | Evidence source |
| --- | --- | --- | --- |
| `rust-test` | One or more Rust tests re-express the donor method | `rust_tests`: non-empty array of test paths exactly as `cargo test -- --list` prints them, each prefixed by its crate and test target, for example `console-core::fifo::tests::arrival_order` | B (blocking) |
| `scenario` | One or more recorded scenarios cover the method | `scenarios`: non-empty array of scenario ids; each id names a scenario file under `console/conformance/` that has a committed reference | A (replayed in the blocking job) |
| `shim` | The donor test runs unchanged against the Rust artifact | `shim`: the shim runner (`engine-contract` or `stop`); `shim_record`: the path of the committed result record of the last manual shim run at the pin | Manual job; the blocking checker verifies only the committed record (section 5) |
| `web-test` | A Node test of the adapted dashboard re-expresses the method | `web_tests`: non-empty array of `console/web/<path>.test.mjs::<test name>` | B (blocking, Node with no packages) |
| `vendor-render` | A vendor-template render case covers the method; the case runs only where the template can be read lawfully (decision B4, deviation LIC-1) | `vendor_cases`: non-empty array of case ids; `vendor_record`: the path of the committed hash record of the last manual run | Manual job; the blocking checker verifies only the committed record |
| `deviation` | The behavior differs on purpose under an approved register entry | `deviation`: a register id or sub-item id, for example `SEC-5` or `SEC-5.2`; `asserted_by`: non-empty array of `rust_tests`, `web_tests` or `scenarios` entries that pin the PulsarMLX Console behavior | B or A, through `asserted_by` |
| `not-applicable` | The method tests something outside this increment | `reason`: one value from the closed list in section 3.3; `notes`: one sentence naming what the method depends on | None |
| `pending` | Not yet resolved | none | None |

A row has exactly one disposition. A donor method that is covered by both a Rust test and
a scenario takes the disposition that carries the stronger evidence for its assertions,
and may name the other in `notes`.

### 3.3 Closed list of not-applicable reasons

| Reason | Use it when the donor method |
| --- | --- |
| `engine-source-reads` | reads or greps project-maya engine sources (C++, CUDA, Metal) or the server's own Python source text, which have no counterpart in the Rust tree |
| `launcher-only` | imports or drives the donor's launcher (`maya.py`, `setup.py`, `maya.sh`) or tests behavior that exists only there |
| `needs-real-pack-or-GPU` | needs a real model pack, tokenizer pack or GPU, which no synthetic backend can supply |
| `Windows-only-process-model` | tests Windows process behavior that has no POSIX counterpart and cannot be type-checked into meaning |

This list is closed. Adding a reason is a change to this contract, reviewed like any other
contract change. A behavior that PulsarMLX Console implements differently is never
`not-applicable`: it is a `deviation`.

### 3.4 Example rows

```json
{
  "id": "serve/test_fair.py::FairLockOrder::test_waiters_get_it_in_arrival_order",
  "file": "serve/test_fair.py",
  "class": "FairLockOrder",
  "method": "test_waiters_get_it_in_arrival_order",
  "subsystem": "console-core (scheduler)",
  "disposition": "rust-test",
  "package": "ENG-09",
  "rust_tests": ["console-core::fifo::tests::arrival_order"]
}
```

```json
{
  "id": "serve/test_update.py::Updating::test_update_moves_to_the_tag_and_ends_for_maya_py",
  "file": "serve/test_update.py",
  "class": "Updating",
  "method": "test_update_moves_to_the_tag_and_ends_for_maya_py",
  "subsystem": "console-manage (update contract)",
  "disposition": "deviation",
  "package": "OPS-22",
  "deviation": "SEC-5.2",
  "asserted_by": ["console-manage::update::tests::post_never_updates"]
}
```

The test paths in these examples are illustrations of the format, not existing tests.

## 4. How the row list is produced

1. **Static listing, never execution.** `console/tools/list_donor_tests.py` reads each
   `serve/test_*.py` file of the pinned donor checkout as text and parses it with Python's
   `ast` module. It never imports, executes or evaluates donor code, and it runs no `git`
   command inside the donor checkout. It is run with an isolated interpreter
   (`python3 -I`), from outside the donor checkout, with the donor path as an argument.
2. **What counts as a test.** A `def test*` or `async def test*` written directly in the
   body of a module-level class, keyed `file::Class::method`; or one written directly at
   module level, keyed `file::function`. Inherited methods are not repeated under a
   subclass, and nested functions are not listed.
3. **Writing the ledger.** With `--write-ledger console/parity/ledger.json` the tool
   writes the ledger. Existing rows keep their subsystem and disposition; new rows start
   `pending`. It refuses to drop a row, and it refuses a donor checkout at a commit other
   than the ledger's pinned commit.
4. **Who runs it.** The listing runs where donor source is available as data: the manual
   reference job, or a developer's own read-only checkout. Parsing the donor's text with
   `ast` is not executing it.

### 4.1 Re-pinning the donor

Re-pinning project-maya to another commit is a separate owner decision (plan section 12;
OPEN-28 in the register of open items).
The tool's refusals in step 3 exist so that a re-pin cannot happen by accident. When the
owner approves a re-pin:

1. The new commit is recorded as a full SHA, with a new file-hash manifest for the manual
   reference job.
2. The listing is produced again at the new commit through an explicit re-pin path of the
   tool (to be added by CNF-12), which reports every added, removed and renamed row.
3. Removed rows are deleted only with that report reviewed; added rows start `pending`;
   rows whose donor method changed text are reset to `pending` for re-review.
4. The reference corpus is captured again in the manual job, and the vendor-render and
   shim records are re-run.
5. The deviation register is re-checked: a donor line it cites may have moved or changed.

## 5. Checker rules

The checker is built by CNF-12 and runs in the blocking Rust on Linux job. It reads the
ledger, the register and the evidence listings, and fails the build when any rule fails.

1. **Row set.** The rows are exactly the listing at the pinned commit: same count (913 at
   `7e68a30f`), same ids, sorted, no duplicates.
2. **One disposition.** Every row has exactly one disposition from section 3.2 and every
   field that disposition requires, and no field outside section 3.1 and its own required
   fields.
3. **Every reference resolves.**
   - Every `rust_tests` entry appears in the `cargo test -- --list` output of the same job.
   - Every `scenarios` entry names a scenario file with a committed reference, and that
     reference was replayed in the same run.
   - Every `web_tests` entry appears in the Node test listing of the web logic job.
   - Every `deviation` value is an id or sub-item id present in the register and marked
     approved there.
   - Every `shim_record` and `vendor_record` exists, names the pinned commit, and lists the
     row's method as passed.
   - Every `reason` is in the closed list.
4. **Pending rows.** Before close-out, pending rows are allowed and reported as a count per
   subsystem in the ledger report. At close-out (M10) the gate requires **no pending
   rows**.
5. **Unused deviation entries are flagged.** A register id or sub-item that no row and no
   comparator annotation references is reported as unused, so a deviation cannot linger
   without a test that shows it. The report lists it for the lead's review.
6. **Package gate.** A package is not done until the ledger rows it claims resolve, as its
   definition of done in `tasks.md` states (plan section 10).
7. **Report.** Each run writes a ledger report: counts by disposition and subsystem, unused
   deviation entries, rows marked `upstream_skipped`, and the evidence job each manual
   record came from.

## 6. Relation to other checks

- The comparator that replays references suppresses a difference only with an approved
  register id as its annotation, and flags unused annotations (CNF-04).
- The inventory extractor (CNF-12) lists environment names, routes and written files from
  the pinned source statically; their coverage is checked against the HTTP, ops and naming
  contracts, not against this ledger.
- Evidence C and D attach to subsystems rather than to donor rows. The ledger report lists,
  per subsystem, the independent test families that cover it; a package is not done until
  its subsystem has at least one.

## 7. Open items

Each open item is also listed in the register of open items,
[`../checklists/analysis.md`](../checklists/analysis.md), under the id in the last column,
which also says who decides it.

| Id | Item | Register |
| --- | --- | --- |
| L1 | Resolved, no longer open: the lead's decision recorded in section 2 (shim runs and vendor-template renders are manual; blocking CI checks their committed records) refines the plan's evidence table. | none |
| L2 | Resolved, no longer open: section 1.1 records the lead's decision on what counts as observable and what is volatile. | OPEN-37 (settled) |
| L3 | The exact format and location of `shim_record` and `vendor_record` files, and how the manual job's run id is recorded in them (CNF-10, CNF-11, CNF-12). | OPEN-38 |
| L4 | Whether the ledger stores the donor's baseline pass and skip results, produced by running the donor's suite in the manual job, as a separate file or as the `upstream_skipped` field only. | OPEN-36 |
