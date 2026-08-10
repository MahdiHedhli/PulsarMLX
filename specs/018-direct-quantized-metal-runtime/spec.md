# Feature Specification: Direct-Quantized Metal Runtime

**Feature Branch**: `feat/018-direct-quantized-metal-runtime`

**Created**: 2026-08-09

**Status**: Draft

**Input**: Establish a correctness-first direct-quantized Apple GPU path for the measured GLM-5.2 IQ2_XXS routed gate/up hotspot, with bounded qualification, explicit fallback, and evidence before any full-model performance claim.

## Background

The Feature 016 MoE sprint established an exact two-token GLM-5.2 boundary and
measured routed expert decode as the largest recoverable warm-stack cost. The
measured model attributes 55.750817 seconds of a warm stack to IQ2_XXS routed
gate/up decode across 1,184 matrix touches. This feature accepts that target
selection and asks whether packed IQ2_XXS weights can be used directly without
first materializing a complete decoded f32 matrix.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Frozen numerical qualification (Priority: P1)

A runtime engineer can evaluate a candidate path against an independently
understandable reference using classifications and tolerances that were fixed
before real-kernel results were observed.

**Why this priority**: A faster path has no value if its numerical result is
classified after the fact or if token divergence is hidden by stopping the
comparison early.

**Independent Test**: A synthetic candidate and deliberately divergent
candidate can be classified without checkpoint access, including continued
teacher-forced validation after an argmax disagreement.

**Acceptance Scenarios**:

1. **Given** identical candidate and reference outputs, **When** qualification
   runs, **Then** the result is `golden_identical` with exact hashes retained.
2. **Given** numerically acceptable but non-identical outputs with the same
   greedy choices, **When** qualification runs, **Then** the result is
   `numerically_qualified_greedy_identical`.
3. **Given** numerically acceptable outputs with an argmax disagreement,
   **When** teacher-forced qualification runs, **Then** later frozen positions
   are still evaluated and the result is
   `numerically_qualified_greedy_divergent`.
4. **Given** a non-finite, out-of-tolerance, identity-mismatched, fallback, or
   nondeterministic result, **When** qualification runs, **Then** the result is
   `numerically_failed` and no deeper performance claim is admitted.

---

### User Story 2 - Direct packed-matrix execution (Priority: P1)

A runtime engineer can execute one admitted IQ2_XXS gate or up projection from
its packed checkpoint representation, compare it to both scalar and optimized
reference paths, and prove that a successful candidate contains no hidden CPU
fallback or complete f32 weight materialization.

**Why this priority**: The single real matrix is the smallest boundary that
tests the measured target without conflating expert activation, aggregation,
or full-model behavior.

**Independent Test**: One bound real matrix and one fixed activation produce a
qualified output with recorded identity, memory, first-use, and steady-state
measurements.

**Acceptance Scenarios**:

1. **Given** a valid admitted packed matrix and activation, **When** the direct
   path executes, **Then** it produces a classified output and separates read,
   registration, compilation, dispatch, execution, synchronization, and total
   time.
2. **Given** truncated, misaligned, wrong-shape, wrong-quantization, or stale
   checkpoint input, **When** execution is requested, **Then** it fails before
   dispatch without substituting another backend.
3. **Given** a supported matrix is executed repeatedly, **When** steady-state
   samples are collected, **Then** every raw sample is retained and first-use
   setup remains separate from warm execution.

---

### User Story 3 - Bounded expert ladder (Priority: P2)

A model researcher can advance the qualified direct path through gate, up, one
complete routed expert, one top-8 plus shared block, and one representative
complete layer, stopping at the first ineligible boundary.

**Why this priority**: A matrix microbenchmark alone cannot establish useful
expert, layer, or token impact.

**Independent Test**: Each rung can be executed and reviewed separately with a
reference comparison, resource record, explicit claim boundary, and rollback
path.

**Acceptance Scenarios**:

