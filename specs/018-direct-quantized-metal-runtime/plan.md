# Implementation Plan: Direct-Quantized Metal Runtime

**Branch**: `feat/018-direct-quantized-metal-runtime` | **Date**: 2026-08-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/018-direct-quantized-metal-runtime/spec.md`

## Summary

Build the smallest correctness-first Apple Metal path that consumes packed
IQ2_XXS gate/up weights and an f32 activation to produce an f32 output vector
without materializing a complete f32 weight matrix. Freeze the numerical
classification contract first, reuse the reviewed Feature 017 page-aligned
slab and `newBufferWithBytesNoCopy` ownership commits selectively, qualify a
synthetic boundary, then advance through one real matrix and only the bounded
expert/layer rungs supported by passing evidence.

## Technical Context

**Language/Version**: Rust 1.97.1; Objective-C++17; Metal Shading Language compiled by macOS 26.0; Python 3.14.6 for the independent oracle/evidence harness

**Primary Dependencies**: Apple Metal and Foundation frameworks; existing `stream`, `quant`, `gguf`, and Python research modules; MLX 0.32.0 and NumPy 2.4.5 only for reference comparison

**Storage**: Local six-shard immutable GLM-5.2 GGUF checkpoint for Tier-3 tests; tiny generated synthetic fixtures for CI; no checkpoint bytes committed

**Testing**: Rust unit/integration tests, native Metal tests on Apple Silicon, Python `unittest` evidence validators, existing Cargo workspace and MLX fixture suites

**Target Platform**: arm64 macOS on Apple Silicon; Linux/CUDA behavior must remain unchanged and Apple-only code must compile conditionally

**Project Type**: Rust workspace with an Apple Objective-C++ platform bridge and Python research oracle

**Performance Goals**: Retain 3 warmups and at least 30 steady-state samples for one real matrix; materially reduce absolute IQ2_XXS gate/up boundary time relative to the committed optimized NumPy-decode-plus-MLX path, or preserve a qualified negative result

**Constraints**: No complete f32 weight materialization in the direct path; zero hidden CPU fallback; frozen tolerances; bounded memory; no P2/golden-eight; one optional P1 only after a qualified material complete-layer gain

**Scale/Scope**: First target is a `[2048, 6144]` IQ2_XXS routed gate/up matrix with 66-byte blocks per 256 weights; ladder stops at the deepest qualified bounded rung

## Constitution Check

*GATE: Passed before Phase 0 research and rechecked after Phase 1 design.*

| Principle | Plan evidence | Status |
| --- | --- | --- |
| Correctness before optimization | Numerical contract and scalar/NumPy references precede kernel execution | Pass |
| Preserve Linux/CUDA | Objective-C++ compilation and public APIs are macOS-gated; portable fallback is unchanged | Pass |
| Verified claims only | Every rung has a raw record, validator, claim boundary, and negative-result state | Pass |
| Apple Silicon first-class | Metal availability, unified-memory lifetime, device identity, and memory pressure are explicit | Pass |
| Portable interfaces | Packed-matrix request and result contracts avoid leaking policy into shared model semantics | Pass |
| MLX reference before Metal | Feature 016 already qualified the exact scalar/NumPy/MLX reference boundary | Pass |
| Reproducible benchmarks | Source/checkpoint/input binding, warmups, raw samples, and synchronized timings are required | Pass |
| Explicit compatibility | Only IQ2_XXS gate/up and admitted shapes/layouts are initially supported | Pass |
| Licensing and attribution | No donor code is introduced; Feature 017 commits are same-repository reviewed lineage | Pass |
| Incremental commits | Spec, ownership import, synthetic gate, real matrix, and deeper rungs are separate commits | Pass |
| No secrets or weights | Tier-3 paths are symbolic; checkpoint bytes and private paths are excluded and scanned | Pass |
| Documentation complete | Contracts, quickstart, raw evidence, reviewer index, and overnight review ship with behavior | Pass |

No constitution exception is requested.

## Design Decisions

1. **Selective Feature 017 reuse**: cherry-pick clean commits `111ffb6d`
   (stable slab allocator), `f2b1b130` (no-copy Metal registration), and
   `a5fcf92f` (exact IQ2/IQ3 f32 reference decoder), resolving only mechanical
   conflicts. Do not merge Feature 017 or touch its worktree.
2. **Smallest kernel**: initially dispatch one logical output row per Metal
   thread. Each thread walks packed 66-byte IQ2_XXS blocks in row order, looks
   up magnitude/sign bytes, multiplies the f32 activation, and accumulates f32.
   This is deliberately simple and inspectable; later geometry is evidence-led.
3. **Ancillary lookup buffers allowed**: immutable IQ2 magnitude and sign
   tables may be uploaded once. The prohibition is complete decoded f32 weight
   materialization, not small format metadata.
4. **Synchronous validation mode**: every measured dispatch waits for command
   completion and records command-buffer failure. Asynchronous batching remains
   deferred until the single-matrix contract qualifies.
5. **No implicit fallback**: direct mode returns a bounded error on unsupported
   input. Reference execution is an explicit caller-selected mode.
6. **Evidence before integration**: the direct bridge remains opt-in and does
   not alter default inference until the complete bounded ladder supports it.

## Bounded Ladder and Gates

| Rung | Boundary | Admission gate |
| --- | --- | --- |
| A | Synthetic packed block/matrix | 100 deterministic repetitions; malformed/lifetime tests pass |
| B | One real IQ2_XXS matrix | Frozen binding, scalar/NumPy/direct comparison, 3 warmups + 30 samples |
| C | Repeated warm matrix | Stable registration reuse, setup separated, no memory growth |
| D | Real gate projection | Qualified against existing gate reference |
| E | Real up projection | Qualified against existing up reference |
| F | One routed expert | Gate/up direct; down remains qualified reference until separately selected |
| G | Top-8 plus shared MoE | Exact routes; numerical classification and component timings |
| H | Representative complete layer | Exact route/midpoint contract and material absolute gain |
| Optional P1 | `[9703,21615]` | Clean committed source, normal pressure, no competing inference, H material and green |

Failure, divergence, unsafe lifetime, or critical/urgent pressure stops deeper
admission while preserving the failing record.

## Project Structure

### Documentation (this feature)

```text
specs/018-direct-quantized-metal-runtime/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── numerical-qualification-contract.md
├── quickstart.md
├── checklists/
│   └── requirements.md
├── contracts/
│   ├── direct-metal-iq2-xxs.md
│   └── evidence-record.md
└── tasks.md
```

### Source Code (repository root)

```text
crates/stream/
├── build.rs
├── src/
│   ├── stable_slab.rs
│   ├── apple_metal_bridge.rs
│   ├── apple_metal_bridge.mm
│   └── lib.rs
└── tests/
    ├── apple_metal_bridge.rs
    └── iq2_xxs_metal.rs

