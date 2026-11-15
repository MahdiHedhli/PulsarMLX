# Deviation Register

- **Status**: Register of record, dated 2026-11-14. Every SEC, PRIV, BRAND, LIC, POL,
  PLAT, FIX and PLAN id below was approved by the owner with the plan on 2026-11-14. The
  SEC, PRIV, BRAND, LIC, POL, PLAT and FIX ids come from plan section 4, "Deviations from
  literal parity that need your approval"; the PLAN-1 to PLAN-6 ids register differences
  that other plan sections decide, and each cites its section. On 2026-11-14, at owner
  checkpoint 1, the owner approved proposals
  P-1 to P-4, P-6 to P-11 and P-13 to P-16 (registered below under their P- ids, in
  "Approved proposals"), declined P-12 and P-17, deferred P-5 and P-18, and settled the
  open values of SEC-1.1 and PLAN-2. The "PulsarMLX Console does" lines describe planned
  behavior unless an entry carries an implementation note that names the package and the
  commit that built it.
- **Feature**: `specs/022-console-serving-parity`
- **Written by**: GOV-06. Each implementing package adds its tests to the "Affected donor
  tests" lines and its ledger rows cite the id or sub-item id
  ([parity-ledger.md](parity-ledger.md)).
- **Donor**: project-maya at commit `7e68a30f2f208056195352129188661fb6b94445` (v1.1.63).
  Donor locations such as `serve/server.py:6141` are paths and lines in that tree.
- **Terms**: "Decision B1" to "decision B13" are the binding cross-cutting decisions
  restated in [`../tasks.md`](../tasks.md), section "Binding cross-cutting decisions". A
  "planner" is one of the per-area design proposals (API, ENG, PRM, RSP, OPS, WEB and
  conformance) written before the plan was approved; those records are not in the
  repository, and nothing they propose is approved unless an id below covers it.
- **Open items**: every open item in this register is also listed, with a stable
  `OPEN-nn` id and who decides it, in the register of open items,
  [`../checklists/analysis.md`](../checklists/analysis.md).

## How to read this register

Parity means PulsarMLX Console behaves like project-maya `serve/` at the pinned commit
(plan section 4). Each entry here is a place where it deliberately does not. An entry has:
what the donor does, what PulsarMLX Console does, why, the approval, the donor tests known
to be affected, and the packages that implement it.

Sub-items are numbered `<id>.<n>`, such as `SEC-1.1`. A sub-item lists a concrete
difference the planners identified that falls under the approved id. Where a sub-item gives
an exact value (a header list, a file name, a setting name) that the plan itself does not
fix, the value is marked "proposed": the deviation is approved, and the exact value is
settled by the implementing package and reviewed.

"Affected donor tests" are the methods known so far whose assertions meet the deviation.
They were found by reading the planner records and by a text search of the pinned donor
tests; the implementing package confirms each one, and its ledger row then takes the
`deviation` disposition or stays a `rust-test` if the assertion still holds.

Rules:

1. No deviation exists without an entry here. A comparator annotation or ledger row that
   names an id not in this register fails the ledger checker.
2. A planner proposal becomes a deviation only when the owner approves it. Approved
   proposals are registered under their P- ids in the section "Approved proposals".
   Proposals still awaiting a decision are listed under "Deferred, awaiting owner
   decision" and are **not** approved. Declined proposals are kept, marked declined, in
   "Declined proposals", so their ids are never reused. A ledger row or comparator
   annotation that names a deferred or declined P- id fails the ledger checker.
3. An entry that no ledger row and no comparator annotation uses is flagged by the
   checker as unused.
4. Numbering (decided by the lead on 2026-11-14; this settles OPEN-39): an owner-approved
   proposal keeps its P-n id as its deviation id; a later owner-approved deviation that
   was never a listed proposal takes the next free P- number; ids are never reused; a
   declined proposal keeps its id, marked declined.

## Index

