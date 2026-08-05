# Implementation Plan: Apple Silicon MLX Backend Bring-Up

**Branch**: `main` (planning only; implementation branch not created)

**Date**: 2026-08-05

**Spec**: [spec.md](spec.md)

**Input**: Feature specification from
`/specs/001-apple-silicon-mlx/spec.md`

**Status**: Pre-implementation plan. This document does not claim that MLX is
installed, that an MLX operation has run, or that model inference works.

## Summary

Bring up an additive Apple Silicon backend in correctness-gated stages while
leaving the inherited Linux/CUDA path and defaults intact. The reference path
will use MLX 0.32.0 through one persistent Python worker controlled by Rust,
with a versioned bounded protocol. Shared Rust types will express backend
capabilities and tensor semantics; `crates/stream` will gain an additive exact
positional-read source; `crates/quant` will provide independent scalar
oracles. Validation proceeds from an evaluated GPU smoke probe to tensor and
quantized fixtures, a synthetic routed-MoE layer, and one bounded real-model
slice using an immutable external checkpoint.

## Technical Context

**Language/Version**: Rust 2021 edition with the audited rustc 1.97.1 baseline;
CPython 3.14.6 for the first local worker environment, while the worker contract
requires native CPython 3.10 or newer supported by the pinned MLX wheel.

**Primary Dependencies**: Existing Cargo workspace dependencies; pinned
`mlx==0.32.0` in a project-local Python virtual environment; Python standard
library for the initial worker transport. No PyO3, custom Metal, or native MLX
C/C++ dependency in the reference path.

**Storage**: Existing GGUF and split-GGUF files remain external to Git. The
portable reference source uses opened file handles and exact positional reads;
owned compressed payloads cross the storage boundary. Mapping is optional and
deferred until its lifetime and residency claims can be proved.

**Testing**: `cargo test`, focused Rust unit/contract/integration tests, Python
worker unit tests, deterministic cross-process fixtures, scalar numerical
oracles, and named real-model comparison evidence. The existing exact macOS
workspace commands remain release gates.

**Target Platform**: Native arm64 Apple Silicon on macOS 14 or newer for MLX;
the audited host is macOS 26.0 on Apple M1 Ultra. Existing Linux/CUDA targets
remain supported and behaviorally unchanged. Minimal CI uses GitHub's standard
`macos-15` arm64 runner, whose resource limits exclude giant-model validation.

**Project Type**: Multi-crate Rust runtime plus a local Python worker package.

**Performance Goals**: No throughput target is admitted during reference
bring-up. First establish reproducible latency, throughput, I/O, and peak-memory
baselines after correctness passes; later optimization must name and measure a
bottleneck.

**Constraints**: No silent CPU fallback; no model files or credentials in Git;
no broad engine rewrite; no custom Metal before MLX reference parity; exact
range and checked arithmetic at storage boundaries; bounded IPC; deterministic
fixtures; conservative memory headroom; stop on unknown layout, provenance,
device, or parity.

**Scale/Scope**: One MLX device, one process-local worker, small committed
synthetic fixtures, Q8_0 as the first real-checkpoint quantization candidate,
one routed layer or similarly bounded real-model forward boundary, and no
production HTTP/MCP serving in this feature.

## Constitution Check

*GATE: Passed before Phase 0 research and re-evaluated after Phase 1 design.*

