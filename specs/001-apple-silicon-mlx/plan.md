# Implementation Plan: Apple Silicon MLX Backend Bring-Up

**Branch**: `main` (implemented and validated in focused commits)

**Date**: 2026-08-05

**Spec**: [spec.md](spec.md)

**Input**: Feature specification from
`/specs/001-apple-silicon-mlx/spec.md`

**Status**: Complete for the specified initial bounded bring-up. All 78 tasks
are complete; the exact verified depth and exclusions below are authoritative.

## Summary

The delivered additive Apple Silicon reference backend uses MLX 0.32.0 through
one persistent Python worker controlled by Rust and a versioned bounded
protocol. Shared Rust types express backend capabilities and tensor semantics;
`crates/stream` provides an additive exact positional-read source; and
`crates/quant` provides independent scalar Q8_0 oracles. Executed validation
progressed from an evaluated GPU smoke probe through seven tensor fixtures,
portable storage, synthetic routed-MoE, and one 16-row Qwen3MoE Q8_0
gate-projection prefix. Inherited Linux/CUDA source selection and defaults are
unchanged, while their compile/runtime parity remains explicitly unverified.

## Technical Context

**Language/Version**: Rust 2021 edition with the audited rustc 1.97.1 baseline;
the lock-resolved evaluated worker uses native CPython 3.12.13. CPython 3.14.6
is the separate preflight system interpreter, not the MLX worker runtime. The
worker contract admits native CPython 3.10 or newer only when supported by the
pinned MLX wheel.

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
the audited host is macOS 26.0 on Apple M1 Ultra. Static review confirms that
inherited Linux/CUDA selectors and defaults are unchanged, but supported-host
compile/runtime parity was unavailable and remains unverified. GitHub's
standard `macos-15` arm64 CI runs the exact Cargo baseline and a separate
lockfile-backed small-MLX-fixture job; external models and giant-model
validation remain excluded.

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

*GATE: Passed before Phase 0 research, after Phase 1 design, and against actual
T078 completion evidence.*

| Principle | Design evidence | Gate |
| --- | --- | --- |
| Correctness before optimization | Every stage has an independent oracle; performance starts only after parity | PASS |
| Preserve Linux/CUDA behavior | Protected inherited runtime paths are unchanged; additive shared exports were reviewed; runtime parity remains unverified and no cross-platform-safe claim is made | PASS |
| Verified claims only | Fourteen indexed records and the exact-level matrix separate evaluated, synthetic, bounded-real, unavailable, and not-run states | PASS |
| Apple Silicon first class | Explicit MLX GPU selection, Metal proof, native memory gauges, local evidence, and arm64 fixture CI passed | PASS |
| Portable, non-flattened interfaces | Tested common types express tensor/routing/storage semantics while backend mechanisms remain private | PASS |
| MLX before custom Metal | Every Apple execution used the MLX reference path; no custom Metal was added | PASS |
| Reproducible benchmarks | The correctness-gated schema is tested; the initial record is explicitly zero-sample `not_run` with no performance claim | PASS |
| Explicit compatibility | A complete six-level exact matrix prevents fixture, synthetic, bounded-real, giant, and serving implication | PASS |
| License and attribution | External model provenance/license is mandatory; upstream MIT/NOTICE remain intact | PASS |
| Incremental test-backed commits | All 78 dependency-ordered tasks landed in focused validated commits | PASS |
| No secrets or weights | Weights stayed external; staged scans found no secrets, private identifiers, caches, or generated binaries | PASS |
| Documentation is implementation | Spec Kit, validation, session, compatibility, CI, and limitations were reconciled with actual results | PASS |

Final implementation re-check: no constitutional exception is required. Two
separate runtime components remain justified by failure isolation and official
MLX package availability, not by bypassing a shared semantic contract.

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

### Implemented source layout

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
└── validation/                 # committed bounded evidence records, never model weights
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
   has the simplest portable reference path. The artifact was later authorized,
   acquired outside Git, identified immutably, and used only for the admitted
   bounded prefix.
7. Use standard `macos-15` arm64 CI for Cargo baseline evidence and a separately
   pinned small-MLX-fixture job. The fixture job now passes; the external
   checkpoint remains excluded from resource-constrained CI.

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
- [quickstart.md](quickstart.md) gives the replayed validation sequence, actual
  results, and retained stop points for unsupported or deeper stages.

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

