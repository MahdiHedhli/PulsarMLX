# Feature Specification: Real Expert Execution

**Feature Branch**: `003-real-expert-execution`

**Created**: 2026-08-06

**Status**: Draft

**Input**: User description: "Execute one real routed expert from the verified
Qwen checkpoint with exact tensor identity, exact expert selection, gate, up
projection, activation, down projection, weighted output, and independent CPU
parity. No generation."

## Background and baseline

Feature 001 verified a bounded Q8_0 **gate-projection prefix** for expert 0
(rows 0–15 only). Feature 002 verified the complete layer-0 **router** and
froze top-8 expert IDs for the genuine `ffn_norm-0` input. Feature 003 extends
that chain by executing **one full routed expert MLP** selected from Feature
002’s frozen top-8, producing a weighted expert contribution comparable to an
independent CPU oracle.

This feature does **not** execute other experts, aggregate a full top-8 MoE
block, run attention, produce logits, or generate tokens.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Admit one routed expert’s tensors (Priority: P1)

An engineer reuses the Feature 002 checkpoint and router-selected expert and
admits the exact GGUF tensors required for that expert’s full MLP (gate, up,
down) without downloading a new model.

**Why this priority**: Without immutable tensor identity there is no parity
claim.

**Independent Test**: Read-only inspection records exact names, offsets,
shapes, types, ranges, and hashes for the selected expert’s projections.

**Acceptance Scenarios**:

1. **Given** the immutable Qwen3-30B-A3B Q8_0 checkpoint and a frozen expert
   index from Feature 002 top-8, **When** expert tensors are inspected,
   **Then** each required projection has exactly one occurrence, the expected
   layout for that expert, and a stable encoded-range SHA-256.
2. **Given** a missing, aliased, or mutated expert tensor, **When** admission
   runs, **Then** execution stops with a retained fail-closed code and no
   partial success claim.

---

### User Story 2 - Independent CPU full-expert oracle (Priority: P1)

An engineer freezes a complete CPU oracle for one expert’s MLP on the genuine
`ffn_norm-0` row before any Apple result is trusted.

**Why this priority**: MLX results must compare against an independent oracle
that does not call the MLX path under test.

**Independent Test**: A CPU-only oracle (scalar and/or NumPy) computes gate,
up, activation, down, and routing-weight scaling and freezes hashes and
metrics without importing the MLX worker.

**Acceptance Scenarios**:

1. **Given** the frozen input row, expert weights, activation definition, and
   Feature 002 normalized routing weight for that expert, **When** the oracle
   runs twice, **Then** outputs and hashes are identical.
2. **Given** any attempt to import or call the MLX path from the oracle,
   **When** the oracle package is validated, **Then** the package is rejected.

---

### User Story 3 - Apple MLX single-expert execution with parity (Priority: P1)

An engineer runs one full expert MLP on Apple MLX GPU for the admitted expert
and proves numerical parity with the frozen CPU oracle.

**Why this priority**: This is the first real expert execution milestone on the
runtime roadmap.

**Independent Test**: An external Apple command evaluates gate, up, activation,
down, and weighted output; comparison metrics pass frozen tolerances with zero
ID/shape mismatches.

**Acceptance Scenarios**:

1. **Given** admitted tensors, frozen input, and frozen oracle, **When**
   `validate-expert` (or equivalent) runs on MLX GPU, **Then** the candidate
   reports evaluated, synchronized, no fallback, exact shapes, finite values,
   and comparison pass under frozen absolute/relative tolerances.
2. **Given** a failed comparison or resource admission failure, **When** the
   command exits, **Then** the failed or postponed evidence is retained
   externally and no claim is promoted.

---

### User Story 4 - Publishable evidence and claims (Priority: P2)

An engineer publishes sanitized raw evidence, regenerates tables/figures, and
records a single verified claim for one expert full-MLP parity.

**Why this priority**: Publication is required before Feature 004 may begin.

**Independent Test**: Package verification accepts the raw record, claim, and
reviewer index; clean-checkout reproduction matches promotion identity.

**Acceptance Scenarios**:

1. **Given** a passing sanitized candidate, **When** raw evidence is
   published append-only, **Then** package verification and claims ledger
   reference only that evidence.