| Principle | Design evidence | Gate |
| --- | --- | --- |
| Correctness before optimization | Every stage has an independent oracle; performance starts only after parity | PASS |
| Preserve Linux/CUDA behavior | Apple path is additive; existing fetcher, engine, defaults, and CUDA interfaces stay intact | PASS |
| Verified claims only | Capability states separate unavailable, unevaluated, and evaluated; evidence records actual commands/results | PASS |
| Apple Silicon first class | Explicit MLX selection, Metal proof, native memory gauges, arm64 CI | PASS |
| Portable, non-flattened interfaces | Common types express model/storage semantics; backend extensions remain optional | PASS |
| MLX before custom Metal | Worker reference path precedes and gates any Metal proposal | PASS |
| Reproducible benchmarks | Benchmark entity records commit, input, warmup, samples, statistics, device, memory, and correctness prerequisite | PASS |
| Explicit compatibility | Quantization and model records are required before claims or execution | PASS |
| License and attribution | External model provenance/license is mandatory; upstream MIT/NOTICE remain intact | PASS |
| Incremental test-backed commits | Stages are bounded and independently testable | PASS |
| No secrets or weights | `.gitignore`, external immutable model identity, and pre-commit secret review are required | PASS |
| Documentation is implementation | Each slice updates Spec Kit, validation, session log, compatibility, and limitations | PASS |

Post-design re-check: no constitutional exception is required. Two separate
runtime components are justified by failure isolation and official MLX package
availability, not by bypassing a shared semantic contract.

## Project Structure

### Documentation (this feature)

```text
specs/001-apple-silicon-mlx/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── backend-and-worker-v1.md
│   ├── expert-source.md
│   ├── tensor-and-quant-v1.md
│   └── validation-evidence.md
├── checklists/
│   ├── requirements.md
│   └── design-readiness.md
└── tasks.md
```

### Proposed source layout

```text
Cargo.toml
crates/
├── backend/                    # backend-neutral capabilities and tensor contracts
│   ├── Cargo.toml
│   └── src/lib.rs
├── mlx-backend/                # macOS/arm64 worker client and bounded vertical graph
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs
│       └── bin/pulsar-mlx.rs
├── stream/                     # existing crate plus additive portable exact source
├── quant/                      # existing crate plus scalar quant reference entry points
├── gguf/                       # inherited parser; focused checked-arithmetic fixes only
├── tokenizer/                  # inherited tokenizer reused through explicit contracts
├── kernels/                    # inherited CUDA implementation, unchanged by default
├── engine/                     # inherited Linux/CUDA engine, unchanged by default
└── serve/                      # inherited server, outside initial Apple feature
python/
└── pulsar_mlx_worker/
    ├── __init__.py
    ├── __main__.py
    ├── protocol.py
    ├── runtime.py
    └── tests/
fixtures/
└── mlx/                        # small deterministic, reviewable generated fixtures only
docs/
├── apple-silicon/
└── validation/                 # future committed evidence records, never model weights
```

**Structure Decision**: Use a small semantic Rust crate and a separate
MLX-worker client rather than injecting Python/MLX concerns into the inherited
CUDA engine. Add portable file sourcing to the existing storage crate and
portable scalar references to the existing quant crate because those are the
current owners of those semantics. The Python worker is a sibling runtime
component with a narrow versioned contract. Existing Linux-only crates and
entry points retain their paths and selection behavior.

## Phase 0: Research Decisions

Research is recorded in [research.md](research.md). Resolved decisions:

1. Use official MLX 0.32.0 Python arm64 wheels and one persistent subprocess.
2. Prove Metal availability and an explicitly scheduled, evaluated,
   synchronized GPU matmul; import success is insufficient.
3. Use bounded NDJSON only for control/small evidence; keep tensors and weights
   inside the worker and introduce separate binary/file-backed framing only
   when measured need exists.
4. Use owned exact positional reads as the portable storage reference; defer
   mmap and make no zero-copy claim.
5. Preserve the inherited `io_uring`/`O_DIRECT` fetch path. Harden it only in a
   separate focused change with Linux evidence.
6. Target the official Qwen3-30B-A3B-GGUF Q8_0 artifact for the first real-model
   candidate because its `qwen3moe` metadata is recognized upstream and Q8_0
   has the simplest portable reference path. The artifact is not downloaded in
   this preflight.
7. Use standard `macos-15` arm64 CI for Cargo baseline evidence; keep MLX and
   real-model validation outside that resource-constrained baseline until a
   bounded fixture job is specified.