| Id | Short title | Packages |
| --- | --- | --- |
| [SEC-1](#sec-1) | Host allowlist, Origin on every route, JSON content type, gated admin routes | API-02, API-03, API-15, OPS-23, CNF-14 |
| [SEC-2](#sec-2) | Security headers, HTML sanitizer, sandboxed preview route | WEB-02, WEB-03, WEB-06 |
| [SEC-3](#sec-3) | `/?q=` prefills, never sends | WEB-03, WEB-06 |
| [SEC-4](#sec-4) | Remote image URLs and local image paths are opt-in | RSP-17, RSP-18, RSP-16 |
| [SEC-5](#sec-5) | No self-update; opt-in, notify-only release check | OPS-22, OPS-11, WEB-09 |
| [SEC-6](#sec-6) | Client keys starting with `_` stripped; internal flags typed | API-04, PRM-11, ENG-03 |
| [SEC-7](#sec-7) | No environment override of the download command; wider engine-env denylist | OPS-15, OPS-05, ENG-15 |
| [PRIV-1](#priv-1) | Resume kept in memory; disk persistence off by default; truthful settings text | API-10, WEB-10 |
| [BRAND-1](#brand-1) | Product name, binary, prefix, storage keys, log prefix, neutral quant labels | all packages; API-15, OPS-02, WEB-01 lead |
| [BRAND-2](#brand-2) | Letter tiles, system font stack, SVG icons only | WEB-01 |
| [LIC-1](#lic-1) | Vendor chat templates never committed; load at run time | PRM-02, PRM-03, PRM-08, CNF-11 |
| [LIC-2](#lic-2) | MiniMax picture preprocessor not built | RSP-19, RSP-17 |
| [POL-1](#pol-1) | Refusal-ablation switch not ported; capability flag refused | API-04, OPS-05, WEB-09 |
| [PLAT-1](#plat-1) | Hardware and OS ports behind traits, fixture-tested, unverified on real hardware, built last | OPS-19, OPS-20, ENG-13, ENG-16, API-18, WEB-08, CNF-16, ENG-08, ENG-14, ENG-15, RSP-18, OPS-07 |
| [PLAT-2](#plat-2) | Apple Silicon reader and monitor view | OPS-17, OPS-18, WEB-07 |
| [PLAT-3](#plat-3) | `pulsar-console fetch` and `supervise`; empty catalog | OPS-11, OPS-14, OPS-15, OPS-16 |
| [FIX-1](#fix-1) | Three upstream defects fixed | ENG-06, ENG-07, ENG-08, ENG-12 |
| [PLAN-1](#plan-1) | Permanent synthetic badge; `/health` reports the synthetic backend; an engine that is not synthetic is refused at start | API-06, WEB-07, ENG-01, ENG-10, API-08 |
| [PLAN-2](#plan-2) | Scripted engine's default model name is `pulsar-console-synthetic` | ENG-02, API-08, API-17 |
| [PLAN-3](#plan-3) | Embedded dashboard assets; no filesystem path served | WEB-02 |
| [PLAN-4](#plan-4) | License notices reachable from the About page | WEB-01 |
| [PLAN-5](#plan-5) | In-house schema validator, always available | RSP-02 |
| [PLAN-6](#plan-6) | HTTPS MCP servers through the outbound `curl` facade | RSP-10 |
| [P-1](#p-1) | `Server: pulsar-console/<version>` | API-02 |
| [P-2](#p-2) | 400 for both `Content-Length` and chunked `Transfer-Encoding` | API-02 |
| [P-3](#p-3) | `malformed request (` prefix kept, Rust-side detail text | API-01, API-07, PRM-06 |
| [P-4](#p-4) | Reader error prefixes kept, Rust-side parenthesized detail | RSP-12, RSP-18, RSP-19 |
| [P-6](#p-6) | Optional engine ready timeout, off by default | ENG-06 |
| [P-7](#p-7) | Whitespace-free base for the vision temporary directory, checked at start | ENG-14, RSP-18, RSP-19 |
| [P-8](#p-8) | Template `raise_exception` and DeepSeek encoder assertion failures answer 400 | PRM-03, PRM-07, PRM-08, API-07 |
| [P-9](#p-9) | Backend label table on Models cards | WEB-08 |
| [P-10](#p-10) | Frozen-engine watchdog needs a GPU-busy signal on macOS; native samplers | ENG-08, OPS-17 |
| [P-11](#p-11) | Strong `ETag`s, 304 responses and `HEAD` for dashboard assets | WEB-02 |
| [P-13](#p-13) | `window.console_debug` only with `#debug` in the address | WEB-03 |
| [P-14](#p-14) | `details.format` reports `safetensors` for PulsarMLX MLX checkpoints | OPS-12 |
| [P-15](#p-15) | MLX checkpoint configurations listed with `ok: false` | OPS-03, OPS-16 |
| [P-16](#p-16) | Catalog revision `main` refused | OPS-14 |

---

## SEC-1

**`Host` allowlist (loopback binds, and any bind where `allowed_hosts` is set); `Origin`
checked on every route; JSON content type on POST; mutating admin routes need loopback or
a key.**

- **project-maya does.** It compares `Origin` with `Host` on some routes only and has no
  `Host` allowlist. `_foreign_page` refuses a browser `Origin` that is neither this server
  nor listed in `cors_origins` (`serve/server.py:6141-6150`); `_own_page` requires
  `application/json` and a same-host `Origin`, but only on the dashboard's mutating routes
  (`serve/server.py:6327-6338`). Both compare against the request's own `Host` header, so
  under DNS rebinding both carry the attacker's name and match. Only pull, delete and swap
  are loopback-gated; other mutating ops routes are open to any client that omits `Origin`
  when no API key is set (OPS planner).
- **PulsarMLX Console does.** It enforces the posture below on every route from the first
  HTTP package on, taking the archived serving crate (tag
  `archive/2026-09-21/feat/openai-serving`, `crates/serve-synthetic`) as the reference for
  `Host`, `Origin`, content-type and token handling and for its raw-HTTP tests
  (decision B8).
- **Why.** DNS rebinding, and cross-site requests from any page the user visits, could
  otherwise change settings, move the port or run MCP tools with the user's rights.
  PulsarMLX's own earlier serving work already held this posture.
- **Approval.** Approved by the owner with the plan on 2026-11-14. The values of sub-item
  SEC-1.1 (the `Host` rule on loopback and non-loopback binds and the `allowed_hosts`
  key) were decided by the owner on 2026-11-14 at checkpoint 1 (OPEN-04).
- **Affected donor tests (known).** `serve/test_server.py::CorsOptIn::*` (8 methods),
  `serve/test_server.py::SharedSettings::test_only_strata_s_own_page_may_set_them`,
  `serve/test_mcp.py::ToolLoop::test_only_from_the_app_s_own_page`,
  `serve/test_attach.py::Route::test_foreign_page_refused`,
  `serve/test_dashboard.py::Dashboard::test_out_of_range_and_foreign_pages_are_refused`,
  `serve/test_dashboard.py::Port::test_refused_with_nothing_saved`,
  `serve/test_models.py::Page::test_refused`, `serve/test_models.py::DeletePage::*`,
  `serve/test_savings.py::Page::*`,
  `serve/test_responses.py::Responses::test_auth_cors_capabilities_and_reload`. Many of
  these will keep passing as written; each is confirmed by its package.
- **Implementation (SEC-1.1, reading the key only).** API-15 (commit `9671312a`,
  2026-11-15) reads the optional run-config key `allowed_hosts` in `console-core::config`:
  `RunConfig::allowed_hosts` and `ServerSettings::allowed_hosts` give no list when the key
  is absent or null, keep a list of non-blank strings with each entry stripped, and stop
  start-up with `ALLOWED_HOSTS_MESSAGE` for any other value. The tests
  `console-core::api15_settings::allowed_hosts_is_absent_by_default_and_read_as_a_list` and
  `console-core::config::document::tests::allowed_hosts_absent_by_default` pin it. Nothing
  enforces the list yet: the guard is API-03's and is not built, and API-08 wires the list
  into it.
- **Packages.** API-02, API-03 (guards; enforces the `allowed_hosts` list), API-15 (reads
  the optional run-config key `allowed_hosts`), OPS-23 (ops route guards), CNF-14
  (independent security tests).

| Sub-item | Difference |
| --- | --- |
| SEC-1.1 | Decided by the owner on 2026-11-14 (OPEN-04). On a loopback bind, a request is accepted only if its `Host` is a loopback name (`localhost`, `127.0.0.1`, `[::1]`, any port) or a name listed in the optional run-config key `allowed_hosts`. The key is absent by default, so by default only loopback names pass. On a non-loopback bind, `Host` is not restricted, as in the donor, unless `allowed_hosts` is set; when it is set, only the listed names and the loopback names pass. A refused request gets 403 `permission_error`. The key name `allowed_hosts` is decided. Matching details (case, port, IPv6 forms, a missing `Host` header) follow the archived serving crate (decision B8) and are settled by API-03. The lead confirms with the owner at checkpoint 2 that `allowed_hosts` also extends the list on a loopback bind, as this text states (lead note LD30). |
| SEC-1.2 | `Origin` is checked on every route, not only on the routes that call `_foreign_page` or `_own_page`. `Origin: null` is treated as a foreign origin. |
| SEC-1.3 | Every POST requires a JSON content type, not only the dashboard's mutating routes (donor `_own_page`, `serve/server.py:6331-6333`, answers 415 "send application/json"). |
| SEC-1.4 | Every mutating admin and ops route is accepted only from a loopback peer or with a valid API key, not only pull, delete and swap. The OPS planner lists settings, engine environment, switch, Turbo, savings reset and update among the routes this adds. |
| SEC-1.5 | API-key handling follows the archived crate (decision B8). The donor already compares keys in constant time with `hmac.compare_digest` (`serve/server.py:5811-5819`); any observable difference the porting package finds is recorded here as a new sub-item before it ships. |

## SEC-2

**Strict Content-Security-Policy and related headers; a sanitizer on every HTML sink;
HTML preview in its own sandboxed route with network off unless allowed per preview.**

- **project-maya does.** It sends no security headers. Model output reaches `innerHTML`,
  with safety resting on `md.js` escaping before formatting. The HTML preview of
  model-written code runs in a `srcdoc` frame that inherits the page and may load anything
  from the internet (WEB planner).
- **PulsarMLX Console does.** It sends a strict policy and related headers on dashboard
  responses, sanitizes every HTML sink, and serves the preview from a dedicated route with
  its own policy, where network access is off unless the user allows it for that preview.
- **Why.** Model output must not be able to call the server or the internet. The stored
  API key and the model-deleting and tool-running routes make script injection costly.
- **Approval.** Approved by the owner with the plan on 2026-11-14.
- **Affected donor tests (known).** None identified that assert the absence of headers.
  `serve/test_server.py::WebApp::*` checks static serving and is confirmed by WEB-02.
- **Packages.** WEB-02 (headers), WEB-03 (CSP compatibility, sanitizer, preview route),
  WEB-06 (browser end-to-end checks).

| Sub-item | Difference |
| --- | --- |
| SEC-2.1 | A strict `Content-Security-Policy` and related headers. Proposed set (WEB planner): `script-src 'self'`, `style-src 'self'`, `connect-src 'self'` plus the validated host with a port wildcard for the port-move probe, `frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy`. |
| SEC-2.2 | The inline theme script, sprite inline styles and the `noscript` inline style move to files and classes so the policy needs no `unsafe-inline`. The rendered page is meant to look the same. |
| SEC-2.3 | An allowlist sanitizer runs on every HTML-string sink, with a Trusted Types default policy where the browser supports it. For ordinary model output `md.js` emits the same HTML as the donor, checked against a golden corpus. |
| SEC-2.4 | The HTML preview runs in a frame loaded from a dedicated preview route with its own policy and the donor's sandbox flags without same-origin; code is delivered by one `postMessage`. Network is off by default; an explicit per-preview control allows it for that preview only. |

## SEC-3

**`/?q=<text>` prefills the composer; sending needs a keypress.**

- **project-maya does.** Opening `/?q=<text>` starts a chat with that text immediately
  (`serve/web/app.js:109-110`, `:119-122`), with server-side MCP tools enabled if the
  user's switch is on.
- **PulsarMLX Console does.** It prefills the composer, strips the query from the address
  as the donor does, focuses the composer and shows a hint that Enter sends. Nothing is
  sent and no tool runs without the user's keypress.
- **Why.** A link from any website should not be able to trigger tool calls with the
  user's rights.
- **Approval.** Approved by the owner with the plan on 2026-11-14.
- **Affected donor tests (known).**
  `serve/test_server.py::WebApp::test_home_screen_start_url`
  (candidate).
- **Packages.** WEB-03, WEB-06.

| Sub-item | Difference |
| --- | --- |
| SEC-3.1 | `/?q=` fills the composer and does not send. |

## SEC-4

**`data:` URLs always; remote image URLs and local image paths only when enabled in
settings.**

- **project-maya does.** `Vision.load` accepts a `data:` URL, fetches any `http(s)` URL
  with a 60-second timeout, and reads any `file://` URL or bare local path that exists
  (`serve/server.py:1819-1830`). Video sources follow the same pattern (RSP planner).
- **PulsarMLX Console does.** It always accepts `data:` URLs. Remote URLs and local paths
  are refused by default with a 400 that names the setting, and are accepted only when the
  setting enables them (decision B7: remote and local sources are opt-in). When enabled,
  remote fetches go through the single outbound facade over the system `curl`, with the
  donor's 60-second timeout.
- **Why.** Arbitrary file read and server-side request forgery on behalf of any caller who
  can reach the port.
- **Approval.** Approved by the owner with the plan on 2026-11-14.
- **Affected donor tests (known).** Tests that pass picture sources as remote URLs or local
  paths; candidates from a text search include
  `serve/test_ds41_conformance.py::Images::test_anthropic_nested_tool_images_preserve_source_types_and_order`
  and `serve/test_tool_videos.py::VideoGuards::*`. Confirmed by RSP-17.
- **Packages.** RSP-17 (sources and policy), RSP-18 (video), RSP-16 (file parts).

| Sub-item | Difference |
| --- | --- |
| SEC-4.1 | `data:` URLs are always accepted. |
| SEC-4.2 | `http(s)` picture and video URLs are refused unless enabled. The RSP planner proposed a setting shaped like `media_sources: ["data", "http", "file"]`; the name and shape are proposed (OPEN-18). |
| SEC-4.3 | `file://` URLs and bare local paths are refused unless enabled. |
| SEC-4.4 | When remote fetches are enabled they use the outbound `curl` facade (decision B7) and the product's own `User-Agent` (BRAND-1.6) instead of `maya`. |

## SEC-5

**Route shapes kept; the server never fetches or runs code; the release check is opt-in
and only notifies.**

- **project-maya does.** `POST /api/update` fast-forwards its own git checkout to a tag
  from its `origin` remote and exits with code 75 so its launcher restarts it, compiling
  the new code, with no signature or checksum check (`serve/update.py:18-24`,
  `:140-176`). The release check queries project-maya's release feed on dashboard load at
  most every six hours unless `MAYA_UPDATE_CHECK=0` (`serve/update.py:4`, `:74-75`).
- **PulsarMLX Console does.** It keeps the route shapes. The check is off unless enabled,
  makes no request on dashboard load, and only reports. `POST /api/update` never updates
  anything. Self-update is not built in this increment (decision B10: route shapes only).
- **Why.** An unsigned, self-modifying update aimed at project-maya's release feed. A
  compiled binary also cannot update itself by moving a source checkout.
- **Approval.** Approved by the owner with the plan on 2026-11-14.
- **Affected donor tests (known).** `serve/test_update.py` (10 methods): the five
  `Updating::*` methods assert git and exit behavior that is not built;
  `Pieces::test_check_off` and `Pieces::test_github_unreachable_is_said_and_retried_later`
  meet the opt-in change; the remaining `Pieces::*` methods (versions, summary, newer) are
  expected to keep passing.
- **Packages.** OPS-22 (update contract), OPS-11 (the supervisor still understands exit
  75), WEB-09 (update card).

| Sub-item | Difference |
| --- | --- |
| SEC-5.1 | `GET /api/update` and the `POST /api/update` error forms keep the donor's shapes. |
| SEC-5.2 | No git command, no code execution and no exit 75 from the server. `can_update` is always false and `POST /api/update` always answers 400; the blocker text tells the user how to update by hand (OPS planner). |
| SEC-5.3 | The release check is opt-in, off by default, never runs on dashboard load, and only notifies. Its environment name is `PULSAR_CONSOLE_UPDATE_CHECK` ([naming.md](naming.md)). |
| SEC-5.4 | The check does not query project-maya's release feed. Which feed it queries, if any, is fixed by OPS-22 (the OPS planner proposed a compile-time PulsarMLX releases URL and a generic `User-Agent`). |

## SEC-6

**Client JSON keys starting with `_` are stripped at the API boundary; internal flags are
typed and never read from client input.**

- **project-maya does.** It passes the request dictionary through as the sampling
  dictionary and strips only `_restore` (`serve/server.py:4424-4431`). Internal markers
  such as `_prefill`, `_think_budget`, `_think_end`, `_think_soft`, `_think_stops`,
  `_responses`, `_blocked`, `_think_max` and `_think_resume` travel in the same dictionary
  (`serve/server.py:1218-1225` reads some of them for the engine line), so a client can
  inject them; a client `_prefill` can reach the output parser as answer text (API and
  PRM planners).
- **PulsarMLX Console does.** It removes every top-level client key beginning with `_` at
  the dialect boundary. Internal flags live in typed structures that are never filled from
  client JSON ([backend-seam.md](backend-seam.md), section 6).
- **Why.** A client could otherwise inject parser and engine state.
- **Approval.** Approved by the owner with the plan on 2026-11-14.
- **Affected donor tests (known).**
  `serve/test_ds4_restore_points.py::RestorePoints::test_off_with_0_and_never_the_clients_own`
  already asserts that a forged `_restore` is ignored and should keep passing. Tests that
  read internal keys from the recorded sampling dictionary (for example
  `serve/test_server.py::ThinkingBudget::*`,
  `serve/test_server.py::ThinkingBudgetAtASentenceEnd::*`) are re-expressed against the
  typed fields.
- **Implementation.** API-04 (commit `89d40258`, 2026-11-15) implements SEC-6.1 in
  `console_core::request::strip_internal_keys`, which removes every top-level client key
  that starts with `_`; `console_core::sampling::effective_sampling` strips them again as a
  second layer. The donor's `_level_shared` marker is the typed field
  `InternalFlags::level_shared` (SEC-6.2). The tests
  `console-core::request::tests::underscore_keys_are_stripped_at_the_boundary` and
  `console-core::api04_request::underscore_keys_never_reach_the_checks` pin the stripping.
  No entry point calls `strip_internal_keys` yet: the boundary strip belongs to the dialect
  handlers (API-07, API-08 and the Responses packages).
- **Packages.** API-04 (request boundary), PRM-11 (prompt-side flags), ENG-03 (typed
  engine parameters).

| Sub-item | Difference |
| --- | --- |
| SEC-6.1 | Top-level client keys beginning with `_` are removed before any processing. |
| SEC-6.2 | `_prefill`, `_blocked`, `_think_max`, `_think_resume`, `_responses` and `_restore` are typed internal fields. |
| SEC-6.3 | The engine-line thinking keys (`_think_budget`, `_think_end`, `_think_soft`, `_think_stops`) are typed fields of the generation request. |

## SEC-7

**No environment override of the download command; a wider denylist for library and
executable variables.**

- **project-maya does.** `MAYA_PULL_COMMAND` (a JSON argument list) replaces the model
  download command in any build (`serve/server.py:3115-3121`). The Models page may write
  any engine environment variable except names matching
  `LD_*`, `DYLD_*`, `PYTHON*`, `PATH`, `PATHEXT`, `BASH_ENV`, `ENV`, `IFS`, `COMSPEC`,
  `SYSTEMROOT` (`serve/models.py:54`), so engine variables that name programs or files
  (for example `MAYA_GLM_HELPER_EXE`) are accepted.
- **PulsarMLX Console does.** The download command is fixed; tests inject a command only
  through a constructor. The denylist is wider.
- **Why.** Arbitrary command or library injection.
- **Approval.** Approved by the owner with the plan on 2026-11-14.
- **Affected donor tests (known).** `serve/test_model_api.py::Pull` (its `hook()` helper
  sets `MAYA_PULL_COMMAND`, `serve/test_model_api.py:226-229`);
  `serve/test_models.py::Settings::test_loader_variables_not_from_the_page` (extended
  with new refusal cases).
- **Packages.** OPS-15 (pull driver), OPS-05 (engine-settings profiles), ENG-15 (engine
  launch specification).

| Sub-item | Difference |
| --- | --- |
| SEC-7.1 | No environment variable replaces the download command; release builds always use the built-in command (`pulsar-console fetch`, PLAT-3.1). |
| SEC-7.2 | The engine-environment denylist adds, as proposed by the OPS planner: further `DYLD_*` and `LD_*` variants, names ending in `_EXE`, `_LIB`, `_LIBRARY_PATH` or `_PATH`, and PulsarMLX Console's own `PULSAR_CONSOLE_*` variables. Other free-form engine variables stay editable. |

## PRIV-1

**Resume kept in memory; disk persistence off by default; the settings text states what is
stored.**

- **project-maya does.** The Settings page says chats stay in the browser and "The server
  keeps none of them" (`serve/web/settings.js:306`). In fact every web-chat answer is sent
  with `strata_resume: true` (`serve/web/chats.js:435`), and the server keeps that answer's
  stream in memory and, when started with a run config, in `answers/<id>.jsonl` beside the
  config for 24 hours after it ends, at most 32 finished answers
  (`serve/server.py:5126-5140`, `:7348`).
- **PulsarMLX Console does.** It keeps resumable answers in memory. Writing them to disk is
  off by default. The settings text states what the server stores and for how long.
- **Why.** The donor's statement is untrue.
- **Approval.** Approved by the owner with the plan on 2026-11-14.
- **Affected donor tests (known).** `serve/test_stream_jobs.py::StreamJobFiles::*` and
  other methods that expect files under `answers/` by default; confirmed by API-10.
- **Packages.** API-10 (resumable streams), WEB-10 (settings text).

| Sub-item | Difference |
| --- | --- |
| PRIV-1.1 | Resumable answers are kept in memory with the donor's retention rules. |
| PRIV-1.2 | `answers/<id>.jsonl` is written only when disk persistence is enabled; the setting's name is to be fixed by API-10 and recorded in [naming.md](naming.md); whether the opt-in exists at all, and its retention, are open (OPEN-19). |
| PRIV-1.3 | The "Data and privacy" text states the actual retention, and that chats themselves live in the browser. |

## BRAND-1

**Product name "PulsarMLX Console", binary `pulsar-console`, prefix `PULSAR_CONSOLE_*`,
neutral quant labels, no sponsor links; a published old-to-new table; legacy names are not
accepted.**

- **project-maya does.** It presents the Maya name, logo, icons, quant names and sponsor
  links; uses `MAYA_*` environment variables with `STRATA_*` fallbacks
  (`tools/maya_names.py`); stores browser data under `maya.` keys and an IndexedDB
  database `maya` (`serve/web/lib.js:28-47`); prefixes logs with `[maya]`; names files
  `maya-*.json` and `.maya-*.json` (`serve/models.py:32-33`, `:682`).
- **PulsarMLX Console does.** It uses its own identity throughout, as listed in
  [naming.md](naming.md), and does not accept the legacy names. Wire names `strata_*` and
  `/v1/strata/*` are kept unchanged: they are not Maya's name and the dashboard depends on
  them (decision B2).
- **Why.** The owner's branding.
- **Approval.** Approved by the owner with the plan on 2026-11-14.
- **Affected donor tests (known).** Every test that asserts a Maya-named string, variable,
  key or file. Examples:
  `serve/test_dashboard.py::PageLogic::test_about_has_the_support_line_always_and_the_update_card_none`,
  `serve/test_responses_tools.py::ToolContracts::test_codex_encrypted_reasoning_round_trip`
  (the `maya-r1:` prefix), tests of quant labels such as `Maya-XS` in
  `serve/test_models.py` and `serve/test_glm_dsa_think_budget.py`, and tests that set
  `MAYA_*` variables. Each package re-expresses them against the new names; the comparator
  applies the rename map to the reference corpus.
- **Packages.** Every package that ports a name; API-15 and OPS-02 (settings), WEB-01
  (dashboard identity), CNF-02 (rename map).

| Sub-item | Difference |
| --- | --- |
| BRAND-1.1 | Product name "PulsarMLX Console" and binary `pulsar-console`. User-facing text that names Maya, Project Maya, `./maya.sh`, `START-MAYA.bat` or "a pack Maya built" is reworded with the same meaning (for example `serve/server.py:6336`, `:2496`; the `/api/report` version line; Settings and About copy). |
| BRAND-1.2 | Environment variables use `PULSAR_CONSOLE_`; `MAYA_*` and `STRATA_*` are not accepted. Engine passthrough names inside a run config's `env` block pass verbatim. |
| BRAND-1.3 | Run-config files `pulsar-<name>.json`; note files `.pulsar-*`; temporary directory prefixes renamed. |
| BRAND-1.4 | Browser storage prefix `pulsar.`; IndexedDB database `pulsar-console`; the legacy `strata.` read fallback and the old-key cleanups are not carried over. |
| BRAND-1.5 | Log prefix `[console]`. |
| BRAND-1.6 | Wire identifiers that name the product change: `/v1/status` `service`, the Prometheus `maya:` prefix, MCP `clientInfo`, the `User-Agent`, `/api/version`, the `maya` object in `/api/tags` and `/api/show`, the `--engine maya` value, and the emitted sealed-reasoning prefix. Values are proposed in [naming.md](naming.md) (OPEN-35; the Prometheus prefix is OPEN-22 and the sealed-reasoning prefix OPEN-02); whether the donor's sealed-reasoning prefix is accepted on input is open (naming item N1, OPEN-01). |
| BRAND-1.7 | Quant names (`Maya-XS`, `Maya-S`, `Maya-M`, `Maya-L` and their keys) are replaced by neutral labels from a data-driven table. The quant-specific thinking-budget default becomes a per-model registry value with the same arithmetic (PRM planner). |
| BRAND-1.8 | No sponsor links: the sidebar heart, the About support line and `SUPPORT_URL` (`serve/web/lib.js:6`, `serve/web/sidebar.js:280`) are removed. |
| BRAND-1.9 | Dashboard identifiers that carry the name are renamed: the `maya:context` DOM event, the `--maya-side`, `--maya-read` and `.maya-mark` CSS names, the `maya-code.<ext>` and `maya-chat-<stamp>.md` download names, and the `window.maya` global. Its debug-only replacement, `window.console_debug`, is approved deviation [P-13](#p-13). |

## BRAND-2

**Letter tiles per model family, system font stack, SVG icons only.**

- **project-maya does.** It ships vendor logo images (`serve/web/logo-deepseek.svg`,
  `logo-glm.svg`, `logo-minimax.svg`, `logo-qwen.svg`), the Outfit font files
  (`serve/web/fonts/`, declared in `serve/web/tokens.css:5-7`), and PNG icons including
  the Maya logo (`serve/web/icon-32.png`, `icon-180.png`, `icon-192.png`, `icon-512.png`).
- **PulsarMLX Console does.** It shows a letter tile per model family, uses the system
  font stack, and ships SVG icons only.
- **Why.** Third-party marks, and the repository's staged-content scan rejects binary
  files.
- **Approval.** Approved by the owner with the plan on 2026-11-14.
- **Affected donor tests (known).** Tests of `modelLogo()` keep their matching table and
  return shape (WEB planner); confirmed by WEB-04.
- **Packages.** WEB-01, WEB-02 (the `/fonts/<name>` route and the web manifest).

| Sub-item | Difference |
| --- | --- |
| BRAND-2.1 | Vendor logos are replaced by letter tiles per family; family detection is unchanged. |
| BRAND-2.2 | The Outfit font files are not shipped; the dashboard uses the system font stack. |
| BRAND-2.3 | Icons are SVG only. The WEB planner proposed PNG icons rendered from a new SVG mark; that conflicts with this entry and is not done. The Lucide sprite stays, with its ISC notice. |
| BRAND-2.4 | `GET /fonts/<name>` answers 404; no font file is shipped. |
| BRAND-2.5 | `manifest.webmanifest` lists SVG icons only; no PNG file is shipped. |

## LIC-1

**Templates load from the model directory at run time and are never committed;
vendor-template checks run only in the manual job and record hashes, not text.**

- **project-maya does.** It ships model vendors' chat templates and uses one as a
  fallback: `serve/chat_template.jinja` (Qwen Community License),
  `serve/glm5_chat_template.jinja`,
  `data/glm-dsa/templates/glm-5.3.official.jinja` (no license text in the donor),
  `tools/ds4/chat_template.jinja`, `tools/mm3/chat_template.jinja` and
  `serve/fixtures/minimax_m31/` (MiniMax Community License), `tools/glm_chat_template.jinja`.
- **PulsarMLX Console does.** It never commits a vendor template. A template comes from
  the model directory or an explicit configuration path at run time; with none
  configured, start-up fails with a clear error and there is no bundled fallback
  (decision B4). Tests use PulsarMLX-authored synthetic templates. Vendor-template checks
  run only in the manual job and record hashes, not text.
- **Why.** The templates carry their vendors' licenses.
- **Approval.** Approved by the owner with the plan on 2026-11-14.
- **Affected donor tests (known).** `serve/test_qwen_template.py` (7),
  `serve/test_render_other_models.py` (2), the golden cases of
  `serve/test_ds41_conformance.py`, the shared-mode cases of
  `serve/test_minimax_frontend.py`, the per-model cases of `serve/test_prompt_memo.py`,
  and `serve/test_glm_dsa_serve.py::TemplateAtStart::test_a_pack_without_a_template_gets_the_official_one`
  (which asserts the fallback that is not built). Most take the `vendor-render`
  disposition; the fallback test takes `deviation`.
- **Packages.** PRM-02 (synthetic templates, vendor-template provider), PRM-03 (Jinja
  runtime), PRM-08 (start-up template selection), CNF-11 (vendor-render checks).

| Sub-item | Difference |
| --- | --- |
| LIC-1.1 | No vendor template is committed anywhere in the repository. |
| LIC-1.2 | With no template configured, start-up fails with a clear error; there is no bundled vendor fallback. |
| LIC-1.3 | Tests use PulsarMLX-authored synthetic templates with each family's special-literal sets. |
| LIC-1.4 | Vendor-template render checks run only in the manual job, read the hash-verified pinned donor checkout, and record hashes, never text. |

## LIC-2

**The MiniMax picture preprocessor is not built in this increment.**

- **project-maya does.** `serve/mm3_vision.py` resizes pictures for MiniMax-M3.1-Flash and
  writes them in the MMI1 file format for an engine that reports `INFO vision=mm3`
  (`serve/server.py:7265`). Its header describes it as the server's half of the model's
  own image processor (`serve/mm3_vision.py:1-12`).
- **PulsarMLX Console does.** It does not build the preprocessor (decision B10). The MMI1
  file format is documented in the media contract, and an engine reporting `vision=mm3`
  gets a clear error for pictures.
- **Why.** The algorithm may carry a non-commercial license. The owner asked to be told if
  it should be built.
- **Approval.** Approved by the owner with the plan on 2026-11-14.
- **Affected donor tests (known).** `serve/test_mm3_vision.py` (7 methods:
  `SmartResize::*` and `Spans::*`).
- **Packages.** RSP-19 (builds only the DeepSeek DSI1 half), RSP-17 (capability and error).

| Sub-item | Difference |
| --- | --- |
| LIC-2.1 | No MiniMax resize or span code is written. |
| LIC-2.2 | The MMI1 format is documented in the media contract (RSP-17, RSP-18). |
| LIC-2.3 | A picture request to an engine with `vision=mm3` is refused with a clear 400; the RSP planner proposed that `/health` then report images as unavailable. |

## POL-1

**The capability flag is recognized and refused unless an engine advertises it; the switch
and its configuration keys are not ported.**

- **project-maya does.** A per-request `ablate` field and a Models-page switch project a
  refusal direction out of the model when the engine loaded one (`INFO ablate=1`;
  `serve/server.py:2481-2487`, `:2497-2504`; the engine key at `:1352-1356`).
- **PulsarMLX Console does.** It recognizes the `ablate` field and refuses `ablate: true`
  unless an engine advertises the capability; no engine in this increment does. The switch
  and its configuration keys are not ported (decision B10).
- **Why.** A product policy decision that belongs to the owner; nothing in this increment
  could use it.
- **Approval.** Approved by the owner with the plan on 2026-11-14.
- **Affected donor tests (known).** `serve/test_models.py::Ablate::*` (4 methods),
  `serve/test_server.py::RequestChecks::test_ablate`, and ablation cases inside
  `serve/test_models.py::Settings::*`, `serve/test_glm_dsa_models.py::Page::*` and
  `serve/test_mixed_gpus.py::TestMixedGpus::test_flags` (candidates).
- **Implementation.** API-04 (commit `89d40258`, 2026-11-15) recognizes the request field
  `ablate` in `console_core::request::check_request` and refuses `ablate: true` unless
  `EngineCaps::ablate` is set (POL-1.1); the refusal reads "ablate: this model has no
  refusal direction loaded", without the donor's pointer to the unported Models-page
  switch (a wording that awaits the lead's review, [naming.md](naming.md) section 3.8). The
  run-config key `sampling.ablate` is not ported and is reported as an unknown key
  (POL-1.2). The tests
  `console-core::api04_request::ablate_is_recognized_and_refused_unless_advertised` and
  `console-core::api04_sampling::run_config_sampling_block` pin both. The ledger row
  `serve/test_server.py::RequestChecks::test_ablate` cites POL-1 with the `deviation`
  disposition.
- **Packages.** API-04 (request check), OPS-05 (settings profiles), WEB-09 (Models page).

| Sub-item | Difference |
| --- | --- |
| POL-1.1 | `ablate: true` is refused with a 400 unless the engine advertises `ablate`. |
| POL-1.2 | The Models-page switch, its per-model default and its storage key are not ported. |
| POL-1.3 | No `ablate=1` key is ever sent to an engine in this increment. |

## PLAT-1

**NVIDIA NVML, AMD sysfs and Windows readers and multi-GPU helpers are ported behind
traits, tested with the same fixtures, type-checked for Linux and Windows in CI, labeled
unverified on real hardware, and built last.**

- **project-maya does.** It reads NVIDIA cards through NVML in a child process
  (`serve/telemetry.py:185-340`), AMD cards through Linux sysfs (`:449-597`) and Windows
  DXGI, PDH and hipinfo (`:598-816`), and supports multi-GPU layouts (`serve/gpu_map.py`,
  `serve/mixed_gpus.py`, `serve/glm_link.py`).
- **PulsarMLX Console does.** It ports these behind traits in milestone M9, tests them with
  the same fixtures, type-checks them for Linux and Windows in CI, and labels them
  unverified on real hardware everywhere they are mentioned (decision B11).
- **Why.** They cannot run on a Mac.
- **Approval.** Approved by the owner with the plan on 2026-11-14.
- **Affected donor tests (known).** `serve/test_telemetry.py` (`AmdSysfs::*`,
  `AmdWindows::*`, `ReaderProcess::*`), `serve/test_mixed_gpus.py` (8),
  `serve/test_glm_link.py` (4). These keep the `rust-test` disposition when the fixture
  tests pass; the deviation is the "unverified on real hardware" label and the late
  milestone.
- **Packages.** OPS-19 (NVIDIA), OPS-20 (AMD and Windows), ENG-13 (GPU map), ENG-16 (mixed
  GPUs), API-18 (Windows lifecycle shims), WEB-08 (GPU-era monitor paths), CNF-16 (fixture
  kit). Hardware-specific parts that land before M9 are built in their own milestones
  behind traits, with fixture or mocked providers, and labeled unverified on real
  hardware; the real readers stay in M9. These are the NVML process check in ENG-08
  (milestone M3), the GLM link mode in ENG-15 (M3), GPU vision memory lending in ENG-14
  and RSP-18 (M6), and the `nvidia-smi` and KFD parsers in OPS-07 (M7).

| Sub-item | Difference |
| --- | --- |
| PLAT-1.1 | The NVIDIA reader runs in a crash-isolated child process behind a trait, fixture-tested. |
| PLAT-1.2 | The AMD sysfs and Windows DXGI/PDH readers sit behind traits, fixture-tested. |
| PLAT-1.3 | The GPU map, mixed-GPU helper and GLM link mode are fixture-tested only. |
| PLAT-1.4 | Windows lifecycle and process code is type-checked for Windows in CI. The RSP planner proposed leaving Windows-only code "not compiled in CI"; decision B11 requires the type-check, so that proposal is not followed. |
| PLAT-1.5 | GPU vision-encoder memory lending (`VLEND`/`VRECLAIM`) sits behind a trait and is verified only against fake replies. |
| PLAT-1.6 | Every mention of these readers in the product and its documents carries the label "unverified on real hardware". |

## PLAT-2

**An Apple Silicon reader and a matching monitor view.**

- **project-maya does.** It reports no GPU figures on a Mac (its GPU readers are NVML, AMD
  sysfs and Windows only, `serve/telemetry.py:185-816`), and without `psutil` no CPU or
  RAM figures, because the fallback reads Windows APIs or Linux `/proc` (`:15-16`,
  `:892-937`); the Monitor shows dashes for what is missing (OPS and WEB planners).
- **PulsarMLX Console does.** It adds an Apple Silicon reader (unified memory, memory
  pressure, swap, disk; GPU activity as an experimental field) and a matching monitor view.
- **Why.** What the monitor needs on the machine this project targets.
- **Approval.** Approved by the owner with the plan on 2026-11-14.
- **Affected donor tests (known).** `serve/test_telemetry.py::Sampler::test_this_machine`
  (candidate). The additive fields leave GPU-platform outputs unchanged.
- **Packages.** OPS-17 (sampler core), OPS-18 (Apple Silicon reader), WEB-07 (monitor
  view).

| Sub-item | Difference |
| --- | --- |
| PLAT-2.1 | An Apple Silicon reader supplies unified memory, pressure, swap and disk figures; GPU activity is an experimental field. Proposed details (OPS planner): one Apple GPU entry with unified-memory size, an additive `unified_memory` field, temperature, power and PCIe reported as null. |
| PLAT-2.2 | A monitor view for Apple Silicon, selected by an additive platform field (WEB planner proposes `hardware_static.platform`); without it, the donor's GPU views render unchanged. |

## PLAT-3

**`pulsar-console fetch` and `pulsar-console supervise` with the same progress, exit-code
and restart contracts; the model catalog ships empty.**

- **project-maya does.** Downloads run the Python launcher as a child
  (`maya.py --setup --model <id> --download-model ...`, `serve/model_pull.py:2`,
  `:193-205`), restarts are driven by that launcher (`serve/update.py:19-21`: exit 75 after
  an update, 76 after a saved port or switch), and the catalog lists project-maya's own
  quants.
- **PulsarMLX Console does.** The pull driver spawns `pulsar-console fetch` with the same
  argument shape and progress-line contract; `pulsar-console supervise` keeps the restart
  protocol. The catalog ships empty (decision B10).
- **Why.** The launcher is outside this increment, and the catalog lists Maya quants.
- **Approval.** Approved by the owner with the plan on 2026-11-14.
- **Affected donor tests (known).** `serve/test_model_api.py::Pull`; catalog tests that
  read the launcher's tables (OPS planner names `Catalog.test_the_setup_takes_its_command`)
  become `not-applicable` (`launcher-only`) with replacement manifest tests.
- **Packages.** OPS-11 (supervisor), OPS-14 (catalog and manifest schema), OPS-15 (pull
  driver), OPS-16 (fetch tool).

| Sub-item | Difference |
| --- | --- |
| PLAT-3.1 | `pulsar-console fetch` replaces the launcher's download child, with the same argument shape and progress lines. It uses the system `curl` (decision B7). |
| PLAT-3.2 | `pulsar-console supervise` keeps the restart protocol (exit 76 with a switch note, exit 75, parent pipe, signals, newest-config start) and re-executes the current binary. It does no setup, compiling, calibration, report or benchmark. |
| PLAT-3.3 | The catalog is a schema-validated manifest that ships with no real entries; synthetic entries live in tests. Real entries need the owner's approval. |

## FIX-1

**A few upstream defects are fixed, each listed here.**

- **project-maya does.** See each sub-item.
- **PulsarMLX Console does.** It fixes the three defects below.
- **Why.** Reproducing a defect has no value.
- **Approval.** Approved by the owner with the plan on 2026-11-14.
- **Packages.** ENG-06, ENG-07, ENG-08, ENG-12.

| Sub-item | Donor behavior | PulsarMLX Console behavior | Affected donor tests (known) | Packages |
| --- | --- | --- | --- | --- |
| FIX-1.1 | **Context reload kills instead of quitting.** `StrataEngine.stop` is defined twice; the graceful QUIT-and-wait version (`serve/server.py:985-999`) is shadowed by the request-level `stop` (`:1693-1700`). `Service._restart_with` calls `stop()` then `restart()`, which kills the engine (`:2765-2772`), so an engine that keeps sessions on QUIT loses them on every reload. | A reload uses the graceful close: STOP if advertised, QUIT, wait up to the quit time, then kill; then it sets the new context and starts the engine. | `serve/test_dashboard.py::Dashboard::test_reload_changes_the_context_and_saves_it` and `serve/test_dashboard.py::ContextCost::test_set_context_rewrites_the_command` (candidates; the fake engine then writes its kept-session file on reload) | ENG-08, ENG-12 |
| FIX-1.2 | **Concurrent writes to the engine pipe.** In multi-conversation mode each request thread writes its own `GEN`, `STOP` and `PAUSE` lines to the child's standard input (`serve/server.py:1572`, `:1678-1690`) without a lock. | One writer owns the child's standard input and writes every line whole. Nothing else observable changes. | none known | ENG-06, ENG-07 |
| FIX-1.3 | **Untagged stop in multi mode.** `StrataEngine.stop()` never sends a request id (`serve/server.py:1693-1700`), and a multi engine ignores an untagged `STOP`, so the shutdown cut after `WRAP` stops no request. | During shutdown on a multi engine, `STOP <rid>` is sent for each request in flight after the wrap window. Single-conversation behavior is unchanged. | none known | ENG-07, ENG-12 |

---

## Differences decided elsewhere in the plan (PLAN-1 to PLAN-6)

These differences follow from decisions the approved plan states outside its deviation
table. The decision is the owner's, made with the plan on 2026-11-14; each entry cites the
plan section that decides it as its approval basis. The ledger cites them as `deviation`
like any other id. A sub-item of these entries that gives an exact value the plan does not
fix is marked "proposed", as elsewhere in this register.

### PLAN-1

- **project-maya does.** It shows no synthetic badge, and `/health` does not report a
  synthetic backend.
- **PulsarMLX Console does.** The dashboard shows a permanent "Synthetic engine: no real
  model" badge and `/health` reports the synthetic backend. The API planner proposed
  concrete fields (`synthetic: true`, `backend`) in `/health` and `/v1/status`, and a
  suffix on the ready line; those values are proposed (OPEN-35). An engine that does not
  report synthetic provenance is refused at start: the server does not serve it, at
  process start or at a later restart, model switch or context reload (owner decision of
  2026-11-14 on OPEN-29; the mechanism is in [backend-seam.md](backend-seam.md), section
  5.1). What must be done to allow a non-synthetic engine is written in
  [`ALLOWING_NON_SYNTHETIC_ENGINES.md`](../../../docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md).
- **Why.** This increment can at most be "qualified on synthetic backends", and nothing
  may suggest a real model is served.
- **Approval basis.** Plan section 7, item 5; for the refusal at start, the owner's
  decision of 2026-11-14 on OPEN-29 (seam question Q9).
- **Packages.** API-06 (`/health`), WEB-07 (badge), ENG-01 (the provenance type and the
  synthetic-only guard), ENG-10 (the guard on every engine admission path), API-08 (the
  refusal at process start).

### PLAN-2

- **project-maya does.** The scripted engine's default model name is
  `qwen3.8-flash-next` (`serve/server.py:2383`).
- **PulsarMLX Console does.** The default model name is exactly
  `pulsar-console-synthetic`, decided by the owner on 2026-11-14 (OPEN-03).
- **Why.** A real model's name on a synthetic engine would overclaim.
- **Approval basis.** Plan section 12 ("Overclaiming": model names containing
  `synthetic`); the exact string, the owner's decision of 2026-11-14.
- **Implementation.** ENG-02 (commit `c86cf84f`, 2026-11-15) defines
  `console_engine::fake::DEFAULT_MODEL_NAME` as `pulsar-console-synthetic`. The tests
  `console-engine::fake::tests::fake_default_model_name_is_the_decided_one` and
  `console-engine::eng02_seam::fake::the_decided_names_hold` pin it. The API-08 tests that
  assert it in the `model` field are not built yet.
- **Packages.** ENG-02 (the scripted engine's default model name), asserted by the tests of
  API-08; API-17 keeps it when the full command line lands.

### PLAN-3

- **project-maya does.** It reads `serve/web` from disk on each request
  (`serve/server.py:5971-5988`).
- **PulsarMLX Console does.** Dashboard assets are embedded from a fixed compile-time table
  and no filesystem path is ever served. The API planner's proposed opt-in development
  override that serves files from a directory conflicts with "no filesystem path is ever
  served" and is not adopted (OPEN-41).
- **Why.** The plan's front-end choice: no filesystem path is ever served.
- **Approval basis.** Plan section 6, technology table (front end).
- **Packages.** WEB-02.

### PLAN-4

- **project-maya does.** It serves no license notices.
- **PulsarMLX Console does.** License notices are served from the dashboard's About page
  (the WEB planner proposed `/web/notices.txt` assembled from `console/LICENSES/`).
- **Why.** The donor qualification requires the MIT, Preact, htm and Lucide notices to
  ship and to be reachable by the user.
- **Approval basis.** Plan section 7, item 4.
- **Packages.** WEB-01.

### PLAN-5

- **project-maya does.** Structured output needs the optional `jsonschema` package and
  answers 400 "structured output requires jsonschema" without it
  (`serve/response_schema.py:96`).
- **PulsarMLX Console does.** The schema validator is written in-house, so structured
  output never depends on an optional package and that 400 path cannot occur. JSON Schema
  meta-validation wording may differ while the `invalid JSON Schema: ` prefix and the
  accept and reject decisions match (RSP planner); that wording difference still awaits
  the owner's decision (OPEN-15; see "Deferred, awaiting owner decision").
- **Why.** Few dependencies; no `jsonschema` crate.
- **Approval basis.** Plan section 6, technology table (schema validation, written
  in-house; no `jsonschema`), restated as decision B6.
- **Packages.** RSP-02.

### PLAN-6

- **project-maya does.** It reaches HTTP and HTTPS MCP servers with Python's
  `urllib.request` (`serve/mcp.py:31-32`, `:275-277`).
- **PulsarMLX Console does.** HTTPS MCP servers are reached through the outbound `curl`
  facade (module `outbound` in `console-core`, written by RSP-10). The RSP planner
  proposed refusing `https` MCP servers until a TLS crate existed; the plan routes HTTPS
  MCP through `curl`, so that proposal is superseded.
- **Why.** No TLS crate in this increment; all outbound network goes through one facade.
- **Approval basis.** Plan section 6, technology table (outbound network), restated as
  decision B7.
- **Packages.** RSP-10.

## Approved proposals

The owner approved the proposals below on 2026-11-14, at owner checkpoint 1. Each keeps its
P- id as its deviation id (rule 4) and is a deviation like any other id in this register:
ledger rows and comparator annotations cite it. The ids P-5, P-12 and P-17 to P-25 are not
here: P-12 and P-17 were declined, P-5 and P-18 are deferred, and P-19 to P-25 were raised
later and await the owner (the two sections that follow).

### P-1

- **project-maya does.** It sends Python's default `Server: BaseHTTP/0.6 Python/3.x`.
- **PulsarMLX Console does.** It sends `Server: pulsar-console/<version>`. The header name
  and its position stay observable. The value stays on the volatile list for comparison
  against donor references (parity-ledger section 1.1), and the tests of API-02 assert the
  console's own value.
- **Why.** API planner: copying the donor's value would misrepresent the implementation.
- **Approval.** Approved by the owner on 2026-11-14 at checkpoint 1.
- **Affected donor tests (known).** None identified yet; the implementing package
  confirms. API-02 found none among the donor test methods it owns.
- **Implementation.** API-02 (commit `d64685f7`, 2026-11-15) implements P-1 in
  `console_http::transport::SERVER_HEADER`: `pulsar-console/` followed by the crate version
  (`pulsar-console/0.0.0` at that commit). The header comes right after the status line and
  before `Date`, where Python's `send_response` writes it. The test
  `console-http::transport::wire::tests::server_header_is_the_product_version` and the raw
  head assertions of `console-http::api02_transport` and `console-http::api02_donor` pin it.
- **Packages.** API-02.

### P-2

- **project-maya does.** It prefers chunked framing silently when a request carries both
  `Content-Length` and `Transfer-Encoding: chunked` (`serve/server.py:5416-5444`).
- **PulsarMLX Console does.** It answers 400 to a request that carries both.
- **Why.** API planner: ambiguous framing is a request-smuggling vector behind proxies. It
  is not part of SEC-1's approved text, so it is registered on its own.
- **Approval.** Approved by the owner on 2026-11-14 at checkpoint 1.
- **Affected donor tests (known).** None identified yet; the implementing package
  confirms. `serve/test_server.py::RequestBodies::test_a_chunked_body` sends chunked
  framing alone and is expected to keep passing. API-02 found none: no donor test
  method's assertion changes, so no ledger row cites P-2.
- **Implementation.** API-02 (commit `d64685f7`, 2026-11-15) answers the 400 in the
  donor's bad-body form:
  `{"error": {"type": "invalid_request_error", "message": "both Content-Length and a chunked Transfer-Encoding were sent; send only one"}}`
  (`CONFLICTING_FRAMING`). The transport sends it for every request with a served method
  (`GET`, `POST`, `DELETE`, `OPTIONS`), after the 501 method check and before the handler
  is called, so it applies on every route, whether or not the route reads a body, and
  before any router guard. The answer carries the end-headers hook's headers (CORS). It
  applies when any `Content-Length` header is present, an empty one included, and any
  `Transfer-Encoding` header has a comma-separated value that is `chunked` once stripped
  and lower-cased, in any position. That is wider than the donor's decoding rule, which
  looks only at the last value of the first header. `read_body` checks again as a second
  guard. The code is in `console_http::transport` (`has_conflicting_framing`,
  `serve_connection`, `read_body`). The tests
  `console-http::transport::body::tests::both_framings_are_refused` and
  `console-http::api02_transport::both_content_length_and_chunked_are_refused` pin it.
- **Packages.** API-02.

### P-3

- **project-maya does.** The `malformed request (...)` answer includes the Python
  exception class and its `repr`.
- **PulsarMLX Console does.** It keeps the `malformed request (` prefix and a Python-like
  category, with different detail text.
- **Why.** API planner: the Python text has no Rust counterpart.
- **Approval.** Approved by the owner on 2026-11-14 at checkpoint 1.
- **Affected donor tests (known).** None identified yet; the implementing package
  confirms. `serve/test_server.py::RequestBodies::test_a_malformed_body_is_a_400` asserts
  only the status and is expected to keep passing. No donor test method owned by API-01 is
  affected.
- **Implementation.** API-01 (commit `c2392605`, 2026-11-14) implements P-3 in
  `console_http::error::ApiError::Malformed`. The message is
  `malformed request (<Category>: <detail>)`, where the category is one of `KeyError`,
  `TypeError`, `AttributeError` or `IndexError` (`MalformedCategory`) and the detail is the
  server's own text. The test
  `console-http::api01_error::malformed_request_keeps_prefix_and_category_p3` pins it.
- **Packages.** API-01, API-07, PRM-06.

### P-4

- **project-maya does.** Reader error messages embed `zipfile`, `ElementTree`, Pillow,
  `json` and `OSError` text.
- **PulsarMLX Console does.** It keeps the error-message prefixes exactly, with the
  parenthesized detail taken from the Rust reader.
- **Why.** RSP planner: library exception text cannot be reproduced.
- **Approval.** Approved by the owner on 2026-11-14 at checkpoint 1.
- **Affected donor tests (known).** None identified yet; the implementing package
  confirms. The error-message checks in `serve/test_attach.py::Text::*` assert prefixes
  and phrases only and are expected to keep passing.
- **Packages.** RSP-12, RSP-18, RSP-19.

### P-6

- **project-maya does.** It waits for `READY` forever.
- **PulsarMLX Console does.** It offers an optional engine ready-timeout setting, off by
  default. The setting is additive. This settles OPEN-10.
- **Why.** ENG planner: a hung engine start hangs the server start.
- **Approval.** Approved by the owner on 2026-11-14 at checkpoint 1.
- **Affected donor tests (known).** None identified yet; the implementing package
  confirms.
- **Packages.** ENG-06, which adds the setting to the settings store that API-15 builds
  and records its name in [naming.md](naming.md).

### P-7

- **project-maya does.** A temporary path that contains a space silently breaks picture
  requests.
- **PulsarMLX Console does.** It creates the vision temporary directory under a
  whitespace-free base and refuses to start if none exists.
- **Why.** ENG planner: an upstream defect, not one of the three FIX-1 items.
- **Approval.** Approved by the owner on 2026-11-14 at checkpoint 1.
- **Affected donor tests (known).** None identified yet; the implementing package
  confirms.
- **Packages.** ENG-14, which creates the directory and refuses at start when no
  whitespace-free base exists; RSP-18 and RSP-19, which write their files under it. The
  per-request `GENI` path check of ENG-04 is the donor's behavior and is not part of this
  deviation (settled by the lead on 2026-11-14).

### P-8

- **project-maya does.** A template `raise_exception` and a DeepSeek encoder assertion
  failure end in an unclean server error.
- **PulsarMLX Console does.** Both answer 400. This settles OPEN-07.
- **Why.** PRM planner: an upstream defect, not one of the three FIX-1 items.
- **Approval.** Approved by the owner on 2026-11-14 at checkpoint 1.
- **Affected donor tests (known).** None identified yet; the implementing package
  confirms.
- **Packages.** PRM-03 (template error), PRM-07 (encoder error), PRM-08 (render-time
  failures), API-07 (the HTTP mapping).

### P-9

- **project-maya does.** Models cards label `hip` as `HIP` and every other backend as
  `CUDA`.
- **PulsarMLX Console does.** It uses a backend label table: `hip` to HIP, `cuda` to CUDA,
  `metal` to Metal, synthetic to Synthetic, else the raw value. The table has no entry
  for `fake`: the planner detail's mapping of `fake` to Synthetic was not part of the
  proposal and is not approved.
- **Why.** WEB planner: an upstream defect that would label every synthetic or Apple model
  CUDA.
- **Approval.** Approved by the owner on 2026-11-14 at checkpoint 1.
- **Affected donor tests (known).** None identified yet; the implementing package
  confirms.
- **Packages.** WEB-08.

### P-10

- **project-maya does.** The frozen-engine watchdog never fires on a Mac in practice,
  because `psutil` lacks `io_counters` there.
- **PulsarMLX Console does.** On macOS the watchdog fires only when a GPU-busy signal
  exists. The activity samplers are implemented on macOS and Linux without `psutil`.
- **Why.** ENG planner: a naive watchdog could kill a healthy GPU-bound engine. The
  behavior is close to the donor's, but the mechanism differs.
- **Approval.** Approved by the owner on 2026-11-14 at checkpoint 1.
- **Affected donor tests (known).** `serve/test_server.py::StallWatchdog::test_stuck`,
  `serve/test_server.py::StallWatchdog::test_working` and
  `serve/test_server.py::StallWatchdog::test_without_psutil_nothing_is_ended`
  (candidates: they inject samples and a GPU-busy hook and are expected to keep passing).
- **Packages.** ENG-08, OPS-17.

### P-11

- **project-maya does.** It sends dashboard assets with `Cache-Control: no-cache` and no
  validators, and has no `HEAD` support.
- **PulsarMLX Console does.** It sends strong `ETag`s with 304 responses, and answers
  `HEAD`, for dashboard assets. The development-directory module (`devdir`) is not part
  of this deviation and stays not adopted (PLAN-3, OPEN-41).
- **Why.** WEB planner: about 600 KB is re-downloaded on every load.
- **Approval.** Approved by the owner on 2026-11-14 at checkpoint 1.
- **Affected donor tests (known).** `serve/test_server.py::WebApp::*` checks static
  serving (candidates; confirmed by WEB-02).
- **Packages.** WEB-02.

### P-13

- **project-maya does.** It sets `window.maya = {S, chatView}` always
  (`serve/web/app.js:126`).
- **PulsarMLX Console does.** It replaces `window.maya` with
  `window.console_debug = {S, chatView}`, set only when `#debug` is in the address.
  BRAND-1.9 covers removing the name; adding the debug global is this deviation.
- **Why.** WEB planner: the global exposes the whole state object.
- **Approval.** Approved by the owner on 2026-11-14 at checkpoint 1.
- **Affected donor tests (known).** None identified yet; the implementing package
  confirms.
- **Packages.** WEB-03.

### P-14

- **project-maya does.** `details.format` is always `gguf`.
- **PulsarMLX Console does.** `details.format` reports `safetensors` for PulsarMLX MLX
  checkpoints.
- **Why.** OPS planner: accuracy for a format the donor does not know.
- **Approval.** Approved by the owner on 2026-11-14 at checkpoint 1.
- **Affected donor tests (known).** None identified yet; the implementing package
  confirms.
- **Packages.** OPS-12.

### P-15

- **project-maya does.** Its pack-centric rule marks MLX checkpoint configurations not
  startable.
- **PulsarMLX Console does.** MLX checkpoint configurations are listed with `ok: false`
  and "no engine for this backend in this build".
- **Why.** OPS planner: PulsarMLX checkpoints are Safetensors directories.
- **Approval.** Approved by the owner on 2026-11-14 at checkpoint 1.
- **Affected donor tests (known).** None identified yet; the implementing package
  confirms.
- **Packages.** OPS-03, OPS-16.

### P-16

- **project-maya does.** It has no rule on the catalog revision.
- **PulsarMLX Console does.** It refuses catalog revision `main`.
- **Why.** OPS planner: a moving revision cannot be verified. The catalog ships empty
  (PLAT-3.3), so this matters only when real entries are approved.
- **Approval.** Approved by the owner on 2026-11-14 at checkpoint 1.
- **Affected donor tests (known).** None identified yet; the implementing package
  confirms.
- **Packages.** OPS-14.

## Declined proposals

The owner declined these proposals on 2026-11-14, at checkpoint 1. They are not
deviations. Each keeps its id, marked declined, so the id is never reused (rule 4). A
ledger row or comparator annotation that cites one fails the checker.

| Ref | Proposed difference | Reason declined | Decided | What stands instead |
| --- | --- | --- | --- | --- |
| P-12 (declined) | A report-only switch for the Content-Security-Policy (WEB planner: a rollback aid) | It would weaken SEC-2 while on | By the owner, 2026-11-14 | SEC-2 as approved; no report-only switch is built |
| P-17 (declined) | A literal-parity setting for the old reload behavior (ENG planner, offered as an alternative to FIX-1.1) | FIX-1.1 is approved | By the owner, 2026-11-14 | FIX-1.1 as approved: a reload uses the graceful close; no literal-parity reload setting is built |

## Deferred, awaiting owner decision

The owner deferred P-5 and P-18 on 2026-11-14, at checkpoint 1. P-19 to P-25 were raised
by the M1 packages on 2026-11-14 and 2026-11-15 and have not been put to the owner yet;
they are put at checkpoint 2. None of the nine is **approved**. Until the owner decides, the
implementing package reproduces the donor's behavior where it can, and records the row as
`pending` where it cannot. For P-19 to P-25 it cannot: the code ships the proposed
behavior, says so where it does, and changes if the owner declines. The register of open
items tracks all nine as OPEN-15.

| Ref | Proposed difference | Donor behavior | Planner and reason | Decide before |
| --- | --- | --- | --- | --- |
| P-5 | Decode and resample pictures with Rust code (Catmull-Rom for bicubic, in-house pad, EXIF orientation); formats PNG, JPEG, GIF, BMP, WebP; pixel values labeled not bit-exact with Pillow | Pillow decode, `ImageOps.pad`, bicubic | RSP: Pillow is unavailable and no real vision tower makes pixel differences observable. | The picture packages of M6 (RSP-18, RSP-19) |
| P-18 | An optional, explicit model-family override in configuration, beside the substring-based family detection | The template family is detected only from marker substrings in the chat template's source (`serve/frontend.py`, class `ChatTemplate`); there is no override | PRM (PRM-05): detection by substrings is brittle; the override is additive and leaves detection unchanged when unset. | PRM-05 in M2 |
| P-19 | Refuse a JSON document that holds an unpaired UTF-16 surrogate inside a string (an escape from `\uD800` to `\uDFFF` without its pair, or such a surrogate in the body bytes), with the reader's own message in Python's position format; a request body that does so is answered 400 | CPython's `json.loads` accepts it and builds a `str` that holds the lone surrogate | API-01: a Rust `String` cannot hold a lone surrogate. Outside a string a lone surrogate fails exactly as in CPython. | Checkpoint 2 (the behavior ships with API-01) |
| P-20 | Refuse a JSON document nested deeper than 1000 levels, in the reader and the writer, with CPython's `RecursionError` wording; a request body that deep is answered 400 | CPython has no fixed limit: far deeper documents parse, and one deep enough to exhaust its stack raises an uncaught `RecursionError`, so the client gets no answer | API-01: an explicit bound keeps the reader, the writer and the recursive drop of a parsed value within the stack. | Checkpoint 2 (the behavior ships with API-01) |
| P-21 | Four parse differences on engine output that no working engine produces: an `INFO` value with more than one leading minus sign stays a string; a value in non-ASCII decimal digits stays a string; an integer beyond 64 bits stays a string; and a `DONE` count that is negative or above 32 bits is refused | The donor's `int()` raises on the first, so the engine start fails; reads the second; keeps the third as a Python integer; and accepts the fourth (`serve/server.py:927-930`, `:1192-1199`) | ENG-01: typed, bounded figures in the seam; each case is a malformed line from an engine. | Checkpoint 2 (the behavior ships with ENG-01) |
| P-22 | Answer Python's error page for a refused request head (400, 414, 431, 505) also when `cors_origins` is set | With `cors_origins` set, the donor's `end_headers` override raises an `AttributeError` on these pages, because the request path or headers are not set yet, and the client gets no answer (`serve/server.py`, the handler's `end_headers`) | API-02: an upstream defect that is not one of the three FIX-1 items; the transport cannot reproduce a crash without an answer. For the 431 page the hook runs with empty headers, so a listed-origin list adds no CORS header. | Checkpoint 2 (the behavior ships with API-02) |
| P-23 | Five differences in the run-config store: a config file above 16 MiB is not read; a config `env` that is not an object, a config `host` that is not a string and an `installer` that is not an object stop the server with the console's own message; a document nested deeper than the reader's bound reads as an empty config on the lenient path (tied to P-20); the savings path expands only `~` and `~/`, not `~name/`; and a rewritten config keeps its file permissions | The donor reads a file of any size; stops with a Python traceback or `TypeError` in the three cases; reads a deep document; uses `Path.expanduser()`; and writes a new file with default permissions | API-15: bounded reads and readable start-up errors; the server stops in the same cases as the donor, only the text differs. | Checkpoint 2 (the behavior ships with API-15) |
| P-24 | Tokenizer pack loading: refuse, with the crate's own messages, a `vocab.json` that leaves exactly one id empty, a `special_ids` that is truthy but not an object, token-type values that are truthy but not a list, and GGUF token or merge arrays that are not arrays of strings; refuse a pack file above 512 MiB before reading it; and bound the compile size of the special-literal pattern at 256 MiB | The donor accepts these inputs (for example it turns a string into a list of characters) and has no size limits | PRM-04: inputs no working pack has; explicit limits on anything sized by a file. Plain spans are byte offsets into the Rust string where the donor uses code-point indexes, which changes no observable behavior. | Checkpoint 2 (the behavior ships with PRM-04) |
| P-25 | Under `--port 0` the server's ready line names the port the operating system bound | The donor prints the requested port (`a.port`, `serve/server.py:7387`), so under `--port 0` its line would say `:0`; its own tests never start it with port 0 | CNF-07: the conformance harness starts every server on port 0 and reads the port from the ready line. For any other port the line is identical to the donor's. API-08 and API-17 implement it. | Checkpoint 2 (the harness of CNF-07 relies on it) |

Two further items are still open under OPEN-15 and await the owner in the same way: the
JSON Schema meta-validation wording of PLAN-5 (the `invalid JSON Schema: ` prefix and the
accept and reject decisions match the donor; the wording after the prefix may differ), and
the advisory lock on the savings ledger (OPS-21).

The planners also recorded items that change no externally observable behavior, so they
need no deviation: the thread-local embeddings handle passed explicitly (API), prompt-memo
internals that keep identical ids (PRM), a per-service tool-order cache (PRM), the unused
`ResponseStore.expand()` helper not ported (RSP), a permanent `fieldsOf` export in
`models.js` (WEB), the GLM-family split of the engine conformance suite (ENG), and fixtures
replacing tests that read engine sources (ENG, OPS; ledger reason `engine-source-reads`).
A reviewer who finds an observable effect in any of them adds it to the deferred table
above as a new proposal for the owner.
