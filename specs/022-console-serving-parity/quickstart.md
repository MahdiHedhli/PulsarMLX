# Quickstart: PulsarMLX Console Serving Parity

**Date**: 2026-11-14

**Status**: The toolchain check of section 2, the `cargo` commands of section 3 and the
two check scripts of section 4 were run on 2026-11-14 at commit `1a2db9b9`, with a clean
working tree, against the empty skeleton. Section 4 also records the negative cases, which
were observed earlier the same day on the uncommitted working tree. Sections 3, 9 and 10
also record the first three M1 packages, merged on 2026-11-14 (API-01, ENG-01 and CNF-01),
and the first CI runs. Sections 3 and 9 also record the seven packages of wave 2 of M1,
merged on 2026-11-15 (API-02, API-04, API-15, ENG-02, ENG-09, PRM-04 and CNF-02), and
sections 3, 5, 9 and 10 the four packages of wave 3 of M1, merged on 2026-11-15 (API-03,
ENG-10, CNF-03 and CNF-07), and sections 3, 5, 9 and 10 the four packages of wave 4 of M1,
merged on 2026-11-15 (API-07, API-19, CNF-04 and a follow-up to API-03). Every other
command is planned. At M0 the only runnable
content is the empty `console/` workspace skeleton and its check tools (GOV-06). Each
command is marked **Available from** with the work package that makes it real. When a
package lands, it updates its entries here in the same change: it replaces "planned"
with the observed result, the date, the commit and any excluded or failing coverage, as
constitution principle III and XII require. Treat any
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
was recorded at that commit; the first CI run, at commit `0f4bc320`, is recorded in
section 10. That says nothing about any console behavior, because none was implemented at
that commit.

**Observed (API-01, Python-compatible JSON and the error model)**: merged on 2026-11-14 at
commit `c2392605`. From `console/`:

```sh
nice -n 10 cargo test --locked -p console-pyjson -p console-http
```

