# Quickstart: PulsarMLX Console Serving Parity

**Date**: 2026-11-14

**Status**: The toolchain check of section 2, the `cargo` commands of section 3 and the
two check scripts of section 4 were run on 2026-11-14 at commit `1a2db9b9`, with a clean
working tree, against the empty skeleton. Section 4 also records the negative cases, which
were observed earlier the same day on the uncommitted working tree. Every other command is
planned. At M0 the only runnable content is the empty `console/` workspace skeleton and
its check tools (GOV-06). Each command is marked **Available from** with the work
package that makes it real. When a package lands, it updates its entries here in the same
change: it replaces "planned" with the observed result, the date, the commit and any
excluded or failing coverage, as constitution principle III and XII require. Treat any
count recorded here as evidence for that commit only.

Everything the console serves in this increment is synthetic. No command here loads or
serves a real model, and no project-maya code is run on a contributor's machine.

## 1. Read the source of truth

From the repository root:

```sh
sed -n '1,200p' specs/022-console-serving-parity/spec.md
sed -n '1,200p' specs/022-console-serving-parity/plan.md
sed -n '1,200p' specs/022-console-serving-parity/tasks.md
sed -n '1,200p' docs/architecture/decisions/0008-console-serving-ahead-of-stage-f.md
```

**Available from**: GOV-01 to GOV-04 (M0).

`.specify/feature.json` is not updated for this feature and must not be edited; the Spec
Kit artifacts here are authored by hand (plan exception E4).

## 2. Toolchain and build environment

The console is a standalone nested workspace. Run every Cargo command from `console/`, so
`console/rust-toolchain.toml` (Rust 1.97.1 with `rustfmt` and `clippy`) applies. Commands
run from the repository root build the root workspace, not the console.

```sh
cd console
bash tools/check-toolchain.sh   # fails unless rustc -V reports the pinned 1.97.1
cargo -V
```

Without `rustup`, the pin file is ignored, so the script enforces it: it reads the channel
from `console/rust-toolchain.toml` and fails unless `rustc -V` reports exactly that version
(a lead decision of 2026-11-14). On the owner's build host on 2026-11-14, `rustc -V`
reported `1.97.1` from a package-manager install without `rustup`, and the script printed
its `ok` line.

Keep build output outside the repository and build at low priority on a shared machine:

```sh
# Any directory outside the repository will do.
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$HOME/.cache/pulsar-console-target}"
```

Prefix long builds with `nice -n 10`, as in `console/README.md`. Before a build wave on
the owner's build host, check that no engine qualification process is running; stop when
the owner says a qualification run is coming.

**Available from**: GOV-06 (M0) for the pin file and the script.

## 3. Build and test the workspace

From `console/`:

```sh
bash tools/check-toolchain.sh
cargo fetch --locked
cargo fmt --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked
```

These are the forms `.github/workflows/console.yml` runs, except the toolchain script: CI
keeps its own `rustc -V` assertion. `cargo fetch --locked` fetches crates that are not
already cached; nothing is vendored (a lead decision of 2026-11-14). **Available from**:
GOV-06 (M0), on the empty skeleton. Each later package adds its tests to the same
commands. Observed on 2026-11-14 at commit `1a2db9b9`, on the owner's build host (macOS,
Apple Silicon): the toolchain script printed its `ok` line, `cargo fetch --locked` had
nothing to fetch because the skeleton has no dependencies, and `cargo fmt --check`,
`cargo clippy` and `cargo test` passed, with one skeleton test. No Linux run and no CI run
is recorded yet, because nothing has been pushed. That says nothing about any console
behavior, because none is implemented.

The root commands in `CONTRIBUTING.md` (`cargo check --workspace --all-targets`,
`cargo test --workspace --no-fail-fast`) do not build `console/` (plan exception E1); run
them as well only when a change also touches root-workspace files, which this feature
never does.

## 4. Non-interference and hygiene checks

Run both before every commit, from the repository root:

```sh
console/tools/check-boundary.sh
console/tools/check-hygiene.sh
git diff --stat origin/main...HEAD
git diff --check
```

