# Research: PulsarMLX Console Serving Parity

**Date**: 2026-11-14

**Scope**: Phase 0 design decisions for feature 022. Each decision below comes from the
plan the owner approved on 2026-11-14 (recorded in
[ADR 0008](../../docs/architecture/decisions/0008-console-serving-ahead-of-stage-f.md)) and
its binding cross-cutting decisions B1 to B13 (stated in
[tasks.md](tasks.md#binding-cross-cutting-decisions)), and from the lead decisions taken
after approval that this file names as such. The rationale and the alternatives come from
the planning records: seven subsystem work breakdowns ("planners" below), three architect
proposals and two red-team reviews, all reading project-maya at commit `7e68a30f` and this
repository at `main` (`aaf076f1`). Those records are not in the repository; what the
feature takes from them is restated in [tasks.md](tasks.md) and `tasks/`. Nothing in this
file was built or measured when it was written; where a package has since recorded a
result, the entry says so with its commit. Questions the approved plan does not decide are listed
under [Open items](#open-items) and are not decisions.

**Sources checked for this file**: the approved plan; the constitution; the pinned donor
checkout, read as text (44 test files and 913 test methods under `serve/`, the note-file
names in `serve/models.py`, the license file); `git show 005867d8` and the tree of tag
`archive/2026-09-21/feat/openai-serving`; the license fields of crate versions present in
the local Cargo registry.

## Decision 1: Placement

**Decision**: Build the console as a standalone nested Cargo workspace in a new top-level
directory `console/`, with its own `[workspace]`, `Cargo.lock` and
`rust-toolchain.toml`, not a member of the root workspace, with a target directory outside
the repository and no path dependency on anything outside `console/`. Feature documents
live in `specs/022-console-serving-parity/`; CI lives in a new
`.github/workflows/console.yml`.

**Rationale**: The engine track binds SHA-256 hashes of the root `Cargo.toml`,
`Cargo.lock` and `.github/workflows/macos.yml` into frozen evidence, so even an additive
member line would disturb it. A nested workspace changes no engine-track byte. The pattern
has precedent, though neither example is on `main`: the reverted `crates/serve-synthetic`
(kept at tag `archive/2026-09-21/feat/openai-serving`) declared its own `[workspace]`, and
so does the engine track's `experiments/packed-affine-adoption` on its feature branch. A
path dependency onto `crates/tokenizer` or `crates/gguf` would make hash-bound root files
build inputs, so small probes are reimplemented inside `console/`.

**Alternatives considered**:

- A member of the root workspace: needs edits to the hash-bound root manifest and lock.
- Reviving `crates/serve-synthetic` by reverting the revert: places the work under
  `crates/`, which is on the no-touch list, and inherits a gate that is red.
- A separate repository: loses the shared Spec Kit governance, the constitution and the
  history that ADR 0004 qualification and the roadmap refer to.
- Aligning console pins with the root lock: creates false coupling to a file both
  engine-track streaming groups edit, for no benefit given a separate lock.

## Decision 2: HTTP transport

**Decision**: A hand-written HTTP/1.0 transport on `tokio` and `httparse` that closes the
connection after each response (B1). No `hyper`, no `axum`. Strict limits on request line,
headers and body; client-disconnect detection for queued, streaming and non-streaming
requests.

**Rationale**: project-maya's server is Python's standard-library HTTP server. Byte-level
parity covers its status lines, its `Date` header, the name and position of its `Server`
header (whose value is `pulsar-console/<version>` under P-1, approved by the owner on
2026-11-14), 501 for unsupported methods, 414 and 431 for oversized request lines and
headers, no `100-continue`, and connection close after every response. A framework answers
HTTP/1.1 with chunked bodies and different headers, which would need a deviation, and adds
dependencies parity does not need. Disconnect detection (the donor's client watcher) is
simpler to reproduce with direct control of the socket.

**Alternatives considered**:

- `hyper` 1.x as in the reverted crate: different framing, more dependencies, and a
  deviation for HTTP/1.1 chunked responses that the conformance planner had flagged as a
  question for the owner.
- `axum`: all of the above plus a routing layer that does not match the donor's dispatch
  order.
- Treating framing as unobservable and using HTTP/1.1: the approved plan chose byte-level
  parity instead.

**Amended on 2026-11-15 (lead decision LD34)**: API-02 writes the request-head parser by
hand, without `httparse`, so that it accepts what CPython's request and header parsing
accepts; `httparse` refuses lines that Python accepts. The purpose of the decision,
byte-level parity, is unchanged. `httparse` stays a dependency of `console-conformance`
only (see [Dependencies](#dependencies)).

## Decision 3: JSON

**Decision**: `serde_json` with the `preserve_order` and `arbitrary_precision` features
across the whole workspace, and one Python-compatible writer in `console-pyjson` used for
every wire body and every persisted file (B3). The writer reproduces Python's
`json.dumps` byte for byte for the modes the donor uses: default separators, compact
separators, `indent=1`, `ensure_ascii` on and off, `sort_keys`, and Python float `repr`.

**Rationale**: Prompt bytes drive token ids, so separators, escaping and float formatting
inside rendered prompts and tool arguments must match. Run-config rewrites must be
byte-identical to the donor's `indent=1` output. Python accepts integers wider than 64 bits
and keeps exact decimal text, which `arbitrary_precision` preserves. One writer avoids
several subsystems drifting apart; the planners had proposed it independently in three
places (API-01, PRM-01, OPS-01), which are merged into API-01.

**Alternatives considered**:

- Default `serde_json` with `f64` numbers: big integers and some floats would change, a
  documented deviation the plan did not accept.
- One writer per subsystem: duplicated logic and divergent output.
- A different JSON crate: no gain over `serde_json` with the two features.

## Decision 4: Chat templates

**Decision**: `minijinja` plus `minijinja-contrib` (for Python string methods such as
`.split`, `.strip`, `.items` and `.startswith` through its Python-compatibility callback),
with a custom Python-compatible `tojson` filter (B4). Vendor chat templates are never
committed. When no template is configured, start-up fails with a clear error; there is no
bundled vendor fallback. Tests use PulsarMLX-authored synthetic templates. Vendor-template
render checks run only in the manual job and record hashes, not text. A template
compatibility spike comes first in M2 (PRM-03), accepted against synthetic-template goldens
in CI and vendor-template hashes in the manual job.

**Rationale**: The donor renders with Jinja2 under the transformers sandbox semantics.
The donor's templates use `break` and `continue` (a non-default `minijinja` feature) and
Python string methods that plain `minijinja` does not provide, which is why
`minijinja-contrib` is part of the decision. Vendor templates
carry their vendors' licenses (Qwen Community License, MiniMax Community License; the
GLM-5.3 template has no license text in the donor), so committing them is excluded by
LIC-1. A failed start is clearer than silently rendering with another vendor's template.

**Alternatives considered**:

- `minijinja` without `minijinja-contrib` (the prompting planner's PRM-03 text): cannot
  render the donor's templates; superseded by B4.
- Embedding Python Jinja2: a required Python process in the shipping runtime, against
  ADR 0001.
- Shipping the donor's default (Qwen-licensed) template as a fallback: excluded by LIC-1.
- Vendoring the two donor-derived templates with provenance: excluded by B4 (never
  committed).

## Decision 5: Tokenizer

**Decision**: A new `console-tokenizer` crate (B5): byte-level BPE reader, byte tokenizer
and incremental detokenizer, shaped for a real tokenizer
(`encode(text, parse_special, plain_spans)` and token bytes for incremental UTF-8). It has
no template dependency and no path dependency on any crate outside `console/`. Usage
counts always come from the backend.

**Rationale**: The existing `crates/tokenizer` is built only from GGUF metadata and sits
under `crates/`, which the console may not depend on. Splitting the tokenizer from
`console-prompt` lets the engine, media and HTTP crates use it without pulling in the
template engine. The pre-tokenizer patterns are transcribed from llama.cpp (MIT) with
notice, as the donor does.

**Alternatives considered**:

- Reusing `crates/tokenizer` by path: makes engine-track sources console build inputs.
- The `tokenizers` crate: a large dependency tree for behavior the donor implements in a
  few hundred lines of its own.
- Converging with `crates/tokenizer` now: a later, separately approved step.

**Recorded by PRM-04 (commit `7b58580f`, 2026-11-15)**: the residual differences between
Python's `regex` module and `unicodedata` on one side and the Rust crates on the other,
which the lead decided on 2026-11-14 to accept when a test names and pins them (item 28).
Each is pinned by a named test in
`console/crates/console-tokenizer/tests/prm04_unicode_tables.rs`. No Python oracle was run
and no donor code was executed, so the two points marked "believed" below are not verified.

1. `whitespace_class_excludes_u001c_to_u001f`: `\s` is Unicode `White_Space`
   (`regex-syntax`), so U+001C to U+001F are not whitespace for the pre-tokenizers (`!\x1c`
   is one piece). Python's `str.isspace` and the `re` module's `\s` include them. The
   `regex` module's `\s` for str patterns is believed to be `White_Space`, as here.
2. `letter_classes_use_unicode_16_tables`: `\p{L}`, `\p{N}`, `\p{M}`, `\p{P}` and `\p{S}`
   come from Unicode 16.0.0 (`regex-syntax` 0.8.11). Characters assigned in Unicode 17 (for
   example Sidetic U+10940) are unassigned here, so `a\u{10940}` splits into two pieces,
   where a `regex` module with Unicode 17 tables gives one. The donor's CI installs an
   unpinned `regex`.
3. `nfc_tables_are_unicode_18`: the MiniMax NFC step uses `unicode-normalization` 0.1.26
   (Unicode 18.0.0), against CPython 3.14's `unicodedata` 16.0.0 (15.0.0 on the donor CI's
   Python 3.12). Only characters assigned after 16.0 can normalize differently. Which
   interpreter version is the reference for such differences is open item OPEN-60; the
   working default is CPython 3.14 (lead decision LD38).
4. `case_insensitive_contraction_folds_long_s`: the MiniMax `(?i:'s|...)` group uses simple
   case folding, so U+017F matches `s`. This is believed to equal the `regex` module.

PRM-04 also changed how the pre-tokenizer matches. The patterns are kept verbatim as the
donor writes them (the DeepSeek-3 CJK stage included, with its `\uXXXX` escapes). Each
pattern's last two branches, `\s+(?!\S)|\s+`, are applied by hand: the whole run at the
end of the text, L-1 characters before a non-space when L is 2 or more, one character when
L is 1. The remaining branches run on the `regex` crate (leftmost-first, linear time). A
backtracking engine (`fancy-regex` 0.20.2, with its fixed 1,000,000-entry stack) failed on
whitespace runs of about a million characters, which the donor's `regex` module splits;
matching can no longer fail. The unit test
`pretok::tests::hand_applied_whitespace_tail_equals_the_whole_pattern` checks the
equivalence against `fancy-regex` running the donor's full pattern text, which is why
`fancy-regex` is now a test-only dependency. Runs of 2,000,000 spaces and tabs encode and
round-trip for every scheme
(`prm04_roundtrip::two_million_character_whitespace_runs_encode_and_round_trip`).

## Decision 6: Schema validation

**Decision**: A restricted JSON Schema validator written in-house as a pure module of
`console-responses` (B6), covering the keyword subset the donor accepts for structured
output, with the donor's accept and reject decisions, instance-validation semantics, error
ordering and path rendering. No `jsonschema` crate.

**Rationale**: The donor validates a bounded subset, so a general validator brings far
more than parity needs. A pure module with no `tokio` and no I/O can later build for
WebAssembly for Phase 2. Structured output is always available, where the donor returned
an "install jsonschema" error when its optional Python package was absent; that difference
is registered as PLAN-5 in [contracts/deviations.md](contracts/deviations.md).

**Alternatives considered**:

- The `jsonschema` crate: large dependency set, different error texts, and validation
  semantics beyond the donor's subset.
- Skipping validation: loses the donor's validate-before-publish behavior.

## Decision 7: MCP client

**Decision**: The MCP client is written in-house in `console-mcp` (B6): JSON-RPC framing,
stdio transport with process groups, Streamable HTTP transport through the outbound
facade, server lifecycle, tool naming and result text, the tool loop and the
`strata_mcp` chunk events. One fake MCP server binary in the `console-mcp` test support
(CNF-06 merged into RSP-08). No `rmcp`.

**Rationale**: Parity is defined at the level of exact handshake fields, paging limits,
timeouts, cancellation notifications, tool-name cleaning and result texts, which a
general SDK does not reproduce. `rmcp` in the root lock pulls `reqwest`, whose TLS story
conflicts with B7.

**Alternatives considered**:

- `rmcp` as used by the inherited `crates/serve`: different behavior and a heavy
  dependency chain.
- Running the donor's Python fake MCP server in tests: forbidden locally by B9.

## Decision 8: Attachment and PDF readers

**Decision**: All attachment readers in `console-attach`, written in-house over small
format crates: a ZIP reader over `miniz_oxide` (central directory with ZIP64, stored and
deflate members, CRC check, per-member and cumulative inflate caps), XML through
`roxmltree` (no external entities), HTML entities through `html-escape`, and readers for
Word, Excel, PowerPoint, OpenDocument, EPUB and RTF. A PDF object layer (lexer, object
scan, stream filters, page tree), a text interpreter with fonts and encodings, and an
orchestrator, also in-house. An optional external poppler adapter sits behind a cargo
feature. The core is pure (bytes in, result out; no `tokio`, no process spawning).

**Rationale**: The donor's readers are its own Python code over the standard library, so
parity is about its exact detection order, error messages and text layout, not about a
general document library. A pure core can be reused client-side in Phase 2. Inflate caps
stop ZIP bombs at a fixed bound.

**Alternatives considered**:

- General document or PDF crates: different text extraction and error texts, larger
  attack surface.
- Requiring poppler: an external program as a hard dependency; the donor treats it as
  optional.

## Decision 9: Images (conditional on proposal P-5)

**Decision, conditional on P-5**: Picture decoding is planned through the `image` crate
with default features off and only PNG, JPEG, GIF, BMP and WebP enabled, CatmullRom
resampling for the donor's bicubic filter, an in-house centered pad, and EXIF orientation
applied. This implementation depends on deviation proposal P-5 in
[contracts/deviations.md](contracts/deviations.md): pixel values that differ from Pillow
and the refusal of other formats are not approved. The owner deferred P-5 on 2026-11-14
to a decision before the picture packages of M6 (OPEN-15).
`data:` URLs are always accepted; remote URLs and local file paths are refused unless
enabled in settings (SEC-4). The DeepSeek picture preprocessor is built in M6; the MiniMax
picture preprocessor is not built (LIC-2), its file format is documented, and an engine
reporting MiniMax vision gets a clear error. No image file is committed: image test data
is generated in code (B13). There is one fake vision encoder binary, in
`console-fake-engines` (package ENG-14), used by RSP-18 (a lead decision).

**Rationale**: Reading any local path or fetching any URL named by a client is an
arbitrary file read and a server-side request forgery risk. The MiniMax algorithm is
described as ported from MiniMax's own image processor, whose license may be
non-commercial. The repository's staged-content scan rejects binary files.

**Alternatives considered**:

- Pillow-exact resampling in-house: large effort for differences in pixel values only,
  which P-5 proposes to accept.
- Building the MiniMax preprocessor from the donor's MIT code: deferred to an owner
  decision by LIC-2.

## Decision 10: Outbound network

**Decision**: Every outbound request goes through one facade over the system `curl`; no
TLS crate is added in this increment (B7). By lead decision the facade lives in
`console-core` (module `outbound`), is written by RSP-10, its first consumer, and is
reused by RSP-17 and OPS-16. The users are model pulls by `pulsar-console fetch`,
Streamable HTTP MCP servers (HTTPS MCP through the facade is registered as PLAN-6 in
[contracts/deviations.md](contracts/deviations.md)), the opt-in release check (SEC-5:
notify only, never fetch or run code) and the opt-in remote image fetch (SEC-4).

**Rationale**: One facade gives one place for timeouts, size caps, the user agent with the
product name, and tests through a loopback fixture. The system `curl` brings HTTPS without
adding a TLS stack to the dependency tree or choosing between `rustls` and the platform
stack now.

**Alternatives considered**:

- `ureq` with `rustls`: adds a TLS stack and certificate roots to maintain.
- `reqwest`: large dependency tree.
- No network at all: model pulls and HTTPS MCP servers are part of parity.

## Decision 11: Front end and its two phases

**Decision**: **Phase 1 (this increment):** adapt project-maya's no-build dashboard (ES
modules with vendored Preact and htm), keep upstream file names so `/web/<name>` URLs are
unchanged, and embed every asset in the binary from a fixed compile-time table; no
filesystem path is ever served (registered as PLAN-3 in
[contracts/deviations.md](contracts/deviations.md)). Identity is neutral (BRAND-1,
BRAND-2): product name "PulsarMLX Console", letter tiles per model family, a system font
stack and SVG icons only, no sponsor links, browser storage prefix `pulsar.` and IndexedDB
database `pulsar-console`. By lead decision, no font or PNG file is shipped under BRAND-2:
the `/fonts/<name>` route answers 404 and the web manifest lists SVG icons only. Security:
strict Content-Security-Policy and related headers, a sanitizer on every HTML sink, the
HTML preview in its own sandboxed route with network off unless allowed per preview
(SEC-2), and `/?q=` prefills without sending (SEC-3). Page logic is tested under Node with
no packages. A written UI-to-server contract (WEB-05) fixes every request and response the
page uses. **Phase 2 (later, roadmap):** a complete rewrite in Rust compiled to
WebAssembly against that contract, served beside Phase 1 until cutover. Phase 3 (real
engine attachment) is separately approved.

**Rationale**: Adapting the donor's existing dashboard delivers the full parity surface in
this increment at a fraction of the cost of a rewrite, and the written contract turns
Phase 1 into the specification for Phase 2. Fonts and PNG icons would be binary files and
carry third-party obligations; vendor logos are third-party marks.

**Alternatives considered**:

- Rust/WebAssembly in this increment: adds a WebAssembly toolchain and CI steps before the
  server exists; scheduled as Phase 2 instead.
- Serving from a directory at run time: exposes filesystem paths; an opt-in developer
  override serving the same names is a separate question for WEB-02 (OPEN-41).
- Keeping upstream identity, fonts and icons: excluded by BRAND-1 and BRAND-2.

## Decision 12: Reuse of the archived serving crate

**Decision**: `crates/serve-synthetic` at tag `archive/2026-09-21/feat/openai-serving` is
superseded as a merge candidate and used as the reference for the security posture: Host
allowlist, `Origin`, content type and token handling, its limits, and its raw-HTTP tests
(B8). What is reused lands inside `console/` as new code with its own tests; the archived
crate is not re-merged.

**Rationale**: It is PulsarMLX's own earlier work and already held the posture SEC-1
requires (Host allowlist on loopback binds, `Origin` checked on every route including
`null`, JSON content type on POST, constant-time token comparison). Its tests
(`tests/raw_http.rs` and others at the tag) express attacks that the donor's tests do not.
Its framework (`hyper`) and its Python campaign harness are not reused. The owner settled
the allowlist's scope on 2026-11-14 (SEC-1.1, OPEN-04): on a loopback bind a request is
accepted only if its `Host` is a loopback name (`localhost`, `127.0.0.1`, `[::1]`, any
port) or a name listed in the optional run-config key `allowed_hosts`, absent by default;
on a non-loopback bind `Host` is not restricted, as in the donor, unless `allowed_hosts`
is set, and then only the listed names and the loopback names pass. A refused request
gets 403 `permission_error`. That `allowed_hosts` also extends the list on a loopback bind
follows the SEC-1.1 text the owner reviewed; the lead confirms it with the owner at
checkpoint 2 (lead note LD30). Matching details (case, port, IPv6 forms, a missing `Host`
header) follow this crate and are settled by API-03.

**Alternatives considered**:

- Reverting the revert and repairing its gate: places code under `crates/` and restores a
  `hyper` stack and a Python-orchestrated gate.
- Ignoring it: loses tested security behavior and repeats work.

## Decision 13: Conformance evidence and the parity ledger

**Decision**: Parity is measured by `console/parity/ledger.json`, one row per donor test
method (913 rows, keyed by file, class and method, listed by a static AST reading of the
pinned source, never by executing it). By lead decision, each row has exactly one of
eight dispositions: `rust-test`, `scenario`, `web-test`, `shim`, `vendor-render`,
`deviation`, `not-applicable` (with a reason from a closed list) and the transitional
`pending`, as defined in section 3.2 of
[contracts/parity-ledger.md](contracts/parity-ledger.md). This refines the five
dispositions the approved plan names by adding the two that run only in the manual job. A
checker fails the build on a dangling row; no row may remain pending at close-out. Four
sources of evidence feed it:

| Evidence | What it is | Where it runs |
| --- | --- | --- |
| A. Reference corpus | Requests, responses, streams and rendered-prompt probes captured from project-maya's own server in fake-engine mode at the pinned commit, normalized (ids, timestamps) and committed as text with a provenance header. | Capture: manual GitHub Actions job, once per pin. Replay against the Rust server: every CI run, offline. |
| B. Re-expressed donor tests | About 800 of the 913 methods build Python objects in-process and cannot be pointed at a binary, so they are translated: 29 files to Rust unit tests, 13 to black-box HTTP tests, 2 run as-is through a shim. | Blocking CI. The two files run through the shim (`serve/test_engine_contract.py` and `serve/test_stop.py`) run only in the manual reference job, as do the vendor-template renders; blocking CI checks their committed records (a lead decision refining the plan's table, which put the shim under blocking CI). |
| C. Independent tests | Written from PulsarMLX contracts by a different agent than the one that ported the behavior, as ADR 0004 requires; includes the security tests salvaged from the archived serving crate. | Blocking CI. |
| D. Client SDK tests | The official `openai` and `anthropic` Python clients parse the server's output. | Manual job, pinned by hash. |

**Rationale**: The donor's tests are white-box, so most cannot run against a binary; a
ledger with a cited donor method per row makes silent omission visible, and the reference
corpus gives an oracle that is independent of the translation. Committed references keep
the gate working without the donor and without Python. The fake engines are deterministic
functions of scenario, prompt and call index, synchronized with gates and an injectable
clock rather than sleeps.

**Alternatives considered**:

- Running project-maya's server beside the Rust server in every CI run (the conformance
  planner's design): brings an unpinned Python harness and third-party code into the
  blocking gate, the failure class behind the September revert; excluded by B9 and B12.
- Re-expressed tests only: a translator can quietly weaken assertions with no independent
  check.
- Spec-derived goldens without a donor capture: loses the donor as the reference where it
  departs from the public specifications, which the parity definition requires.

## Decision 14: CI design and the lesson of the reverted serving crate

**Decision**: `.github/workflows/console.yml` is path-filtered to console paths, pins
actions by commit SHA, uses explicit runner labels, runs every job from `console/` on the
pinned toolchain, installs that exact toolchain and asserts `rustc -V` first (B12). Blocking
jobs are deliberately small: preflight on Linux (boundary check, ignored-file check,
credential, binary and size scan ported from `scripts/research/check_staged.sh`, no AI
attribution in the commit range); Rust on Linux (`fmt`, `clippy -D warnings`, tests,
replay of committed references, cross type-check for Windows); Rust on macOS arm64
(tests, including the Apple Silicon reader and process lifecycle); web logic tests under
Node with no packages. Manual `workflow_dispatch` jobs: reference capture and the live
differential against project-maya at the pinned commit (verified by SHA and a file-hash
manifest, checked out outside the workspace, hash-pinned Python environment under
`console/`), vendor-template render checks, SDK client tests, a toolchain drift canary,
and the browser end-to-end suite. Never in a blocking job: pip installs, scrubbed or
offline rebuild campaigns, mutation runs, third-party code.

**Rationale**: `git show 005867d8` records why the archived crate was reverted on
2026-09-20: its gate "Serving synthetic qualification" was red at the merged head because
the "Mutation guards" step failed with `TOOLING_NOT_READY: pristine did not compile`. The
mutation campaign rebuilt a pristine copy with `cargo test --offline --locked` inside a
scrubbed environment using whatever toolchain the hosted runner shipped. The revert message
records that every step passed locally on rustc 1.95.0 and that the runner's newer
toolchain is where it failed. The gate was
already red before the merge, and the merge went ahead. The same crate had already been
hit once by toolchain drift (a new Clippy lint on its first CI run). The lessons applied
here: pin the toolchain and honor the pin by running from `console/` (a toolchain file is
found from the working directory upward, not from `--manifest-path`); keep the blocking
gate to deterministic functions of repository content plus pinned tools; move heavy or
drift-prone qualification into manual jobs; never merge a console change on a red console
gate; and surface drift through a canary as a planned toolchain bump, never as a red
`main`. Path filtering keeps engine-track pushes from running or failing the console
workflow after it reaches `main`.

**Alternatives considered**:

- No path filter, so that skipped jobs never report success (the conformance planner's
  preference): would run, and could fail, on every engine-track push once merged, which
  is direct interference; B12 chose a path filter.
- Adding jobs to `macos.yml`: the file is frozen and hash-bound.
- A required in-CI differential and mutation gate: the September failure class.

Known cost: `macos.yml`'s classifier treats `console/`, `specs/` and a new workflow file as
code, so every push of this branch also runs the full native qualification (about 35
minutes of macOS runner time), and the branch is green only when `main`'s native jobs are.
Pushes are therefore batched at owner checkpoints.

## Decision 15: Toolchain pin

**Decision**: Rust 1.97.1, pinned exactly in `console/rust-toolchain.toml` with the
`rustfmt` and `clippy` components. CI installs exactly that toolchain and asserts the
version. On hosts without `rustup`, where the pin file is not enforced, local gates run
`console/tools/check-toolchain.sh`, which reads the channel from the pin file and fails
unless `rustc -V` reports exactly that version (a lead decision of 2026-11-14). Toolchain
bumps are a reviewed one-line change to the pin together with any new lint fixes, prompted
by the manual drift canary.

**Rationale**: 1.97.1 is the version installed on the owner's build host; `rustc -V` there
reported `1.97.1` on 2026-11-14. An exact pin removes the drift that broke the archived
crate's gate twice.

**Alternatives considered**:

- Floating stable: the September failure mode.
- A channel name without a patch version: still drifts.
- Matching whatever the hosted runner ships: drift by definition.

## Decision 16: Naming

**Decision** (B2, BRAND-1): Product "PulsarMLX Console", binary `pulsar-console`,
environment prefix `PULSAR_CONSOLE_`. Legacy `MAYA_*` and `STRATA_*` names are not
accepted as aliases; a published old-to-new table lives in
[contracts/naming.md](contracts/naming.md). Variable names inside a run config `env` block
that are passed through to engine child processes are opaque data and pass through
verbatim, once: by lead decision, the donor's export of each engine setting under both a
`MAYA_` and a `STRATA_` name is not reproduced. The wire names `strata_resume`,
`strata_mcp`, `strata_tune`, `strata_level_default`, `/v1/strata/stream` and
`/v1/strata/cancel` are kept unchanged (they are not project-maya's name and the dashboard
depends on them). Run-config files use the prefix `pulsar-` and note files `.pulsar-*`
(the donor's `.maya-switch.json`, `.maya-delete.json` and `.maya-verified.json` become
`.pulsar-switch.json`, `.pulsar-delete.json` and `.pulsar-verified.json`, subject to the
naming contract). Browser storage prefix `pulsar.` and IndexedDB database
`pulsar-console`. Log prefix `[console]`. The sealed-reasoning prefix emitted is the
product one; whether the donor prefix is accepted on input is an open item (OPEN-01). By
lead decision, test-harness switches read by the product or its tests also use the
`PULSAR_CONSOLE_` prefix, with the mechanical names `PULSAR_CONSOLE_<old suffix>` listed
in the naming contract, while the control variables of the fake engines and the fake MCP
server keep the names the donor's fakes use, because they are a test-double interface, not
product identity.

**Rationale**: Owner branding; project-maya is named only where attribution or provenance
requires it. Accepting legacy names would make project-maya's identity part of the
product's interface. Engine pass-through names are the engines' interface, not the
server's.

**Alternatives considered**:

- Accepting `MAYA_*` and `STRATA_*` as read-only aliases (proposed by several planners):
  rejected by B2.
- Renaming the `strata_*` wire names with aliases: would break the adapted dashboard and
  existing clients for no branding gain.

## Decision 17: Backend seam

**Decision**: Two levels. The *token level*, which an engine implements: ids in, ids out;
synchronous; the engine instance is owned by one driver thread and need not be `Send`,
because the engine track's coordinator is single-owner; capability flags mirror the
donor's `READY` and `INFO` lines; per-request sampling keys; cancel, pause and wrap;
prompt-progress, statistics and residency telemetry as side events; usage reported by the
backend; delivery at-least-once and keyed by position, with a shared ledger that drops
exact replays and rejects gaps. The *event level*: reasoning, content and tool events and
exactly one terminal event. The server keeps tokenization, template rendering,
detokenization, stop handling, tool-call parsing, thinking budget, loop guard, finish
reason and usage, as the donor's server does. The line protocol is written down as a
PulsarMLX contract with the donor's cited as prior art. Launching `maya-metal` or any
other project-maya engine binary is out of scope (B10). The normative draft is
[contracts/backend-seam.md](contracts/backend-seam.md) (GOV-06), which ENG-01 freezes; its
event ledger turns a rewind, a changed id at a committed position, or a gap into a
protocol failure, and drops only an exact repeat of the most recently accepted token.
The server assigns the request id. How a multi-conversation engine fits the single-owner
seam is settled by ENG-01 before the seam is frozen (OPEN-30). The lead's guidance: the
instance stays owned by one driver thread; for more than one concurrent generation the
token-level trait offers a submit-and-pump form with request-id-tagged events, and the
blocking `generate` form is the single-conversation case.

The server refuses to start an engine that does not report synthetic provenance (seam
question Q9, OPEN-29, decided by the owner on 2026-11-14). By lead decision LD28, the
descriptor's provenance type can express an engine that declares another provenance or
none, and synthetic is the only value accepted in this increment; one guard function in
`console-core` decides, every path that admits an engine (first start, restart, model
switch, context reload) calls it before the engine serves a request, and no environment
variable, configuration key, command-line flag or Cargo feature bypasses it. A
line-protocol engine that does not declare synthetic provenance in its start-up lines
counts as not synthetic; the form of the declaration is open item OPEN-58. ENG-01 settles the exact shape of the
type. What must be done before such an engine may be allowed is in
[ALLOWING_NON_SYNTHETIC_ENGINES.md](../../docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md).

**Rationale**: The at-least-once, position-keyed delivery matches how the engine track's
post-commit `deliver` hook in `crates/backend/src/step.rs` behaves after a refused
delivery, so a future PulsarMLX engine can attach without changing its commit semantics. A
coordinator-shaped test adapter (ENG-19) proves the fit on synthetic runtimes.

**Alternatives considered**:

- An event-level seam only: would force the engine to own text decisions the donor keeps
  in the server.
- An async, `Send` engine trait only: does not fit a single-owner coordinator.

## Dependencies

Every dependency is pinned with `=` when first added to `console/Cargo.lock`, and this
table is updated in the same change. "Introduced by" names the first package that needs
it. Licenses marked "checked" were read on 2026-11-14 from the crate manifest of the
version present in the local Cargo registry (the version the root lock uses); they are
re-checked against the version actually pinned. "Not yet checked" licenses are recorded
from the pinned crate's manifest when it is added. A crate shown with an `=` version is
pinned in `console/Cargo.toml`; for those rows the license was re-read on 2026-11-14 from
the manifest of the pinned version.

| Crate | Purpose | License | Introduced by |
| --- | --- | --- | --- |
| `serde` =1.0.229 | Derive and data model for every JSON type | MIT OR Apache-2.0 (checked) | API-01 |
| `serde_json` =1.0.151 (`preserve_order`, `arbitrary_precision`) | JSON values with insertion order and exact numbers (B3) | MIT OR Apache-2.0 (checked) | API-01 |
| `indexmap` 2.14.0 (locked) | Ordered map behind `preserve_order` (transitive) | Apache-2.0 OR MIT (checked) | API-01 |
| `tokio` =1.53.1 | Async runtime, sockets, timers, processes, signals | MIT (checked) | API-02 |
| `httparse` =1.10.1 | HTTP/1.x response parsing in the raw conformance client; not used by the transport, whose request-head parser is written by hand (LD34) | MIT OR Apache-2.0 (checked) | API-02 (pinned with the M1 scaffold); used by CNF-03 |
| `libc` =0.2.189 | Operating-system randomness for ids; signals, process groups, POSIX calls in lifecycle and supervision | MIT OR Apache-2.0 (checked) | API-01 |
| `fancy-regex` =0.20.2 | Test-only: checks the pre-tokenizer's hand-applied whitespace tail against the donor's full patterns, which use look-around | MIT (checked) | PRM-04 |
| `regex` =1.12.4 | Pre-tokenizer patterns (with the whitespace tail applied by hand), literal alternation and Unicode classes in tokenizer, parsers and loop guards | MIT OR Apache-2.0 (checked) | PRM-04 |
| `unicode-normalization` =0.1.26 | NFC for the MiniMax tokenizer path | (MIT OR Apache-2.0) AND Unicode-3.0 (checked) | PRM-04 |
| `minijinja` | Chat-template runtime (B4) | Not yet checked | PRM-03 |
| `minijinja-contrib` | Python string-method compatibility for templates (B4) | Not yet checked | PRM-03 |
| `sha2` =0.10.9 | Content hashes: store keys, owner ids, template and manifest hashes | MIT OR Apache-2.0 (checked) | API-03 |
| `base64` | Sealed reasoning, `data:` URLs, file parts | MIT OR Apache-2.0 (checked) | RSP-03 |
| `tokio-util` | Cancellation token for background jobs, unless the core provides its own | MIT (checked) | RSP-05 |
| `miniz_oxide` | Deflate for the ZIP reader and PDF stream filters | Not yet checked | RSP-12 |
| `roxmltree` | XML parsing without external entities | Not yet checked | RSP-12 |
| `html-escape` | HTML5 named entity table | Not yet checked | RSP-12 |
| `image` (PNG, JPEG, GIF, BMP, WebP only) | Picture decoding and resampling | Not yet checked | RSP-18 |
| `fantoccini` (no TLS backend; test-only crate), **excluded if `cargo tree -i hyper` shows `hyper`** | WebDriver client for the browser end-to-end suite. Current releases are believed to build on `hyper`, which is excluded everywhere, test-only crates included (not verified: the crate is not in the local registry). WEB-06 runs that check before adding it; if it fails, WEB-06 needs a WebDriver client without `hyper`. | Not yet checked | WEB-06 |

The M1 scaffold pins the crates below in `[workspace.dependencies]` of
`console/Cargo.toml`, and `console/Cargo.lock` records them. Member crates inherit them
with `workspace = true` and add only the features their package needs.

| Crate and pin | Features | Used by | Why |
| --- | --- | --- | --- |
| `serde` =1.0.229 | `default-features = false`; `std`, `derive` | `console-pyjson`, `console-core`, `console-conformance` | Data model and derive for JSON types (API-01 per PRM-01, API-15, CNF-02) |
| `serde_json` =1.0.151 | `default-features = false`; `std`, `preserve_order`, `arbitrary_precision` | `console-pyjson`, `console-core`, `console-tokenizer`, `console-http`, `console-testkit`, `console-conformance` | Binding decision B3: order-preserving, exact-number JSON across the workspace |
| `libc` =0.2.189 | default (`std`) | `console-pyjson`, `console-testkit`, `console-conformance` | `getentropy` for ids (API-01; no `uuid`); process groups and signals (CNF-07, the API-19 process helper) |
| `tokio` =1.53.1 | `default-features = false` at workspace level; `console-core`: `rt`, `sync`, `time`, `macros` (dev adds `test-util`); `console-http`: `rt`, `rt-multi-thread`, `net`, `io-util`, `time`, `sync`, `macros` (dev adds `test-util`); `console-testkit`: `rt`, `rt-multi-thread`, `net`, `io-util`, `time`, `sync`, `macros` | `console-core`, `console-http`, `console-testkit` | Hand-written HTTP/1.0 transport (API-02, B1); FIFO with `Mutex` and `Notify` and paused-time tests (ENG-09); spawned turn tasks and bounded channels (ENG-10); in-process test server (API-19) |
| `httparse` =1.10.1 | default (`std`) | `console-conformance` | Response parsing in the raw client (CNF-03). Since 2026-11-15 `console-http` does not use it: its request-head parser is written by hand so that it accepts what CPython accepts (LD34) |
| `sha2` =0.10.9 | `default-features = false` | `console-core`, `console-conformance` | SHA-256 response owner id (API-03 `response_owner`) and the vendor-template SHA-256 check (CNF-02) |
| `fancy-regex` =0.20.2 | `default-features = false`; `std`, `unicode` | `console-tokenizer`, as a dev-dependency only since 2026-11-15 | A unit test that checks the hand-applied whitespace tail against the donor's full patterns (PRM-04, Decision 5) |
| `regex` =1.12.4 | `default-features = false`; `std`, `unicode` | `console-tokenizer` | Pre-tokenizer patterns, literal alternation and Unicode classes (PRM-04) |
| `unicode-normalization` =0.1.26 | default (`std`) | `console-tokenizer` | NFC for the MiniMax pre-tokenizer path (PRM-04) |

The licenses above matter once a binary is distributed: a notices file for the linked
crates is owed before that (open item OPEN-59). Nothing is vendored and this increment
distributes no binary.

Transitive crates, locked but not declared: `aho-corasick` 1.1.3, `bit-set` 0.8.0,
`bit-vec` 0.8.0, `block-buffer` 0.10.4, `bytes` 1.12.1, `cfg-if` 1.0.5, `cpufeatures`
0.2.17, `crypto-common` 0.1.7, `digest` 0.10.7, `equivalent` 1.0.2, `generic-array`
0.14.7, `hashbrown` 0.17.1, `indexmap` 2.14.0, `itoa` 1.0.18, `memchr` 2.8.3, `mio` 1.2.2,
`pin-project-lite` 0.2.17, `proc-macro2` 1.0.107, `quote` 1.0.47, `regex-automata` 0.4.18,
`regex-syntax` 0.8.11, `serde_core` 1.0.229, `serde_derive` 1.0.229, `socket2` 0.6.5,
`syn` 3.0.6, `tinyvec` 1.13.3, `tokio-macros` 2.7.2, `typenum` 1.20.1, `unicode-ident`
1.0.26, `version_check` 0.9.5, `wasi` 0.11.1+wasi-snapshot-preview1, `windows-link` 0.2.1,
`windows-sys` 0.61.2 and `zmij` 1.0.23. Their licenses, read on 2026-11-14 from each
crate's own manifest in the local Cargo registry: `aho-corasick` and `memchr` Unlicense OR
MIT; `bytes`, `generic-array`, `mio`, `tokio-macros` and `zmij` MIT; `tinyvec` Zlib OR
Apache-2.0 OR MIT; `unicode-ident` (MIT OR Apache-2.0) AND Unicode-3.0; `version_check`
MIT/Apache-2.0; `wasi` Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT; all others MIT
OR Apache-2.0 (or Apache-2.0 OR MIT). `bytes` arrives only through `tokio`; no console
crate declares it (OPEN-40 unchanged).

Two rows changed when the scaffold pinned them. `libc` is now introduced by API-01 instead
of API-16, because `console-pyjson` reads operating-system randomness for ids through
`getentropy`. `sha2` is now introduced by API-03 instead of PRM-02, because the response
owner id (API-03) and the vendor-template check (CNF-02) need it before any store key or
manifest hash does. No decision in this document named a version, and no crate was
replaced.

Explicitly excluded: `hyper`, `axum` (B1; by lead decision `hyper` is excluded everywhere,
including test-only crates and fixture servers); `rmcp`, `jsonschema` (B6); any TLS crate
(B7); the `tokenizers` crate (Decision 5); `resvg` and any rasterizer (BRAND-2 uses SVG
icons only); `uuid` (by lead decision, ids are random hexadecimal from operating-system
randomness). Proposed by one planner but not adopted by the plan: `http`/`bytes` for the
web crate (OPEN-40). Tools used only in CI, never linked: an exact Node.js version with no
packages; `cargo-mutants` would be advisory and manual only if ever used, and is not part
of the approved CI design.

## Planner Questions Resolved by the Approved Plan

The planning records raised questions that the approved plan or its binding decisions
answer. They are listed so nobody reopens them by accident.

| Question | Answer and source |
| --- | --- |
| HTTP/1.0 close-delimited or HTTP/1.1 chunked | HTTP/1.0, connection closed after each response (B1). |
| Accept `MAYA_*` and `STRATA_*` as aliases | No; published table only (B2). |
| Keep the `strata_*` wire names | Yes, unchanged (B2). |
| `arbitrary_precision` workspace-wide | Yes (B3). |
| Default chat template when none is configured | None; start-up fails with a clear error (B4). |
| Vendor templates in CI, or vendored | Never committed; checks only in the manual job, hashes recorded (B4, LIC-1). |
| Who owns the fake engine binaries | `console-fake-engines` (CNF-05 merged into ENG-05). |
| Run the donor's Python suite or fakes locally, or as a blocking oracle | No; donor code runs only in the manual GitHub Actions job (B9). |
| TLS stack | None in this increment; system `curl` behind one facade (B7). |
| Self-update and `/api/update` | Route shapes only; the release check is opt-in and only notifies (SEC-5). |
| Refusal-ablation switch and `ablate` | Not ported; the capability is recognized and refused unless an engine advertises it (POL-1). |
| MiniMax picture preprocessor | Not built (LIC-2). |
| First real catalog entry | None; the catalog ships empty (B10). |
| Loopback-or-key gate for mutating admin routes | Yes (SEC-1). |
| Preview network default | Off unless allowed per preview (SEC-2). |
| Remote image URLs and local paths | Opt-in; `data:` URLs always (SEC-4). |
| Resumable answers on disk | Kept in memory; disk persistence off by default; settings text states what is stored (PRIV-1). |
| Apple GPU figures | GPU activity is an experimental field of the Apple Silicon reader (PLAT-2). |
| Launcher, restart and download | `pulsar-console supervise` and `pulsar-console fetch` with the donor's progress, exit-code and restart contracts (PLAT-3). |
| Graceful QUIT on context reload, single writer to the engine pipe, untagged stop in multi mode | Fixed (FIX-1). |
| Windows code | Ported behind traits, type-checked for Linux and Windows in CI, labeled unverified (PLAT-1, B11). |
| Node.js as a CI test tool | Yes, with no packages (B12). |
| Browser end-to-end as a required job | No; manual job (B12). |
| Default merge policy | A merge commit; engine branches are never asked to rebase (approved plan, section 10). |
| Pre-existing `crates/serve` web UI | Untouched (nothing under `crates/` changes). |

## Open Items

Everything below is open unless marked resolved. None of it is decided by this file. The
consolidated register of every open item in this feature, with stable `OPEN-` ids, is in
[checklists/analysis.md](checklists/analysis.md); the id of each item below is given in
parentheses. Each item names who decides and which package is blocked by it. "Owner" means
the item changes product behavior, licensing or policy and needs the owner's decision;
"Lead" means it is a design choice within the approved plan that the lead settles and
records in the named contract.

### Owner decisions

1. **Required check** (OPEN-13). Whether `console.yml` (or a summary job in it) becomes a
   required status check on `main`. Until then a red console gate does not block a merge
   in GitHub's eyes and reviews must check it by hand. Decided at merge time.
2. **Merge order** (OPEN-14) of the feature branch relative to engine-track branches with
   tree-bound evidence. Decided at the pull-request checkpoint.
3. **Donor sealed-reasoning prefix on input** (OPEN-01). Whether the donor's `maya-r1:`
   prefix in Responses `encrypted_content` is accepted on input (portability of
   histories), while only the product prefix is emitted. Blocks RSP-03.
4. **Further deviations proposed by planners but not among the approved ids** (OPEN-15;
   the engine ready timeout was also OPEN-10 and the template and encoder failures
   OPEN-07; the accessibility fixes are OPEN-12). Most are listed with `P-` ids in the
   proposals section of [contracts/deviations.md](contracts/deviations.md). On 2026-11-14
   the owner approved fourteen of P-1 to P-18, declined two and deferred two:
   - **Approved**, and now deviations under their `P-` ids: a
     `Server: pulsar-console/<version>` header (API-02, P-1); 400 when both
     `Content-Length` and chunked transfer encoding are present (API-02, P-2); a different
     detail text inside `malformed request (...)` errors (API-07, P-3); exception detail
     text inside parenthesized error tails (RSP-12 and others, P-4); an optional engine
     ready timeout, off by default (ENG-06, P-6, which settles OPEN-10); a whitespace-free
     vision temporary directory (ENG-14, P-7); template `raise_exception` and DeepSeek
     encoder assertion failures mapped to 400 instead of the donor's generic error (PRM-03,
     PRM-07, PRM-08 and API-07, P-8, which settles OPEN-07); the backend label table on Models
     cards (WEB-08, P-9); the frozen-engine watchdog rule on macOS (ENG-08, P-10); strong
     ETags, 304 and `HEAD` for static assets (WEB-02, P-11; the developer asset override
     stays not adopted, OPEN-41); `window.console_debug` only under `#debug` (WEB-03,
     P-13); `details.format` of `safetensors` for MLX checkpoints in the model API
     (OPS-12, P-14); MLX checkpoint configurations listed as not startable (OPS-03, P-15);
     refusal of catalog revision `main` (OPS-14, P-16).
   - **Declined**: a report-only switch for the Content-Security-Policy (P-12), because it
     would weaken SEC-2 while on; a literal-parity setting for the old reload behavior
     (P-17), because FIX-1.1 is approved and no such setting is built.
   - **Deferred**, still awaiting the owner: image formats beyond PNG, JPEG, GIF, BMP and
     WebP refused, and pixel values not bit-exact with Pillow (RSP-18, P-5), before the
     picture packages of M6; an explicit model-family override in config (PRM-05, P-18),
     before PRM-05 in M2.
   - **Still open under OPEN-15**: JSON Schema meta-validation wording (RSP-02, PLAN-5)
     and an advisory lock on the savings ledger (OPS-21). The accessibility fixes the donor
     leaves open (WEB-10) stay open as OPEN-12.

   Each item still open or deferred needs owner approval before the package that relies on
   it is merged, or the package keeps literal parity.
5. **Upstream defects not listed under FIX-1** (OPEN-16 for `/props`, OPEN-09 for the
   untagged `ERR`). Whether to reproduce or fix: `/props`
   reporting `model_path` as a literal fallback for configs that use a pack or GGUF flag;
   an untagged `ERR` in multi-conversation mode being delivered to no request, which then
   waits out the quiet timeout. Blocks ENG-07 and API-11.
6. **Licensed vendor material in the manual job** (OPEN-11). Whether the manual
   vendor-template job may fetch and render the MiniMax Community License template and
   fixtures (with a prohibited-use appendix) and the GLM-5.3 template, which has no
   license text in the donor, even for test-only use with hashes recorded. If not, those
   ledger rows become deviations. Blocks CNF-11.
7. **Private mirror** (OPEN-17). Whether the owner keeps a private read-only mirror of
   project-maya at `7e68a30f` so the manual reference job survives an upstream history
   rewrite. Affects CNF-08.
8. **Built-in savings price table** (OPEN-08). Keep the donor's table of third-party
   prices dated 2026-10 with its as-of date, or ship it empty so only user prices apply.
   Blocks OPS-21.
9. **Supervised entry point** (OPEN-05). Whether `pulsar-console supervise` is the
   documented default entry point, with the server alone running unsupervised (restarts
   reported as unavailable), as the donor splits its launcher and server. Affects OPS-11
   and API-17.
10. **Run-config directory default and importer** (OPEN-06). Decided by the lead on
    2026-11-14: API-15 (M1) resolves every persisted file relative to the directory of the
    run config passed with `--config`, as the donor does. Still open: the default
    directory when no config is given (for example a fixed per-user application-support
    folder), and whether a one-time importer for existing project-maya run configs is
    offered (an importer is not an alias, so B2 does not settle it). Due before OPS-11
    (M7).
11. **Media-source opt-in form** (OPEN-18). Whether the SEC-4 opt-in is a run-config key, an
    environment variable, or both, and its name. Blocks RSP-17.
12. **Resumable answers on disk** (OPEN-19). PRIV-1 makes disk persistence off by default;
    whether an opt-in to disk persistence exists at all, its name and its retention
    period. Blocks API-10 and WEB-10.
13. **Phase 2 framework** (OPEN-20). Leptos client-side rendering, or a neutral spike
    among Leptos, Dioxus and Yew. Roadmap only (WEB-P2-01).
14. **Engine boundary for Phase 3** (OPEN-21). Whether the later PulsarMLX engine attaches
    first as an executable speaking the line protocol or through the in-process runtime
    adapter fed by the engine track's post-commit `deliver` hook. Both are supported; the
    choice decides which conformance profile becomes required. Not blocking in this
    increment.
15. **Default synthetic model name** (OPEN-03) reported by the scripted engine in every
    `model` field and in `/v1/models`. Resolved by the owner on 2026-11-14: the name is
    exactly `pulsar-console-synthetic`, which meets the plan's rule that synthetic model
    names contain `synthetic` (PLAN-2). ENG-02 delivers the default, the tests of API-08
    assert it, and API-17 keeps it.
16. **Prometheus metric prefix** (OPEN-22). Whether metric names follow the environment
    prefix. Blocks API-06.
17. **Logo** (OPEN-23). The neutral product mark (BRAND-2 allows SVG only). Blocks WEB-01.

### Lead decisions (recorded in the named contract)

18. **Ledger dispositions.** Resolved by a lead decision: the disposition set is
    `rust-test`, `scenario`, `web-test`, `shim`, `vendor-render`, `deviation`,
    `not-applicable` and `pending` (see Decision 13 and section 3.2 of
    [contracts/parity-ledger.md](contracts/parity-ledger.md)). Still open: the
    `upstream-skipped` marker (OPEN-36) and the format of the shim and vendor-render
    records (OPEN-38).
19. **Deviation ids for later deviations** (OPEN-39). Resolved by the lead on 2026-11-14
    (LD29) and recorded in `contracts/deviations.md` (GOV-06): an owner-approved proposal
    keeps its `P-` id as its deviation id; a later owner-approved deviation that was never
    a listed proposal takes the next free `P-` number; ids are never reused; a declined
    proposal keeps its id, marked declined.
20. **Upstream-skipped methods** (OPEN-36). Methods the donor's own CI skips (official
    SDK, poppler, tokenizer packs, transformers, a real engine) still need a disposition;
    whether evidence C or D may satisfy them. CNF-12.
21. **Ids.** Resolved by a lead decision: no `uuid` crate; ids are random hexadecimal from
    operating-system randomness (API-01).
22. **Web crate HTTP types** (OPEN-40). Whether `console-web` uses the `http` and `bytes`
    crates (WEB-02 proposal) or the transport's own types under B1. WEB-02.
23. **Developer asset override** (OPEN-41). Whether an opt-in development mode serves
    dashboard assets from a directory, given that no filesystem path is ever served in the
    product. WEB-02.
24. **Staged-scan word rules in console paths** (OPEN-42). `check_staged.sh` rejects words
    such as `cuda`, `nvidia` and `target_os linux` under some paths. Whether
    `console/tools/check-hygiene.sh` applies that rule to `console/` given that the M9
    ports cannot avoid those words in code and test data. GOV-06, M9.
25. **Timing-sensitive tests** (OPEN-43). Whether multi-conversation and fair-slice tests
    run in the default blocking jobs or in a separate job with scaled time. ENG-07,
    ENG-11.
26. **Ownership of product facts** (OPEN-44). Confirm that GLM-5.3 pack detection,
    template choice and memory constants (donor `glm_dsa_product.py`) split between
    `console-prompt` and `console-manage`. OPS-04, PRM-05.
27. **Engine-only `LOGP` command** (OPEN-45). Exposed by the engine conformance binary for
    later evidence work, or encoded and unused. ENG-18.
28. **Unicode tables** (OPEN-46). Resolved by a lead decision: residual differences
    between Python's regex module and the Rust regex crates are accepted when a test names
    and pins them; PRM-04 records them.
29. **Fetching new crates in CI** (OPEN-47). Resolved by a lead decision: CI fetches crates
    that are not already cached (`miniz_oxide`, `roxmltree`, `html-escape`, `image`,
    `minijinja`, and others) with `cargo fetch --locked` at run time; nothing is
    vendored.
30. **Contract review before Responses and MCP routes** (OPEN-48). Whether the Responses
    and MCP contract documents go to the owner before RSP-06 and RSP-11 start, since they
    fix behavior the HTTP-level tests lock in.
31. **preact.js provenance** (OPEN-49). Keep the vendored bundle byte-identical with a
    recorded hash, or compare it once against the published Preact 10.29.8 and htm 3.1.1
    packages, which needs a network step. WEB-01.
32. **Local browser driver** (OPEN-50) for the manual end-to-end suite (`safaridriver`
    needs a one-time administrator enable). WEB-06.

### Verification items

33. **Local toolchain enforcement** (OPEN-51). Resolved by a lead decision: the owner's
    build host has `rustc` 1.97.1 from a package-manager install without `rustup`, so
    `console/rust-toolchain.toml` is not enforced locally; `console/tools/check-toolchain.sh`
    enforces it in the per-task gate (Decision 15).
34. **macOS process statistics** (OPEN-52). Whether the pinned `libc` exposes the Apple
    process statistics calls the supervision sampler needs; if not, a small `extern`
    declaration or another crate is needed. ENG-08, OPS-18.
35. **Windows type-check** (OPEN-53). Installing the Windows standard library for the cross
    type-check in the Linux job. API-18, B11.
36. **Path filter and required checks** (OPEN-13). How a required check would behave for a
    pull request that the path filter skips (no console path changed) has not been
    checked; it must be confirmed on GitHub when item 1 is decided.
