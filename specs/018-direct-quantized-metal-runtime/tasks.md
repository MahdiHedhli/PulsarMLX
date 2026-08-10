# Tasks: Direct-Quantized Metal Runtime

**Input**: Design documents from `specs/018-direct-quantized-metal-runtime/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `numerical-qualification-contract.md`, `contracts/`

**Tests**: Correctness-first TDD is required. Contract and native tests precede each implementation boundary.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel without changing the same files or depending on incomplete work
- **[Story]**: Maps the task to a specification user story

## Phase 1: Setup and Feature Freeze

**Purpose**: Freeze scope, branch, and selectively reused infrastructure before kernel work.

- [x] T001 Create and validate Feature 018 specification artifacts in `specs/018-direct-quantized-metal-runtime/`
- [x] T002 Commit and push the clean Feature 018 specification boundary from `specs/018-direct-quantized-metal-runtime/`
- [x] T003 Selectively import reviewed Feature 017 stable-slab commit `111ffb6d` into `crates/stream/` without touching the Feature 017 worktree
- [x] T004 Selectively import reviewed Feature 017 no-copy Metal registration commit `f2b1b130` into `crates/stream/` and resolve only mechanical branch conflicts
- [x] T005 Validate imported slab/registration ownership with `cargo test -p stream` and commit the infrastructure boundary

---

## Phase 2: Foundational Contracts

**Purpose**: Implement frozen classification, ABI validation, and evidence structures that block every direct-kernel claim.

**⚠️ CRITICAL**: No real candidate kernel result is observed before this phase is committed.

- [x] T006 [P] Add failing numerical-classification tests, including teacher-forced continuation after argmax divergence, in `scripts/research/tests/test_f018_numerical_contract.py`
- [x] T007 [P] Add failing evidence-contract/privacy/duplicate-key tests in `scripts/research/tests/test_f018_evidence.py`
- [x] T008 Implement immutable Feature 018 numerical classification in `scripts/research/f018_numerical_contract.py`
- [x] T009 Implement Feature 018 evidence parsing and semantic validation in `scripts/research/f018_evidence.py`
- [x] T010 Add failing packed-layout, shape, overflow, and malformed-request tests in `crates/stream/tests/iq2_xxs_metal.rs`
- [x] T011 Define the macOS-gated packed IQ2_XXS request/result and telemetry API in `crates/stream/src/apple_metal_bridge.rs`
- [x] T012 Validate all foundational tests, mark the frozen contract source identity, and commit the numerical/ABI boundary

**Checkpoint**: Tolerances and failure semantics are immutable before any candidate output.

---

## Phase 3: User Story 1 - Frozen Numerical Qualification (Priority: P1) 🎯 MVP

**Goal**: Classify exact, qualified same-greedy, qualified divergent, and failed candidates without checkpoint access.

**Independent Test**: Synthetic records exercise all four classes and every teacher-forced position remains evaluated after disagreement.

- [x] T013 [US1] Add deterministic signed-zero, non-finite, shape, route, and repeat-hash cases to `scripts/research/tests/test_f018_numerical_contract.py`
- [x] T014 [US1] Add a public-safe generated numerical-contract fixture in `fixtures/metal/iq2-xxs-numerical-v1.json`
- [x] T015 [US1] Validate deterministic fixture regeneration and exact frozen constants through `scripts/research/f018_numerical_contract.py`
- [x] T016 [US1] Commit and push the independently testable numerical-classification MVP

**Checkpoint**: Numerical classification works without Metal or checkpoint access.

---

## Phase 4: User Story 2 - Synthetic Direct Packed Execution (Priority: P1)

**Goal**: Execute packed IQ2_XXS weights directly on Metal with explicit ownership and no complete f32 weight matrix.

**Independent Test**: A generated packed matrix matches the Rust/Python scalar reference for 100 deterministic native executions and rejects malformed inputs before dispatch.

- [x] T017 [US2] Add deterministic IQ2_XXS grid/sign table generation and hashes in `crates/stream/src/iq2_xxs.rs`
- [x] T018 [US2] Add scalar Rust packed IQ2_XXS GEMV oracle and exact synthetic fixture generation in `crates/stream/src/iq2_xxs.rs`
- [x] T019 [US2] Add the smallest packed-IQ2_XXS f32-accumulating kernel and pipeline lifecycle in `crates/stream/src/apple_metal_bridge.mm`
- [x] T020 [US2] Implement Rust bridge dispatch, completion, telemetry, and zero-materialization accounting in `crates/stream/src/apple_metal_bridge.rs`
- [x] T021 [US2] Pass native deterministic, malformed, in-flight lifetime, and teardown tests in `crates/stream/tests/iq2_xxs_metal.rs`
- [x] T022 [US2] Record checkpoint-free synthetic evidence and generated review table under `docs/research/glm52/raw/` and `docs/research/glm52/tables/`
- [x] T023 [US2] Commit and push the synthetic direct-quantized Metal gate

**Checkpoint**: Rung A passes; no real checkpoint claim yet.

---

## Phase 5: User Story 2 - One Real Matrix and Warm Lifecycle (Priority: P1)

**Goal**: Bind one measured hotspot matrix and compare scalar, optimized reference, and direct Metal with setup separated from steady state.

**Independent Test**: One real IQ2_XXS gate matrix passes the frozen contract, 10 deterministic repeats, 3 warmups, and 30 retained samples.

- [x] T024 [US2] Add the fail-closed real matrix runner and immutable binding in `scripts/research/benchmark_glm52_iq2_xxs_metal.py`
- [x] T025 [US2] Add semantic validation for real matrix identity, raw samples, zero fallback, and zero full-f32 materialization in `scripts/research/tests/test_f018_evidence.py`
- [x] T026 [US2] Run the admitted real gate matrix and preserve raw evidence in `docs/research/glm52/raw/f018-iq2-xxs-gate-matrix-0001.json`
- [x] T027 [US2] Run the admitted real up matrix only after T026 passes and preserve `docs/research/glm52/raw/f018-iq2-xxs-up-matrix-0001.json`
- [x] T028 [US2] Generate deterministic matrix comparison tables with `scripts/research/analyze_glm52_iq2_xxs_metal.py`
- [x] T029 [US2] Commit and push the real matrix and repeated-warm lifecycle evidence

**Checkpoint**: Rungs B-E pass or the feature stops with a qualified negative/failing record.

---

## Phase 6: User Story 3 - Bounded Expert Ladder (Priority: P2)

**Goal**: Determine absolute expert/layer value without launching a full model prematurely.

**Independent Test**: Each eligible rung passes its scalar/NumPy/MLX reference comparison with setup, compute, memory, and claim scope recorded.

- [ ] T030 [US3] Integrate explicit direct IQ2_XXS gate/up selection into the bounded expert harness in `scripts/research/glm52_expert_cache_runtime.py`
- [ ] T031 [US3] Add a complete routed-expert candidate to `scripts/research/benchmark_glm52_routed_expert.py` and retain IQ3_XXS down on the qualified reference path
- [ ] T032 [US3] Run and commit one qualified routed expert record under `docs/research/glm52/raw/`
- [ ] T033 [US3] Add and run the eligible top-8 plus shared MoE rung through `scripts/research/benchmark_glm52_moe_profile.py`
- [ ] T034 [US3] Add and run the eligible representative complete-layer rung through `scripts/research/benchmark_glm52_complete_layer.py`
- [ ] T035 [US3] Generate before/after absolute-opportunity analysis and decide whether complete-layer improvement is material in `scripts/research/analyze_glm52_iq2_xxs_metal.py`
- [ ] T036 [US3] Commit and push the deepest qualified bounded rung

**Checkpoint**: Rungs F-H stop at the first divergence, unsafe resource state, or non-material design result.

---

## Phase 7: User Story 4 - Lifecycle, Evidence, and Optional P1 (Priority: P2)

**Goal**: Harden the deepest qualified path and admit no more than one P1 only if every gate passes.

**Independent Test**: CI-safe lifecycle/evidence tests pass; optional P1 is either admitted with exact `[9703,21615]` or explicitly deferred.

- [ ] T037 [P] [US4] Add command failure, cross-context registration, stale-generation, and repeated-teardown tests in `crates/stream/tests/iq2_xxs_metal.rs`
- [ ] T038 [P] [US4] Add reviewer-index, claims-ledger, and privacy checks for Feature 018 evidence in `scripts/research/tests/test_f018_evidence.py`
- [ ] T039 [US4] Evaluate P1 admission from the complete-layer evidence and document the decision in `docs/research/glm52/F018_OVERNIGHT_REVIEW.md`
- [ ] T040 [US4] If admitted, run one clean-source exact P1 to a fresh public-safe record; otherwise record the evidence-backed deferral in `docs/research/glm52/F018_OVERNIGHT_REVIEW.md`
- [ ] T041 [US4] Update `docs/research/glm52/CLAIMS_LEDGER.md` and `docs/research/glm52/REVIEWER_INDEX.md` with only verified Feature 018 claims

---

## Phase 8: Polish and Morning Review

**Purpose**: Validate the branch, publish the truthful boundary, and prepare expert review questions.

- [ ] T042 Create the complete morning handoff and Opus review questions in `docs/research/glm52/F018_OVERNIGHT_REVIEW.md`
- [ ] T043 Regenerate every Feature 018 table from committed raw data and verify deterministic output
- [ ] T044 Run full research, privacy, generated-artifact, Cargo workspace, native Metal/MLX, Spec Kit, and `git diff --check` gates
- [ ] T045 Review the staged diff for private paths, checkpoint bytes, credentials, donor code, and unsupported claims with `scripts/research/check_staged.sh`
- [ ] T046 Commit and push Feature 018 overnight closeout and confirm both Apple Silicon CI jobs
- [ ] T047 Send final acknowledged NTFY milestone to `Mahdi-Dev` with the deepest qualified boundary and exact next gate

---

## Dependencies and Execution Order

- Phase 1 precedes every implementation task.
- Phase 2 freezes numerical and ABI behavior before any candidate output.
- US1 classification is independently deliverable after Phase 2.
- US2 synthetic execution depends on Phase 2 and must precede real weights.
- Real matrix rung order is gate then up; neither can be bypassed.
- US3 proceeds expert → MoE → layer and stops at the first failed gate.
- US4 may admit P1 only after a material qualified complete-layer result.
- P2, golden-eight, second-format implementation, and all-format coverage are not tasks in this feature sprint.

## Parallel Opportunities

- T006 and T007 affect separate test modules.
- T037 and T038 harden separate Rust and evidence contracts after the ladder.
- All real checkpoint runs are sequential to keep resource state and evidence attribution unambiguous.

## Implementation Strategy

1. Publish the frozen spec and numerical contract.
2. Selectively reuse only the reviewed Feature 017 ownership commits.
3. Deliver checkpoint-free classification and synthetic Metal GEMV first.
4. Bind and qualify exactly one real matrix before integrating expert semantics.
5. Advance only through eligible bounded rungs.
6. Preserve a negative result if direct execution is not materially better.
7. Run at most one P1; never run P2 or golden-eight in this sprint.

## Stop Conditions

- Unexplained numerical divergence
- Unsafe buffer lifetime or teardown
- Critical or urgent memory pressure
- Metal behavior contradicting the frozen packed-layout assumptions
- Checkpoint/source/evidence integrity failure
- Operator-level architecture decision required

## Notes

- Every completed task is marked `[x]` only after its acceptance evidence passes.
- Focused commits follow independently testable boundaries.
- No private checkpoint path or weight bytes may enter version control.
- Feature 017 remains independent; only named clean commits may be reused.
