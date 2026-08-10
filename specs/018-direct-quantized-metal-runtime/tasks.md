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

- [x] T030 [US3] Integrate explicit direct IQ2_XXS gate/up selection into the bounded expert harness in `scripts/research/glm52_expert_cache_runtime.py`
- [x] T031 [US3] Add a complete routed-expert candidate in `scripts/research/benchmark_glm52_routed_expert_metal.py` and retain IQ3_XXS down on the qualified reference path
- [x] T032 [US3] Run and commit one qualified routed expert record under `docs/research/glm52/raw/`
- [x] T033 [US3] Add and run the eligible top-8 plus shared MoE rung through the bounded `scripts/research/benchmark_glm52_moe_metal.py` profile
- [x] T034 [US3] Add and run the eligible representative complete-layer rung through `scripts/research/benchmark_glm52_complete_layer_metal.py`
- [x] T035 [US3] Generate before/after absolute-opportunity analysis and decide that the 0.742-second (30.5%) complete-layer median reduction is material in `scripts/research/analyze_glm52_iq2_xxs_metal.py`
- [x] T036 [US3] Commit and push the deepest qualified bounded rung

**Checkpoint**: Rungs F-H stop at the first divergence, unsafe resource state, or non-material design result.

---

## Phase 7: User Story 4 - Lifecycle, Evidence, and Optional P1 (Priority: P2)

**Goal**: Harden the deepest qualified path and admit no more than one P1 only if every gate passes.

**Independent Test**: CI-safe lifecycle/evidence tests pass; optional P1 is either admitted with exact `[9703,21615]` or explicitly deferred.

- [x] T037 [P] [US4] Add command failure, cross-context registration, stale-generation, and repeated-teardown tests in `crates/stream/tests/iq2_xxs_metal.rs`
- [x] T038 [P] [US4] Add reviewer-index, claims-ledger, and privacy checks for Feature 018 evidence in `scripts/research/tests/test_f018_evidence.py`
- [x] T039 [US4] Evaluate P1 admission from the complete-layer evidence and document the decision in `docs/research/glm52/F018_OVERNIGHT_REVIEW.md`
- [x] T040 [US4] If admitted, run one clean-source exact P1 to a fresh public-safe record; otherwise record the evidence-backed deferral in `docs/research/glm52/F018_OVERNIGHT_REVIEW.md`
- [x] T041 [US4] Update `docs/research/glm52/CLAIMS_LEDGER.md` and `docs/research/glm52/REVIEWER_INDEX.md` with only verified Feature 018 claims

---

## Phase 8: Polish and Morning Review

**Purpose**: Validate the branch, publish the truthful boundary, and prepare expert review questions.

- [x] T042 Create the complete morning handoff and Opus review questions in `docs/research/glm52/F018_OVERNIGHT_REVIEW.md`
- [x] T043 Regenerate every Feature 018 table from committed raw data and verify deterministic output
- [x] T044 Run full research, privacy, generated-artifact, Cargo workspace, native Metal/MLX, Spec Kit, and `git diff --check` gates
- [x] T045 Review the staged diff for private paths, checkpoint bytes, credentials, donor code, and unsupported claims with `scripts/research/check_staged.sh`
- [x] T046 Commit and push Feature 018 overnight closeout and confirm both Apple Silicon CI jobs
- [x] T047 Send final acknowledged NTFY milestone to `Mahdi-Dev` with the deepest qualified boundary and exact next gate

---

## Phase 9: Post-Opus Contract and Compiler Qualification

**Purpose**: Close the required review fixes before admitting another quantized format.

- [x] T048 Freeze the same-order scalar/NumPy oracle, Tier-B MLX role, scaffold status, and future parallel-kernel classification in `numerical-qualification-contract.md`
- [x] T049 Pin qualification compilation to `fastMathEnabled = NO` and an explicit Metal language version, expose those settings in native telemetry, and add failing-then-passing assertions
- [x] T050 Re-run the synthetic IQ2_XXS fixtures under strict compilation and record whether the sequential scaffold is `golden_identical` or Tier-B qualified without changing tolerances
- [x] T051 Inventory every explicit P1 reference dispatch with layer, expert, tensor role/name, quantization, shape, and reason code
- [x] T052 Make validation-mode unexpected fallback/error a hard failure while retaining explicit, observable production-policy fallback as a separate state

---

## Phase 10: In-Flight Ownership and Lookup Placement

**Purpose**: Make registration destruction, slot reuse, and immutable lookup ownership mechanically safe through command completion.

- [x] T053 Add explicit native in-flight registration accounting and completion-handler retention for every submitted command
- [x] T054 Add submit/wait/destroy, attempted early destroy/reuse, repeated lifecycle, error/cancellation, and generation-protection tests
- [x] T055 Evaluate IQ2 grid/sign tables in Metal constant address space and retain the change only if exactness and bounded safety pass
- [x] T056 Document the generic Feature 017 lifecycle/telemetry boundary versus Feature 018 format-specific kernel ownership

---

## Phase 11: Decisive Same-Boundary Performance Gate

**Purpose**: Decide IQ3 admission from a strict direct-versus-optimized-reference comparison, not the whole-model P1 delta.

