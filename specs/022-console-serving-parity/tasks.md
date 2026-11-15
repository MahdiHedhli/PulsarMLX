# Tasks: 022-console-serving-parity

**Feature**: PulsarMLX Console serving parity (`specs/022-console-serving-parity/`)

**Branch**: `feat/022-console-serving-parity`

**Date**: 2026-11-14

**Status**: Planned. No task in this list is implemented. When the work is built, the
strongest claim any task can support is "qualified on synthetic backends": no real model is
served, no donor engine runs, and hardware readers are verified only against fixtures.

**Input**: the owner's approved plan of 2026-11-14, the lead decisions of the same day
recorded in this file, and the seven planner records of the same day, which broke the
increment into work packages. The approved plan's decisions are restated in
[spec.md](spec.md), [plan.md](plan.md) and ADR 0008. The planner records, and the architect
proposals of the design panel that preceded them, are planning documents that are not in
the repository: what this list takes from them is restated here and, verbatim, in the
detail files under `tasks/`, and nothing in them is a decision unless the approved plan or
a lead decision recorded here adopts it.

**Prerequisites**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md).

**Tests**: Required for every package. Parity is proven test by test against the donor,
project-maya at commit `7e68a30f` (v1.1.63), and recorded in the parity ledger
`console/parity/ledger.json` (one row per donor test method, 913 rows).

## How to read this file

This is the complete task list of the increment: 131 tasks. Six are governance tasks
(GOV-01 to GOV-06) for milestone M0. The other 125 are the work packages of the planner
records after four merges: PRM-01 merges into API-01 (one `console-pyjson` crate); OPS-01
merges into API-01 (the JSON writer) and API-15 (the run-config document store); CNF-05
merges into ENG-05 (one set of fake engine binaries, in `console-fake-engines`); CNF-06
merges into RSP-08 (one fake MCP server). The merged ids do not appear as tasks; their donor
sources and parity tests are folded into the task that absorbs them. WEB-P2-01 to WEB-P2-03
are Phase 2 roadmap items in `docs/roadmap/CONSOLE_ROADMAP.md`, not tasks of this increment.

Phases are milestones M0 to M10, in the order the approved plan fixes. Each task has this
shape:

```text
- [ ] <ID> [P] [Mn] <title> — <target crate or path>
  - Depends on: <ids that must be done first>. Seams: <ids in later milestones>
  - Donor sources: <file:lines relative to the donor repository root>
  - Parity tests: <donor test files, classes and method counts>
  - Risk: <level and reason>
  - Done when: <definition of done, condensed from the planner record>
  - Note: <reconciliation or deviation, when one applies>
  - Detail: <link to the full package text>
```

- **ID**: the work package id from the planner records, or GOV-01 to GOV-06. Ids are not
  renumbered into T001 form, so every review, ledger row and commit can cite the same id.
- **[P]**: the task has no prerequisite inside its own milestone, so it can start as soon as
  its milestone opens and its earlier-milestone prerequisites are done, in parallel with the
  other [P] tasks. A task without [P] waits for the tasks named in its "Depends on" line
  that share its milestone.
- **[Mn]**: the milestone. It takes the place of the template's user-story label, because the
  milestone order is binding and most packages serve several stories. The user stories are
  defined in [spec.md](spec.md); the table below shows which milestones deliver each of them.
- **Depends on** lists hard prerequisites, all in the same or an earlier milestone. Free-text
  dependencies in the planner records ("CORE run loop", "MANAGE savings summary") are
  translated to the ids that provide them.
- **Seams** lists packages in a later milestone that this task calls through a trait or hook.
  The task exposes the seam with an inert default and does not wait for them; the later
  package owns the joint tests. The task's checkbox is ticked only when its full definition of
  done holds, which can be after the seam package lands (see R13).
- **Donor sources** are paths relative to the donor repository root at the pinned commit; an
  `L` before a number also means a line. Parenthetical descriptions from the planner records
  are dropped here and kept in the detail files. Donor files are read as data; they are never
  executed locally (B9).
- **Parity tests** gives donor test files with class names and method counts as the planners
  counted them. The ledger, generated from the pinned donor files, is authoritative for
  counts.
- **Done when** condenses the planner's definition of done into one or two sentences. The
  full definition in the detail file still applies and is not softened by the condensation;
  where it conflicts with a binding decision, the binding decision wins.
- **Detail**: full package text (behaviors, tests, sizes, new dependencies) is in
  `tasks/api.md`, `tasks/engine.md`, `tasks/prompt.md`, `tasks/responses.md`, `tasks/ops.md`,
  `tasks/web.md` and `tasks/conformance.md`, anchored by lower-case id. The GOV tasks have no
  detail file; their entry here is complete.

| Milestone | User stories in [spec.md](spec.md) it mainly delivers |
| --- | --- |
| M0 | Prerequisite for all; US9 starts with the ledger skeleton |
| M1 | US1 (streamed chat completion), US2 (loopback security posture), US9 (test kit, scenarios) |
| M2 | US4 (Anthropic clients and tool-calling agents) |
| M3 | US8 (backend seam and line-protocol engines), US2 (engine lifecycle) |
| M4 | US2 (binary start and stop), US7 (monitoring) |
| M5 | US5 (Responses API) |
| M6 | US6 (MCP tools and attachments) |
| M7 | US7 (model management) |
| M8 | US3 (dashboard with the synthetic badge), US7 (Apple Silicon monitor view) |
| M9 | US7 (GPU-era monitor paths, fixture-verified only) |
| M10 | US9 (parity measurement and close-out) |

## Binding cross-cutting decisions

These decisions come from the approved plan and the milestone assignment. **They override
any conflicting text in a planner record, in a detail file under `tasks/`, or in a task entry
below.** Where a task entry seems to say otherwise, the decision applies and the entry is a
defect to report.

- **B1. Transport.** HTTP/1.0 with the connection closed after each response, hand-written on
  `tokio` and `httparse`, for byte-level parity with the donor. No `hyper`, no `axum`.
  Pointer added on 2026-11-15: the transport's request-head parser is written by hand,
  without `httparse`, for the same purpose (lead decision LD34, R29).
- **B2. Names.** The canonical environment prefix is `PULSAR_CONSOLE_`. Legacy `MAYA_*` and
  `STRATA_*` names are not accepted as aliases. The published old-to-new table lives in
  [contracts/naming.md](contracts/naming.md). Variable names inside a run config `env` block
  that are passed through to engine child processes are opaque data and pass through
  verbatim. The wire names `strata_resume`, `strata_mcp`, `strata_tune`,
  `strata_level_default`, `/v1/strata/stream` and `/v1/strata/cancel` are kept unchanged.
  Run-config files use the prefix `pulsar-`; note files are `.pulsar-*`. Browser storage uses
  the prefix `pulsar.` and the IndexedDB database `pulsar-console`. The log prefix is
  `[console]`. The emitted sealed-reasoning prefix is the product one; whether the donor
  prefix is accepted on input is open item OPEN-01. Test-harness switches and the control
  variables of the fake engines and the fake MCP server are covered in R5.
- **B3. JSON.** `serde_json` with `preserve_order` and `arbitrary_precision` across the
  workspace, and one Python-compatible writer in `console-pyjson` used for every wire body and
  persisted file.
- **B4. Templates.** `minijinja` plus `minijinja-contrib` with a Python-compatible `tojson`.
  Vendor chat templates are never committed. When no template is configured, start-up fails
  with a clear error; there is no bundled vendor fallback. Tests use PulsarMLX-authored
  synthetic templates. Vendor-template checks run only in the manual job and record hashes,
  not text.
- **B5. Tokenizer.** A new `console-tokenizer` crate; no path dependency on any crate outside
  `console/`.
- **B6. No `rmcp` and no `jsonschema` crate.** The MCP client and the restricted JSON Schema
  validator are written in-house.
- **B7. Outbound network** only through one facade over the system `curl`; no TLS crate in
  this increment. The release check is opt-in. Remote image URLs and local image paths are
  opt-in (SEC-4).
- **B8. Security posture** SEC-1 to SEC-7 applies to every route from the first HTTP package
  on, taking the archived PulsarMLX serving crate (tag
  `archive/2026-09-21/feat/openai-serving`, `crates/serve-synthetic`) as the reference for
  Host, Origin, content-type and token handling and for its raw-HTTP tests.
- **B9. Fakes.** The fake engines and the fake MCP server are Rust binaries in
  `console-fake-engines` and in `console-mcp` test support. The donor's Python fakes are never
  executed locally. project-maya code runs only in the manual GitHub Actions reference job.
- **B10. Not built in this increment:** the MiniMax picture preprocessor (LIC-2); the
  refusal-ablation switch and its config keys (POL-1: the capability flag is recognized and
  refused unless an engine advertises it); self-update (SEC-5: route shapes only); any real
  model catalog entry (the catalog ships empty); launching any project-maya engine binary.
- **B11. Hardware and OS specific ports** (PLAT-1) come last (M9), behind traits,
  fixture-tested, type-checked for Linux and Windows in CI, and labeled unverified on real
  hardware.
- **B12. CI.** `.github/workflows/console.yml` is path-filtered, runs every job from
  `console/` on the pinned toolchain 1.97.1, and keeps blocking jobs small: preflight, Rust on
  Linux, Rust on macOS arm64, and web logic tests under Node with no packages. Reference
  capture, the live differential, vendor-template checks, SDK client tests, the drift canary
  and browser end-to-end tests are manual `workflow_dispatch` jobs.
- **B13. Test data** directories are named `testdata/` or `tests/data/`, never `fixtures/` at
  the console root and never a name the repository `.gitignore` drops. Generated fixtures are
  built in code; no binary file is committed.

The deviations from literal parity that the owner approved with the plan (SEC-1 to SEC-7,
PRIV-1, BRAND-1, BRAND-2, LIC-1, LIC-2, POL-1, PLAT-1 to PLAT-3, FIX-1) are recorded in
[contracts/deviations.md](contracts/deviations.md), together with PLAN-1 to PLAN-6, the
differences the plan decides outside its deviation table (the synthetic badge and health
report, a synthetic default model name, embedded assets with no filesystem path served,
license notices reachable from the About page, the always-available schema validator, and
HTTPS MCP through the curl facade). Planner proposals that no approved id covers were listed
there, before checkpoint 1, under "Proposed, awaiting owner decision"; that section is now
split into "Approved proposals", "Declined proposals" and "Deferred, awaiting owner
decision".
Amended on 2026-11-14: the owner decided those proposals at checkpoint 1 (R29). P-1 to P-4,
P-6 to P-11 and P-13 to P-16 are approved deviations under their `P-` ids; P-12 and P-17
are declined and not built; P-5 and P-18 still await the owner. Under lead decision LD29
(OPEN-39, settled by the lead on 2026-11-14), an approved proposal keeps its `P-` id, a
later approved deviation that was never a listed proposal takes the next free `P-` number,
no id is reused, and a declined proposal keeps its id, marked declined. Task entries cite
deviation ids where they apply.

## Reconciliations

Each item names a place where a planner record (or an architect proposal of the design panel)
conflicts with a binding decision, with the approved plan, or with another planner record
after the merges, and states how this task list resolves it. Resolutions marked "decided by
the lead on 2026-11-14" record a lead decision made after this list was first drafted; each
applies a binding rule to a case it does not name or settles a choice the approved plan
leaves to the lead, and none adds an owner decision.

**R1. HTTP version and framework (B1).** Two architect proposals built the server on `hyper`
and a third used an HTTP/1.1 test client; the conformance planner left "HTTP/1.0 or HTTP/1.1
with chunked bodies" as an open question; the dashboard planner asked the HTTP subsystem for
"HTTP/1.1 keep-alive"; the API planner titled API-02 "HTTP/1.x transport". Resolution:
HTTP/1.0, connection closed after every response, no chunked response encoding, hand-written
on `tokio` and `httparse`. API-02 is retitled accordingly. The dashboard works over
close-delimited responses, as it does against the donor.

**R2. `hyper` in test fixtures (B1).** RSP-08 assumed a `hyper` server feature for the fake
MCP server's HTTP mode, CNF-03 self-tests against "an in-test hyper or std server", and
OPS-16 tests against "a loopback hyper fixture server". Resolution: no `hyper` dependency is
added; fixture servers use `std::net` or the in-house transport from API-02. Decided by the
lead on 2026-11-14: no `hyper` anywhere, including test-only fixture servers, so B1 applies
to test code as well.

**R3. Legacy names are not aliases (B2, BRAND-1).** The engine planner proposed reading every
setting through a layer that accepts `MAYA_X` and `STRATA_X` as lower-precedence aliases. The
API planner would accept the old `--engine` values if the owner approved, and planned API-17
to re-express `test_old_engine_name` "for the renamed engine flag and the accepted alias".
RSP-01 lists two donor alias-precedence tests. API-15, OPS-02 and ENG-05 cite
`tools/maya_names.py`, which implements the donor aliasing. Resolution: no legacy name is
accepted, as an environment variable, a CLI value or a config key. Each donor test that
asserts an alias is re-expressed to assert that the legacy name is refused or ignored, and
its ledger row cites BRAND-1. `tools/maya_names.py` is cited only for the names it maps.

**R4. One name table (B2).** API-15 planned "a settings table in specs/022", OPS-02 planned
`contracts/ops-environment.md`, the prompting planner planned its own mapping table, and
CNF-02 planned `contracts/rename-map.json`. Resolution: the single published table is
[contracts/naming.md](contracts/naming.md). Package tests check their Rust tables against it;
a machine-readable rename map used by the scenario loader is derived from it and checked
against it. No second table is maintained.

**R5. Test-harness environment variables (B2).** The planners named test switches with a
`CONSOLE_` prefix (vendor directory, require-vendor, browser end-to-end, require-Node, pack
tokenizer). Resolution: B2 states one canonical environment prefix, so these switches take
`PULSAR_CONSOLE_` as well and are listed in the name table. Decided by the lead on
2026-11-14: switches read by the product or its tests use the `PULSAR_CONSOLE_` prefix,
while the control variables of the fake engines (ENG-05) and the fake MCP server (RSP-08)
keep the names the donor fakes use, because they are a test-double interface, not product
identity. The lead also decided on 2026-11-14 that each test-only setting and test-harness
switch takes the mechanical name `PULSAR_CONSOLE_<old suffix>` listed in
[contracts/naming.md](contracts/naming.md).

**R6. Sealed reasoning prefix (B2).** The Responses planner proposed emitting a new prefix and
also accepting the donor's prefix on input. Resolution: the emitted prefix is the product one
named in the name table; acceptance of the donor prefix on input stays open (OPEN-01) and is
not implemented until decided.

**R7. Wire names stay (B2).** The API, dashboard and Responses planners asked whether to
rename `strata_*` fields and `/v1/strata/*` routes with aliases. Resolution: they are kept
unchanged and no alias is added.

**R8. One Python-compatible JSON writer (B3).** Three writers were planned: API-01 in
`console-core::pyjson`, PRM-01 as the `console-pyjson` crate, OPS-01 in
`console-manage::registry::pyjson`. API-01 also limited itself to `serde_json` with
`preserve_order` only, while PRM-01 added `arbitrary_precision`. Resolution: one
`console-pyjson` crate (API-01, absorbing PRM-01 and the OPS-01 writer) with both features
enabled workspace-wide. The planners disagreed on generating ids with the `uuid` crate or
in-house. Decided by the lead on 2026-11-14: no `uuid` crate; ids are random hexadecimal
drawn from operating-system randomness.

**R9. Templates (B4).** PRM-03 specified `minijinja` "with no minijinja-contrib". PRM-02,
PRM-03, PRM-05, PRM-08, PRM-15 and ENG-17 planned vendor-gated tests run against a local
donor checkout, and PRM-17's definition of done required "CI with the pinned project-maya
checkout". Resolution: `minijinja` plus `minijinja-contrib` with a Python-compatible
`tojson`. Blocking jobs use synthetic templates only; every vendor-gated or donor-checkout
test runs only in the manual job, which records hashes, never template text, and outside it
those tests report skipped, never passed. A missing template is a start-up error (PRM-08).

**R10. Donor code is never executed locally (B9).** CNF-05 required `test_engine_contract.py`
to pass "when run locally" against the Rust fake; CNF-06 planned cross-runs of the donor hub
against the Rust fake MCP server; PRM-02 verified a vendor manifest "against the scratch
clone". Resolution: all of this moves to the manual GitHub Actions jobs (CNF-09, CNF-10,
CNF-11). Locally and in blocking jobs, donor files are at most read as text. Decided by the
lead on 2026-11-14, refining the approved plan's evidence table, which put the shim under
blocking CI: the two donor test files that run as-is against the Rust artifacts through a
shim (`serve/test_engine_contract.py` and `serve/test_stop.py`, CNF-10) and the
vendor-template renders (CNF-11) run only in the manual reference job, and blocking CI
checks their committed record. The ledger dispositions are therefore `rust-test`,
`scenario`, `web-test`, `shim`, `vendor-render`, `deviation`, `not-applicable` and
`pending`. Amended on 2026-11-14: this lead decision was reported to the owner at checkpoint
1, and the owner raised no objection (R29).

**R11. Duplicate fakes and crates.** CNF-05 and ENG-05 both planned fake engine binaries, and
CNF-06 and RSP-08 both planned a fake MCP server; the approved merges resolve both. ENG-14
and RSP-18 both planned a fake vision encoder binary (one in `console-fake-engines`, one in
`console-media`). Resolution, following B9 and the CNF-05 merge: one fake vision encoder in
`console-fake-engines`, built by ENG-14 and used by RSP-18; decided by the lead on
2026-11-14. API-19 and PRM-02 both created `console-testkit`: API-19 creates it in M1 and
PRM-02 extends it in M2. OPS-01's run-config document store becomes part of API-15's
`RunConfigStore`.

**R12. PRM-04 is in M1 but its planner depended on PRM-02 (M2), and API-19 and PRM-04
depended on each other.** The milestone assignment is binding. Resolution: PRM-04 depends
only on API-01; its tests build their synthetic vocabularies in code (B13). API-19 depends on
PRM-04 for the byte tokenizer. When PRM-02 adds the shared synthetic trainer, PRM-04's tests
may switch to it without changing expectations. Decided by the lead on 2026-11-14: PRM-04
does not depend on PRM-02, not even as a seam.

**R13. Dependencies on later milestones.** Several packages depend on work the binding
assignment places later: API-07 on the attachment planner (RSP-16), engine reload state
(ENG-12) and the updater (OPS-22); API-08 on prompt parsers (M2) and MCP (RSP-11); API-06,
API-14, API-17 and API-20 on M5 to M8 views; API-19 on the fake engine binary (ENG-05);
RSP-06 and RSP-07 on media (M6); WEB-04 and WEB-11 on M9 packages. Resolution, confirmed
by the lead on 2026-11-14: these are listed as "Seams". The earlier package defines
the trait with an inert default and does not wait; the later package owns the joint tests
and updates the earlier package's tests when it lands. No definition of done is reduced: a
task whose full definition needs a seam package stays unticked until it lands. A milestone
exits when its deliverable in the approved plan is met; M1, for example, needs only "chat
completions for plain content" from API-08.

**R14. Branding assets (BRAND-1, BRAND-2, B13).** WEB-01 planned `console/web/fonts/` with
Outfit font files and `OFL.txt`, PNG icons rasterized by `resvg` in `xtask`, a placeholder
name "Pulsar Console", and license texts under `console/web/LICENSES/`. WEB-02 tests
`/fonts/outfit-latin-wght.woff2`, and the planned web CI job checks `OFL.txt`. Resolution:
no font files, PNG icons or vendor logos are imported; the dashboard uses the system font
stack, letter tiles per model family and SVG icons only; `resvg` is not added; the product
name is "PulsarMLX Console"; license texts live in `console/LICENSES/`. Decided by the lead
on 2026-11-14: no font or PNG file is shipped, the `/fonts/<name>` route answers 404, and
the web manifest lists SVG icons only; both behaviors are sub-items of BRAND-2 in the
deviation register.

**R15. Static routes: API-12 and WEB-02.** The approved plan puts embedded dashboard assets,
static routes and security headers in `console-web`. API-12 planned
`console-http::routes::static_assets` with its own embedding build step, and both packages
claimed the same three donor tests. Resolution: WEB-02 owns embedding, the asset table and
the handlers; API-12 mounts them in the `console-http` router and owns the HTTP-level and
traversal tests. Each donor test is one ledger row, resolved jointly.

**R16. Allowlisted paths and one UI contract.** WEB-05 and WEB-P2-01 planned a new
`docs/roadmap/CONSOLE_FRONTEND_ROADMAP.md`, which is outside the paths this work may touch.
Resolution: the Phase 2 entry goes into `docs/roadmap/CONSOLE_ROADMAP.md`. CNF-15 planned
`contracts/ui-api.json` while WEB-05 planned `contracts/ui-server/`. Resolution: one
UI-to-server contract under `contracts/ui-server/`, with CNF-15's endpoint list inside it.
WEB-05 to WEB-11 named a `contracts/ui-server/fixtures/` directory; under B13 it is
`contracts/ui-server/testdata/`.

**R17. Outbound network (B7).** The Responses planner left the TLS stack open (`rustls` or
the platform library) and the operations planner offered `ureq` with `rustls` as an
alternative to `curl`. Resolution: the system `curl` behind one facade, no TLS crate, the
release check opt-in (SEC-5), remote image URLs and local paths opt-in (SEC-4). The planner
records put the curl driver in OPS-16 (M7), while RSP-10 and RSP-17 (M6) need it earlier.
Decided by the lead on 2026-11-14: the outbound curl facade lives in `console-core` (module
`outbound`), is written by RSP-10, its first consumer, and is reused by RSP-17 and OPS-16,
which depend on RSP-10. HTTPS MCP through the facade is deviation PLAN-6. Facade tests run
against loopback fixture servers built on `std::net` (R2); no claim about a real remote
server is made.

**R18. CI shape (B12).** The conformance planner proposed `console.yml` with no path filter
(because a skipped path-filtered job reports success), the differential job J4 required from
CNF-09 onward, the SDK job J5 inside the summary, weekly schedules for the drift canary and
the donor baseline, and a preflight that allows any new file under `docs/`. Resolution: the
workflow is path-filtered; the summary depends only on the four blocking jobs; reference
capture, the live differential (J4), vendor-template checks, SDK client tests (J5), the drift
canary, the mutation advisory, the donor baseline and the browser end-to-end suite run only
on `workflow_dispatch`, with no schedule; the preflight boundary check uses the allowlist in
section 5 of the approved plan. The planner's concern is real: whether `console.yml` becomes a
required check is the owner's call at merge time, as the plan says (OPEN-13). CNF-01
depended on "the workspace skeleton from the core/workspace planner"; that is GOV-06, which
creates the first `console.yml`, and CNF-01 extends it.

**R19. Ledger location and timing.** CNF-12 placed the ledger at
`specs/022-*/contracts/parity-ledger.json` and builds its checker in M10, yet every package's
gate needs its rows resolved from M1 on. Resolution: the ledger is `console/parity/ledger.json`;
GOV-06 creates it with 913 pending rows; API-19 assigns an owning package to every row of the
API-reader files; each package resolves its own rows; CNF-12 adds the full checker,
inventories and the zero-pending gate. Until CNF-12 lands, the per-task gate's ledger check is
done by the reviewer with the structural checks GOV-06 ships.

**R20. Answer persistence (PRIV-1).** API-10's planner kept the donor default of storing
web-chat answers on disk for 24 hours. Resolution: resume is kept in memory and disk
persistence is off by default; API-10's file-backed tests (restart survival, eviction, the
restart note) enable persistence explicitly; WEB-10's privacy text states what is stored.

**R21. Refusal ablation (POL-1, B10).** OPS-05 planned an `ablate` profile module and four
`Ablate` tests, and the API planner needed `ablate_choice` and `ablate_default`. Resolution:
the switch and its config keys are not ported; the capability flag is recognized and refused
unless an engine advertises it (ENG-03); the donor rows resolve to POL-1.

**R22. MiniMax picture preprocessor (LIC-2, B10).** RSP-19 planned both the DeepSeek (DSI1)
and MiniMax (MMI1) preprocessors. Resolution: only DSI1 is built; the MMI1 format is
documented in the media contract, an engine reporting MiniMax vision gets a clear error, and
the donor `test_mm3_vision.py` rows resolve to LIC-2.

**R23. Hardware-specific code before M9 (B11, PLAT-1).** The binding assignment places some
hardware-specific code earlier than M9: the NVML process check in ENG-08 (M3), the GLM link
mode for an AMD APU with an NVIDIA card in ENG-15 (M3), GPU lending in ENG-14 and RSP-18
(M6), and the `nvidia-smi` and KFD parsers in OPS-07 (M7). Resolution: those parts are built
in their milestone behind traits with fixture or mocked providers and labeled unverified on
hardware, exactly as PLAT-1 requires; the real readers (NVML, AMD, Windows), the GPU map, the
mixed-GPU helper, the Windows shims and the GPU-era dashboard paths stay in M9. Decided by
the lead on 2026-11-14.

**R24. Donor engine binaries (B10).** ENG-06 and ENG-15 launch whatever executable a run
config names. Resolution: no test, document, default or example launches a project-maya
engine binary, and ADR 0008 states it is out of scope. Whether the launcher should actively
refuse known donor engine names is open (OPEN-24). ENG-18's real-engine oracle profile stays
skipped.

**R25. Shared documents.** WEB-01 targets `NOTICE.md` and `docs/upstream/PROJECT_MAYA.md`,
which GOV-05 writes in M0. Resolution: GOV-05 creates both; WEB-01 adds the dashboard section
through the lead in M8.

**R26. Mutual dependencies inside the planner records.** API-13 and API-17 depend on each
other, and PRM-11, PRM-12 and PRM-15 form a cycle. Resolution: API-13 calls a lifecycle trait
that API-17 implements, and PRM-11 calls the cross-turn guard through a trait that PRM-15
implements; the notes on those tasks say so.

