# PulsarMLX Feature 017 Opus review packet

## Numerical parity sprint update

- Final parity boundary: `8adee21`; current feature branch tip is recorded by
  the sprint commit that updates this packet.
- Checkpoint-free synthetic gates now pass in strict order: projection, router, complete expert, top-8 plus shared, MLA/dense, complete layer, and final norm/logits/top-k.
- Q8_0 remains the only decoder exercised by these public-safe parity gates; no new decoder was added because the current fixtures do not require Q2_K, Q3_K, IQ2_S, IQ4_XS, or Q5_K.
- Final output is classified `numerically_qualified_greedy_identical` under `golden_strict`; it is not claimed `golden_identical` because the independent RMS reference differs by operation order below the explicit `1e-14` threshold.
- Apple lifecycle qualification now has a fail-closed Rust contract covering register, submit, completion, cancel-before-submit, queued cancellation modeling, release, destroy, repeated generations, and stale-generation rejection. This is lifecycle evidence, not proof of MLX import behavior.
- Official MLX C API CPU and GPU managed import/synchronization are qualified
  by the standalone child-process matrix in
  `docs/architecture/reviews/f017-mlx-gpu-teardown-forensics.md`. The prior
  exit-134 result was caused by an uninitialized `mlx_stream` output passed to
  `mlx_get_default_stream`; initialized handles, explicit synchronization,
  ownership callbacks, teardown order, and reuse all pass. The recommendation
  remains a narrow Rust C ABI plus Objective-C++ adapter with these invariants.
- The actual Rust/Objective-C++ adapter now carries those invariants in
  `crates/stream/src/apple_mlx_bridge.rs` and `.mm`. Adapter tests cover
  borrowed/default and owned streams, explicit evaluation/synchronization,
  pointer identity, exactly-once callbacks, 30 borrowed cycles, 100 owned
  cycles, and fail-closed invalid imports.
- A 500-iteration deterministic semantic soak passed through final
  norm/logits/top-k with stable fingerprint, bounded RSS growth, balanced
  registrations/generations/teardowns, protected-shared residency, and stale
  generation rejection. The public-safe decoder report separates decode time
  from allocator behavior for Q8_0, Q6_K, IQ2_XXS, and IQ3_XXS.
- No full-model inference or Feature 018 kernel work was performed.

## Review scope

Independent review of the native runtime foundation after the M2 Max recovery
and checkpoint-free contract milestones. This packet intentionally excludes
full-model inference and direct quantized Metal kernel implementation.

## Branch and evidence

- Branch: `feat/017-rust-native-inference-runtime`
- Recovery: the externally-mutated Studio linked worktree was archived outside
  the repository and removed using normal Git worktree cleanup. Only the M2
  worktree remains registered.
- F017 branch ancestry preserves `c4a760ae` and all later F017 commits.
- Current committed boundaries include the page-aligned slab, whole-matrix
  positional I/O, inventory-driven residency budgets, Q8_0/Q6_K/IQ2_XXS/IQ3_XXS
  exact Rust decoders, Metal no-copy registration, attributed telemetry,
  mode-aware validation, expert residency tiers, fixture ladder adapter, and
  backend-neutral runtime contracts.

## Ownership and residency

- Rust owns checkpoint identity, slots, admission, lifecycle, cancellation,
  and telemetry.
- Metal registration is an opaque adapter handle over Rust-owned aligned
  storage; reuse and teardown are explicit.
- Expert tiers are compressed resident, decoded hot, native-ready hot, and
  transient. Admission is bounded and does not implicitly evict.
- Shared entries can be required to remain protected.
- Missing entries return an explicit reference fallback.
- Decoded-all trunk residency remains rejected by the M2 Max safety policy.

## Validation and fixtures

- `golden_strict` and `teacher_forced_validation` use the frozen classification
  vocabulary and deterministic stop/continue behavior.
- The synthetic public-safe manifest binds all 11 ordered ladder boundaries to
  hash-bound artifacts and telemetry/memory evidence.
- The adapter is structural only: router, expert, MLA, layer, and logits math
  still require real local or generated boundary executors before numerical
  parity can be claimed.

## Native MLX and F018 boundary

- ADR 0005 selects a narrow Rust C ABI with an Objective-C++ implementation
  boundary. The qualified stream initialization, explicit synchronization,
  owner-last, and exactly-once callback rules are now implemented and tested.
- Python remains the research/reference path and is not a shipping
  dependency.
- The F017/F018 boundary contract defines capability discovery, ownership
  handoff, qualified-direct versus reference-fallback classification,
  validation mode, telemetry, cancellation, and qualification metadata.

## Format scope

- Q5_K is the next justified exact Rust decoder candidate from 162 real
  non-expert trunk tensors and existing real reference evidence.
- Q2_K, Q3_K, IQ2_S, and IQ4_XS are deferred until a GLM52 expert manifest or
  other format-bound fixture justifies them.

## Questions for Opus

1. Is any Rust/FFI lifetime or `newBufferWithBytesNoCopy` teardown ordering
   unsound under asynchronous completion?
2. Does the expert residency abstraction support future compressed expert
   residency and native-ready reuse without coupling Feature 018 policy into
   Feature 017?
3. Is the official-MLX-through-Objective-C++ recommendation maintainable, or
   is a narrower C-only API required before native import qualification?
4. Is the F017/F018 capability and ownership boundary sufficiently narrow for
   future direct kernels?
5. What minimum checkpoint-free router, complete-expert, MLA/layer, and logits
   evidence must pass before requesting the first M1 Ultra P1 run?

## Remaining P1 prerequisites

- Remote CI for adapter-integrated SHA `6cf0d18419f5782870d43268a65d976492113c39`
  passed in [run 31424679913](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31424679913),
  including both Apple Silicon jobs.
- Complete numerical checkpoint-free executors for real bound model slabs;
  synthetic semantic gates are already banked through logits/top-k.
- Retain the existing Apple registration and cancellation/teardown tests as
  prerequisites for the native GPU bridge; queued MLX cancellation is not
  exposed by the official C API and remains an outer Rust lifecycle concern.
- Select additional decoder formats only from a bound inventory/fixture need.
- Run public-safe workspace CI and resolve independent review blockers.

## Final adapter integration evidence

- The actual Rust/Objective-C++ adapter carries initialized MLX output handles,
  borrowed versus owned stream lifetimes, explicit submission-stream
  synchronization, Rust owner retention through array teardown, fail-closed
  import validation, and exactly-once managed ownership callbacks.
- Local native tests cover CPU and GPU managed import, borrowed/default and
  owned streams, pointer identity, explicit operations and synchronization,
  invalid input, repeated lifecycle cycles, and callback balance.
- The adapter is synchronous at this boundary because the installed MLX C API
  does not expose queued cancellation. Outer Rust cancellation must therefore
  complete or reject work before host reuse.
- The M1 handoff is prepared at
  `docs/architecture/reviews/f017-m1-ultra-p1-handoff.md`; it is not executed
  on ColPanicM2.