- [x] T057 Extend the real-matrix harness and evidence contract with compiler settings, pipeline creation, first-use, dispatch preparation, kernel, synchronization, RSS, and every warm sample
- [x] T058 Run the admitted representative IQ2_XXS gate matrix against optimized NumPy+MLX and the strict sequential Metal scaffold under identical bindings
- [x] T059 Generate and validate a three-way review artifact, retaining historical/default compilation only as labeled historical evidence when comparable
- [x] T060 Apply the frozen verdict rule: `GO`, `GO WITH PERFORMANCE REDESIGN`, or `NO-GO`
- [x] T061 If required by T060, retain the sequential scaffold and specify/implement a separately qualified parallel IQ2 kernel through the bounded ladder; otherwise record why it was not started
- [x] T062 Admit IQ3-down only if the final verdict is `GO` and every compiler, numerical, fallback, lifetime, evidence, and CI gate is committed

---

## Phase 12: Post-Opus Closeout

**Purpose**: Publish a reviewable, reproducible qualification boundary.

- [x] T063 Create `docs/research/glm52/F018_POST_OPUS_QUALIFICATION.md`, update claims/reviewer indexes, regenerate artifacts, and send the final acknowledged NTFY result
- [x] T064 Run all Feature 018 native, Cargo, research, privacy, generated-artifact, Spec Kit, staged-safety, and `git diff --check` gates; commit, push, and confirm CI

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
- Phase 9 through Phase 12 are the post-Opus qualification gate. T048-T060 are
  sequential. T061 is eligible only for a performance-redesign verdict. T062
  is a decision task and MUST NOT start IQ3 implementation unless every named
  admission condition passes.

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

---

## Phase 13: IQ3-Down Contract Freeze

**Purpose**: Freeze the independent second-format boundary before candidate code or output.

- [x] T065 Bind the authoritative layer-3 expert-15 IQ3_XXS down matrix and freeze `iq3-down-numerical-qualification-contract.md`
- [x] T066 Add the IQ3 packed-layout contract, extend Feature 018 spec/plan/research/data model/quickstart, and commit/push the pre-candidate contract boundary

---

## Phase 14: IQ3 Synthetic Scaffold

- [x] T067 Add failing IQ3 request/layout/oracle, malformed/truncated, scale/sign, boundary-shape, finite-value, deterministic, fallback, and materialization tests
- [x] T068 Implement the separate Rust IQ3 spec, lookup identities, deterministic synthetic generator, and same-order scalar GEMV oracle
- [x] T069 Implement the strict sequential packed IQ3 Metal kernel and distinct bridge dispatch using the qualified compiler/lifetime/telemetry infrastructure
- [x] T070 Pass 100 deterministic synthetic executions, retain public-safe evidence/table, and commit/push the synthetic gate

---

## Phase 15: Real IQ3 Matrix and Same-Boundary Gate

- [x] T071 Add the fail-closed real IQ3 matrix harness, semantic evidence validator, generator checks, and immutable binding
- [x] T072 Send the hardware NTFY, verify checkpoint/resource admission, and run scalar/NumPy+MLX/strict-Metal on one real layer-3 expert-15 down matrix
- [x] T073 Retain 3 warmups/30 samples, classify under `f018-iq3-down-v1`, generate the comparison table, apply the material-performance decision, and commit/push
- [x] T074 If the strict scaffold is not materially faster, retain it and qualify a separate Tier-B parallel IQ3 kernel; otherwise record why no parallel kernel was built

---

## Phase 16: Composed IQ2 + IQ3 Ladder

- [ ] T075 Extend validation dispatch so qualified IQ2 gate/up and IQ3 down execute directly while unsupported roles/formats remain explicit reference dispatches and direct failures remain fatal
- [ ] T076 Run and commit one qualified complete routed expert with separated IQ2, activation, IQ3, registration, kernel, sync, total, memory, and dispatch accounting
- [ ] T077 Run repeated-warm same-expert reuse and validate registration/pipeline/native-ready reuse, deterministic output, teardown, generation, mutation, fallback, and materialization gates
- [ ] T078 Run and commit the eligible representative top-8 plus shared MoE boundary with direct IQ2/IQ3 and explicit shared/reference accounting
- [ ] T079 Run and commit the eligible representative complete-layer boundary with a layer-scoped numerical/performance claim

---

## Phase 17: IQ3 Closeout and Next Profile

- [ ] T080 Generate the post-IQ3 bounded hotspot profile and select no third kernel before the measured ranking is committed
- [ ] T081 Decide optional P1 from the complete-layer gate; if admitted run exactly one clean-source P1 `[9703,21615]`, otherwise document deferral; never run P2/golden-eight
- [ ] T082 Record only format-neutral IQ3 lessons as concrete Feature 017 requirements without moving IQ3 semantics into Feature 017
- [ ] T083 Create `F018_IQ3_DOWN_QUALIFICATION.md`, update claims/reviewer indexes, regenerate artifacts, and send the final acknowledged NTFY result
- [ ] T084 Run IQ2/IQ3 native, lifetime, Cargo, research, privacy, generated-artifact, Spec Kit, staged-safety, `git diff --check`, push, and confirm both Apple Silicon CI jobs

### IQ3 extension dependencies

- T065-T066 precede every IQ3 candidate implementation or output.
- T067-T070 are sequential TDD and synthetic gates.
- T071 precedes checkpoint access; T072-T074 bank the real matrix before any composed work.
- T075-T079 advance expert → reuse → MoE → complete layer and stop at the first failed or non-material gate.
- T080 precedes any third-kernel recommendation. T081 is optional and may run only after T079 passes materially from a clean committed source.
- No P2, golden-eight, third kernel, or Feature 017 implementation belongs to this extension.
