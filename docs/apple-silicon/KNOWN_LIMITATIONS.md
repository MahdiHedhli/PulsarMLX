# Known limitations

The original host and upstream observations were captured on 2026-08-05 at
revision `12c2406`; implementation-specific sections are updated through the
T070 evidence publication and independent replay. This list separates
demonstrated limits from planned work. See the exact host snapshot in
[../preflight/ENVIRONMENT.md](../preflight/ENVIRONMENT.md), validation output
in [../preflight/BASELINE_VALIDATION.md](../preflight/BASELINE_VALIDATION.md),
and the source audit in
[UPSTREAM_ARCHITECTURE.md](UPSTREAM_ARCHITECTURE.md).

## Verified Apple execution boundary

- PulsarMLX now has a bounded Apple worker/client and device-smoke path. On
  tested commit `4ff4301`, a native arm64 Python 3.12.13 worker using exact
  MLX 0.32.0 selected `gpu`, evaluated and synchronized a nonsymmetric float32
  matmul, and matched four independently fixed expected values exactly without
  fallback. This is a device proof, not model inference.
- The inherited real `engine` implementation and CUDA `kernels` wrapper remain
  Linux-gated; the new path is additive and does not make the inherited engine
  execute models on macOS.
- The inherited non-Linux `serve` CLI and server path remains a compatibility
  stub. The separate `pulsar-mlx` validation CLI does not provide inference
  serving, so a successful macOS workspace build does not provide serving.
- The ignored project environment contains native MLX/MLX-Metal 0.32.0; the
  device probe and seven bounded tensor fixtures executed successfully. Q8_0
  is verified for strict complete-row scalar decode/matvec, one bounded
  evaluated MLX decoded-row dot, and one named real-checkpoint expert gate
  projection prefix covering 16 output rows. Tokenization, complete tensors,
  routing, full layers, generation, and serving have not been executed.
- No real-model fixture is present in the repository. An external
  Qwen3-30B-A3B Q8_0 artifact now has verified complete size, SHA-256, and the
  exact required tensor inventory. A pinned CPU oracle and Apple MLX both
  executed the same admitted 34,816-byte prefix of one layer-0 expert-0 gate
  tensor and agreed for all 16 outputs under the frozen tolerance. That bounded
  intermediate does not establish complete-tensor, routed-layer, checkpoint,
  or giant-model compatibility. The evaluated synthetic routed-MoE fixture
  separately establishes only its committed expert bytes, routes, aggregation,
  and four-value output.
- Mapped GGUF-to-MLX aliasing, unified-memory residency behavior, giant-model
  correctness, behavior under elevated memory pressure, and SSD streaming
  performance have not been measured.

## Platform and test coverage

- At the final US5 T072 gate,
  `cargo check --workspace --all-targets` passed on native arm64 macOS, and
  `cargo test --workspace --no-fail-fast` listed 172 tests: 171 active tests
  passed, zero failed, and one native MLX integration test was explicitly
  ignored by the baseline. That test passed when run directly with `--ignored`
  against the frozen local environment. The most recent complete Python worker
  suite separately ran 44 passing tests during T060. These results cover only
  targets selected by macOS.
- Engine, kernel, and Linux-gated server test targets each ran zero tests on
  macOS. The test run does not exercise the Linux server, CUDA execution,
  `io_uring`, or `handle_chat` behavior.
- Linux/CUDA compilation and runtime behavior were not run on this Apple host.
  Multi-GPU, CUDA graphs, device caches, and GPU kernel parity are unverified.
- There is no checked-in code-coverage configuration or report.
- The inherited Linux expert fetcher depends on `io_uring`, `O_DIRECT`, Unix
  descriptors, and aligned reads. An additive portable exact positional source
  now passes its macOS reference tests, but it is not wired into or claimed as
  a replacement for the inherited Linux engine path.

## Evidence publication, replay, and performance boundary

- The backend evidence constructors now require a bounded actual-result
  summary, a known-clean full commit identity, an independent oracle, valid
  state transitions, and validated independent memory gauges when supplied.
  They reject a reported sum of overlapping memory gauges. Benchmark records
  are admitted as performance evidence only when every named correctness
  prerequisite is executed, passed, and verified.
