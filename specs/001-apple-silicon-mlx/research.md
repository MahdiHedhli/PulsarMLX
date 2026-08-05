# Research: Apple Silicon MLX Backend Bring-Up

**Date**: 2026-08-05

**Scope**: Phase 0 design research only. No MLX package or model weight was
installed or downloaded as part of this research.

## Decision 1: MLX version and supported host

**Decision**: Pin the first reference environment to `mlx==0.32.0` from the
official Python distribution. Require a native Apple Silicon process, macOS 14
or newer, and a supported native CPython interpreter. The audited CPython
3.14.6 interpreter is eligible because MLX 0.32.0 publishes a matching arm64
wheel.

**Rationale**: MLX 0.32.0 was the current stable release on the research date.
The official wheel is the smallest supported route to a current MLX runtime and
does not require introducing a source-built C++ toolchain into the Rust
workspace.

**Alternatives considered**:

- Building MLX from source adds C++20, CMake, Clang, Xcode, SDK, and Metal asset
  packaging requirements before the reference path is proved.
- Using an unpinned latest version would make validation evidence
  irreproducible.
- Silently using CPU when Metal is absent would invalidate Apple accelerator
  claims.

**Primary sources**:

- [MLX v0.32.0 release](https://github.com/ml-explore/mlx/releases/tag/v0.32.0)
- [Official MLX installation requirements](https://ml-explore.github.io/mlx/build/html/install.html)
- [MLX 0.32.0 wheel files](https://pypi.org/project/mlx/#files)

## Decision 2: Initial Rust-to-MLX boundary

**Decision**: Start one long-lived Python MLX worker from a Rust client. Use a
versioned, bounded newline-delimited JSON protocol for lifecycle, metadata,
small fixtures, checksums, and small comparison outputs. Keep weights and
working tensors inside the worker. Add a separate length-framed binary or
file-backed channel only if a later validated operation needs larger transfer.

**Rationale**: The official Python wheel is the simplest current packaged path
for this reference and has the broadest Python model ecosystem. A persistent
subprocess avoids an interpreter startup per operation, isolates Python/MLX
failures from the Rust server, and creates a boundary that can later be
replaced by MLX C without changing backend semantics.

**Alternatives considered**:

- PyO3 embedding reduces control-message overhead but introduces interpreter,
  GIL, linking, packaging, lifecycle, and crash-containment concerns.
- Direct MLX C is a plausible later native bridge, but its current tagged
  package is source-built and trails current MLX core.
- A direct C++ shim exposes the latest core API but adds ABI and Metal-library
  packaging work.
- Swift adds another language and build layer over the MLX C bridge.
- An HTTP model server exposes a much broader contract than the tensor proof
  needs.
- Large tensors encoded as JSON or base64 would be inefficient and difficult
  to bound.

**Primary sources**:

- [MLX project frontends](https://github.com/ml-explore/mlx)
- [MLX C repository](https://github.com/ml-explore/mlx-c)
- [MLX Swift v0.31.6](https://github.com/ml-explore/mlx-swift/releases/tag/0.31.6)
- [MLX LM](https://github.com/ml-explore/mlx-lm)

## Decision 3: Accelerator proof

**Decision**: The first smoke case must establish all of the following in one
evidence record:

1. pinned MLX version and native arm64 Python;
2. `mx.metal.is_available()` is true;
3. at least one `mx.gpu` device exists;
4. a nonsymmetric deterministic matmul is explicitly scheduled on `mx.gpu`;
5. the graph is forced with `mx.eval` and synchronized; and
6. the numerical result matches an independently calculated value.

The capability report remains `available-but-unevaluated` until the evaluated
operation succeeds. Failure is explicit; there is no CPU fallback.

**Rationale**: MLX is lazy. Importing the package, constructing an array, or
reporting a default device does not prove that the intended accelerator
executed a graph.

**Alternatives considered**:

- Treating import as the smoke test cannot distinguish packaging success from
  device execution.
- A symmetric fixture can hide orientation errors; use nonsymmetric data.
- Timing alone is not an execution or correctness oracle.

**Primary sources**:

- [MLX Metal availability](https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.core.metal.is_available.html)
- [MLX devices and streams](https://ml-explore.github.io/mlx/build/html/python/devices_and_streams.html)
- [MLX lazy evaluation](https://ml-explore.github.io/mlx/build/html/usage/lazy_evaluation.html)
- [`mlx.core.eval`](https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.core.eval.html)
- [`mlx.core.synchronize`](https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.core.synchronize.html)

## Decision 4: Portable expert storage

**Decision**: Add an owned, exact-range positional source to `crates/stream`
without replacing the inherited Linux fetcher. Validate a complete contiguous
split-shard layout at open time; validate each half-open request before
allocation; route it to exactly one shard; and loop around Unix `read_at` until
the exact logical payload is read or a structured short-read error occurs.

The first implementation returns a non-cloneable owned payload. mmap is
optional and deferred. No file mapping is described as zero-copy into MLX.

**Rationale**: Positional reads are available on macOS and Linux, avoid shared
seek cursors, give deterministic ownership, and provide the smallest reliable
reference for exact data. Rust explicitly permits successful short reads, so a
loop and exact logical-length check are required.

**Alternatives considered**:

- Shared seek/read requires cursor locking and remains race-prone.
- Whole-shard loading is incompatible with checkpoints larger than memory.
- Automatic cross-shard concatenation would hide invalid GGUF layout
  assumptions; a straddling tensor is rejected.
- Mandatory mmap complicates mapping lifetime and residency claims before it
  provides measured value.
- Replacing the `io_uring` path risks changing inherited Linux performance and
  semantics without Linux/CUDA evidence.

**Primary sources**:

- [Rust Unix `FileExt`](https://doc.rust-lang.org/std/os/unix/fs/trait.FileExt.html)
- [Apple `pread(2)`](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/pread.2.html)
- [Apple `mmap(2)`](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/mmap.2.html)

## Decision 5: Memory evidence

**Decision**: Report independent gauges instead of summing overlapping values:

- model file bytes;
- mapped virtual bytes;
- mapped resident bytes when sampled;
- owned compressed bytes;
- decoded array bytes;
- temporary current and peak array bytes;
- MLX active, cache, and peak bytes when available;
- process physical footprint when available; and
- system memory-pressure state.

Budgets separately cover compressed cache, decoded cache, temporary reserve,
and mandatory system headroom. Optional or overlapping gauges remain labeled
as such.

**Rationale**: Unified memory avoids a conventional CPU-to-GPU copy model, but
it does not mean mappings, MLX allocations, process footprint, and resident
pages are disjoint. Adding them produces a misleading total. MLX memory limits
are guidance, not a hard process allocation guarantee.

**Alternatives considered**:

- A single “GPU memory” number loses file, cache, allocator, and process
  distinctions.
- Treating mapped virtual size as resident memory materially overstates use.
- Assuming mapped file pages alias MLX arrays would be an unverified zero-copy
  claim.

**Primary sources**:

- [MLX unified memory](https://ml-explore.github.io/mlx/build/html/usage/unified_memory.html)
- [MLX active memory](https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.core.get_active_memory.html)
- [MLX cache memory](https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.core.get_cache_memory.html)
- [MLX memory limit](https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.core.set_memory_limit.html)

## Decision 6: First quantized reference and real-model candidate

**Decision**: Establish Q8_0 scalar decode/matvec parity first and use the
official `Qwen/Qwen3-30B-A3B-GGUF` Q8_0 artifact as the initial real-checkpoint
candidate. Before any download or execution, record the exact repository
revision, filename, size, SHA-256, model license, architecture metadata,
tensor/quantization inventory, and a conservative disk and memory budget.

The first real proof is bounded to a routed expert set or similarly narrow
intermediate forward boundary. It may emit named intermediate values, logits,
or a token depending on the proven graph depth. It is not a full giant-model
inference claim.

**Rationale**: The inherited parser recognizes `qwen3moe`; the official model
card describes 30.5B total parameters, 3.3B activated, 128 experts, and 8 active
experts. The official GGUF repository provides a 32.5 GB Q8_0 artifact. Q8_0 is
larger than Q4_K_M but offers the simplest current portable reference route.
The audited 128 GB host can be budgeted for this bounded candidate, while the
standard CI runner cannot.

**Alternatives considered**:

- The Q4_K_M artifact is smaller (18.6 GB) but must wait for complete Q4_K
  reference parity.
- Qwen3-235B-A22B GGUF is far larger and inappropriate as the first slice.
- Qwen1.5-MoE-A2.7B is smaller, but uses a different `qwen2_moe` architecture
  not recognized by the current source and a different license; selecting it
  would expand loader and licensing scope.
- Synthetic fixtures remain necessary but cannot establish real-checkpoint
  compatibility.

**Primary sources**:

- [Qwen3-30B-A3B model card](https://huggingface.co/Qwen/Qwen3-30B-A3B)
- [Official Qwen3-30B-A3B GGUF card](https://huggingface.co/Qwen/Qwen3-30B-A3B-GGUF)
- [Official Q8_0 artifact](https://huggingface.co/Qwen/Qwen3-30B-A3B-GGUF/blob/514a59606e483e4e0d22d4e4e7b39715a41786bb/Qwen3-30B-A3B-Q8_0.gguf)
- [Qwen3 technical announcement](https://qwenlm.github.io/blog/qwen3/)
- [Qwen3-235B-A22B GGUF card](https://huggingface.co/Qwen/Qwen3-235B-A22B-GGUF)
- [Qwen1.5-MoE-A2.7B card](https://huggingface.co/Qwen/Qwen1.5-MoE-A2.7B)

## Decision 7: CI runner and validation split

**Decision**: Keep the repository baseline on GitHub's standard public
`macos-15` runner and assert `arm64` before running the exact Cargo check and
test commands. Do not put the external real model in CI. Add a pinned MLX
fixture job only after the worker and its small deterministic test dependency
are specified and lockable.

**Rationale**: GitHub documents the standard `macos-15` public runner as arm64
Apple M1 with limited CPU, memory, and disk. It is appropriate for build and
small fixture evidence, not a 32.5 GB model or giant-MoE performance claim.

**Alternatives considered**:

- `macos-15-intel` would validate the wrong architecture.
- A larger Apple runner is unnecessary for the current Cargo baseline and may
  not be available under repository billing or policy.
- Calling standard CI a local M1 Ultra performance proxy would be misleading.

**Primary sources**:

- [GitHub-hosted runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [GitHub runner image labels](https://github.com/actions/runner-images#available-images)
- [macOS 15 arm64 image inventory](https://github.com/actions/runner-images/blob/main/images/macos/macos-15-arm64-Readme.md)

## Resolved Unknowns and Deferred Gates

The platform, MLX version, process boundary, storage reference, first quant
format, model candidate, and CI runner are resolved. These items are
deliberately deferred to measured implementation evidence. The trusted
real-model oracle and exact reachable output boundary are a mandatory gate
before User Story 4, but they do not block the earlier baseline, worker,
storage, tensor, quantization, or synthetic tasks:

- exact float tolerances per primitive and dtype;
- whether a binary side channel is needed after small worker fixtures;
- whether mmap improves the measured storage bottleneck;
- the immutable trusted-reference runtime/version/command and exact real-model
  graph depth achievable under the declared memory budget;
- Linux `io_uring` hardening, which is a separate regression-tested change;
  and
- any custom Metal kernel target, which requires a correct MLX reference and a
  measured bottleneck first.