**R27. The backend seam (ENG-01).** The engine planner designed an async, `Send + Sync`
`Engine` trait with boxed futures, in which the engine assigns the request id, documented in
a file named `engine-seam.md`. The approved plan (section 6) and
[contracts/backend-seam.md](contracts/backend-seam.md) specify a synchronous token-level
seam whose engine instance is owned by one driver thread and need not be `Send`, and a
server-assigned request id. Resolution, decided by the lead on 2026-11-14: ENG-01 implements
`contracts/backend-seam.md`; the server assigns the request id; and the seam document is
`backend-seam.md` (the detail file `tasks/engine.md` has been corrected to that name, and
its other ENG-01 text is superseded where it conflicts with the contract). Before the
seam is frozen, ENG-01 settles how multi-conversation engines fit the single-owner seam.
The lead's guidance is that the instance stays owned by one driver thread; for more than one
concurrent generation the token-level trait offers a submit-and-pump form with events tagged
by request id, and the blocking generate form is the single-conversation case. The draft is
offered to the engine track for review before it is frozen (FR-039 in spec.md). The open
seam questions are OPEN-30. Amended on 2026-11-14: the owner decided seam question Q9
(OPEN-29): the server refuses to start an engine that does not report synthetic
provenance, and ENG-01 builds the provenance type and the single guard of lead decision
LD28 (R29). Who on the engine track reviews the draft, and in what form, is still not
decided (seam question Q12, OPEN-30); reaching the engine track goes through the owner.

**R28. Dashboard caching and asset source (WEB-02).** The dashboard planner gave WEB-02
strong `ETag`s with 304 responses and `HEAD` support, and a `devdir` module that serves
assets from a directory in development. The first is proposal P-11 in the deviation
register, awaiting owner decision (OPEN-15); the second conflicts with the approved plan's
rule that no filesystem path is ever served (PLAN-3), and the question is recorded as
OPEN-41. Resolution: WEB-02 keeps the donor's `Cache-Control: no-cache` without validators
and no `HEAD` support until the owner decides P-11, and builds no `devdir` module. Amended
on 2026-11-14: the owner approved P-11 at checkpoint 1, so WEB-02 builds strong `ETag`s,
304 responses and `HEAD` support for dashboard assets; the `devdir` module stays not
adopted and OPEN-41 is unchanged (R29).

**R29. Owner decisions at checkpoint 1 (2026-11-14).** The owner reviewed checkpoint 1 on
2026-11-14, accepted and approved the decisions put to it, and asked for a clear note on
what must be done before the server may start an engine that is not synthetic. The
decisions below, and the lead decisions LD28 and LD29 that carry them out, override any
conflicting sentence in the detail files under `tasks/` and in earlier reconciliations. In
particular they supersede R28's "until the owner decides P-11", any "working default" or
"open" wording about the scripted engine's default model name, and any detail text that
keeps the donor's behavior where an approved proposal now applies.

- **ADR 0008** is accepted by the owner, as written (GOV-04).
- **OPEN-27 is settled.** The owner accepts that donor benefit is recorded as a
  pre-adoption estimate and measured at close-out (plan exception E6; GOV-02). OPEN-57,
  which named checklist the close-out coverage figure uses, stays open (CNF-17).
- **OPEN-03 is settled.** The scripted engine's default model name is exactly
  `pulsar-console-synthetic` (PLAN-2). ENG-02 delivers it, API-08 asserts it and API-17
  keeps it; it is the decided name, no longer a working default.
- **OPEN-04 is settled** by the owner as deviation SEC-1.1. On a loopback bind a request is
  accepted only if its `Host` is a loopback name (`localhost`, `127.0.0.1` or `[::1]`, any
  port) or a name listed in the optional run-config key `allowed_hosts`; the key is absent
  by default, so by default only loopback names pass. On a non-loopback bind `Host` is not
  restricted, as in the donor, unless `allowed_hosts` is set; when it is set, only the
  listed names and the loopback names pass. A refused request gets 403 `permission_error`,
  unchanged. The key name `allowed_hosts` is decided. API-15 reads the key from the run
  config and API-03 enforces the list. Matching details (case, port, IPv6 forms, a missing
  `Host` header) follow the archived serving crate (B8) and are settled by API-03. Lead note
  LD30: the one-line recommendation put to the owner read "Loopback names only on loopback
  binds; elsewhere no restriction unless an allowed_hosts key is set". That `allowed_hosts`
  also extends the list on a loopback bind follows the SEC-1.1 text the owner reviewed; the
  lead confirms it with the owner at checkpoint 2.
