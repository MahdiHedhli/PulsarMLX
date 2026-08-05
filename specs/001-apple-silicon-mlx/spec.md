# Feature Specification: Apple Silicon MLX Backend Bring-Up

**Feature Branch**: `main` (implemented and validated in focused commits)

**Created**: 2026-08-05

**Status**: Complete for the specified initial bounded bring-up

**Input**: Establish a correctness-first Apple Silicon backend using MLX,
progressing from the verified macOS build baseline through device and tensor
proofs, portable expert storage, quantized references, synthetic routed-MoE
validation, and the lowest-cost compatible real-model vertical slice without
changing the inherited Linux/CUDA behavior.

**Completion boundary**: All 78 tasks in this feature plan are complete. The
verified runtime depth is an evaluated Apple MLX device proof, seven tensor
fixtures, strict Q8_0 references, portable expert storage, synthetic routed-MoE,
and one 16-row Qwen3MoE Q8_0 gate-projection prefix. Full-checkpoint inference,
checkpoint routing, a complete expert/layer, generation, serving, giant-model
execution, performance, and Linux/CUDA runtime parity are not implied. Actual
records are indexed in
[`docs/validation/README.md`](../../docs/validation/README.md).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Establish a Trustworthy Apple Baseline (Priority: P1)

As a PulsarMLX developer, I can build and test the complete workspace on an
Apple Silicon host and obtain an explicit accelerator capability report, so I
know whether later evidence comes from the intended Apple execution device
rather than a silent CPU fallback.

**Why this priority**: Every later tensor, model, and performance result is
invalid if the workspace does not build or if the selected device is unknown.

**Independent Test**: From a clean checkout on a supported Apple Silicon host,
run the documented baseline commands and a device smoke probe. The workspace
passes its macOS-selected tests and the probe reports the actual selected
device or a bounded unsupported error.

**Acceptance Scenarios**:

1. **Given** a supported native Apple Silicon host, **When** the workspace
   baseline is run, **Then** all targets compile and all macOS-selected tests
   pass without requiring CUDA or Linux.
2. **Given** an available Apple accelerator, **When** the device smoke probe
   runs, **Then** the result identifies the selected MLX device and proves one
   evaluated operation completed there.
3. **Given** an unavailable or mismatched accelerator, **When** the probe runs,
   **Then** it returns an explicit unsupported result and does not record a
   successful GPU claim.

---

### User Story 2 - Prove Tensor and Quantized Operations (Priority: P2)

As a backend developer, I can execute deterministic tensor and quantized
reference cases with declared shapes, layouts, dtypes, and tolerances, so each
primitive has a correctness oracle before it is used in a model graph.

**Why this priority**: Plausible-looking tensor output can conceal orientation,
block-layout, dtype, and tail-handling errors that compound in routed models.

**Independent Test**: Run a fixture suite covering device transfer, embedding,
normalization, dense multiplication, routing primitives, and the first
supported quantized row operation. Every result is compared with an
independent scalar or trusted reference using a declared comparison policy.

**Acceptance Scenarios**:

1. **Given** deterministic tensor fixtures, **When** each supported primitive
   executes, **Then** output shape, dtype, values, and error bounds match the
   fixture contract.
2. **Given** invalid dimensions, byte counts, or partial quantization blocks,
   **When** a primitive is requested, **Then** it fails before execution with a
   bounded diagnostic.
3. **Given** a quantized fixture with an independent reference decoder,
   **When** the Apple operation runs, **Then** its decoded or multiplied output
   satisfies the recorded parity rule.

---

### User Story 3 - Validate Portable Expert Routing and Storage (Priority: P3)

As a model-runtime developer, I can resolve routed experts through a
backend-neutral storage contract and execute a synthetic routed-MoE layer, so
storage correctness and routing correctness are established without a giant
checkpoint.

**Why this priority**: Expert addressing, exact reads, route tie-breaking, and
weighted aggregation are the central correctness risks for oversized MoE
inference.

**Independent Test**: Use a small generated, licensed fixture with multiple
experts and shards. Exercise exact and invalid read ranges, deterministic
routing, repeated experts, ties, and weighted expert aggregation against a
scalar oracle.

**Acceptance Scenarios**:

1. **Given** valid expert ranges in one or more fixture shards, **When** reads
   are resolved, **Then** the returned bytes correspond exactly to the
   requested logical ranges.
2. **Given** a short, out-of-bounds, below-base, or shard-straddling read,
   **When** it is requested, **Then** the operation fails without exposing a
   partial payload as complete.
3. **Given** synthetic router and expert weights, **When** a routed layer runs,
   **Then** selected expert IDs, normalized weights, tie order, and final output
   match the independent oracle.

---

### User Story 4 - Execute the First Compatible Real-Model Slice (Priority: P4)

