# PulsarMLX Console roadmap

**Updated 2026-11-15. Planning, not execution authorization beyond Phase 1.**

PulsarMLX Console is the planned serving layer and browser dashboard for PulsarMLX: a
Rust server, binary `pulsar-console`, rebuilt from the `serve/` directory of the donor
project-maya at commit `7e68a30f` (v1.1.63). The decisions behind it are recorded in
[ADR 0008](../architecture/decisions/0008-console-serving-ahead-of-stage-f.md), the donor
qualification in [`docs/upstream/PROJECT_MAYA.md`](../upstream/PROJECT_MAYA.md), and the
requirements, plan and tasks in
[`specs/022-console-serving-parity/`](../../specs/022-console-serving-parity/).

The owner asked on 2026-11-14 for the two-phase front-end plan to be committed to the
roadmap. This document records it, together with the engine attachment that would
follow and would need its own approval. It changes nothing in the
[strategy](PULSARMLX_STRATEGY.md)'s engine sequence: real-model serving acceptance remains
gated as Stage F and [OPT-08](OPTIMIZATION_ROADMAP.md#concrete-work-register) describe.

## Status vocabulary

| Term | Meaning here |
| --- | --- |
| Not started | No artifact exists and no work is authorized beyond this roadmap entry. |
| Planned | Scoped in committed planning documents; no implementation exists. |
| In development | Work has started on the feature branch; nothing is claimed as working. |
| Qualified on synthetic backends | Its tests, scenarios and ledger rows pass against synthetic engines in the recorded CI jobs. This is the strongest claim available to Phases 1 and 2. It says nothing about any real model. |
| Unverified on real hardware | Exercised only against recorded fixtures; never run on the hardware it reads. |

No phase on this roadmap serves a real model. A claim that the console serves a real model
requires Phase 3 and the qualification that Stage F requires.

## Phases at a glance

| Phase | What it delivers | Status on 2026-11-15 |
| --- | --- | --- |
| 1 | Rust server and the adapted JavaScript dashboard, at full behavioral parity with project-maya's `serve/`, on synthetic backends | In development: the 18 work packages of M1 are built on the feature branch, and their tests pass on the build host against synthetic engines; the minimal binary answered a streamed chat completion from the scripted synthetic engine in a local demonstration on 2026-11-15. No CI run covers any M1 package, so nothing is claimed as qualified. Owner checkpoint 2 is not held yet. Target: qualified on synthetic backends. |
| 2 | Complete rewrite of the front end in Rust compiled to WebAssembly, against the written UI-to-server contract, served beside Phase 1 until cutover | Not started; planned only at the level of this outline |
| 3 | A real engine attached to the console through the backend seam | Not started; needs its own approval |

## Phase 1: Rust server and adapted dashboard (this increment)

**Scope.** Driven by equivalent fake engines, the Rust implementation shows the same
externally observable behavior as project-maya's `serve/` at the pinned commit for every
route, stream format, error, configuration key, environment variable and persisted file.
Parity is measured by the parity ledger, `console/parity/ledger.json`, with one row per
donor test method; every intended difference is an approved entry in
[`contracts/deviations.md`](../../specs/022-console-serving-parity/contracts/deviations.md).
The dashboard is project-maya's no-build JavaScript front end, adapted to the PulsarMLX
Console identity and served by the Rust server from assets compiled into the binary. It
shows a permanent "Synthetic engine: no real model" badge.

**Boundaries.** All work lives in the standalone `console/` Cargo workspace and the
feature's documents. It touches no file the engine track edits or hash-binds. Launching
any project-maya engine binary is out of scope. Not built in this increment: the MiniMax
picture preprocessor (LIC-2), the refusal-ablation switch (POL-1), self-update beyond its
route shapes (SEC-5), and any real model catalog entry (the catalog ships empty).
Hardware and OS specific readers (PLAT-1) come last, in M9, and stay unverified on real
hardware; hardware-specific parts that land before M9 are built behind traits, tested with
fixtures and labelled unverified.

**Milestones.** Each milestone ends reviewable, with tests green and the ledger updated.
After M1 the milestones M2 to M8 can run largely in parallel; M9 is deliberately last.
Work package ids are those of the feature's `tasks.md`.

| Milestone | Delivers | Work packages | Status |
| --- | --- | --- | --- |
| M0 Governance and skeleton | Spec Kit artifacts, ADR 0008, this roadmap, donor qualification, `NOTICE.md` and the project-maya license text; empty `console/` workspace, boundary and hygiene tools, `console.yml`, parity ledger skeleton, cross-cutting contracts | GOV-01 to GOV-06 | In development |
| M1 Core pipeline | Python-compatible JSON; HTTP/1.0 transport, router and security posture; request validation; backend seam, scripted engine, FIFO scheduler and turn driver; byte tokenizer and detokenizer; chat completions for plain content; run-config store; test kit and scenario comparator. First end-to-end goal: a streamed answer over `curl` from the scripted engine | API-01, API-02, API-03, API-04, API-07, API-08, API-15, API-19, ENG-01, ENG-02, ENG-09, ENG-10, PRM-04, CNF-01, CNF-02, CNF-03, CNF-04, CNF-07 | In development: built on 2026-11-14 and 2026-11-15, three of 18 tasks ticked, owner checkpoint 2 not held yet |
| M2 Prompt and output | Template runtime after a compatibility spike; request normalization; BPE tokenizer; special-literal protection; streaming parser for all tool-call syntaxes; DeepSeek encoder; thinking levels and budget; stop strings; both loop guards; Anthropic Messages | PRM-02, PRM-03, PRM-05 to PRM-16, API-09 | Planned |
| M3 Engine supervision | Line-protocol codec, client and supervisor; request-key encoder; multi-conversation mode; fair slices; restart, unload and shutdown; prompt memo and restore points; fake engine binaries; engine conformance suite; coordinator-shaped adapter | ENG-03 to ENG-08, ENG-11, ENG-12, ENG-15, ENG-17, ENG-18, ENG-19 | Planned |
| M4 Monitoring and admin | `/health`, `/status`, `/metrics` and Prometheus output; discovery and tokenizer routes; settings, context, thinking-budget, port and report routes; resumable web streams; logging, signals, CLI and graceful shutdown; telemetry core and the Apple Silicon reader | API-05, API-06, API-10, API-11, API-13, API-14, API-16, API-17, API-20, OPS-17, OPS-18 | Planned |
| M5 Responses API | Normalizer and serializer; in-memory store; background jobs with replay; restricted JSON Schema validator; routes | RSP-01 to RSP-07 | Planned |
| M6 MCP, attachments, media | MCP client over stdio and streamable HTTP, tool loop, fake MCP server; Office, OpenDocument, EPUB, RTF and PDF readers; media seam, external encoder adapter, DeepSeek picture preprocessor | RSP-08 to RSP-19, ENG-14 | Planned |
| M7 Model management | Registry, settings profiles, Turbo, switch and restart, delete and leftovers, both model APIs, catalog and pull driver, `pulsar-console fetch` and `pulsar-console supervise`, savings, update contract | OPS-02 to OPS-16, OPS-21, OPS-22, OPS-23 | Planned |
| M8 Dashboard, Phase 1 | Asset import with provenance and neutral identity; embedded serving with security headers; hardened rendering of model output; page-logic tests; the UI-to-server contract and schemas that Phase 2 targets; Apple Silicon monitor view; Models, Settings and MCP pages; browser end-to-end scenarios | WEB-01 to WEB-07, WEB-09, WEB-10, WEB-11, API-12, CNF-15 | Planned |
| M9 Hardware and OS ports | NVIDIA, AMD and Windows readers, GPU map, mixed-GPU helper, Windows lifecycle shims and the GPU-era monitor paths, behind traits and fixture-tested; type-checked for Linux and Windows in CI; unverified on real hardware | OPS-19, OPS-20, ENG-13, ENG-16, API-18, WEB-08, CNF-16 | Planned |
| M10 Close-out | Reference capture with every mismatch triaged; scenario corpora; ledger with no pending rows; SDK client tests; parity report; quickstart; status rows | CNF-08 to CNF-14, CNF-17 to CNF-20, PRM-17 | Planned |

**Phase 1 is complete when** the ledger has no pending rows, the committed reference
corpus replays cleanly in the blocking CI jobs, and the parity report states matched,
deviation and not-applicable counts. At that point Phase 1 may be described as qualified
on synthetic backends, and no more than that.

## Phase 2: front end rewritten in Rust and WebAssembly (later, not started)

**Goal.** Replace the adapted JavaScript dashboard with a front end written in Rust and
compiled to WebAssembly, without changing the server. Phase 2 targets the written
UI-to-server contract that Phase 1 produces in M8 (WEB-05): every route the page calls,
the stream formats, the restart-following protocol, browser storage keys and the
IndexedDB chat record schema, URLs, export format, design tokens and the Markdown subset.
The Phase 1 dashboard and its golden fixtures are the behavioral oracle.

**Data compatibility (proposed).** Phase 2 reads the same browser storage keys (prefix
`pulsar.`) and the same IndexedDB chat records (database `pulsar-console`) unchanged, so
chats created in either phase open in the other.

**Coexistence (proposed).** Phase 1 stays at `/` while Phase 2 is served at `/ui2/` against
the same API. Both are same-origin, so storage is shared. A server option chooses the
default UI.

The steps below are a proposed outline, not decisions. The owner has decided only that
Phase 2 is a complete rewrite in Rust and WebAssembly, against the written UI-to-server
contract, served beside Phase 1 until cutover. Paths, browsers, crate names and the
cutover sequence are settled in the WEB-P2-01 decision record that the owner approves. The
steps are items WEB-P2-01 to WEB-P2-03 in
[`tasks/web.md`](../../specs/022-console-serving-parity/tasks/web.md); they are roadmap
items, not tasks of the current increment, and are not sized.

| Step | What it does | Done when |
| --- | --- | --- |
| WEB-P2-01 Shared contract crate and tooling decision | A `console-ui-contract` crate of serialization types for every UI-facing request and response, building for both `wasm32-unknown-unknown` and native, checked against the Phase 1 schemas and fixtures so that client and server share one Rust definition. A framework spike with a written decision record comparing candidates on payload size against the current dashboard bundle, streaming-render cost on a long answer, and fetch-stream and IndexedDB ergonomics. A pinned toolchain driven from `xtask`, with build output in `console/web-wasm/out` (never `dist/`, which `.gitignore` ignores). The Markdown renderer is ported by hand so the Markdown-subset goldens still match. | The owner approves the decision record, and the contract crate builds for wasm32 and native and passes a conformance test against the Phase 1 fixtures. |
| WEB-P2-02 Chat core | The shell, store, storage, chat streaming with resume and cancel, composer, attachments, Markdown painter, sidebar and search, using the same CSS, design tokens and accessible names, served at `/ui2/`. The Phase 1 browser end-to-end suite runs unchanged against `/ui2/` through a base-path switch; that is the parity gate. The Node page-logic tests do not apply to WebAssembly and are re-expressed as Rust tests of the ported functions. | The end-to-end chat suite passes on `/ui2/` in Safari and Chrome, and chats round-trip between the two phases. |
| WEB-P2-03 Remaining views and cutover | Monitor, Models, Settings and Turbo, with every fixture-driven GPU and Apple path and every restart-following flow. Then cutover: the WebAssembly UI becomes the default at `/`, Phase 1 moves to `/ui1/`, and its assets are then removed. `NOTICE.md` drops entries for third-party code no longer shipped. | The full end-to-end suite and the conformance gate are green on the WebAssembly UI at `/`, and Phase 1 assets are removed with the owner's approval. |

**Open in Phase 2 (OPEN-20).** The framework choice is open: Leptos, Dioxus and Yew are
proposed as candidates, and the WEB-P2-01 spike informs the owner's decision. Also open:
whether built WebAssembly output is committed with reproducibility checks or built in CI,
given that the repository's staged-content checks reject binary files, and how the server
embeds it.

Phase 2 starts only with the owner's approval after Phase 1, and remains synthetic-backend
only until Phase 3 is approved.

## Phase 3: real engine attachment (later, needs its own approval)

**Goal.** Attach a real PulsarMLX engine to the console through the backend seam that
Phase 1 defines, without changing the server's HTTP behavior.

The seam has a token level and an event level, so the engine can attach at whichever
level it owns; both are defined in
[`contracts/backend-seam.md`](../../specs/022-console-serving-parity/contracts/backend-seam.md).
How the token level serves more than one concurrent generation is settled before the seam
is frozen (OPEN-30). Phase 1 proves the fit only with a coordinator-shaped test adapter,
and the seam contract is offered to the engine track for review before it is frozen.

Phase 3 depends on the engine track, not on this roadmap. It needs its own decision, and
real-model serving acceptance remains gated as the strategy describes: a stable local
runtime under Stage F, and native generation and streaming equivalence before OPT-08.
Launching a project-maya engine binary is not a route to Phase 3; it would need its own
ADR 0004 qualification.

In this increment the server refuses to start an engine that does not report
synthetic provenance, on every path that admits an engine, and no flag, environment
variable, configuration key or Cargo feature bypasses the refusal. The owner decided this
on 2026-11-14, settling OPEN-29. The decisions and engineering steps that must come before
the refusal is lifted are listed in
[`docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md`](../console/ALLOWING_NON_SYNTHETIC_ENGINES.md).

## Open items

These are recorded, not decided. Every open item of the feature, with who decides it, is
listed in the register in
[`checklists/analysis.md`](../../specs/022-console-serving-parity/checklists/analysis.md);
the ids below are its ids.

- OPEN-13: whether `.github/workflows/console.yml` becomes a required check on `main`,
  decided by the owner at merge time.
- OPEN-14: the merge order of the feature branch relative to engine-track branches whose
  evidence is bound to tree identity.
- OPEN-20: the Phase 2 framework and the handling of built WebAssembly output.
- OPEN-28: any re-pin of project-maya beyond `7e68a30f`.

## Traceability

| Source | What this roadmap takes from it |
| --- | --- |
| Owner-approved plan of 2026-11-14, as recorded in ADR 0008 and carried into [`plan.md`](../../specs/022-console-serving-parity/plan.md) and [`tasks.md`](../../specs/022-console-serving-parity/tasks.md) | The two-phase front end, full parity, synthetic-only backends, milestones M0 to M10, the deviations and the CI shape. |
| [ADR 0008](../architecture/decisions/0008-console-serving-ahead-of-stage-f.md) | The authorization for Phase 1 ahead of Stage F and its limits. |
| [Strategy](PULSARMLX_STRATEGY.md) and [optimization roadmap](OPTIMIZATION_ROADMAP.md) | Stage F and OPT-08 as the gates for real-model serving. |
| [`tasks/web.md`](../../specs/022-console-serving-parity/tasks/web.md), items WEB-05 and WEB-P2-01 to WEB-P2-03 | The UI-to-server contract and the proposed Phase 2 outline. |

This document is a mutable planning register. It authorizes Phase 1 only through
ADR 0008 and authorizes nothing in Phases 2 and 3.
