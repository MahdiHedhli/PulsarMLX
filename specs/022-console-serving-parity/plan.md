# Implementation Plan: PulsarMLX Console Serving Parity

**Branch**: `feat/022-console-serving-parity` | **Date**: 2026-11-14 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/022-console-serving-parity/spec.md`

**Status**: Planned. Milestone M0 (governance and skeleton) was reviewed by the owner at
checkpoint 1 on 2026-11-14, and M1 may start. No serving code exists yet, nothing in this
plan has been built or measured, and the strongest claim any part of this increment can
earn when built is "qualified on synthetic backends".

**Authority**: The decisions in this plan come from the plan the owner approved on
2026-11-14 and are recorded in
[ADR 0008](../../docs/architecture/decisions/0008-console-serving-ahead-of-stage-f.md),
which the owner accepted on 2026-11-14. The owner's decisions at checkpoint 1 on
2026-11-14 settle open items and proposals that this plan marks as decided where they
appear. A few come from lead decisions taken after approval, within the approved plan;
each is marked as a lead decision where it appears and none is presented as the owner's.
Where a question is not decided there, this plan and [research.md](research.md) record it
as an open item, never as a decision. Every open item of this feature is listed, with a
stable `OPEN-` id and who decides it, in the register in
[checklists/analysis.md](checklists/analysis.md).
The work-package breakdowns, architect proposals and reviews prepared before approval
("planner records" below) are not in the repository; what this feature takes from them is
restated in [tasks.md](tasks.md) and `tasks/`, and nothing in them is a decision unless
the approved plan or a lead decision recorded in this feature's documents adopts it.

## Summary

PulsarMLX has no serving layer that runs on Apple Silicon. The inherited `crates/serve`
builds its server only for Linux with CUDA, and the Rust synthetic serving crate of
September 2026 was merged and reverted (commit `005867d8`) and survives only at tag
`archive/2026-09-21/feat/openai-serving`.

This feature rebuilds the serving layer and dashboard of project-maya
(`github.com/mw00/project-maya`, MIT, pinned at commit `7e68a30f`, release v1.1.63) in
Rust, inside a standalone nested Cargo workspace `console/`, as the product **PulsarMLX
Console** with the binary `pulsar-console`. The target is full behavioral parity with
project-maya's `serve/` at the pinned commit: driven by equivalent fake engines, the Rust
server shows the same externally observable behavior for every route, stream format,
error, configuration key, environment variable and persisted file, except where an
approved deviation (SEC-1 to SEC-7, PRIV-1, BRAND-1, BRAND-2, LIC-1, LIC-2, POL-1, PLAT-1
to PLAT-3, FIX-1, the proposals the owner approved on 2026-11-14 under their `P-` ids, and
any later deviation the owner approves) says otherwise.

The backend is synthetic only. Engines in this increment are a scripted in-process engine,
a line-protocol child-process client driven by PulsarMLX-authored Rust fake engine
binaries, and a test adapter shaped like the engine track's single-owner coordinator. A
two-level backend seam (token level and event level) is designed so that the PulsarMLX
native engine can attach later, in a separately approved Phase 3.

Parity is measured by a ledger with one row per project-maya test method (913 methods in
44 test files at the pin), fed by four sources of evidence: a reference corpus captured
from project-maya's own server in a manual CI job, re-expressed donor tests, independent
tests written from PulsarMLX contracts, and official client SDK tests. The front end is
delivered in two phases: Phase 1 adapts project-maya's no-build JavaScript dashboard and
serves it from the Rust server; Phase 2, later, rewrites it in Rust compiled to
WebAssembly. The work is ordered in eleven milestones, M0 to M10, each of which ends
reviewable so the program can stop cleanly after any of them.

## Technical Context

**Language/Version**: Rust 1.97.1, pinned exactly in `console/rust-toolchain.toml` with
the `rustfmt` and `clippy` components. Every CI job runs from `console/` so the pin is
honored, installs that exact toolchain and asserts `rustc -V` before any other step.
Observed on the owner's build host on 2026-11-14: `rustc -V` reports `1.97.1` from a
package-manager install without `rustup`, so the pin file is not enforced locally by a
toolchain manager. By lead decision, local gates run `console/tools/check-toolchain.sh`,
which fails unless `rustc -V` reports exactly the pinned version. Phase 1 web
assets are JavaScript ES modules and CSS adapted from the donor; Node.js is used only as a
test tool, with no packages. Python is used only in manual GitHub Actions jobs (reference
capture, the live differential, the shim run of the two donor test files that run as-is,
vendor-template checks and the SDK client tests), in environments pinned by hash under
`console/`, never in a blocking job and never on the owner's machines.

**Primary Dependencies**: `tokio` and `httparse` for a hand-written HTTP/1.0 transport
that closes the connection after each response (no `hyper`, no `axum`); `serde` and
`serde_json` with `preserve_order` and `arbitrary_precision` across the workspace, with
one Python-compatible writer in `console-pyjson` for every wire body and persisted file;
`minijinja` and `minijinja-contrib` with a Python-compatible `tojson`; small format crates
for the in-house readers (`miniz_oxide`, `roxmltree`, `html-escape`) and `image` for
picture decoding. The MCP client, the restricted JSON Schema validator, the ZIP and PDF
readers and the tokenizer are written in-house; there is no `rmcp`, no `jsonschema`, and
no TLS crate. Outbound network goes through one facade over the system `curl`. Every
dependency is pinned with `=` when first added and recorded with its license in
[research.md](research.md). No crate depends by path on anything outside `console/`.

**Storage**: No database. Runtime state is in memory (response store, background jobs,
resumable answers, monitor history) or in files beside the run config in a configuration
directory outside the repository: the run config document `pulsar-<NAME>.json`, note files
`.pulsar-*`, the savings ledger, and, only when enabled (PRIV-1), resumable answers on
disk. Repository-tracked data is text only: the parity ledger, the deviation register,
conformance scenarios and recorded references, synthetic templates and generated-in-code
test data. Entities and file locations are in [data-model.md](data-model.md).

**Testing**: `cargo test --locked` from `console/` on Linux and on macOS arm64 (unit tests,
re-expressed donor tests, black-box raw-HTTP tests, fake-engine integration tests, replay
of committed references, independent contract, property and security tests); `node --test`
for the web page logic with no packages; manual GitHub Actions jobs for reference capture,
the live differential, the shim run of `serve/test_engine_contract.py` and
`serve/test_stop.py` against the Rust artifacts, vendor-template checks, SDK client tests,
the toolchain drift canary and the browser end-to-end suite. By lead decision, the shim
and the vendor-template renders run only in the manual reference job, and blocking CI
checks their committed records. Fake engines are deterministic Rust programs; timing is
controlled with gates and an injectable clock, never with sleeps.

**Target Platform**: macOS on Apple Silicon (arm64) is the primary target and has a
blocking CI job. Linux (ubuntu-24.04) runs the full Rust suite in CI. Windows is
type-checked in CI only. Hardware- and OS-specific readers for other platforms (PLAT-1)
are built last, behind traits, verified only against fixtures, and labeled unverified on
real hardware.

**Project Type**: A Rust server binary with an embedded browser dashboard, a library
workspace behind it, and test-only crates (fake engines, test kit, conformance harness,
browser end-to-end harness, `xtask`).

**Performance Goals**: None are admitted. This increment serves no real model and makes
no throughput or latency claim. Tests assert ordering and protocol behavior, never speed.
Monitor figures produced against synthetic engines are telemetry plumbing, not benchmarks.

**Constraints**: Synthetic backends only, with a permanent "Synthetic engine: no real
model" badge in the dashboard and the same fact on `/health`; no change to any file the
engine track edits or hash-binds; no binary file committed; vendor chat templates never
committed; no project-maya code executed locally; security posture SEC-1 to SEC-7 on
every route from the first HTTP package; builds on the owner's build host run at low
priority with a target directory outside the repository and pause for engine
qualification runs.

**Scale/Scope**: 125 work packages in M1 to M10 plus six governance packages (GOV-01 to
GOV-06) in M0. The planning estimates are about 80,000 lines of Rust and 76,000 lines of
tests and scenarios plus about 7,000 lines of adapted JavaScript and CSS; these estimates
are soft and may be off by a wide margin. The donor's `serve/` is about 19,800 lines of
Python with 44 test files and 913 test methods; the ledger has one row per method.

## Constitution Check

*GATE: Evaluated for the M0 design on 2026-11-14. Re-checked at the end of every
milestone and recorded in that milestone's report. Every result below is a design
commitment, not observed evidence; evidence is attached as packages land.*

| Principle | How this feature complies | Gate |
| --- | --- | --- |
| I. Correctness before optimization | Every behavior has an oracle before it is accepted: the recorded reference corpus from the pinned donor, re-expressed donor tests, and independent contract tests. Comparisons are exact for everything that does not depend on time (bytes on the wire, engine tapes, prompt token ids, persisted files); only fields listed as volatile are compared by class and range. No performance work is in scope. | PASS (design) |
| II. Preserve upstream Linux and CUDA behavior | Nothing under `crates/` is touched, including the inherited `crates/serve` and its web UI, which stay Linux-only and unchanged. The console is additive in its own workspace and its own workflow file; `console/tools/check-boundary.sh` fails on any change outside the allowlist and on any difference in the blobs of the root `Cargo.toml`, `Cargo.lock` and `.github/workflows/macos.yml` against those at the merge base with `main`. No cross-platform-safe claim is made about inherited code. | PASS (design) |
| III. Verified claims only | Every document and the product itself say "synthetic backends only"; the dashboard badge and `/health` report it; model names used by the synthetic engines contain `synthetic`, and the scripted engine's default model name is `pulsar-console-synthetic` (decided by the owner on 2026-11-14, OPEN-03). The server refuses to start an engine that does not report synthetic provenance, through one guard in `console-core` with no bypass in this increment (decided by the owner on 2026-11-14, OPEN-29); what must be done before such an engine may be allowed is in [ALLOWING_NON_SYNTHETIC_ENGINES.md](../../docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md). [quickstart.md](quickstart.md) marks each command with the package that makes it available and records results only after they are observed. Hardware readers built in M9 are labeled unverified on real hardware wherever they are mentioned. Upstream-skipped donor tests are marked as such in the ledger so nobody assumes they were ever green. | PASS (design) |
| IV. Apple Silicon is a first-class backend | macOS arm64 is the primary target with a blocking CI job that runs the full suite, the Apple Silicon telemetry reader and the process-lifecycle tests. PLAT-2 adds an Apple Silicon reader (unified memory, pressure, swap, disk; GPU activity as an experimental field) and a matching monitor view, instead of modeling the Mac as a GPU-less CUDA host. Unified memory is a native input to the telemetry model. | PASS (design) |
| V. Portable interfaces without lowest-common-denominator design | The backend seam expresses token-level and event-level semantics with explicit capability flags (stop, pause, multi-conversation capacity, logit bias, log probabilities, vision kind), not engine internals. Unsupported operations fail clearly: a missing chat template is a start-up error, the POL-1 capability is refused unless an engine advertises it, a MiniMax-vision engine gets a clear error under LIC-2, and a backend without an engine in this build is listed as not startable (deviation P-15, approved by the owner on 2026-11-14). | PASS (design) |
| VI. MLX reference before custom Metal | Not engaged: this increment contains no MLX execution, no Metal code and no GPU compute. The console never launches an engine that does (binding decision B10 in [tasks.md](tasks.md#binding-cross-cutting-decisions)). | N/A |
| VII. Reproducible benchmarks | No performance result is published. No project-maya benchmark is presented as PulsarMLX evidence. Monitor and savings figures computed against synthetic engines are labeled as such and are not benchmarks. | PASS (design) |
| VIII. Explicit model and quantization compatibility | No real model is served. The model catalog ships empty (B10); synthetic catalog entries exist only in test data. Model classification and checkpoint probes read bounded headers only and return bounded errors on unknown or truncated input. Synthetic coverage is the only coverage claimed. The support matrix this principle requires (model family, chat template, tool-call syntax, checkpoint format and backend, every cell labeled synthetic) is planned as part of the M10 parity report: CNF-12 produces it and CNF-17 publishes it in that report ([tasks.md](tasks.md)). | PASS (design) |
| IX. Clean licensing and upstream attribution | project-maya is qualified as a donor by its ADR 0004 record, `docs/upstream/PROJECT_MAYA.md` with `PROJECT_MAYA_SYNC.md`, with both copyright lines, the pinned commit and a per-module classification, and with benefit recorded as a pre-adoption estimate and measured at close-out (exception E6, accepted by the owner on 2026-11-14). Adapted and translated files carry a provenance header in the form that record states. M0 ships the project-maya MIT text in `console/LICENSES/`; by lead decision, the Preact MIT, htm Apache-2.0 and Lucide ISC texts arrive with WEB-01 and DeepSeek's notice with PRM-07, each in the change that imports the component, and the texts are served from the About page; `NOTICE.md` gains a matching section. Vendor chat templates are never committed (LIC-1); the MiniMax picture preprocessor is not built (LIC-2); vendor logos and font files are not carried (BRAND-2). project-maya is never product identity. | PASS (design) |
| X. Incremental, test-backed commits | One work package per commit series, each with failing-then-passing tests and its ledger rows resolved. The gate before each commit is: formatted, Clippy-clean and tests green in the nested workspace; boundary and hygiene checks pass; a conventional message (`feat(console): ...`) that explains one change. | PASS (design) |
| XI. No secrets or model weights | `console/tools/check-hygiene.sh` ports the repository's staged-content rules (credentials, binary files, sizes, home-directory paths, UUIDs, host and user JSON values, AI attribution) and runs before every commit and in the blocking preflight job. Test data is generated in code; example tokens are short and obviously fake; no path matches a `.gitignore` trap; no model file is read or written. | PASS (design) |
| XII. Documentation is part of the implementation | Each package updates its contract document, its ledger rows, the deviation register when relevant and [quickstart.md](quickstart.md) in the same change as the behavior. The README status row, the strategy pointer and the `CONTRIBUTING.md` console commands land in M0 so no committed document contradicts the decision. | PASS (design) |

Six departures from the constitution's workflow or from standing project direction are
needed. Each is recorded below as the constitution's Governance section requires.

### Constitution Exceptions

| Exception | Scope | Evidence | Risk | Expiration or removal condition | Approval |
| --- | --- | --- | --- | --- | --- |
| E1. The nested `console/` workspace is invisible to `cargo check --workspace` and `cargo test --workspace` at the repository root, which the constitution's workflow step 4 names as handoff gates. | Every crate under `console/`. Root commands keep their meaning for the root workspace. | The root `Cargo.toml` is hash-bound into the engine track's frozen evidence and cannot be edited, so `console/` cannot become a member. The console equivalents (`cargo fmt --check`, `cargo clippy --locked --all-targets -- -D warnings`, `cargo test --locked`, all run from `console/`; locally after `console/tools/check-toolchain.sh`, while CI asserts the version itself) are blocking in `console.yml`: fmt, Clippy and tests on Linux, and tests on macOS arm64. They are documented in `CONTRIBUTING.md` and [quickstart.md](quickstart.md). | A contributor runs only the root commands and believes the console was checked; the console drifts from the root toolchain. | Removed if the owner later joins `console/` to the root workspace, which needs an engine-track agreement because the root manifest and lock are hash-bound; otherwise kept for the life of the nested workspace and re-confirmed at each milestone report. | Owner, in the approved plan of 2026-11-14 (section 7, "nested workspace outside `--workspace`"). The owner's reply at checkpoint 1 on 2026-11-14 accepted the decisions put to it; this exception's text was not among them and is put to the owner at checkpoint 2. |
| E2. Serving work proceeds ahead of strategy Stage F, which allows OpenAI-compatible serving only after the local runtime is stable, and ahead of OPT-08. | The serving layer, dashboard and conformance harness on synthetic backends only. It does not authorize serving a real model. | [ADR 0008](../../docs/architecture/decisions/0008-console-serving-ahead-of-stage-f.md) records the owner's decision; the strategy gains a dated pointer under Stage F in M0. | Readers take the console as evidence of real-model serving; the engine sequence is disturbed. | Removed when Stage F is reached by the engine track, or superseded by the separately approved Phase 3 decision for real-engine attachment. Real-model serving stays gated exactly as Stage F and OPT-08 describe. | Owner, in the approved plan of 2026-11-14 and ADR 0008. The owner's reply at checkpoint 1 on 2026-11-14 accepted the decisions put to it; this exception's text was not among them and is put to the owner at checkpoint 2. |
| E3. JavaScript and CSS assets live inside the Rust-owned runtime during front-end Phase 1, beside ADR 0001's rule that Rust owns the shipping runtime. | The adapted dashboard under `console/web/`, embedded in the binary from a fixed compile-time table and run only in the browser. No JavaScript runs in the server and no Node or Python process is needed to serve. | Approved plan section 2 (two-phase front end); ADR 0008 decision 4; web logic tests under Node in the blocking `console-web` job; provenance headers and license texts for every adapted file. | The adapted JavaScript becomes permanent; security of model-output rendering (mitigated by SEC-2). | Expires at the Phase 2 cutover, when the Rust/WebAssembly front end replaces Phase 1 and the Phase 1 assets are retired with the owner's approval. | Owner, in the approved plan of 2026-11-14 (section 7, "JavaScript assets in the Rust-owned runtime"). The owner's reply at checkpoint 1 on 2026-11-14 accepted the decisions put to it; this exception's text was not among them and is put to the owner at checkpoint 2. |
| E4. The Spec Kit artifacts of this feature are authored by hand from `.specify/templates/` instead of through `$speckit-specify`, `$speckit-plan` and `$speckit-tasks`. | All files under `specs/022-console-serving-parity/`. | The generator script would choose number 021, which is taken by `specs/021-qwen38-io-prefetch-spike` on an unmerged research branch, and it rewrites the tracked `.specify/feature.json`, which this feature must not touch. Structure follows the templates and the precedents in `specs/001-apple-silicon-mlx/` and `specs/016-glm52-full-execution/`. The gated order (spec and checklist, then plan, then tasks and analysis) is still followed. | Hand-authored artifacts drift from the template structure or skip a gate. | Kept for the life of this feature; it expires when the feature closes. A later feature can use the generator once it accepts an explicit number without rewriting `.specify/feature.json`. | Owner, in the approved plan of 2026-11-14 (section 7, "hand-authored artifacts"). The owner's reply at checkpoint 1 on 2026-11-14 accepted the decisions put to it; this exception's text was not among them and is put to the owner at checkpoint 2. |
| E5. A manual cross-artifact analysis recorded in `checklists/analysis.md` replaces the `$speckit-analyze` command, which the constitution requires before implementation. | The analysis of spec, plan, tasks and contracts for this feature (GOV-03). | The analyze command operates on the active feature named in `.specify/feature.json`, which cannot be changed (E4). The approved plan calls for "a recorded cross-artifact analysis"; `checklists/analysis.md` records each check, its result and the findings. | The manual analysis misses an inconsistency the command would have found. | Re-recorded whenever `tasks.md` or a contract changes materially, and at each milestone; expires with E4 when the feature closes. | Owner, in the approved plan of 2026-11-14 (section 7, step 1). The owner's reply at checkpoint 1 on 2026-11-14 accepted the decisions put to it; this exception's text was not among them and is put to the owner at checkpoint 2. |
| E6. Donor benefit is recorded as a pre-adoption estimate before adaptation starts and measured only at close-out, whereas ADR 0004 asks for measured benefit before donor code is copied or adapted. | Every file adapted or translated from project-maya: translated donor tests from M1, the adapted dashboard from M8 (WEB-01). | `docs/upstream/PROJECT_MAYA.md`, section "Measured benefit", records the pre-adoption estimate from the planning analysis; the measured figures (adapted lines against a clean-rewrite estimate, feature coverage on a named checklist) are recorded in the M10 parity report. | Adaptation proceeds on an estimate, and the measured benefit turns out smaller than estimated. | Expires when the M10 parity report records the measured benefit. | Owner, accepted at checkpoint 1 on 2026-11-14 (OPEN-27, settled). Which named checklist the close-out coverage figure uses stays open (OPEN-57). |

No other exception is requested. In particular, the constitution's step 5 (repository-wide
rustfmt and Clippy debt) does not apply inside `console/`: formatting and
`clippy -D warnings` are clean from the first commit and enforced in CI.

## Project Structure

### Documentation (this feature and its companions)

```text
specs/022-console-serving-parity/
├── spec.md                    # GOV-01: requirements, user stories, success criteria
├── checklists/
│   ├── requirements.md        # GOV-01: specification quality checklist
│   └── analysis.md            # GOV-03: cross-artifact analysis (E5), open-item register
├── plan.md                    # GOV-02: this file
├── research.md                # GOV-02: decisions, dependency table, open items
├── data-model.md              # GOV-02: entities, fields, invariants, persisted files
├── quickstart.md              # GOV-02: build, test and run commands (updated per package)
├── contracts/                 # GOV-06 cross-cutting contracts; packages add their own
│   ├── backend-seam.md        # token-level and event-level seam (draft; ENG-01 freezes it)
│   ├── naming.md              # old-to-new name table (binding decision B2)
│   ├── parity-ledger.md       # ledger schema and dispositions
│   └── deviations.md          # deviation register
├── tasks.md                   # GOV-03: every work package with its definition of done
└── tasks/                     # GOV-03: per-subsystem package detail
    ├── api.md  engine.md  prompt.md  responses.md
    └── ops.md  web.md  conformance.md