As an inference developer, I can run a legally accessible routed checkpoint
through one bounded documented slice and compare it with a trusted reference,
so synthetic evidence is connected to real weights without claiming a smaller
artifact, a deeper graph, or giant-model completion than was actually proved.

**Why this priority**: Real metadata, tensor names, layouts, tokenizer behavior,
and model graph interactions expose integration errors that synthetic fixtures
cannot.

**Independent Test**: Select the lowest-cost candidate that satisfies the
architecture, quantization, provenance, memory, and licensing criteria, record
its immutable identity outside Git, run one deterministic prompt through the
defined vertical slice, and compare intermediate or final outputs with a
trusted reference selected before execution.

**Acceptance Scenarios**:

1. **Given** a checkpoint with recorded provenance and supported tensors,
   **When** it is inspected, **Then** compatibility is decided explicitly
   before any execution claim.
2. **Given** the approved checkpoint and deterministic prompt, **When** the
   vertical slice runs, **Then** it produces the specified named intermediate
   tensor, logits, or token output and satisfies the declared correctness
   comparison.
3. **Given** an unsupported tensor, architecture detail, or memory requirement,
   **When** the model is loaded, **Then** execution stops with a compatibility
   record and does not fall through to an unvalidated interpretation.

---

### User Story 5 - Publish Reproducible Evidence and Boundaries (Priority: P5)

As a maintainer or reviewer, I can see exactly which Apple capabilities are
verified, planned, excluded, or blocked and can reproduce every benchmark, so
project claims remain trustworthy as the backend evolves.

**Why this priority**: Correct engineering evidence is only reusable when its
environment, inputs, commands, comparison rules, and exclusions are durable.

**Independent Test**: Review the compatibility matrix, validation guide,
benchmark record, and known-limitations document for traceability to commands,
inputs, and results; independently repeat one recorded validation case.

**Acceptance Scenarios**:

1. **Given** a completed validation case, **When** its documentation is
   reviewed, **Then** the commit, environment, input identity, command, actual
   result, warnings, and exclusions are present.
2. **Given** a performance comparison, **When** it is published, **Then**
   correctness passed first and all benchmark conditions required by the
   project constitution are recorded.
3. **Given** an unexecuted capability, **When** it appears in documentation,
   **Then** it is labeled planned, unsupported, or blocked rather than verified.

### Edge Cases

- The MLX package imports, but the selected device is CPU or the GPU operation
  is not actually evaluated.
- The shell is translated, the machine is Intel, or the selected process target
  does not match native Apple Silicon.
- Tensor orientation is valid by shape but transposed relative to GGUF storage.
- A quantized row has an invalid byte count, unsupported tail, non-finite scale,
  or unsupported tensor type.
- A logical expert range starts before a shard, ends after it, crosses a shard
  boundary, or returns fewer bytes than requested.
- Router scores tie exactly, repeat the same expert across tokens, contain
  non-finite values, or request more experts than exist.
- Unified-memory pressure prevents the bounded test case from completing.
- A candidate checkpoint lacks clear redistribution or access provenance.
- The trusted reference and Apple result exceed the declared tolerance.
- A shared change compiles on macOS but cannot yet be exercised on Linux/CUDA.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The project MUST retain a passing Apple Silicon workspace baseline
  for the exact all-target compile and no-fail-fast test commands.
- **FR-002**: The runtime MUST expose explicit backend selection and a
  capability report that identifies unavailable, available-but-unevaluated, and
  evaluated device states.
- **FR-003**: The Apple bring-up MUST preserve the inherited Linux/CUDA runtime
  path and MUST NOT change its default behavior implicitly.
- **FR-004**: Shared backend boundaries MUST describe stable model operations
  and owned data without exposing a required CUDA or Apple implementation
  mechanism to every backend.
- **FR-005**: A device smoke case MUST prove that one deterministic operation
  was evaluated on the selected MLX accelerator rather than merely allocated or
  queued.
- **FR-006**: Every Apple tensor operation admitted to a model graph MUST have
  an independent fixture, shape and dtype contract, and declared comparison
  rule.
- **FR-007**: Public tensor entry points MUST reject invalid shapes, dtypes,
  byte counts, and unsupported layouts before execution.
- **FR-008**: The first supported quantized operation MUST be strict Q8_0 row
  decode and matvec coverage with a scalar oracle independent of the Apple
  execution result.
- **FR-009**: Quantization support MUST be explicit per tensor role, block
  layout, divisibility rule, tail policy, and comparison tolerance.
- **FR-010**: Expert storage MUST use a backend-neutral logical-range contract
  that can represent split GGUF shards without requiring `io_uring`,
  `O_DIRECT`, or CUDA-addressable buffers.
- **FR-011**: Expert reads MUST enforce exact lengths and reject below-base,
  beyond-end, short, overflowing, and shard-straddling ranges.