1. **Given** the previous rung qualifies, **When** the next rung executes,
   **Then** its numerical class, memory, setup, steady-state time, and reference
   comparison are retained before deeper work begins.
2. **Given** a rung diverges or fails lifecycle safety, **When** the result is
   reviewed, **Then** the ladder stops with the failing evidence preserved.
3. **Given** a representative complete layer improves materially and remains
   qualified, **When** the optional full-stack gate is considered, **Then** at
   most one exact first-token run may be admitted from a clean immutable source.

---

### User Story 4 - Reviewable lifecycle and evidence (Priority: P2)

A maintainer can inspect ownership, teardown, telemetry, fallback behavior,
and public evidence without checkpoint access or private machine paths.

**Why this priority**: Direct device access is only maintainable when buffer
lifetimes and failures are explicit and CI can validate the evidence contract.

**Independent Test**: Checkpoint-free tests exercise allocation, reuse,
teardown, malformed requests, classification, evidence parsing, and privacy.

**Acceptance Scenarios**:

1. **Given** a registered buffer is in flight, **When** its host owner would
   otherwise be released, **Then** ownership keeps the memory valid until
   completion and teardown occurs exactly once afterward.
2. **Given** a candidate is unsupported or rejected, **When** the caller uses
   the explicit reference mode, **Then** the reference path remains available
   and the fallback is reported rather than hidden.
3. **Given** committed public evidence, **When** CI validation runs, **Then** it
   rejects private paths, missing provenance, duplicate keys, unsupported
   claims, and summaries that disagree with raw samples.

### Edge Cases

- Packed input is truncated by one byte, contains a partial block, or exceeds
  the declared matrix range.
- Matrix dimensions are zero, overflow address arithmetic, or contain a tail
  not covered by the admitted layout.
- Host memory is not page aligned or is released while device work is pending.
- Device, command queue, compilation, command buffer, or synchronization fails.
- Candidate output contains NaN, infinity, nondeterministic bits, or a signed
  zero discrepancy relevant to an exact classification.
- Greedy argmax diverges even though boundary error metrics remain inside the
  frozen numerical envelope.
- Memory pressure becomes critical or urgent during a bounded test.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-018-001**: The feature MUST freeze and version four mutually exclusive
  numerical classifications before observing a real candidate failure:
  `golden_identical`, `numerically_qualified_greedy_identical`,
  `numerically_qualified_greedy_divergent`, and `numerically_failed`.
- **FR-018-002**: Teacher-forced validation MUST continue across all committed
  positions after candidate argmax disagreement, while the divergence remains
  explicit and ineligible for an exact-greedy claim.
- **FR-018-003**: The first target MUST remain IQ2_XXS routed gate/up unless new
  committed measurements invalidate the Feature 016 opportunity ranking.
- **FR-018-004**: A successful direct-quantized execution MUST consume packed
  weights without complete f32 matrix materialization and MUST report zero
  hidden CPU fallback.
- **FR-018-005**: Every real matrix record MUST bind source commit, checkpoint
  set identity, immutable revision, tensor name, layer, expert, role,
  quantization, dimensions, compressed byte range, activation hash, and
  reference output hash.
- **FR-018-006**: The candidate MUST retain the scalar and optimized reference
  paths as independently selectable oracles and rollback paths.
- **FR-018-007**: Timing MUST distinguish storage read, buffer registration,
  first-use compilation, dispatch, device execution, synchronization, and
  steady-state total where the platform exposes them honestly.
- **FR-018-008**: The implementation MUST reject malformed, truncated,
  overflowing, unsupported, or identity-mismatched inputs before dispatch.
- **FR-018-009**: The implementation MUST provide explicit ownership and
  teardown rules that prevent device access after host-memory release and
  prevent release while work is in flight.
- **FR-018-010**: The bounded ladder MUST advance in order: synthetic block,
  one real matrix, repeated warm matrix, gate, up, complete routed expert,
  top-8 plus shared block, representative complete layer, and optional P1.
