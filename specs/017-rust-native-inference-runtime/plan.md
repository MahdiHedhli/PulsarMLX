# Implementation Plan: 017-rust-native-inference-runtime

**Branch**: `feat/017-rust-native-inference-runtime`
**Feature Spec**: `spec.md`
**Status**: Draft, bounded and inventory-driven

## Phase 0 — Reconciliation and repository lockstep

- Confirm branch state and `main` ancestry in `a948b68d9868a34b0cc9b00aacaa4ad2330b0f55`.
- Confirm Feature 016 evidence remains immutable.
- Ingest authoritative post-run and trunk inventory files as read-only inputs.

## Phase 1 — Spec and contracts (completed)

- `spec.md`, `plan.md`, `tasks.md`, `checklists/requirements.md`, and starter contracts are in place and aligned to authoritative metrics.

## Phase 2 — Portable differential fixture contract

- Add validator that reads fixture manifests and verifies:
  - source commit and checkpoint identity
  - tensor id, dimension, quantization, shard, and range
  - position/layer/offset metadata
  - payload hash and provenance
- Reuse previously generated public-safe samples when available; no private weight bytes in source.

Gate: manifest validation succeeds and rejects missing fields or unknown checksums.

## Phase 3 — Inventory-driven residency model

- Ingest `f016-gguf-trunk-inventory-0001.json` and derive slot classes from measured dimensions and use counts.
- Define slot-size classes from empirical trunk distributions and natural residency candidates.
- Model options A–F from Feature 016 derived table.

Gate: no hard-coded slot size constants are introduced without deriving from inventory.

## Phase 4 — Native slab allocator

- Design and implement allocator contract first; enforce bounded alignment, zeroing policy, and ownership.
- Add explicit failure modes and deterministic reuse behavior.
- Add occupancy, peak, request/allocate metrics.

Gate: deterministic stress tests confirm no UAF and safe pressure rejection.

## Phase 5 — Whole-matrix positional I/O

- Implement full-tensor/matrix positional read as the primary contract.
- Keep row reads as a test helper and compatibility mode.
- Add overflow checks, exact byte accounting, cancellation hooks, and request-count telemetry.

Gate: row-read amplification can be measured and improved with bounded whole-read path.

## Phase 6 — Telemetry split and attribution

- Add split telemetry fields for each of:
  - storage/read
  - decode
  - materialization
  - backend build/import
  - compute
- Ensure totals are traceable to boundary-level stages.

Gate: one-layer representative call produces non-overlapping attribution buckets.

## Phase 7 — Exact Rust decode qualification

- Qualify decoder boundary against existing Feature 016 anchors.
- Start with the required baseline formats and add malformed/truncated rejection tests.

Gate: at least one exact or numerically qualified format is committed with deterministic classification.

## Phase 8 — Residency + bridge implementation

- Build residency abstractions for compressed, decoded-hot, transient, and hybrid experiments.
- Add Objective-C++ bridge spike and command/teardown ordering.
- Demonstrate deterministic read/write ownership, registration, and destruction.

Gate: stable registration lifecycle with no silent fallback and explicit teardown order.

## Phase 9 — Native MLX boundary ADR

- Evaluate available options (C API, shim, ObjC++), and produce ADR for minimal-risk path.

Gate: recommendation published before adopting deeper MLX-native compute.

## Phase 10 — Runtime skeleton

- Add reusable runtime configuration, model identity, catalog, telemetry, cancellation, and execution traits.
- Keep GLM-specific math behind trait/plugin boundary.

Gate: rust-only initialization without requiring model execution service.

## Phase 11 — Checkpoint-free ladder with mode-aware validation

- Build ladder boundaries in order, with hard stop on any unsupported mismatch:
  1. byte-range tensor read
  2. one quant block decode
  3. complete matrix decode
  4. matrix/reference compare
  5. router boundary
  6. one expert projection
  7. complete expert
  8. top-8 + shared MoE
  9. representative MLA/dense
  10. representative layer
  11. final logits
- Apply `golden_strict` and `teacher_forced_validation` classes.

Gate: ladder advances only when previous boundary remains deterministic and bounded.

Current boundary: R6-R8 are composed checkpoint-free. The permanent exact-order
qualification scaffold is bit-identical to the independent R7 oracle. The
production MLX expert and top-8-plus-shared paths qualify under the separately
frozen Tier-B contract with fail-closed dispatch. R9 remains the next gate; no
checkpoint or M1 model time is admitted by this result.

## Final phase

- No 018 kernels are selected inside this feature.
- M1 Ultra parity is not requested until the ladder, residency budget gates, and bridge ownership are green.

## Phase 12 — Canonical runner contract

- Freeze the dedicated binary name, strict CLI, exit classes, validation modes,
  public-safe evidence schema, and atomic progress rules.
- Bind the runner to the production F017 adapter; prohibit Python orchestration,
  Linux/CUDA engine substitution, Feature 018 kernels, and hidden fallback.

Gate: contract/schema tests reject unknown options, duplicate keys, invalid
mode combinations, and incomplete lifecycle evidence.

## Phase 13 — Runner identity and storage vertical slice

- Add an immutable multi-shard manifest with exact shard identities.
- Compose the existing GGUF parser and positional reader into one production
  catalog/store with overflow, short-read, duplicate-name, and path-sanitizing
  failures.
- Implement `--dry-run`, `--checkpoint-identity-only`, and a fake split-GGUF
  fixture without checkpoint downloads.

Gate: the actual binary reaches R4 and records exact read/hash evidence from a
tiny public-safe multi-shard fixture.

## Phase 14 — Production adapter execution surface

- Bind `--adapter-preflight-only` to the actual production adapter.
- Add only typed MLX C operations required by the next semantic boundary,
  starting with shaped f32 import, matvec, bounded result extraction, and
  explicit synchronization.
- Record capability, dispatch, setup, compute, synchronization, and ownership
  telemetry with no silent fallback.

Gate: R5 projection fixture passes against its independent oracle on the native
Apple job and every lifecycle counter reconciles.

## Phase 15 — GLM-5.2 runtime composition

- Validate the complete 79-layer `glm-dsa` tensor map before execution.
- Compose router, expert, MLA/DSA, layer, final-output, and generation state in
  R6 through R11 order.
- Run a tiny synthetic multi-layer model through the actual runner binary at
  R12; no unit-only bypass satisfies this gate.

Gate: the checkpoint-free end-to-end runner produces its expected token,
complete evidence, cancellation behavior, and zero lifecycle state.

## Phase 16 — Local-only and M1 ladder

- Consume hash-bound, non-redistributed R13 boundary fixtures on the M2/M1
  development machines.
- Review and bank M1-A through M1-G separately before documenting the literal
  M1-H command.
- M1-H requires a new independent review and a fresh one-P1 authorization.

Gate: do not claim P1 readiness before R0-R14 and M1-A through M1-G are green.