- **OPEN-29 is settled** (seam question Q9): the server refuses to start an engine that
  does not report synthetic provenance. The mechanism is lead decision LD28:
  1. The provenance type in the engine descriptor can express "not synthetic": an engine
     that declares another provenance, or declares none. Synthetic is the only value the
     server accepts in this increment. ENG-01 settles the exact shape of the type.
  2. One guard function in `console-core` decides. Every path that admits an engine (first
     start, restart, model switch, context reload) calls it before the engine serves a
     request. No environment variable, configuration key, command-line flag or Cargo
     feature bypasses it in this increment.
  3. At process start a refusal makes `pulsar-console` exit with a non-zero status after
     one line on standard error that names the engine kind, what the engine reported, and
     the path `docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md`. At a later restart, switch
     or reload, the engine is closed, the operation fails with the same message, and the
     server serves nothing from that engine.
  4. A line-protocol engine declares synthetic provenance in its start-up lines before it
     is admitted; one that declares another provenance, or none, counts as not synthetic
     (fail closed). The form of the declaration is settled with the line-protocol packages
     in M3 (OPEN-58, a lead item; the lead's direction is a fact on an `INFO` line). It is
     not the synthetic marker proposed for the server's own ready line, which belongs to
     PLAN-1 and OPEN-35.
  5. Tests pin the refusal: ENG-01 for the guard, ENG-10 for the turn driver, API-08 for
     process start (kept by API-17). They are not deleted or weakened to make a real engine
     start.
  6. What must be done to allow a non-synthetic engine is written in
     [docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md](../../docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md),
     requested by the owner on 2026-11-14 so that whoever picks the work up next can act on
     it. A task that adds, moves or removes an enforcement point of the synthetic-only rule
     updates that note in the same change (per-task gate, step 7).

  Tasks changed: ENG-01, ENG-02, ENG-10, API-08, API-17 and, for the line-protocol
  declaration, ENG-04, ENG-05 and ENG-06.
- **Proposals P-1 to P-18**, decided by the owner on 2026-11-14. Approved, and now
  deviations under their `P-` ids: P-1 and P-2 (API-02; P-1 fixes the `Server` header as
  `pulsar-console/<version>`); P-3 (API-01, API-07, PRM-06); P-4 (RSP-12, RSP-18, RSP-19);
  P-6 (ENG-06; it settles OPEN-10: an optional engine ready-timeout setting, off by
  default); P-7 (ENG-14; RSP-18 and RSP-19 write under its directory); P-8 (PRM-03, PRM-07, PRM-08, API-07; it
  settles OPEN-07: a template `raise_exception` and DeepSeek encoder assertion failures
  answer 400); P-9 (WEB-08); P-10 (ENG-08, OPS-17); P-11 (WEB-02); P-13 (WEB-03); P-14 (OPS-12);
  P-15 (OPS-03, OPS-16); P-16 (OPS-14). Declined, and not built: P-12, because a report-only
  switch for the Content-Security-Policy would weaken SEC-2 while on (WEB-02, WEB-03); and
  P-17, because FIX-1.1 is approved and no literal-parity reload setting is built (ENG-12,
  API-14). Deferred, still awaiting the owner: P-5, decided before the picture packages of
  M6 (RSP-18, RSP-19), and P-18, decided before PRM-05 in M2. OPEN-15 stays open for those
  two and for the JSON Schema meta-validation wording (PLAN-5, RSP-02) and the advisory
  savings lock (OPS-21).
- **WEB-02.** R28's "until the owner decides P-11" is superseded: WEB-02 builds strong
  `ETag`s, 304 responses and `HEAD` support for dashboard assets. The `devdir` module stays
  not adopted (OPEN-41 unchanged).
- **OPEN-39 is settled** by the lead on 2026-11-14 (LD29): an owner-approved proposal keeps
  its `P-n` id as its deviation id; a later owner-approved deviation that was never a
  listed proposal takes the next free `P-` number; ids are never reused; a declined
  proposal keeps its id, marked declined.
- **Lead decisions reported.** LD1 (shim runs and vendor-template renders only in the manual
  job, and the eight ledger dispositions; R10) and LD17 (third-party license texts arrive
  with the importing package; GOV-05) were reported to the owner at checkpoint 1, and the
  reply raised no objection.
- **Lead decisions that go with the above** (2026-11-14, made with the M1 scaffold).
  - LD31: API-08 owns the minimal `pulsar-console` entry point that M1 needs, in
    `console/crates/pulsar-console/`: the scripted engine, the listen address and port, the
    wiring of `allowed_hosts` from the run config into the API-03 guard, and the
    process-start refusal of LD28 with its spawned-process test. API-17 (M4) replaces it
    with the full command line and keeps the refusal. The lead runs the M1 demonstration
    of owner checkpoint 2 with that binary.
  - LD32: the SHA-256 helper `console-core::digest` is owned by API-03, the first task
    that needs it. `console-conformance` keeps no internal dependency and uses `sha2`
    directly (CNF-02).
  - Later admission paths: any task that adds a path which starts, restarts, switches or
    reloads an engine (ENG-06, ENG-12, API-14 and OPS-10 among them) routes it through the
    admission step of ENG-10, so that the LD28 guard runs, and adds a test that an engine
    which is not synthetic is refused on that path.
  - P-6: ENG-06 adds the ready-timeout setting to the settings store that API-15 builds
    and records its name in contracts/naming.md; API-15 does not define it in M1.
  - P-7: ENG-14 creates the vision temporary directory and refuses at start when no
    whitespace-free base exists; RSP-18 and RSP-19 write under it. The per-request `GENI`
    path check of ENG-04 is the donor's behavior and is not part of P-7.
  - P-9: the approved table has no entry for `fake`. The WEB-08 detail's mapping of `fake`
    to Synthetic is not approved and is not built unless the owner approves it.
  - The `Server` and `Date` headers in comparisons: the detail file tasks/conformance.md
    calls both headers not observable. contracts/parity-ledger.md section 1.1 governs:
    header names and positions are observable, and only the two values are volatile.
  - LD33 (2026-11-14, with CNF-01): the reading of binding decision B12 that CNF-01 built
    is accepted. The preflight and summary jobs run no cargo command, so they install no
    toolchain and do not assert `rustc -V`; the two Rust jobs install the pinned toolchain
    and assert it. The Rust jobs wait for preflight.
  - LD34 (2026-11-15, with API-02): the request-head parser of API-02 is written by hand so
    that it accepts what CPython's request and header parsing accepts. `httparse` refuses
    lines that Python accepts, so the transport does not use it; it stays a dependency of
    `console-conformance` only (the raw client). This departs from the wording of B1 and of
    the approved plan's technology table ("tokio and httparse"), keeps their purpose
    (byte-level parity), and is reported to the owner at checkpoint 2. Property-style tests
    of the head parser join the scope of CNF-14 (M10).
  - LD35 (2026-11-15): text that comes from a client or from an engine is made log-safe
    (control characters escaped) before it is written to one of the server's own log
    lines. Log lines are not part of the wire parity definition. API-01's mid-answer line
    does this; ENG-10 does it for the phase text that the FIFO's queue watch prints.
  - LD36 (2026-11-15, with ENG-09): the FIFO keeps the donor's release arithmetic,
    including what an exclusive holder frees after the capacity grew while it held. No
    deviation is registered for it.
  - LD37 (2026-11-15): a donor test method that a task can only partly re-express stays
    `pending` in the ledger and is resolved by the task that completes it, which names the
    earlier task's tests beside its own; the earlier task's checkbox stays open until
    then. First case: `RequestBodies::test_a_chunked_body` and
    `::test_a_malformed_body_is_a_400`, partly covered by API-02 and completed by API-08.
  - LD38 (2026-11-15, working default; the owner decides, OPEN-60): the ports follow the
    standard-library behavior of CPython 3.14, the interpreter the M1 tables were recorded
    with (3.14.7). The donor's own CI runs Python 3.12 and its README asks for 3.10 or
    later, so text that comes from the interpreter (JSON decode messages, request-line
    parsing details, Unicode tables) can differ by version in the donor itself. Until the
    owner decides, the manual reference job (CNF-08) is planned on CPython 3.14 instead of
    3.12, and every table says which version it was recorded with.
  - LD39 (2026-11-15, with API-03): SEC-1.3 (a JSON content type on every POST) does not
    apply to the two raw-upload routes, `/attach` and `/pdf`, which take the donor's
    attachment content types and keep the donor's own refusal for any other type; every
    other POST needs a JSON content type. Reported to the owner at checkpoint 2.
  - LD40 (2026-11-15, with API-03): an `allowed_hosts` entry that cannot be parsed stops
    the server at start, with a message that names the entry and the accepted forms.
    API-08 wires it; `GuardConfig::rejected_allowed_hosts` gives the entries.
  - LD41 (2026-11-15, with API-03): the product wording API-03 fixed is accepted: "only
    from PulsarMLX Console's own page" and "files are read only for PulsarMLX Console's own
    page", and the texts of the SEC-1.1 `Host` refusal and of the SEC-1.4 local-only
    refusal as API-03 wrote them (`HOST_REFUSED_MESSAGE` and `LOCAL_ONLY_MESSAGE` of
    `console_http::guard`; contracts/naming.md section 3.11).
  - LD42 (2026-11-15, with ENG-10): the refusal while the server is stopping is answered
    400 `invalid_request_error`, as the donor's `ValueError` is
    (`serve/server.py:4364-4365`); the API-07 detail's "503 shape" is superseded.
  - LD43 (2026-11-15, with API-03): the matching details of SEC-1.1 as API-03 built them,
    to be confirmed with the owner together with LD30: exactly one `Host` header, and a
    missing one is refused; names are compared without regard to case; any port, or none,
    is accepted; an `allowed_hosts` entry that names a port matches only that port; no
    trimming, no IPv6 normalization, no forgiveness of a trailing dot.
- **Not decided.** Who on the engine track reviews the seam draft, and in what form (FR-039,
  seam question Q12, OPEN-30). ENG-01's code may land; the seam stays a draft and ENG-01
  stays unticked until that review is recorded. Reaching the engine track goes through the
  owner.

With these decisions, M1 may start.

## Open items

These are not decided by the approved plan. The single register of open items for this
feature is in [checklists/analysis.md](checklists/analysis.md); it gives each item a stable
`OPEN-` id, who decides it and where it came from. The table below lists, under their
register ids, the items that must be resolved by the owner or the lead, as marked, before
the named task closes. The register is authoritative where the two differ.

| Id | Item | Who decides | Blocks |
| --- | --- | --- | --- |
| OPEN-01 | Whether the donor's sealed-reasoning prefix is accepted on input (B2) | Owner | RSP-03 |
| OPEN-06 | The default run-config directory when no config is given, and whether an importer for project-maya run configs exists | Owner | OPS-11 |
| OPEN-09 | An untagged ERR in multi-conversation mode: reproduce the donor's wait, or deliver it to the single in-flight request (FIX-1 covers only the untagged stop) | Owner | ENG-07 |
| OPEN-15 | The proposals still awaiting the owner after checkpoint 1: P-5 (picture decoding and resampling) and P-18 (an explicit model-family override); P-19 (refusal of an unpaired surrogate inside a JSON string), P-20 (the nesting bound of 1000 levels in the JSON reader and writer) and P-21 (four parse differences on engine `INFO` and `DONE` values), raised by API-01 and ENG-01 on 2026-11-14; P-22 (Python's error page for a refused request head also when `cors_origins` is set), P-23 (five differences in the run-config store) and P-24 (refusals and size limits in tokenizer pack loading), raised by API-02, API-15 and PRM-04 on 2026-11-15; P-25 (under `--port 0` the server's ready line names the port the operating system bound), raised by CNF-07 on 2026-11-15; P-19 to P-25 are put to the owner at checkpoint 2; also the JSON Schema meta-validation wording (PLAN-5) and the advisory savings lock (R29) | Owner | RSP-18, RSP-19 (P-5); PRM-05 (P-18); API-01 (P-19, P-20); ENG-01 (P-21); API-02 (P-22); API-15 (P-23); PRM-04 (P-24); CNF-07, API-08, API-17 (P-25); RSP-02; OPS-21 |
| OPEN-24 | Whether launching refuses known project-maya engine names | Owner | ENG-15 |
| OPEN-25 | Which names Turbo and the settings profiles write into a run-config `env` block (the donor writes `MAYA_GLM_*` and `MAYA_DS4_*`), and the engine variable names shown in the dashboard; B2 fixes only that such names pass through verbatim | Owner | OPS-05, OPS-06, WEB-09 |
| OPEN-30 | Seam design details ENG-01 settles before freezing the seam (R27) | Lead | ENG-01 |
| OPEN-58 | The form in which a line-protocol engine declares synthetic provenance in its start-up lines (LD28; the lead's direction is a fact on an `INFO` line) | Lead | ENG-04, ENG-05, ENG-06 |

Points that earlier drafts of this list left open and that the lead decided on 2026-11-14:
how ids are generated (R8), whether `hyper` may appear in test code (R2), which package
builds the curl facade (R17), the behavior of `/fonts/<name>` and the manifest icons (R14),
which further packages get an extra reviewer (see the risk section), when third-party
license texts arrive (GOV-05), how CI fetches crates (`cargo fetch --locked` at run time,
nothing vendored), how local gates enforce the toolchain pin (the per-task gate), the
provenance header format (`docs/upstream/PROJECT_MAYA.md`, Attribution), the single
verbatim passthrough of run-config `env` names (API-15), the test-switch names (R5), what
counts as observable (CNF-04), accepted Unicode-table differences (PRM-04), the
run-config directory rule of API-15, and the delivery of PLAN-2 (ENG-02).

Points the owner settled at checkpoint 1 on 2026-11-14 (R29): OPEN-03, the scripted
engine's default model name, which is exactly `pulsar-console-synthetic` (ENG-02, API-08,
API-17); OPEN-04, the `Host` allowlist of SEC-1.1, under which only loopback names and the
names listed in the optional run-config key `allowed_hosts` pass on a loopback bind, and
`Host` is unrestricted on a non-loopback bind unless `allowed_hosts` is set (API-03,
API-15); OPEN-29 (seam question Q9), under which the server refuses to start an engine
that does not report synthetic provenance, through the single guard of lead decision LD28
(ENG-01, ENG-10, API-08, API-17); OPEN-07 and OPEN-10, settled by the approved proposals
P-8 and P-6; and OPEN-27, the pre-adoption estimate of donor benefit with its measurement
at close-out (plan exception E6). What must be done before any other engine may start is in
[docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md](../../docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md).
The lead settled OPEN-39, the numbering of later deviations, on the same day (LD29).

## Phase M0: Governance and skeleton

**Purpose**: Section 7 of the approved plan in full: the Spec Kit artifacts, ADR 0008, the
roadmap, the donor qualification, and an empty `console/` workspace with `console.yml` and
the boundary and hygiene tools. No code.

**Checkpoint**: Owner checkpoint 1: spec.md with its checklist, ADR 0008, the roadmap
entries, NOTICE.md and the donor qualification record. Held on 2026-11-14: the owner
accepted and approved the decisions put to it, and M1 may start (R29).

- [ ] GOV-01 [P] [M0] Feature specification and requirements checklist —
  specs/022-console-serving-parity/spec.md, checklists/requirements.md
  - Depends on: none.
  - Donor sources: none directly; the approved plan and the planning records of 2026-11-14
    (not committed).
  - Parity tests: none; the spec names the parity definition, the 913-method ledger and the
    deviation ids.
  - Risk: medium. It speaks in the owner's name and is reviewed at checkpoint 1.
  - Done when: spec.md states user stories, functional requirements and success criteria
    that match the approved plan without adding decisions, every claim is labeled planned or
    synthetic-only, and the requirements checklist is complete with no open item hidden.
  - Detail: this entry is complete; the files it produces are listed in plan.md.
- [ ] GOV-02 [M0] Plan, research, data model and quickstart —
  specs/022-console-serving-parity/plan.md, research.md, data-model.md, quickstart.md
  - Depends on: GOV-01.
  - Donor sources: none directly; the decisions recorded in ADR 0008.
  - Parity tests: none.
  - Risk: medium. plan.md carries the Constitution Exceptions table (nested workspace
    outside `--workspace`, serving ahead of Stage F, JavaScript assets in the Rust-owned
    runtime, hand-authored artifacts, the manual cross-artifact analysis, donor benefit
    estimated before adoption and measured at close-out).
  - Done when: plan.md records the architecture, the constitution check and the six
    exceptions (E1 to E6) with scope, risk and removal condition; research.md records
    every chosen crate with its license and exact pin as packages add them; quickstart.md
    gives commands that are marked as planned until they run.
  - Note: Owner decision 2026-11-14: exception E6 is accepted, settling OPEN-27; OPEN-57
    stays open (R29).
  - Detail: this entry is complete; the files it produces are listed in plan.md.
- [ ] GOV-03 [M0] Task list and recorded cross-artifact analysis —
  specs/022-console-serving-parity/tasks.md (this file) and checklists/analysis.md
  - Depends on: GOV-01, GOV-02.
  - Donor sources: none directly; the planner records of 2026-11-14.
  - Parity tests: none.
  - Risk: medium. A dropped or duplicated package would silently change scope.
  - Done when: every one of the 131 ids appears exactly once in this file with its
    milestone, dependencies, donor sources, parity tests, risk and definition of done; every
    conflict with the approved plan is listed under Reconciliations; the cross-artifact
    analysis, with the single open-item register, is recorded in checklists/analysis.md
    before any M1 code.
  - Detail: this entry is complete; the files it produces are listed in plan.md.
- [ ] GOV-04 [P] [M0] ADR 0008, console roadmap, and the strategy, README and CONTRIBUTING
  notes — docs/architecture/decisions/0008-console-serving-ahead-of-stage-f.md,
  docs/roadmap/CONSOLE_ROADMAP.md, docs/roadmap/PULSARMLX_STRATEGY.md (dated pointer),
  README.md (one status row), CONTRIBUTING.md (nested-workspace commands)
  - Depends on: none.
  - Donor sources: none directly; ADR 0004 and the approved plan section 7.
  - Parity tests: none.
  - Risk: medium. These documents speak in the owner's name and are reviewed at checkpoint
    1.
  - Done when: ADR 0008 records serving ahead of Stage F on synthetic backends only, the
    donor qualification, the two-phase front end, the superseded archived serving crate, the
    out-of-scope donor engine binaries and the CI cost; the roadmap names Phases 1, 2 and 3;
    the three small edits contradict nothing the owner decided.
  - Note: Owner decision 2026-11-14: ADR 0008 is accepted, as written (R29).
  - Detail: this entry is complete; the files it produces are listed in plan.md.
- [ ] GOV-05 [P] [M0] Donor qualification record, NOTICE section and license texts —
  docs/upstream/PROJECT_MAYA.md, docs/upstream/PROJECT_MAYA_SYNC.md, NOTICE.md (new
  section), console/LICENSES/
  - Depends on: none.
  - Donor sources: LICENSE (both copyright lines); README.md ownership and credits; the
    per-module layout of serve/.
  - Parity tests: none.
  - Risk: medium. Attribution and license completeness are constitution principle IX.
  - Done when: the donor record names the pinned commit, both copyright lines, a per-module
    classification (adapted, reimplemented, excluded) and the concrete ADR 0004 evidence
    plan; M0 ships the project-maya MIT text only, in console/LICENSES/; the license texts
    of third-party components are added in the same change that imports the component:
    Preact (MIT), htm (Apache-2.0) and Lucide (ISC) with WEB-01, and the DeepSeek reference
    encoder notice with PRM-07, which commits the five DeepSeek fixture pairs together with
    that notice (decided by the lead on 2026-11-14; the owner was informed at checkpoint 1
    and raised no objection, R29);
    NOTICE.md gains the matching section; no donor benchmark is presented as PulsarMLX
    evidence.
  - Detail: this entry is complete; the files it produces are listed in plan.md.
- [ ] GOV-06 [M0] Workspace skeleton, hygiene tools, console.yml, ledger skeleton and
  cross-cutting contracts — console/Cargo.toml, console/rust-toolchain.toml (1.97.1),
  console/tools/ (boundary, hygiene and toolchain checks), .github/workflows/console.yml,
  console/parity/ledger.json, specs/022-console-serving-parity/contracts/ (backend-seam.md
  draft, naming.md, deviations.md)
  - Depends on: GOV-02.
  - Donor sources: all 44 serve/test_*.py, listed as text (method names only) for the ledger
    skeleton.
  - Parity tests: none; creates the 913 ledger rows, all pending.
  - Risk: medium. A wrong boundary or ignore rule would let a later package touch a frozen
    file or lose a file silently.
  - Done when: an empty nested workspace builds on the pinned toolchain;
    console/tools/check-toolchain.sh passes on it and fails on any other rustc version;
    console/tools/check-boundary.sh passes on the branch and fails on a staged change to any
    never-touched path; console.yml is path-filtered with the preflight, Rust on Linux and
    Rust on macOS arm64 blocking jobs and the summary (the web logic job of B12 arrives with
    CNF-15, and the Windows cross type-check by API-18 at the latest, whose definition of
    done needs it); the ledger lists 913 pending rows; naming.md publishes the old-to-new
    name table; and deviations.md lists every deviation id of the approved plan and
    PLAN-1 to PLAN-6, with unapproved proposals kept apart.
  - Note: Owner decision 2026-11-14: the proposals are decided as recorded in R29; the
    approved ones are deviations under their `P-` ids (LD29).
  - Detail: this entry is complete; the files it produces are listed in plan.md.

## Phase M1: Core pipeline

**Purpose**: Python-compatible JSON; HTTP transport, router and security posture; request
validation; backend seam, scripted engine, FIFO and turn driver; byte tokenizer and
detokenizer; chat completions for plain content; run-config store; test kit and scenario
comparator.

**Checkpoint**: Owner checkpoint 2: the first end-to-end demonstration, a streamed answer
over `curl` from the scripted engine, and the decision on the first push. The owner
authorized the first push of the feature branch on 2026-11-14, ahead of this checkpoint;
each later push remains a checkpoint decision.

- [ ] API-01 [P] [M1] Wire foundations: Python-compatible JSON, error model, ids (absorbs
  PRM-01 and the JSON writer of OPS-01) — console-pyjson (new crate) and console-http::error
  - Depends on: none.
  - Donor sources: serve/server.py:416-428, 5375-5381, 5457-5463, 6152-6158, 6283-6297,
    4936, 5251, 2577, 2818, 2863, 2918, 167-171, 163; from PRM-01: serve/frontend.py
    (json.dumps and json.loads sites), serve/ds41_encoding.py, serve/loop_guard.py:314-326,
    serve/response_schema.py:14-21, serve/server.py:4909-4930; from OPS-01: serve/models.py
    L662-700 (write).
  - Parity tests: no dedicated donor method (ledger: foundation). Golden tables derived from
    documented Python behavior: at least 40 values (API-01) and at least 120 pairs (PRM-01)
    covering separators, ensure_ascii and astral escapes, float repr, indent and sort_keys;
    about 40 indent=1 documents (OPS-01), hand-derived and never produced by running the
    donor.
  - Risk: medium (planner ratings low for API-01, medium for PRM-01 and OPS-01). Float repr
    in exponent form and ensure_ascii parity are the subtle parts.
  - Done when: console-pyjson builds standalone and its table tests reproduce Python's
    output byte for byte for every escape class, float boundary, big integer, NaN or
    Infinity, indent, separator and sort_keys combination, with a table of at least 40
    values each matching the recorded Python output; every error constructor produces the
    documented body and status; the crate depends on nothing beyond serde, serde_json (with
    the B3 features) and libc, and ids are random hexadecimal from operating-system
    randomness with no `uuid` crate (R8).
  - Note: Owner decision 2026-11-14: implements approved deviation P-3, so the malformed
    request error keeps the `malformed request (` prefix and a Python-like category with
    Rust-side detail text.
  - Note: Built and merged on 2026-11-14 at commit `c2392605`. The checkbox stays open: the
    reader refuses an unpaired surrogate inside a string and both the reader and the writer
    bound nesting at 1000 levels, which are proposals P-19 and P-20, awaiting the owner's
    decision at checkpoint 2 (OPEN-15). If the owner declines either, the behavior changes.
  - Detail: [tasks/api.md#api-01](tasks/api.md#api-01);
    [tasks/prompt.md#prm-01](tasks/prompt.md#prm-01);
    [tasks/ops.md#ops-01](tasks/ops.md#ops-01).
- [ ] API-02 [M1] HTTP/1.0 transport: listener, request parsing, bodies, responses,
  disconnect watch — console-http::transport (tokio, with the request head parsed by hand,
  LD34; one request per connection)
  - Depends on: API-01.
  - Donor sources: serve/server.py:5346-5372, 5403-5455, 5457-5463, 6463-6474, 5019-5044,
    6715-6734, 6797-6803, 7166-7171; Python http.server semantics.
  - Parity tests: serve/test_server.py RequestBodies (5), NoDelayStreaming (1), raw-socket
    parts of GoneClients and QueuedKeepAlives; new tests for 501, 414, 431, 505 and the
    per-operation timeout.
  - Risk: medium. Hand-written HTTP parsing is security-sensitive; SEC-1 applies from this
    package on (B8).
  - Done when: the listed tests pass; a 300 MB Content-Length gets 413 without the body
    being read, chunked request bodies decode, a blocked handler is cancelled within 1 s of
    the client closing, SSE sockets have TCP_NODELAY, and raw response bytes show no
    keep-alive and no chunked response encoding. Every response carries
    `Server: pulsar-console/<version>` (P-1), and a request with both `Content-Length` and
    chunked `Transfer-Encoding` gets 400 (P-2); raw-byte tests pin both.
  - Note: Owner decision 2026-11-14: implements approved deviation P-1, the `Server` header
    `pulsar-console/<version>` in place of the donor's Python value.
  - Note: Owner decision 2026-11-14: implements approved deviation P-2, a 400 answer to a
    request that carries both `Content-Length` and chunked framing, where the donor silently
    prefers chunked; the detail file's chunked-first rule applies only when
    `Content-Length` is absent.
  - Note: Built and merged on 2026-11-15 at commit `d64685f7`. Its request-head parser is
    written by hand, without `httparse` (LD34, R29). The checkbox stays open: two of its six
    donor rows, `RequestBodies::test_a_chunked_body` and
    `RequestBodies::test_a_malformed_body_is_a_400`, need the router, validation and the
    chat route (API-03, API-04, API-08), and only their transport parts are tested; and
    Python's error page for a refused request head when `cors_origins` is set is proposal
    P-22, awaiting the owner's decision (OPEN-15).
  - Detail: [tasks/api.md#api-02](tasks/api.md#api-02).
- [ ] API-03 [M1] Router, authentication, CORS and cross-site guards — console-http::router
  and console-http::guard; console-core::digest (the SHA-256 helper, LD32)
  - Depends on: API-01, API-02.
  - Donor sources: serve/server.py:5383-5400, 5780-5819, 5821-5826, 5923-5933, 5934-6139,
    6141-6150, 6160-6282, 6327-6338, 6434-6450.
  - Parity tests: serve/test_server.py CorsOptIn (8), RequestBodies.test_several_api_keys
    (1), WebApp key checks (2), SharedSettings guard tests (2), ModelManagement guard half,
    ClientShapes.test_query_string (1); new dispatch-table and rebinding tests.
  - Risk: medium. Dispatch-order subtleties; the SEC-1 Host allowlist and Origin rules are
    deviations, taken from the archived crate (B8).
  - Done when: a table-driven test enumerates every donor route with and without a key and
    with foreign, same-host and absent Origin and asserts the status, and a reviewer can
    diff that table against the donor dispatch order; all listed donor methods pass. The
    rebinding test covers the `Host` allowlist of SEC-1.1 as the owner settled it (OPEN-04):
    on a loopback bind only loopback names (`localhost`, `127.0.0.1`, `[::1]`, any port)
    and names listed in `allowed_hosts` pass; on a non-loopback bind `Host` is unrestricted
    unless `allowed_hosts` is set, and then only the listed names and the loopback names
    pass; a refused request gets 403 `permission_error`.
  - Note: Owner decision 2026-11-14 (R29): the guard takes the `allowed_hosts` list that
    API-15 reads from the run config (absent by default); API-03 settles the matching
    details (case, port, IPv6 forms, a missing `Host` header) from the archived serving
    crate (B8). Lead note LD30: that `allowed_hosts` also extends the list on a loopback
    bind is confirmed with the owner at checkpoint 2.
  - Note: Built and merged on 2026-11-15 at commit `60fa1461`; its implementation and the
    donor tests it confirmed are recorded under SEC-1 in contracts/deviations.md. The
    checkbox stays open: ten of its fourteen donor rows need the handlers of later packages
    (API-06, API-07, API-08, API-09, API-11, API-12, API-13), and only their router halves
    are tested; LD30 and the matching details of LD43 await the owner's confirmation at
    checkpoint 2; and a follow-up, built in wave 4 with a commit that cites API-03, runs
    the `Host` check also before the transport's 501 page and its P-2 400 page, which are
    answered before the check until it lands. LD39 and LD41 apply (R29).
  - Detail: [tasks/api.md#api-03](tasks/api.md#api-03).
- [ ] API-04 [M1] Request validation, sampling normalization and shared defaults —
  console-core::request and console-core::sampling
  - Depends on: API-01.
  - Donor sources: serve/server.py:497-521, 624-632, 635-718, 2489-2530, 2571-2609,
    4275-4278, 6806-6854, 6899-6960, 1263-1319; docs/SETTINGS.md:407-464.
  - Parity tests: serve/test_server.py SamplingKeys (9, jointly with ENG-03), RequestChecks
    (7), SharedSettings (4, with API-13); serve/test_logprobs.py Fields (2); new tests for
    every message and the SEC-6 underscore stripping.
  - Risk: medium. Python numeric coercion quirks on serde_json values.
  - Done when: every message string from the donor's validation functions appears in a Rust
    test with its triggering input, a precedence matrix test passes, and the SamplingKeys
    expectations hold through the engine encoder in a joint test.
  - Note: Built and merged on 2026-11-15 at commit `89d40258`. The checkbox stays open: the
    joint rows, the SamplingKeys expectations through the engine encoder, need the encoder
    of ENG-03 (M3).
  - Note: Optional later refactor (lead, 2026-11-15): the Python `repr` and number-coercion
    helpers of `console_core::request` (`pyrepr`, `pynum`) may move into `console-pyjson`.
  - Detail: [tasks/api.md#api-04](tasks/api.md#api-04).
- [ ] API-15 [M1] Run config store, environment variables and settings (absorbs the
  run-config document store of OPS-01) — console-core::config (RunConfigStore, EnvSettings)
  - Depends on: API-01.
  - Donor sources: serve/server.py:395-409, 599-621, 5347-5372, 6737-6755, 6857-6960,
    7139-7166, 7327-7333, 7153-7154; tools/maya_names.py:1-78;
    serve/response_config.py:4-14; docs/SETTINGS.md:206-217; from OPS-01: serve/models.py
    L32-54, L662-700, L804-840, serve/server.py L2818, L2863, L2918, L3155-3158, maya.py
    L3895-4051 (schema reference only).
  - Parity tests: serve/test_server.py StallWatchdog env (1), CorsOptIn config (1),
    ModelManagement default (1), listen backlog (1, with API-02); from OPS-01:
    serve/test_models.py Page.test_secrets_in_the_environment_stay_on_this_pc,
    Page.test_another_models_settings_leave_which_one_starts_next,
    Settings.test_glm_written_back_with_the_rest_kept (preservation part).
  - Risk: low (OPS-01 rated medium). Unknown keys, key order and mtime handling must survive
    a rewrite.
  - Done when: an untouched config is rewritten byte-identical to Python's indent=1 output,
    unknown nested keys survive read-modify-write with order kept, the three OPS-01 donor
    tests pass, a test asserts that EnvSettings and the name table in
    contracts/naming.md agree, and the optional run-config key `allowed_hosts` (SEC-1.1,
    OPEN-04 settled by the owner on 2026-11-14) is read as a list of host names, absent by
    default, for the API-03 guard.
  - Note: Decided by the lead on 2026-11-14: every persisted file is resolved relative to
    the directory of the run config passed with --config, as the donor does; the default
    directory when no config is given, and whether an importer for project-maya run
    configs exists, stay owner item OPEN-06, to be settled before OPS-11 (M7). Names in a
    run-config `env` block pass through to the engine child verbatim, once; the donor's
    export of each engine setting under both a `MAYA_` and a `STRATA_` name is not
    reproduced (contracts/naming.md rule 3).
  - Note: Built and merged on 2026-11-15 at commit `9671312a`. The checkbox stays open: five
    of its seven donor rows need the model routes of M7 or the listener, and only their
    run-config parts are tested; not all typed accessors of the absorbed OPS-01 text are
    built; and five differences in the run-config store are proposal P-23, awaiting the
    owner's decision (OPEN-15).
  - Note: The typed run-config accessors API-15 did not build (`exe`, `args`, `gpu`,
    `backend`, `installer`, `vision`, `vision_off`, `ablate`, `turbo`, `sampling`, `port`)
    go to the packages that consume them: ENG-15 and the OPS packages of M7 (lead,
    2026-11-15). Until then they are read through the untyped `RunConfig::get`.
  - Detail: [tasks/api.md#api-15](tasks/api.md#api-15);
    [tasks/ops.md#ops-01](tasks/ops.md#ops-01).
- [ ] ENG-01 [P] [M1] Backend seam: engine trait, event model, capabilities, facts and
  contract document — console-core::engine;
  specs/022-console-serving-parity/contracts/backend-seam.md (freezes the GOV-06 draft)
  - Depends on: none.
  - Donor sources: serve/server.py:19-21, 191-193, 412-428, 532-568, 1173-1215, 2643-2666,
    4123-4126, 4340-4342, 4698-4701.
  - Parity tests: no donor test exercises the seam alone; about 15 new unit tests.
  - Risk: medium. Every later package builds on this; cancellation must be an explicit
    step.
  - Done when: the crate compiles with no dependency on console-http or console-prompt and
    implements contracts/backend-seam.md: a `Send + Sync` engine factory, an engine instance
    that need not be `Send` and is owned by the driver thread, and a request id assigned by
    the server; backend-seam.md maps every optional donor engine member to a trait method or
    capability; its open questions Q1 to Q8 and Q12 are answered or explicitly deferred
    (Q9 to Q11 are owner decisions; the owner decided Q9 on 2026-11-14), with Q1
    (multi-conversation engines) settled before the freeze (R27); the engine descriptor
    carries a provenance type that can express "not synthetic" (another provenance, or
    none), and one guard function in console-core admits only synthetic provenance, with no
    environment variable, configuration key, command-line flag or Cargo feature that
    bypasses it, and unit tests pin its refusal of another provenance and of none (LD28);
    and the draft has been offered to the engine track, with its review recorded, before
    version 1.0 is frozen (FR-039).
  - Note: The detail file's async `Send + Sync` trait, its engine-assigned request id and
    its `Box<dyn Engine>` and `Send + 'static` handle checks are superseded by
    contracts/backend-seam.md where they conflict (R27).
  - Note: Owner decision 2026-11-14: seam question Q9 is decided (OPEN-29): the server
    refuses to start an engine that does not report synthetic provenance (R29). The guard
    tests are not deleted or weakened to make a real engine start, and this task records
    the guard's symbol and test names in
    [docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md](../../docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md).
    The code may land, but the seam stays a draft and this task stays unticked until the
    engine track's review is recorded (FR-039); who reviews it, and in what form, is not
    decided (seam question Q12, OPEN-30).
  - Note: Built and merged on 2026-11-14 at commit `6200f4ac`, with the seam contract at
    draft 0.2. The checkbox stays open: it waits for the engine track's review of the seam
    contract (FR-039; contract draft 0.2, section "Review request to the engine track") and
    for the owner's decision on proposal P-21, the four parse differences on engine `INFO`
    and `DONE` values (OPEN-15).
  - Detail: [tasks/engine.md#eng-01](tasks/engine.md#eng-01).
- [ ] ENG-02 [M1] In-process fake engine (MockEngine parity) and scriptable test engines —
  console-engine::fake
  - Depends on: ENG-01.
  - Donor sources: serve/server.py:198-240, 2765-2772, 7117, 7287-7290;
    serve/test_server.py:32, 906-934, 1099, 1150, 1387, 1869-1880, 2166;
    serve/test_fair.py:24-92; serve/test_logprobs.py:35;
    serve/test_ds4_restore_points.py:48.
  - Parity tests: defines the engine behind most HTTP tests: serve/test_fair.py fakes (5),
    serve/test_server.py UsageAndStatus (5), TimingsDrafts (1), StatsAfterConsumerStops (1),
    NonFiniteRetry (4), EngineDeath (2); serve/test_logprobs.py OneConversation (3); about
    25 unit tests.
  - Risk: low. Must stay deterministic.
  - Done when: the fake engine implements the ENG-01 trait, every listed donor double has a
    Rust counterpart naming its upstream class, the scripted engine's default model name
    is exactly `pulsar-console-synthetic` (PLAN-2; decided by the owner on 2026-11-14,
    settling OPEN-03) and its descriptor reports synthetic provenance (LD28), and
    `cargo test -p console-engine fake` passes offline with --locked.
  - Note: Built and merged on 2026-11-15 at commit `c86cf84f`; its enforcement point is
    recorded as implemented in
    [docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md](../../docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md).
    The checkbox stays open: none of its 21 listed donor rows is re-expressed yet; they need
    the turn driver (ENG-10), the HTTP layer (API-07, API-08) or the line-protocol client
    (ENG-04, ENG-06), and ENG-02 delivers the doubles they use.
  - Detail: [tasks/engine.md#eng-02](tasks/engine.md#eng-02).
- [ ] ENG-09 [M1] EngineFifo: FairLock parity with places, exclusive holders, yields, queue
  keep-alives and watchdog — console-core::fifo
  - Depends on: ENG-01.
  - Donor sources: serve/server.py:172-187, 243-401, 3239-3270, 3813-3860, 4346-4378.
  - Parity tests: serve/test_fair.py FairLockOrder (3), FairLockYields (5);
    serve/test_multi.py Places (2); serve/test_server.py GoneClients (1), QueuedKeepAlives
    (1); about 14 tests.
  - Risk: medium. A custom Mutex plus Notify structure; fairness bugs are subtle.
  - Done when: every listed test passes deterministically under paused time 50 times with no
    flake, and a 1,000-operation stress test never exceeds capacity and ends with zero units
    used.
  - Note: Built and merged on 2026-11-15 at commit `5880f298`. The checkbox stays open: two
    of its rows, GoneClients and QueuedKeepAlives, need the HTTP layer (API-07 on API-02's
    transport, with ENG-10's queued counter); only their FIFO halves are tested. The FIFO
    keeps the donor's release arithmetic, including what an exclusive holder frees after
    the capacity grew while it held (LD36, R29).
  - Detail: [tasks/engine.md#eng-09](tasks/engine.md#eng-09).
- [ ] ENG-10 [M1] Engine turn driver: place, ensure_engine, engine calls, drain, context
  rule, errors, non-finite retry, figures — console-core::turn
  - Depends on: ENG-01, ENG-02, ENG-09.
  - Donor sources: serve/server.py:163, 431-432, 2639-2661, 3680-3694, 4097-4126, 4256-4271,
    4273-4307, 4340-4378, 4433-4454, 4491-4496, 4657-4793, 5011-5016.
  - Parity tests: serve/test_server.py MaxTokens (5), FitMaxTokens (3), NoRoomOrNoToken (3),
    NonFiniteRetry (4), EngineDeath (2), UsageAndStatus (5), TimingsDrafts (1),
    StatsAfterConsumerStops (1), PromptProgressStream (3), TestCarryEmbeddings (1);
    serve/test_glm_dsa_serve.py HistoryReuse (2); about 30 tests.
  - Risk: high. The most entangled port; nested generators become an explicit async state
    machine. Extra reviewer.
  - Done when: every listed test passes, a recording fake shows that dropping the consumer
    mid-stream still produces STOP, drain and place release in that order, a test shows the
    non-finite retry rules, timings match the donor's formula on fixed DoneFigures fixtures,
    the turn API is documented in contracts/backend-seam.md, and the driver calls the
    ENG-01 guard before an admitted engine serves a request, at first start, restart, model
    switch and context reload, with a test showing that a refused engine is closed, the
    operation fails with the refusal message, and nothing is served from it (LD28).
  - Note: Owner decision 2026-11-14: the synthetic-only rule of OPEN-29 (R29). This task
    records its test names in
    [docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md](../../docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md);
    the tests are not deleted or weakened to make a real engine start.
  - Note: This task settles what the server does when an engine delivers a token id outside
    the vocabulary, porting the donor's behavior. ENG-01 left
    `EngineFailure::out_of_vocabulary` with a provisional text that has no donor
    counterpart; this task replaces or maps it.
  - Note: Built and merged on 2026-11-15 at commit `4e7c438a`; the lead's fix-up at
    `78a408a7` gave the out-of-vocabulary failure a structured form
    (`EngineFailure::out_of_vocabulary_parts`). Its call of the guard on every admission
    path is recorded as implemented in
    [docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md](../../docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md),
    and a token id outside the vocabulary is answered as the donor's tokenizer
    `IndexError` (contracts/backend-seam.md section 12.1). The checkbox stays open: 29 of
    its 35 donor rows need the HTTP layer (API-07, API-08), the line-protocol client
    (ENG-04, ENG-05, ENG-06) or the continuation packages (ENG-11), and only their driver
    halves are tested; several generations at once on an engine with several places are
    left to ENG-07, and the continuations to ENG-11.
  - Detail: [tasks/engine.md#eng-10](tasks/engine.md#eng-10).
- [ ] API-07 [M1] Inference request lifecycle driver (dialect-agnostic) —
  console-http::inference
  - Depends on: API-02, API-03, API-04, ENG-10. Seams: PRM-11 (M2), PRM-12 (M2), ENG-12
    (M3), RSP-16 (M6), OPS-22 (M7).
  - Donor sources: serve/server.py:6160-6166, 6241-6297, 5019-5044, 6607-6624, 6692-6710,
    4796-4808, 2093-2110, 3680-3694.
  - Parity tests: serve/test_server.py EngineDeath (2, HTTP halves), GoneClients (1),
    QueuedKeepAlives (1), ModelManagement 503-while-starting (1), MaxTokens debug log (1);
    serve/test_dashboard.py Dashboard.test_chat_gets_503_while_reloading (1).
  - Risk: high. Dropping the stream must always produce STOP and drain before the FIFO place
    is released. Extra reviewer.
  - Done when: gone-client and keep-alive tests pass 50 times in a loop, every error class
    maps to its documented status and body in a table test, and a fake-engine transcript
    shows that a write failure triggers exactly one engine STOP.
  - Note: Owner decision 2026-11-14: implements approved deviation P-3, so typed-extraction
    failures answer 400 `malformed request (<category>: <detail>)` with Rust-side detail
    text.
  - Note: Owner decision 2026-11-14: implements approved deviation P-8, so the error table
    maps a template `raise_exception` (PRM-03) and a DeepSeek encoder assertion failure
    (PRM-07) to 400 instead of the donor's unclean server error (OPEN-07 settled).
  - Note: Follow-ups from wave 3 of M1 (lead, 2026-11-15): the refusal while the server is
    stopping is answered 400 `invalid_request_error` (LD42); a token id outside the
    vocabulary is answered as the donor's tokenizer `IndexError` (ENG-10's finding,
    contracts/backend-seam.md section 12.1); and this task's error table is where approved
    deviation P-8 is mapped.
  - Detail: [tasks/api.md#api-07](tasks/api.md#api-07).
- [ ] API-08 [M1] OpenAI Chat Completions adapter and SSE stream —
  console-http::dialect::openai; pulsar-console (the minimal M1 entry point, LD31)
  - Depends on: API-07, ENG-10. Seams: PRM-06 (M2), PRM-09 (M2), PRM-16 (M2), RSP-11 (M6).
  - Donor sources: serve/server.py:6566-6624, 4909-4930, 4933-5008, 5204-5246, 581-596;
    serve/frontend.py:561-724.
  - Parity tests: serve/test_server.py MaxTokens (5), FitMaxTokens (3), UsageAndStatus (3),
    PromptProgressStream (3), MalformedToolCallAnswers (1), ClientShapes (2), ThinkingBudget
    OpenAI cases (6, joint); serve/test_logprobs.py Api (7); about 30 methods.
  - Risk: medium. Frame order and the content null-versus-empty rule are easy to break.
  - Done when: golden raw-byte SSE transcripts for plain text, reasoning, streamed and whole
    tool calls, JSON mode, logprobs, prompt progress, cancel and engine death match, the
    non-stream collector matches its JSON goldens, all listed donor methods pass, the
    tests assert that the `model` field reports ENG-02's synthetic default model name
    `pulsar-console-synthetic` (PLAN-2), and a spawned-process test shows that at process
    start an engine refused by the ENG-01 guard makes `pulsar-console` exit with a non-zero
    status after one line on standard error naming the engine kind, what the engine
    reported and the path `docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md` (LD28).
  - Note: M1 exit needs only the plain-content subset (the approved plan's 'chat completions
    for plain content'); the checkbox is ticked only when the full definition of done holds,
    after the M2 parsers land.
  - Note: Owner decision 2026-11-14: the synthetic-only rule of OPEN-29 (R29). This task
    records its process-start test name in
    [docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md](../../docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md);
    API-17 keeps the refusal when the full command line lands.
  - Note: Lead decision LD31 (2026-11-14): this task owns the minimal `pulsar-console`
    entry point of M1, in `console/crates/pulsar-console/`, with its tests
    `tests/api08_*.rs` there: the scripted engine, the listen address and port, the wiring
    of `allowed_hosts` from the run config into the API-03 guard, and the process-start
    refusal. API-17 replaces it with the full command line.
  - Note: Follow-ups from wave 2 of M1 (lead, 2026-11-15): this task wires API-15's
    environment settings into the transport's `TransportConfig` and `allowed_hosts` into
    the API-03 guard; prints a `ConfigSamplingError`'s notes on standard output and its
    message on standard error before a non-zero exit; and decides whether the binary
    installs a one-line panic hook (the transport already logs one line per failed request).
  - Note: Follow-ups from wave 3 of M1 (lead, 2026-11-15): the binary prints the ready line
    of contracts/cli.md section 2 on standard output, flushed, once the server accepts
    connections; under `--port 0` it names the bound port (proposal P-25); it carries no
    synthetic marker unless the owner approves the one proposed under PLAN-1. This task
    also wires LD40: an `allowed_hosts` entry that cannot be parsed stops the server at
    start.
  - Detail: [tasks/api.md#api-08](tasks/api.md#api-08).
- [ ] PRM-04 [M1] Byte-level BPE tokenizer, ByteTokenizer and incremental detokenizer —
  console-tokenizer (new crate)
  - Depends on: API-01.
  - Donor sources: tools/strata_tokenizer.py:1-451; serve/server.py:2061-2084, 2294-2313,
    7178-7184; tools/test_tokenizer_glm.py.
  - Parity tests: tools/test_tokenizer_glm.py (11, synthetic vocabularies);
    serve/test_detok.py (3); decode(encode(s)) round trips over the donor boundary corpus
    for four pre-tokenizer families.
  - Risk: medium. Unicode property tables differ between Python's regex module and Rust.
  - Done when: all re-expressed tokenizer and detokenizer tests pass, round trips hold for
    every family, plain-span and type-3/4 behavior is covered, including a literal match
    straddling a span boundary, the ByteTokenizer matches donor ids on hand-computed cases,
    and the crate depends on nothing outside console/ and not on minijinja.
  - Note: Decided by the lead on 2026-11-14: residual Unicode-table differences between
    Python's regex module and the Rust regex crates are accepted when a test names and pins
    them; PRM-04 records them.
  - Note: PRM-04 does not depend on PRM-02, not even as a seam; its tests may later switch
    to PRM-02's shared synthetic trainer with unchanged expectations (R12).
  - Note: Built and merged on 2026-11-15 at commit `7b58580f`. Its Unicode-table
    differences are recorded in research.md, Decision 5, and the llama.cpp license text for
    its pre-tokenizer patterns was added at commit `91a02fd5`. The checkbox stays open: its
    refusals of malformed pack inputs and its explicit size limits are proposal P-24,
    awaiting the owner's decision (OPEN-15). Round trips on a real vocabulary are
    unverified: the test that checks them is ignored unless `PULSAR_CONSOLE_PACK_TOKENIZER`
    names a pack's tokenizer directory.
  - Detail: [tasks/prompt.md#prm-04](tasks/prompt.md#prm-04).
- [ ] API-19 [M1] HTTP test kit and parity ledger population — console-testkit (dev-only
  crate, created here) and console/parity/ledger.json
  - Depends on: API-02, ENG-02, PRM-04, GOV-06. Seams: PRM-02 (M2), ENG-05 (M3).
  - Donor sources: serve/test_server.py:31-35, 1869-1883, 2037-2070, 2364-2475, 1671-1692;
    serve/test_logprobs.py:35-52, 160-192; serve/test_stop.py:1-140.
  - Parity tests: no donor methods of its own; it assigns an owning package to every method
    of the eight API-reader files and the related test_dashboard.py methods.
  - Risk: low. The ledger is the anti-drop mechanism.
  - Done when: the kit is used by at least the API-02 and API-03 tests, and every ledger row
    of the listed files has an owning package that a reviewer can reproduce by counting
    methods in the pinned donor files.
  - Detail: [tasks/api.md#api-19](tasks/api.md#api-19).
- [ ] CNF-01 [P] [M1] Conformance crate scaffold and the console.yml preflight and summary
  jobs — console-conformance (lib and cnf binary skeleton); .github/workflows/console.yml
  (extends the GOV-06 skeleton)
  - Depends on: GOV-06.
  - Donor sources: .github/workflows/tests.yml (the donor gate shape); this repository's
    archived serving-synthetic.yml and revert 005867d8 (anti-patterns).
  - Parity tests: none directly; enables all.
  - Risk: medium. The only workflow file allowed; a YAML mistake blocks every later package.
  - Done when: console.yml runs green on a change containing only the scaffold, a file
    outside the allowed paths and a file under console/ whose name the repository .gitignore
    drops each make preflight fail with a named class, and a rustc -V mismatch is shown to
    fail.
  - Note: Built and merged on 2026-11-14 at commit `fb87f8a2`. The checkbox stays open
    until a green run of CNF-01's revision of console.yml is observed: the only run of
    console.yml so far (2026-11-14, at commit `0f4bc320`) predates that revision, and
    nothing has been pushed since. The reading of B12 it builds is accepted (LD33, R29).
  - Detail: [tasks/conformance.md#cnf-01](tasks/conformance.md#cnf-01).
- [x] CNF-02 [M1] Scenario format, schema, loader, substitution tokens and rename map —
  console-conformance::scenario; contracts/conformance-scenario.schema.json,
  contracts/rename-map.json, contracts/volatile-fields.json
  - Depends on: CNF-01.
  - Donor sources: serve/server.py:199-240, 2061-2100, 7115-7300;
    serve/glm_dsa_fake_engine.py and serve/fake_multi_engine.py headers; serve/test_stop.py
    fake_config.
  - Parity tests: none (infrastructure); the schema is reviewed against at least 10 donor
    test setups.
  - Risk: low.
  - Done when: schema and loader are merged with unit tests for every field and error, ten
    scenarios transcribed from donor test setups load cleanly, and the staged-scan rules
    pass on all sample files.
  - Note: Built and merged on 2026-11-15 at commit `8dc26783`, and done: eleven sample
    scenarios load cleanly, and the three contract files are checked against the loader,
    contracts/naming.md, contracts/deviations.md and contracts/parity-ledger.md. Nothing
    runs a scenario yet (CNF-03, CNF-04, CNF-07, CNF-09).
  - Detail: [tasks/conformance.md#cnf-02](tasks/conformance.md#cnf-02).
- [x] CNF-03 [M1] Raw HTTP client and observation recorder (SSE, NDJSON, disconnect control)
  — console-conformance::client and ::observe
  - Depends on: CNF-02.
  - Donor sources: serve/server.py:5405 (HTTP/1.0), the SSE writers, NDJSON in
    serve/model_api.py; the donor tests' request helpers.
  - Parity tests: self-tests against an in-test std::net server emitting each framing.
  - Risk: medium. SSE edge cases must match what the donor emits.
  - Done when: self-tests show identical observations for the same logical response under
    all three framings, HTTP/1.0 request mode works, and disconnect timing is exact to the
    event.
  - Note: Built and merged on 2026-11-15 at commit `21f5be60`, and done: the self-tests
    show identical logical observations under the three framings, HTTP/1.0 requests are
    sent byte for byte, and disconnects are exact to the event. It uses blocking `std::net`
    sockets, and its self-tests use `std::net` servers. A scenario cannot yet say that a
    step half-closes or disconnects right after its request (CNF-09).
  - Detail: [tasks/conformance.md#cnf-03](tasks/conformance.md#cnf-03).
- [ ] CNF-04 [M1] Normalizer and comparator with deviation annotations —
  console-conformance::normalize and ::compare
  - Depends on: CNF-03.
  - Donor sources: id generation in serve/responses.py (354, 412-418), serve/server.py
    (4936, 5251), serve/frontend.py (805); created and created_at sites; the volatile fields
    of /metrics and /health.
  - Parity tests: negative self-tests: a mutated status, header, event, id cross-reference,
    tape entry or file field each must produce a diff.
  - Risk: high. An over-lenient normalizer creates parity that is not real. Extra reviewer.
  - Done when: all negative self-tests fail as expected, the normalizer implements the
    observable and volatile rule of contracts/parity-ledger.md section 1.1, and the
    volatile-fields list is reviewed against the donor's response builders with a citation
    for each field.
  - Detail: [tasks/conformance.md#cnf-04](tasks/conformance.md#cnf-04).
- [ ] CNF-07 [M1] Process harness for pulsar-console and the fakes —
  console-conformance::process
  - Depends on: CNF-02. Seams: API-17 (M4).
  - Donor sources: serve/test_stop.py:70-140 (Proc, gone, descendants);
    serve/test_glm_dsa_serve.py:220-250.
  - Parity tests: self-tests with a tiny test-only child binary; later used by every
    black-box test.
  - Risk: medium. Process-group semantics differ between Linux and Darwin.
  - Done when: a leak check is proven with a child that forks a grandchild, the harness
    passes on both Linux and macOS runners, and the ready-line contract is documented in
    contracts/cli.md.
  - Note: This task covers the refusal of reserved environment names in the `env` block of
    a scenario's `server.config`, which CNF-02's loader does not check (lead, 2026-11-15).
  - Note: Built and merged on 2026-11-15 at commit `d270f113`:
    `console_conformance::process` (`Launch`, `ServerProcess`, `StopReport`,
    `ScenarioFiles`, `lifecycle_lock`), the test-only child `src/bin/cnf_child.rs` and the
    draft contract contracts/cli.md (the ready line and the process harness). It holds the
    `env` block of a run config it writes to the reserved-name rule. The checkbox stays open: the leak check is proven on
    macOS with the test-only child, and the Linux paths are unverified until a CI run; no
    `pulsar-console` binary exists yet. That the ready line names the bound port under
    `--port 0` is proposal P-25, awaiting the owner (OPEN-15).
  - Detail: [tasks/conformance.md#cnf-07](tasks/conformance.md#cnf-07).

## Phase M2: Prompt and output

**Purpose**: Template compatibility spike and Jinja runtime; request normalization;
special-literal protection; streaming parser for all tool-call syntaxes and both rewriters;
DeepSeek encoder; thinking levels and budget; stop strings; both loop guards; Anthropic
Messages.

**Checkpoint**: Milestone report to the owner: ledger counts and deviations added.

- [ ] PRM-02 [P] [M2] Parity test kit: vendor-template provider, synthetic templates,
  MT19937 and synthetic BPE trainer — console-testkit (extends the API-19 crate);
  console/crates/console-prompt/testdata/; console/.gitattributes
  - Depends on: API-01, API-19.
  - Donor sources: serve/test_prompt_memo.py:37-130;
    serve/test_render_other_models.py:1-113; data/glm-dsa/templates/README.md;
    serve/fixtures/minimax_m31/README.md; serve/fixtures/deepseek_v41/README.md;
    .gitattributes:1-25; Python random.Random as used by serve/test_loop_guard.py and
    serve/test_tools.py.
  - Parity tests: defines the harness: MT19937 reference vectors; the synthetic trainer is
    verified end to end through the render_ids fixture in PRM-08; vendor manifest checks run
    only in the manual job.
  - Risk: medium. License hygiene is the point: no vendor template text or render of one is
    committed.
  - Done when: the MT19937 vectors pass, `git check-attr` shows -text on testdata,
    vendor-gated tests report skipped (never passed) outside the manual job, and a grep of
    console/ for distinctive vendor template phrases finds nothing.
  - Detail: [tasks/prompt.md#prm-02](tasks/prompt.md#prm-02).
- [ ] PRM-03 [M2] Jinja runtime with transformers and Jinja2 sandbox semantics on minijinja
  — console-prompt::jinja
  - Depends on: API-01, PRM-02.
  - Donor sources: serve/frontend.py:37-51; the feature inventory of the donor's chat
    templates (serve/chat_template.jinja, serve/glm5_chat_template.jinja,
    data/glm-dsa/templates/*.jinja, tools/glm_chat_template.jinja,
    tools/mm3/chat_template.jinja, serve/fixtures/minimax_m31/chat_template.jinja,
    tools/ds4/chat_template.jinja, serve/fixtures/glm_tool_images.jinja), read as data.
  - Parity tests: serve/test_qwen_template.py Golden (2, vendor-gated, manual job);
    serve/test_minimax_frontend.py Template differential (2, vendor-gated, manual job);
    about 45 new feature-conformance cases on synthetic snippets.
  - Risk: high. The subsystem's main technical risk; minijinja features are unverified until
    the spike. Extra reviewer.
  - Done when: a spike note lists each inventory feature as supported, overridden or
    rewritten, all synthetic conformance cases pass, and tojson, string and trim use
    console-pyjson semantics; the vendor goldens are checked in the manual job, which
    records hashes, not text.
  - Note: Owner decision 2026-11-14: implements approved deviation P-8: a template
    `raise_exception` yields a typed TemplateError that answers 400 (mapped by API-07).
  - Detail: [tasks/prompt.md#prm-03](tasks/prompt.md#prm-03).
- [ ] PRM-07 [M2] DeepSeek-V4.1 prompt encoder and reference decoder port —
  console-prompt::deepseek
  - Depends on: API-01, PRM-02.
  - Donor sources: serve/ds41_encoding.py:1-995; docs/deepseek-prompt-format.md;
    serve/fixtures/deepseek_v41/*.
  - Parity tests: serve/test_ds41_conformance.py Rendering (19) and Images (4).
  - Risk: low. Mechanical port; DeepSeek's MIT notice must be kept.
  - Done when: the 5 DeepSeek fixture pairs are committed together with DeepSeek's notice
    and match byte for byte, the Rendering and Images tests pass, the module header and
    NOTICE.md carry DeepSeek's MIT notice and source revision, and DeepSeek's license text
    is added to console/LICENSES/ in the same change (lead decision of 2026-11-14).
  - Note: Owner decision 2026-11-14: implements approved deviation P-8: an encoder
    assertion failure yields a typed EncodeError that answers 400 (mapped by API-07).
  - Detail: [tasks/prompt.md#prm-07](tasks/prompt.md#prm-07).
- [ ] PRM-05 [M2] Thinking-level vocabulary, GLM effort dialects and ChatTemplate family
  rendering — console-prompt::effort and console-prompt::template
  - Depends on: PRM-03, PRM-07.
  - Donor sources: serve/frontend.py:37-172, 188-296; serve/glm_dsa_template.py:1-97;
    serve/server.py:6874-6886.
  - Parity tests: serve/test_minimax_frontend.py EffortNames (2), Effort (1), Template (5,
    vendor-gated); serve/test_qwen_template.py Family (2); serve/test_glm_dsa_serve.py
    EffortDialect (7); serve/test_glm_dsa_think_budget.py Level (2); serve/test_server.py
    GlmThinkingLevels (3); serve/test_tools.py ConditionalThinkingTools (2);
    serve/test_ds41_conformance.py effort cases (about 4).
  - Risk: medium. Family detection by substrings is brittle but is the parity target.
  - Done when: every listed test is re-expressed and passes (vendor-gated ones in the manual
    job), invalid-effort error texts match the donor modulo approved branding, and a table
    test covers every spelling and family combination.
  - Note: Proposal P-18, an optional explicit model-family override in configuration, still
    awaits the owner, who decides it before this package starts (OPEN-15, R29); until then
    the detail file's override is not built.
  - Detail: [tasks/prompt.md#prm-05](tasks/prompt.md#prm-05).
- [ ] PRM-06 [M2] Request normalization for OpenAI Chat Completions and Anthropic Messages —
  console-prompt::normalize
  - Depends on: API-01, PRM-05.
  - Donor sources: serve/frontend.py:176-186, 299-398, 561-797;
    serve/response_schema.py:14-36.
  - Parity tests: serve/test_tools.py ClientStops (2 of 5), JsonMode prompt side (4);
    serve/test_server.py StableToolOrder (4), ClientShapes (4);
    serve/test_ds41_conformance.py adapter cases (about 8); serve/test_glm_dsa_serve.py
    ToolPassThrough (3); serve/test_tool_images.py (4) and serve/test_tool_videos.py (9),
    normalization assertions only.
  - Risk: medium. Python truthiness and key order are load-bearing.
  - Done when: every listed test passes, a golden table of at least 40 request bodies maps
    to expected normalized JSON with citations, client key order is preserved, and
    underscore-prefixed client fields never reach internal flags (SEC-6).
  - Note: Owner decision 2026-11-14: implements approved deviation P-3: its typed
    MalformedRequest error carries a Python-like category with Rust-side detail text.
  - Detail: [tasks/prompt.md#prm-06](tasks/prompt.md#prm-06).
- [ ] PRM-08 [M2] Special-literal protection, render_ids, startup template selection and
  prompt measurement — console-prompt::literals, ::render, ::select, ::measure
  - Depends on: PRM-04, PRM-05, PRM-06, PRM-07.
  - Donor sources: serve/frontend.py:401-558; serve/server.py:2532-2569, 2128-2240, 2088,
    2478-2479, 6855-6871, 3704-3763, 3922-3928.
  - Parity tests: serve/test_server.py LiteralSpecials (6), ImageMarkers (1);
    serve/test_ds41_conformance.py ServiceIntegration (3); serve/test_prompt_memo.py SameIds
    (9), LiteralMemoSame (2), SameIdsRealTokenizers (1, opt-in);
    serve/test_render_other_models.py (2: all 72 entries, vendor-gated);
    serve/test_glm_dsa_serve.py TemplateAtStart (2).
  - Risk: medium. This is where Jinja and tokenizer mismatches surface.
  - Done when: LiteralSpecials, the memo and selection tests pass, the verify mode and its
    failure are tested, the start-up error for a missing template is tested and documented
    (B4), and all 72 render_ids entries match in the manual vendor job.
  - Note: Owner decision 2026-11-14: implements approved deviation P-8: a template
    `raise_exception` and a DeepSeek encoder assertion failure raised while rendering a
    request answer 400 (OPEN-07 settled).
  - Detail: [tasks/prompt.md#prm-08](tasks/prompt.md#prm-08).
- [ ] PRM-09 [M2] Streaming OutputParser and parse_tool_call (GLM and Qwen call forms) —
  console-prompt::parse
  - Depends on: API-01, PRM-02.
  - Donor sources: serve/frontend.py:800-936, 1264-1689.
  - Parity tests: serve/test_tools.py GlmCalls (8), QuotedCalls (3), CallEndRescan (2);
    serve/test_server.py MalformedToolCallAnswers (2); serve/test_glm_dsa_serve.py
    ToolPassThrough (1).
  - Risk: medium. Code-point versus byte slicing.
  - Done when: all listed tests pass, chunking invariance holds over every donor vector plus
    a seeded corpus of at least 500 outputs, and the event contract is published in
    contracts/parser-events.md.
  - Detail: [tasks/prompt.md#prm-09](tasks/prompt.md#prm-09).
- [ ] PRM-10 [M2] DSML and MiniMax stream rewriters — console-prompt::parse::rewrite
  - Depends on: PRM-09, PRM-07.
  - Donor sources: serve/frontend.py:939-1261, 1264-1297.
  - Parity tests: serve/test_ds41_conformance.py Parsing (10);
    serve/test_minimax_frontend.py Parser (5); serve/test_deepseek_tool_block.py (6, parser
    parts).
  - Risk: low.
  - Done when: the Parsing and Parser tests pass, the fixture completions re-parse to the
    reference decoder's result at chunk sizes 1, 7 and whole, and MT19937-seeded composition
    fuzzing passes.
  - Detail: [tasks/prompt.md#prm-10](tasks/prompt.md#prm-10).
- [ ] PRM-11 [M2] Prompt-side orchestration: prepare(), forced tool-call prefills, JSON
  mode, context room, media pad expansion — console-prompt::prepare
  - Depends on: PRM-08, PRM-07. Seams: RSP-17 (M6).
  - Donor sources: serve/server.py:3526-3702, 416; serve/frontend.py:599-609;
    serve/response_schema.py:14-36.
  - Parity tests: serve/test_tools.py ForcedToolCalls (3), ConditionalThinkingTools (1),
    JsonMode (4); serve/test_ds41_conformance.py ServiceIntegration (1), Images (4);
    serve/test_server.py MaxTokens (5), FitMaxTokens (3), NoRoomOrNoToken (3);
    serve/test_tool_images.py (4), serve/test_tool_videos.py (9),
    serve/test_glm_dsa_serve.py TextOnlyImages (4), with a fake vision trait.
  - Risk: medium. PRM-11 and PRM-15 depend on each other; media is verified with fakes only.
  - Done when: the listed tests pass with a fake engine and a fake vision trait, all
    overflow and media error texts match, prefill strings for the four families are
    table-tested, and the prepared-prompt contract is documented for console-core.
  - Note: The planner record lists PRM-15 as a dependency, which closes a cycle (PRM-15
    needs PRM-12, which needs PRM-11). PRM-11 calls the cross-turn guard through a trait;
    PRM-15 supplies the implementation and finishes the wiring.
  - Detail: [tasks/prompt.md#prm-11](tasks/prompt.md#prm-11).
- [ ] PRM-12 [M2] Output pipeline: detokenize, stops, quoted markers, thinking resume and
  the run() event logic — console-prompt::pipeline
  - Depends on: PRM-09, PRM-10, PRM-04, PRM-11.
  - Donor sources: serve/server.py:2439-2479, 624-632, 4273-4763, 456-457, 2294-2313,
    3766-3773.
  - Parity tests: serve/test_tools.py ClientStops (5); serve/test_server.py
    SpelledStopMarker (2), EngineEndTests (4, stop parts); serve/test_loop_guard.py
    ThinkingMarkers (8); serve/test_logprobs.py OneConversation (3) and Fields (4),
    attachment-rule assertions.
  - Risk: high. The order of checks must match the donor exactly. Extra reviewer.
  - Done when: the listed tests pass against scripted token streams, a property test shows
    the pipeline equals the parser on inputs without stops or markers, and the directive and
    output contract is published in contracts/output-pipeline.md.
  - Detail: [tasks/prompt.md#prm-12](tasks/prompt.md#prm-12).
- [ ] PRM-13 [M2] Thinking budget: arithmetic, soft close at a sentence end, engine keys,
  Qwen close-as-rendered, settings — console-prompt::budget
  - Depends on: PRM-12, PRM-05, PRM-04.
  - Donor sources: serve/server.py:438-500, 1217-1226, 2831-2867, 3862-3975, 4116-4199,
    4383-4421, 6889-6896, 7311-7320; tools/maya_quants.py:106-165.
  - Parity tests: serve/test_think_budget.py Default (3), Field (3), per-model default (2);
    serve/test_glm_dsa_think_budget.py EngineBudget (12) and related classes (about 11);
    serve/test_server.py ThinkingBudget (6), ThinkingBudgetAtASentenceEnd (5);
    serve/test_qwen_template.py ServerClose (3).
  - Risk: medium. The soft close needs a fixed controller interface with console-core.
  - Done when: every donor arithmetic case is table-tested, the soft close is verified with
    a scripted engine that records each call's prompt and sampling keys, and settings
    validation matches the donor's error texts.
  - Detail: [tasks/prompt.md#prm-13](tasks/prompt.md#prm-13).
- [ ] PRM-14 [M2] Loop guard inside one answer and its slice-controller integration —
  console-prompt::loopguard::answer
  - Depends on: PRM-12, PRM-13.
  - Donor sources: serve/loop_guard.py:1-296; serve/server.py:612-621, 435-437, 3977-3986,
    4087-4095, 4113-4271, 4433-4454.
  - Parity tests: serve/test_loop_guard.py Detection (4), Policy (8), ToolCalls (9),
    Settings (2), Server (10), GuardedUsage (1); Http (1) is in PRM-17.
  - Risk: medium. Depends on console-core honoring bounded sampling overrides.
  - Done when: all listed tests pass with MT19937-reproduced corpora, legitimate-repetition
    cases do not fire, and each restart's ids and sampling are asserted through a recording
    fake engine.
  - Detail: [tasks/prompt.md#prm-14](tasks/prompt.md#prm-14).
- [ ] PRM-15 [M2] Loop guard across turns: tool repeats, blocking, history collapse and
  keep-going — console-prompt::loopguard::turns
  - Depends on: PRM-05, PRM-08, PRM-12.
  - Donor sources: serve/loop_guard.py:299-701; serve/server.py:3534-3572, 3988-4085,
    4291-4303, 4475-4482, 4546-4585, 4625-4644.
  - Parity tests: serve/test_loop_guard.py ToolRepeat (2), ToolBlock (9), Collapse (7);
    serve/test_deepseek_tool_block.py (6); serve/test_prompt_memo.py GistByText (1).
  - Risk: high. The most policy-dense package; it injects server-authored text into prompts.
    Extra reviewer.
  - Done when: all listed tests pass, collapse prefix stability holds over MT19937-generated
    conversations, and the block and keep suffixes for every synthetic family are asserted
    byte for byte; checks against donor source strings run only in the manual job.
  - Note: Implements the cross-turn guard trait that PRM-11 calls (see the note on PRM-11).
  - Detail: [tasks/prompt.md#prm-15](tasks/prompt.md#prm-15).
- [ ] PRM-16 [M2] Parser events to OpenAI and Anthropic response shapes (streamed and
  collected) — console-prompt::shapes
  - Depends on: PRM-09, PRM-12.
  - Donor sources: serve/server.py:4909-4930, 4933-5008, 5204-5246, 5250-5314, 5317-5343;
    serve/frontend.py:808-816.
  - Parity tests: serve/test_tools.py HttpToolCalls (2, shapes), ClientStops and JsonMode
    shape cases; serve/test_ds41_conformance.py ResponseSerialization (2);
    serve/test_server.py ClientShapes (4); at least 20 scripted-run goldens.
  - Risk: low. Ownership boundary with console-http and console-responses.
  - Done when: all shape tests pass, fold-equals-collect is property-tested, and the chunk
    and event schemas are published in the contracts as part of the UI-to-server contract.
  - Detail: [tasks/prompt.md#prm-16](tasks/prompt.md#prm-16).
- [ ] API-09 [M2] Anthropic Messages adapter and event stream —
  console-http::dialect::anthropic
  - Depends on: API-07, ENG-10, PRM-06, PRM-16.
  - Donor sources: serve/server.py:6674-6710, 5250-5314, 5317-5343, 6268-6282;
    serve/frontend.py:727-797, 290-296.
  - Parity tests: serve/test_server.py UsageAndStatus.test_anthropic (1), ClientShapes (1),
    and the Anthropic paths of EngineDeath, QueuedKeepAlives, ThinkingBudget and MaxTokens;
    about 8 methods plus new goldens.
  - Risk: low. The block-index state machine is the subtle part.
  - Done when: golden event transcripts for thinking then text, thinking then tool_use
    (streamed and whole), two consecutive tool calls, stop_sequence, max_tokens and engine
    death match byte for byte, and the collector output matches its JSON goldens.
  - Detail: [tasks/api.md#api-09](tasks/api.md#api-09).

## Phase M3: Engine supervision

**Purpose**: Line-protocol codec, client and supervisor; request-key encoder;
multi-conversation mode; fair slices; restart, unload and shutdown; prompt memo and restore
points; fake engine binaries; engine conformance suite; coordinator-shaped adapter.

**Checkpoint**: Milestone report to the owner.

- [ ] ENG-03 [P] [M3] Typed sampling parameters, request validation and the GEN-line key
  encoder — console-core::engine::params and console-engine::line::keys
  - Depends on: ENG-01, API-04.
  - Donor sources: serve/server.py:466-495, 624-718, 1217-1356, 2489-2530, 4275-4278;
    serve/glm_dsa_tune.py:1-59.
  - Parity tests: serve/test_server.py SamplingKeys (9), RequestChecks (7, engine-capability
    parts), lines 810-829; serve/test_glm_dsa_tune.py Whitelist (4), RequestBody (1),
    EngineLine (1); serve/test_ds4_restore_points.py test_the_engine_line (1);
    serve/test_logprobs.py Fields (4); a committed table of 200 Python float repr outputs.
  - Risk: medium. Byte parity of float formatting.
  - Done when: every SamplingKeys, tune and restore oracle string reproduces byte for byte,
    the float repr table passes, validation errors carry the donor's field names and
    messages, and a default parameter set encodes to an empty key string.
  - Note: Deviation POL-1: the ablate capability is recognized and refused unless an engine
    advertises it.
  - Detail: [tasks/engine.md#eng-03](tasks/engine.md#eng-03).
- [ ] ENG-04 [P] [M3] Line-protocol codec and handshake state machine (pure, no I/O) —
  console-engine::line::codec and ::vram
  - Depends on: ENG-01.
  - Donor sources: serve/server.py:924-951, 1001-1060, 1192-1215, 1356-1451, 1504-1526,
    1528-1555, 532-568, 2242-2262; serve/gpu_map.py:15-30.
  - Parity tests: serve/test_logprobs.py Fields (parse cases); serve/test_prompt_memo.py
    JoinIdsMemo (2); serve/test_dashboard.py GpuMap.test_parse (1); serve/test_server.py
    StaleDoneAfterErr (2, codec half) and lines 1011-1019, 1318-1345;
    serve/test_engine_contract.py ready-flag rules; about 60 table cases and a seeded fuzz
    test.
  - Risk: low. Must never panic on malformed engine output and must share no code with the
    fakes.
  - Done when: every line form of the wire contracts round-trips under table tests, fuzz
    tests run with no panic, and contracts/engine-wire.md restates the grammar with donor
    line citations.
  - Note: Owner decision 2026-11-14: implements approved deviation P-7: the `GENI` path is
    checked against the whitespace-free vision base.
  - Detail: [tasks/engine.md#eng-04](tasks/engine.md#eng-04).
- [ ] ENG-05 [P] [M3] Fake engine binaries speaking the line protocol (absorbs CNF-05) —
  console-fake-engines (new crate): console-fake-engine, console-fake-multi-engine,
  console-fake-silent-engine, console-fake-slow-stop-engine
  - Depends on: none.
  - Donor sources: serve/glm_dsa_fake_engine.py:1-177; serve/fake_multi_engine.py:1-111;
    serve/test_multi.py:236-259, 303-333; tools/maya_names.py:1-78;
    serve/test_engine_contract.py (the contract the fakes satisfy).
  - Parity tests: the fixtures behind serve/test_multi.py (15), serve/test_stop.py
    ServerStops, serve/test_logprobs.py SeveralConversations (1),
    serve/test_glm_dsa_serve.py (7), serve/test_glm_dsa_api.py (23) and
    serve/test_glm_dsa_tune.py EngineLine; about 25 black-box transcript tests; the
    cross-check of tapes against the donor fakes and the as-is run of
    serve/test_engine_contract.py (10) happen only in the manual reference job (CNF-09,
    CNF-10).
  - Risk: medium. The fakes are an independent oracle and must not reuse the client's codec.
  - Done when: four binaries build with no dependency on any other console crate and never
    touch the network, the transcript tests pass, and each binary documents its environment
    controls so a reviewer can compare them line by line with the donor fakes.
  - Detail: [tasks/engine.md#eng-05](tasks/engine.md#eng-05);
    [tasks/conformance.md#cnf-05](tasks/conformance.md#cnf-05).
- [ ] ENG-06 [M3] Line-protocol child engine: spawn, handshake, pump, single-conversation
  generate and drain — console-engine::line::engine and ::io
  - Depends on: ENG-01, ENG-03, ENG-04, ENG-05.
  - Donor sources: serve/server.py:881-1060, 1173-1199, 1356-1526, 1549-1555, 1678-1700,
    2093-2104.
  - Parity tests: serve/test_multi.py AStoppedLongPrompt (2) and Engine single-path
    assertions; serve/test_server.py StaleDoneAfterErr (2), EngineDeath (2),
    PromptProgressStream (3), StatsAfterConsumerStops (1), EngineEndTests (2), lines
    1318-1345; serve/test_engine_contract.py gen, stop and wrap from the client side; about
    22 tests.
  - Risk: high. Correctness bugs here leak one request's tokens into the next. Extra
    reviewer.
  - Done when: all listed tests pass against the Rust fakes on macOS, a cancelled slow
    prompt never hands its lines to the next request, a late EOF from a replaced process
    does not mark the new one dead, and stdin lines are never interleaved under a
    100-request stress test (FIX-1).
  - Note: Owner decision 2026-11-14: implements approved deviation P-6, an optional engine
    ready-timeout setting that is off by default, so the donor's unbounded wait for `READY`
    stays the default (OPEN-10 settled).
  - Note: Owner decision 2026-11-14 (OPEN-29, R29): a line-protocol engine that does not
    declare synthetic provenance in its start-up lines counts as not synthetic and is
    refused by the ENG-01 guard (LD28, fail closed). The form of the declaration is open
    item OPEN-58 (lead; the direction is a fact on an `INFO` line) and is settled with the
    line-protocol packages of this milestone, which record it in
    [docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md](../../docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md).
  - Detail: [tasks/engine.md#eng-06](tasks/engine.md#eng-06).
- [ ] ENG-07 [M3] Multi-conversation mode: rid tagging, routing, quiet timeout and bounded
  drain — console-engine::line::multi
  - Depends on: ENG-06.
  - Donor sources: serve/server.py:1039-1060, 1139-1171, 1557-1676, 1678-1691, 7297-7299;
    serve/fake_multi_engine.py.
  - Parity tests: serve/test_multi.py Engine (6), Interleaved (3), AWedgedRequest (2);
    serve/test_logprobs.py SeveralConversations (1); about 13 tests.
  - Risk: medium. Timing-sensitive tests need scaled timeouts.
  - Done when: every listed test passes, the rid-reuse-after-restart scenario cannot recur,
    and a stress test with 4 places and random cancels ends with an empty routing table and
    every place returned.
  - Note: FIX-1 covers the untagged stop in multi mode; the untagged ERR case is open item
    OPEN-09.
  - Note: This task drives several generations at once over the seam's submit-and-pump
    form; the turn driver of ENG-10 runs one engine call at a time (lead, 2026-11-15).
  - Detail: [tasks/engine.md#eng-07](tasks/engine.md#eng-07).
- [ ] ENG-08 [M3] Engine supervision: restart, graceful close, kill, stall watchdog, death
  notes, narration, context cost, memory settle — console-engine::supervise, ::activity,
  ::settle
  - Depends on: ENG-06.
  - Donor sources: serve/server.py:85-151, 721-770, 828-878, 958-983, 985-999, 1062-1171,
    1702-1728.
  - Parity tests: serve/test_server.py StallWatchdog (4), EngineEndTests (2),
    FailedRestartKeepsContext (1); serve/test_multi.py restart half;
    serve/test_engine_contract.py test_99_quit; serve/test_glm_dsa_serve.py Released (3);
    about 25 tests.
  - Risk: medium. Real process sampling is OS-specific; the NVML path is labeled unverified
    on hardware.
  - Done when: every listed test passes on macOS, the vm_stat and /proc parsers have fixture
    tests, a failed restart keeps max_context and the rid counter, close() kills after the
    configured quit wait, and death notes name no donor URL or product.
  - Note: Owner decision 2026-11-14: implements approved deviation P-10: the frozen-engine
    watchdog uses native samplers on macOS and Linux without `psutil`, and on macOS fires
    only when a GPU-busy signal exists.
  - Detail: [tasks/engine.md#eng-08](tasks/engine.md#eng-08).
- [ ] ENG-11 [P] [M3] Server-side continuations: fair slices, soft thinking close,
  loop-guard and penalty continuation hooks — console-core::turn::continuations
  - Depends on: ENG-09, ENG-10.
  - Donor sources: serve/server.py:296-327, 403-409, 438-495, 3881-3975, 4097-4271,
    4383-4421.
  - Parity tests: serve/test_fair.py FairSlices (5), FairSlicesParallel (1);
    serve/test_server.py ThinkingBudgetAtASentenceEnd (5), ThinkingBudget (6, driver half);
    serve/test_glm_dsa_think_budget.py EngineBudget (12, continuation half); about 30
    driver-level tests.
  - Risk: high. Exact accounting of produced, sent and held tokens across engine calls.
    Extra reviewer.
  - Done when: every listed test passes with stub policies, a property test shows the client
    receives exactly the produced tokens in order with no duplicates or losses, and the
    continuation trait is documented and signed off by the console-prompt owner.
  - Note: Fair slices, the soft close of a thinking budget and the loop guard's
    continuations go through the `ContinuationPolicy` hook of ENG-10's turn driver (lead,
    2026-11-15).
  - Detail: [tasks/engine.md#eng-11](tasks/engine.md#eng-11).
- [ ] ENG-12 [M3] EngineHost lifecycle: start, unload and idle unload, model load and
  unload, context reload, facts, shutdown — console-core::host
  - Depends on: ENG-08, ENG-10.
  - Donor sources: serve/server.py:2639-2821, 5465-5505, 6027-6036, 6101-6131, 6256-6267,
    6963-7041, 7409-7452, 7164-7299.
  - Parity tests: serve/test_server.py IdleUnload (4), ModelManagement (5, host half),
    FailedRestartKeepsContext (1), EngineDeath.test_error_then_restart; serve/test_stop.py
    ServerStops (engine wind-down); serve/test_glm_dsa_serve.py Released (3); about 22
    tests.
  - Risk: medium. Writes back to the run config.
  - Done when: every listed test passes, a failed reload restores the old size and reports
    failed, the config write is atomic and keeps unknown keys, and shutdown sends WRAP
    before STOP with no fake engine surviving (FIX-1: reload quits gracefully).
  - Note: Proposal P-17, a literal-parity setting for the old reload behavior: not built
    (declined 2026-11-14); FIX-1.1 applies.
  - Note: When it ports the reload path, this task fixes two timing differences in
    ENG-02's scripted engine: the reload delay is read once when the engine is built, where
    the donor reads the environment at each reload; and a reload to the same context does
    not sleep, where the donor always sleeps (lead, 2026-11-15).
  - Note: The wrap and shutdown sequencing and the idle-unload timing use ENG-10's
    `TurnDriver::unload` and `TurnDriver::set_stopping` (lead, 2026-11-15).
  - Detail: [tasks/engine.md#eng-12](tasks/engine.md#eng-12).
- [ ] ENG-15 [P] [M3] Engine launch specification from the run config, and GLM link mode —
  console-engine::launch and ::multigpu::glm_link
  - Depends on: ENG-01, API-15.
  - Donor sources: serve/server.py:2006-2058, 893-897, 920-923, 7197-7203, 7246-7252;
    serve/glm_link.py:1-124; tools/maya_names.py:50-57.
  - Parity tests: serve/test_server.py GpuChoice (1); serve/test_glm_link.py (4, probe
    mocked); about 15 tests.
  - Risk: low. Hardware branches are fixture-tested and labeled unverified on hardware
    (PLAT-1).
  - Done when: every listed test passes on macOS with a mocked probe, the child_env table
    covers all branches including the SEC-7 denylist, and OS checks happen at run time
    rather than through cfg gates.
  - Note: This task builds the typed run-config accessors it consumes that API-15 did not
    build (`exe`, `args`, `gpu`, `backend`, `installer`, `vision`, `vision_off`, `ablate`,
    `turbo`, `sampling`, `port`), with the OPS packages of M7 (lead, 2026-11-15).
  - Detail: [tasks/engine.md#eng-15](tasks/engine.md#eng-15).
- [ ] ENG-17 [M3] Prompt memo and DeepSeek restore points — console-prompt::memo
  - Depends on: ENG-03, PRM-08.
  - Donor sources: serve/server.py:773-825, 2088-2090, 2128-2239, 2265-2291, 2532-2569,
    4422-4431.
  - Parity tests: serve/test_prompt_memo.py SameIds (10), LiteralMemoSame (2),
    RestorePointsFast (2), GistByText (1); serve/test_ds4_restore_points.py RestorePoints
    (8); about 22 tests, on synthetic templates.
  - Risk: medium. Tests must not depend on vendor templates.
  - Done when: randomized multi-turn histories give equal ids with the memo on and off for
    every synthetic family template, verify mode raises on an injected difference, the
    restore-point variants agree on 10,000 random sequences, and all 8 RestorePoints tests
    pass.
  - Detail: [tasks/engine.md#eng-17](tasks/engine.md#eng-17).
- [ ] ENG-19 [P] [M3] Blocking runtime adapter: the in-process seam a future PulsarMLX
  engine plugs into — console-engine::runtime
  - Depends on: ENG-01.
  - Donor sources: no donor source; shape references in this repository:
    crates/backend/src/step.rs:59-78, 273-300 and the archived
    crates/serve-synthetic/src/runtime_adapter.rs (tag
    archive/2026-09-21/feat/openai-serving), read only; donor semantics:
    serve/server.py:191-240.
  - Parity tests: no donor test (the seam does not exist in the donor); passes the ENG-18
    seam battery plus about 12 adapter tests.
  - Risk: medium. Must not depend on any engine-track crate.
  - Done when: the adapter passes the seam battery with a synthetic runtime, depends on
    nothing outside console/, and contracts/backend-seam.md documents how an engine-track
    deliver hook maps onto the sink, including replay of a committed step.
  - Detail: [tasks/engine.md#eng-19](tasks/engine.md#eng-19).
- [ ] ENG-18 [M3] Engine conformance suite and seam conformance harness —
  console-engine::conformance (feature), console-engine-check binary,
  console-engine/tests/conformance_*.rs
  - Depends on: ENG-05, ENG-06, ENG-07, ENG-19.
  - Donor sources: serve/test_engine_contract.py:1-289; tools/test_metal_serve.py:1-75;
    serve/test_glm_dsa_serve.py:530-542.
  - Parity tests: serve/test_engine_contract.py (10) re-expressed one to one;
    serve/test_glm_dsa_serve.py ContractTestOnTheFake (1); tools/test_metal_serve.py (3
    checks) as an optional profile skipped because no real engine runs; a seam battery of
    about 12 tests.
  - Risk: low.
  - Done when: `cargo test -p console-engine --features conformance` runs the protocol and
    GLM profiles against the fake engine with 10 run and 1 skipped, the seam battery passes
    for all four implementations, and console-engine-check exits non-zero on failure.
  - Detail: [tasks/engine.md#eng-18](tasks/engine.md#eng-18).

## Phase M4: Monitoring and admin

**Purpose**: `/health`, `/status`, `/metrics` and Prometheus; discovery and tokenizer
routes; settings, context, thinking-budget, port and report routes; resumable web streams;
logging, signals, CLI and graceful shutdown; telemetry core and the Apple Silicon reader.

**Checkpoint**: Milestone report to the owner.

- [ ] API-05 [P] [M4] Monitor model: status, live rate, peaks, totals, history and queue
  watchdog — console-core::monitor
  - Depends on: API-01.
  - Donor sources: serve/server.py:172-196, 2345-2379, 2383-2480, 3239-3311, 3774-3811,
    4692-4756, 4766-4793.
  - Parity tests: serve/test_server.py LiveRateBursts (5), LiveRate (3), TimingsDrafts (1),
    StatsAfterConsumerStops (1); serve/test_dashboard.py peak and api tests (3); injected
    clock.
  - Risk: low.
  - Done when: all listed tests pass with an injected clock, the hook trait is documented in
    the contracts, and the rate arithmetic matches the donor's burst scenarios.
  - Detail: [tasks/api.md#api-05](tasks/api.md#api-05).
- [ ] API-10 [P] [M4] Resumable web-app streams and answers/*.jsonl — console-http::resume
  - Depends on: API-08, API-15. Seams: RSP-17 (M6).
  - Donor sources: serve/server.py:5011-5016, 5047-5119, 5122-5201, 6598-6606, 6626-6672,
    7348-7350.
  - Parity tests: serve/test_stream_jobs.py StreamJobs (4), StreamJobFiles (4);
    serve/test_server.py TestCarryEmbeddings (1); new HTTP tests for reconnect, cancel and
    the 404.
  - Risk: medium. The job outlives its connection.
  - Done when: all 9 donor methods pass, a kill-and-restart test shows the restart note and
    a replayable stream, and a generated .jsonl holds one chunk per line plus the done line;
    the file-backed tests run with disk persistence explicitly enabled (PRIV-1).
  - Detail: [tasks/api.md#api-10](tasks/api.md#api-10).
- [ ] API-11 [P] [M4] llama.cpp-compatible discovery and utility routes —
  console-http::routes::llama
  - Depends on: API-03, PRM-04, PRM-05, PRM-08, ENG-12. Seams: RSP-17 (M6).
  - Donor sources: serve/server.py:6101-6131, 6299-6325, 6247-6255, 3704-3763.
  - Parity tests: serve/test_server.py WebApp discovery tests (3); serve/test_dashboard.py
    token count and tokenize tests (2).
  - Risk: low. /props exposes a run-time template source that must never be captured in
    committed fixtures (B4).
  - Done when: all 5 donor methods pass, /props, /slots and /v1/models match their goldens
    in loaded, unloaded and dead states, and error messages match.
  - Detail: [tasks/api.md#api-11](tasks/api.md#api-11).
- [ ] API-16 [P] [M4] Logging, signals and parent watch — pulsar-console (lib) ::logging and
  ::signals
  - Depends on: API-15.
  - Donor sources: serve/server.py:6963-7041, 7044-7112, 7155-7163.
  - Parity tests: serve/test_server.py StampedLog (1); serve/test_stop.py WatchParent (5).
  - Risk: low.
  - Done when: all 6 donor methods pass, and a spawned-binary test shows SIGHUP under an
    inherited SIG_IGN is ignored and a double SIGINT exits 130.
  - Detail: [tasks/api.md#api-16](tasks/api.md#api-16).
- [ ] OPS-17 [M4] Telemetry sampler core and the /metrics hardware fields —
  console-host::sampler
  - Depends on: API-05, ENG-10.
  - Donor sources: serve/telemetry.py L33-35, L870-1116; serve/server.py L3219-3237,
    L3313-3374.
  - Parity tests: serve/test_telemetry.py Sampler (5 of the class's 6, fake reader and
    injected clock; test_gpu_pids is listed under OPS-19).
  - Risk: low.
  - Done when: the 5 tests pass deterministically over 50 repeated runs, and the /metrics
    hardware and history shape is checked against a contract fixture with nulls in every
    position.
  - Note: Owner decision 2026-11-14: implements approved deviation P-10: the sampler's
    native macOS and Linux readers replace `psutil` and supply the GPU-busy signal the
    ENG-08 watchdog needs.
  - Detail: [tasks/ops.md#ops-17](tasks/ops.md#ops-17).
- [ ] API-06 [M4] Monitoring routes: /health, /status, /v1/status, /metrics,
  /metrics/prometheus — console-http::routes::monitor
  - Depends on: API-03, API-05, OPS-17, ENG-09, ENG-10, ENG-12. Seams: RSP-06 (M5), OPS-21
    (M7), OPS-22 (M7), ENG-13 (M9).
  - Donor sources: serve/server.py:6019-6049, 6087-6100, 5989-6002, 3313-3374, 3376-3388,
    3390-3472, 3474-3524, 2316-2343, 2481-2487.
  - Parity tests: serve/test_server.py PrometheusMetrics (1), WebApp metrics tests (4),
    UsageAndStatus.test_v1_status (1); serve/test_dashboard.py health and metrics tests (6),
    GpuMap route half; about 13 methods.
  - Risk: medium. Wide surface; key order and conditional fields must match.
  - Done when: golden JSON tests for /health, /v1/status and /metrics assert key order and
    conditional fields, a Prometheus golden checks the exposition text byte for byte,
    /health reports the synthetic backend, and all listed donor methods pass.
  - Detail: [tasks/api.md#api-06](tasks/api.md#api-06).
- [ ] API-13 [M4] Dashboard admin routes: settings, thinking budget, port and report —
  console-http::routes::admin
  - Depends on: API-03, API-04, API-15, PRM-13, OPS-17, ENG-12. Seams: RSP-09 (M6).
  - Donor sources: serve/server.py:6003-6006, 6419-6432, 2571-2582, 6054-6056, 6191-6202,
    2831-2867, 6057-6060, 6354-6366, 2869-2929, 6078-6086, 3181-3217, 158-159, 7368-7376;
    tools/maya_quants.py:158-165.
  - Parity tests: serve/test_server.py SharedSettings (6, HTTP halves);
    serve/test_dashboard.py Port (2), Dashboard.test_report_leaves_secrets_out (1); new
    tests for the run-script rewrite and the exit-76 path.
  - Risk: medium. Rewrites must preserve unknown keys and formatting.
  - Done when: all listed donor methods pass, the shared-settings and run-config rewrites
    match Python's indent=1 output, and the report test shows secrets masked and log
    filtering applied.
  - Note: The planner records make API-13 and API-17 depend on each other (the port route
    restarts through the lifecycle). API-13 calls a lifecycle trait that API-17 implements,
    so API-13 does not wait for API-17.
  - Detail: [tasks/api.md#api-13](tasks/api.md#api-13).
- [ ] OPS-18 [M4] Apple Silicon host reader — console-host::apple
  - Depends on: OPS-17.
  - Donor sources: serve/telemetry.py L871-889, L963-988; serve/server.py L85-119; maya.py
    L873-878.
  - Parity tests: no donor equivalent (PLAT-2); serve/test_telemetry.py
    Sampler.test_this_machine as a live shape test; new fixture tests for the
    vm_statistics64, processor-tick and PerformanceStatistics parsers.
  - Risk: medium. Undocumented macOS keys; every value degrades to null.
  - Done when: fixture parsers pass on every platform, a live sample on the macOS runner has
    non-null cpu, ram_used, ram_total and gpu_name, unsafe code is confined to one module
    with SAFETY comments, and the docs label it measured on the CI runner only.
  - Detail: [tasks/ops.md#ops-18](tasks/ops.md#ops-18).
- [ ] API-14 [M4] Context reload route and the delegated dashboard route shells —
  console-http::routes::admin_delegated
  - Depends on: API-03, API-15, ENG-09, ENG-12, OPS-18. Seams: OPS-05 (M7), OPS-06 (M7),
    OPS-07 (M7), OPS-09 (M7), OPS-10 (M7), OPS-21 (M7), OPS-22 (M7), RSP-12 (M6), RSP-16
    (M6).
  - Donor sources: serve/server.py:6050-6053, 6340-6352, 2721-2821, 6061-6077, 6203-6240,
    6368-6417, 6179-6181, 6434-6461.
  - Parity tests: serve/test_dashboard.py context tests (4),
    ContextCost.test_set_context_rewrites_the_command (1); serve/test_turbo.py TurboServer
    (2, route halves); serve/test_server.py FailedRestartKeepsContext (1, joint).
  - Risk: medium. Ownership overlap with the manage, engine and attachment packages; each
    handler shell lives in exactly one package.
  - Done when: all listed donor methods pass with fake manage and engine traits, a route
    table test shows each delegated route's guard and status rules, and the reload test
    shows 503 on inference routes during a reload, both end states and the saved context.
  - Note: Proposal P-17, a literal-parity setting for the old reload behavior: not built
    (declined 2026-11-14); the reload route uses the FIX-1.1 graceful close of ENG-12.
  - Detail: [tasks/api.md#api-14](tasks/api.md#api-14).
- [ ] API-17 [M4] pulsar-console binary: CLI, start-up assembly and graceful shutdown —
  pulsar-console (bin and lib)
  - Depends on: API-02, API-03, API-06, API-07, API-08, API-09, API-10, API-11, API-13,
    API-14, API-15, API-16, ENG-02, ENG-05, ENG-06, ENG-12, PRM-04, PRM-08, OPS-18. Seams:
    API-12 (M8), RSP-09 (M6), OPS-05 (M7), OPS-09 (M7), OPS-21 (M7).
  - Donor sources: serve/server.py:7115-7452, 6758-6794, 6797-6803, 1702-1728;
    serve/update.py:20; serve/test_stop.py:1-140.
  - Parity tests: serve/test_stop.py ServerStops (5, spawned binary with the fake engine);
    new tests for port in use, the ready line, the API-key default and the wrap-then-QUIT
    order.
  - Risk: high. The integration point for every subsystem; start-up and shutdown order are
    user-visible. Extra reviewer.
  - Done when: all 5 ServerStops methods pass on macOS and Linux, a start-up test asserts
    the exact order of log lines for the scripted engine and the line engine, a shutdown
    transcript shows WRAP, then DONE or STOP, then QUIT, and the full command line keeps
    ENG-02's synthetic default model name `pulsar-console-synthetic` (PLAN-2) and the
    API-08 start-up refusal, with its test, of an engine that does not report synthetic
    provenance (LD28).
  - Note: test_old_engine_name is re-expressed as a refusal of the legacy engine name with a
    clear error (BRAND-1, B2).
  - Note: Follow-up from wave 3 of M1 (lead, 2026-11-15): the binary prints the ready line
    of contracts/cli.md section 2 on standard output, flushed, once the server accepts
    connections; under `--port 0` it names the bound port (proposal P-25); it carries no
    synthetic marker unless the owner approves the one proposed under PLAN-1.
  - Detail: [tasks/api.md#api-17](tasks/api.md#api-17).
- [ ] API-20 [M4] HTTP API contract documents and route inventory gate —
  specs/022-console-serving-parity/contracts/http/ and a console-http test
  - Depends on: API-03, API-06, API-08, API-09, API-10, API-11, API-13, API-14. Seams:
    API-12 (M8), WEB-05 (M8).
  - Donor sources: all routes above; serve/web/*.js route references.
  - Parity tests: no donor methods; documents what the other packages' tests define.
  - Risk: low. Documentation drifts unless gated.
  - Done when: every route in the router appears in the contract index and the reverse,
    every deviation id appears where it applies, and a reviewer can follow any route from
    contract to handler to tests.
  - Detail: [tasks/api.md#api-20](tasks/api.md#api-20).

## Phase M5: Responses API

**Purpose**: Normalizer and serializer; in-memory store; background jobs with replay; schema
validator; routes.

**Checkpoint**: Milestone report to the owner.

- [ ] RSP-01 [P] [M5] Responses limits configuration and in-memory ResponseStore —
  console-responses::config and ::store
  - Depends on: API-01, API-15.
  - Donor sources: serve/response_config.py (32 lines); serve/response_store.py (201 lines);
    serve/server.py:6476-6491.
  - Parity tests: serve/test_response_store.py (8); serve/test_responses.py StoreBounds (2).
  - Risk: low. Byte thresholds depend on exact Python JSON encoding.
  - Done when: all 10 re-expressed tests pass, a table test proves each of the 18 limits'
    default, bounds and error, and the limits section of contracts/responses.md is written;
    the two donor alias tests assert that legacy names are not read (B2).
  - Detail: [tasks/responses.md#rsp-01](tasks/responses.md#rsp-01).
- [ ] RSP-02 [P] [M5] Structured output: restricted JSON Schema validator and
  validate-before-publish buffer — console-responses::schema (no tokio, no I/O)
  - Depends on: API-01, ENG-10.
  - Donor sources: serve/response_schema.py (204 lines); serve/server.py:3500-3501;
    serve/frontend.py:599-609.
  - Parity tests: serve/test_responses_schema.py (10; eight become HTTP tests in RSP-06, one
    is replaced because the validator is built in, one becomes a structural assertion);
    about 40 new edge-semantics unit tests.
  - Risk: medium. Divergence from python-jsonschema edge semantics.
  - Done when: unit tests cover every allowed keyword, every compile error, strict mode, the
    limits, the zero deadline and cancellation, and a scripted-stream test proves the buffer
    releases nothing on failure; no jsonschema crate is used (B6).
  - Detail: [tasks/responses.md#rsp-02](tasks/responses.md#rsp-02).
- [ ] RSP-03 [M5] Responses request normalizer, input items, tools and sealed reasoning —
  console-responses::request
  - Depends on: RSP-02, PRM-06, PRM-11.
  - Donor sources: serve/responses.py:1-352; docs/RESPONSES.md (wording only).
  - Parity tests: serve/test_responses.py rejected shapes (28), HistoryValidation (2) and
    related methods; serve/test_responses_tools.py request-shape halves (5).
  - Risk: medium. Python type-strictness traps.
  - Done when: all 28 rejected shapes pass with their message substrings, every 400 grouping
    condition is tested, and a seal and unseal round trip and a foreign-blob drop are
    tested; the emitted sealed-reasoning prefix is the product one (B2).
  - Detail: [tasks/responses.md#rsp-03](tasks/responses.md#rsp-03).
- [ ] RSP-04 [M5] Responses event serializer and response object — console-responses::events
  - Depends on: RSP-02, RSP-03, ENG-10, PRM-09, PRM-10.
  - Donor sources: serve/responses.py:353-545.
  - Parity tests: serve/test_responses.py (6 serializer-level);
    serve/test_responses_tools.py ToolContracts (about 12 of 15).
  - Risk: medium.
  - Done when: scripted-stream tests reproduce the exact event-name sequence, sequence
    numbers, terminal uniqueness and snapshot shapes for every listed case, with goldens
    under console/crates/console-responses/tests/data/.
  - Detail: [tasks/responses.md#rsp-04](tasks/responses.md#rsp-04).
- [ ] RSP-05 [M5] Background job manager with bounded event history and replay —
  console-responses::jobs
  - Depends on: RSP-01, ENG-09.
  - Donor sources: serve/response_jobs.py (273 lines).
  - Parity tests: serve/test_response_jobs.py manager-level halves of 21 methods, with
    scripted work closures.
  - Risk: high. Exactly one terminal state under completion, cancel and deadline races.
    Extra reviewer.
  - Done when: all manager-level tests pass including a 200-iteration race stress, no path
    emits two terminal events, and a cancel wait returns in_progress while the worker holds
    the engine.
  - Detail: [tasks/responses.md#rsp-05](tasks/responses.md#rsp-05).
- [ ] RSP-06 [M5] Responses HTTP routes (foreground, store, retrieve, input_items, delete)
  and status and metrics hooks — console-responses::routes
  - Depends on: RSP-01, RSP-02, RSP-03, RSP-04, API-03, API-07, API-08, ENG-02, PRM-02,
    PRM-09, PRM-10. Seams: RSP-16 (M6), RSP-17 (M6).
  - Donor sources: serve/server.py:6160-6297, 6476-6524, 6526-6564, 5821-5921, around 3500,
    the responses metrics exporters.
  - Parity tests: serve/test_responses.py (21, two SDK tests become structural assertions);
    serve/test_responses_tools.py (15 plus 5 DeepSeek); serve/test_responses_schema.py (10);
    about 54 methods.
  - Risk: medium. Heavy reliance on the prompt layer and the fake engine.
  - Done when: all ported HTTP tests pass against the in-process server with the fake
    engine, each donor method maps to a Rust test in a parity table, and /v1/status and the
    Prometheus output carry the responses blocks.
  - Detail: [tasks/responses.md#rsp-06](tasks/responses.md#rsp-06).
- [ ] RSP-07 [M5] Background Responses over HTTP: queued create, replay streams, cancel and
  resource ownership — console-responses::routes::background
  - Depends on: RSP-05, RSP-06, ENG-09, ENG-12. Seams: RSP-17 (M6), RSP-19 (M6).
  - Donor sources: serve/server.py:6497-6505 and the background stream and cancel handlers;
    serve/response_jobs.py.
  - Parity tests: serve/test_response_jobs.py (21 at HTTP level, one SDK test structural);
    serve/test_responses.py (2).
  - Risk: high. Cross-cutting with the engine FIFO and idle unload. Extra reviewer.
  - Done when: all 23 ported methods pass, and stress loops of create, cancel and
    retrieve-stream leak no reader slots, FIFO places or temp files.
  - Detail: [tasks/responses.md#rsp-07](tasks/responses.md#rsp-07).

## Phase M6: MCP, attachments, media

**Purpose**: MCP hub over stdio and Streamable HTTP, tool loop and fake MCP server; Office,
OpenDocument, EPUB, RTF and PDF readers; media seam, external encoder adapter and the
DeepSeek picture preprocessor.

**Checkpoint**: Milestone report to the owner.

- [ ] ENG-14 [P] [M6] Vision helper process, SVE1 embeddings files and engine memory lending
  — console-engine::vision; the fake vision encoder binary in console-fake-engines
  - Depends on: ENG-05, ENG-06, ENG-09, ENG-10.
  - Donor sources: serve/server.py:1731-1955, 1957-2003, 3574-3679, 4693-4694, 7217-7286.
  - Parity tests: serve/test_server.py VisionFootprint (3), TestCarryEmbeddings (1);
    serve/test_engine_contract.py test_09; serve/test_glm_dsa_serve.py TextOnlyImages (4);
    serve/test_tool_images.py (4), serve/test_tool_videos.py (9, joint with console-media);
    about 25 tests.
  - Risk: medium. Lending is unverified on hardware; on Apple Silicon the encoder stays
    resident.
  - Done when: every listed test passes with the fake encoder, the vision-memory.json key
    format and selection rule match the donor on fixtures, every FIFO place is held from
    VLEND to VRECLAIM, and per-request embeddings files are removed after success, error and
    cancellation.
  - Note: Owner decision 2026-11-14: implements approved deviation P-7: the vision
    temporary directory is created under a base path free of whitespace, and start-up
    refuses when no such base exists.
  - Detail: [tasks/engine.md#eng-14](tasks/engine.md#eng-14).
- [ ] RSP-08 [P] [M6] MCP JSON-RPC framing and the fake MCP server binary (absorbs CNF-06) —
  console-mcp::jsonrpc and the console-mcp test-support binary fake-mcp-server
  - Depends on: API-02.
  - Donor sources: serve/mcp_fake_server.py (172 lines); serve/mcp.py:155-171;
    serve/test_mcp.py (usage).
  - Parity tests: no direct donor tests; all 24 serve/test_mcp.py methods drive this binary;
    6 smoke tests; the hub-versus-fake cross-runs against the donor happen only in the
    manual reference job.
  - Risk: low. It must misbehave exactly as the donor double does.
  - Done when: the binary builds in the console workspace, its smoke tests pass, its command
    line matches the fake MCP server contract, and integration tests reach it through
    `CARGO_BIN_EXE_fake-mcp-server`.
  - Detail: [tasks/responses.md#rsp-08](tasks/responses.md#rsp-08);
    [tasks/conformance.md#cnf-06](tasks/conformance.md#cnf-06).
- [ ] RSP-09 [M6] MCP client: configuration, stdio transport, server lifecycle and hub —
  console-mcp::{config, stdio, server, hub, text}
  - Depends on: RSP-08, API-15, API-17, ENG-10.
  - Donor sources: serve/mcp.py:1-243, 373-460, 458-591, 594-660.
  - Parity tests: serve/test_mcp.py Client (9), Config (2), spawning fake-mcp-server; config
    files never named mcp.json.
  - Risk: medium. Process-group kill and restart races.
  - Done when: all 11 ported tests pass on macOS, the process group is gone within about 4 s
    of close, the GET /mcp status shape is snapshot-tested, and contracts/mcp.md is written;
    no rmcp crate is used (B6).
  - Detail: [tasks/responses.md#rsp-09](tasks/responses.md#rsp-09).
- [ ] RSP-10 [M6] MCP Streamable HTTP transport, the outbound curl facade and the MCP
  listing CLI — console-mcp::http; console-core::outbound (curl facade); `pulsar-console mcp
  list`
  - Depends on: RSP-09, API-17.
  - Donor sources: serve/mcp.py:244-371, 662-669.
  - Parity tests: serve/test_mcp.py HttpClient (2) against fake-mcp-server in HTTP mode; 3
    new tests; facade tests against a loopback `std::net` fixture server.
  - Risk: medium. Outbound HTTPS goes only through the single curl facade (B7), which this
    package writes for reuse by RSP-17 and OPS-16; see Reconciliations R17.
  - Done when: all 5 tests pass, the facade's own tests pass against the loopback fixture
    server with no TLS crate and no `hyper`, the CLI is documented in contracts/mcp.md, and
    a reviewer confirms the header set and timeout arithmetic match the contract.
  - Detail: [tasks/responses.md#rsp-10](tasks/responses.md#rsp-10).
- [ ] RSP-11 [M6] MCP tool loop, strata_mcp chunk events and the GET /mcp route —
  console-mcp::tool_loop and the GET /mcp handler
  - Depends on: RSP-09, API-03, API-06, API-08, API-11, PRM-11. Seams: WEB-05 (M8).
  - Donor sources: serve/server.py:4811-4887, 6572-6594, the MCP chunk rendering around
    4971-4974, 6007-6011, 6327-6338; serve/web/chats.js:313, 357-369, 432, 483;
    serve/web/server.js:115-129.
  - Parity tests: serve/test_mcp.py ToolLoop (10), NoServers (1), at HTTP level with the
    fake engine and fake MCP server.
  - Risk: medium. Chunk ordering and cancel propagation during a tool.
  - Done when: all 11 ported tests pass, the strata_mcp event schema with every field the
    dashboard reads is in the UI-to-server contract, and a test shows no MCP path is
    reachable from /v1/responses or /v1/messages.
  - Detail: [tasks/responses.md#rsp-11](tasks/responses.md#rsp-11).
- [ ] RSP-12 [P] [M6] Attachment readers: text sniffing, ZIP, Word, Excel, PowerPoint,
  OpenDocument, EPUB, RTF — console-attach::{text, zip, ooxml, odf, epub, rtf, detect}
  (pure, no tokio)
  - Depends on: none.
  - Donor sources: serve/attach.py:1-503.
  - Parity tests: serve/test_attach.py Documents (7), Text (6), with fixtures generated in
    test code; about 15 new unit tests.
  - Risk: medium. The ZIP reader is security-relevant and must enforce caps while inflating.
  - Done when: all 13 ported tests and the new unit tests pass, a fuzz test feeds 1,000
    random and mutated zips without panics and within caps, every donor error string is
    traceable, and new dependencies are recorded with licenses in research.md.
  - Note: Owner decision 2026-11-14: implements approved deviation P-4: error-message
    prefixes are kept exactly, with the parenthesized detail taken from the Rust reader.
  - Detail: [tasks/responses.md#rsp-12](tasks/responses.md#rsp-12).
- [ ] RSP-13 [M6] PDF object layer: lexer, object scan, stream filters, page tree —
  console-attach::pdf::{lexer, object, filters, document}
  - Depends on: RSP-12.
  - Donor sources: serve/pdf_text.py:1-454.
  - Parity tests: no donor test at this layer (serve/test_attach.py PurePdf depends on it);
    about 25 new unit tests.
  - Risk: medium. A tolerant parser over hostile input.
  - Done when: unit tests pass, a 2,000-iteration mutation fuzz produces no panic and
    respects caps and the deadline, and module heads carry mapping comments to the donor
    lines.
  - Detail: [tasks/responses.md#rsp-13](tasks/responses.md#rsp-13).
- [ ] RSP-14 [M6] PDF text interpreter, fonts and encodings, and page pictures —
  console-attach::pdf::{fonts, glyphs, content, pictures}
  - Depends on: RSP-13.
  - Donor sources: serve/pdf_text.py:455-805.
  - Parity tests: serve/test_attach.py PurePdf (5); about 15 new unit tests.
  - Risk: medium. Exact-string outputs; the glyph table must be transcribed exactly.
  - Done when: all 5 PurePdf tests pass with identical strings, the new unit tests pass, the
    glyph-table provenance line is in NOTICE.md, and the fuzz harness is extended to content
    streams with no panic path.
  - Detail: [tasks/responses.md#rsp-14](tasks/responses.md#rsp-14).
- [ ] RSP-15 [M6] PDF orchestrator and optional poppler adapter —
  console-attach::pdf::extract and console-attach::poppler (feature)
  - Depends on: RSP-14.
  - Donor sources: serve/pdf.py (184 lines).
  - Parity tests: serve/test_pdf.py Extract (6), RealPdfExtras (1), MissingPoppler (3),
    against fake poppler scripts in tests/data/fake-poppler/; 4 contract tests.
  - Risk: low. Poppler stays an optional external program, never bundled.
  - Done when: all tests pass with and without real poppler, the fake-poppler tests assert
    exact argv, the temp directory is removed on every path, and the timeout is proven with
    a sleeping fake.
  - Detail: [tasks/responses.md#rsp-15](tasks/responses.md#rsp-15).
- [ ] RSP-17 [M6] Media plumbing and the vision seam: sources, capabilities, prompt
  placeholder expansion — console-media::{source, seam, expand, capability}
  - Depends on: ENG-02, ENG-09, ENG-10, ENG-12, ENG-14, PRM-04, PRM-06, PRM-11, API-15,
    RSP-10 (the outbound curl facade, R17).
  - Donor sources: serve/server.py:3575-3679, 1820-1831, 7217-7286 and the capability
    reporting sites; serve/frontend.py media_of and deepseek_images.
  - Parity tests: serve/test_tool_videos.py and serve/test_tool_images.py media-order tests
    (shared with PRM-11); serve/test_responses.py test_images_reach_prompt_and_engine; media
    halves of serve/test_response_jobs.py image tests; about 10 new tests.
  - Risk: medium. Remote URLs and local paths are opt-in (SEC-4).
  - Done when: the ported tests pass with fake backends, no temp file survives any failure
    path, capability flags appear in /health, /v1/models and /v1/status, source-policy
    refusals are tested, and the vision backend trait is documented in contracts/media.md.
  - Detail: [tasks/responses.md#rsp-17](tasks/responses.md#rsp-17).
- [ ] RSP-16 [M6] Inline file parts in the three dialects and the /attach and /pdf routes —
  console-attach::parts and ::routes
  - Depends on: RSP-12, RSP-15, RSP-17, API-03, API-07, ENG-12.
  - Donor sources: serve/attach.py:504-610; serve/server.py:6434-6461, 6268-6274, 164-171.
  - Parity tests: serve/test_attach.py ApiParts (6), Route (6); serve/test_pdf.py Route (4);
    16 methods.
  - Risk: low.
  - Done when: all 16 ported tests pass, the attach result and route are documented in the
    UI-to-server contract, and a test per dialect shows expansion happens before dialect
    parsing.
  - Detail: [tasks/responses.md#rsp-16](tasks/responses.md#rsp-16).
- [ ] RSP-18 [M6] External vision encoder adapter, video guards and GPU memory lending —
  console-media::external (uses the fake vision encoder from ENG-14)
  - Depends on: RSP-17, ENG-14, OPS-17, API-15. Seams: OPS-19 (M9).
  - Donor sources: serve/server.py:1731-1958, 1961-2010, 7217-7286.
  - Parity tests: serve/test_tool_videos.py VideoGuards (4); about 14 tests against the fake
    vision encoder.
  - Risk: medium. Lending and pinning are meaningful only on discrete GPUs and are labeled
    unverified on hardware (PLAT-1).
  - Done when: all 18 tests pass on macOS with the fake encoder, vision-memory.json is
    documented as a persisted file in contracts/media.md, and every hardware-only branch
    sits behind a trait and carries the unverified label.
  - Note: Owner decision 2026-11-14: implements approved deviation P-4: the "the image
    could not be read (" prefix is kept, with Rust-side detail text.
  - Note: Owner decision 2026-11-14: implements approved deviation P-7: its private
    temporary files go under the whitespace-free vision base that ENG-14 sets up.
  - Note: Proposal P-5 (picture decoding and resampling in Rust, its format set, and pixel
    values labeled not bit-exact with Pillow) still awaits the owner, who decides it before
    the picture packages of M6 (OPEN-15, R29).
  - Detail: [tasks/responses.md#rsp-18](tasks/responses.md#rsp-18).
- [ ] RSP-19 [M6] DeepSeek (DSI1) picture preprocessor; MiniMax (MMI1) documented, not built
  — console-media::ds4 (the mm3 module is not built: LIC-2)
  - Depends on: RSP-17, ENG-02.
  - Donor sources: serve/ds4_vision.py (186 lines); serve/mm3_vision.py (175 lines, read
    only to document the MMI1 format); serve/server.py:3586-3605, 7255-7270.
  - Parity tests: serve/test_ds4_vision.py Plan (2), Spans (1); Template (2) recorded as not
    exercisable; serve/test_mm3_vision.py (7) resolved as deviation LIC-2 in the ledger;
    serve/test_response_jobs.py ds4 image tests with RSP-07; about 6 new pixel tests.
  - Risk: medium. Pixel values are not bit-exact with Pillow and are labeled so.
  - Done when: the runnable ds4 methods pass with identical geometry, the DSI1 byte layout
    is verified by header parsing, NOTICE.md carries the DeepSeek MIT line, and an engine
    reporting MiniMax vision gets a clear error while the MMI1 format is documented in the
    contract.
  - Note: Owner decision 2026-11-14: implements approved deviation P-4: the "the image
    could not be read (" prefix is kept, with Rust-side detail text.
  - Note: Owner decision 2026-11-14: implements approved deviation P-7: its DSI1 request
    files go under the whitespace-free vision base that ENG-14 sets up.
  - Note: Proposal P-5 (picture decoding and resampling in Rust, its format set, and pixel
    values labeled not bit-exact with Pillow) still awaits the owner, who decides it before
    the picture packages of M6 (OPEN-15, R29).
  - Detail: [tasks/responses.md#rsp-19](tasks/responses.md#rsp-19).

## Phase M7: Model management

**Purpose**: Registry, settings profiles, Turbo, switch and restart, delete and leftovers,
both model APIs, catalog and pull driver, `fetch`, `supervise`, savings and the update
contract.

**Checkpoint**: Milestone report to the owner.

- [ ] OPS-02 [P] [M7] Settings sources, environment naming and precedence —
  console-manage::settings_env
  - Depends on: API-15.
  - Donor sources: tools/maya_names.py; serve/server.py L599-609, L2036-2058, L6737-6755,
    L7115-7176, L7313, L7327; docs/SETTINGS.md L6-7, 94, 165, 261-263.
  - Parity tests: serve/test_server.py ModelManagement precedence part (1);
    serve/test_models.py Settings fast-prompt switch, child_env part (1); new tests per
    precedence row.
  - Risk: low.
  - Done when: every precedence row has a passing test, the name table in
    contracts/naming.md is checked against the Rust table by a test, legacy names are
    refused, and child_env matches the donor for cuda, hip, metal and synthetic fixtures.
  - Detail: [tasks/ops.md#ops-02](tasks/ops.md#ops-02).
- [ ] OPS-03 [P] [M7] Model classification: family, quant label, GGUF and MLX probes,
  context range — console-manage::registry::{classify, gguf_probe, mlx_probe, context}
  - Depends on: API-15.
  - Donor sources: tools/maya_quants.py L19-330; serve/models.py L34-46, L129-188, L715-738;
    tools/gguf_reader.py; maya.py L1755-1765.
  - Parity tests: serve/test_models.py Settings label and context tests (5);
    serve/test_glm_dsa_models.py Page.test_labels (1); with neutral quant names and
    synthetic headers built in the test.
  - Risk: low. Uses no engine-track crate.
  - Done when: all listed tests pass with neutral quant labels (BRAND-1), the GGUF probe
    refuses every truncated prefix, and pulsar-mlx and synthetic configs classify correctly.
  - Note: Owner decision 2026-11-14: implements approved deviation P-15: an MLX checkpoint
    configuration reports `ok: false` with "no engine for this backend in this build".
  - Detail: [tasks/ops.md#ops-03](tasks/ops.md#ops-03).
- [ ] OPS-04 [M7] GLM-DSA product facts and per-request tune knobs —
  console-manage::registry::glm_dsa and console-manage::tune
  - Depends on: OPS-03, ENG-03.
  - Donor sources: serve/glm_dsa_product.py (195 lines); serve/glm_dsa_tune.py (59 lines);
    serve/models.py L382-392.
  - Parity tests: serve/test_glm_dsa_models.py CacheBytes (2); serve/test_glm_dsa_tune.py
    Whitelist (4), RequestBody (1), EngineLine (1).
  - Risk: low.
  - Done when: all 8 tests pass, the two integration ones behind the fake engine, and
    engine_keys matches the donor reading for a table of 30 inputs.
  - Detail: [tasks/ops.md#ops-04](tasks/ops.md#ops-04).
- [ ] OPS-05 [M7] Engine-settings profiles: settings_of, choices, apply, commit, own
  defaults (ablation not ported) — console-manage::profiles::{glm, glm_dsa, deepseek,
  minimax, qwen, pulsar_mlx, synthetic, env_guard}
  - Depends on: API-15, OPS-03, OPS-04.
  - Donor sources: serve/models.py L49-61, L191-659, L804-840; serve/server.py L2967-2991,
    L6368-6390.
  - Parity tests: serve/test_models.py Settings (19 in the pinned class; the planner counted
    17, and test_listing is also listed under OPS-07); serve/test_glm_dsa_models.py Apply
    (2), Page (2), Defaults (2); serve/test_models.py Ablate (4) resolved as deviation POL-1
    in the ledger.
  - Risk: high. The largest table-driven surface, diffed line by line against the donor.
    Extra reviewer.
  - Done when: all ported settings tests pass, a table in the contracts lists every key,
    range and flag per family and is cross-checked by a test, and dry_run never touches the
    filesystem.
  - Note: POL-1: the ablate module and its config keys are not ported (B10).
  - Detail: [tasks/ops.md#ops-05](tasks/ops.md#ops-05).
- [ ] OPS-08 [M7] Delete plan and reference graph (read-only) — console-manage::delete::plan
  - Depends on: API-15, OPS-03.
  - Donor sources: serve/models.py L982-1262.
  - Parity tests: serve/test_models.py Delete (10); serve/test_model_api.py two delete-plan
    tests (2).
  - Risk: high. Wrong answers delete shared data. Extra reviewer.
  - Done when: 12 tests pass on temp trees, a property test over random trees with symlinks
    and hard links finds no planned item outside known roots or referenced elsewhere, and
    the module cannot mutate the filesystem.
  - Detail: [tasks/ops.md#ops-08](tasks/ops.md#ops-08).
- [ ] OPS-10 [M7] Restart controller and model switch (server side) —
  console-manage::restart
  - Depends on: API-15, OPS-05, ENG-09, ENG-12, ENG-14, RSP-09.
  - Donor sources: serve/server.py L3023-3043, L3155-3168, L5635-5668; serve/models.py
    L32-33, L804-821; serve/update.py L19-21.
  - Parity tests: serve/test_models.py Page switch tests (3); serve/test_model_api.py
    Api.test_swap_on_request (1).
  - Risk: medium. Process exit must not lose state.
  - Done when: 4 tests pass, and a test asserts the FIFO is held, the in-flight request
    completes, the note content is correct and the injected exit receives 76; unsupervised
    paths write no note.
  - Detail: [tasks/ops.md#ops-10](tasks/ops.md#ops-10).
- [ ] OPS-06 [M7] Turbo preset and /api/turbo — console-manage::turbo
  - Depends on: OPS-05, OPS-10.
  - Donor sources: serve/models.py L852-979; serve/server.py L2993-3021, L6061-6064,
    L6392-6405.
  - Parity tests: serve/test_turbo.py ResidentSkip (5), TurboMap (6), TurboSnapshot (7),
    TurboServer (2); serve/test_glm_dsa_models.py Turbo (2).
  - Risk: medium. Snapshot and restore exactness across interleaved page edits.
  - Done when: 22 tests pass, and the GET shape without a run config is verified through
    HTTP.
  - Detail: [tasks/ops.md#ops-06](tasks/ops.md#ops-06).
- [ ] OPS-07 [M7] Model listing, machine GPU inventory and GET /api/models and settings
  routes — console-manage::listing and ::gpu_inventory
  - Depends on: OPS-05, OPS-08, OPS-10, API-03.
  - Donor sources: serve/models.py L741-801; serve/server.py L2931-2991, L6065-6068,
    L6368-6390; setup.py gpus() and amd_gpus().
  - Parity tests: serve/test_models.py Settings.test_listing and Page tests (5);
    serve/test_glm_dsa_models.py Page (2); new GPU parser fixture tests.
  - Risk: medium. Key order in describe() is asserted.
  - Done when: 8 listed tests pass through HTTP against the fake engine, the GPU parsers
    pass on fixtures (unverified on hardware), and GET /api/models stays under 50 ms on a
    2,000-file fixture folder after the first call.
  - Detail: [tasks/ops.md#ops-07](tasks/ops.md#ops-07).
- [ ] OPS-11 [M7] Supervisor process and launcher-facing contracts (`pulsar-console
  supervise`) — console-launch::supervise and ::parent_pipe
  - Depends on: API-15, OPS-02, OPS-10, API-16, API-17.
  - Donor sources: maya.py L5235-5413, L97-99; the server's --parent-pipe handling and
    stop-signal semantics.
  - Parity tests: no serve/ test (the launcher side lived outside serve/); new tests with a
    test-only fake server child for exits 76, 75 and 3 with fresh, stale and missing notes.
  - Risk: medium.
  - Done when: the exit-code and note decision table is covered, an end-to-end switch test
    shows 202, exit 76, restart with the new config and the new file running, and
    parent-pipe EOF stops the server within the wrap and quit budget (PLAT-3).
  - Detail: [tasks/ops.md#ops-11](tasks/ops.md#ops-11).
- [ ] OPS-12 [M7] Ollama-shaped model API: pure translation layer —
  console-manage::model_api
  - Depends on: API-15, OPS-03.
  - Donor sources: serve/model_api.py (265 lines).
  - Parity tests: serve/test_model_api.py Pure (4).
  - Risk: low.
  - Done when: the 4 Pure tests pass with every assertion carried over, the duration parser
    is fuzzed without panics, and no new time crate is added.
  - Note: Owner decision 2026-11-14: implements approved deviation P-14: `details.format`
    reports `safetensors` for PulsarMLX MLX checkpoints instead of the donor's constant
    `gguf`.
  - Detail: [tasks/ops.md#ops-12](tasks/ops.md#ops-12).
- [ ] OPS-13 [M7] Model API routes and llama.cpp-style model management routes —
  console-http::routes::model_api
  - Depends on: OPS-10, OPS-12, API-03, API-08, ENG-12.
  - Donor sources: serve/server.py L5465-5754, L5756-5778, L5923-5942, L6167-6173.
  - Parity tests: serve/test_model_api.py Api (9, two delete tests via OPS-09);
    serve/test_server.py ModelManagement (5).
  - Risk: medium.
  - Done when: 14 tests pass as black-box HTTP tests against the fake engine, NDJSON line
    order for tool calls matches the donor, and the SSE frame format is checked byte for
    byte.
  - Detail: [tasks/ops.md#ops-13](tasks/ops.md#ops-13).
- [ ] OPS-14 [M7] Download catalog and manifest schema (the catalog ships empty) —
  console-manage::catalog
  - Depends on: API-15, OPS-03, OPS-07.
  - Donor sources: serve/model_pull.py L20-190, L193-211; maya.py L129-779 (catalog tables,
    read for shape only); tools/ds4/download*.json, tools/mm3/download*.json,
    tools/qwen/download*.json; docs/MODELS.md.
  - Parity tests: serve/test_model_api.py OtherQuantsTest (8) and
    serve/test_glm_dsa_models.py Catalog (2), re-expressed against synthetic manifest
    entries.
  - Risk: low.
  - Done when: 10 re-expressed tests pass, the validator rejects a non-commit revision, a
    missing sha256, a duplicate id or a gitignored path, and the empty production catalog
    yields its documented empty shape without error (B10).
  - Note: Owner decision 2026-11-14: implements approved deviation P-16: the validator
    refuses the catalog revision `main` and any other revision that is not a 40-hex commit.
  - Detail: [tasks/ops.md#ops-14](tasks/ops.md#ops-14).
- [ ] OPS-15 [M7] One-slot pull driver and download routes — console-manage::pull and
  console-http::routes::pull
  - Depends on: OPS-14, API-02, API-03.
  - Donor sources: serve/model_pull.py L214-340; serve/server.py L5508-5633, L3114-3124;
    serve/web/models.js L876-923.
  - Parity tests: serve/test_model_api.py Pull (4), with a test-only fake setup binary.
  - Risk: medium. No environment override of the download command (SEC-7).
  - Done when: 4 tests pass, cancel leaves no live child, the NDJSON sequence matches the
    contract for success, failure and cancel, and detached pulls survive client disconnect.
  - Detail: [tasks/ops.md#ops-15](tasks/ops.md#ops-15).
- [ ] OPS-09 [M7] Delete execution, leftovers and deferred delete of the running model —
  console-manage::delete::{exec, leftovers, deferred}
  - Depends on: OPS-08, OPS-10, OPS-15.
  - Donor sources: serve/models.py L1265-1389; serve/server.py L3045-3153, L6141-6164,
    L6327-6338.
  - Parity tests: serve/test_models.py Leftovers (4), DeletePage (6);
    serve/test_model_api.py delete tests (route part).
  - Risk: high. Two-process deferred deletion. Extra reviewer.
  - Done when: all listed tests pass, stale, foreign-folder and running-config notes delete
    nothing, and a partial failure keeps the config; note files use the .pulsar- prefix
    (B2).
  - Detail: [tasks/ops.md#ops-09](tasks/ops.md#ops-09).
- [ ] OPS-16 [M7] Fetch tool: `pulsar-console fetch`, replacing the launcher's download
  child — console-launch::fetch
  - Depends on: API-15, OPS-14, RSP-10 (reuses the outbound curl facade, R17).
  - Donor sources: maya.py L2813-2843, L2985-3210, L3895-4051; setup.py L504-574 (reference
    only); docs/MODELS.md.
  - Parity tests: no serve/ tests; new tests against a test-only loopback fixture server
    built on `std::net` (R2) supporting Range, stalls, truncation, oversize, wrong hashes
    and bearer tokens.
  - Risk: high. Network and filesystem heavy; token handling is security-relevant. Extra
    reviewer.
  - Done when: resume, stall abort, oversize restart, hash-mismatch deletion, ledger reuse,
    disk-space refusal and gated-token tests pass on macOS against the loopback server,
    progress lines parse with the OPS-15 parser, and an end-to-end pull to fetch to
    new-config test passes with a synthetic catalog (PLAT-3).
  - Note: Owner decision 2026-11-14: implements approved deviation P-15: a fetched MLX
    checkpoint gets a pulsar-mlx config with backend `mlx` that is listed but not startable
    in this increment.
  - Detail: [tasks/ops.md#ops-16](tasks/ops.md#ops-16).
- [ ] OPS-21 [P] [M7] Savings ledger and /api/savings — console-manage::savings
  - Depends on: API-01, API-15, ENG-10.
  - Donor sources: serve/savings.py (244 lines); serve/server.py L4729, L4755-4756, L7346,
    L6069-6072, L6212-6240.
  - Parity tests: serve/test_savings.py Prices (3), Counting (4), LedgerPath (3), Page (3),
    with a fixed clock.
  - Risk: low.
  - Done when: 13 tests pass, the ledger JSON matches Python's indent=1 output through
    console-pyjson, and peak detection is tested at the band edges.
  - Detail: [tasks/ops.md#ops-21](tasks/ops.md#ops-21).
- [ ] OPS-22 [M7] Update contract: opt-in, check-only release notifier —
  console-manage::update
  - Depends on: API-15, OPS-16.
  - Donor sources: serve/update.py (176 lines); serve/server.py L6027-6036, L6073-6077,
    L6256-6259, L6407-6417; serve/web/server.js L340-398.
  - Parity tests: serve/test_update.py Pieces (5) with a fake fetcher; Updating (5)
    re-expressed as always-blocked assertions with no git invocation.
  - Risk: low. SEC-5: route shapes only; the check is opt-in and only notifies.
  - Done when: 10 tests pass, a test proves that with default settings GET /api/update
    performs zero process spawns and zero network calls, and the About page renders the
    disabled shape.
  - Detail: [tasks/ops.md#ops-22](tasks/ops.md#ops-22).
- [ ] OPS-23 [M7] Ops route integration, guard conformance and contract documents —
  console-http::routes::ops and specs/022-console-serving-parity/contracts/ops-*.md
  - Depends on: OPS-06, OPS-07, OPS-09, OPS-10, OPS-13, OPS-15, OPS-17, OPS-21, OPS-22,
    API-03.
  - Donor sources: serve/server.py L5507-5520, L6141-6164, L6327-6338 and the dispatch lines
    of every ops route; serve/web/app.js L116-117.
  - Parity tests: serve/test_savings.py Page.test_reset_only_from_the_page (1);
    serve/test_server.py ModelManagement guard test (1); a new guard matrix over every
    mutating ops route.
  - Risk: medium.
  - Done when: the guard matrix passes for all routes, the start-up suite passes in all
    three configurations, and a test asserts every registered ops route appears in the
    contract documents.
  - Detail: [tasks/ops.md#ops-23](tasks/ops.md#ops-23).

## Phase M8: Dashboard, Phase 1

**Purpose**: Asset import with provenance and neutral identity; embedded serving with
security headers; hardened model-output rendering; page-logic tests; the UI-to-server
contract for Phase 2; the Apple Silicon monitor view; Models, Settings and MCP pages against
the parity routes; browser end-to-end scenarios.

**Checkpoint**: Milestone report to the owner.

- [ ] WEB-01 [P] [M8] Asset import, provenance, licenses and neutral identity — console/web/
  (flat, upstream file names), console/crates/console-web/tests/brand_audit.rs,
  console/crates/xtask (notices assembler); NOTICE.md and docs/upstream/PROJECT_MAYA.md web
  sections through the lead
  - Depends on: GOV-05.
  - Donor sources: serve/web/* (37 files); LICENSE:1-21; README.md:347-381; the donor-name
    sites listed in the planner record (app.js, md.js, server.js, lib.js, chats.js,
    models.js, monitor.js, settings.js, sidebar.js, state.js, turbo.js, ui.js, the CSS
    files, index.html, manifest.webmanifest, sprite.svg).
  - Parity tests: serve/test_dashboard.py Offline.test_the_vendored_code_keeps_its_notices
    (1) and PageLogic.test_about_has_the_support_line_always_and_the_update_card_none (1,
    inverted: no support line, no sponsor link); a new brand audit and a notices-freshness
    test.
  - Risk: medium. About 400 lines of copy edits across 20 files.
  - Done when: console/web holds every served asset with a provenance header on each adapted
    file, the brand audit finds no donor name, sponsor, quant or vendor-logo string outside
    the allowlist, the vendored Preact and htm notices and the Lucide ISC notice are intact,
    the Preact MIT, htm Apache-2.0 and Lucide ISC texts are added to console/LICENSES/ in
    the same change, a check fails unless every file under console/web carries a
    `Provenance` line or is listed as PulsarMLX-original (the header rule is in
    docs/upstream/PROJECT_MAYA.md, Attribution), and the page shows the neutral identity
    with no broken references.
  - Note: BRAND-2: no font files, PNG icons or vendor logos are imported; see
    Reconciliations R14.
  - Detail: [tasks/web.md#web-01](tasks/web.md#web-01).
- [ ] WEB-02 [M8] console-web crate: embedded assets, static routes, caching and security
  headers — console-web: build.rs (asset table), assets, routes, headers (CSP)
  - Depends on: WEB-01, API-03, API-15.
  - Donor sources: serve/server.py:5934-5988, 6012-6018, 5405, 6715-6722, 5811-5819,
    5946-6049; serve/test_server.py:1694-1762; serve/test_dashboard.py:662-687.
  - Parity tests: serve/test_server.py test_page_and_files, test_home_screen_start_url,
    test_only_the_app_files_are_served (3); serve/test_dashboard.py
    Offline.test_nothing_loaded_from_the_network (1); new header, CSP, Host and
    `/fonts/<name>` 404 tests.
  - Risk: low. SEC-2: the CSP must be proven against the real page before it is enforced.
  - Done when: cargo test -p console-web passes the three static-route tests, the offline
    scan, and the header, CSP and `/fonts/<name>` tests; responses keep the donor's
    `Cache-Control: no-cache` and add strong `ETag`s, with 304 and no body for a matching
    `If-None-Match` and `HEAD` answered without a body, each pinned by a test (P-11); and
    pulsar-console serves the page from the embedded table with no files on disk (PLAN-3).
  - Note: No `devdir` module (OPEN-41 unchanged); see Reconciliations R28, amended on
    2026-11-14. The `/fonts/<name>` 404 and the SVG-only manifest are BRAND-2 sub-items
    (R14).
  - Note: Owner decision 2026-11-14: implements approved deviation P-11: strong `ETag`s,
    304 responses and `HEAD` support for dashboard assets.
  - Note: Proposal P-12, a report-only switch for the Content-Security-Policy: not built
    (declined 2026-11-14), because it would weaken SEC-2 while on.
  - Note: The `HEAD` support of P-11 needs a transport extension (lead, 2026-11-15): a way
    for a handler to admit more methods than the four donor methods, and a head-only
    response. API-02's transport answers 501 to any other method before a handler sees it.
  - Detail: [tasks/web.md#web-02](tasks/web.md#web-02).
- [ ] API-12 [M8] Static dashboard routes mounted in console-http — console-http (mount of
  the console-web routes)
  - Depends on: API-03, WEB-01, WEB-02.
  - Donor sources: serve/server.py:5946-5988, 6012-6018; serve/web.
  - Parity tests: serve/test_server.py WebApp test_page_and_files,
    test_home_screen_start_url, test_only_the_app_files_are_served (3, through HTTP, shared
    with WEB-02); new traversal tests.
  - Risk: low. Embedding instead of per-request disk reads is deviation PLAN-3.
  - Done when: all 3 donor methods pass through HTTP, traversal attempts fail, and the
    binary serves the dashboard from a temporary working directory with no disk access to
    console/web.
  - Note: See Reconciliations R15 for the split with WEB-02.
  - Detail: [tasks/api.md#api-12](tasks/api.md#api-12).
- [ ] WEB-03 [M8] CSP compatibility and model-output hardening (page side and the preview
  route) — console/web/{boot.js, guard.js, md.js, ui.js, chat-view.js, settings.js, app.js,
  index.html, sprite.svg, components.css, preview.html}; console-web preview route
  - Depends on: WEB-01, WEB-02.
  - Donor sources: serve/web/index.html:20-34; md.js:75-84, 166-179, 195-216, 233-253;
    ui.js:146-190; chat-view.js:109-127, 205-243; settings.js:298; sprite.svg;
    app.js:107-126.
  - Parity tests: no upstream tests for these sinks; a new Node XSS corpus (about 40 cases)
    and a 60-case golden equality corpus recorded once from the unmodified upstream md.js;
    Rust tests for /preview headers and a main CSP with no unsafe-inline or unsafe-eval.
  - Risk: medium. CSP breakage only shows in a real browser. SEC-2, SEC-3.
  - Done when: index.html has no inline script or style, the sprite has no style attributes,
    every innerHTML sink calls guard.js, the XSS and golden corpora pass, /preview returns
    its documented CSP, and the ?q= link only prefills (SEC-3).
  - Note: Owner decision 2026-11-14: implements approved deviation P-13: `window.maya` is
    replaced by `window.console_debug = {S, chatView}`, exposed only when `#debug` is in
    the address.
  - Note: Proposal P-12, the Content-Security-Policy-Report-Only fallback switch in the
    detail file's risk text: not built (declined 2026-11-14).
  - Detail: [tasks/web.md#web-03](tasks/web.md#web-03).
- [ ] WEB-04 [M8] Node page-logic oracle re-hosted in Rust —
  console/crates/console-web/tests/page_logic.rs and tests/node/*.mjs
  - Depends on: WEB-01, WEB-03, ENG-04. Seams: ENG-13 (M9).
  - Donor sources: serve/test_dashboard.py:690-926; serve/test_turbo.py:258-303;
    serve/test_glm_dsa_models.py:315-420; serve/test_glm_dsa_serve.py:592-700;
    serve/test_glm_dsa_think_budget.py:502-640; serve/test_server.py:1719-1735;
    serve/test_glm_dsa_api.py:534-545.
  - Parity tests: about 26 upstream methods: serve/test_dashboard.py PageLogic (8),
    serve/test_turbo.py node class (5), serve/test_glm_dsa_models.py node class (3),
    serve/test_glm_dsa_serve.py node class (about 5), serve/test_glm_dsa_think_budget.py
    (2), serve/test_server.py literal halves (2), serve/test_glm_dsa_api.py (1).
  - Risk: low. Node is a test tool only, with no packages.
  - Done when: the page-logic tests pass with Node required on macOS, each upstream method
    maps to a named Rust test, no test writes into console/web, and a run without Node
    prints the skip reason.
  - Detail: [tasks/web.md#web-04](tasks/web.md#web-04).
- [ ] WEB-05 [M8] UI-to-server contract documents, JSON Schemas and the Phase 2 roadmap
  entry — specs/022-console-serving-parity/contracts/ui-server/; the Phase 2 entry in
  docs/roadmap/CONSOLE_ROADMAP.md; console-web tests/contract_lint.rs
  - Depends on: WEB-01, RSP-02, API-20.
  - Donor sources: serve/web/server.js, chats.js:400-660, models.js, settings.js,
    sidebar.js:126-266; serve/server.py:5934-6139, 6160-6297.
  - Parity tests: no upstream contract tests; the schemas cite serve/test_dashboard.py
    Dashboard (17), Port (2) and the route tests of the model, savings, update, turbo and
    thinking-budget files.
  - Risk: medium. A large contract partly owned by other packages.
  - Done when: every page-called route appears in routes.md with schema links and the
    coverage scan passes, the schemas validate the recorded fixtures, and the roadmap names
    Phase 2 concretely.
  - Note: See Reconciliations R16: no separate frontend roadmap file.
  - Detail: [tasks/web.md#web-05](tasks/web.md#web-05).
- [ ] WEB-06 [M8] Browser end-to-end harness and chat-core scenarios —
  console/crates/console-web-e2e (manual job only)
  - Depends on: WEB-02, WEB-03, ENG-02, API-06, API-08, API-10, API-11, RSP-08, RSP-11,
    RSP-16.
  - Donor sources: serve/web/app.js, chats.js, chat-view.js, sidebar.js:16-125, 285-374,
    ui.js, md.js; serve/test_stream_jobs.py.
  - Parity tests: no upstream browser tests; about 25 scenarios derived from the JavaScript
    and the server tests that define its routes.
  - Risk: high. Real-browser tests are slow and can be flaky. Extra reviewer.
  - Done when: with the opt-in variable set, the suite passes on macOS Safari and on Chrome
    with zero CSP violations and zero console errors per scenario, the mid-stream-drop
    resume test proves text equality, and one documented command produces screenshots of
    each scenario.
  - Detail: [tasks/web.md#web-06](tasks/web.md#web-06).
- [ ] WEB-07 [M8] Apple Silicon Monitor view and synthetic-backend labeling —
  console/web/monitor-apple.js (new) and the related monitor, settings, sidebar and
  chat-view edits
  - Depends on: WEB-01, WEB-05, OPS-18, API-06.
  - Donor sources: serve/web/monitor.js:28-312, 489-534, 590-628; settings.js:430-477;
    sidebar.js:16-35, 267-283; docs/METAL.md:5-16 (context only).
  - Parity tests: no upstream counterpart (PLAT-2); about 10 Node tests and about 4 browser
    scenarios; upstream tier tests must still pass unchanged.
  - Risk: medium. Real-machine figures are unverified while backends are synthetic.
  - Done when: with an Apple fixture the Monitor shows the unified-memory bar and Apple
    cards with no GPU or NVML text, with a GPU fixture it is unchanged, and the permanent
    synthetic badge appears on chat, monitor, models and settings whenever the backend is
    synthetic.
  - Detail: [tasks/web.md#web-07](tasks/web.md#web-07).
- [ ] WEB-09 [M8] Models page, engine-settings editor, catalog and pull, leftovers, Turbo,
  update, port and context flows — console/web/models.js, turbo.js, server.js, settings.js;
  console-web-e2e scenarios
  - Depends on: WEB-06, OPS-06, OPS-07, OPS-11, OPS-13, OPS-15, OPS-22, ENG-08, ENG-12,
    API-13, API-14.
  - Donor sources: serve/web/models.js:1-1079; turbo.js, turbo-core.js, turbo.css;
    server.js:150-244, 262-309, 345-397; settings.js:70-145, 378-420.
  - Parity tests: server behavior from serve/test_models.py, serve/test_model_api.py,
    serve/test_turbo.py, serve/test_update.py, serve/test_think_budget.py (other owners);
    about 14 end-to-end scenarios here.
  - Risk: high. The most cross-subsystem flows. Extra reviewer.
  - Done when: every listed flow passes as an end-to-end scenario against pulsar-console
    with fake engines and a supervisor, no copy references the donor's launcher, update
    mechanism or releases, and Turbo on then off restores preferences and engine settings
    exactly.
  - Detail: [tasks/web.md#web-09](tasks/web.md#web-09).
- [ ] WEB-10 [M8] Settings dialog, Saved panel, MCP tools page, shared defaults and
  accessibility checks — console/web/settings.js, sidebar.js; console-web-e2e scenarios
  - Depends on: WEB-06, API-13, RSP-11, OPS-21.
  - Donor sources: serve/web/settings.js:1-542; sidebar.js:126-266; server.js:101-124,
    311-342; state.js:154-277; ui.js:49-201.
  - Parity tests: server behavior from serve/test_savings.py, serve/test_mcp.py,
    serve/test_dashboard.py report test and the settings tests (other owners); about 14
    end-to-end scenarios here.
  - Risk: medium. The privacy wording depends on actual retention (PRIV-1).
  - Done when: every settings page and the Saved panel work against pulsar-console with
    fakes, the privacy text matches actual server retention, the notices link serves the
    license notices, and the accessibility assertions pass on Safari and Chrome.
  - Detail: [tasks/web.md#web-10](tasks/web.md#web-10).
- [ ] WEB-11 [M8] Contract conformance gate and Phase 1 close-out —
  console/crates/console-web/tests/contract_conformance.rs; contracts/ui-server/testdata/
  - Depends on: WEB-05, WEB-07, WEB-09, WEB-10. Seams: WEB-08 (M9).
  - Donor sources: WEB-05's contract; the fetch sites in serve/web/*.js (35 routes).
  - Parity tests: aggregates the above; about 40 route checks generated from routes.md.
  - Risk: low.
  - Done when: contract_conformance passes for every documented route, golden fixtures are
    current, the parity matrix maps every upstream web-related test to a counterpart or
    deviation id, and the job runs green in CI.
  - Detail: [tasks/web.md#web-11](tasks/web.md#web-11).
- [ ] CNF-15 [M8] Front-end test harness and UI-to-server contract check —
  console/web/tests/*.test.mjs (node --test, no packages); console-conformance
  tests/web_contract.rs; the console.yml web job
  - Depends on: CNF-01, WEB-01, WEB-03, WEB-04, WEB-05.
  - Donor sources: serve/test_dashboard.py PageLogic (from about line 690);
    serve/test_glm_dsa_models.py:364-380; serve/test_glm_dsa_serve.py:592-660;
    serve/test_glm_dsa_think_budget.py:502-580; serve/test_turbo.py:258-300;
    serve/test_glm_dsa_api.py:536; serve/test_server.py:1671-1880.
  - Parity tests: about 25 Node-run methods across 5 files plus serve/test_server.py WebApp
    (about 8).
  - Risk: medium.
  - Done when: the blocking web job is green, and the endpoint list is complete for every
    endpoint the page calls and is published inside the WEB-05 contract as the Phase 2
    target.
  - Detail: [tasks/conformance.md#cnf-15](tasks/conformance.md#cnf-15).

## Phase M9: Hardware and OS ports

**Purpose**: NVIDIA, AMD and Windows readers, GPU map, mixed-GPU helper, Windows lifecycle
shims and the GPU-era monitor paths, all fixture-verified and labeled unverified on real
hardware. Deliberately last (B11).

**Checkpoint**: Milestone report to the owner.

- [ ] API-18 [P] [M9] Windows lifecycle and transport shims (unverified on hardware) —
  pulsar-console::platform::windows and cfg(windows) branches of console-http::transport
  - Depends on: API-02, API-16, API-17.
  - Donor sources: serve/server.py:6716-6718, 6991, 7007-7020, 7032-7033, 7401-7405, 6442,
    6773-6774.
  - Parity tests: no GPU-free donor tests; cfg(windows) unit tests; checked with a
    Windows-target cargo check.
  - Risk: medium. It cannot run in this program's CI (PLAT-1).
  - Done when: the code compiles for x86_64-pc-windows-msvc in CI, every behavior is listed
    in the ledger as ported and unverified on Windows, and no Windows API is used outside
    this module.
  - Detail: [tasks/api.md#api-18](tasks/api.md#api-18).
- [ ] ENG-13 [P] [M9] GPU map: VRAM parts joined with per-card readings (fixture-driven) —
  console-engine::gpu_map
  - Depends on: ENG-04.
  - Donor sources: serve/gpu_map.py:1-147; serve/server.py:931-934, 1032-1037, 3376-3388.
  - Parity tests: serve/test_dashboard.py GpuMap (17); serve/test_glm_dsa_api.py
    MonitorFigures (4, against a committed key-list fixture).
  - Risk: low. Labeled unverified on real NVIDIA and AMD hardware.
  - Done when: all 17 GpuMap tests and the key-list tests pass, the card-reading input
    struct is documented for console-host, and gpu_map is absent for an engine with no VRAM
    lines.
  - Detail: [tasks/engine.md#eng-13](tasks/engine.md#eng-13).
- [ ] ENG-16 [P] [M9] Mixed GPUs: DeepSeek on two GPUs of different makers —
  console-engine::multigpu::mixed; a fake mixed engine binary in console-fake-engines
  - Depends on: ENG-08, ENG-15, ENG-05.
  - Donor sources: serve/mixed_gpus.py:1-442; serve/server.py:2620-2637, 7239-7245.
  - Parity tests: serve/test_mixed_gpus.py (8, probes mocked); about 8 process-level tests
    with the fake mixed engine.
  - Risk: medium. No meaning on Apple Silicon; only the supervision logic is exercised
    (PLAT-1).
  - Done when: the 8 upstream tests and the fake-process tests pass on macOS, the fallback
    and swap paths are covered, and every function of the donor module maps to a Rust item
    or a recorded omission.
  - Detail: [tasks/engine.md#eng-16](tasks/engine.md#eng-16).
- [ ] CNF-16 [P] [M9] Hardware and OS reader fixture kit — console-conformance::hwfixtures
  (dev-only) and a fake NVML reader binary
  - Depends on: OPS-17.
  - Donor sources: serve/test_telemetry.py (fake NVML child at 19-60, KFD sysfs at 276-300);
    serve/test_mixed_gpus.py; serve/test_glm_link.py; serve/test_dashboard.py NVML and pool
    cases.
  - Parity tests: serve/test_telemetry.py (23), serve/test_mixed_gpus.py (8),
    serve/test_glm_link.py (4), dashboard NVML and pool cases (about 4).
  - Risk: low.
  - Done when: console-host's re-expressed tests use only this kit, run in the Linux job
    (Apple ones in the macOS job), and none touch real hardware.
  - Detail: [tasks/conformance.md#cnf-16](tasks/conformance.md#cnf-16).
- [ ] OPS-19 [M9] NVIDIA reader: NVML in a crash-isolated child process —
  console-host::nvidia (hidden child subcommand)
  - Depends on: OPS-17, CNF-16.
  - Donor sources: serve/telemetry.py L38-442, L823-867, L1119-1120; serve/server.py
    L120-135.
  - Parity tests: serve/test_telemetry.py ReaderProcess (8),
    Sampler.test_sample_through_the_reader and test_gpu_pids (2), through the fake child.
  - Risk: medium. The real FFI is unverifiable on a Mac (PLAT-1).
  - Done when: 10 tests pass on macOS in under 20 s, cargo check succeeds for the Linux and
    Windows targets, and the docs label the reader unverified on NVIDIA hardware.
  - Detail: [tasks/ops.md#ops-19](tasks/ops.md#ops-19).
- [ ] OPS-20 [M9] AMD readers: Linux amdgpu sysfs and Windows DXGI, PDH and D3DKMT —
  console-host::amd::{sysfs, windows}
  - Depends on: OPS-17, OPS-19, CNF-16.
  - Donor sources: serve/telemetry.py L445-820.
  - Parity tests: serve/test_telemetry.py AmdSysfs (3) on fixture trees, AmdWindows (6) with
    fakes.
  - Risk: medium. Only the cross-target check proves the Windows code compiles (PLAT-1).
  - Done when: 9 tests pass on macOS, a Windows cross-target check passes, and the docs
    label both readers fixture-verified and unverified on AMD hardware.
  - Detail: [tasks/ops.md#ops-20](tasks/ops.md#ops-20).
- [ ] WEB-08 [M9] GPU-era Monitor and About paths verified against fixture telemetry —
  console/web/models.js, settings.js; contracts/ui-server/testdata/metrics-*.json;
  console-web tests/node/gpu_paths.mjs; end-to-end scenarios
  - Depends on: WEB-04, WEB-06, OPS-07, OPS-19, OPS-20, ENG-13.
  - Donor sources: serve/web/monitor.js:28-50, 313-486, 489-534, 590-628; settings.js:48,
    421-477; models.js:804, 993.
  - Parity tests: server arithmetic from serve/test_dashboard.py GpuMap, NvmlPids,
    GpuRelease, ContextCost (other owners); about 8 Node tests over five fixtures and about
    5 end-to-end scenarios.
  - Risk: medium. Verified only against fixtures and labeled so.
  - Done when: all five GPU fixtures render the GPU map, cards, banners and About facts
    without errors and with upstream wording except brand words, and the Node and end-to-end
    tests pass.
  - Note: Owner decision 2026-11-14: implements approved deviation P-9: the Models cards
    label `hip` as HIP, `cuda` as CUDA, `metal` as Metal, synthetic as Synthetic, and any
    other value as the raw value.
  - Detail: [tasks/web.md#web-08](tasks/web.md#web-08).

## Phase M10: Close-out

**Purpose**: Reference capture with every mismatch triaged; scenario corpora; a ledger with
no pending rows; SDK client tests; the end-to-end prompt suite; the parity report,
quickstart and status rows.

**Checkpoint**: Milestone report to the owner, and any pull request only with the owner's
go-ahead.

- [ ] PRM-17 [P] [M10] End-to-end prompt and output parity suite on the fake backend, plus
  the PRM test map and contracts — console/crates/pulsar-console/tests/prm_e2e_*.rs; the PRM
  test map; contracts/{prompting.md, parser-events.md, output-pipeline.md,
  thinking-and-loop-guard.md}
  - Depends on: PRM-12, PRM-13, PRM-14, PRM-15, PRM-16, API-08, API-09, API-11, API-13,
    ENG-02, ENG-05, ENG-10, ENG-11.
  - Donor sources: all PRM sources; HTTP-level tests in serve/test_tools.py,
    serve/test_loop_guard.py, serve/test_glm_dsa_serve.py,
    serve/test_glm_dsa_think_budget.py, serve/test_server.py PromptProgressStream,
    serve/test_deepseek_tool_block.py.
  - Parity tests: serve/test_tools.py HttpToolCalls (2); serve/test_loop_guard.py Http (1);
    serve/test_glm_dsa_serve.py HistoryReuse (2), WebAppHistory (4), ContractTestOnTheFake
    (1); serve/test_glm_dsa_think_budget.py WebChat (3), McpLoop (1);
    serve/test_deepseek_tool_block.py HTTP parts.
  - Risk: medium.
  - Done when: the end-to-end suite passes in the blocking jobs on synthetic templates and
    in the manual vendor job, the test map accounts for every cited donor method, the
    contracts are linked from spec.md, and every claim is labeled synthetic-backend only.
  - Detail: [tasks/prompt.md#prm-17](tasks/prompt.md#prm-17).
- [ ] CNF-08 [P] [M10] Donor oracle driver, pinned oracle environment and pin manifest —
  console/conformance/oracle/ (driver, pyproject.toml, uv.lock, pin manifest; Python, our
  MIT code)
  - Depends on: CNF-02.
  - Donor sources: serve/server.py (Service, serve, MockEngine, the line engine,
    ByteTokenizer); serve/frontend.py ChatTemplate; serve/mcp.py McpHub;
    .github/workflows/tests.yml package list.
  - Parity tests: self-check: the driver reproduces three donor tests' observable results in
    the manual job.
  - Risk: medium. The sparse checkout list must be complete.
  - Done when: `uv sync --frozen` works in the manual job on the reference interpreter (the
    planner wrote Python 3.12; lead decision LD38 makes CPython 3.14 the working default
    until the owner decides OPEN-60), the driver serves
    a scenario whose tape matches expectations, and a tampered file makes the pin check fail
    with a named class.
  - Detail: [tasks/conformance.md#cnf-08](tasks/conformance.md#cnf-08).
- [ ] CNF-09 [M10] Differential runner, golden recording and freshness, cross-engine matrix
  and the manual differential job — console-conformance cnf record, diff, matrix and
  freshness; console/conformance/golden; the manual differential job in console.yml
  - Depends on: CNF-04, ENG-05, RSP-08, CNF-07, CNF-08.
  - Donor sources: as CNF-08.
  - Parity tests: defines the differential tiers and the matrix; an initial corpus of about
    20 scenarios from serve/test_server.py, serve/test_glm_dsa_api.py and
    serve/test_responses.py.
  - Risk: high. Concurrent scenarios can be flaky unless gated. Extra reviewer.
  - Done when: a recorded manual run of the differential job is green with a corpus of at
    least 20 scenarios, an injected behavior change produces a parity diff, and a
    hand-edited golden produces a stale-golden failure; the offline replay of committed
    references runs in the blocking Linux job.
  - Note: May add a `cnf check-scenarios` subcommand that loads every scenario file in a
    directory, so the corpus can be checked before the runner exists (lead, 2026-11-15).
  - Note: The scenario format may gain a way to say how and when a step disconnects: a
    half-close mode and a disconnect right after the request, which CNF-03's client
    already supports (CNF-03's request; lead, 2026-11-15).
  - Detail: [tasks/conformance.md#cnf-09](tasks/conformance.md#cnf-09).
- [ ] CNF-10 [M10] Shim tier: donor tests run as-is against Rust artifacts (manual job only)
  — console/conformance/oracle/ shim scripts invoked from the manual differential job
  - Depends on: ENG-05, CNF-08, ENG-08, API-16.
  - Donor sources: serve/test_engine_contract.py; serve/test_stop.py (server_cmd at line 68,
    fake_config at line 44).
  - Parity tests: serve/test_engine_contract.py (10); serve/test_stop.py server-level
    methods (about 9).
  - Risk: medium. POSIX signal semantics.
  - Done when: all selected shim methods pass in the manual job, and the excluded methods
    are listed in the ledger with reasons.
  - Detail: [tasks/conformance.md#cnf-10](tasks/conformance.md#cnf-10).
- [ ] CNF-11 [M10] Vendor-template render conformance (fetched, hash-verified, never
  committed) — console-prompt tests/vendor_renders.rs, reading the vendor directory given to
  the manual job
  - Depends on: CNF-08, PRM-03, PRM-04.
  - Donor sources: serve/chat_golden.json; the donor chat templates and fixtures named in
    the planner record, read as data in the manual job only.
  - Parity tests: serve/test_qwen_template.py (7), serve/test_render_other_models.py (2),
    serve/test_ds41_conformance.py golden cases (about 4), serve/test_minimax_frontend.py
    shared-copy cases (about 4), serve/test_prompt_memo.py per-model cases (6),
    template-level glm_dsa cases (about 8).
  - Risk: high. minijinja and jinja2 differences surface here. Extra reviewer.
  - Done when: all listed cases pass in the manual job, which records hashes and never
    template text, and without the vendor directory they report skipped, never passed.
  - Detail: [tasks/conformance.md#cnf-11](tasks/conformance.md#cnf-11).
- [ ] CNF-12 [M10] Parity ledger checker, baseline and inventories —
  console/parity/ledger.json (populated since GOV-06), contracts/routes.json,
  config-inventory.json, errors.json, deviations.md;
  console/conformance/oracle/extract_inventory.py (AST only); cnf ledger-check
  - Depends on: CNF-09, GOV-06, API-19.
  - Donor sources: all 44 serve/test_*.py (AST listing of 913 methods); serve/server.py
    SERVER_ENV and routes; serve/response_config.py RESPONSE_ENV_KEYS; environment reads
    across serve/*.py.
  - Parity tests: defines the ledger and inventory checks.
  - Risk: medium. Ledger upkeep across every package.
  - Done when: all 913 rows are present, the checker reports every unresolved row, the
    increment gate requires zero pending rows at close-out, and it produces the support
    matrix that plan.md promises under constitution principle VIII (model family, chat
    template, tool-call syntax, checkpoint format and backend, every cell labeled
    synthetic).
  - Detail: [tasks/conformance.md#cnf-12](tasks/conformance.md#cnf-12).
- [ ] CNF-13 [P] [M10] Independent official-SDK client tests (manual job) —
  console/conformance/sdk (pyproject.toml, uv.lock, tests); the manual SDK job
  - Depends on: CNF-07, API-08, API-09, RSP-06.
  - Donor sources: none (independent by design); public OpenAI and Anthropic SDK
    documentation.
  - Parity tests: covers the donor's upstream-skipped SDK methods in serve/test_responses.py
    (2), serve/test_responses_schema.py (1) and serve/test_response_jobs.py (1) as
    independent tests.
  - Risk: low.
  - Done when: the manual SDK job is green, SDK versions are exact and at least two weeks
    old, and each test cites the documented behavior it checks.
  - Detail: [tasks/conformance.md#cnf-13](tasks/conformance.md#cnf-13).
- [ ] CNF-14 [M10] Independent contract, metamorphic, property and security suites —
  console-conformance tests/contracts_*.rs, metamorphic.rs, properties.rs, security.rs
  - Depends on: CNF-03, CNF-07, CNF-12, API-20, OPS-23, RSP-06.
  - Donor sources: none for expectations (independent);
    specs/022-console-serving-parity/contracts as the source of truth; this repository's
    archived serving crate for the security cases (B8).
  - Parity tests: independent (evidence C); generalizes serve/test_tools.py
    test_every_split_agrees_with_whole and the serve/test_prompt_memo.py invariants.
  - Risk: medium. Written by an agent told not to read the donor tests.
  - Done when: all suites are green in the blocking Linux and macOS jobs, and the
    authentication test enumerates routes.json so that adding an unprotected route makes it
    fail, as demonstrated.
  - Note: Adds property-style tests of API-02's hand-written request-head parser (LD34,
    R29; lead, 2026-11-15).
  - Detail: [tasks/conformance.md#cnf-14](tasks/conformance.md#cnf-14).
- [ ] CNF-17 [M10] Drift canary, mutation advisory and conformance documentation — manual
  jobs in .github/workflows/console.yml; docs/console/conformance.md
  - Depends on: CNF-09, CNF-12.
  - Donor sources: this repository's revert 005867d8 (lessons).
  - Parity tests: none.
  - Risk: low.
  - Done when: the drift canary, mutation and oracle-baseline jobs run only through
    workflow_dispatch without affecting the blocking jobs, the documentation is reviewed,
    and the M10 parity report publishes CNF-12's support matrix (constitution principle
    VIII).
  - Detail: [tasks/conformance.md#cnf-17](tasks/conformance.md#cnf-17).
- [ ] CNF-18 [M10] Scenario corpus I: chat dialects, errors and budgets —
  console/conformance/scenarios/chat/ plus goldens
  - Depends on: CNF-09, API-08, API-09, OPS-13.
  - Donor sources: serve/test_server.py chat classes; serve/test_tools.py HTTP classes;
    serve/test_logprobs.py; serve/test_glm_dsa_api.py; serve/test_glm_dsa_tune.py;
    serve/test_model_api.py chat and generate.
  - Parity tests: scenario rows for about 120 ledger entries.
  - Risk: medium.
  - Done when: coverage thresholds are met for the chat routes, and the manual differential
    run is green with no unannotated diffs.
  - Detail: [tasks/conformance.md#cnf-18](tasks/conformance.md#cnf-18).
- [ ] CNF-19 [M10] Scenario corpus II: Responses, MCP tool loop, attachments, PDF and media
  — console/conformance/scenarios/responses, mcp, attach, media
  - Depends on: CNF-09, RSP-06, RSP-07, RSP-08, RSP-11, RSP-16, RSP-17.
  - Donor sources: serve/test_responses.py, serve/test_response_jobs.py,
    serve/test_responses_schema.py, serve/test_responses_tools.py, serve/test_mcp.py,
    serve/test_attach.py and serve/test_pdf.py HTTP classes, serve/test_tool_images.py,
    serve/test_tool_videos.py.
  - Parity tests: scenario rows for about 110 ledger entries.
  - Risk: high. Background-job races must be fully gated. Extra reviewer.
  - Done when: coverage thresholds are met for these routes, and the manual differential run
    is green.
  - Detail: [tasks/conformance.md#cnf-19](tasks/conformance.md#cnf-19).
- [ ] CNF-20 [M10] Scenario corpus III: management, settings, telemetry, savings, Turbo,
  resumable streams, supervision — console/conformance/scenarios/manage, telemetry, savings,
  streams
  - Depends on: CNF-09, OPS-23, API-10, ENG-12, OPS-17.
  - Donor sources: serve/test_models.py HTTP classes, serve/test_model_api.py,
    serve/test_dashboard.py, serve/test_savings.py, serve/test_turbo.py,
    serve/test_stream_jobs.py, serve/test_server.py management classes,
    serve/test_glm_dsa_serve.py subprocess cases.
  - Parity tests: scenario rows for about 100 ledger entries.
  - Risk: medium.
  - Done when: coverage thresholds are met for the remaining routes, all coverage gates
    pass, and the manual differential run is green.
  - Detail: [tasks/conformance.md#cnf-20](tasks/conformance.md#cnf-20).

## Dependencies and execution order

### Dependency graph by milestone

Milestones are sequential checkpoints, but packages are scheduled by their own "Depends on"
lines: a package may start once its prerequisites are done, even if its milestone has other
open tasks. The approved plan makes M9 deliberately last, and M10 closes the increment.

- **M0.** GOV-01 (spec and checklist) comes first. GOV-02 (plan, research, data model,
  quickstart) follows it, and GOV-03 (this list and the analysis) follows both. GOV-04 (ADR,
  roadmap, notes) and GOV-05 (donor record, NOTICE, licenses) depend only on the approved
  plan. GOV-06 (workspace skeleton, tools, `console.yml`, ledger skeleton, contracts) follows
  GOV-02. M0 ends at owner checkpoint 1: spec and checklist, ADR 0008, the roadmap entries,
  `NOTICE.md` and the donor record.
- **M1.** Three chains start together. The wire chain: API-01, then API-02, API-04 and API-15
  in parallel, then API-03 after API-02. The engine chain: ENG-01, then ENG-02 and ENG-09, then
  ENG-10. The conformance chain (after GOV-06): CNF-01, CNF-02, then CNF-03 and CNF-07, then
  CNF-04 after CNF-03. PRM-04 needs only API-01. API-19 joins the chains (API-02, ENG-02,
  PRM-04). API-07 needs API-02, API-03, API-04 and ENG-10; API-08 follows API-07. M1 ends at
  owner checkpoint 2: a streamed answer over `curl` from the scripted engine, and the decision
  on the first push.
- **M2.** PRM-02 first (it extends the API-19 test kit). Then PRM-03, PRM-07 and PRM-09 in
  parallel; PRM-05 after PRM-03 and PRM-07; PRM-06 after PRM-05; PRM-08 after PRM-05, PRM-06
  and PRM-07; PRM-10 after PRM-07 and PRM-09; PRM-11 after PRM-08; PRM-12 after PRM-09,
  PRM-10 and PRM-11; then PRM-13, PRM-15 and PRM-16 after PRM-12, and PRM-14 after PRM-13.
  API-09 closes the milestone after PRM-06 and PRM-16.
- **M3.** ENG-03, ENG-04, ENG-05, ENG-11, ENG-15 and ENG-19 start together (they need only M1).
  ENG-06 needs ENG-03, ENG-04 and ENG-05; ENG-07 and ENG-08 follow ENG-06; ENG-12 follows
  ENG-08. ENG-17 needs ENG-03 and PRM-08. ENG-18 runs last, after ENG-05, ENG-06, ENG-07 and
  ENG-19.
- **M4.** API-05, API-10, API-11 and API-16 start together. OPS-17 follows API-05, and OPS-18
  follows OPS-17. API-06 needs API-05 and OPS-17 (and ENG-12 from M3); API-13 needs OPS-17;
  API-14 needs OPS-18. API-17, the binary, needs every other M4 route package; API-20 closes
  the route inventory after the route packages.
- **M5.** RSP-01 and RSP-02 start together. RSP-03 follows RSP-02, RSP-04 follows RSP-03, and
  RSP-05 follows RSP-01. RSP-06 needs RSP-01 to RSP-04; RSP-07 needs RSP-05 and RSP-06.
- **M6.** Three chains. MCP: RSP-08, RSP-09, then RSP-10 (which writes the outbound curl
  facade) and RSP-11. Attachments: RSP-12, RSP-13, RSP-14, RSP-15, then RSP-16 (which also
  needs RSP-17). Media: ENG-14, RSP-17 (which also needs RSP-10), then RSP-18 and RSP-19.
- **M7.** OPS-02, OPS-03 and OPS-21 start together. OPS-04, OPS-08 and OPS-12 follow OPS-03;
  OPS-05 follows OPS-04; OPS-10 follows OPS-05; OPS-06 needs OPS-05 and OPS-10; OPS-07 needs
  OPS-05, OPS-08 and OPS-10; OPS-11 needs OPS-02 and OPS-10; OPS-13 needs OPS-10 and OPS-12;
  OPS-14 needs OPS-07; OPS-15 and OPS-16 follow OPS-14, and OPS-16 also needs RSP-10 (M6);
  OPS-09 needs OPS-08, OPS-10 and OPS-15;
  OPS-22 follows OPS-16; OPS-23 integrates everything last.
- **M8.** WEB-01 first. WEB-02 and WEB-05 follow it; WEB-03 and API-12 follow WEB-02; WEB-04
  follows WEB-03; WEB-06 needs WEB-02 and WEB-03; WEB-07 follows WEB-05; WEB-09 and WEB-10
  follow WEB-06; CNF-15 needs WEB-04 and WEB-05; WEB-11 closes Phase 1 after WEB-05, WEB-07,
  WEB-09 and WEB-10 (WEB-08 extends the gate in M9).
- **M9.** CNF-16, ENG-13, ENG-16 and API-18 start together. OPS-19 needs CNF-16; OPS-20 needs
  OPS-19 and CNF-16; WEB-08 needs OPS-19, OPS-20 and ENG-13.
- **M10.** CNF-08, CNF-13 and PRM-17 start together. CNF-09, CNF-10 and CNF-11 follow CNF-08;
  CNF-12, CNF-18, CNF-19 and CNF-20 follow CNF-09; CNF-14 follows CNF-12; CNF-17 follows
  CNF-09 and CNF-12. The increment closes with zero pending ledger rows, every mismatch from
  the reference capture triaged, the parity report and the status rows.

### Parallel lanes after M1

After M1 the lanes M2 to M8 run largely in parallel, one package per coding session, four to
six lanes at a time. They are not fully independent: the hard dependencies below decide when
each package can start. The lanes are:

| Lane | Milestone | Needs from other lanes before its later packages |
| --- | --- | --- |
| Prompt and output | M2 | M1 only |
| Engine supervision | M3 | M1; ENG-17 needs PRM-08 (M2) |
| Monitoring and admin | M4 | M1; API-11, API-13 and API-17 need M2 and M3 packages |
| Responses API | M5 | M1; RSP-03, RSP-04 and RSP-06 need M2 parsers; RSP-07 needs ENG-12 (M3) |
| MCP, attachments, media | M6 | RSP-09 needs API-17 (M4); ENG-14 needs M3; RSP-17 needs M2, M3 and RSP-10 |
| Model management | M7 | M1, M3 and M4; OPS-10 needs ENG-14 and RSP-09 (M6); OPS-16 needs RSP-10 (M6) |
| Dashboard Phase 1 | M8 | WEB-01 needs only GOV-05; WEB-05 needs RSP-02 (M5) and API-20 (M4); WEB-06 onward need M4 to M7 routes |

These packages from M2 to M8 depend only on M0 and M1 work, so they can start as soon as M1
is done:

- M2: PRM-02.
- M3: ENG-03, ENG-04, ENG-05, ENG-11, ENG-15, ENG-19.
- M4: API-05, API-10, API-16.
- M5: RSP-01, RSP-02.
- M6: RSP-08, RSP-12.
- M7: OPS-02, OPS-03, OPS-21.
- M8: WEB-01.

M9 starts after M8, as B11 and the approved plan require; within M9, CNF-16, ENG-13, ENG-16
and API-18 are independent. M10 needs the work it measures and runs last.

### Highest-risk packages

The approved plan names the highest-risk functions for an extra independent reviewer, on
top of the reviewers every package gets (contract, security, parity with the cited donor
lines, non-interference). The package ids below map those functions to the work packages:

| Milestone | Package | What the plan calls it |
| --- | --- | --- |
| M1 | API-07 | Request lifecycle driver |
| M1 | ENG-10 | Turn driver |
| M2 | PRM-03 | Jinja runtime |
| M2 | PRM-12 | Output pipeline |
| M2 | PRM-15 | Cross-turn loop guard |
| M3 | ENG-06 | Line-protocol client |
| M3 | ENG-11 | Server-side continuations |
| M5 | RSP-05 | Background jobs |
| M7 | OPS-05 | Settings profiles |
| M7 | OPS-08 | Delete plan |
| M7 | OPS-16 | Fetch tool |
| M8 | WEB-06 | Browser end-to-end |
| M8 | WEB-09 | Models page |
| M10 | CNF-09 | Differential runner |

Six further packages that the planning rated high risk, API-17, CNF-04, CNF-11, CNF-19,
OPS-09 and RSP-07, are added by a lead decision of 2026-11-14 and get an extra reviewer as
well:

| Milestone | Package | Planner's reason |
| --- | --- | --- |
| M1 | CNF-04 | An over-lenient normalizer creates parity that is not real |
| M4 | API-17 | The integration point for every subsystem |
| M5 | RSP-07 | Cross-cutting with the engine FIFO and idle unload |
| M7 | OPS-09 | Two-process deferred deletion |
| M10 | CNF-11 | minijinja and jinja2 differences surface here |
| M10 | CNF-19 | Background-job races must be fully gated |

### Per-task gate before commit

Every task passes this gate before its commit, in the nested workspace, run from `console/`
on the pinned toolchain 1.97.1. For documentation-only tasks (the GOV tasks), the Rust steps
apply to the workspace as it stands.

1. **Toolchain and format:** `bash tools/check-toolchain.sh` passes (it fails unless
   `rustc -V` reports exactly the version pinned in `rust-toolchain.toml`), then
   `cargo fmt --check` passes.
2. **Clippy-clean:** `cargo clippy --locked --all-targets -- -D warnings` passes.
3. **Tests green:** `cargo test --locked` passes, and `node --test` passes for web
   logic tests the task touches. Tests that need the manual job report skipped, never passed.
4. **Ledger rows resolved:** every ledger row the task owns resolves to one of the
   dispositions of R10: a Rust test (`rust-test`), a recorded scenario (`scenario`), a web
   logic test (`web-test`), a shim run (`shim`) or vendor-template render
   (`vendor-render`) whose committed record from the manual job exists, an approved
   deviation (`deviation`), or `not-applicable` with a reason from the closed list; no row
   it touches is left `pending` or dangling.
5. **Boundary and hygiene checks pass:** `console/tools/check-boundary.sh` (only allowlisted
   paths changed; root `Cargo.toml`, `Cargo.lock` and `.github/workflows/macos.yml` equal
   the merge base with `main`, not a moving `main` tip), the ignored-file check (nothing
   under `console/` or the feature directory dropped by `.gitignore`), and the
   staged-content scan (no credential-shaped string, no binary file, no oversize file, no
   absolute home-directory path).
6. **Commit message:** conventional (for example `feat(console): ...`), one coherent change,
   citing the task id, with no AI or tool attribution and no co-author trailer.
7. **Claims:** nothing in code comments, documents or the commit message describes the work as
   more than qualified on synthetic backends, and hardware-specific code says it is unverified
   on real hardware. A task that adds, moves or removes an enforcement point of the
   synthetic-only rule updates
   [docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md](../../docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md)
   in the same change (owner request of 2026-11-14, R29).

## Constitution compliance

The principle-by-principle Constitution Check and the six recorded exceptions (E1 to E6)
are in [plan.md](plan.md#constitution-check). The per-task gate enforces them for every
task as follows:

- Steps 1 to 3 (toolchain, format, Clippy, tests): principle X (incremental, test-backed
  commits) and principle I (each behavior is accepted against its oracle).
- Step 4 (ledger rows resolved): principles I and III (parity is shown row by row, and a
  pending row is never claimed).
- Step 5 (boundary and hygiene checks): principle II (nothing outside the allowlist, and
  the hash-bound root files unchanged) and principle XI (no secrets, model weights or
  binary files).
- Step 6 (commit message): principle X (one coherent change per commit).
- Step 7 (claims): principle III (verified claims only) and principle VII (no performance
  claim).

Principles IV, V, VI, VIII, IX and XII are checked at review against each package's
definition of done and its contracts, and at every milestone report, where the
Constitution Check is re-run.

## Implementation strategy

M1 is the minimum useful slice: it ends with a streamed chat completion for plain content
over `curl` from the scripted engine, at owner checkpoint 2. Every later milestone ends
reviewable, with its tests green and its ledger rows updated, so the work can stop cleanly
after any milestone and be re-scoped at the milestone report, as the approved plan
intends. After M1, delivery is incremental across the lanes in
[Parallel lanes after M1](#parallel-lanes-after-m1), scheduled by each package's
"Depends on" line; M9 comes last and M10 closes the increment.

## Counts

| Milestone | Name | Tasks |
| --- | --- | ---: |
| M0 | Governance and skeleton | 6 |
| M1 | Core pipeline | 18 |
| M2 | Prompt and output | 15 |
| M3 | Engine supervision | 12 |
| M4 | Monitoring and admin | 11 |
| M5 | Responses API | 7 |
| M6 | MCP, attachments, media | 13 |
| M7 | Model management | 18 |
| M8 | Dashboard, Phase 1 | 12 |
| M9 | Hardware and OS ports | 7 |
| M10 | Close-out | 12 |
| **Total** | | **131** |

Of the 131 tasks, 6 are governance tasks and 125 are work packages: 132 planner records (API
20, ENG 19, PRM 17, RSP 19, OPS 23, WEB 14, CNF 20) minus the 3 Phase 2 roadmap items and
the 4 merged ids. Each id appears exactly once as a task line; the merged ids PRM-01,
OPS-01, CNF-05 and CNF-06 and the roadmap items WEB-P2-01 to WEB-P2-03 appear only in prose.
