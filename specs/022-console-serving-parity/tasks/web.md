# Task detail: Dashboard, front-end Phase 1

Feature 022, PulsarMLX Console. This file gives the full specification of each work package
with the prefix `WEB-`. The task list, the milestone order and the binding cross-cutting
decisions are in [`../tasks.md`](../tasks.md); **a binding decision or a reconciliation
there overrides any conflicting sentence in this file**.

Provenance: rendered without paraphrase from the planning records of 2026-11-14 (one planning
agent per subsystem, reading the pinned donor source). Path shorthand: `MAYA` is the pinned
project-maya checkout (commit `7e68a30f`), `ORIGIN` is this repository at `main` when the plan
was written. Sizes are estimates. Donor names such as `MAYA_*` variables describe the donor;
the product names are in [`../contracts/naming.md`](../contracts/naming.md).

## Subsystem summary

The Phase 1 front end is project-maya's no-build dashboard: 37 static files in serve/web. It has 14 hand-written ES modules (5,489 lines), a vendored Preact 10.29.8 + htm 3.1.1 bundle, 7 CSS files, an HTML shell, a 65-symbol Lucide sprite, Outfit fonts, PNG icons, four lobe-icons vendor logos and a manifest. In this increment it is adapted and served by the new Rust server from console/web, compiled into the binary. Full parity means three things. First, every view (Chat, Models with engine-settings editor, catalog/pull and leftovers, Monitor with GPU memory map and NVML cards, eight-page Settings, Saved panel, Turbo, search, phone layout) behaves as at 7e68a30f. Second, the page drives the Rust server through the same roughly 35 routes, the SSE format with strata_* extensions, the resume/cancel protocol and the restart-following protocol. Third, browser storage, URL, export and theming contracts stay the same. Only the deliberate deviations listed are approved changes. About half the JavaScript (Models, Monitor GPU map, NVML cards, Turbo, About facts) is written for NVIDIA/AMD multi-GPU. It is kept intact and checked against fixture-driven telemetry profiles and fake model configs, and labelled unverified on real hardware. A new Apple Silicon Monitor view (unified memory, memory pressure, SSD expert streaming, thermal state) is added beside it, chosen by an additive platform field. Every screen carries a visible synthetic-backend label, as D3 requires. Rebranding replaces the Maya name, logo, icons, vendor logos, sponsor line, storage prefixes and download names with a neutral identity, all held in one brand module. Provenance headers, NOTICE.md and a served notices file carry the MIT, Apache-2.0, ISC and OFL obligations. Because the Rust server sets the headers, the plan adds security hardening: a strict per-request CSP and related headers, the inline boot script removed, a sanitizer gate on every innerHTML sink, and an HTML preview moved to its own sandboxed route. Testing keeps project-maya's Node-driven page-logic oracle (about 26 test methods re-hosted in a Rust harness) and translates the static-route and offline tests into Rust. It adds a WebDriver end-to-end suite written against roles and labels, so Phase 2 can reuse it. Finally, the UI-to-server contract is written as Markdown plus JSON Schemas plus golden fixtures under specs/022-*/contracts/ui-server. It is the target for the Phase 2 Rust/WebAssembly rewrite, recorded now in the roadmap.

## Build order proposed by the planner

- WEB-01 (first; pure asset and copy work, no server needed)
- WEB-02 and WEB-05 in parallel (WEB-05 is written from upstream source and needs no running server)
- WEB-03 and WEB-04 in parallel (both need only WEB-01/02; WEB-04 also hosts WEB-03's Node corpus, so merge WEB-04's harness first or land both in the same review window)
- WEB-06 (once the HTTP, chat SSE, resume, MCP and attach server packages from other subsystems are merged)
- WEB-07, WEB-08, WEB-09 and WEB-10 in parallel, each gated on its server-side counterpart (host sampler and fixture telemetry; the manage subsystem plus supervision; the settings, savings and MCP routes)
- WEB-11 (last Phase 1 package; the conformance gate and parity matrix)
- WEB-P2-01, then WEB-P2-02, then WEB-P2-03 (a later increment; recorded in the roadmap by WEB-05)

## Work packages

<a id="web-01"></a>
### WEB-01 Asset import, provenance, licences and neutral identity