- `check-boundary.sh` fails when a change touches a path outside the allowlist in the plan,
  when the root `Cargo.toml`, `Cargo.lock` or `.github/workflows/macos.yml` differ from
  the merge base with `main`, when a file under `console/` or the feature directory would
  be ignored by `.gitignore` or uses a trap name, when a console manifest has a path
  dependency outside `console/`, or when a reserved engine-track name is used.
- `check-hygiene.sh` applies the content rules ported from
  `scripts/research/check_staged.sh` and the documentation credential scan (credentials,
  binary files, sizes, home-directory paths, UUIDs, host and user JSON values) and rejects
  AI attribution in added lines and in commit messages.

Without options both scripts measure the working tree as well as the commits since the
merge base (local use before a commit); CI passes `--committed`. Options and exit codes are
documented in each script's usage text.

**Available from**: GOV-06 (M0).

**Observed (negative cases)**: observed on 2026-11-14 on the uncommitted M0 working tree,
copied into a throwaway clone outside the repository. Each case was set up on its own and
reverted before the next, and each made the named check fail with a non-zero exit:

| Case | Script and check that failed |
| --- | --- |
| A change to the root `Cargo.toml` (in the working tree, staged, and committed with `--committed`) | `check-boundary.sh`: allowlist and frozen-blobs |
| A file under `crates/` | `check-boundary.sh`: allowlist |
| A trap-named directory (`console/logs/`) | `check-boundary.sh`: ignored-files |
| A trap-named file (a `*.trace` file under `console/`) | `check-boundary.sh`: ignored-files |
| A single-quoted `path` dependency that leaves `console/` | `check-boundary.sh`: path-deps |
| A `.cargo/` directory under `console/` | `check-boundary.sh`: path-deps |
| A reserved package name (`pulsar-serve`) | `check-boundary.sh`: reserved-names |
| A submodule (gitlink) under `console/`, staged and committed | `check-hygiene.sh`: file-mode |
| A binary file (a NUL byte after the first 8,000 bytes) | `check-hygiene.sh`: binary-file |
| An oversized file (1.2 MB) | `check-hygiene.sh`: file-size |
| A credential-shaped assignment | `check-hygiene.sh`: credential-assignment |
| An absolute home-directory path | `check-hygiene.sh`: home-path |
| An attribution line in a file | `check-hygiene.sh`: ai-attribution |
| An attribution line in a commit message | `check-hygiene.sh`: commit-attribution |
| An allow marker whose id is not in `hygiene-allow.txt` | `check-hygiene.sh`: allow-marker |
| An added line that starts with `+++ ` (in a new file and in a changed tracked file) | `check-hygiene.sh`: the line gate its content matches (ai-attribution, home-path) |

The staged submodule case did not fire at first: in working-tree mode `check-boundary.sh`
listed only working-tree and untracked changes, so a staged gitlink with no checked-out
directory was never scanned. The script now lists staged changes as well, and the case
fires.

**Observed (positive runs)**: on 2026-11-14 at commit `1a2db9b9`, eight commits after the
merge base `aaf076f1`, with a clean working tree, in the form the workflow uses:

```sh
bash console/tools/check-boundary.sh --base origin/main --committed
bash console/tools/check-hygiene.sh --base origin/main --committed
```

Both passed: 44 changed paths and all five boundary checks; every hygiene gate over 44
files, 22,455 added lines and 8 commit messages. Neither script changed the working tree
or the index. The repository's own `scripts/research/check_staged.sh` also passed on the
staged content of each of the eight commits.

**Observed (interpreter)**: the check tools are bash scripts. At the same commit, each of
the three (`check-boundary.sh`, `check-hygiene.sh`, `check-toolchain.sh`), started with
`sh`, `dash` or `bash --posix`, stopped at once with exit status 2 and a message that says
to use bash. Before that guard was added, `sh console/tools/check-hygiene.sh` stopped
part-way with a syntax error.

## 5. Run the server with the scripted engine

The first end-to-end target of M1 is a streamed answer over `curl`. The command-line
interface is defined by API-17; until then the server is started from the test kit
(API-19). Once available, start the server with the scripted engine and a
PulsarMLX-authored synthetic chat template, read the bound port from its ready line, and:

```sh
curl -N http://127.0.0.1:<port>/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"hello"}],"stream":true}'
```

