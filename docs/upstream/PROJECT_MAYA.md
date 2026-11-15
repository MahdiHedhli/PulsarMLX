# Upstream donor: project-maya

**Status**: approved on 2026-11-14 as the donor for adaptation and reimplementation of
the PulsarMLX Console serving layer and dashboard (feature 022). The source and license
review is complete, and attribution and compatibility analysis are set up; independent
tests are planned; benefit is recorded as a pre-adoption estimate and measured at
close-out (M10), an ordering the owner accepted on 2026-11-14 (OPEN-27, settled). See [ADR 0004 requirements](#adr-0004-requirements).

**Decision**: project-maya's `serve/` and `serve/web/` at the pinned commit are the
behavioral reference for PulsarMLX Console. The dashboard's JavaScript is adapted; the
Python server is reimplemented in Rust against written contracts. project-maya is **not a
runtime dependency** of PulsarMLX, and **its engines are not used**.

project-maya was chosen as the donor in the plan the owner approved on 2026-11-14 (not
published in this repository; its decisions are recorded in ADR 0008 and in the feature's
Spec Kit artifacts).
[ADR 0008](../architecture/decisions/0008-console-serving-ahead-of-stage-f.md) records it.
This document is the source and license review that
[ADR 0004](../architecture/decisions/0004-donor-code-qualification.md) requires.

Everything below that describes PulsarMLX Console is **planned work**. As of 2026-11-14 no
donor-derived file has been committed, nothing has been built, and nothing has been
measured. When built, the console can at most be described as *qualified on synthetic
backends*: it serves no real model.

## Pin

| Field | Value |
| --- | --- |
| Repository | <https://github.com/mw00/project-maya> |
| Commit SHA | [`7e68a30f2f208056195352129188661fb6b94445`](https://github.com/mw00/project-maya/commit/7e68a30f2f208056195352129188661fb6b94445) |
| Package version | 1.1.63 (`VERSION`; `CHANGELOG.md` entry "v1.1.63 - 2026-11-14") |
| Commit date | 2026-11-14 17:32:50 UTC |
| License | **MIT**, with two copyright lines (below) |
| Copyright | Copyright (c) 2026 Peasant Smith and the Project Maya contributors |
| Copyright | Copyright (c) 2026 Niko1221 and the Strata contributors |
| Platforms | Engines: Linux x86-64 and Windows 10/11 with NVIDIA (CUDA) or AMD (ROCm/HIP) GPUs. macOS on Apple Silicon is experimental: the README names GLM-5.3-Flash only, and `docs/METAL.md` adds an experimental MiniMax-M3.1-Flash engine; both run GGUF quants on ggml's Metal backend. Server: Python 3.10 or newer per the README; the donor's own CI runs the server tests on Ubuntu with Python 3.12 and no GPU. |

The pin was checked against a shallow, read-only local checkout of that commit (one
commit, no tags, 1,708 tracked files), kept outside this repository. Files were read as
text. No project-maya code was executed on a PulsarMLX machine, and none will be: under
that plan, project-maya's own server runs only in a manual GitHub Actions job.

The second copyright line records project-maya's lineage from the MIT-licensed Strata
project. It is kept even though only server and dashboard behavior is used, because
project-maya's own documentation says its server and dashboard grew from Strata, and its
changelog records server features taken from Strata releases.

## What it is

project-maya runs very large mixture-of-experts models locally by tiering experts across
GPU memory, pinned RAM and NVMe storage. It has three layers:

1. **Per-model engines**: C++ processes built for NVIDIA CUDA and AMD HIP (`maya`, still
   called `strata` internally, plus `maya-ds4` and `maya-mm3`), an external vision
   encoder, and two experimental Apple Silicon engines on ggml's Metal backend
   (`maya-metal`, `maya-metal-mm3`). An engine reads GGUF or EXL3 model files and speaks
   a newline-delimited text protocol over stdin and stdout: token ids in, token ids and
   statistics out.
2. **A Python HTTP server** (`serve/`): standard-library `http.server` speaking
   HTTP/1.0, plus `jinja2`. It owns tokenization, chat-template rendering,
   detokenization, stop handling, tool-call parsing, the thinking budget and the loop
   guard. It serves OpenAI Chat Completions, Anthropic Messages, the Responses API, a
   model-management API, MCP tools for the web chat, file attachments, and the
   dashboard's data routes. `serve/` holds 31 non-test Python modules (19,784 lines) and
   44 test files (17,759 lines, 913 test methods) that need no GPU: they drive an
   in-process `MockEngine` and two fake engine scripts.
3. **A no-build dashboard** (`serve/web/`): 37 static files using native ES modules and
   a vendored Preact and htm bundle, about 7,000 lines of JavaScript and CSS. Nothing in
   the repository builds or bundles it.

Around these sit a Python launcher and setup (`maya.py`, 8,373 lines; `setup.py`, 870
lines; and helpers in `tools/`), which download models, build engines and supervise the
server.

Nothing in project-maya is MLX-based. Its model files are GGUF, EXL3 safetensors and its
own pack and profile files.

## Module map and classification

Three classes are used:

- **Adapted**: donor files taken into PulsarMLX with changes. This covers the dashboard's
  JavaScript, CSS, HTML and icon sprite.
- **Reimplemented**: donor behavior written again in Rust, against PulsarMLX contracts in
  `specs/022-console-serving-parity/contracts/`, with the donor as the reference. Some
  reimplemented files are *translated*: Rust tests and test doubles that port donor tests
  or donor fakes closely carry a provenance header (see [Attribution](#attribution)). This
  covers the donor's
  tests, re-expressed in Rust (or as web logic tests) with their expectations kept, and
  the fake engines and fake MCP server, written in Rust from the donor's fakes.
- **Excluded**: not used. Some excluded items are replaced by a PulsarMLX design; the
  deviation ids refer to the register described under
  [Compatibility analysis](#compatibility-analysis).

Milestones (M0 to M10) are those of that plan. Work-package ids are those of
`specs/022-console-serving-parity/tasks.md`.

### `serve/` (server)

| Donor path | Lines | Role in project-maya | Class | Planned PulsarMLX destination |
| --- | ---: | --- | --- | --- |
| `server.py` | 7,456 | HTTP server and routes, engine client and supervisor, `MockEngine`, byte tokenizer, detokenizer, resumable web streams, settings and admin routes | Reimplemented | `console-http`, `console-core`, `console-engine`, `console-tokenizer`, `console-manage` (M1 to M7) |
| `frontend.py` | 1,689 | Request normalization, chat templates, output parsers, tool-call syntaxes, thinking levels | Reimplemented | `console-prompt` (M2) |
| `loop_guard.py` | 701 | Loop detection and breaking | Reimplemented | `console-prompt` (M2) |
| `ds41_encoding.py` | 995 | DeepSeek's own reference prompt encoder, vendored by project-maya without functional changes | Reimplemented (a translation of third-party MIT code; see below) | `console-prompt` (PRM-07, M2) |
| `glm_dsa_product.py`, `glm_dsa_template.py`, `glm_dsa_tune.py` | 351 | GLM-5.3 product facts, thinking-level dialects, per-request engine knobs | Reimplemented | `console-manage`, `console-prompt` (M2, M7) |
| `responses.py`, `response_store.py`, `response_jobs.py`, `response_schema.py`, `response_config.py` | 1,255 | Responses API, store, background jobs, schema validation, limits | Reimplemented; the schema validator is written in-house with no `jsonschema` crate | `console-responses` (M5) |
| `mcp.py` | 669 | MCP client hub (stdio and streamable HTTP) and tool loop | Reimplemented in-house, with no `rmcp` crate | `console-mcp` (M6) |
| `attach.py`, `pdf.py`, `pdf_text.py` | 1,599 | Attachment readers and PDF text | Reimplemented | `console-attach` (M6) |
| `ds4_vision.py` | 186 | DeepSeek picture preprocessor | Reimplemented | `console-media` (M6) |
| `mm3_vision.py` | 175 | MiniMax picture preprocessor, described by the donor as the server's half of the model's `image_processor.py` | **Excluded** (LIC-2); the file format is documented and a MiniMax-vision engine gets a clear error | none |
| `models.py`, `model_api.py`, `model_pull.py`, `savings.py` | 2,238 | Run-config registry and settings, model APIs, pull driver, savings line | Reimplemented; the catalog ships empty (PLAT-3) | `console-manage` (M7) |
| `update.py` | 176 | Release check and self-update by `git fetch` and fast-forward | Route shapes and an opt-in, check-only notifier reimplemented; **self-update excluded** (SEC-5) | `console-manage` (M7) |
| `telemetry.py` | 1,120 | Hardware readers for the Monitor (NVML, AMD sysfs, Windows) | Reimplemented behind traits; NVIDIA, AMD and Windows readers are built last and labeled unverified on real hardware (PLAT-1); an Apple Silicon reader is new PulsarMLX work (PLAT-2) | `console-host` (M4, M9) |
| `gpu_map.py`, `glm_link.py`, `mixed_gpus.py` | 713 | GPU memory map and multi-GPU helpers | Reimplemented behind traits, fixture-tested, unverified on real hardware (PLAT-1) | `console-engine`, `console-host` (the launch specification with GLM link mode in M3; the rest in M9) |
| `glm_dsa_fake_engine.py`, `fake_multi_engine.py` | 288 | Fake engines speaking the line protocol | Reimplemented (translated) as Rust binaries from the donor fakes | `console-fake-engines` (ENG-05, M3) |
| `mcp_fake_server.py` | 172 | Fake MCP server | Reimplemented (translated) as a Rust binary | `console-mcp` test support (RSP-08, M6) |
| `test_*.py` (44 files) | 17,759 | 913 test methods | Reimplemented (translated): re-expressed (29 files as Rust unit tests, 13 as black-box HTTP tests); 2 files are run unchanged through a shim in the manual reference job | `console/parity/ledger.json`, one row per method |
| `chat_template.jinja`, `glm5_chat_template.jinja`, `chat_golden.json` | n/a | Vendor chat templates and golden renders made with them | **Excluded** (LIC-1) | none; see vendor templates below |
| `fixtures/` | n/a | Vendor templates, DeepSeek encoder fixtures, rendered-id fixtures | **Excluded** from the repository, except the five DeepSeek encoder fixture pairs, which PRM-07 commits together with DeepSeek's notice (decided by the lead on 2026-11-14); other vendor material is used only by hash in the manual vendor-template job. | `console-prompt` test data, for the DeepSeek fixture pairs only (PRM-07, M2) |
| `__init__.py` | 1 | Package marker | Not applicable | none |

### `serve/web/` (dashboard)

| Donor path | Role | Class | Planned handling |
| --- | --- | --- | --- |
| `app.js`, `chat-view.js`, `chats.js`, `lib.js`, `md.js`, `sidebar.js`, `state.js`, `ui.js`, `server.js`, `settings.js`, `turbo-core.js`, `turbo.js` | Shell, chat page, browser chat store, Markdown and preview, sidebar, state, UI primitives, server polling, settings, Turbo | Adapted | Upstream file names kept; neutral identity (BRAND-1); hardened output rendering and no inline script (SEC-2); prefill-only `?q=` (SEC-3); storage text corrected (PRIV-1) (M8) |
| `models.js`, `monitor.js` | Models page and Monitor, written around NVIDIA, AMD and multi-GPU concepts | Adapted | Parity routes and an Apple Silicon monitor view in M8; the GPU-era paths are fixture-verified in M9 (PLAT-1, PLAT-2) |
| `preact.js` | Preact 10.29.8 with hooks and htm 3.1.1, pre-bundled by the donor with esbuild | Adapted as a vendored third-party bundle, taken unchanged | Imported in WEB-01 with its SHA-256 recorded; its license texts are added to `console/LICENSES/` in the same change |
| `app.css`, `components.css`, `models.css`, `monitor.css`, `settings.css`, `tokens.css`, `turbo.css` | Styles | Adapted | System font stack replaces Outfit (BRAND-2) |
| `index.html`, `manifest.webmanifest` | Page shell and web-app manifest | Adapted | Neutral name; the manifest lists SVG icons only (BRAND-2); the inline script is removed (SEC-2) |
| `sprite.svg` | Icon sprite: 63 Lucide icons, the donor's own `i-stop`, and the donor's logo mark `i-maya` | Adapted | SVG only; `i-maya` is replaced by a neutral mark (BRAND-1); Lucide's notice travels with it |
| `LICENSE.lucide.txt` | Lucide's ISC notice | Carried as a license text | Added to `console/LICENSES/` in WEB-01 |
| `icon-32.png`, `icon-180.png`, `icon-192.png`, `icon-512.png` | project-maya app icons | **Excluded** (BRAND-1, BRAND-2) | Not committed; no binary file enters the repository |
| `logo-deepseek.svg`, `logo-glm.svg`, `logo-minimax.svg`, `logo-qwen.svg` | Model vendors' marks | **Excluded** (BRAND-2) | Letter tiles per model family |
| `fonts/outfit-latin-wght.woff2`, `fonts/outfit-latin-ext-wght.woff2`, `fonts/OFL.txt` | Outfit font and its license | **Excluded** (BRAND-2) | System font stack; no font file is shipped and the `/fonts/<name>` route answers 404 |

### Outside `serve/`

| Donor path | Class | Note |
| --- | --- | --- |
| `src/`, `include/`, `cmake/`, `CMakeLists.txt`, `third_party/`, `ref/`, `bench/`, `tests/` | **Excluded** | The engines and their build. Launching `maya-metal` or any other project-maya engine binary is out of scope; it would be a donor runtime and needs its own ADR 0004 qualification. |
| `maya.py`, `setup.py`, `setup.sh`, `maya.sh`, `START-MAYA.bat`, `docker/` | **Excluded** | The launcher and setup. Download and restart are replaced by `pulsar-console fetch` and `pulsar-console supervise` with the same progress, exit-code and restart contracts (PLAT-3). |
| `tools/strata_tokenizer.py`, `tools/gguf_reader.py` | Reimplemented | Byte-level BPE tokenizer in the new `console-tokenizer` crate, with no path dependency outside `console/`; GGUF metadata probe in `console-manage` |
| `tools/maya_names.py`, `tools/maya_quants.py` | **Excluded** as identity | Legacy `MAYA_*` and `STRATA_*` names are not accepted as aliases, and Maya quant names are not used (BRAND-1); family classification logic is reimplemented with neutral labels |
| `assets/`, README files, `.github/FUNDING.yml` | **Excluded** | Name, logo, sponsor links and documentation are project-maya's identity |
| Root `LICENSE.qwen-community-1.0`, `LICENSE.minimax-m31`, `LICENSE.deepseek-v41` | See third-party components | Vendor license files |

## Third-party components inside the donor

project-maya's MIT license covers project-maya's own work. The donor also ships material
under other licenses. The ones that matter to the server and dashboard are:

| Component | Where in the donor | License as stated in the donor | What PulsarMLX does |
| --- | --- | --- | --- |
| Preact 10.29.8 (with hooks) | `serve/web/preact.js` | MIT, Copyright (c) 2015-present Jason Miller | The bundle is taken unchanged with a recorded hash in WEB-01, and the MIT text is added to `console/LICENSES/` in that change, to be served from the dashboard's About page. |
| htm 3.1.1 | Same bundle | Apache License 2.0, Copyright 2018 Google Inc. The donor ships only a notice and a URL, not the license text. | The full Apache-2.0 text is added to `console/LICENSES/` in WEB-01. |
| Lucide v1.50.0 icons | `serve/web/sprite.svg` (every symbol except `i-stop` and `i-maya`); notice in `serve/web/LICENSE.lucide.txt` | ISC (Lucide Contributors 2022), with portions from Feather under MIT (Cole Bemis 2013-2022) | Icons kept as SVG; the ISC notice is added to `console/LICENSES/` in WEB-01. |
| llama.cpp pre-tokenizer patterns | Transcribed in `tools/strata_tokenizer.py`, which cites `llama-vocab.cpp` line ranges | MIT (llama.cpp); the donor ships no separate notice for the transcribed patterns | The patterns are transcribed into `console-tokenizer` in PRM-04 with llama.cpp's notice, and its MIT text is added to `console/LICENSES/` in that change. |
| Outfit font | `serve/web/fonts/` | SIL Open Font License 1.1, Copyright 2021 The Outfit Project Authors | **Excluded**: no font file is committed (BRAND-2). |
| lobe-icons 1.98.0 vendor marks | `serve/web/logo-*.svg` (DeepSeek, Z.ai, MiniMax, Qwen) | Each file's one-line comment says MIT; no lobe-icons license text is shipped; the marks belong to the model vendors | **Excluded**: letter tiles per model family (BRAND-2). |
| DeepSeek reference encoder | `serve/ds41_encoding.py`, `serve/fixtures/deepseek_v41/`, root `LICENSE.deepseek-v41` | MIT, Copyright (c) 2023 DeepSeek; vendored from DeepSeek's repository at revision `1bae0e1088993b9b82de08f59de5be5a34e42170` | Translated to Rust in PRM-07 (M2), which also commits the five DeepSeek fixture pairs together with DeepSeek's notice. The Rust module header and `NOTICE.md` will carry DeepSeek's notice and the source revision, and DeepSeek's license text is added to `console/LICENSES/` in that change. |
| Model vendors' chat templates | `serve/chat_template.jinja` (a Qwen-derived template with no license header), `serve/glm5_chat_template.jinja` (Z.ai), `tools/mm3/chat_template.jinja` and `serve/fixtures/minimax_m31/` (MiniMax), `data/glm-dsa/templates/`; root `LICENSE.qwen-community-1.0` and `LICENSE.minimax-m31` | The vendors' own licenses; the MiniMax Community License grants rights for non-commercial purposes and puts conditions on commercial use | **Excluded** (LIC-1). Vendor templates are never committed. A template is loaded from the model directory at run time; when none is configured, start-up fails with a clear error and there is no bundled fallback. Tests use PulsarMLX-authored synthetic templates. Vendor-template checks run only in the manual job and record hashes, not text. |

The engine-side third-party code (`third_party/ggml`, `third_party/exllamav3`,
`third_party/beellama.cpp`) and the launcher's Python wheels (`third_party/wheels`) are
excluded with the engines and the launcher. None of it enters PulsarMLX.

## ADR 0004 requirements

ADR 0004 allows no donor runtime dependency and no copied or adapted implementation
without source and license review, attribution, independent tests, compatibility
analysis, and measured benefit. Each requirement is made concrete here.

### Source and license review

This document is the review. It records the pinned commit, the MIT license with both
copyright lines exactly as they appear in the donor's `LICENSE`, a per-module
classification, and the third-party components with their licenses and dispositions.
The facts above were checked against the pinned checkout. A re-pin repeats the review;
see [PROJECT_MAYA_SYNC.md](PROJECT_MAYA_SYNC.md).

### Attribution

- `NOTICE.md` has a project-maya section naming the repository, the pinned commit, the
  license and both copyright lines.
- `console/LICENSES/project-maya-MIT.txt` holds the full text of the donor's `LICENSE`,
  verbatim, as the MIT license requires for copies and substantial portions.
  `console/LICENSES/README.md` lists what each license file covers. M0 ships the
  project-maya MIT text only. The license text of a third-party component is added in the
  same change that imports the component: the Preact (MIT), htm (Apache-2.0) and Lucide
  (ISC) texts with WEB-01, and DeepSeek's reference encoder notice with PRM-07, which
  commits the five DeepSeek fixture pairs together with that notice (decided by the lead
  on 2026-11-14; reported to the owner at checkpoint 1, who raised no objection).
- Provenance headers follow this rule, decided by the lead on 2026-11-14:
  - A file adapted from the donor (JavaScript, CSS, HTML, SVG) starts with a comment, in
    that file type's comment syntax, of these four lines:

    ```text
    Provenance: adapted from project-maya <donor path> at 7e68a30f (MIT).
    Copyright (c) 2026 Peasant Smith and the Project Maya contributors.
    Copyright (c) 2026 Niko1221 and the Strata contributors.
    License text: console/LICENSES/project-maya-MIT.txt.
    ```

  - A Rust test or test double translated from a donor test or donor fake carries a
    module-level comment:

    ```text
    Provenance: translated from project-maya <donor path>[::Class::method] at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
    ```

  - A Rust module reimplemented from the written contracts carries no donor copyright
    lines. It may cite the donor file and lines as
    `Behavior reference: project-maya <path>:<lines> at 7e68a30f.`
  - Package WEB-01 adds a check that every file under `console/web` either carries a
    `Provenance` line or is listed as PulsarMLX-original.
- project-maya is named only where attribution or provenance requires it. It is never
  PulsarMLX Console's identity: no Maya name, logo or quant name appears in anything the
  console presents as its own (BRAND-1).

### Independent tests

Re-expressed donor tests show parity, but they come from the donor and are not
independent. Independent evidence comes from two sources, both in blocking CI:

- **Contract tests** written from the PulsarMLX contracts in
  `specs/022-console-serving-parity/contracts/`, by a different agent than the one that
  ported the behavior. That agent is told not to read the donor tests.
- **Security tests** salvaged from PulsarMLX's own archived serving crate (tag
  `archive/2026-09-21/feat/openai-serving`, `crates/serve-synthetic`): Host allowlist,
  `Origin`, content-type and token handling, request limits, and its raw-HTTP tests. This
  is PulsarMLX's own code, not donor code. The posture SEC-1 to SEC-7 applies to every
  route from the first HTTP package on.

### Compatibility analysis

- **Deviation register**: `specs/022-console-serving-parity/contracts/deviations.md`
  lists every intended difference from project-maya, each with a reason and its approval
  basis. Approving that plan approved SEC-1 to SEC-7, PRIV-1, BRAND-1, BRAND-2, LIC-1,
  LIC-2, POL-1, PLAT-1 to PLAT-3 and FIX-1. The register also holds PLAN-1 to PLAN-6,
  differences that plan decides outside its deviation table, each citing the plan section
  that decides it: the synthetic badge and health report (PLAN-1, plan section 7,
  item 5), a synthetic default model name (PLAN-2, section 12; the owner settled it as
  exactly `pulsar-console-synthetic` on 2026-11-14, OPEN-03), embedded assets with no
  filesystem path served (PLAN-3, section 6), license notices reachable from the About
  page (PLAN-4, section 7, item 4), the always-available schema validator (PLAN-5,
  section 6), and HTTPS MCP through the `curl` facade (PLAN-6, section 6). Any further
  deviation needs the owner's approval. On 2026-11-14 the owner approved the proposals
  P-1 to P-4, P-6 to P-11 and P-13 to P-16, which are now approved deviations under their
  `P-` ids; declined P-12 and P-17, which keep their ids marked declined; and deferred
  P-5 and P-18, which stay unapproved in the register's section "Deferred, awaiting owner decision" (OPEN-15). A later
  approved deviation that was never a listed proposal takes the next free `P-` number,
  and no id is reused (OPEN-39, settled by the lead on 2026-11-14).
- **Parity ledger**: `console/parity/ledger.json` has one row per donor test method (913
  rows at this pin). Each row resolves to exactly one disposition: `rust-test`,
  `scenario`, `web-test`, `shim`, `vendor-render`, `deviation`, `not-applicable` (with a
  reason from a closed list) or `pending` (see
  `specs/022-console-serving-parity/contracts/parity-ledger.md`, section 3.2). The
  `shim` and `vendor-render` rows run only in the manual reference job; blocking CI
  checks their committed record. A checker fails the build on a dangling row.
- **Reference corpus**: requests, responses, streams and rendered-prompt probes captured
  from project-maya's own server in fake-engine mode at the pinned commit, normalized and
  committed as text with a provenance header. Capture runs only in the manual GitHub
  Actions job; replay against the Rust server runs offline in every CI run.

### Measured benefit

No measurement exists yet.

**Pre-adoption estimate.** This paragraph is an estimate from the planning analysis of
2026-11-14 (not published in this repository), not a measurement. What is adapted is the
dashboard. At the pinned commit `serve/web/` holds 37 files; counted with `wc -l` for this
record, the files to be adapted are 14 hand-written JavaScript modules (5,489 lines), 7
CSS files (1,477 lines), the HTML shell (37 lines), the manifest (11 lines) and the icon
sprite (69 lines): 7,083 lines in 24 files, plus the vendored Preact and htm bundle (32
lines), which is taken unchanged. The planning analysis of the dashboard estimated the
adaptation edits at about 400 lines of JavaScript and CSS across 20 files. For writing an
equivalent front end from scratch, the same planning analysis gives no line count of its
own: it states that all 5,489 lines of JavaScript would have to be re-expressed (the CSS
could be kept only if its class names were reproduced), that a WebAssembly toolchain and
a build step would be added where the donor has none, and that the donor's Node
page-logic tests would be lost as an oracle; the corresponding Phase 2 rewrite packages
were left unsized. On that estimate, adapting reuses about 7,000 lines for about 400
lines of edits, where a rewrite would re-express at least the 5,489 lines of JavaScript.

The measured figures are recorded at close-out (M10). The parity report will state:

- **Adapted lines against a clean-rewrite estimate**: the number of lines in `console/`
  that derive from donor files (identified by their provenance headers), set against an
  estimate of the lines a clean rewrite of the same surface would need.
- **Feature coverage on a named checklist**: the share of the items on one named feature
  checklist that the console covers on synthetic backends, together with the ledger
  counts (matched, deviation, not applicable, none pending). Which checklist is named is
  open item OPEN-57.

This order differs from ADR 0004, which names measured benefit among the conditions to
meet before donor code is copied or adapted. Here an estimate precedes adoption, which
starts in M1 (translated donor tests) and M8 (the dashboard, WEB-01), and the measurement
follows at close-out. The feature plan records this ordering as constitution exception E6
in [`plan.md`](../../specs/022-console-serving-parity/plan.md#constitution-exceptions),
and the owner accepted it on 2026-11-14, settling open item OPEN-27. The pre-adoption
estimate above stays the record until the close-out measurement; which checklist that
measurement uses is still open (OPEN-57).

## Important differences

- **Hardware and model formats.** project-maya's engines target NVIDIA and AMD GPUs and
  read GGUF and EXL3 files; its Apple Silicon engines are experimental and run on ggml's
  Metal backend, not MLX. PulsarMLX targets Apple Silicon and MLX. Only the serving layer
  and dashboard are taken, behind a backend seam the PulsarMLX native engine can attach
  to later, in a separately approved phase.
- **Synthetic backends only.** In this increment the console is driven by a scripted
  in-process engine, a line-protocol client and Rust fake engine binaries. Nothing serves
  a real model. The dashboard shows a permanent "Synthetic engine: no real model" badge
  and `/health` reports it.
- **Security posture.** PulsarMLX does not copy project-maya where it is weaker: Host
  allowlist and `Origin` checks on every route (SEC-1), strict security headers and a
  sandboxed preview (SEC-2), no auto-send from a link (SEC-3), opt-in remote image URLs
  and local image paths (SEC-4), no self-update and an opt-in release check (SEC-5),
  internal parser state unreachable from client input (SEC-6), and no environment
  override of the download command (SEC-7). Outbound network goes through one facade
  over the system `curl`.
- **Not built in this increment.** The MiniMax picture preprocessor (LIC-2), the
  refusal-ablation switch and its config keys (POL-1: the capability flag is recognized
  and refused unless an engine advertises it), self-update (SEC-5), any real model
  catalog entry (the catalog ships empty), and launching any project-maya engine binary.
- **No donor benchmark is PulsarMLX evidence.** project-maya's speed and quality figures
  are user-reported measurements on NVIDIA and AMD hosts with its own models. They say
  nothing about PulsarMLX and are never cited as PulsarMLX results.
- **No endorsement.** project-maya's authors and contributors, and the Strata authors and
  contributors, do not endorse PulsarMLX and are not responsible for its modifications,
  behavior, support, or releases.

## Open items

These are not decided by that plan. Each needs a decision before the work package that
depends on it. The register of every open item for this feature, with who decides each
one, is `specs/022-console-serving-parity/checklists/analysis.md`; the ids below are its
ids.

1. **OPEN-57, coverage checklist.** Which feature checklist the close-out coverage figure
   uses. A candidate is the feature list in the donor `README.md` at the pin (its
   browser, API, thinking, loop-guard, pictures, files and MCP items); this is a
   suggestion, not a decision.
2. **OPEN-49, `preact.js` provenance.** Whether the donor's pre-built bundle is accepted
   on its recorded hash, or checked once against the upstream Preact 10.29.8 and htm
   3.1.1 releases.

The benefit ordering (OPEN-27) is decided: the owner accepted on 2026-11-14 that an
estimate precedes adoption and the measurement follows at close-out (see
[Measured benefit](#measured-benefit)).
The provenance header format and the timing of third-party license texts are decided
(see [Attribution](#attribution)).
Where the two donor test files run through a shim is decided: they and the
vendor-template renders run only in the manual reference job, and blocking CI checks
their committed record (`specs/022-console-serving-parity/contracts/parity-ledger.md`,
section 3.2).

See also [PROJECT_MAYA_SYNC.md](PROJECT_MAYA_SYNC.md) and the "Donor: project-maya"
section of [`NOTICE.md`](../../NOTICE.md).
