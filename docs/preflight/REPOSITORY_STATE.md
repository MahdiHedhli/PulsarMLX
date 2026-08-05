# Repository-state preflight

Captured on 2026-08-05 before the documentation/bootstrap edits in this
session. The initial audit was read-only. Existing work was preserved: no
reset, clean, stash, checkout, rebase, history rewrite, or file deletion was
performed.

## Inspection snapshot

| Item | Observed state |
| --- | --- |
| Working directory | `/Users/mhedhli/Documents/Coding/PulsarMLX` |
| Branch | `main` |
| HEAD | `12c2406` (`build: establish macOS workspace baseline`) |
| Tracked upstream | `origin/main` at `183a54b` |
| Divergence | Local `main` was 2 commits ahead and 0 behind |
| Worktree | Clean: no staged, modified, deleted, or standard untracked files |
| Remote at inspection | Only `origin`, with fetch and push URL `https://github.com/giannisanni/pulsar.git` |
| Tags / submodules | No local tags and no configured submodules |

The original upstream commit graph is intact and `183a54b` is an ancestor of
the two local commits. This is a derived checkout, not a source-code copy with
history removed.

Ignored local content was also inventoried:

- `Cargo.lock`: about 40 KiB, ignored by `.gitignore:2` and not tracked.
- `target/`: about 936 MiB of build/test artifacts, ignored by `.gitignore:1`.

Neither ignored item was deleted or added to Git. There were no other standard
untracked files at inspection time.

## Repository bootstrap outcome

After the read-only audit, the authorized repository setup established this
topology:

| Remote | URL | Purpose |
| --- | --- | --- |
| `origin` | `https://github.com/MahdiHedhli/PulsarMLX.git` | New independent PulsarMLX repository |
| `upstream` | `https://github.com/giannisanni/pulsar.git` | Original Pulsar source and future upstream synchronization |

The active GitHub account created `MahdiHedhli/PulsarMLX` as a public,
independent repository; GitHub reports `isFork: false`. Successful creation and
the subsequent metadata update demonstrated repository-creation permission for
the authenticated account. The public description is:

> Experimental Apple Silicon and MLX runtime for oversized Mixture-of-Experts
> models, derived from Pulsar.

The old `origin` was renamed to `upstream` rather than removed, so both the
upstream relationship and complete commit ancestry remain explicit.

The bootstrap also:

- changes the workspace `repository` URL to PulsarMLX;
- adds a prominent derivative-project notice and upstream link to `README.md`;
- updates the README clone command for the independent repository; and
- leaves the upstream `LICENSE` file unchanged.

## Recent history

The most recent commits at inspection were:

| Commit | Author date | Summary |
| --- | --- | --- |
| `12c2406` | 2026-08-04 | `build: establish macOS workspace baseline` |
| `a5901d5` | 2026-08-04 | `docs: map upstream architecture and Apple Silicon seams` |
| `183a54b` | 2026-08-02 | upstream `fix(dsv4): wire Dsv4 into PULSAR_KV (#23)` |
| `a7fc493` | 2026-08-02 | upstream `feat(loader): accept F32/BF16/Q8_0 pass-throughs and UD-* token_embd (#22)` |
| `131b358` | 2026-08-02 | upstream merge commit |

## Preserved prior-session work

Relative to upstream `origin/main` at inspection (now `upstream/main`), the
checkout already contained three tracked changes totaling 415 inserted lines:

| Commit | Files | Inspection and verification status |
| --- | --- | --- |
| `a5901d5` | Adds `docs/apple-silicon/UPSTREAM_ARCHITECTURE.md` (389 lines) | Preserved. `git show --check` passes. It is a static source audit, not runtime proof; its MLX, mapped-memory, giant-model, and CUDA-runtime claims remain explicitly unverified. |
| `12c2406` | Adds `.github/workflows/macos.yml`; adds one Linux cfg gate to `crates/serve/src/main.rs` | Preserved. `git show --check`, local workspace compilation, and local portable tests pass. The GitHub Actions workflow has not yet run remotely, and this Apple host cannot validate Linux/CUDA runtime behavior. |