Check the frames (`data:` chunks, a final chunk with `finish_reason` and `usage`, then
`data: [DONE]`) and that the server reports a synthetic engine.

**Available from**: API-08 with API-07, ENG-02 and ENG-10 (M1); the documented CLI from
API-17 (M4). Not yet available.

An Anthropic message:

```sh
curl -N http://127.0.0.1:<port>/v1/messages \
  -H 'Content-Type: application/json' \
  -d '{"max_tokens":64,"messages":[{"role":"user","content":"hello"}],"stream":true}'
```

**Available from**: API-09 (M2). Not yet available.

Security posture checks by hand (SEC-1): a POST with a foreign `Origin` header, or with a
non-JSON content type, is refused; a request whose `Host` is not on the loopback allowlist
is refused when bound to loopback.

**Available from**: API-03 (M1). Not yet available.

## 6. Run through the line-protocol engine

Repeat section 5 with a run config that points the line-protocol engine at a fake engine
binary from `console-fake-engines`, then kill the fake engine mid-answer and confirm the
503 with the restart message and that the next request restarts it.

**Available from**: ENG-05, ENG-06 and ENG-08 (M3). Not yet available.

## 7. Monitoring and admin routes

```sh
curl http://127.0.0.1:<port>/health
curl http://127.0.0.1:<port>/metrics
```

`/health` must state that the engine is synthetic.

**Available from**: API-06 (M4). Not yet available.

## 8. Dashboard

Open `http://127.0.0.1:<port>/` in a browser against the scripted engine. Send, stream,
stop, reload mid-answer and switch views; confirm the permanent "Synthetic engine: no real
model" badge, the security headers on every asset, and that a cross-origin POST is
refused.

**Available from**: WEB-02 and API-12, with WEB-03 and WEB-07 (M8). Not yet available.

Web page-logic tests, run with Node and no packages (the exact path is fixed by CNF-15 and
WEB-04):

```sh
node --test <web test directory>
```

**Available from**: WEB-04 and CNF-15 (M8). Not yet available.

## 9. Parity ledger and reference replay

The ledger checker resolves every row of `console/parity/ledger.json` and fails on a
dangling or missing row; the replay compares the Rust server with the committed recorded
references, offline. Both run inside `cargo test` in CI; their standalone invocation is
defined by the conformance packages.

**Available from**: the ledger skeleton from GOV-06 (M0); the comparator from CNF-04 (M1);
the full checker and inventories from CNF-12 and the replay of captured references from
CNF-09 (M10). Not yet available.

## 10. CI jobs

`.github/workflows/console.yml` is path-filtered to console paths. Its blocking jobs each
name the local command that reproduces them: preflight (the two check scripts of
section 4), Rust on Linux (toolchain assertion, `cargo fetch`, `fmt`, `clippy`, `test`),
Rust on macOS arm64 (toolchain and architecture assertion, `cargo fetch`, `test`), and a
summary job. The blocking web logic job that binding decision B12 in
[tasks.md](tasks.md#binding-cross-cutting-decisions) requires is not in the M0 workflow
file. The two donor test files run through the shim and the vendor-template renders run
only in the manual reference job; blocking CI checks their committed records.

**Available from**: GOV-06 (M0) for the workflow and its blocking jobs; CNF-01 (M1)
extends it; CNF-15 (M8) for the web logic job. No run has been observed yet; nothing is
pushed before owner checkpoint 2.

The manual `workflow_dispatch` jobs are dispatched by the owner or the lead, never run on
a contributor's machine: reference capture and the live differential against project-maya
at `7e68a30f`, the shim run of `serve/test_engine_contract.py` and `serve/test_stop.py`,
vendor-template render checks (hashes only), SDK client tests, the toolchain
drift canary and the browser end-to-end suite.

**Available from**: CNF-08, CNF-09, CNF-10, CNF-11, CNF-13 and CNF-17 (M10), and WEB-06
(M8) for the browser suite. Not yet available.

## Stop points

Stop and report instead of working around the problem when:

- `rustc -V` in `console/` does not print 1.97.1;
- either check script fails, or `git diff --stat origin/main...HEAD` shows a path outside
  the allowlist;
- a test needs a vendor chat template, a real model, network access in a blocking job, or
  project-maya code on a local machine;
- an engine qualification run is starting on the shared build host.