- **FR-012**: Synthetic routed-MoE validation MUST cover deterministic top-k
  selection ordered by score descending and exact ties by ascending expert ID,
  normalized route weights, repeated experts, expert computation, and weighted
  aggregation; it MUST reject non-finite scores, zero top-k, and top-k greater
  than the expert count.
- **FR-013**: Apple memory evidence MUST distinguish model-file bytes, mapped
  virtual bytes, mapped resident bytes when observable, owned compressed bytes,
  decoded arrays, temporary current and peak arrays, MLX active/cache/peak
  gauges when available, process footprint when available, and separately
  budgeted caches and system headroom without summing overlapping gauges.
- **FR-014**: The first real checkpoint MUST be selected by documented size,
  architecture, tensor, quantization, provenance, and memory-fit criteria.
- **FR-015**: The real-model vertical slice MUST use a deterministic prompt and
  produce a bounded intermediate, logits, or token result that can be compared
  with a trusted reference.
- **FR-016**: Correctness comparisons MUST record the reference identity,
  compared values or hashes, tolerance, mismatch diagnostics, and actual result.
- **FR-017**: A committed compatibility matrix MUST distinguish synthetic,
  small real-model, and giant-model evidence for every claimed architecture and
  quantization.
- **FR-018**: Benchmark records MUST satisfy the reproducibility fields in the
  project constitution and MUST be rejected when correctness has not passed.
- **FR-019**: Custom Metal kernels and equivalent low-level Apple optimization
  MUST remain excluded until the corresponding MLX reference case passes.
- **FR-020**: The feature MUST expose unsupported and out-of-scope capabilities
  explicitly in user-facing and developer documentation.
- **FR-021**: Work MUST stop at a declared stop condition instead of bypassing
  device proof, correctness, provenance, compatibility, memory, or upstream
  regression gates.
- **FR-022**: Model weights, credentials, local caches, and private machine
  identifiers MUST NOT be committed.
- **FR-023**: Each completed slice MUST update its Spec Kit artifacts,
  validation guide, session log, compatibility evidence, and known limitations
  in the same bounded change.
- **FR-024**: The selected persistent MLX worker MUST use a versioned handshake,
  bounded messages, request IDs, protocol-only stdout, diagnostic stderr,
  structured outcomes for malformed or oversized input, timeouts, version
  mismatch and worker exit, and controlled shutdown as defined by the normative
  worker contract.

### Key Entities

- **Backend Capability Report**: Backend identity, selected device, availability,
  evaluation state, supported operations, and explicit exclusions.
- **Tensor Contract**: Logical shape, storage orientation, dtype, byte layout,
  validation rules, output contract, and comparison tolerance.
- **Expert Read Request**: Logical shard-aware offset and length with exact-read
  and ownership guarantees.
- **Quantization Compatibility Record**: Tensor role, quantization type, block
  layout, divisibility and tail rules, reference coverage, and backend status.
- **Validation Case**: Immutable input identity, command, environment, oracle,
  actual result, warnings, exclusions, and evidence location.
- **Model Compatibility Record**: Model identity, architecture, tensor and
  quantization coverage, execution depth, provenance, and support status.
- **Benchmark Record**: Correctness prerequisite plus the complete reproducible
  timing and environment context required by the constitution.

## Explicit Exclusions and Stop Conditions

### Known Exclusions

- Full giant-model inference is not required for the first real-model slice.
- Custom Metal kernels, manual graph fusion, and unsafe mapped-array aliasing are
  excluded until a correct MLX reference exists.
- Multi-device Apple execution, distributed inference, and production server
  exposure are excluded from initial bring-up.
- Refactoring the full Linux/CUDA engine into a universal trait hierarchy is
  excluded; only the smallest proven shared seams are in scope.
- Linux/CUDA performance changes and repository-wide formatting or Clippy
  cleanup are separate features.

### Mandatory Stop Conditions

Work on a slice MUST stop and be recorded as blocked when any of these applies:

- the intended MLX accelerator cannot be proven as the evaluated device;
- an independent tensor, quantization, routing, or model parity case fails;
- input shape, layout, tensor type, quantization, or shard bounds are unknown;
- no legally accessible checkpoint with adequate provenance is available;
- no immutable trusted-reference identity, reproducible command, and named
  comparison output can be selected before the real-model slice;
- the bounded model or fixture cannot fit within a conservative memory budget;
- a shared change regresses the verified macOS baseline or known Linux/CUDA
  validation;
- correctness evidence is absent for a proposed benchmark or optimization; or
- proceeding would require committing a secret, private identifier, or model
  weight.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The required all-target workspace check and no-fail-fast test run
  complete with 100% of macOS-selected tests passing.
- **SC-002**: The device smoke case reports one evaluated Apple accelerator
  operation and zero successful claims based solely on package import,
  allocation, or queued work.
