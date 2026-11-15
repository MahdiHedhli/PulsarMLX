# PulsarMLX Console workspace

**Status (2026-11-15):** in development. The claim table below says which parts exist.
The M1 binary `pulsar-console` answers chat completion requests from a scripted synthetic
engine; nothing in this directory serves a real model.

This directory will hold PulsarMLX Console: a Rust serving layer and dashboard rebuilt
from the serving layer of project-maya (the donor, pinned at commit `7e68a30f`), driven
only by synthetic engines in this increment. The feature is specified in
[`../specs/022-console-serving-parity/`](../specs/022-console-serving-parity/) and the
decision to build it ahead of strategy Stage F is recorded in
[ADR 0008](../docs/architecture/decisions/0008-console-serving-ahead-of-stage-f.md).

## Claim status

| Item | Status |
| --- | --- |
| Cargo workspace with eight members: `console-pyjson`, `console-core`, `console-tokenizer`, `console-engine`, `console-http`, `console-testkit`, `console-conformance` and the `pulsar-console` binary | Present. Merged on 2026-11-14: `console-pyjson`, the `error` module of `console-http`, the `engine` module of `console-core` and the `cnf` runner skeleton of `console-conformance`. Merged on 2026-11-15: the `transport` module of `console-http`; the `request`, `sampling`, `config` and `fifo` modules of `console-core`; the `fake` module of `console-engine`; `console-tokenizer`; and the `scenario` module of `console-conformance`; then the `router` and `guard` modules of `console-http`, the `digest` and `turn` modules of `console-core`, and the `client`, `observe` and `process` modules of `console-conformance`; then the `inference` module of `console-http`, `console-testkit`, and the `normalize` and `compare` modules of `console-conformance`; then the `dialect::openai` module of `console-http` and the `pulsar-console` crate (its library, its `cli` module and the binary) (rows below). Every other crate and module is still a skeleton that declares its planned modules and implements nothing. |
| Python-compatible JSON, error model and ids (package API-01), `console-pyjson` and `console-http::error` | Implemented (commit `c2392605`, 2026-11-14) and qualified on synthetic inputs only: golden tables recorded from CPython 3.14.7, no donor code run; 182 workspace tests passed at commit `fb87f8a2` (quickstart section 3). Open: its refusal of an unpaired surrogate inside a string and its nesting bound of 1000 levels are proposals P-19 and P-20, awaiting the owner's decision, so the task stays unticked. |
| Backend seam and the synthetic-only guard (package ENG-01), `console-core::engine` | Implemented (commit `6200f4ac`, 2026-11-14) and qualified on synthetic backends only, with synthetic test engines in its tests. Open: the seam contract is draft 0.2 until the engine track's review is recorded (FR-039); four parse differences on engine `INFO` and `DONE` values are proposal P-21, awaiting the owner's decision. The turn driver calls the guard (ENG-10), and the process start of API-08 reaches it through the turn driver (commit `5b327fa8`, 2026-11-15). The task stays unticked. |
| HTTP/1.0 transport (package API-02), `console-http::transport` | Implemented (commit `d64685f7`, 2026-11-15) and qualified on synthetic inputs only: its tests drive it with a test handler, and no engine is involved. The request head is parsed by hand by CPython's rules (lead decision LD34). API-08 wires its environment settings at start (commit `5b327fa8`, 2026-11-15), and the two donor rows that needed the chat route are resolved with API-08's tests. Open: one donor row it named, QueuedKeepAlives, is still pending (owner API-09); Python's error page for a refused request head when `cors_origins` is set is proposal P-22, awaiting the owner's decision. The task stays unticked. |
| Request validation, sampling normalization and shared defaults (package API-04), `console-core::request` and `console-core::sampling` | Implemented (commit `89d40258`, 2026-11-15) and qualified on synthetic inputs only. Open: the joint test through the engine encoder needs ENG-03 (M3). The OpenAI dialect of API-08 calls it (commit `5b327fa8`, 2026-11-15). The task stays unticked. |
| Run-config store and environment settings (package API-15), `console-core::config` | Implemented (commit `9671312a`, 2026-11-15) and qualified on synthetic inputs only: five run configs recorded from CPython's `json.dumps(obj, indent=1)` are rewritten byte for byte. Open: five of its donor rows need the model routes of M7 or the listener; some typed accessors are left to ENG-15 and the OPS packages; five differences in the store are proposal P-23, awaiting the owner's decision; `allowed_hosts` is read, and API-08 passes it to the API-03 guard at start (commit `5b327fa8`, 2026-11-15). The task stays unticked. |
| Scripted engine and test engines (package ENG-02), `console-engine::fake` | Implemented (commit `c86cf84f`, 2026-11-15) and qualified on synthetic backends only. It reports synthetic provenance and the default model name `pulsar-console-synthetic`; a test-only engine that reports another provenance exists for the refusal tests and cannot be selected by any configuration, flag or environment variable. Open: 14 of its 21 listed donor rows are still pending (five were resolved with ENG-10 and two with API-08; the rest need the HTTP layer of later packages, the line-protocol client, the continuation packages (ENG-11) or the output pipeline (PRM-12)); two reload timing differences are left to ENG-12. The task stays unticked. |
| Engine FIFO (package ENG-09), `console-core::fifo` | Implemented (commit `5880f298`, 2026-11-15) and qualified on synthetic inputs only, with paused-time and stress tests. Open: one of its donor rows, QueuedKeepAlives, is still pending; its owner is API-09 (it was left pending by API-08); API-07 resolved the other, GoneClients, on 2026-11-15. The task stays unticked. |
| Byte-level BPE tokenizer, byte tokenizer and incremental detokenizer (package PRM-04), `console-tokenizer` | Implemented (commit `7b58580f`, 2026-11-15) and qualified on synthetic vocabularies only; round trips on a real vocabulary are unverified (the real-pack test is ignored without `PULSAR_CONSOLE_PACK_TOKENIZER`). Open: its pack-loading refusals and size limits are proposal P-24, awaiting the owner's decision. The task stays unticked. |
| Scenario format and loader (package CNF-02), `console-conformance::scenario` and the contract files `conformance-scenario.schema.json`, `rename-map.json` and `volatile-fields.json` | Implemented (commit `8dc26783`, 2026-11-15); the task is ticked. Eleven sample scenarios load; nothing runs a scenario yet (CNF-03, CNF-04, CNF-07, CNF-09). |
| Router, authentication, CORS and cross-site guards (package API-03), `console-http::router`, `console-http::guard` and `console-core::digest` | Implemented (commit `60fa1461`, 2026-11-15) and qualified on synthetic inputs only: its tests drive every donor route through the router with a probe handler in place of the handlers of later packages, and at that merge no binary served it. Since API-08 (commit `5b327fa8`, 2026-11-15) the `pulsar-console` binary serves the router, with the guard, the API key, the CORS origins and `allowed_hosts` wired at start. Open: eight of its donor rows need the handlers of later packages (API-08 resolved two); the matching details of the `Host` check (LD43) and the reading of `allowed_hosts` on a loopback bind (LD30) await the owner's confirmation. The task stays unticked. |
| Early `Host` refusal (the follow-up to API-03), `console-http::transport` (`Handler::early_refusal`) and `console-http::router` | Implemented (commit `50179f0d`, 2026-11-15) and qualified on synthetic inputs only: the `Host` check now also runs before the transport's 501 page for an unserved method and its P-2 400 page. Open: the 431 pages, and the request-line 400, 414 and 505 pages, have no usable headers and are still answered without the check. The `pulsar-console` binary of API-08 serves it. |
| Engine turn driver (package ENG-10), `console-core::turn` | Implemented (commit `4e7c438a`, 2026-11-15) and qualified on synthetic backends only, with the scripted engine and the test engines of ENG-02 on a paused clock. It calls the synthetic-only guard on every engine start it performs: first start, restart, model switch, context reload, and the start after an idle unload, a death or a caught engine panic. Open: 24 of its donor rows are still pending (API-08 resolved five); they need the HTTP layer of later packages, the line-protocol client or the continuation packages; it runs one engine call at a time (several places at once is ENG-07's), and the continuations are ENG-11's. The task stays unticked. |
| Raw HTTP client and observation recorder (package CNF-03), `console-conformance::client` and `::observe` | Implemented (commit `21f5be60`, 2026-11-15); the task is ticked. Its self-tests run against servers they start themselves on loopback; it has not been run against the console's own transport or a binary, and the scenario format cannot yet express a half-close or a disconnect right after the request (CNF-09). |
| Process harness (package CNF-07), `console-conformance::process`, the test-only child `cnf_child` and the draft contract [`cli.md`](../specs/022-console-serving-parity/contracts/cli.md) | Implemented (commit `d270f113`, 2026-11-15) and proven on macOS only, with the test-only child. The `pulsar-console` binary of API-08 now exists, but this harness has not been run against it yet. Open: its Linux paths are unverified until a CI run; that the ready line names the bound port under `--port 0` is proposal P-25, awaiting the owner's decision. The task stays unticked. |
| Inference request lifecycle driver (package API-07), `console-http::inference` | Implemented (commit `f6c42bb4`, 2026-11-15) and qualified on synthetic backends only: its tests drive it with a probe dialect in place of the client dialects, and ENG-02's synthetic engines behind ENG-10's turn driver. It takes a chat request from the route to its last byte: the overloaded gate, the SEC-6.1 strip of client keys that start with `_`, the turn, the stream with its keep-alives, and the error table (P-3, and the P-8 mapping point, tested with stand-ins). Since API-08 (commit `5b327fa8`, 2026-11-15) it serves the OpenAI dialect on `/v1/chat/completions`, and since commit `87d96406` its turn trace carries the donor's `http`, `body` and `json` marks at the instants the router recorded. Open: five of its seven donor rows are still pending: the two EngineDeath rows, QueuedKeepAlives and the MaxTokens debug-line row, which API-08 left pending, and the Dashboard 503-while-reloading row, which waits for ENG-12; its seams to ENG-12, OPS-22, RSP-16 and the prompt packages keep their M1 defaults; a start that fails during a request is answered 503, where the donor answers nothing: proposal P-26, awaiting the owner's decision. The task stays unticked. |
| HTTP test kit (package API-19), `console-testkit` | Implemented (commit `b1f4709a`, 2026-11-15) and qualified on synthetic backends only: a raw client, an SSE reader, an in-process test server over the transport, the router and the turn driver, engine helpers, a process helper and ledger checks; the tests of API-02 and API-03 use it. The tests of API-08 use its process helper against the `pulsar-console` binary. Open: the fake engine binaries of M3 do not exist yet; the chat-template fixture is M2's; its ledger checks work at source level only, and the full checker is CNF-12's. The task stays unticked. |
| Normalizer and comparator (package CNF-04), `console-conformance::normalize` and `::compare` | Implemented (commit `7259f941`, 2026-11-15) and qualified on synthetic inputs only: its negative self-tests show that each one-field mutation is a difference, and only the values listed in `volatile-fields.json` are replaced. The follow-up to CNF-04 (commit `55e81f27`, 2026-11-15) derives the value of `Content-Length` from the normalized body (lead decision LD44), accepts a stored reference only as a fixed point of normalization under its recording context, requires an annotation to name the kind of difference it covers or both expected values, and limits four `json-key` fields to the root object; the task is ticked. Open: nothing runs a scenario end to end yet; how hardware and machine readings are compared is open item OPEN-61. |
| OpenAI Chat Completions dialect, plain-content subset (package API-08), `console-http::dialect::openai` | Implemented (commit `5b327fa8`, 2026-11-15) and qualified on synthetic backends only, with the scripted engine of ENG-02 behind the turn driver: its tests compare golden SSE transcripts and JSON bodies, and resolve 11 donor rows. A local demonstration on synthetic input on 2026-11-15 (quickstart section 5) answered a streamed and a whole chat completion; no CI run covers it. All text is answer content under the M1 output stage, and the prompt is the stand-in of lead decision LD45, so its token counts are not parity figures. Open: 34 of its donor rows are pending; reasoning, streamed and whole tool calls and the JSON-mode prompt instruction need the output parsers and prompt packages of M2, and some rows need API-09 and API-06; proposals P-25 and P-27 await the owner's decision; whether a run config's `model_name` may rename the synthetic engine is owner item OPEN-62. The task stays unticked. |
| The `pulsar-console` binary, minimal M1 entry point (package API-08, lead decision LD31), `console/crates/pulsar-console` | Implemented (commit `5b327fa8`, 2026-11-15) and qualified on synthetic backends only. It serves a scripted synthetic engine and no real model: its `main` names only the scripted engine, the refusal of an engine that is not synthetic at process start is pinned by tests, and before its ready line it prints `[console] engine: scripted, synthetic provenance - no real model is served` (LD46). It serves only `/v1/chat/completions`; its ready line keeps the donor's text, which also names `/v1/responses` and `/v1/messages` (LD54). In the lead's local demonstration on 2026-11-15 at commit `df01fec5` (macOS on Apple Silicon) it started, answered a streamed chat completion and refused foreign pages, foreign host names, a request that is not JSON and an option it does not have (quickstart section 5); no CI run covers it. Open: the full command line, the line engine, signals and the shutdown order are API-17's (M4). |
| Anthropic and Responses dialects, every route but `/v1/chat/completions`, the dashboard, reasoning and tool calls on the chat route | Planned (milestones M2 to M9). Not implemented. A request to a route M1 does not serve yet is answered 404. |
| Parity ledger, [`parity/ledger.json`](parity/ledger.json) | Present. 913 rows, one per donor test method. At commit `df01fec5` (2026-11-15), 50 rows are resolved (48 `rust-test`, 2 `deviation`) and 863 are `pending`; 248 of the pending rows name the package that owns them, and 615 have no owner recorded yet. |
| Boundary, hygiene and toolchain checks, [`tools/`](tools/) | Present. Meant to be run locally before each commit. They have run in CI once, in the `console` workflow run at commit `0f4bc320` on 2026-11-14, which succeeded. |
| CI, [`../.github/workflows/console.yml`](../.github/workflows/console.yml) | Written. Run once on GitHub: run 43674353677, at commit `0f4bc320` (the M0 skeleton and the M1 scaffold) on 2026-11-14, succeeded. CNF-01's revision of the workflow (commit `fb87f8a2`, 2026-11-14), with named failure classes, has not run; nothing has been pushed since `0f4bc320`, so no CI run covers any M1 package or the revised workflow, and the Linux behavior of the M1 code, the `pulsar-console` binary and CNF-07's process harness included, is unobserved. The lead's local gate run at commit `df01fec5` (2026-11-15, macOS on Apple Silicon) passed, with 1,206 tests passed and 1 ignored (quickstart section 3). |
| Real model serving | Out of scope for this increment. When built, the work can at most be described as "qualified on synthetic backends". |

Nothing here may be described as working until its command, environment, input and
result are recorded, as constitution principle III requires.

In the table, "qualified on synthetic inputs only" and "qualified on synthetic backends
only" state the limit of a row's evidence: its tests pass on the build host against
synthetic inputs or engines, with the commands and results recorded in the quickstart.
The roadmap's status "Qualified on synthetic backends" also needs the recorded CI jobs,
and no M1 package has that yet, because nothing has been pushed since `0f4bc320`.

## Synthetic engines only

The server refuses to start an engine that does not report synthetic provenance, on every
path that admits an engine; the owner decided this on 2026-11-14. The guard itself exists
(ENG-01), the turn driver calls it on every engine start it performs (ENG-10), and the
process start of the `pulsar-console` binary goes through the turn driver, so an engine
that is not synthetic is refused before anything is served (API-08). No command-line
flag, environment variable, configuration key or Cargo feature bypasses the refusal.
[`../docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md`](../docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md)
is the one place that says what must be done before the server may start a real engine.

## A separate workspace

`console/` is a standalone, nested Cargo workspace with its own
[`Cargo.toml`](Cargo.toml), `Cargo.lock` and [`rust-toolchain.toml`](rust-toolchain.toml)
(Rust 1.97.1 with rustfmt and clippy). It is **not** a member of the root workspace, so
the root commands in [`../CONTRIBUTING.md`](../CONTRIBUTING.md)
(`cargo check --workspace`, `cargo test --workspace`) and the `macOS baseline` workflow
never build it. A green root build says nothing about this directory.

Run cargo from this directory, never from the repository root with `--manifest-path`:
rustup reads `rust-toolchain.toml` from the current directory upward, so the pin applies
only when the working directory is `console/` or below. Keep the target directory outside
the repository, because the root `.gitignore` drops any directory named `target`,
`debug` or `release`, and because builds share the machine with engine qualification
runs. Without rustup the pin file is ignored, so check the compiler first; the script
fails unless `rustc -V` reports exactly the pinned version:

```sh
cd console
bash tools/check-toolchain.sh
# Any directory outside the repository will do.
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$HOME/.cache/pulsar-console-target}"
nice -n 10 cargo fmt --check
nice -n 10 cargo clippy --locked --all-targets -- -D warnings
nice -n 10 cargo test --locked
```

Before each commit, from the repository root:

```sh
console/tools/check-boundary.sh
console/tools/check-hygiene.sh
```

Both take `--base REF` (default `origin/main`) and `--committed` (check only
`merge-base..HEAD`, as CI does). Each prints one line per check and exits non-zero on
any failure.

| Tool | What it checks |
| --- | --- |
| [`tools/check-boundary.sh`](tools/check-boundary.sh) | Every changed path is on the allowlist below; root `Cargo.toml`, `Cargo.lock` and `.github/workflows/macos.yml` equal the merge base byte for byte; nothing under `console/` or the feature directory is ignored by git or uses a `.gitignore` trap name; no manifest under `console/` points outside it and no `.cargo/` directory exists there; no reserved engine-track name is used. |
| [`tools/check-toolchain.sh`](tools/check-toolchain.sh) | `rustc -V`, run from `console/`, reports exactly the channel pinned in `rust-toolchain.toml`. It prints one line and exits non-zero on a mismatch or when `rustc` is missing. |
| [`tools/check-hygiene.sh`](tools/check-hygiene.sh) | Added content has no submodule or other non-regular Git object, binary file, symbolic link, file over 1 MiB, more than 16 MiB in total, model and tensor extension or whitespace error; added lines have no credential-shaped value, home-directory path, UUID, machine identifier, literal `host` or `user` JSON value or AI attribution; commit messages in the range have no attribution lines. Rare justified exceptions to the heuristic line gates (credential assignment, bearer token, UUID, machine identifier, identity JSON) use a same-line allow marker whose id is listed in [`tools/hygiene-allow.txt`](tools/hygiene-allow.txt). |
| [`tools/list_donor_tests.py`](tools/list_donor_tests.py) | Lists the donor's test methods by parsing them as text; it regenerates the parity ledger. See [`parity/README.md`](parity/README.md). |

## Non-interference rules

The engine track works in the same repository, and some of its evidence is bound to file
hashes. This work therefore follows these rules, which `check-boundary.sh` enforces where
a machine can:

- **Paths this work may touch:** `console/**`, `specs/022-console-serving-parity/**`,
  `docs/console/**`, `docs/roadmap/CONSOLE_ROADMAP.md`,
  `docs/roadmap/PULSARMLX_STRATEGY.md`, `docs/upstream/PROJECT_MAYA.md`,
  `docs/upstream/PROJECT_MAYA_SYNC.md`,
  `docs/architecture/decisions/0008-console-serving-ahead-of-stage-f.md`, `NOTICE.md`,
  `README.md`, `CONTRIBUTING.md` and `.github/workflows/console.yml`.
- **Never touched:** the root `Cargo.toml` and `Cargo.lock`,
  `.github/workflows/macos.yml`, anything under `crates/`, `experiments/`, `fixtures/`,
  `scripts/` or `docs/research/`, `.specify/`, `.gitignore`, the root
  `pyproject.toml` and `uv.lock`.
- **No path dependency outside `console/`.** Every third-party dependency is pinned with
  `=` in `[workspace.dependencies]` and recorded with its license in the feature's
  `research.md`.
- **No trap names.** The root `.gitignore` silently drops directories named `models`,
  `weights`, `checkpoints`, `logs`, `dist`, `env`, `debug`, `release` and `target`, and
  files such as `*.log`, `*.key`, `*.pem`, `secrets.*`, `credentials.json`, `mcp.json`,
  `*.trace.json`, `*.bench.json` and `*.prof*`. Do not use those names anywhere under
  `console/`. Test data lives in `testdata/` or `tests/data/`, never in a `fixtures/`
  directory at the console root, and generated fixtures are built in code.
- **No binary files, no vendor chat templates, no model weights.**
- **Reserved names** stay with the engine track: the packages `mlx-expert-ranges`,
  `mlx-expert-mlp`, `expert-residency-core`, `packed-affine-adoption`, `serve`,
  `pulsar-serve` and `pulsar-serve-synthetic`, and the directories `experiments/`,
  `crates/serve-synthetic` and `docs/serving/`.
- **project-maya is data, not a runtime.** Its code is never executed on a development
  machine; it runs only in a manual GitHub Actions reference job, which arrives with a
  later work package. No project-maya engine binary is launched in this increment.

What the rules guarantee: no file the engine track edits or hashes changes. What they do
not guarantee: the tree identity of `main` changes when this work merges, like any commit,
so the merge order is decided with the owner (OPEN-14 in the open-item register,
[`checklists/analysis.md`](../specs/022-console-serving-parity/checklists/analysis.md)).

## Picking this work up

A maintainer new to this work reads, in this order:

1. The feature specification,
   [`spec.md`](../specs/022-console-serving-parity/spec.md).
2. The plan, [`plan.md`](../specs/022-console-serving-parity/plan.md).
3. The tasks, [`tasks.md`](../specs/022-console-serving-parity/tasks.md), including its
   [per-task gate](../specs/022-console-serving-parity/tasks.md#per-task-gate-before-commit).
4. The register of open items in
   [`checklists/analysis.md`](../specs/022-console-serving-parity/checklists/analysis.md#9-register-of-open-items).
5. The deviation register,
   [`contracts/deviations.md`](../specs/022-console-serving-parity/contracts/deviations.md).
6. The parity ledger contract,
   [`contracts/parity-ledger.md`](../specs/022-console-serving-parity/contracts/parity-ledger.md).
7. [ADR 0008](../docs/architecture/decisions/0008-console-serving-ahead-of-stage-f.md).
8. The [console roadmap](../docs/roadmap/CONSOLE_ROADMAP.md).
9. [`../docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md`](../docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md).

Progress is read from the checkboxes in `tasks.md` and from the parity ledger,
[`parity/ledger.json`](parity/ledger.json), not from this README.

## Layout

Only the files in the claim table exist today. The planned layout, from the feature
[`plan.md`](../specs/022-console-serving-parity/plan.md):

| Path | Planned content |
| --- | --- |
| `crates/` | `console-pyjson`, `console-core`, `console-tokenizer`, `console-prompt`, `console-engine`, `console-http`, `console-responses`, `console-mcp`, `console-attach`, `console-media`, `console-manage`, `console-host`, `console-launch`, `console-web` and the `pulsar-console` binary; test-only `console-fake-engines`, `console-testkit`, `console-conformance`, `console-web-e2e` and `xtask`. |
| `web/` | Phase 1 dashboard, adapted from the donor's JavaScript, with neutral product identity. |
| `conformance/` | Scenarios, recorded references and the reference pin. |
| `parity/` | The parity ledger. |
| `tools/` | Boundary, hygiene and toolchain checks and the donor test lister. |
| `LICENSES/` | Full license texts: the donor's now, and each third-party text with the change that imports its component. |