In the package clone before the merge, 22 `console-pyjson` unit tests, 14 golden
integration tests in `tests/api01_pyjson_golden.rs`, 4 doctests, 2 `console-http::error`
unit tests and 11 tests in `tests/api01_error.rs` passed (53 tests, the whole workspace of
that clone), and 50 consecutive runs of the same command passed; the lead's run at
`fb87f8a2`, below, confirmed them. The golden tables were recorded from CPython 3.14.7
with `python3 -I` and the standard library only; no donor file was run. They cover 69
values (wire and default form), 160 option pairs (indent, sort_keys, separators,
ensure_ascii), 46 floats plus 4 exact-tie cases, 42 indent=1 documents that round-trip
byte for byte, 81 `json.loads(str)` outcomes with CPython's messages and positions, 39
`json.loads(bytes)` outcomes, and 10 `raw_decode` cases. CPython accepts two inputs that
the console refuses: a string holding an unpaired surrogate, and nesting deeper than 1000
levels. These are proposals P-19 and P-20, awaiting the owner's decision
([deviation register](contracts/deviations.md#deferred-awaiting-owner-decision)); the
behavior changes if the owner declines either. Not done here: `json_from_text` (API-08,
PRM-16) and the product wording of the overloaded message (API-07).

**Observed (ENG-01, the backend seam in `console-core::engine`)**: merged on 2026-11-14 at
commit `6200f4ac`. From `console/`:

```sh
cargo test --locked -p console-core --lib
cargo test --locked -p console-core --test eng01_guard --test eng01_ledger --test eng01_seam
```

The first command runs the 26 unit tests of `console-core::engine`; the second runs the 68
integration tests (8 in `eng01_guard`, 39 in `eng01_ledger`, 21 in `eng01_seam`).
Observed with `rustc` 1.97.1 in the package clone before the merge: 94 `console-core`
tests passed, 0 failed, and 50 consecutive runs of the `console-core` suite had no
failure; the lead's run at `fb87f8a2`, below, confirmed them. Everything runs offline,
with synthetic test engines only; nothing here is qualified beyond synthetic backends. Not
done at that commit: no admission path called the guard yet (ENG-10 has called it since
wave 3, below; the process-start refusal is API-08's); the seam contract stays
draft 0.2 until the engine track's review is recorded (FR-039, OPEN-30); and the four
parse differences on engine `INFO` and `DONE` values are proposal P-21, awaiting the
owner's decision.

**Observed (lead's gate run after wave 1 of M1)**: on 2026-11-14 at commit `fb87f8a2`, on
macOS on Apple Silicon: `bash tools/check-toolchain.sh` printed its `ok` line (`rustc`
1.97.1); `cargo fmt --check`, `cargo clippy --locked --all-targets -- -D warnings` and
`cargo test --locked` passed, with 182 tests in the workspace; and both check scripts of
section 4 passed. No Linux run and no CI run covers this commit (section 10).

**Observed (API-02, the HTTP/1.0 transport in `console-http::transport`)**: merged on
2026-11-15 at commit `d64685f7`. From `console/`:

```sh
nice -n 10 cargo test --locked -p console-http --lib transport
nice -n 10 cargo test --locked -p console-http --test api02_donor
nice -n 10 cargo test --locked -p console-http --test api02_transport
```

In the package clone before the merge, 29 unit tests, 8 donor tests and 21 transport tests
passed, and the `console-http` suite passed 15 runs in a row; the lead's run at
`8ea4c27a`, below, confirmed them. The transport file took about 3.5 s, because its timeout
and watcher tests wait 1 to 2 s on the real clock. These are claims about the transport
with a test handler only; no engine is involved. The request head is parsed by hand by
CPython's rules, without `httparse` (lead decision LD34 in
[tasks.md](tasks.md#reconciliations), R29). Not done: the donor rows
`RequestBodies::test_a_chunked_body` and `RequestBodies::test_a_malformed_body_is_a_400`
need the router, validation and the chat route (API-03, API-04, API-08), and only their
transport parts are tested; API-08 wires the three environment settings into the
transport; the `HEAD` support of P-11 needs a transport extension (WEB-02); and Python's
error page for a refused request head when `cors_origins` is set is proposal P-22,
awaiting the owner's decision
([deviation register](contracts/deviations.md#deferred-awaiting-owner-decision)).

**Observed (API-04, request validation and sampling in `console-core::request` and
`console-core::sampling`)**: merged on 2026-11-15 at commit `89d40258`. From `console/`:

```sh
nice -n 10 cargo test --locked -p console-core --test api04_request --test api04_sampling
nice -n 10 cargo test --locked -p console-core --lib request::
```

In the package clone before the merge, the 33 integration tests (17 in `api04_request`, 16
in `api04_sampling`) and the 15 unit tests the second command selects (13 in
`console-core::request` and 2 in `console-core::engine::request`, whose path the filter
also matches) passed offline in under a second, with no sockets or clocks; the two
integration binaries passed 50 runs in a loop. The tests pin every validation message with
the input that triggers it, CPython's `float()` and `int()` whitespace rules (U+001C to
U+001F are not stripped), the SEC-6 underscore stripping (also enforced in
`effective_sampling`), the POL-1 `ablate` refusal, the start-up notes carried with a config
refusal, and a 48-row precedence matrix (the request, then the shared defaults, then the
run-config block, or the model's defaults when the config has no block). The Unicode
tables were recorded from CPython 3.14.7 with `python3 -I` and the standard library only;
no donor code was run. Not done: the joint test of the SamplingKeys expectations through
the engine encoder needs ENG-03 (M3), and the HTTP halves of the SharedSettings rows
belong to API-13 and API-08.

**Observed (API-15, the run-config store and environment settings in
`console-core::config`)**: merged on 2026-11-15 at commit `9671312a`. From `console/`:

```sh
nice -n 10 cargo test --locked -p console-core config::
nice -n 10 cargo test --locked -p console-core \
  --test api15_store --test api15_settings --test api15_naming --test api15_donor
```

In the package clone before the merge, 37 unit tests and 37 integration tests (14 in
`api15_store`, 12 in `api15_settings`, 4 in `api15_naming`, 7 in `api15_donor`) passed,
and each of these test sets passed 50 runs in a loop. `api15_naming` reads
`contracts/naming.md` and fails when its section 3.1 or 3.2 and `EnvSettings` disagree.
`api15_store` shows that an untouched run config is rewritten byte for byte as Python's
`json.dumps(obj, indent=1)` writes it (on five CPython-recorded documents), that a 0600
config and its `.prev` stay 0600 across saves (Unix), and that concurrent writers never
leave a partial config. Not done: five of its seven donor rows need the model routes of M7
or the listener, and only their run-config parts are tested; the typed accessors it did
not build go to ENG-15 and the OPS packages of M7; and five differences in the store are
proposal P-23, awaiting the owner's decision.

**Observed (ENG-02, the scripted engine and the test engines in `console-engine::fake`)**:
merged on 2026-11-15 at commit `c86cf84f`. From `console/`:

```sh
nice -n 10 cargo test --locked -p console-engine fake
```

In the package clone before the merge, 52 unit tests and 9 integration tests (module
`fake` of `tests/eng02_seam.rs`) passed offline, and the same filter passed 20 runs in a
row. The scripted engine and every test engine built on it report synthetic provenance,
except the test-only `NotSyntheticEngine`, which the guard refuses. Qualified on synthetic
backends only. Not done: none of its 21 listed donor rows is re-expressed yet (they need
ENG-10, API-07, API-08 or the line-protocol client of M3), and two timing differences on
a context reload are left to ENG-12.

**Observed (ENG-09, the engine FIFO in `console-core::fifo`)**: merged on 2026-11-15 at
commit `5880f298`. From `console/`:

```sh
nice -n 10 cargo test --locked -p console-core --lib fifo
nice -n 10 cargo test --locked -p console-core \
  --test eng09_fair_lock --test eng09_queue --test eng09_stress
```

In the package clone before the merge, 20 unit tests, 10 translated donor tests, 15 queue,
log and watchdog tests and 4 stress tests passed, offline on tokio's paused time, in under
a second, and 50 of 50 runs in a loop passed. Each stress run makes 1,000 random
operations and keeps its own tally of the places the tasks really hold. Without capacity
changes, the places held never exceed the capacity and always equal the FIFO's count, and
no over-release line is logged. Every run ends with no place held or in use, nobody in
line and no yield claim outstanding. With capacity changes, the run reports moments where
more places are held than the capacity: an exclusive release is worked out against the
capacity at release time, as the donor does, which the lead kept (LD36). Not done: the
GoneClients and QueuedKeepAlives rows need the HTTP layer (API-07 on API-02's transport,
with ENG-10); API-07 resolved the GoneClients row in wave 4 (below).

**Observed (PRM-04, the byte-level BPE tokenizer in `console-tokenizer`)**: merged on
2026-11-15 at commit `7b58580f`. From `console/`:

```sh
nice -n 10 cargo test --locked -p console-tokenizer
```

In the package clone before the merge, 55 unit tests and 57 integration tests
(`tests/prm04_*.rs`) passed in about 25 s in a debug build, about 17 s of it in the
2,000,000-character whitespace round trip; one test is ignored. The donor ports are
`--test prm04_tokenizer_glm` (11 tests, from `tools/test_tokenizer_glm.py`) and
`--test prm04_detok` (the 3 tests of `serve/test_detok.py` and 3 more).
`--test prm04_roundtrip` checks decode(encode(s)) over the donor's boundary corpus for
qwen35, glm4, glm5, deepseek3 and minimax (minimax round-trips to NFC), and the
2,000,000-character whitespace runs. The vocabularies are synthetic, trained in code; no
Python oracle was run. The Unicode-table differences it pins are listed in
[research.md](research.md), Decision 5. Optional real-pack check:

```sh
PULSAR_CONSOLE_PACK_TOKENIZER=<pack>/tokenizer \
  nice -n 10 cargo test --locked -p console-tokenizer --test prm04_roundtrip -- --ignored
```

Without the variable the test is reported ignored, and round trips on real vocabularies
are unverified. Not done: end-to-end id parity against the donor (PRM-08); and its
refusals of malformed pack inputs and its size limits are proposal P-24, awaiting the
owner's decision.

**Observed (lead's gate run after wave 2 of M1)**: on 2026-11-15 at commit `8ea4c27a`, on
macOS on Apple Silicon: `bash tools/check-toolchain.sh` printed its `ok` line (`rustc`
1.97.1); `cargo fmt --check` and `cargo clippy --locked --all-targets -- -D warnings`
passed; `cargo test --locked` gave 668 passed, 0 failed and 1 ignored, the ignored test
being `console-tokenizer` `prm04_roundtrip::real_pack_round_trip`, which needs a real
pack's tokenizer directory named by `PULSAR_CONSOLE_PACK_TOKENIZER` and reports unverified
without it; and both check scripts of section 4 passed. The parity ledger at this commit
has 27 of 913 rows resolved (26 `rust-test`, 1 `deviation`: API-02 4, API-04 8, API-15 2,
ENG-09 10, PRM-04 3) and 886 `pending`. No Linux run and no CI run covers this commit
(section 10).

**Observed (ENG-10, the engine turn driver in `console-core::turn`)**: merged on
2026-11-15 at commit `4e7c438a`. From `console/`:

```sh
nice -n 10 cargo test --locked -p console-core --lib turn::
nice -n 10 cargo test --locked -p console-core \
  --test eng10_donor --test eng10_turn --test eng10_admission
```

The first command runs the 17 unit tests of `console_core::turn`; the second runs 6
translated donor methods, 28 driver tests and 9 admission tests, all on tokio's paused
clock with ENG-02's synthetic engines. In the package clone before the merge, with `rustc`
1.97.1, all passed, and the three integration targets passed 50 runs out of 50 in a loop;
the lead's run at `6faf815b`, below, confirmed them. A recording fake shows that a dropped
consumer still gives the engine's stop, then the drain, then the release of the place. The
admission tests show an engine that is not synthetic refused at first start, restart,
context reload, model switch and the start after an idle unload or a death, each reached
through the context rule as a request is; the refused engine is shut down and never
generates. Qualified on synthetic backends only. Not done: 29 of its 35 donor rows need
the HTTP layer (API-07, API-08), the line-protocol client (ENG-04, ENG-05, ENG-06) or the
continuations (ENG-11), and only their driver halves are tested; the driver runs one
engine call at a time, so several generations at once on an engine with several places
are left to ENG-07; the continuations of fair slices, the thinking budget and the loop
guard are ENG-11's, over the driver's `ContinuationPolicy` hook; and the wrap, shutdown
and idle-unload timing are ENG-12's.

**Observed (lead's gate run after wave 3 of M1)**: on 2026-11-15 at commit `6faf815b`, on
macOS on Apple Silicon: `bash tools/check-toolchain.sh` printed its `ok` line (`rustc`
1.97.1); `cargo fmt --check` and `cargo clippy --locked --all-targets -- -D warnings`
passed; `cargo test --locked` gave 909 passed, 0 failed and 1 ignored, the ignored test
being the real-pack tokenizer round trip, which reports unverified without a pack; and
both check scripts of section 4 passed. The parity ledger at this commit has 37 of 913
rows resolved (35 `rust-test`, 2 `deviation`; wave 3 added API-03 4 and ENG-10 6) and 876
`pending`. No Linux run and no CI run covers this commit (section 10).

**Observed (API-07, the inference request lifecycle driver in `console-http::inference`)**:
merged on 2026-11-15 at commit `f6c42bb4`. From `console/`:

```sh
nice -n 10 cargo test --locked -p console-http --lib inference
nice -n 10 cargo test --locked -p console-http --test api07_lifecycle --test api07_errors
```

The first command runs the 15 unit tests of `console_http::inference`; the second runs 16
lifecycle tests and 7 error tests. In the package clone before the merge all passed, the
lifecycle file in about 0.3 s and the error file in about 0.01 s on macOS on Apple
Silicon, and the two integration binaries, which hold the gone-client, keep-alive and
write-failure tests, passed 50 runs in a row; the lead's run at `f5400931`, below,
confirmed them. A recording fake engine shows that a failed write gives exactly one engine
stop, then the drain, then the release of the FIFO place, with the client watcher off and
on. The error table maps every error class to its status and body before and after the
first byte: a malformed request (P-3), a token id outside the vocabulary included, answers
400 before the first byte and cuts the stream after it; the template and encoder refusals
of P-8 answer 400 through the mapping point `PromptFailure`, tested with stand-ins; the
stopping refusal answers 400 (LD42); an engine that fails to start during a request
answers 503, as contracts/backend-seam.md section 10 says, where the donor answers
nothing (no approved deviation covers this difference yet; the lead registers it as a
proposal for the owner with wave 5); and an error the donor's handler does not catch
closes the connection with nothing written. These tests use a probe dialect in place of API-08, API-09 and the
Responses dialect, and ENG-02's synthetic engines; nothing here is qualified beyond
synthetic backends, and no route serves a client dialect yet. Not done: five of its seven
donor rows stay `pending` (LD37): the two EngineDeath rows, QueuedKeepAlives and the
MaxTokens debug-line row wait for API-08 and API-09, and the Dashboard 503-while-reloading
row for ENG-12; the seams to ENG-12, OPS-22, RSP-16, PRM-11 and PRM-12 keep their M1
defaults; the turn trace marks only what the handler sees, so the donor's `http` and
`body` marks wait for a change in API-08; and the line written after the first byte goes
to standard error, where the tests cannot capture it.

**Observed (lead's gate run after wave 4 of M1)**: on 2026-11-15 at commit `f5400931`, on
macOS on Apple Silicon: `bash tools/check-toolchain.sh` printed its `ok` line (`rustc`
1.97.1); `cargo fmt --check` and `cargo clippy --locked --all-targets -- -D warnings`
passed; `cargo test --locked` gave 1,113 passed, 0 failed and 1 ignored, the ignored test
being the real-pack tokenizer round trip, which reports unverified without a pack; and
both check scripts of section 4 passed. The parity ledger at this commit has 39 of 913
rows resolved (37 `rust-test`, 2 `deviation`; wave 4 added API-07 2) and 874 `pending`.
Of the pending rows, 259 name the package that owns them (API-19's assignment for the
API-reader files) and the other 615 have no owner recorded yet. No Linux run and no CI run
covers this commit (section 10).

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
`data: [DONE]`) and that the server reports a synthetic engine with the default model name
`pulsar-console-synthetic`.

Planned (ENG-01, ENG-10 and API-08): the server refuses to start an engine that does not
report synthetic provenance, and `pulsar-console` exits with a non-zero status after one
line on standard error that names the engine kind, what it reported, and the note
[ALLOWING_NON_SYNTHETIC_ENGINES.md](../../docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md).

**Available from**: API-08 with API-07, ENG-02 and ENG-10 (M1); the documented CLI from
API-17 (M4). Not yet available.

**Observed (API-19, the HTTP test kit in `console-testkit`)**: merged on 2026-11-15 at
commit `b1f4709a`. Until API-08's binary exists, tests start an in-process server from the
kit: `TestServer::builder()` binds 127.0.0.1 port 0 over the API-02 transport and the
API-03 router, and can run the scripted engine behind the ENG-10 turn driver, which
applies the synthetic-only guard. A router given to the builder keeps its own guards, and
separate guard settings given with it are refused at start. From `console/`:

```sh
nice -n 10 cargo test --locked -p console-testkit
nice -n 10 cargo test --locked -p console-http --tests
```

The first command runs the kit's 32 unit tests and 29 integration tests (`api19_server`,
`api19_raw`, `api19_process`, `api19_ledger`); the second runs the integration tests of
`console-http`, those of API-02 and API-03 among them, which now use the kit with no
assertion changed. In the package clone before the merge all passed, and a 30-run loop of
the kit's and `console-http`'s tests passed 30 of 30; in one of 13 earlier whole-workspace
runs a summary reported one failed test whose name was not captured, and it did not
recur. The lead's run at `f5400931` (section 3) confirmed them. `api19_ledger` checks
`console/parity/ledger.json`: 913 rows, a valid structure, every named Rust test present
as a test function in the source file its path names, and 244 rows in the eight
API-reader files. The package resolves no donor row; it assigned the owning package of the
pending rows of those files (section 3). Qualified on synthetic backends only. Not done:
the process helper is proven against shell-script stand-ins only, until the binary of
API-08 and the fake engine binaries of M3 exist, and the flags it passes wait for API-08
and API-17; the chat-template fixture is M2's; the ledger checks are a source-level
approximation that ignores `cfg` and `ignore` attributes, and the exact listing comparison
waits for CNF-12; and the kit's own tests run on the real clock, not paused time.

An Anthropic message:

```sh
curl -N http://127.0.0.1:<port>/v1/messages \
  -H 'Content-Type: application/json' \
  -d '{"max_tokens":64,"messages":[{"role":"user","content":"hello"}],"stream":true}'
```

**Available from**: API-09 (M2). Not yet available.

Security posture checks by hand (SEC-1): a POST with a foreign `Origin` header, or with a
non-JSON content type, is refused; a request whose `Host` is not a loopback name or a name
listed in the run-config key `allowed_hosts` is refused with 403 when bound to loopback
(SEC-1.1).

**Available from**: API-03 (M1) as a library; by hand once API-08 wires the router and
`allowed_hosts` into `pulsar-console`. Not yet available by hand.

**Observed (API-03, the router and guards in `console-http::router` and
`console-http::guard`)**: merged on 2026-11-15 at commit `60fa1461`. From `console/`:

```sh
nice -n 10 cargo test --locked -p console-http \
  --test api03_dispatch --test api03_donor --test api03_security
nice -n 10 cargo test --locked -p console-http --lib -- router:: guard::
nice -n 10 cargo test --locked -p console-core --lib digest::
```

The first command runs 29 integration tests (5 in `api03_dispatch`, 14 in `api03_donor`,
10 in `api03_security`); the second the unit tests of the router and the guards; the third
the SHA-256 helper's tests against known vectors. In the package clone before the merge
all passed, and the three integration files and the router unit tests passed 50 runs in a
loop; the lead's run at `6faf815b` (section 3) confirmed them. Observed: every donor route
answers its expected status without a key and with a key, and with no `Origin`, the
server's own page, a foreign page and `Origin: null`, with a probe handler in place of the
handlers of later packages; a foreign or null `Origin` gets 403 on GET and DELETE, and
on POST once the key check passes; a POST without `application/json`, other than to
`/attach` and `/pdf`, gets 415 `{"error": {"message": "send application/json"}}` (lead
decision LD39); on a loopback bind a `Host` other than `localhost`, `127.0.0.1` or `[::1]`
(any port), or a name listed in `allowed_hosts`, gets 403 `permission_error` before
routing. The
transport's own 431 pages are answered before the `Host` check. At this merge so were its
501 page for an unserved method and its P-2 400 page; the follow-up to API-03 at
`50179f0d`, below, closed that gap. These are claims about the router with test handlers,
on synthetic inputs only. By hand, once the
binary exists:

```sh
curl -i -H 'Host: attacker.invalid' http://127.0.0.1:<port>/health     # 403
curl -i -H 'Origin: null' http://127.0.0.1:<port>/health               # 403
curl -i -X POST -H 'Content-Type: text/plain' -d '{}' \
  http://127.0.0.1:<port>/v1/chat/completions                          # 415
```

Not done: ten of its donor rows need the handlers of later packages (API-06, API-07,
API-08, API-09, API-11, API-12, API-13), and only their router halves are tested; the
`Host` matching details (LD43) and the reading of `allowed_hosts` on a loopback bind
(LD30) await the owner's confirmation at checkpoint 2; and API-08 wires the guard at
start, including the refusal to start on an `allowed_hosts` entry that cannot be parsed
(LD40).

**Observed (the follow-up to API-03: the `Host` check before the transport's own
pages)**: merged on 2026-11-15 at commit `50179f0d`. From `console/`:

```sh
nice -n 10 cargo test --locked -p console-http --test api03f_early_host
nice -n 10 cargo test --locked -p console-http --lib -- router::tests::the_early_refusal
```

The transport's `Handler` trait has a new hook, `early_refusal`, whose default refuses
nothing; the transport calls it once per parsed request head, before its 501 page for an
unserved method and its P-2 400 page, and the router implements it with the `Host`
allowlist only. The first command runs 11 tests on loopback sockets; the second the unit
test that the hook gives the router's own `Host` refusal. In the package clone before the
merge all passed, the integration file passed 50 runs in a loop, and no API-02 or API-03
test was changed; the lead's run at `f5400931` (section 3) confirmed them. Observed: a
refused `Host` with an unserved method, with `HEAD` (the 403 head, no body) or with
conflicting framing gets 403 `permission_error`, byte for byte the router's 403 on a route
apart from `Date`, with no CORS header; an allowed `Host` still gets the 501 and the P-2
400; a handler without the hook behaves as before; the hook runs once per request, and a
panic in it closes only its connection. The 431 pages, and the 400, 414 and 505 pages of
the request line, have no usable headers and are still answered without the check.
Qualified on synthetic inputs only.

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
CNF-09 (M10). The comparator exists as a library since CNF-04 (below); the checker and the
replay are not yet available.

The conformance runner `cnf` exists as a skeleton (CNF-01, merged on 2026-11-14 at commit
`fb87f8a2`). From `console/`:

```sh
cargo run --locked -p console-conformance --bin cnf -- help
```

It lists the planned subcommands: `record`, `diff`, `matrix` and `freshness` from CNF-09,
and `ledger-check` from CNF-12. Until its package lands, each exits with status 3 and
prints `cnf: NOT_BUILT: ...`. Usage errors exit with status 2 and print `cnf: USAGE: ...`;
more than 256 arguments are refused with `cnf: USAGE: more than 256 arguments given`.
Observed on 2026-11-14 in the package clone before the merge; the 11 unit tests of
`src/bin/cnf.rs` and the 7 tests of `tests/cnf01_cli.rs`, which run the built binary,
passed again in the lead's run at `fb87f8a2` (section 3). None of the planned subcommands
is built.

**Observed (CNF-02, the scenario format in `console-conformance::scenario`)**: merged on
2026-11-15 at commit `8dc26783`. From `console/`:

```sh
nice -n 10 cargo test --locked -p console-conformance scenario::
nice -n 10 cargo test --locked -p console-conformance \
  --test cnf02_samples --test cnf02_contracts
```

In the package clone before the merge, the 70 unit tests of the loader, the 7 sample tests
and the 9 contract tests passed offline in well under a second, and the crate's tests
passed 50 runs in a loop. They load the eleven sample scenarios in
`console/crates/console-conformance/tests/data/scenarios/` and check
`contracts/conformance-scenario.schema.json` against the loader table,
`contracts/rename-map.json` against `contracts/naming.md` and `contracts/deviations.md`,
and `contracts/volatile-fields.json` against `contracts/parity-ledger.md` section 1.1.
Nothing runs a server or a scenario: the client, comparator, process harness and runner
arrive with CNF-03, CNF-04, CNF-07 and CNF-09. The `cnf` binary does not expose the
loader.

**Observed (CNF-03, the raw HTTP client and observation recorder in
`console-conformance::client` and `::observe`)**: merged on 2026-11-15 at commit
`21f5be60`. It is a library; no `cnf` subcommand uses it yet. From `console/`:

```sh
nice -n 10 cargo test --locked -p console-conformance --test cnf03_client
nice -n 10 cargo test --locked -p console-conformance --lib -- client:: observe::
```

The first command runs 19 self-tests, each against a `std::net` server the test starts on
127.0.0.1 port 0. The server writes the same logical answer with `Content-Length`, chunked
and close-delimited framing, and the tests check that the logical observations are
identical. The tests also cover HTTP/1.0 requests sent byte for byte, raw malformed
requests, answers with no head and heads the parser rejects, which are read to the end of
the connection and recorded the same whatever the server's write sizes, and disconnects
after N events, after N bytes and right after the request, as a close or a half-close. In
the disconnect tests the server waits for the client to go away, so they cannot pass by
timing. The second command runs 52 unit tests: the SSE and NDJSON parsers, the chunked
decoder, the `json.dumps`-compatible body writer, the read limits, the request write that
stops at the exchange deadline, durations up to `Duration::MAX`, and file reads that
refuse symbolic links and named pipes. In the package clone before the merge all passed,
and the integration file passed 30 of 30 runs in a row; the lead's run at `6faf815b`
(section 3) confirmed them. Qualified on synthetic inputs only. Not done: the client has
not been run against the console's own transport or a binary; a scenario cannot yet say
that a step half-closes or disconnects right after its request (a request to CNF-09); and
an answer whose only bytes are a prefix of `HTTP/` is still recorded as truncated with no
body.

**Observed (CNF-07, the process harness in `console-conformance::process`)**: merged on
2026-11-15 at commit `d270f113`. From `console/`:

```sh
nice -n 10 cargo test --locked -p console-conformance --test cnf07_process
nice -n 10 cargo test --locked -p console-conformance --test cnf07_scenario_files
nice -n 10 cargo test --locked -p console-conformance --lib -- process::
```

The first command runs the 27 process-harness self-tests against the test-only child
`cnf_child` (loopback, port 0; each test holds the lifecycle lock; about 4 s on a macOS
host); the second checks the generated tokenizer directory and run config (7 tests, no
process); the third the 23 unit tests of the module. Set
`PULSAR_CONSOLE_TEST_TIME_SCALE=3` on a slow runner: every harness deadline (ready line
20 s, grace 10 s, kill 10 s, the 500 ms exit wait after standard output closes, and the
tests' short 300 ms deadlines) is multiplied by it; a non-numeric or out-of-range value
fails the run instead of being ignored. A failed start keeps its run directory (the error
names it), and so does a drop that finds a stop that was not clean; CI should collect the
kept directories' `stdout.txt` and `stderr.txt` as artifacts. In the package clone before
the merge, on macOS (Darwin): 27 of 27 process tests passed, repeated runs passed, and no
process or run directory was left afterwards; the lead's run at `6faf815b` (section 3)
confirmed them. The leak check is proven with a child that forks a grandchild, inside and
outside its process group. The ready line and the harness are specified in
[contracts/cli.md](contracts/cli.md) (draft). Not done: the Linux paths (the `/proc`
walk, `waitid` with `WNOWAIT`, process groups) are unverified until a CI run; no
`pulsar-console` binary exists yet, so the harness has started only `cnf_child`; and
that the server's ready line names the bound port under `--port 0` is proposal P-25,
awaiting the owner's decision
([deviation register](contracts/deviations.md#deferred-awaiting-owner-decision)).

**Observed (CNF-04, the normalizer and comparator in `console-conformance::normalize` and
`::compare`)**: merged on 2026-11-15 at commit `7259f941`. It is a library; no `cnf`
subcommand uses it yet. From `console/`:

```sh
nice -n 10 cargo test --locked -p console-conformance \
  --test cnf04_negative --test cnf04_contracts
nice -n 10 cargo test --locked -p console-conformance --lib -- normalize:: compare::
```

The first command runs the 65 negative self-tests and contract checks; the second the 28
unit tests. None is timing-sensitive. In the package clone before the merge all passed,
and the two integration files passed 50 runs in a loop; the lead's run at `f5400931`
(section 3) confirmed them. Each one-field mutation of a candidate gives a difference at
the expected JSON pointer: status, reason phrase, header name and its case, header value
and order, a missing or an extra header, a `Date` not in IMF-fixdate form or outside the
run, JSON key order, white space and escapes, an event, an id cross-reference, a client id
replaced by a fresh one, a tape entry, a file field, a log line or its token count, wire
bytes after a half-close, and the exit status. Header names, their case and positions and
JSON key order are differences, as contracts/parity-ledger.md section 1.1 says; only the
values `contracts/volatile-fields.json` lists (71 fields, each with a donor citation) are
replaced, and decided and mechanical renames are applied to the reference side only. A
difference is suppressed only by an annotation that cites an approved deviation. A
donor-shaped reference and a candidate that differ only in listed volatile values and
decided names compare clean apart from `Content-Length`: under the shipped list, each
`Content-Length`-framed answer whose body changes length under normalization differs in
that header, its raw head and its framing length. Lead decision LD44 makes the header's
value derived; a follow-up to CNF-04 builds it in wave 5. Use:
`Normalizer::new(&load_volatile_fields(..)?, load_rename_map(..)?)`, then
`compare_documents(..)` with the annotations and `ApprovedIds::from_register(..)` read
from contracts/deviations.md, then `Report::passed()`; a reference stored in normalized
form is replayed with `compare(&Normalized::stored(doc), ..)`. Qualified on synthetic
inputs only. Not done: nothing runs a scenario end to end yet (CNF-08, CNF-09); a stored
reference is not yet checked as a fixed point of normalization, and an annotation does
not yet name the kind of difference it covers (both with LD44's follow-up); the engine
tape is compared exactly until a location kind for it arrives with the vision packages of
M6; and how hardware and machine readings are compared is open item OPEN-61.

## 10. CI jobs

`.github/workflows/console.yml` is path-filtered to console paths. Its blocking jobs each
name the local command that reproduces them: preflight (the two check scripts of
section 4 and, since CNF-01, a check of the toolchain pin), Rust on Linux (toolchain assertion, `cargo fetch`, `fmt`, `clippy`, `test`),
Rust on macOS arm64 (toolchain and architecture assertion, `cargo fetch`, `test`), and a
summary job. The blocking web logic job that binding decision B12 in
[tasks.md](tasks.md#binding-cross-cutting-decisions) requires is not in the M0 workflow
file. The two donor test files run through the shim and the vendor-template renders run
only in the manual reference job; blocking CI checks their committed records.

**Available from**: GOV-06 (M0) for the workflow and its blocking jobs; CNF-01 (M1)
extends it; CNF-15 (M8) for the web logic job. The owner authorized the first push of the
feature branch on 2026-11-14; each later push remains a checkpoint decision.

**Observed (first CI runs)**: the first push, on 2026-11-14 at commit `0f4bc320` (the M0
skeleton and the M1 scaffold), ran two workflows, and both succeeded: `console` (run
43674353677: preflight, Rust on ubuntu-24.04, Rust on macos-15 arm64, summary) and the
repository's own "macOS baseline" workflow (run 43674353647: classify, Apple MLX
small-fixture validation, Apple Silicon workspace baseline, aggregate status). Nothing has
been pushed since, so no CI run covers API-01, ENG-01 or CNF-01, and CNF-01's revision of
`console.yml`, described below, has not run. As of 2026-11-15 (commit `8ea4c27a`) nothing
has been pushed since `0f4bc320` either: no CI run covers the seven packages of wave 2, and
the Linux behavior of the M1 code is unobserved. The same holds at commit `6faf815b`
(2026-11-15): no CI run covers the four packages of wave 3, and the Linux behavior of the
M1 code, CNF-07's process harness included, is unobserved. The same holds at commit
`f5400931` (2026-11-15) for the four packages of wave 4.

CNF-01 (M1, merged on 2026-11-14 at commit `fb87f8a2`) revises the workflow. preflight,
rust-linux and rust-macos run from `console/`. Every failing step prints one
`console failure class: <CLASS>` line and one `::error` annotation for each failed class,
then once the detail, the local command that reproduces it, and the job, runner image and
toolchain. The classes are listed in the header of `.github/workflows/console.yml`.
`BOUNDARY_` and `HYGIENE_` classes come only from unindented `FAIL <check>` report lines
whose check name is lower-case kebab; the indented path lines under them never add a
class. Preflight and both Rust jobs share one pin check (`console_check_pin`): it reads the
first channel line of `console/rust-toolchain.toml` the way
`console/tools/check-toolchain.sh` does and requires an exact X.Y.Z equal to the
workflow's `CONSOLE_RUST_TOOLCHAIN`. Preflight and the summary run no cargo command, so
they install no toolchain and do not assert `rustc -V` (lead decision LD33). The Rust jobs
wait for preflight, install the pinned toolchain, assert `rustc -V` and `cargo -V`, and
run a dry-run self-test showing that a `rustc -V` mismatch fails both the CI assertion and
`console/tools/check-toolchain.sh`. Each runs `cargo fetch --locked` once; then the Linux
job runs `cargo fmt --check`, `cargo clippy --frozen --all-targets -- -D warnings` and
`cargo test --frozen`, and the macOS job asserts arm64 and runs `cargo test --frozen`. The
17 tests of `console/crates/console-conformance/tests/cnf01_workflow.rs` check the
workflow file as text.

**Observed (CNF-01, without CI)**: on 2026-11-14, before the merge, each step's own script,
taken from the workflow, was run in a scratch copy of the package's work outside the
repository. Preflight passed. A file outside the allowlist failed with
`BOUNDARY_ALLOWLIST`, and files named like `FAIL x::...` added no class of their own; a
`console/x.log` failed with `BOUNDARY_IGNORED_FILES`. These two cases ran in working-tree
mode; the `--committed` form CI uses was not rerun after CNF-01's last revision. A
`rustc -V` mismatch failed with `TOOLCHAIN_MISMATCH`, and the cargo steps passed. The
`rustup` install step did not run, because that host has no `rustup`, and the runner image
fields printed `unknown`. CNF-01 stays unticked until a green CI run of its revision is
observed.

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