## Phase 1: Design Outputs

- [data-model.md](data-model.md) defines capabilities, tensor contracts,
  storage reads, compatibility records, validation cases, and benchmarks.
- [backend-and-worker-v1.md](contracts/backend-and-worker-v1.md) fixes the
  explicit backend-selection and persistent-worker protocol.
- [expert-source.md](contracts/expert-source.md) defines exact owned reads,
  split-shard validation, error behavior, and Linux preservation.
- [tensor-and-quant-v1.md](contracts/tensor-and-quant-v1.md) fixes tensor
  orientation, synchronization, strict Q8_0 layout, routing, and parity rules.
- [validation-evidence.md](contracts/validation-evidence.md) defines the
  evidence schema required before capability or performance claims.
- [quickstart.md](quickstart.md) gives the implementation-session sequence and
  validation stop points without claiming that unbuilt commands work today.

## Delivery Sequence

1. Preserve and continuously re-run the exact Cargo baseline.
2. Establish the backend capability types and persistent worker lifecycle.
3. Add the pinned local Python environment and evaluated MLX device probe.
4. Prove deterministic tensor execution and malformed-input rejection.
5. Add exact portable expert reads and storage contract tests.
6. Implement Q8_0 scalar reference coverage needed by the selected slice.
7. Validate a generated synthetic routed-MoE layer end to end.
8. Create a compatibility record and conservative memory budget for the
   external Qwen3-30B-A3B Q8_0 candidate.
9. Run one bounded real-model intermediate/logits/token slice and compare it
   with a named trusted reference.
10. Publish reproducible evidence; only then propose measured optimization.

Every step stops at the specification's mandatory conditions and lands as a
focused, test-backed change. The task breakdown is in [tasks.md](tasks.md).

## Requirement-to-Stage Traceability

| Stage / story | Primary requirements | Measurable gates | Design authority |
| --- | --- | --- | --- |
| Stage 0 / US1 Cargo baseline | FR-001, FR-003 | SC-001, SC-011 | Preflight baseline and constitution II |
| Stage 1 / US1 worker and device | FR-002, FR-005, FR-024 | SC-002 | Backend/worker contract |
| Stage 2 / US2 tensor proof | FR-004, FR-006, FR-007, FR-016 | SC-003 | Tensor/quant contract |
| Stage 3 / US3 exact storage | FR-010, FR-011, FR-013 | SC-006, SC-012 | Expert-source contract |
| Stage 4 / US2 Q8_0 reference | FR-008, FR-009, FR-016 | SC-004 | Tensor/quant contract |
| Stage 5 / US3 synthetic MoE | FR-012, FR-013, FR-016 | SC-005, SC-012 | Tensor/quant and evidence contracts |
| Stage 6 / US4 model admission | FR-014, FR-017, FR-021, FR-022 | SC-008, SC-010 | Model compatibility record and quickstart gate |
| Stage 7 / US4 bounded parity | FR-015, FR-016 | SC-007 | Preselected trusted oracle and evidence contract |
| Stage 8 / US5 evidence/benchmark | FR-018, FR-019, FR-020, FR-021, FR-022, FR-023 | SC-008, SC-009, SC-010, SC-011, SC-012 | Evidence contract and project constitution |

Cross-cutting FR-019 prevents custom Metal work before the corresponding MLX
reference passes. FR-020 requires every stage to publish explicit unsupported
scope. FR-023 requires source-of-truth and handoff documentation to change with
each completed slice.

## Complexity Tracking

No constitution violation requires an exception. The only deliberate
multi-language complexity is the persistent Python worker. The official Python
wheel is the simplest current packaged path for this reference and has the
broadest Python model ecosystem; direct C/C++ FFI, PyO3 embedding, and Swift
introduce more build, ABI, lifecycle, or crash-domain complexity before
correctness has been established.