- **SC-003**: Every tensor operation used by the first vertical slice passes all
  declared deterministic fixtures with zero shape, dtype, or bounds mismatches.
- **SC-004**: All supported quantized fixtures pass their declared scalar parity
  rules, while every malformed fixture is rejected before execution.
- **SC-005**: The synthetic routed-MoE suite matches the independent oracle for
  expert IDs, tie order, route weights, and final output across every declared
  scenario.
- **SC-006**: Expert-storage tests return exact bytes for every valid range and
  reject 100% of the declared invalid and short-read scenarios.
- **SC-007**: One provenance-recorded real routed checkpoint completes the
  documented deterministic vertical slice and satisfies its declared reference
  comparison.
- **SC-008**: Every architecture/quantization claim in project documentation maps
  to a compatibility record labeled synthetic, small real model, giant model,
  planned, unsupported, or blocked.
- **SC-009**: At least one bounded post-correctness benchmark is either recorded
  with every constitution-required field and a repeatable committed command, or
  explicitly marked not run with no performance claim; incomplete benchmark
  records are rejected.
- **SC-010**: The initial real-model proof is completed with zero custom Metal
  kernels and zero committed model-weight files or detected credentials.
- **SC-011**: Every change to shared parsing, tokenization, storage,
  quantization, or model semantics records Linux/CUDA validation before being
  labeled cross-platform-safe; without suitable hardware or CI it remains
  explicitly unverified and inherited selection/default behavior is unchanged.
- **SC-012**: Every storage, routed-MoE, and real-model evidence record contains
  all applicable memory gauges required by FR-013, marks unavailable gauges,
  records separate budgets/headroom, and does not publish a summed overlapping
  total.

### Completion Assessment

| Success criteria | Final result | Evidence boundary |
| --- | --- | --- |
| SC-001 | **Passed** | Local T077 and arm64 CI passed the exact Cargo gates; 171 active tests passed and one opt-in native smoke remained ignored by the ordinary workspace command. |
| SC-002 | **Passed** | The [device record](../../docs/validation/mlx-device-smoke.json) captures evaluated, synchronized MLX GPU work with no fallback. |
| SC-003–SC-004 | **Passed** | The [tensor record](../../docs/validation/mlx-tensor-fixtures.json) and strict Q8_0 tests cover all admitted primitive cases and malformed-input rejection. |
| SC-005 | **Passed** | The [synthetic record](../../docs/validation/synthetic-moe-v1.json) matches the independent routed-MoE oracle for the exact committed fixture. |
| SC-006 | **Passed** | The [portable-source record](../../docs/validation/portable-expert-source.json) plus its independent replay cover exact and invalid positional-read cases. |
| SC-007 | **Passed at bounded depth** | The pinned CPU reference and Apple result match for one 34,816-byte Qwen tensor prefix and 16 outputs; no deeper model claim follows. |
| SC-008 | **Passed** | The [compatibility matrix](../../docs/apple-silicon/COMPATIBILITY.md) uses exact independent evidence levels backed by the reviewer index. |
| SC-009 | **Passed by explicit no-result path** | The [benchmark record](../../docs/validation/benchmark-initial.json) is `not_run`, has zero samples, and makes no performance claim. |
| SC-010 | **Passed** | The real-model proof uses MLX, no custom Metal, external weights only, and sanitized staged reviews. |
| SC-011 | **Passed at the required boundary** | Inherited selection/defaults are unchanged; unavailable Linux/CUDA runtime evidence remains explicitly unverified, never cross-platform-safe. |
| SC-012 | **Passed** | Storage, synthetic, and bounded-model records retain applicable independent gauges and prohibit an overlapping summed total. |

FR-001 through FR-024 map to these outcomes through the finalized
requirement-to-stage table in [`plan.md`](plan.md). No mandatory stop condition
was bypassed and no constitutional exception was taken.

## Assumptions

- Phase-one support means a native arm64 Apple Silicon process, macOS 14 or
  newer, a native CPython interpreter supported by the pinned `mlx==0.32.0`
  arm64 wheel, and enough headroom for the bounded fixture.
- The existing GGUF parser, tokenizer, expert addressing plan, scalar
  quantization references, and Linux/CUDA path remain available as inherited
  context; reuse still requires focused validation at each new seam.
- MLX is integrated first through the persistent worker contract selected in
  research. A later native bridge may replace that mechanism only while
  preserving the same semantic and validation contracts.
- Synthetic fixtures will be generated deterministically and kept small enough
  for version control when their licensing and contents are reviewable.
- Real model files remain outside Git and are identified by immutable source,
  revision, filename, size, and checksum.
- A supported Linux/CUDA system or suitable CI will be needed before shared
  changes can receive runtime parity claims.
