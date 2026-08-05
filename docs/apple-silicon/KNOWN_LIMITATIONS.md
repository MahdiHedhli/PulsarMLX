# Known limitations

Observed on 2026-08-05 at upstream-derived revision `12c2406`, before MLX
backend implementation. This list separates demonstrated limits from planned
work. See the exact host snapshot in
[../preflight/ENVIRONMENT.md](../preflight/ENVIRONMENT.md), validation output
in [../preflight/BASELINE_VALIDATION.md](../preflight/BASELINE_VALIDATION.md),
and the source audit in
[UPSTREAM_ARCHITECTURE.md](UPSTREAM_ARCHITECTURE.md).

## Apple execution is not implemented

- No Apple Silicon or MLX inference backend exists in the inspected source.
  The real `engine` implementation and CUDA `kernels` wrapper are Linux-gated;
  the engine crate exposes no real implementation on macOS.
- The non-Linux CLI and server are compatibility stubs. A successful macOS
  workspace build does not provide inference or serving.
- MLX was not importable and no MLX distribution metadata was present in the
  active Python 3.14 environment. No MLX device, tensor operation, model load,
  or inference was executed.
- No real-model fixture is present in the repository. Synthetic validation,
  when added, will not establish checkpoint compatibility.
- Mapped GGUF-to-MLX aliasing, unified-memory residency behavior, giant-model
  correctness, memory pressure, and SSD streaming performance have not been
  measured.

## Platform and test coverage

- `cargo check --workspace --all-targets` passed on native arm64 macOS, and
  `cargo test --workspace --no-fail-fast` ran 32 tests: 32 passed, 0 failed.
  These results cover only targets selected by the macOS configuration.
- Engine, kernel, and Linux-gated server test targets each ran zero tests on
  macOS. The test run does not exercise the Linux server, CUDA execution,
  `io_uring`, or `handle_chat` behavior.
- Linux/CUDA compilation and runtime behavior were not run on this Apple host.
  Multi-GPU, CUDA graphs, device caches, and GPU kernel parity are unverified.
- There is no checked-in code-coverage configuration or report.
- The inherited Linux expert fetcher depends on `io_uring`, `O_DIRECT`, Unix
  descriptors, and aligned reads. No portable or macOS expert fetch
  implementation exists yet.

## Existing source-quality debt

- `cargo fmt --all -- --check` failed with differences in 25 pre-existing
  upstream Rust files. No repository-wide formatting was performed.
- `cargo clippy --workspace --all-targets -- -D warnings` failed with exit
  status 101 at `crates/kernels/build.rs:41` on
  `clippy::needless_borrows_for_generic_args`.
- Workspace checking emitted an inherited `unused_mut` warning in
  `crates/quant/src/iq.rs` and 13 dead-code warnings from Linux-oriented serve
  helpers compiled on macOS.
- `Cargo.lock` was ignored and untracked in the inspected checkout. The
  PulsarMLX bootstrap removes that ignore rule and includes the resolved lock
  file for the baseline commit; this is a repository-hygiene change, not an
  upstream runtime claim.

These findings are recorded as upstream debt. They are not current CI gates
and should not be swept into an unrelated Apple backend change.

## Host and tooling constraints

- The filesystem had 210 GiB available and was 89% full at inspection time.
  That headroom can be insufficient for giant checkpoints plus conversions,
  caches, and benchmark output; it must be rechecked before acquiring data.
- No Python virtual environment was active, and MLX was absent from the active
  interpreter.
- Ninja and `rustup` were not installed. Rust 1.97.1 and Cargo 1.97.1 came
  from Homebrew. The revised workflow selects GitHub's `macos-15` OS and arm64
  runner label but does not pin its Rust toolchain contents, so local and CI
  compiler revisions can still differ.
- The standalone Xcode Command Line Tools were selected and functional, but
  full Xcode was not selected. `xcodebuild -version` therefore exited with an
  active-developer-directory error.

These missing tools are facts from the pre-installation snapshot, not a claim
that every one is required by the eventual MLX integration.

## CI and repository publication status

- The public independent repository is published at
  <https://github.com/MahdiHedhli/PulsarMLX>. GitHub reports `isFork: false`,
  visibility `PUBLIC`, and default branch `main`. Local `main` tracks
  `origin/main`; the original Pulsar remote remains `upstream`.
- [Push-triggered GitHub Actions run 30977591362](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/30977591362)
  completed successfully for commit `733dce5`. Its job reported image
  `macos-15-arm64` release `20260727.0256`, `arm64`, macOS 15.7.7 build 24G720,
  rustc 1.97.1, Cargo 1.97.1, and host `aarch64-apple-darwin`.
- The remote run passed `cargo check --workspace --all-targets` and
  `cargo test --workspace --no-fail-fast`; 32 tests ran. It reproduced the
  inherited `quant` warning and macOS serve dead-code warnings.
- Standard `macos-15` is an Apple Silicon runner but is not equivalent to the
  local 128 GiB M1 Ultra. This job validates only the Cargo baseline. It does
  not install MLX, run an MLX device fixture, download a checkpoint, exercise
  Linux/CUDA, or establish model correctness or performance.

## Deliberately unsupported in the first milestone

The initial bring-up does not promise production serving, MCP, every model
family or quantization format, Qwen3.5/3.6 recurrent GDN support, speculative
decoding, long-context performance, custom Metal kernels, or giant-model
performance. These are exclusions in the proposed design, not implemented
features. The staged scope and stop conditions are in
[BACKEND_DESIGN.md](BACKEND_DESIGN.md).