docs/architecture/decisions/0008-console-serving-ahead-of-stage-f.md   # GOV-04
docs/roadmap/CONSOLE_ROADMAP.md                                         # GOV-04: Phases 1 to 3
docs/roadmap/PULSARMLX_STRATEGY.md                                      # GOV-04: dated pointer only
docs/upstream/PROJECT_MAYA.md                                           # GOV-05: donor qualification
docs/upstream/PROJECT_MAYA_SYNC.md                                      # GOV-05: pin and sync rules
docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md                          # owner request of 2026-11-14
docs/console/                                                           # later operator docs
NOTICE.md                                                               # GOV-05: donor section
README.md                                                               # GOV-04: one status row
CONTRIBUTING.md                                                         # GOV-04: console commands
```

Contract documents named in the planner records and written by their packages include the
engine seam and line protocol (ENG-01, ENG-04), the HTTP route contracts (API-20), the
UI-to-server contract that Phase 2 targets (WEB-05), the Responses, MCP, attachment and
media contracts (RSP packages) and the operations contracts (OPS-23). Their exact file
names are fixed by those packages.

### Source code (`console/`, a standalone nested Cargo workspace)

```text
console/
├── Cargo.toml                 # own [workspace]; not a member of the root workspace
├── Cargo.lock                 # own lock; dependencies pinned with =
├── rust-toolchain.toml        # channel 1.97.1, components rustfmt and clippy
├── LICENSES/                  # project-maya MIT; third-party texts arrive with their component
├── crates/
│   ├── console-pyjson         # Python-compatible JSON and string output (wire and files)
│   ├── console-core           # request and event model, backend seam, FIFO scheduler,
│   │                          # turn driver, run-config store, monitor model,
│   │                          # outbound curl facade (module outbound, RSP-10;
│   │                          # placement by lead decision)
│   ├── console-tokenizer      # byte-level BPE reader, byte tokenizer, incremental detokenizer
│   ├── console-prompt         # normalization, chat templates, output parsers, tool-call
│   │                          # syntaxes, thinking budget, loop guards
│   ├── console-engine         # scripted engine, line-protocol client and supervisor,
│   │                          # multi-conversation mode, vision helper, multi-GPU helpers
│   ├── console-http           # transport, security posture, OpenAI and Anthropic dialects,
│   │                          # utility, monitoring and admin routes
│   ├── console-responses      # Responses API, store, background jobs, schema validator
│   ├── console-mcp            # MCP client hub and tool loop (plus fake MCP server for tests)
│   ├── console-attach         # attachment readers, PDF text
│   ├── console-media          # picture and video plumbing
│   ├── console-manage         # model registry and settings, model APIs, pull driver,
│   │                          # savings, update contract
│   ├── console-host           # telemetry: Apple Silicon reader, ported readers behind traits
│   ├── console-launch         # `pulsar-console supervise` and `pulsar-console fetch`
│   ├── console-web            # embedded dashboard assets, static routes, security headers,
│   │                          # preview route
│   ├── pulsar-console         # the binary
│   ├── console-fake-engines   # test only: fake line-protocol engine binaries and the
│   │                          # one fake vision encoder (ENG-14, lead decision)
│   ├── console-testkit        # test only: raw HTTP client, SSE parser, test server builder
│   ├── console-conformance    # test only: scenarios, comparator, ledger checker
│   ├── console-web-e2e        # test only: browser end-to-end harness (manual job)
│   └── xtask                  # test only: maintenance tasks, never linked into the binary
├── web/                       # Phase 1 dashboard (adapted JavaScript, upstream file names)
├── conformance/               # scenarios, recorded references, oracle pin
├── parity/
│   └── ledger.json            # one row per donor test method (913 rows)
└── tools/
    ├── check-boundary.sh      # non-interference check
    ├── check-hygiene.sh       # staged-content and repository-trap check
    └── check-toolchain.sh     # toolchain pin check for hosts without rustup