scripts/research/
├── benchmark_glm52_iq2_xxs_metal.py
├── analyze_glm52_iq2_xxs_metal.py
└── tests/
    ├── test_f018_numerical_contract.py
    └── test_f018_evidence.py

docs/research/glm52/
├── F018_OVERNIGHT_REVIEW.md
├── raw/
└── tables/
```

**Structure Decision**: Extend the selectively imported Feature 017 slab and
Metal registration seam in `stream` for the smallest experiment. Do not create
a second allocator or copy the entire Feature 017 runtime. If the direct path
qualifies, Feature 017 will later decide the permanent crate boundary.

## Validation Strategy

- Tier 1: contract classification, synthetic packed decoder/oracle, malformed
  requests, evidence schemas, generated artifacts, privacy, Linux-safe build.
- Tier 2: native Apple Metal registration, synthetic direct IQ2_XXS GEMV,
  lifecycle reuse/teardown, deterministic repeats, resource checks.
- Tier 3: exact admitted checkpoint matrix, gate/up, and eligible deeper rungs.
- Every Tier-3 record binds the source commit and external checkpoint set hash;
  missing prerequisites fail clearly rather than skip-pass.

## Complexity Tracking

No constitution violations require justification. The Objective-C++ adapter is
the smallest platform component that can own Metal objects and completion
fences while Rust retains policy and lifetime types.