- **FR-018-011**: A deeper rung MUST NOT begin until the preceding rung is
  numerically qualified, resource-safe, committed, and reproducible.
- **FR-018-012**: Performance comparisons MUST retain every raw sample,
  separate setup from steady state, and compare absolute recoverable seconds
  against the current optimized reference.
- **FR-018-013**: A second quantization target MUST NOT begin unless committed
  end-to-end evidence shows it is the next largest recoverable opportunity.
- **FR-018-014**: Public evidence and CI fixtures MUST be checkpoint-free where
  possible and MUST contain no checkpoint bytes, credentials, private paths,
  hostnames, or device-specific secret identifiers.
- **FR-018-015**: The feature MUST preserve inherited Linux and CUDA behavior
  and MUST keep Apple-only execution behind an explicit capability boundary.
- **FR-018-016**: At most one P1 run may occur, and only after a materially
  faster qualified complete-layer result from a clean committed source with
  normal memory pressure and no competing inference.
- **FR-018-017**: P2, golden-eight, all-format coverage, speculative decoding,
  distributed inference, serving, and product work are out of scope.

### Key Entities

- **Qualification Contract**: Versioned classifications, frozen tolerances,
  deterministic rules, teacher-forced continuation behavior, and stop gates.
- **Packed Matrix Binding**: Immutable relationship among source, checkpoint,
  tensor identity, packed byte range, dimensions, activation, and reference.
- **Device Buffer Lease**: Host owner, registered device view, in-flight state,
  completion fence, and teardown outcome.
- **Kernel Attempt**: One configuration and its classification, telemetry,
  resource observations, failures, and raw timing samples.
- **Ladder Rung**: Independently reviewable boundary with prerequisites,
  acceptance result, claim scope, and next eligible gate.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-018-001**: All four numerical classes are exercised by checkpoint-free
  tests, including continued teacher-forced validation after disagreement.
- **SC-018-002**: The synthetic packed-input boundary completes at least 100
  deterministic repetitions with no output drift, lifecycle error, or hidden
  fallback.
- **SC-018-003**: One real IQ2_XXS gate/up matrix completes at least 3 warmups
  and 30 retained steady-state samples with a frozen numerical classification
  and all identity fields present.
- **SC-018-004**: The direct candidate demonstrates that complete f32 weight
  materialization is absent through explicit byte accounting and lifecycle
  telemetry.
- **SC-018-005**: Every admitted rung reports setup, steady-state, memory, and
  reference comparison separately and can be regenerated from committed raw
  data with one documented command.
- **SC-018-006**: The implementation either materially reduces the measured
  absolute gate/up boundary time or records a qualified negative result without
  promoting it to a production optimization.
- **SC-018-007**: Checkpoint-free CI, privacy validation, relevant native tests,
  workspace checks, and workspace tests pass at every published boundary.
- **SC-018-008**: The morning review identifies the deepest qualified boundary,
  unresolved numerical and lifetime risks, whether P1 ran, and one exact next
  gate without claiming P2, golden-eight, production readiness, or general
  token throughput.

## Assumptions

- The Mac Studio is an Apple M1 Ultra with sufficient resources for bounded
  local checkpoint fixtures, and memory admission remains fail-closed.
- The Feature 016 scalar/NumPy/MLX path remains the independent research oracle
  and rollback path.
- Feature 017 owns the shipping runtime and slab-lifecycle work. Feature 018 may
  consume a reviewed ownership contract or keep an explicit integration seam,
  but does not merge unrelated Feature 017 work.
- A direct candidate may be numerically rather than bit identical because
  parallel accumulation order can legitimately differ. Its classification is
  determined only by the frozen contract.
- No direct-kernel speed claim is valid until synchronized device execution and
  setup/steady-state boundaries are measured separately.

## Out of Scope

- Complete support for every GGUF quantization format
- A golden-eight or P2 performance run
- Speculative decoding or distributed inference
- Server, packaging, or product-surface implementation
- Replacing the Python/NumPy reference oracle
- Wholesale merge of the Feature 017 branch