Ignored `target/` timestamps showed that compilation/test targets had been
built after the cfg edit, but there was no durable command log proving the
previous session's result. This session therefore reran the baseline checks
instead of treating artifact timestamps as proof.

## Workspace configuration and crate structure

The root `Cargo.toml` uses resolver 2, Rust edition 2021, an MIT workspace
license, thin release LTO, and one release codegen unit. At inspection its
`repository` field still pointed to upstream Pulsar.

The workspace contains seven crates:

| Crate | Role | Current platform shape |
| --- | --- | --- |
| `gguf` | GGUF metadata, tensor table, split-shard layout | Portable |
| `stream` | Expert read plans and fetching | Plans are portable; `io_uring`/`O_DIRECT` fetchers are Linux-only |
| `kernels` | CUDA FFI and kernel build | Linux/CUDA implementation; effectively empty elsewhere |
| `tokenizer` | GGUF-backed byte-level BPE and chat markers | Portable |
| `engine` | Model loading, forward graphs, caching, and generation | Entire real implementation is Linux-gated and CUDA-coupled |
| `serve` | OpenAI-compatible HTTP server and MCP support | Linux real server plus a non-Linux stub |
| `quant` | Quantization, dequantization, and CPU dot references | Portable scalar code plus guarded x86_64 SIMD paths |

There are no backend feature flags at this baseline; operating-system cfgs
select the available implementation.

## License and upstream attribution

Attribution is present and must remain intact:

- `LICENSE` is the upstream MIT license and credits Gianni Sanrochman.
- The same license records the CUDA derivation from ds4 and ggml and retains
  their copyright notices.
- `README.md` has an MIT/license section and links the ds4 lineage.
- Affected CUDA includes retain source notices, including
  `gqa_kernels.inc`, `dsa_indexer.inc`, and `iq_extra_tables.inc`.
- `docs/apple-silicon/UPSTREAM_ARCHITECTURE.md` records the upstream URL and
  audited upstream revision.
- The full upstream Git history remains in this repository.

The bootstrap does not replace or edit `LICENSE`. Repository identity changes
must continue to distinguish PulsarMLX from, and link back to, upstream Pulsar.

## macOS conditional-compilation baseline

`crates/serve/src/main.rs` already contains the requested gate:

```rust
#[cfg(target_os = "linux")]
fn handle_chat(
```

The gate was introduced by preserved commit `12c2406` and is still necessary.
The function signature references Linux-only `engine::Model`, `engine::State`,
`engine::Result`, and `mcp::McpHub` types. The engine implementation is
declared and re-exported only under `#[cfg(target_os = "linux")]`, and the MCP
module is also Linux-gated. Without the function-level gate, the macOS compiler
would type-check the top-level signature even though its call site is in the
Linux server path.

No duplicate edit was made in this session.

## Linux, CUDA, and io_uring assumptions

The principal platform constraints found by source inspection are:

- `crates/engine/src/lib.rs` places the complete engine in a Linux-only `real`
  module and re-exports it only on Linux.
- `crates/kernels/src/lib.rs` exposes the CUDA wrapper only on Linux.
- `crates/kernels/build.rs` exits early for non-Linux targets; on Linux it
  expects `nvcc`, `cudart`, accepted host compilers, CUDA architecture flags,
  and `/usr/local/cuda/lib64`.
- `crates/stream/Cargo.toml` adds `io-uring` and `libc` only on Linux.
- `crates/stream/src/lib.rs` uses `io_uring`, `O_DIRECT`, Unix file
  descriptors, and 4096-byte aligned requests in its Linux fetchers.
- The engine reads `/proc/meminfo` for host-cache sizing.
- The server contains `/proc/meminfo` and `nvidia-smi` hardware probes.
- `scripts/bench.sh` reads `/proc/loadavg`.
- Engine and server binaries currently print Linux/CUDA-required messages on
  non-Linux systems instead of providing inference.
- `quant::cpu_dot` guards x86_64 SIMD paths and retains scalar fallbacks that
  compile and test on arm64.

