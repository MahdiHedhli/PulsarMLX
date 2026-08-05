# Design Readiness Checklist: Apple Silicon MLX Backend Bring-Up

**Purpose**: Test the quality, traceability, consistency, and measurability of
the written requirements and design before implementation. These questions
evaluate the specification, not whether the software has been built.

**Created**: 2026-08-05

**Audience**: Maintainers reviewing the pre-implementation design

**Depth**: Release-gate quality for the first bounded implementation slice

## Requirement Coverage

- [x] CHK001 Does every requested bring-up area have a functional requirement,
  acceptance scenario, or measurable outcome? [Spec §User Scenarios; §FR-001–FR-024; §SC-001–SC-012]
- [x] CHK002 Is the exact macOS compile/test baseline specified without
  replacing actual results with an expected test count? [Spec FR-001, SC-001; Quickstart §2]
- [x] CHK003 Is device success defined as explicit evaluated and synchronized
  work rather than package import or allocation? [Spec FR-002, FR-005, SC-002; Worker Contract §Worker hello, §tensor_probe]
- [x] CHK004 Are tensor shape, orientation, dtype, byte-count, synchronization,
  and comparison requirements all stated? [Spec FR-006–FR-009; Tensor Contract §Tensor descriptor]
- [x] CHK005 Are valid and invalid exact expert-read requirements both covered?
  [Spec FR-010–FR-011, SC-006; Expert Contract §Exact read semantics]
- [x] CHK006 Are route ordering, invalid score/top-k handling, aggregation, and
  repeat-expert behavior explicit? [Spec FR-012, SC-005; Tensor Contract §Router contract]
- [x] CHK007 Are all requested memory categories, overlap warnings, budgets, and
  unavailable-gauge behavior covered? [Spec FR-013, SC-012; Data Model §BenchmarkRecord]
- [x] CHK008 Are model selection, provenance, compatibility, real output depth,
  and trusted-reference gates covered? [Spec FR-014–FR-017; §Mandatory Stop Conditions; Data Model §ModelCompatibilityRecord]
- [x] CHK009 Are reproducible benchmark requirements non-vacuous and gated by
  correctness? [Spec FR-018, SC-009; Evidence Contract §Benchmark record]
- [x] CHK010 Are documentation, secrets/weights, exclusions, stop conditions,
  and incremental evidence requirements explicit? [Spec FR-019–FR-023; §Known Exclusions; §Mandatory Stop Conditions]

## Clarity and Bounded Meaning

- [x] CHK011 Is “supported host” concretely bounded by architecture, macOS,
  Python, wheel, and headroom prerequisites? [Spec §Assumptions; Research §Decision 1]
- [x] CHK012 Are unavailable, available-but-unevaluated, and evaluated device
  states mutually distinguishable? [Spec FR-002; Data Model §BackendCapabilityReport]
- [x] CHK013 Is “exact read” defined with half-open boundaries, exact payload
  length, ownership, and no straddling ambiguity? [Expert Contract §Exact read semantics]
- [x] CHK014 Is “Q8_0 support” bounded by tensor role, block layout, divisibility,
  strict byte count, malformed input, and parity depth? [Spec FR-008–FR-009; Tensor Contract §Q8_0 encoded layout]
- [x] CHK015 Is real-model verification limited to the named intermediate,
  logits, or token boundary actually compared? [Spec US4, FR-015, SC-007; Quickstart §10]
- [x] CHK016 Is synthetic evidence explicitly prevented from implying real or
  giant checkpoint support? [Spec US3, FR-017, SC-008; Evidence Contract §Compatibility matrix]
- [x] CHK017 Are platform preservation claims explicitly withheld when
  Linux/CUDA validation is unavailable? [Spec FR-003, SC-011; Constitution II]
- [x] CHK018 Are mapped virtual memory, resident pages, MLX allocator numbers,
  and process footprint prevented from becoming a false summed total? [Spec FR-013, SC-012; Research §Decision 5]

## Consistency Across Artifacts

- [x] CHK019 Does the plan select the same MLX version, worker boundary, first
  quant type, model candidate, and CI runner as research? [Plan §Technical Context, §Phase 0; Research Decisions 1–7]