- The compatibility validator uses six independent, non-ordered evidence
  levels: scalar fixture, evaluated MLX tensor fixture, synthetic routed-MoE,
  bounded real-model slice, giant-model execution, and production serving. A
  complete matrix needs one unique cell for every level, and a verified cell
  must link passing verified evidence for that exact level. No state is
  promoted upward or backfilled from another level.
- These Rust types validate records constructed through the backend API; they
  are not a general JSON deserializer that automatically audits every document
  in `docs/validation`. The committed
  [reviewer index](../validation/README.md) maps current JSON records, commands,
  inputs, oracles, results, warnings, and exclusions for human review. The
  index does not turn missing legacy schema fields or non-executed states into
  success.
- The independent T070 replay reran
  `cargo test -p stream --test positional_source` from a later clean commit
  with no intervening `crates/stream` change. Its 14 passed, 0 failed result
  matched the original record exactly. The
  [reproduction record](../validation/reproduction-check.json) covers only the
  additive portable positional source on macOS; it does not reproduce the MLX
  device/tensor cases, the real-checkpoint slice, the inherited Linux fetcher,
  CUDA, serving, or performance.
- The initial benchmark decision is explicitly `not_run`: no command,
  workload, timing boundary, cache/storage policy, samples, statistics, or
  performance claim exists. Passing synthetic and bounded real-checkpoint
  correctness records were noted but were not bound as benchmark
  prerequisites because no benchmark case was selected. See
  [benchmark-initial.json](../validation/benchmark-initial.json). Latency,
  throughput, speedup, bandwidth, memory-efficiency, thermal, and power claims
  remain unsupported.
- The final T072 gate passed 25 typed evidence tests, one committed-reference
  parser test, all 13 JSON syntax and cross-record/link checks, the exact
  workspace check, and the exact workspace test command. Linux/CUDA runtime,
  external-model re-execution, and benchmarking remained explicitly not run;
  their absence was not converted into a successful claim.

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
- The system Python snapshot remains separate; the implementation uses the
  ignored, lock-resolved project `.venv` and an explicit `PYTHONPATH=python`
  because this filesystem marks editable `.pth` files hidden.
- The implementation setup creates an ignored `.venv` from `uv.lock` with
  CPython 3.12.13 and native arm64 `mlx==0.32.0`/`mlx-metal==0.32.0` wheels.
  The committed US1 evidence establishes Metal availability, selected-device
  identity, evaluated GPU work, and parity only for its four-value float32
  probe. US2 separately establishes its seven committed tensor fixtures and
  scoped Q8_0 reference operations; neither record establishes model inference.
- The backend-neutral capability, tensor, comparison, compatibility, evidence,
  memory-gauge, and benchmark-admission contracts are implemented and tested.
  The compatibility surface now also enforces complete exact-level matrices
  without implication between scalar, MLX, synthetic, bounded real-model,
  giant-model, and serving states. These semantic validators do not establish
  any Apple, Linux, CUDA, model, serving, or performance runtime capability by
  themselves; capability claims require separately linked execution records.
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
- [Push-triggered GitHub Actions run 31010989312](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31010989312)
  completed successfully for commit `892fc30` on the standard arm64
  `macos-15` runner after the native MLX integration test was made explicitly
  opt-in.
- The remote run passed `cargo check --workspace --all-targets` and
  `cargo test --workspace --no-fail-fast`; 139 tests passed and one native MLX
  integration test was explicitly ignored. It reproduced the inherited
  `quant` warning and macOS serve dead-code warnings.
- Standard `macos-15` is an Apple Silicon runner but is not equivalent to the
  local 128 GiB M1 Ultra. This job validates only the Cargo baseline. It does
  not install MLX, run an MLX device fixture, download a checkpoint, exercise
  Linux/CUDA, or establish model correctness or performance.

## Deliberately unsupported in the first milestone

The initial bring-up does not promise production serving, MCP, every model
family or quantization format, Qwen3.5/3.6 recurrent GDN support, speculative
decoding, long-context performance, custom Metal kernels, or giant-model
correctness or performance. No committed result establishes Qwen tokenization,
embeddings, checkpoint routing, a complete expert, attention, a complete
transformer layer, logits, tokens, generation, full-checkpoint execution or
streaming, Linux/CUDA runtime parity, or any executed benchmark or performance
result. These are exclusions in the current design, not implemented features.
The staged scope and stop conditions are in
[BACKEND_DESIGN.md](BACKEND_DESIGN.md).