2. **Given** publication artifacts, **When** a clean-checkout reproduction
   reruns the authorized command, **Then** promotion identity matches.

### Edge Cases

- Resource admission (load, memory pressure, thermal) fails before checkpoint
  access.
- Expert index is not in Feature 002 frozen top-8.
- Q8_0 block boundaries or expert packing yield short reads or wrong ranges.
- Non-finite intermediate activations.
- Oracle/MLX orientation mismatch (row/column major).
- Operator pauses local inference (NTFY) required before model access.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: MUST reuse Feature 001/002 immutable checkpoint identity
  (filename, size, SHA-256, repository, revision) without automatic download.
- **FR-002**: MUST select exactly one expert index from Feature 002’s frozen
  single-row top-8 for the genuine `ffn_norm-0` case (default: rank-0 expert
  `114` unless admission proves a safer explicit override with equal
  evidence).
- **FR-003**: MUST admit exact tensor identities for that expert’s gate, up,
  and down projections from the checkpoint.
- **FR-004**: MUST use the frozen genuine `ffn_norm-0` input row corresponding
  to Feature 002 case `qwen3moe-layer0-router-token0-row0-v1`.
- **FR-005**: MUST compute the full expert MLP: gate projection, up
  projection, defined activation (SiLU/SwiGLU as required by Qwen3MoE
  contract), down projection.
- **FR-006**: MUST scale the expert output by the Feature 002 frozen
  normalized routing weight for that expert and row.
- **FR-007**: MUST freeze an independent CPU oracle that does not import or
  call the MLX path under test.
- **FR-008**: MUST compare Apple MLX outputs to the oracle under frozen
  absolute-plus-relative tolerances with zero allowed mismatches unless a new
  explicit amendment is recorded.
- **FR-009**: MUST require evaluated + synchronized MLX GPU with no fallback.
- **FR-010**: MUST retain failed, aborted, and postponed attempts externally
  without mutating them into passes.
- **FR-011**: MUST publish append-only public-safe raw evidence, regenerate
  tables/figures, update claims ledger and reviewer index, and support
  clean-checkout reproduction.
- **FR-012**: MUST notify NTFY topic `Mahdi-Dev` before first model access for
  this feature and on completion or exact blocker.
- **FR-013**: MUST keep CI-safe fixture-only validation green without the
  external checkpoint.

### Key Entities

- **Routed expert admission**: expert index, tensor names, offsets, shapes,
  types, encoded hashes.
- **Expert MLP result**: gate, up, activation, down, and weighted vectors with
  hashes and comparison metrics.
- **CPU oracle freeze**: independent reference for the same identities.
- **Evidence record**: sanitized public experiment envelope for one expert.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: One admitted real expert’s full MLP completes on Apple MLX with
  comparison pass rate 100% against the frozen CPU oracle under frozen
  tolerances.
- **SC-002**: Zero mismatches on vector length and expert identity; max
  absolute and relative errors recorded for every compared element.
- **SC-003**: At least one clean-checkout reproduction matches promotion
  identity (checkpoint, tensors, input, oracle, output hashes).
- **SC-004**: Public package verification accepts the raw evidence and exactly
  one new verified claim for single-expert full-MLP parity.
- **SC-005**: No claim asserts multi-expert aggregation, complete MoE block,
  layer output, logits, tokens, generation, serving, or performance.

## Assumptions

- Qwen3MoE expert FFN uses the SwiGLU-style gate/up/down pattern already
  assumed by Feature 001 inventory (`expert_feed_forward_length` 768).
- Feature 002 frozen input, top-8, and normalized weights remain authoritative.
- Default expert is rank-0 of single-row top-8 (`114`).
- Tolerances start from Feature 001/002 frozen absolute/relative 5e-4 unless
  expert Q8_0 numerics require a documented amendment before any Apple pass.
- External model path remains operator-supplied; CI remains fixture-only.

## Out of Scope

- Executing more than one expert.
- Weighted aggregation of top-8 experts (Feature 004).
- Complete MoE block, attention, residual, layer norm chain (Features 005–006).
- Logits, sampling, generation, serving.
- Benchmark or tokens/sec claims.
- Linux/CUDA runtime revalidation.
- GLM or other checkpoints.