- [x] CHK020 Do the spec, plan, data model, and contracts agree that worker
  failure never silently falls back to CPU? [Spec FR-002, FR-005; Plan §Constraints; Worker Contract §Selection rules]
- [x] CHK021 Do the design artifacts consistently preserve the inherited
  Linux fetcher and runtime defaults? [Spec FR-003; Plan §Summary; Expert Contract §Linux preservation]
- [x] CHK022 Do all artifacts consistently select Q8_0 before Q4/K-quant
  expansion for the current candidate? [Spec FR-008; Plan §Phase 0; Research §Decision 6; Tensor Contract]
- [x] CHK023 Do all artifacts distinguish a verified intermediate graph depth
  from end-to-end inference? [Spec US4; Plan §Delivery Sequence; Quickstart §10; Backend Design §Stage 7]
- [x] CHK024 Is the trusted real-model reference explicitly deferred as a
  mandatory pre-US4 gate rather than falsely described as resolved? [Spec §Mandatory Stop Conditions; Research §Deferred Gates; Quickstart §10]

## Measurability and Evidence

- [x] CHK025 Does each success criterion specify a count, required record,
  exact state, or explicit no-claim outcome that a reviewer can inspect? [Spec SC-001–SC-012]
- [x] CHK026 Are actual command, commit, sanitized environment, immutable input,
  oracle, tolerances, warnings, exclusions, and result required in evidence?
  [Spec FR-016; Data Model §ValidationCase; Evidence Contract §Validation record]
- [x] CHK027 Are comparison tolerances chosen before results and accompanied by
  bounded mismatch diagnostics? [Tensor Contract §Comparison policy; Evidence Contract §Correctness comparison]
- [x] CHK028 Are compatibility states explicit at scalar, MLX fixture,
  synthetic, real-checkpoint, giant-model, and serving depths? [Spec FR-017, SC-008; Evidence Contract §Compatibility matrix]
- [x] CHK029 Can a failed or blocked validation remain durable without being
  misreported as verified? [Data Model §EvidenceStatus; Evidence Contract §Claim rule]
- [x] CHK030 Is benchmark publication rejected or withheld when correctness or
  required reproducibility fields are absent? [Spec FR-018, SC-009; Constitution VII; Evidence Contract §Benchmark record]

## Scenario and Failure Coverage

- [x] CHK031 Do acceptance cases cover both supported and unsupported device
  paths? [Spec US1 Acceptance 2–3]
- [x] CHK032 Do tensor cases cover successful parity and pre-execution malformed
  input rejection? [Spec US2 Acceptance 1–3]
- [x] CHK033 Do expert cases cover success, invalid/short range behavior, and
  deterministic routed output? [Spec US3 Acceptance 1–3]
- [x] CHK034 Do real-model cases cover compatibility admission, bounded parity,
  and unsupported/memory stop behavior? [Spec US4 Acceptance 1–3]
- [x] CHK035 Do documentation cases prevent planned or unrun work from appearing
  as verified capability or benchmark evidence? [Spec US5 Acceptance 1–3]
- [x] CHK036 Are worker malformed messages, version mismatch, timeout, exit, and
  shutdown outcomes required without prescribing secret-bearing diagnostics?
  [Spec FR-024; Worker Contract §Error codes, §Contract validation]

## Dependencies and Stop Gates

- [x] CHK037 Is each deferred dependency assigned to a stage before it becomes
  blocking? [Plan §Delivery Sequence; Research §Deferred Gates]
- [x] CHK038 Does the real-model task stop before download/execution when
  provenance, oracle, compatibility, disk, or memory evidence is missing?
  [Spec §Mandatory Stop Conditions; Quickstart §10]
- [x] CHK039 Does optimization remain downstream of a correct MLX reference and
  measured bottleneck? [Spec FR-019; Constitution VI–VII; Plan §Delivery Sequence]
- [x] CHK040 Can the first baseline/device story be implemented and validated
  independently of storage, MoE, and real-model work? [Spec US1; Plan §Delivery Sequence]

## Review Result

All 40 design-quality questions were answered from explicit committed text.
The checklist does not claim implementation, MLX installation, device
execution, model compatibility, Linux/CUDA parity, or performance. Reopen the
relevant item if a later artifact changes its cited requirement or contract.
