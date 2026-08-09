# Feature Specification: Rust Native Runtime Foundation (017)

**Feature Branch**: `feat/017-rust-native-inference-runtime`
**Created**: 2026-08-09
**Status**: Draft (spec-kit updates applied, implementation not started)
**Input**: Feature 016 completed evidence + post-golden-eight authoritative inputs in `docs/research/glm52/`

## Background

Feature 016 established a validated GLM-5.2 reference path and produced stable post-run analyses under commit `a948b68d9868a34b0cc9b00aacaa4ad2330b0f55`.

Feature 017 must now build a native runtime foundation on the basis of these facts, not speculative assumptions.

## Authoritative inputs for Feature 017 decisions

- `docs/research/glm52/POST_GOLDEN8_CALCULATIONS.md`
- `docs/research/glm52/raw/f016-golden8-post-run-calculations-0001.json`
- `docs/research/glm52/raw/f016-gguf-trunk-inventory-0001.json`

These files are required as read-only inputs; Feature 017 should not redefine foundational size assumptions.

## Key empirical facts (from authoritative inputs)

- Trunk inventory: 1,353 non-expert tensors, excluding 456 expert matrices.
- Logical trunk size: 12.549 GiB compressed.
- Logical trunk size decoded to f32: 61.675 GiB.
- Current dense/trunk read behavior: 6,136,906 total row-read calls.
- Equivalent logical whole-matrix read behavior: 954 calls.
- Reduction is a request-count arithmetic signal only; do not represent as a speedup claim.
- Warm median uninstrumented residual: 1,675.492 s (short-context inference context).
- Warm expert-cache storage appears only at a few seconds per stack.
- No 018 kernel has been selected.

## Scope and goals

1. Build a Rust-native memory and orchestration foundation where ordinary inference does not require a Python process.
2. Establish a page-aligned native slab allocator and stable residency lifecycle.
3. Establish deterministic positional I/O semantics for single-tensor and whole-matrix reads.
4. Define compressed/trunk and decoded residency interfaces that permit compressed-first strategies.
5. Define a portable differential fixture contract for M2 Max development without checkpoint download.
6. Qualify one or more exact Rust decode boundaries.
7. Qualify an Apple native buffer-registration spike and ownership lifecycle.
8. Select a narrow MLX native access route by ADR.
9. Add a checkpoint-free fixture ladder up to representative layer/logit boundaries.
10. Define mode-aware validation classes and mismatch handling.

## Non-goals (explicitly out of scope)

- Production direct quantized Metal kernels.
- End-to-end full-M2 full-architecture kernel optimization.
- Reopening Feature 016 claims.
- Full 238GB checkpoint requirement for routine development/CI.
- Token throughput/SLO claims before M1 Ultra parity gate.
- Server/product serving claims.

## Immutable constraints

- Do not require 61.675 GiB decoded-trunk residency as default baseline.
- Do not implement a policy requiring decoded-all trunk residency before allocator evidence on M2 Max.
- Treat whole-matrix reads as first-class APIs.
- Preserve short-read and overflow safety as hard failures.
- Preserve fail-closed behavior across memory admission and fixture mismatch.
- Do not distribute checkpoint bytes in repository.
- Preserve Python/NumPy/MLX reference paths as immutable checks.

## Authoritative residency strategy

Feature 017 designs must support at least:
- compressed-all trunk residency
- decoded hot-subset residency
- transient decode behavior
- hybrid compressed-all + decoded-hot residency experimentation

No implementation may assume `decoded_all` residency is safe without allocator and pressure experiments on M2 Max.

## User stories (mandatory)

### User Story 1 — Deterministic slab lifecycle
A systems engineer can allocate, retain, and release native slabs with stable IDs and observable pressure metrics, with no use-after-free.

Acceptance:
- Stable slab IDs across lease lifetime.
- Explicit bounded failures under pressure.
- Reuse counters and residency telemetry are available.

### User Story 2 — Whole-matrix-first positional I/O
A runtime developer can request whole tensors/matrices in bounded reads rather than forcing row-by-row amplification by default.

Acceptance:
- Bounded API supports exact matrix range reads and exact-byte counts.
- Request count telemetry records bulk vs row request forms.
- Short-read and overflow are explicit failures.

### User Story 3 — Inventory-driven memory design
A runtime designer can instantiate residency classes from the authoritative trunk inventory and prove safety on M2 Max.

Acceptance:
- Slot classes are derived from measured tensor size/usage categories (not hand-wavy constants).
- Policies that exceed reserved-safe M2 Max memory are rejected.

### User Story 4 — Feature 016-compatible exactness
A developer can run exactness checks against existing reference artifacts at each boundary.

Acceptance:
- Fixture boundaries map to exact decoder and/or measured numerical classes.
- Mismatch paths are fail-closed.

## Functional requirements

- **FR-017-01**: Add Rust-native page-aligned slot allocator with deterministic alignment, slot size classes, stable addresses, and explicit ownership.
- **FR-017-02**: Introduce bounded synchronous positional I/O API with shard id, range checking, short-read handling, and exact byte counts.
- **FR-017-03**: Add first-class whole-matrix/tensor reader; keep row reads as helper mode only.
- **FR-017-04**: Define compressed/decoded/transient slab abstractions and stable `SlotId` lifecycle.
- **FR-017-05**: Support residency options **A**..**F** from authoritative trunk-inventory budget table:
  - A `compressed_all_trunk_residency`
  - B `decoded_all_trunk_residency`
  - C `decoded_attention_mla_only_residency`
  - D `decoded_output_head_only_residency`
  - E `decoded_hot_subset_candidate_output_head_plus_router_norms`
  - F `compressed_all_trunk_plus_decoded_hot_subset`
- **FR-017-06**: Reject memory-admission plans that require decoded-all on bounded hosts unless explicitly measured and approved in a separate gate.
- **FR-017-07**: Record telemetry buckets separately:
  - storage/read seconds
  - read request count
  - decode seconds
  - buffer/materialization seconds
  - backend build/import seconds
  - compute seconds
- **FR-017-08**: Add exact Rust dequant qualification for one or more required formats with malformed/truncated rejection.
- **FR-017-09**: Add a native bridge registration spike proving deterministic buffer ownership and teardown, including `newBufferWithBytesNoCopy` if available.
- **FR-017-10**: Implement a native-bridge-safe, no-Python ordinary inference topology for runtime scaffold operations.
- **FR-017-11**: Add `teacher_forced_validation` and `golden_strict` with stable mismatch classes:
  - `golden_identical`
  - `numerically_qualified_greedy_identical`
  - `numerically_qualified_greedy_divergent`
  - `numerically_failed`

## Validation boundary order

1. Slot and I/O API boundaries
2. Portable fixture validator
3. Exact decode lane (at least one format)
4. Whole-matrix I/O boundary
5. Residency-admission boundary on M2 Max budgets
6. Native bridge registration lifecycle
7. Runtime skeleton and GLM interfaces
8. Checkpoint-free ladder to representative logits

## Completion for first bounded milestone

- Spec kit updated with authoritative fact-driven contracts
- Portable fixture schema references trunk inventory and source checksums
- Allocator + I/O + residency interfaces in code/design with tests
- Whole-matrix request path defined as the normal contract
- One exact decode lane qualified and classified
- Bridge spike telemetry-backed and teardown-safe
- MLX boundary ADR drafted and reviewed
- checkpoint-free ladder reaches representative layer/logits boundary without checkpoint download