.github/workflows/console.yml  # path-filtered console CI
```

**Structure decision**: A standalone nested workspace keeps every engine-track byte
unchanged and gives the console its own lock, toolchain pin and workflow. The pattern has
precedent, though neither example is on `main`: the reverted `crates/serve-synthetic`
(kept at tag `archive/2026-09-21/feat/openai-serving`) declared its own `[workspace]`, and
so does the engine track's `experiments/packed-affine-adoption` on its feature branch. The
crate split follows ownership: `console-core` owns the seam types, the scheduler and the
turn driver; `console-engine` owns every engine implementation; `console-prompt` owns text
decisions as pure state machines; `console-http` frames and sends; feature crates register
routes through a small handler API so the transport does not depend on every feature. The
fake engines live in their own crate so they share no code with the client they test and
never ship in the product binary. Test data directories are named `testdata/` or
`tests/data/` (binding decision B13), never `fixtures/` at the console root and never a
`.gitignore` trap name. The deviation register lives at
`specs/022-console-serving-parity/contracts/deviations.md`, beside the other contracts.

## Milestones

Eleven milestones. Each ends reviewable with tests green and the ledger updated. After M1
the lanes M2 to M8 run largely in parallel; M9 is deliberately last among the feature
lanes, and M10 closes the increment. The assignment of packages to milestones is binding.

| Milestone | Delivers | Packages |
| --- | --- | --- |
| **M0** Governance and skeleton | Spec and requirements checklist; plan, research, data model, quickstart; tasks and recorded cross-artifact analysis; ADR 0008, roadmap, strategy pointer, README row and `CONTRIBUTING.md` commands; donor qualification, `NOTICE.md` section and the project-maya license text; empty `console/` workspace, boundary and hygiene tools, `console.yml`, parity ledger skeleton, cross-cutting contracts. | GOV-01 to GOV-06 |
| **M1** Core pipeline | Python-compatible JSON; HTTP transport, router and security posture; request validation and sampling; backend seam, scripted engine, FIFO, turn driver; byte tokenizer and detokenizer; chat completions for plain content; run-config store; test kit, scenario format, raw client, comparator and process harness. First end-to-end target: a streamed answer over `curl`. | API-01, API-02, API-03, API-04, API-07, API-08, API-15, API-19, ENG-01, ENG-02, ENG-09, ENG-10, PRM-04, CNF-01, CNF-02, CNF-03, CNF-04, CNF-07 |
| **M2** Prompt and output | Test kit for templates; Jinja runtime; thinking levels and template families; request normalization; DeepSeek encoder; special-literal protection; streaming parser for every tool-call syntax and both rewriters; prompt orchestration; output pipeline with stops; thinking budget; both loop guards; response shapes; Anthropic Messages. | PRM-02, PRM-03, PRM-05 to PRM-16, API-09 |
| **M3** Engine supervision | Sampling key encoder; line-protocol codec, fake engine binaries, child engine, multi-conversation mode; supervision, restart, unload and shutdown; fair slices and continuations; engine host lifecycle; launch specification; prompt memo and restore points; engine conformance suite; coordinator-shaped runtime adapter. | ENG-03 to ENG-08, ENG-11, ENG-12, ENG-15, ENG-17, ENG-18, ENG-19 |
| **M4** Monitoring and admin | Monitor model; `/health`, `/status`, `/metrics` and Prometheus; resumable web streams; discovery and utility routes; admin routes; context reload; logging, signals and parent watch; CLI and graceful shutdown; route contracts; telemetry core and the Apple Silicon reader. | API-05, API-06, API-10, API-11, API-13, API-14, API-16, API-17, API-20, OPS-17, OPS-18 |
| **M5** Responses API | Limits and in-memory store; restricted schema validator; normalizer; serializer; background jobs with replay; foreground and background routes. | RSP-01 to RSP-07 |
| **M6** MCP, attachments, media | MCP framing, fake MCP server, client hub over stdio and Streamable HTTP, tool loop; Office, OpenDocument, EPUB, RTF and PDF readers; inline file parts and routes; media seam, external encoder adapter, DeepSeek picture preprocessor (MiniMax half not built, LIC-2); vision helper process. | RSP-08 to RSP-19, ENG-14 |
| **M7** Model management | Settings sources and naming; classification; product facts and tune keys; settings profiles; Turbo; listing; delete plan and execution; restart and switch; supervisor; both model APIs; catalog (shipped empty) and pull driver; `fetch`; savings; update contract (route shapes only, SEC-5); route integration. | OPS-02 to OPS-16, OPS-21, OPS-22, OPS-23 |
| **M8** Dashboard, Phase 1 | Asset import with provenance and neutral identity; embedded serving with security headers; hardened model-output rendering; page-logic tests; UI-to-server contract for Phase 2; browser end-to-end harness; Apple Silicon monitor view and synthetic badge; Models, Settings and MCP pages; static routes; front-end test harness. | WEB-01 to WEB-07, WEB-09, WEB-10, WEB-11, API-12, CNF-15 |
| **M9** Hardware and OS ports | NVIDIA and AMD readers, GPU map, mixed-GPU helper, Windows lifecycle shims, the GPU-era monitor paths, the reader fixture kit; all fixture-verified and labeled unverified on real hardware (PLAT-1, binding decision B11). By lead decision, hardware-specific parts that land before M9 are built behind traits with fixtures and labeled unverified; the real readers stay in M9. | OPS-19, OPS-20, ENG-13, ENG-16, API-18, WEB-08, CNF-16 |
| **M10** Close-out | Oracle driver and pin manifest; reference capture and differential runner; shim tier; vendor-template render checks; ledger checker and inventories; SDK client tests; independent contract, metamorphic, property and security suites; drift canary and conformance documentation; three scenario corpora; end-to-end prompt and output parity suite; every mismatch triaged; ledger with no pending rows; parity report; final quickstart and status rows. | CNF-08 to CNF-14, CNF-17 to CNF-20, PRM-17 |

Merged duplicates: PRM-01 is merged into API-01 (one `console-pyjson` crate); OPS-01 into
API-01 (the JSON writer) and API-15 (the run-config document store); CNF-05 into ENG-05
(one set of fake engine binaries in `console-fake-engines`); CNF-06 into RSP-08 (one fake
MCP server). WEB-P2-01 to WEB-P2-03 are Phase 2 roadmap items, not tasks of this
increment.

**Highest-risk packages**, which get an extra reviewer (the approved plan names them by
function; the package ids are mapped from the planner records): the request lifecycle
driver and turn driver (API-07, ENG-10), the Jinja runtime, output pipeline and cross-turn
loop guard (PRM-03, PRM-12, PRM-15), the line-protocol client and server-side
continuations (ENG-06, ENG-11), background jobs (RSP-05), settings profiles, the delete
plan and the fetch tool (OPS-05, OPS-08, OPS-16), browser end-to-end and the Models page
(WEB-06, WEB-09), and the differential runner (CNF-09). A lead decision made after
approval, not the owner, adds API-17, CNF-04, CNF-11, CNF-19, OPS-09 and RSP-07 to this
list.

**Binding cross-cutting decisions** B1 to B13 (transport, names, JSON, templates,
tokenizer, no `rmcp` or `jsonschema`, outbound network, security posture, fake engines,
items not built, platform ports, CI, test data names) are stated in
[tasks.md](tasks.md#binding-cross-cutting-decisions) and
override any conflicting sentence in a planner record. Their rationale is in
[research.md](research.md).

## Non-Interference

The engine track is active and binds evidence to file hashes and to tree identity. The
console must change none of the files it edits or hashes.

**Rules**

1. **Allowlist.** The work may touch only `console/**`,
   `specs/022-console-serving-parity/**`, `docs/console/**`,
   `docs/roadmap/CONSOLE_ROADMAP.md`, `docs/upstream/PROJECT_MAYA.md`,
   `docs/upstream/PROJECT_MAYA_SYNC.md`,
   `docs/architecture/decisions/0008-console-serving-ahead-of-stage-f.md`, `NOTICE.md`,
   `.github/workflows/console.yml`, and three small edits: a dated pointer in
   `docs/roadmap/PULSARMLX_STRATEGY.md`, one status row in `README.md`, and the console
   commands in `CONTRIBUTING.md`.
2. **Never touched.** The root `Cargo.toml` and `Cargo.lock`,
   `.github/workflows/macos.yml`, everything under `crates/`, `experiments/`, `fixtures/`,
   `scripts/` and `docs/research/`, `.specify/` (including `.specify/feature.json`),
   `.gitignore`, the root `pyproject.toml` and `uv.lock`. The first three are hash-bound
   into the engine track's frozen evidence.
3. **No path dependency** from any console crate to anything outside `console/`, so no
   engine-track source becomes a console build input.
4. **No silently ignored files.** No tracked path under `console/` or the feature
   directory may match a `.gitignore` rule (directories named `models`, `weights`,
   `checkpoints`, `logs`, `dist`, `env`, `debug`, `release`, `target`; files such as
   `*.log`, `*.key`, `*.pem`, `secrets.*`, `credentials.json`, `mcp.json`, `*.trace.json`,
   `*.bench.json`, `*.prof*`, `*.tmp`).
5. **No reserved engine-track name** is used for a console path, crate or branch.
6. **Separate clone and target directory.** The work runs only in the fresh clone outside
   iCloud and its worktrees, never in the owner's iCloud checkout, which is the engine
   track's object store; no `worktree`, `gc` or `prune` runs there. Build output goes to a
   target directory outside the repository.
7. **Host courtesy.** Builds on the owner's build host run at low priority. Before each
   build wave the lead checks that no engine qualification process is running, and work
   stops when the owner says a qualification run is coming.
8. **Pushes are batched at owner checkpoints**, because every push of this branch also runs
   `macos.yml`'s full native qualification (about 35 minutes of macOS runner time; its
   classifier treats `console/`, `specs/` and a new workflow file as code and that file is
   frozen).

**How they are checked**

| Check | What it verifies | When |
| --- | --- | --- |
| `console/tools/check-boundary.sh` | The diff against the merge base with `main` touches only the allowlist; the blobs of the root `Cargo.toml`, `Cargo.lock` and `macos.yml` equal those at the merge base; nothing under `console/` or the feature directory is ignored by `.gitignore` or uses a trap name; no console manifest has a path dependency outside `console/`; no reserved engine-track name is used. | Before every commit, and in the blocking preflight job |
| `console/tools/check-hygiene.sh` | Staged-content rules ported from `scripts/research/check_staged.sh` (credentials, binary files, file and total sizes, home-directory paths, UUIDs, host and user JSON values, forbidden extensions) plus the absence of AI attribution in the commit range. | Before every commit, and in the blocking preflight job |
| `git diff --stat origin/main...HEAD` | Only allowlisted paths changed, read by a person. | At every checkpoint and before any pull request |
| Lead review | The two scripts and `console.yml` are themselves inside the allowlist, so a change could weaken them; any diff to them gets an explicit review line in the commit's review record. | Every commit that touches them |

What this guarantees and what it does not: no file the engine track edits or hashes
changes. The tree identity of `main` still changes when this merges, like any commit, and
engine evidence is bound to tree identity, so merge order is decided with the owner
(OPEN-14).

## Execution Model

- **Roles.** The lead plans, sequences, gates and integrates, and makes every commit. Each
  work package is implemented by one coding agent in one session, then reviewed by
  independent reviewers with distinct lenses: the contract, security, parity with the
  cited donor lines, and non-interference. Findings are fixed and re-verified before the
  commit. Highest-risk packages get an extra reviewer.
- **Independent tests** (evidence C) are written by a different agent than the one that
  ported the behavior, told not to read the donor tests, as ADR 0004 requires.
- **Lanes.** Parallel lanes use git worktrees of the fresh clone after M0 and M1 are
  committed locally, with a shared target directory outside the repository.
- **Gate before each commit.** Formatted, Clippy-clean and tests green in the nested
  workspace; the package's ledger rows resolve; boundary and hygiene checks pass; the
  message is conventional (`feat(console): ...`), explains one change, and carries no AI
  attribution or co-author trailer.
- **Definitions of done** for every package are in `tasks.md` and `tasks/`; a package is
  not done until its quickstart entries, contracts and ledger rows are updated in the same
  change.

## Checkpoints With the Owner

1. **M0 documents that speak in the owner's name**: `spec.md` with its checklist, ADR 0008,
   the roadmap entries, `NOTICE.md` and the donor qualification record. The constitution
   exceptions in this plan are confirmed here.
2. **The M1 demonstration**, and the decision to make the first push.
3. **Every later push, and each milestone report** (ledger counts, deviations added).
4. **Any pull request.** Default merge policy: a merge commit; engine branches are never
   asked to rebase; the no-touch list is re-derived from GitHub first.

Nothing is pushed, opened as a pull request, or merged without the owner's go-ahead.
Whether `console.yml` becomes a required check is the owner's call at merge time (OPEN-13).

## Verification Plan

These are the checks this feature will rely on; none has been run yet.

- **Tests:** `cargo test --locked` from `console/`; `node --test` for the web logic.
- **End to end by hand:** start `pulsar-console` with the scripted engine; `curl -N` a
  streamed chat completion and an Anthropic message and check frames, finish reason and
  usage; repeat through the line-protocol engine against the fake engine binary; kill the
  fake engine mid-answer and confirm the 503 and the restart.
- **Dashboard:** open it in a browser against the scripted engine; send, stream, stop,
  reload mid-answer, switch views; confirm the synthetic badge, the security headers, and
  that a cross-origin POST is refused.
- **Parity:** the ledger report (counts per disposition as defined in
  [contracts/parity-ledger.md](contracts/parity-ledger.md); no pending rows at close-out),
  the reference replay, and the committed records of the manual shim and vendor-render
  runs.
- **Non-interference:** `console/tools/check-boundary.sh` and
  `git diff --stat origin/main...HEAD` showing only allowlisted paths.
- **CI:** `console.yml` green on the exact head; `macos.yml` green, or its failure shown to
  be present on `main` too.

## Complexity Tracking

The six constitution exceptions above are the only departures. Two deliberate sources of
complexity are justified here:

| Complexity | Why needed | Simpler alternative rejected because |
| --- | --- | --- |
| A hand-written HTTP/1.0 transport instead of a framework | Byte-level parity with the donor's standard-library server, including connection close after each response, status lines, and client-disconnect detection | `hyper` or `axum` answer HTTP/1.1 with different framing and headers, and the reverted crate's `hyper` stack would add dependencies that parity does not need |
| A second set of engines (Rust fake binaries) beside the donor's Python fakes | Fakes must run in blocking CI without Python and must share no code with the client they test | Running the donor's Python fakes locally is forbidden (binding decision B9) and would bring a Python harness back into the gate, the failure class behind the September revert |