- **Milestone:** M8
- **Rust target:** console/web/ (served files, flat, same names as upstream so /web/<name> URLs are unchanged), console/web/fonts/, console/web/LICENSES/ (not served), console/xtask (dev-only: icon rasterizer and notices assembler), console/crates/console-web/tests/brand_audit.rs; NOTICE.md (new section); docs/upstream/PROJECT_MAYA.md (web section; shared file, coordinated with the lead)
- **Platform:** platform-neutral
- **Risk:** medium. About 400 lines of JS/CSS copy edits across 20 files. Renaming identifiers that tests import (MayaMark, exports) must be mirrored in WEB-04. The final name and logo are owner decisions, so the brand module keeps that a one-file change. The Apache-2.0 text must be copied from a verified local source and not reproduced from memory.
- **Depends on:** nothing
- **Estimated size:** 250-400 (xtask icon render + notices assembly ~200, brand audit and licence tests ~150) lines of code; 150-250 lines of tests
- **New dependencies:** xtask only (not linked into pulsar-console): resvg (pinned exact, with its usvg/tiny-skia closure) for SVG to PNG; alternatively the owner supplies PNGs and resvg is not added; sha2 =0.10.9 (xtask/test, already used in the PulsarMLX root lock)
- **Donor sources:** MAYA/serve/web/* (all 37 files); MAYA/LICENSE:1-21 (two copyright lines); MAYA/README.md:347-381 (ownership, credits); Maya-name sites: app.js:126, md.js:237, server.js:235,279-307,354-395, lib.js:5-6,28-46, chats.js:79,106,144,182,734,745, models.js (37 lines incl. 52-53,91-119,237,251,624-664,700-809,956-1074), monitor.js:38,102-103,375,396,491, settings.js:48,96,116-121,271,280,360-406,432-456, sidebar.js:8,146,158,279-303, state.js:8,108-130,257-258, turbo.js:48,71,82,97, ui.js:12-13, tokens.css:1-30, components.css:1,34-35, app.css:1,14,68,182,251,289, settings.css:1,36, models.css:1,140, monitor.css:1, index.html:7,21-29,34, manifest.webmanifest:2-4; sprite.svg:3,68 (i-stop, i-maya); logo-{glm,deepseek,minimax,qwen}.svg; icon-{32,180,192,512}.png (icon-512 is byte-identical to assets/maya-logo.png)

**Behaviors to reproduce**

- Copy byte-identical, with recorded SHA-256 in docs/upstream: preact.js, fonts/outfit-latin-wght.woff2, fonts/outfit-latin-ext-wght.woff2, fonts/OFL.txt, LICENSE.lucide.txt. Copy CSS and JS files as the adaptation base.
- New module web/brand.js is the single source of identity strings. It holds the product display name (placeholder 'Pulsar Console' until the owner decides), the short name, the storage prefix 'pulsar.', the IndexedDB name 'pulsar-console', the download prefixes ('pulsar-code.<ext>', 'pulsar-chat-<stamp>.md'), the DOM event prefix ('console:context'), setup and start command hints for the console binary, and SUPPORT_URL = null. Every former Maya string is rewritten to use brand.js or neutral wording.
- Every adapted file carries a header comment: 'Adapted from project-maya serve/web/<file> at 7e68a30f (MIT). Copyright (c) 2026 Peasant Smith and the Project Maya contributors; Copyright (c) 2026 Niko1221 and the Strata contributors.' It also states the changes in one line.
- localStorage keys keep their suffixes (theme, scheme, side-open, folders, folders-open, apikey, model, sampling, sampling_glm53, sampling_<family>, turbo_<prefsKey>, gpu-open, chats-fallback) under the new prefix. The sessionStorage key 'deleted' gets the new prefix. IndexedDB keeps store 'chats' with keyPath 'id' and version 1. The record schema is unchanged.
- The legacy 'strata.' read fallback, the 'maya.ui-theme' removal and the 'strata.chat' cleanup are dropped (see deviations). clearBrowser() clears '<prefix>*' keys except theme and scheme, as upstream does.
- Remove the sponsor heart (sidebar.js:279-281), the SupportLine (settings.js:375-377) and SUPPORT_URL. Layout must not leave empty slots.
- Replace the project logo. A new neutral SVG mark (web/brand-mark.svg, original work) is used as the sidebar brand (renamed MayaMark to BrandMark), the favicon (icon-32.png), apple-touch-icon (icon-180.png) and manifest icons (192, 512). The PNGs are rendered from the SVG by the xtask, which is deterministic and checked by a dimension test.
- Replace the sprite symbol i-maya with i-brand (the new mark). Keep i-stop (project-maya's own drawing, MIT, attributed) and the 63 Lucide symbols unchanged.
- Replace the four lobe-icons vendor marks with neutral in-house family glyphs: web/family-glm.svg, family-deepseek.svg, family-minimax.svg, family-qwen.svg (a letter tile per family, no vendor shapes or colours). modelLogo() keeps the same regex table and return shape {src, mono}.
- Manifest: name and short_name from the brand; a neutral description ('Local model console (synthetic backends)'); start_url and scope '../' unchanged; display standalone; colours unchanged; icons 192 and 512.
- index.html: new title, theme meta unchanged, noscript text rebranded. The inline script is handled in WEB-03. This package only renames the storage keys it reads.
- CSS: rename --maya-side, --maya-read and .maya-mark to --app-side, --app-read and .brand-mark. No visual change.
- Quant names (Maya-XS, Maya-L and so on) appear only in comments in JS. They are removed. The page shows model_label exactly as the server sends it.
- Engine env-var names shown in the UI (models.js:538 MAYA_EXPERT_RAM_GB, monitor.js:396 MAYA_DS4_DRAFT_DEV) are moved into one ENV_NAMES table in brand.js. They take whatever prefix the engine-contract subsystem fixes.
- console/web/LICENSES/ holds: project-maya-MIT.txt (verbatim upstream LICENSE), preact-MIT.txt, htm-Apache-2.0.txt (full Apache-2.0 text, taken verbatim from a local copy such as a LICENSE-APACHE in the cargo registry, never retyped), lucide-ISC.txt (copy of LICENSE.lucide.txt), outfit-OFL-1.1.txt (copy of fonts/OFL.txt), and a README naming which served files each covers.
- The xtask assembles web/notices.txt from LICENSES/ in a fixed order. A test fails if notices.txt is stale.
- NOTICE.md gains a project-maya section: repository, pinned commit 7e68a30f, both copyright lines, MIT, what was adapted (dashboard JS/CSS/HTML) versus reimplemented, and a statement that project-maya does not endorse PulsarMLX. It also records the Preact, htm, Lucide and Outfit entries.

**Parity tests**

MAYA/serve/test_dashboard.py Offline.test_the_vendored_code_keeps_its_notices (1) is re-expressed in Rust. It must find the Preact MIT and htm Apache notices in preact.js, ISC in LICENSE.lucide.txt, the fonts/OFL.txt file, and no fonts.googleapis in index.html. PageLogic.test_about_has_the_support_line_always_and_the_update_card_none (1) is inverted: About has no support line and no sponsor link, and the UpdateCard is unchanged. New tests: brand_audit.rs scans console/web, case-insensitive, for 'maya', 'mw00', 'sponsors', 'Project Maya', quant names /Maya-(XS|S|M|L|XL)/, 'lobe-icons', 'Z.ai' and vendor <title>s. The only allowed hits are LICENSES/, notices.txt, provenance header lines and an explicit allowlist (the wire names strata_mcp, strata_resume, strata_level_default, v1/strata/stream, v1/strata/cancel). A PNG dimension test and a notices-freshness test complete it.

**Definition of done**

console/web holds all served assets. preact.js, the fonts, OFL.txt and LICENSE.lucide.txt match recorded SHA-256 values. No Maya, mw00, sponsor, quant or vendor-logo string survives outside the allowlist, and brand_audit.rs passes. Every adapted file has the provenance header. LICENSES/ and notices.txt exist, and the freshness test passes. NOTICE.md and the docs/upstream entry name the commit and both copyright holders. A reviewer opens the page from disk and sees the neutral identity, with no broken image or icon references.

<a id="web-02"></a>
### WEB-02 console-web crate: embedded assets, static routes, caching and security headers

- **Milestone:** M8
- **Rust target:** console/crates/console-web: build.rs (asset table), src/assets.rs, src/routes.rs, src/headers.rs (CSP builder, security headers), src/devdir.rs. It exposes a transport-agnostic API on http 1.x types that console-http mounts.
- **Platform:** platform-neutral
- **Risk:** low. Main risk is drift between the embedded table and the dev-dir path. Both go through one whitelist function. The CSP must be proven against the real page in WEB-03/WEB-06 before it is enforced.
- **Depends on:** WEB-01; HTTP subsystem: router/mount point in console-http, JSON 404 error body shape, Host allowlist value; config subsystem: name of the dev web-dir option
- **Estimated size:** 700-1000 lines of code; 400-600 lines of tests
- **New dependencies:** http =1.x (same pin as console-http); bytes =1.12.1; sha2 =0.10.9 (build-dependency); regex (dev-dependency only, pinned exact) for the offline scan; may be dropped if a hand-written scanner is preferred
- **Donor sources:** MAYA/serve/server.py:5934-5988 (/web/<name> whitelist, /web redirect, /fonts), 6012-6018 (GET /), 5405 and 6715-6722 (HTTP/1.0 note), 5811-5819 and 5946-6049 (static routes skip auth); contract 'Static dashboard files' in READERS/maya/maya-web.json; MAYA/serve/test_server.py:1694-1762; MAYA/serve/test_dashboard.py:662-687

**Behaviors to reproduce**

- build.rs walks console/web at compile time and emits a static table: published name, include_bytes!, content type, strong ETag (hex SHA-256 prefix) and byte length. Any file not on the whitelist fails the build, so stray files cannot ship.
- GET / returns index.html with 'text/html; charset=utf-8' and no authentication. HEAD is answered the same way without a body (HEAD is additive; upstream has no do_HEAD).
- GET /web/<name> serves only names without '/' whose extension is .css, .js, .svg, .png or .webmanifest. The single extra name notices.txt is a deviation. Content types: text/css; charset=utf-8, text/javascript; charset=utf-8, image/svg+xml, image/png, application/manifest+json. /web/index.html, /web/test.py, licence .txt files and anything else return 404 with the server's JSON error body, which comes from the HTTP subsystem's error shape.
- GET /web and /web/ return 302 with Location './' and '../' respectively, keeping the query ('/web/?q=hi' goes to '../?q=hi').
- GET /fonts/<name>.woff2 serves the fonts with font/woff2 and Cache-Control: max-age=86400. Any other extension or a missing file returns 404.
- The path is not percent-decoded before matching, so '/web/..%2Fserver.py' and '/fonts/..%2F..%2Fsetup.py' are 404. Exact-string matching against the table means traversal is impossible by construction.
- HTML and assets send Cache-Control: no-cache (upstream parity) plus the ETag. If-None-Match returns 304 with no body (the validator is a deviation; upstream re-sends everything).
- Security headers on every response this crate produces. Content-Security-Policy is built per request: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; media-src 'self' data: blob:; font-src 'self'; connect-src 'self' <scheme>://<validated-host>:*; manifest-src 'self'; frame-src 'self'; worker-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'. Also: X-Content-Type-Options: nosniff, Referrer-Policy: no-referrer, Permissions-Policy: camera=(), microphone=(), geolocation=(), usb=(), Cross-Origin-Opener-Policy: same-origin, Cross-Origin-Resource-Policy: same-origin. connect-src carries a port wildcard on the request's validated Host, which lets the port-move flow (server.js:298-301) probe the new port. The host value comes from the HTTP subsystem's Host allowlist and is never echoed unvalidated.
- A helper exports the same header set for the API subsystem's JSON responses (nosniff and Referrer-Policy only, never CSP on API bodies).
- Dev mode: a config/CLI option (name set by the config subsystem) serves the same whitelist from a directory on disk instead of the embedded table. Same headers, ETags computed at read time. Off by default and logged loudly when on.
- The /preview route content and headers are supplied by WEB-03; this crate provides the CSP-variant plumbing.
- Relative-URL property kept: nothing in the server rewrites asset paths, so the page works behind a path-prefix proxy.

**Parity tests**

MAYA/serve/test_server.py test_page_and_files, test_home_screen_start_url, test_only_the_app_files_are_served (3 methods, about 70 lines) become Rust tests on http::Request/Response in console-web, plus one integration test through console-http once it exists. MAYA/serve/test_dashboard.py Offline.test_nothing_loaded_from_the_network (1) is re-expressed with the same regex over console/web (.js, .css, .html, .svg, .webmanifest, w3.org exempt). New tests: header presence and exact CSP string, connect-src host validation (a forged Host is never reflected), 304 on matching ETag, HEAD, build-time whitelist rejection (trybuild-free: a unit test of the table generator function), dev-dir parity with the embedded table.

**Definition of done**

cargo test -p console-web passes the three translated static-route tests, the offline scan, header and CSP tests and 304/HEAD tests. pulsar-console (through console-http) serves the page from the embedded table with no files on disk. A reviewer can run curl -I against /, /web/app.js, /fonts/outfit-latin-wght.woff2 and /web/..%2Fx and see the documented codes and headers.

<a id="web-03"></a>
### WEB-03 CSP compatibility and model-output hardening (page side and the preview route)

- **Milestone:** M8
- **Rust target:** console/web/{boot.js (new), guard.js (new), md.js, ui.js, chat-view.js, settings.js, app.js, index.html, sprite.svg, components.css, preview.html (new, served only at /preview)}; console/crates/console-web/src/preview.rs (route plus its own CSP)
- **Platform:** platform-neutral
- **Risk:** medium. CSP breakage only shows in a real browser: SVG <use> shadow-tree styles, Preact style props (CSSOM cssText is allowed), Trusted Types interaction with Preact's dangerouslySetInnerHTML. A Content-Security-Policy-Report-Only fallback switch in console-web lets enforcement be rolled back without a code change while WEB-06 proves zero violations. Golden-output equality with upstream md.js keeps rendering parity.
- **Depends on:** WEB-01; WEB-02
- **Estimated size:** 150-300 lines of code; 350-500 (Node .mjs corpus + Rust header tests) lines of tests
- **Donor sources:** MAYA/serve/web/index.html:20-34 (inline theme script, noscript inline style); md.js:75-84 (escape-then-format), 166-179 (links), 195-216 (patchHtml/patchCode innerHTML), 233-253 (download, previewHtml srcdoc sandbox); ui.js:146-190 (DialogHost body innerHTML and node host); chat-view.js:109-127, 205-243 (tool blocks as HTML strings, body.innerHTML); settings.js:298 (dangerouslySetInnerHTML codeBlock); sprite.svg (inline style attributes on every symbol); app.js:107-126 (?q= auto-send, window.maya)

**Behaviors to reproduce**

- Move the theme-before-first-paint logic from the inline script to web/boot.js, loaded as a classic non-module <script src> in <head> before the stylesheets. Behaviour is the same: it reads '<prefix>theme' (dark/light/system, default dark) and '<prefix>scheme' (violet) and sets data-theme and data-scheme before first paint.
- Replace the noscript inline style with a class in components.css.
- Rewrite the sprite: the per-<g> style='stroke-width:var(--st-icon-stroke,1.75)' and the root style='display:none' become a CSS rule in components.css (.st-icon g{stroke-width:var(--st-icon-stroke,1.75)}) and a hidden attribute. Rendered icons stay pixel-identical, which WEB-06 checks with a screenshot diff.
- Add web/guard.js, a small allowlist sanitizer with no library. It parses through a <template> and keeps only the tags and attributes md.js, the tool blocks and dialog bodies legitimately emit (p, br, h1-h6, ul, ol, li, blockquote, pre, code, span, div, strong/b, em/i, del, a[href^=http(s):][target=_blank][rel], table, thead, tbody, tr, th, td, hr, svg/use[href^='web/sprite.svg#'], button[data-code-*][type][aria-*][title], plus class and data-lang). Everything else is dropped: event-handler attributes, style, script, iframe, javascript: URLs. All innerHTML sinks go through it: patchHtml, patchCode, dialog body, settings code block, chat-view body writes.
- Where the browser supports Trusted Types, guard.js registers a 'default' policy that applies the same sanitizer, and the CSP adds require-trusted-types-for 'script'; trusted-types default. Browsers without Trusted Types ignore the directive and still get the explicit guard calls.
- md.js keeps its escape-first order unchanged. Emitted HTML for any input not containing raw HTML is byte-identical to upstream; the Node tests in WEB-04 compare the two.
- HTML preview leaves srcdoc (a srcdoc frame inherits the page's strict CSP, which would block the preview's own scripts). The frame is now an <iframe src='preview' sandbox='allow-scripts allow-pointer-lock allow-modals'> with no allow-same-origin. /preview serves a fixed shell. Its CSP: sandbox allow-scripts allow-pointer-lock allow-modals; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; media-src data: blob:; font-src data:. It accepts exactly one postMessage from its parent and document.write()s the model's code into itself. The parent checks event.source on the reply handshake.
- The preview dialog keeps upstream's warning text and adds an 'Allow internet in this preview' control (deviation). It reloads the frame from /preview?net=1, whose CSP adds https: to script-src, style-src, img-src, font-src and connect-src. That reproduces upstream's three.js-CDN behaviour on explicit opt-in.
- /?q=<text> no longer auto-sends (deviation). The text is placed in the composer, the query is stripped from the address as upstream does, focus moves to the composer, and an info toast says 'Press Enter to send'. MCP tools are never engaged without that keypress.
- window.maya is removed. With '#debug' in the address, window.console_debug = {S, chatView} is exposed instead.
- Links from Markdown keep target=_blank rel='noopener noreferrer'.
- Download of a code block uses the brand prefix (WEB-01) and stays a blob: URL. That is allowed: navigation and download are not governed by connect-src.

**Parity tests**

Upstream has no direct tests for these sinks. A new Node XSS corpus (about 40 cases, under console/crates/console-web/tests/node/md_xss.mjs) runs md.js markdown()/codeBlock() in the WEB-04 harness. It asserts that no output contains event attributes, javascript: or unescaped tags, and that outputs equal upstream md.js outputs for a 60-case golden corpus recorded once from the unmodified upstream file. guard.js unit tests run under Node with a minimal template shim; DOM-dependent checks run in WEB-06. Rust tests check the /preview headers and that the main CSP has no 'unsafe-inline' and no 'unsafe-eval'.

**Definition of done**

index.html contains no inline script or style. The sprite has no style attributes. Every innerHTML sink calls guard.js. The XSS corpus and golden-equality Node tests pass. /preview returns the documented CSP. WEB-06's browser run (or an interim manual Safari and Chrome check recorded in the PR) reports zero securitypolicyviolation events across the chat, settings, monitor and models views. The ?q= and window-global deviations behave as described.

<a id="web-04"></a>
### WEB-04 Node page-logic oracle re-hosted in Rust

- **Milestone:** M8
- **Rust target:** console/crates/console-web/tests/page_logic.rs (harness) plus console/crates/console-web/tests/node/*.mjs (one script per upstream test group); console/web/models.js (export fieldsOf for real)
- **Platform:** platform-neutral
- **Risk:** low. Node becomes a CI tool, which is an owner decision. GitHub macOS runners ship it, and the tests skip locally without it. Upstream expectations embed copy, so later copy edits must update both.
- **Depends on:** WEB-01; WEB-03 (md.js golden corpus uses this harness); engine-contract subsystem: machine-readable INFO/STAT key list fixture
- **Estimated size:** 300-450 lines of code; 700-1000 (.mjs scripts plus Rust assertions) lines of tests
- **New dependencies:** serde_json (dev-dependency, already in the workspace); Node.js on PATH as a test tool only (not a dependency; no npm, no packages)
- **Donor sources:** MAYA/serve/test_dashboard.py:690-926 (PAGE_STUBS, PageLogic 8 methods); MAYA/serve/test_turbo.py:258-303 (turbo-core.js under node, 5 methods); MAYA/serve/test_glm_dsa_models.py:315-420 (models.js fieldsOf via a temporary appended export, turbo.js, 3 methods); MAYA/serve/test_glm_dsa_serve.py:592-700 (chats.js apiMessages/addFiles, about 5 methods); MAYA/serve/test_glm_dsa_think_budget.py:502-640 (chats.js levelLeftAtDefault and friends, 2 methods); literal-source assertions: MAYA/serve/test_server.py:1719-1735, MAYA/serve/test_glm_dsa_api.py:534-545

**Behaviors to reproduce**

- The harness writes nothing into console/web. It runs `node <script>.mjs <file-URL of console/web>` with the upstream-style browser stubs (matchMedia, localStorage, document proxy, location) and parses the last stdout line as JSON. The test is skipped with a visible message when node is absent, and fails when CONSOLE_REQUIRE_NODE=1 is set (CI).
- models.js exports fieldsOf permanently, so the upstream run-time appendFileSync mutation (test_glm_dsa_models.py:332) is gone.
- Ported PageLogic assertions, with the storage prefix changed to the brand prefix: per-model preference keys and the GLM-5.3 one-time migration; thinking-pill geometry for every family and level; freeAdvice tensor-parallel text, with the env-var name taken from brand.js ENV_NAMES; speculationView off/waiting/kept states; tierShares bytes; tierSet/tierTip naming for Qwen and GLM; ctxStopsIn/ctxStops/ctxHint strings.
- Ported turbo-core assertions: fastestThinking, turboEnter/turboLeave exact restore, nothing chosen before, chat level changed during Turbo not overwritten, CODING_IDEAS content.
- Ported models.js fieldsOf assertions for GLM-5.3, Flash and the Turbo button state.
- Ported chats.js assertions: apiMessages history shape (kept thinking per tool round, text-only attachments) and levelLeftAtDefault/levelPicked marking (strata_level_default).
- Literal-source assertions kept: sidebar.js contains 'S.health.model_label || modelName(S.health.model)'; chats.js reads S.health.max_text_file and has no MAX_TEXT_FILE. monitor.js eng.* reads are a subset of the engine INFO key list exported by the engine-contract subsystem as a fixture file (the source-of-truth list moves from generate.cpp, which is not ported).
- Every ported test cites its upstream file and method in a comment, so the reviewer can diff the expectations.

**Parity tests**

About 26 upstream methods: test_dashboard.py PageLogic (8), test_turbo.py node class (5), test_glm_dsa_models.py node class (3), test_glm_dsa_serve.py node class (about 5), test_glm_dsa_think_budget.py node class (2), test_server.py literal halves of test_the_model_shown_model_first and test_text_file_limit_follows_the_context (2), test_glm_dsa_api.py test_the_monitor_reads_only_what_the_engine_prints (1). Expectations are kept verbatim except for the brand prefix and env-var names.

**Definition of done**

cargo test -p console-web --test page_logic passes with CONSOLE_REQUIRE_NODE=1 on macOS. Each of the about 26 upstream methods maps to a named Rust test in a table in the test file. No test writes into console/web. Running without node prints the skip reason and passes.

<a id="web-05"></a>
### WEB-05 UI-to-server contract documents, JSON Schemas and Phase 2 roadmap entry

- **Milestone:** M8
- **Rust target:** specs/022-<name>/contracts/ui-server/ (README.md index, routes.md, streams.md, restart-protocol.md, storage.md, urls-and-export.md, theming-and-icons.md, markdown-subset.md, security.md, schemas/*.schema.json, fixtures/*.json); docs/roadmap/CONSOLE_FRONTEND_ROADMAP.md (new file); console/crates/console-web/tests/contract_lint.rs
- **Platform:** platform-neutral
- **Risk:** medium. The contract is large and partly owned by other planners' packages, so it must be written from upstream source first and amended when server packages land. The route-coverage scan keeps it honest. Permissive schemas trade strictness for upstream fidelity, so required-field lists matter.
- **Depends on:** WEB-01; Responses subsystem: JSON Schema validator usable as a dev-dependency; HTTP and API subsystems: confirmation of route shapes and the additive fields
- **Estimated size:** 100-250 lines of code; 150-250 (plus about 2,000-3,000 lines of Markdown and about 1,500 lines of JSON Schema and fixtures) lines of tests
- **New dependencies:** console-responses (dev-dependency, for its JSON Schema validator) or, if it lacks needed keywords, an exactly pinned validator crate approved by the lead
- **Donor sources:** READERS/maya/maya-web.json contracts (35 entries: static files, auth/CSRF/CORS, error shapes, /health, /metrics, chat completions request with strata_* fields, SSE format, strata_mcp events, /v1/strata/stream, /v1/strata/cancel, /api/tokens, /attach, /mcp, /api/context, /api/port, /api/thinking-budget, /settings, /api/turbo, /api/models*, /models/load|unload, /api/catalog, /api/pull*, /api/savings*, /api/update, /api/report, restart-following protocol, browser storage, IndexedDB schema, URL contract, export format, design tokens, sprite, manifest, Markdown subset, advertised public endpoints); primary: MAYA/serve/web/server.js, chats.js:400-660, models.js, settings.js, sidebar.js:126-266, MAYA/serve/server.py do_GET 5934-6139, do_POST 6160-6297

**Behaviors to reproduce**

- Every route the page calls is listed with method, query, request schema, response schema, status codes (200, 202, 302, 400, 401, 403, 404, 415, 503 with Retry-After: 30), error body shape, auth rule (none for page, assets and /health; Bearer when configured; Origin-equals-Host and application/json on settings writes) and the client's polling cadence. Cadences: metrics every 1 s, every 5 s when hidden; mcp every 10 s on Monitor and Tools, 3 s while starting; health every 2 s during reload and turbo; 3 s during update; the 2 s by 300 port probe; pull status cadence.
- Every route also records which client function calls it (file:function) and how the client degrades when it is missing (older-server tolerance list).
- The SSE contract records 'data:' framing, keep-alive comments, the id on the first chunk becoming the job id, delta.content and delta.reasoning_content, usage on the last chunk, timings, error chunks, the strata_mcp event objects, [DONE], and resume via /v1/strata/stream?id&from=n with its 404 meaning 'gone'.
- The restart-following protocol records the 202 responses, the health polling, the status values 'reloading' and 'updating', the reload states waiting/running/done/failed, and the page-reload triggers.
- Browser storage: every localStorage and sessionStorage key with its JSON shape. The IndexedDB 'chats' record schema is declared a compatibility contract that Phase 2 must read unchanged.
- URL contract: #monitor, #models, #settings, #about, #debug, ?q= (prefill semantics). Chat export Markdown format. Design tokens (--st-* names, two themes, two schemes). Sprite symbol ids. Manifest. The Markdown subset md.js renders, including the code-block data attributes.
- Additive fields introduced by this increment are marked as extensions: health.backend ('synthetic' or 'fake-process'), hardware_static.platform, hardware.apple.*.
- JSON Schemas (draft 2020-12, permissive on unknown fields because upstream objects carry many) for /health, /metrics (engine, live, tiers, gpu_map, hardware, hardware_static, history, requests, totals, loop_guard, reload, storage) and every /api/* response the page reads.
- contract_lint.rs checks that every schema parses and that every fixture validates against its schema, using the validator from the Responses subsystem. A route-coverage scan extracts every fetch( and api( literal from console/web/*.js and fails if a route is not documented in routes.md.
- docs/roadmap/CONSOLE_FRONTEND_ROADMAP.md records the two phases. Phase 1: the adapted JS dashboard, this increment. Phase 2: the Rust/WebAssembly rewrite targeting this contract, with the WEB-P2-* outline, the coexistence plan and the data-compatibility rule. Both phases are labelled synthetic-backends-only until real engine attachment is approved.

**Parity tests**

Upstream has no contract tests. Upstream HTTP tests that pin response fields feed the schemas: test_dashboard.py Dashboard.* (17), Port.* (2), test_server.py test_metrics, plus the route tests in test_models.py, test_model_api.py, test_savings.py, test_update.py, test_turbo.py and test_think_budget.py. The schemas cite them. New: contract_lint.rs (schema parse, fixture validation, route coverage).

**Definition of done**

The contract directory exists with all listed documents. Every page-called route appears in routes.md with schema links, and the coverage scan passes. Schemas parse and validate the recorded fixtures. The roadmap file names Phase 2 concretely. A reviewer can pick any fetch in console/web/*.js and find its documented request, response, errors and degradation.

<a id="web-06"></a>
### WEB-06 Browser end-to-end harness and chat-core scenarios

- **Milestone:** M8
- **Rust target:** console/crates/console-web-e2e (publish=false, not a default workspace member): harness (spawn pulsar-console with the in-process fake engine on an ephemeral port, temp state dir), WebDriver session, scenario tests
- **Platform:** platform-neutral
- **Risk:** high. Real-browser tests are slow and can be flaky. Safari needs safaridriver enabled with admin rights, and touch emulation varies by driver. Mitigations: deterministic fake engine timing, explicit waits on accessible state rather than sleeps, the suite kept opt-in for local runs and required in a dedicated CI job.
- **Depends on:** WEB-02; WEB-03; core subsystem: in-process fake engine with a scripted mid-stream drop; HTTP and API subsystems: /v1/chat/completions SSE with strata_resume/strata_mcp/strata_level_default, /v1/strata/stream, /v1/strata/cancel, /api/tokens, /health, /metrics; MCP subsystem: /mcp and the tool loop with a fake MCP server; attachments subsystem: POST /attach
- **Estimated size:** 600-900 (harness, process control, WebDriver helpers, CSP collector) lines of code; 700-1000 lines of tests
- **New dependencies:** fantoccini (pinned exact, default-features=false, no TLS backend: WebDriver over localhost HTTP) — dev-only crate; tokio and serde_json (already in the workspace)
- **Donor sources:** MAYA/serve/web/app.js (routing, keyboard, PhonePush), chats.js (send, stream, stop, cancel, resume, edit, regenerate, attachments, export, clear, folders, pins), chat-view.js (thread, tool blocks, reasoning disclosure, composer, context meter, greeting), sidebar.js:16-125, 285-374 (status, chat list, search dialog), ui.js (menus, dialogs, focus traps, toasts), md.js (streaming patcher, code-block buttons, preview); MAYA/serve/test_stream_jobs.py (resume semantics, server side)

**Behaviors to reproduce**

- The harness drives a real browser over WebDriver. On macOS it uses safaridriver (built in; one-time 'safaridriver --enable'). In CI it uses chromedriver plus Chrome where present. The suite is enabled by CONSOLE_E2E=1 and the browser chosen by CONSOLE_E2E_BROWSER.
- Selectors use roles, accessible names and visible text only, never class names. The same suite is meant to run unchanged against the Phase 2 UI.
- Every page installs a securitypolicyviolation listener (injected by the harness through WebDriver execute) and every scenario asserts zero CSP violations and zero uncaught errors.
- Chat: a new chat sends, the answer streams into the thread, the first-chunk job id is stored, and usage and timings show in the answer info line. Stop cancels: POST v1/strata/cancel is sent and the message is marked stopped. Edit and regenerate. Reasoning disclosure with thinkSecs. Markdown rendering and code-block copy, wrap, download and preview, with the preview frame unable to reach parent storage.
- Resume: the harness makes the fake engine's HTTP connection drop mid-answer. The page reconnects via v1/strata/stream?id&from=n and the final text equals the uninterrupted text. A page reload mid-answer resumes from IndexedDB m.pending/m.job. A 404 shows the 'cut off' error.
- MCP tool loop in chat with a fake MCP server: strata_mcp events render writing/running/done tool blocks and a second round is separated by a blank line.
- Attachments: an image as a data URL, a text file read in the browser up to health.max_text_file, a PDF via POST attach, an oversize rejection with the toast text.
- The context meter uses POST api/tokens, falls back to characters/3.5 when the route returns 404, and uses the live count while streaming.
- 503 during reload: the composer waits with the hint text.
- 401: the API-key toast appears, the Settings key field is filled, and requests succeed.
- History in IndexedDB survives a reload. The localStorage fallback of 30 slim chats applies when IndexedDB is unavailable (run in a private window where the browser allows it). Folders, pins, rename, delete, search dialog with ?-free snippets, Markdown export file name and content, and Clear browser data all work.
- Phone layout at 375x812: drawer push, swipe-to-close (touch actions where the driver supports them, otherwise skipped with a note), inert main, Escape closes. Breakpoint switch on resize.
- Keyboard: Cmd/Ctrl+Shift+O new chat, Cmd/Ctrl+K search, Cmd/Ctrl+, settings, Cmd/Ctrl+Shift+S sidebar. Escape order: dialog, search, settings, drawer, edit, stop.
- Theme boot: no flash. The stored theme and scheme are applied before first paint (checked by reading data-theme at DOMContentLoaded through an injected early observer).
- Screenshots of each scenario's end state are saved under the test temp dir for review (not asserted, except the sprite before/after pixel diff from WEB-03).

**Parity tests**

Upstream has no browser tests; the behaviour comes from the JS itself and from the server-side tests that define the routes (test_stream_jobs.py, test_attach.py, test_mcp.py, test_dashboard.py Dashboard.test_chat_gets_503_while_reloading and test_token_count_matches_the_prompt). About 25 scenario tests here.

**Definition of done**

With CONSOLE_E2E=1 the suite passes on macOS Safari and on Chrome. Every scenario asserts zero CSP violations and zero console errors. The mid-stream-drop resume test proves text equality. A reviewer can run one documented command and get screenshots of each scenario.

<a id="web-07"></a>
### WEB-07 Apple Silicon Monitor view and synthetic-backend labelling

- **Milestone:** M8
- **Rust target:** console/web/monitor-apple.js (new), console/web/monitor.css (additions), console/web/monitor.js (composition switch), console/web/settings.js (About facts rows), console/web/sidebar.js and chat-view.js (synthetic badge), console/crates/console-web/tests/node/monitor_apple.mjs, specs/022-*/contracts/ui-server/fixtures/metrics-apple-*.json
- **Platform:** hardware-or-os-specific
- **Risk:** medium. Depends on what the host sampler can read without root: power and GPU residency may need IOReport or powermetrics. The UI tolerates nulls and shows the reason. Real-machine figures are unverified while backends are synthetic, and the badge says so.
- **Depends on:** WEB-01; WEB-05 (schemas for hardware.apple and platform); host subsystem: Apple Silicon sampler producing hardware_static.platform/chip_name/gpu_cores and hardware.apple.{mem_total, mem_used, wired, compressed, swap_used, pressure, gpu_active, cpu, p_cores, e_cores, ssd_read_mb, power_w|null, thermal} plus history series; core subsystem: health.backend value
- **Estimated size:** 50-120 (fixture plumbing only) lines of code; 350-500 (Node + e2e + fixtures) lines of tests
- **Donor sources:** MAYA/serve/web/monitor.js:28-312 (Banners, Throughput, RightNow, ContextCard, Tiers: reused), 489-534 (Hardware cards: CPU, RAM and Disk read carry over), 590-628 (MonitorPage composition); settings.js:430-477 (About facts); sidebar.js:16-35, 267-283 (status card); MAYA/docs/METAL.md:5-16 (upstream's own Metal note: context only)

**Behaviors to reproduce**

- The Monitor picks its hardware section from hardware_static.platform. 'apple' renders the new AppleHardware and UnifiedMemory components in place of GpuMap and the five GPU cards. Every other value, or absence of the field, renders the upstream GPU path unchanged (WEB-08).
- Upstream components that are platform-neutral stay as they are on Apple: Banners (reload and thermal), Throughput (decode/prefill, peak, speculation), RightNow, ContextCard, Tiers, Requests. The 'VRAM hit' stat and tier labels come from a per-platform label table ('In memory' / 'Streamed from SSD' on apple), keeping upstream labels elsewhere.
- UnifiedMemory: one segmented bar of the machine's unified memory from hardware.apple: model weights resident, KV cache, expert cache, other processes, wired, compressed, free. It has a legend and hover tooltip in upstream GpuMap style, and the expandable detail is a sentence per part.
- AppleHardware cards with sparklines from metrics.history: GPU active residency %, unified memory used / total, memory pressure (normal/warn/critical), swap used, CPU % with P/E core counts, SSD read rate (expert streaming), package power W where available (otherwise a dash with the reason 'needs privileged sampler' as provided by the server), and thermal state (nominal/fair/serious/critical).
- A thermal banner appears when the thermal state is serious or critical (the counterpart of the 87 °C GPU banner).
- About facts on apple: Chip (hardware_static.chip_name, e.g. 'Apple M3 Max'), GPU cores, unified memory size, macOS version. These replace the 'GPU: not readable (NVML)' and PCIe rows. On other platforms the upstream rows are unchanged.
- Synthetic labelling (D3): when health.backend is 'synthetic' or 'fake-process', a persistent badge reading 'Synthetic engine — no real model' appears in the sidebar status card, the chat header and the Monitor header. The Monitor subtitle says the figures are generated by a fake engine, and Copy report output is prefixed with the same statement (prefixing is server side; the page shows it).
- Pure functions are exported for testing: memorySegments(hw), pressureTone(level), thermalTone(state), appleFacts(metrics).

**Parity tests**

There is no upstream counterpart (a new view, listed as a deviation). New Node tests (about 10) for the pure functions, run in the WEB-04 harness against fixtures. About 4 WEB-06-style browser scenarios (apple fixture renders, thermal banner, synthetic badge on every view, GPU path unchanged when platform is absent). Upstream PageLogic tierShares/tierTip tests must still pass unchanged.

**Definition of done**

With an apple metrics fixture the Monitor shows the unified-memory bar, the Apple cards and the Apple About facts, with no GPU/PCIe/NVML text. With a GPU fixture it is unchanged from upstream. The synthetic badge appears on chat, monitor, models and settings whenever health.backend is synthetic. The Node and e2e tests pass. Screenshots of both platforms are attached to the review.

<a id="web-08"></a>
### WEB-08 GPU-era Monitor and About paths verified against fixture telemetry (NVIDIA, AMD, Windows, multi-GPU)

- **Milestone:** M9
- **Rust target:** console/web/models.js (backend label), console/web/settings.js (engine label table via brand.js), specs/022-*/contracts/ui-server/fixtures/metrics-{nvidia-1gpu,nvidia-tp2,nvidia-8gpu-plain,amd-hip,windows-apu}.json, console/crates/console-web/tests/node/gpu_paths.mjs, console-web-e2e scenarios
- **Platform:** hardware-or-os-specific
- **Risk:** medium. Fixtures must come from the ported readers so the UI and server stay in step. This needs the host subsystem's fixture mode first. Verified only against fixtures and labelled so.
- **Depends on:** WEB-04; WEB-06; host subsystem: NVIDIA/AMD/Windows readers behind traits with fixture providers selectable by config, and gpu_map computation; manage subsystem: /api/models backend field values for fake configs
- **Estimated size:** 60-150 lines of code; 400-600 (Node, e2e, fixture JSON) lines of tests
- **Donor sources:** MAYA/serve/web/monitor.js:28-50 (Windows page-file banner, 87 °C banner), 313-486 (GPU_PARTS, gpuLayers, gpuSegs, GpuStats, gpuDetail, freeAdvice, GpuMap incl. the plain NVML fallback at 5 or more GPUs), 489-534 (eight hardware cards incl. PCIe gen/width, per-GPU sub-lines), 590-628 (gpuEach logic); settings.js:48, 421-477 (gpuNames, engine labels, KV format tables, PCIe facts); models.js:804, 993 (HIP/CUDA label); MAYA/serve/test_dashboard.py GpuMap.* (15), NvmlPids.* (2), GpuRelease.* (4), ContextCost.* (2) (server side, owned by the host subsystem; used here as fixture sources)

**Behaviors to reproduce**

- All upstream GPU UI code stays in place and is reached whenever the server reports GPU telemetry (gpu_map present, or hardware.gpus with 5 or more entries for the plain fallback).
- Each part type in GPU_PARTS renders with upstream tooltip and detail sentences: weights, KV cache, activations, prompt buffers, tensor-parallel copies, drafter, expert pool, helper experts, vision encoder, CUDA and the rest, other programs, free. 'processes that are not Maya's' becomes the brand wording.
- freeAdvice texts appear for the tensor-parallel and plain cases (covered by WEB-04 Node tests).
- The eight hardware cards show values and sub-lines for single and multi-GPU, gpuEach suppression of per-card sub-lines when the GPU card rows carry them, mixed PCIe links, and the 'needs psutil' disk note replaced by the brand-neutral reason the host subsystem sends.
- Banners: the Windows page-file banner appears when engine.gpu_commit_capped_gb > 0. The temperature banner appears at 87 °C or above per GPU.
- About: gpuNames aggregation ('2 × Tesla V100', mixed lists), engine-kind labels (neutral names replacing 'maya-ds4'/'maya-mm3'), KV format tables for glm-fast, mm3 and others, PCIe facts.
- Backend label fix (deviation): 'hip' shows HIP, 'cuda' shows CUDA, 'metal' shows Metal, 'synthetic' and 'fake' show Synthetic, and an unknown value shows the raw value rather than CUDA.
- Each GPU fixture is produced by the host subsystem's fixture telemetry providers (NVML, AMD sysfs, Windows DXGI/PDH readers fed recorded fixtures) through the real /metrics route, not hand-edited, so the UI is exercised end to end through the ported readers.
- The Monitor subtitle on these fixtures reads 'fixture telemetry — unverified on real hardware' when the server marks telemetry as fixture-sourced (an additive field).

**Parity tests**

Server-side arithmetic comes from upstream test_dashboard.py GpuMap.*, NvmlPids.*, GpuRelease.* and ContextCost.* (owned by the host subsystem). UI side: PageLogic.test_free_room_a_tensor_parallel_partner_cannot_use_promises_no_experts and the tier tests (in WEB-04), plus new Node tests (about 8) of gpuLayers/gpuSegs/gpuNames/the label tables over the five fixtures, plus about 5 e2e scenarios rendering each fixture with zero console errors and asserting key visible texts.

**Definition of done**

All five GPU fixtures render the GPU map, cards, banners and About facts without errors, with text matching upstream wording except brand words. The backend label table is fixed. Node and e2e tests pass. The review includes screenshots of the 1-GPU, TP-2 and 8-GPU plain views.

<a id="web-09"></a>
### WEB-09 Models page, engine-settings editor, catalog and pull, leftovers, Turbo, update, port and context restart flows

- **Milestone:** M8
- **Rust target:** console/web/models.js, turbo.js, server.js, settings.js (copy via brand.js only); console-web-e2e scenarios; contract fixtures for /api/models, /api/catalog, /api/pull/status, /api/turbo, /api/update
- **Platform:** platform-neutral
- **Risk:** high. These are the most cross-subsystem flows. They depend on a working fake supervisor restart and on the manage subsystem's fake configs carrying all four family field sets. The port-move test needs two ports and must clean up its processes.
- **Depends on:** WEB-06; manage subsystem: /api/models*, /models/load|unload, /api/catalog, /api/pull*, /api/turbo, /api/update with fake configs and a fake pull driver; engine subsystem: supervision and restart so 202 flows complete against fake engine processes; HTTP subsystem: /api/context, /api/port, /api/thinking-budget
- **Estimated size:** 80-200 (e2e helpers for supervised restarts) lines of code; 700-1000 lines of tests
- **Donor sources:** MAYA/serve/web/models.js:1-1079 (MS state, loadModels, watchRestart 78-99, switchTo 101-130, loadOrUnload 132-145, sheet tabs, plan, editor 182-268 and 577-660 with fieldsOf/mm3Fields/qwenFields/Command, delete flow 661-802, Overview/Storage, catalog/pull 882-953, leftovers 955-986, Card, ModelsPage 1029-1079); turbo.js, turbo-core.js, turbo.css; server.js:150-244 (context reload watch), 262-309 (port move), 345-397 (update watch); settings.js:70-145, 378-420 (ModelCtx, Port, ThinkBudget, UpdateCard)

**Behaviors to reproduce**

- The models list renders the fake model configs from /api/models: running outline, family glyph, label, size, set-up date, missing-file warning with the console's own repair hint from brand.js (replacing './maya.sh --setup' and 'START-MAYA.bat').
- Switch: POST api/models/switch, 202, then watchRestart polls health every 2 s and reloads the page with the toast '<name> is running'. When restarts=false it reports 'Saved as the next model' with the brand wording.
- POST models/load and models/unload with their toasts.
- Engine editor per family (GLM, DeepSeek, MiniMax, Qwen field sets, Advanced env vars, and the command preview with changed flags highlighted). A debounced 300 ms POST api/models/settings dry_run returns errors inline and the command line. Save without dry_run returns 202 and the restart is followed. A context-only change on the running model uses POST api/context. 'Reset to the setup's values' works. A '<config>.prev' note is shown.
- Delete with or without files: the plan list (GOES/STAYS), running-model delete after switch, the sessionStorage '<prefix>deleted' guard, and POST api/models/delete.
- Catalog and pull: GET api/catalog, POST api/pull with progress polling of api/pull/status, cancel, and the finished/failed toasts. The download comes from the manage subsystem's fake pull driver and no network is touched.
- Leftovers: listing, hub/pack badges (the 'Maya pack' badge renamed to the brand wording), and delete via POST api/models/leftovers.
- Turbo: GET api/turbo on boot, with the button hidden on error or when hidden is true. Switching on confirms, snapshots preferences under '<prefix>turbo_<prefsKey>', writes temperature 0 and the fastest level, POSTs api/turbo {on:true} and follows the restart (health every 2 s, up to 450 tries). Switching off restores both exactly. Engine lines list the changes. The 640px rule is kept.
- Context reload from Settings > Chat defaults: confirm text with the loadTime estimate, 202, the composer hint, and the waiting/running/done/failed handling, then the console:context event refreshes the Models editor.
- Port move: confirm, POST api/port. restarts=true moves the page to the new origin after a no-cors probe of the new port's /health (allowed by the CSP port wildcard). restarts=false gives the saved-for-next-start toast.
- Thinking budget validation (0 or 256-262144) and save.
- Update card: GET api/update with an optional force=1, states (up to date, available, updating, failed), POST api/update, and the update watch that reloads the page when health.version equals the target. The copy talks about updating the console, not git-pulling project-maya. What the server does is the manage subsystem's update contract; the UI only renders its states.

**Parity tests**

Server behaviour comes from upstream test_models.py, test_model_api.py, test_turbo.py (server classes), test_update.py, test_think_budget.py and test_dashboard.py Dashboard.test_reload_changes_the_context_and_saves_it and Port.* (owned by other subsystems). UI side: WEB-04 covers fieldsOf, turbo-core and ctxStops. This package adds about 14 e2e scenarios (switch with restart, switch without supervisor, load/unload, editor dry-run error and save, context-only save, delete running and idle, pull progress and cancel, leftovers delete, Turbo on/off exact restore, context reload failed path, port move restarts true and false, update available to done).

**Definition of done**

Every listed flow passes as an e2e scenario against pulsar-console with fake engines and a supervisor. No copy references maya.sh, START-MAYA.bat, git or GitHub releases of project-maya. Turbo on then off restores both browser preferences and engine settings exactly (checked through /api/models). Screenshots of the editor for each family are attached.

<a id="web-10"></a>
### WEB-10 Settings dialog, Saved panel, MCP tools page, shared defaults and accessibility checks

- **Milestone:** M8
- **Rust target:** console/web/settings.js, sidebar.js (copy via brand.js), console-web-e2e scenarios
- **Platform:** platform-neutral
- **Risk:** medium. Mostly verification. Copy changes must stay in sync with the WEB-04 literal tests. The privacy wording depends on the server retention decision (open question).
- **Depends on:** WEB-06; HTTP/API subsystem: GET/POST /settings, /api/thinking-budget; MCP subsystem: GET /mcp; manage subsystem: /api/savings*, /api/report
- **Estimated size:** 50-120 lines of code; 600-900 lines of tests
- **Donor sources:** MAYA/serve/web/settings.js:1-542 (GROUPS, OLD_IDS, General, ChatDefaults with presets and penalties, Instructions, Connect, Tools, Data, Savings/PriceCard, About, SettingsDialog); sidebar.js:126-266 (usd, useSavings, SavedBody, SavedPop, SavedSheet, SavedLine); server.js:101-124 (loadMcp/mcpOn), 311-342 (shared settings); state.js:154-277 (DEFAULTS, presets, prefs, newModelCheck, resetPrefs); ui.js:49-201 (menus, Seg, Switch, CtxSlider, DialogHost, trapTab, Toasts); accessibility facts in READERS maya-web key_facts

**Behaviors to reproduce**

- Eight pages in five groups, with old ids redirected (model→chat, connection/openai/anthropic→connect). #settings and #about open the right page. Changes apply at once. Confirmation is required only for context and port.
- Appearance: theme System/Dark/Light and scheme Default/Violet are persisted and applied live, including the theme-color meta.
- Chat defaults: thinking levels for the running family, presets Precise/Balanced/Creative with presetOf detection, sliders, penalties blank means not sent, seed, max tokens, show reasoning, MCP switch, 'Use these for other apps too' via GET/POST settings with sharedDefaults and a 600 ms debounced sync, and Reset to the model's own.
- Global instructions with sys_default.
- Connect your tools: the OpenAI and Anthropic base URLs and model name from location.origin and health, copy buttons, an API key field stored in '<prefix>apikey', and example tabs (Claude Code, OpenAI SDKs, curl) rendered through codeBlock and guard. The placeholder token 'maya' becomes a neutral 'local'.
- MCP tools: the server list with ready/starting/failed states, tool counts and retry while starting.
- Usage and savings: GET api/savings, PriceCard edit with POST api/savings/prices and validation, reset via POST api/savings/reset, the DeepSeek peak-hour note when prices carry peak. The sidebar SavedLine, SavedPop and the phone SavedSheet show the same numbers. Copy uses the brand name.
- Data and privacy: the chat count, and Clear chats and settings. The copy is corrected to state what the server keeps (resumable answers retained up to the server's configured period) instead of 'The server keeps none of them'.
- About: UpdateCard (WEB-09), facts (WEB-07/WEB-08), Show engine log and Copy report via GET api/report (the server keeps secrets out). A new 'Open-source notices' link opens web/notices.txt.
- Accessibility checks in the browser: dialogs have role=dialog and aria-modal, Tab is trapped, and focus returns on close. Menus support arrow keys. Radio groups use roving tabindex. The thinking slider has role=slider. The search combobox and listbox, aria-live toasts, progressbars, inert on the closed drawer, a visible :focus-visible outline, and the reduced-motion and reduced-transparency rules all apply. These are asserted through accessibility properties read via WebDriver.
- Browser baseline: the suite runs on Safari 17 or later and current Chrome. The page refuses nothing; unsupported features degrade as upstream does.

**Parity tests**

Server side comes from upstream test_savings.py, test_mcp.py (GET /mcp), test_dashboard.py Dashboard.test_report_leaves_secrets_out and the settings tests in test_server.py (owned by other subsystems). UI side: about 14 e2e scenarios here (each settings page, the presets round trip, shared defaults posted and reflected by GET /settings, price edit and reset, the Saved line equal to the Settings page, the notices link, a focus-trap and keyboard sweep, phone SavedSheet).

**Definition of done**

Every settings page and the Saved panel work against pulsar-console with fakes, as shown by e2e scenarios. The privacy text matches actual server retention. The notices link serves notices.txt. The accessibility assertions pass on Safari and Chrome.

<a id="web-11"></a>
### WEB-11 Contract conformance gate and Phase 1 close-out

- **Milestone:** M8
- **Rust target:** console/crates/console-web/tests/contract_conformance.rs (runs pulsar-console with the fake engine and records live responses); specs/022-*/contracts/ui-server/fixtures (regenerated golden files); docs updates in the contract README
- **Platform:** platform-neutral
- **Risk:** low. Late failures here show schema or server mismatches that belong to other subsystems. The gate reports them per route so they can be routed back.
- **Depends on:** WEB-05; WEB-07; WEB-08; WEB-09; WEB-10
- **Estimated size:** 300-500 lines of code; 200-350 lines of tests
- **Donor sources:** Everything in WEB-05's contract; MAYA/serve/web/*.js fetch sites (35 routes)

**Behaviors to reproduce**

- Start pulsar-console with the in-process fake engine (and fixture telemetry profiles apple and nvidia-tp2). Call every page-used route with the requests the page sends, as captured by WEB-06 and WEB-09 network logs. Validate each live response against its schema and status-code table.
- Regenerate golden fixtures with a documented command and diff them against the committed ones. Any change requires a contract edit in the same commit.
- Cross-check that every route in routes.md is answered (none 404 that the page expects) and that every additive extension field is present when documented.
- Produce the Phase 1 parity matrix in the contract README: each upstream web-related test method mapped to its Rust or e2e counterpart, or to an approved deviation, so nothing is silently dropped.
- Supply the job definition for the new workflow file (owned by the lead): cargo test -p console-web with CONSOLE_REQUIRE_NODE=1, and an e2e job with chromedriver that is required on push to the console branch.

**Parity tests**

Aggregates all of the above. Conformance adds about 40 route checks generated from routes.md.

**Definition of done**

contract_conformance passes for every documented route. Golden fixtures are current. The parity matrix lists every upstream web-related test (Offline, PageLogic, the turbo/glm_dsa Node classes, the static-route tests, the literal-source tests) with a mapped counterpart or deviation id. The CI job definition has been handed to the lead and runs green.

<a id="web-p2-01"></a>
### WEB-P2-01 PHASE 2 (roadmap, not this increment): shared contract crate and framework/toolchain decision

- **Milestone:** Phase 2 roadmap item (not a task of this increment)
- **Rust target:** console/crates/console-ui-contract (serde DTOs for every UI-facing request and response, no tokio or hyper, builds for wasm32-unknown-unknown); console/web-wasm/ (spike crate); docs/roadmap/CONSOLE_FRONTEND_ROADMAP.md decision record
- **Platform:** platform-neutral
- **Risk:** medium. This is the first front-end build step in the project, and payload size and toolchain pinning are the open costs.
- **Depends on:** WEB-11
- **Estimated size:** not sized (roadmap) lines of code; not sized (roadmap) lines of tests
- **New dependencies:** candidate: leptos, wasm-bindgen, web-sys, js-sys, gloo, serde-wasm-bindgen (decided in the spike)
- **Donor sources:** Phase 1 contract (specs/022-*/contracts/ui-server), console/web as the behavioural oracle; READERS maya-web ANALYSIS option (b)

**Behaviors to reproduce**

- DTOs are generated from or checked against the Phase 1 JSON Schemas and golden fixtures. The server's responses deserialize into them in a conformance test, so client and server share one Rust definition.
- Framework spike with a written decision record. Leptos (client-side rendering, fine-grained signals; the leading candidate because the imperative streaming painter maps onto signals and direct DOM handles), Dioxus web and Yew are compared on payload size against the current 17 KB Preact bundle, streaming-render cost on a 14k-token answer, and IndexedDB/fetch-stream ergonomics through web-sys and gloo.
- Toolchain: pinned wasm-bindgen-cli and wasm-opt driven by a console xtask, not trunk defaults. The output directory is named console/web-wasm/out (never 'dist', which .gitignore ignores). Decide whether the built wasm is committed with reproducibility checks or built in CI, and how build.rs embeds it.
- Markdown: port md.js's escape-first renderer and highlighter by hand. Do not switch to pulldown-cmark, because the Markdown-subset contract and golden outputs must match. md.js:33's lookbehind is replaced by a manual scanner, since the regex crate lacks lookbehind.

**Parity tests**

Phase 1 golden fixtures and the md.js golden corpus (WEB-03) become the oracle for the DTOs and the Rust Markdown port.

**Definition of done**

Decision record approved by the owner. The contract crate builds for wasm32 and native, and its conformance test passes against Phase 1 fixtures.

<a id="web-p2-02"></a>
### WEB-P2-02 PHASE 2 (roadmap): chat core rewrite in Rust/WebAssembly, served beside Phase 1

- **Milestone:** Phase 2 roadmap item (not a task of this increment)
- **Rust target:** console/web-wasm (the console-ui crate), console-web asset table extended with the wasm bundle under /ui2/
- **Platform:** platform-neutral
- **Risk:** high. The Node page-logic oracle does not apply to wasm. Its cases must be re-expressed as wasm-bindgen-test or native unit tests of the Rust ports.
- **Depends on:** WEB-P2-01
- **Estimated size:** not sized (roadmap) lines of code; not sized (roadmap) lines of tests
- **Donor sources:** console/web/{app,state,lib,ui,md,chats,chat-view,sidebar}.js (2,677 lines upstream) as the oracle

**Behaviors to reproduce**

- Re-express the shell, store, storage (the same localStorage keys and the same IndexedDB 'chats' schema, so existing chats survive), chat streaming over fetch streams with resume and cancel, the composer, attachments, the Markdown painter, sidebar and search, using the same CSS and design tokens and the same accessible names.
- Coexistence: Phase 1 stays at '/'. Phase 2 is served at '/ui2/' with the same API. A server option chooses the default UI. Both are same-origin, so storage is shared.
- The WEB-06 e2e suite runs unchanged against /ui2/ through a base-path switch in the harness. That is the parity gate.

**Parity tests**

The WEB-06 suite (role and label selectors) and the md.js golden corpus run against the wasm UI.

**Definition of done**

The e2e chat suite passes on /ui2/ in Safari and Chrome. Chats created in Phase 1 open in Phase 2 and the reverse.

<a id="web-p2-03"></a>
### WEB-P2-03 PHASE 2 (roadmap): Monitor, Models, Settings and Turbo rewrite, cutover and Phase 1 retirement

- **Milestone:** Phase 2 roadmap item (not a task of this increment)
- **Rust target:** console/web-wasm; console-web (default UI switch, removal of Phase 1 assets after approval)
- **Platform:** platform-neutral
- **Risk:** medium. Retiring Phase 1 removes the JS oracle, so the cutover waits until every e2e suite is green on the wasm UI.
- **Depends on:** WEB-P2-02
- **Estimated size:** not sized (roadmap) lines of code; not sized (roadmap) lines of tests
- **Donor sources:** console/web/{monitor,monitor-apple,models,settings,server,turbo,turbo-core}.js as the oracle

**Behaviors to reproduce**

- Port the remaining views, with all GPU-fixture and Apple paths and every restart-following flow. Re-express the Node page-logic tests (PageLogic, turbo-core, fieldsOf, chats) as Rust unit tests of the ported functions, with identical expectations.
- Cutover: the wasm UI becomes the default at '/' and Phase 1 moves to '/ui1/' for one release, then is removed. NOTICE entries for Preact, htm and Lucide are dropped if their code is no longer shipped. Lucide and Outfit stay if the sprite and font are kept.

**Parity tests**

The full WEB-06 to WEB-10 e2e suites plus the WEB-11 conformance gate against the wasm UI.

**Definition of done**

The whole e2e suite and the conformance gate are green on the wasm UI at '/'. Phase 1 assets are removed with the owner's approval, and NOTICE.md is updated.