Every step stopped at the specification's mandatory conditions and landed as a
focused, test-backed change. The completed breakdown is in [tasks.md](tasks.md).

## Requirement-to-Stage Traceability

| Stage / story | Requirements | Criteria | Final evidence and status |
| --- | --- | --- | --- |
| Stage 0 / US1 Cargo baseline | FR-001, FR-003 | SC-001, SC-011 | **Passed on macOS** — [final replay](../../docs/validation/reproduction-check.json) and [arm64 CI](../../docs/validation/ci-mlx-smoke.json); Linux/CUDA runtime remains unverified. |
| Stage 1 / US1 worker and device | FR-002, FR-005, FR-024 | SC-002 | **Passed** — [device record](../../docs/validation/mlx-device-smoke.json), 44 Python tests, 12 Rust lifecycle tests, evaluated GPU/no fallback. |
| Stage 2 / US2 tensor proof | FR-004, FR-006, FR-007, FR-016 | SC-003 | **Passed at fixture scope** — [seven tensor cases](../../docs/validation/mlx-tensor-fixtures.json) and malformed-input contract tests. |
| Stage 3 / US3 exact storage | FR-010, FR-011, FR-013 | SC-006, SC-012 | **Passed at portable-source scope** — [source record](../../docs/validation/portable-expert-source.json) and [independent replay](../../docs/validation/reproduction-check.json). |
| Stage 4 / US2 Q8_0 reference | FR-008, FR-009, FR-016 | SC-004 | **Passed for declared Q8_0 roles** — strict scalar tests and evaluated Q8_0 fixture in the [tensor record](../../docs/validation/mlx-tensor-fixtures.json). |
| Stage 5 / US3 synthetic MoE | FR-012, FR-013, FR-016 | SC-005, SC-012 | **Passed for the exact synthetic fixture** — [routed-MoE record](../../docs/validation/synthetic-moe-v1.json); no real-checkpoint routing implication. |
| Stage 6 / US4 model admission | FR-014, FR-017, FR-021, FR-022 | SC-008, SC-010 | **Passed for one immutable external artifact and depth** — [admission chain](../../docs/validation/models/qwen3-30b-a3b-q8_0-compatibility.json), external weights, no secret or custom Metal. |
| Stage 7 / US4 bounded parity | FR-015, FR-016 | SC-007 | **Passed at one 16-row intermediate** — [trusted reference](../../docs/validation/models/qwen3-30b-a3b-q8_0-reference-result.json) and [Apple result](../../docs/validation/qwen3-30b-a3b-q8_0-slice.json); no complete model graph. |
| Stage 8 / US5 evidence/benchmark | FR-018, FR-019, FR-020, FR-021, FR-022, FR-023 | SC-008, SC-009, SC-010, SC-011, SC-012 | **Passed at the declared evidence boundary** — [14-record index](../../docs/validation/README.md), exact-level [matrix](../../docs/apple-silicon/COMPATIBILITY.md), and explicit zero-sample [not-run benchmark](../../docs/validation/benchmark-initial.json). |

Cross-cutting FR-019 prevents custom Metal work before the corresponding MLX
reference passes. FR-020 requires every stage to publish explicit unsupported
scope. FR-023 requires source-of-truth and handoff documentation to change with
each completed slice.

## Next Bounded Milestone

This feature plan is closed; there is no next incomplete task in its 78-task
list. The recommended follow-on is a new Spec Kit feature for the same immutable
Qwen checkpoint's layer-0 router projection and deterministic top-8 expert IDs
and weights. It must freeze an independent CPU oracle and exact tensor/memory
admission before Apple output, notify `Mahdi-Dev` before model access, and stop
short of expert MLP execution, a complete layer/model, generation, serving,
performance work, custom Metal, or a Linux/CUDA parity claim.

## Complexity Tracking

No constitution violation requires an exception. The only deliberate
multi-language complexity is the persistent Python worker. The official Python
wheel is the simplest current packaged path for this reference and has the
broadest Python model ecosystem; direct C/C++ FFI, PyO3 embedding, and Swift
introduce more build, ABI, lifecycle, or crash-domain complexity before
correctness has been established.
