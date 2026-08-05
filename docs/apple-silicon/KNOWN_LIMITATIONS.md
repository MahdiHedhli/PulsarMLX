# Known limitations

The original host and upstream observations were captured on 2026-08-05 at
revision `12c2406`; implementation-specific sections are updated through the
T078 final reconciliation. This list separates
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

## Feature 002 offline-router boundary

- The complete-router path is currently verified only against two committed,
  generated f32 fixtures: one `[1,2048]` row and one `[2,2048]` batch using
  generated expert-major `[128,2048]` weights. It evaluates all 128 logits and
  full-softmax probabilities, deterministic top-8 selection, selected
  probabilities, and selected-sum-normalized weights on explicit MLX GPU. This
  is model-free fixture execution, not Qwen checkpoint routing.
- A raw router response with `passed: true` establishes only that `gpu` was
  requested and selected, fallback was false, and the returned operation was
  evaluated and synchronized. It does not establish independent-oracle parity,
  checkpoint admission, genuine hidden-state provenance, repeatability, or
  timing.
- The host admission seam now rejects missing or duplicate router roles,
  aliases, identity and file mutations, wrong F32 type or quantization, wrong
  dimensions or orientation, invalid top-k, truncated/overlong/overflowing
  positional ranges, non-finite values, and failed disk/unified-memory/pressure
  admission before calling a router runner. This was exercised with bounded
  generated resources only; it is not evidence that an external GGUF router
  tensor has the assumed identity, type, shape, offset, or length.
- Worker control validation rejects malformed fields, unsupported case
  identities, committed-byte-count disagreement, explicit CPU selection, and
  fallback requests before core-runner dispatch. Direct matrix shape, dtype,
  and finiteness checks plus runtime selected-device validation occur inside
  the router runner but still stop before constructing or scheduling a router
  MLX array. These traps prove the tested boundaries, not arbitrary malformed-
  input coverage beyond the admitted protocol.
- Synthetic exact ties are deterministically ordered by probability descending
  and then expert ID ascending. A real-checkpoint exact F32 tie across ranks
  eight and nine is deliberately a `comparison_failed` stop condition; the
  synthetic policy cannot be used to waive or relabel that stop.
- Retained fixture evidence distinguishes two evaluated MLX positive cases,
  two host-contract tie cases, and seven fixture-contract negative cases. The
  negative manifest entries retain expected codes and links to focused tests;
  they are not mislabeled as seven separate MLX mutation executions. Failed or
  aborted command evidence is retained, but the retained format itself does
  not promote a checkpoint or performance claim.
- The independent [`router oracle`](../../scripts/research/router_oracle.py)
  source and orchestration contract pass their twelve
  model-free tests, including pinned-revision, two-capture, cancellation,
  scalar-f32 accumulation, injected NumPy cross-check, import-independence, and
  no-download checks. The pinned llama.cpp checkout and helper have not been
  built or run against the live checkpoint, so no `ffn_norm-0` capture or real
  oracle result exists.
- No Feature 002 command resolved, statted, hashed, opened, or executed an
  external checkpoint. Exact router-tensor occurrence, type, offsets, encoded
  range/hash, scale/bias metadata, genuine real hidden states, real rank-8/9
  tie state, Apple parity, ten-repeat identity, and timing all remain
  unverified at their explicit gates.
- Router-only evidence does not establish any selected expert projection,
  expert MLP, weighted expert aggregation, routed-MoE block, transformer layer,
  attention or earlier hidden-state computation in PulsarMLX, language-model
  logits, token generation, serving, full/giant-model inference, custom Metal,
  tokens per second, or Linux/CUDA runtime parity.

The latest model-free safety replay reported 8 Rust backend routing tests, 21
Rust router-contract tests, 23 focused Python router tests, and one explicitly
selected Rust-to-Python generated-router integration passing. The fixture
generator reported 12 files byte-identical; retained validation observed two
MLX positive, two host tie, and seven negative contract cases over all 11
manifest files. The exact workspace gate separately reported 204 active tests
passing, zero failed, and two native integrations ignored; complete Python
worker discovery passed 67 tests. All 53 research tests, the one-record schema
validation, and the fixture-only six-artifact package verification also
passed. Feature 001's requested Cargo regressions passed 120 tests, and its
`specs/001-apple-silicon-mlx` tree is unchanged from its actual closing commit
`8e10012`. These results establish only their generated, contract-test, and
model-free scopes.

## Platform and test coverage

- At the T076 final focused gate and T077 literal quickstart replay,
  `cargo check --workspace --all-targets` passed on native arm64 macOS, and
  `cargo test --workspace --no-fail-fast` listed 172 tests: 171 active tests
  passed, zero failed, and one native MLX integration test was explicitly
  ignored by the baseline. That test passed when run directly with `--ignored`
  against the frozen local environment. The complete Python worker suite
  separately ran 44 passing tests during T077. These results cover only
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
- The T076 gate passed 25 typed evidence tests, one committed-reference parser
  test, all 14 JSON syntax and cross-record/link checks, the exact workspace
  check, and the exact workspace test command. T077 then replayed every
  supported quickstart command, including the separately authorized bounded
  model prefix. Linux/CUDA runtime, giant-model execution, serving, and
  benchmarking remained explicitly not run; their absence was not converted
  into a successful claim.

## Existing source-quality debt

- `cargo fmt --all -- --check` failed with differences in 25 pre-existing
  upstream Rust files. No repository-wide formatting was performed.
- `cargo clippy --workspace --all-targets -- -D warnings` failed with exit
  status 101 at `crates/kernels/build.rs:41` on
  `clippy::needless_borrows_for_generic_args`.
- The T075 rerun retained the same 25-file rustfmt boundary. Strict workspace
  Clippy reported 25 diagnostics across six inherited tokenizer, kernels,
  GGUF, and quant files. No diagnostic named a PulsarMLX-added crate or source
  target, but inherited errors prevented a complete strict-Clippy pass for the
  whole workspace.
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
- [Push-triggered GitHub Actions run 31023865090](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31023865090)
  later completed successfully for commit `751eb7d` with both the unchanged
  Cargo baseline job and the bounded Apple MLX fixture job. The Cargo job
  reported 171 passed tests, one ignored, and zero failed. The fixture job
  passed 44 Python worker tests, one explicitly selected native device smoke,
  seven evaluated tensor cases, and the synthetic routed-MoE case using the
  frozen environment.
- [Push-triggered GitHub Actions run 31026431975](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31026431975)
  passed the same two-job boundary at quickstart commit `5a43cf0`: the Cargo
  job reported 171 passed, zero failed, and one ignored; the fixture job passed
  44 Python worker tests, one native device smoke, seven tensor cases, and the
  synthetic routed-MoE case. The external-model variable remained empty.
- Standard `macos-15` is an Apple Silicon runner but is not equivalent to the
  local 128 GiB M1 Ultra. The newer fixture job explicitly kept the external
  model variable empty and did not download a checkpoint. Its CPU model/count,
  unified-memory capacity, available disk, thermals, and power were not
  measured. Neither run establishes full-checkpoint or giant-model execution,
  serving, performance, Linux, CUDA, or `io_uring` runtime behavior. Exact run
  evidence and exclusions are in
  [`ci-mlx-smoke.json`](../validation/ci-mlx-smoke.json).

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