The deeper architecture and backend-seam audit is in
`docs/apple-silicon/UPSTREAM_ARCHITECTURE.md`.

## Documentation inventory

Existing documentation covers the expert store, MCP server, layer-split
design, multiple model ports, benchmark/run examples, a CUDA crash fix, and
the new Apple Silicon architecture map. There were no `docs/preflight/`
reports in the inspection snapshot; this session bootstraps them.

The upstream README still described and branded the Linux/CUDA Pulsar project
and used the upstream clone URL. Minimal identity edits in this bootstrap name
the derivative PulsarMLX, link upstream prominently, and leave the upstream
technical and license content in place.

## Tests, coverage, and CI

Source inspection found 52 literal `#[test]` markers. Platform cfgs mean the
same number does not execute everywhere:

- macOS runs portable GGUF, quantization, tokenizer, and stream-plan tests.
- Linux-only engine tests are excluded on macOS.
- CUDA kernel integration/self-tests are Linux-gated; the macOS kernel crate
  has no executable CUDA tests.
- Linux-gated server tests are excluded on macOS.
- No code-coverage workflow, configuration, or stored coverage report was
  found.

`scripts/check.sh` is the more extensive CUDA-machine gate: it builds release
artifacts, serializes GPU self-tests, runs portable tests, and can perform
optional model decode/census checks when model data is available.

Upstream `origin/main` at inspection (now `upstream/main`) had no checked-in
GitHub Actions workflow. Preserved commit `12c2406` added the only workflow at
that snapshot, `.github/workflows/macos.yml`, using `macos-15`, asserting
`arm64`, and running the narrower `cargo check --workspace` and
`cargo test --workspace`. The bootstrap revision now configures the exact
required commands, `cargo check --workspace --all-targets` and
`cargo test --workspace --no-fail-fast`; remote execution remains unverified
until a GitHub Actions run completes.

## Verification performed in this session

After the read-only host and repository audits completed:

| Command | Result |
| --- | --- |
| `git show --check a5901d5` | Pass |
| `git show --check 12c2406` | Pass |
| `cargo check --workspace --all-targets` | Pass, exit 0, on native arm64 macOS |
| `cargo test --workspace --no-fail-fast` | Pass, exit 0: 32 tests passed, 0 failed |
| `cargo fmt --all -- --check` | Fail, exit 1: differences in 25 pre-existing upstream Rust files |
| `cargo clippy --workspace --all-targets -- -D warnings` | Fail, exit 101: `clippy::needless_borrows_for_generic_args` at `crates/kernels/build.rs:41` |

The successful compile emitted one existing `unused_mut` warning in `quant`
and dead-code warnings for Linux-oriented server helpers that remain compiled
beside the non-Linux stub. The tests emitted the same warning classes.

The rustfmt and Clippy checks were diagnostic only and changed no files. Their
broad or unrelated failures predate the Apple bring-up, so the source tree was
not mass-formatted or broadly lint-fixed during this baseline.

## Verified and unverified boundaries

Verified locally:

- The complete workspace compiles on this native Apple Silicon host.
- The required `handle_chat` Linux gate is present and resolves the macOS
  type-availability baseline.
- All 32 tests selected by the macOS cfg set pass.
- Both preserved local commits are free of whitespace errors reported by
  `git show --check`.

Not yet verified:

- MLX import, device selection, kernels, or inference; MLX is not installed in
  the active Python environment and no MLX backend exists yet.
- Any real or synthetic MLX model execution.
- Linux/CUDA build or runtime parity on this machine.
- CUDA and `io_uring` tests excluded by macOS cfgs.
- A remote GitHub Actions run of the new macOS workflow.
- Giant-model correctness, performance, memory-pressure behavior, or SSD
  streaming on Apple Silicon.
- Repository-wide rustfmt conformance is not achieved; formatting cleanup
  remains out of scope for this preflight.

These limits keep the baseline claim precise: it is a clean, compiling macOS
workspace foundation, not an implemented MLX inference backend.
