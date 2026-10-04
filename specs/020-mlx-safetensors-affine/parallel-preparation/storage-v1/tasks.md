# Tasks: Bounded storage preparation
Input: this addendum's spec/plan/research/data-model/contracts.

## Phase 1 — Setup
- [x] T001 Read project/accepted sources and document decisions in storage-v1/research.md (FR-010, FR-011).
- [x] T002 Write storage-v1/spec.md and checklists/requirements.md (FR-001–FR-011).

## Phase 2 — Foundation
- [x] T003 Write storage-v1/plan.md, data-model.md, contracts/interface.md and quickstart.md (FR-001–FR-008).
- [x] T004 Analyze spec/plan/tasks read-only and retain report in private audit (SC-001).

## Phase 3 — US1: admission
- [x] T005 [US1] Write independent accounting/refusal/byte-fidelity tests in scripts/research/tests/test_glm53_native_preparation_storage_v1.py before implementation (FR-001–FR-003, FR-007).
- [x] T006 [US1] Implement bounded source seal/reservation/read/admission fixture in scripts/research/glm53_flash/native_preparation_storage_v1/fixture.py (FR-001–FR-003, FR-007).

## Phase 4 — US2: ownership
- [x] T007 [US2] Test transfer, pins, generation, source lifetime and eviction in scripts/research/tests/test_glm53_native_preparation_storage_v1.py (FR-004, FR-005).
- [x] T008 [US2] Implement ownership/refusal transitions in scripts/research/glm53_flash/native_preparation_storage_v1/fixture.py (FR-004, FR-005).

## Phase 5 — US3: cancellation/recovery
- [x] T009 [US3] Author explicit expected adversarial traces in scripts/research/glm53_flash/native_preparation_storage_v1/adversarial.json independently of fixture implementation (FR-006–FR-009).
- [x] T010 [US3] Test faults/cancellation/step bindings/repeated cycles/leak and double-release mutations in scripts/research/tests/test_glm53_native_preparation_storage_v1.py (FR-006–FR-009).
- [x] T011 [US3] Implement cancellation/acknowledgement and receipt fixture in scripts/research/glm53_flash/native_preparation_storage_v1/fixture.py (FR-006–FR-009).

## Final phase — Exact review/handoff
- [x] T012 Record targeted host results and scope checks in storage-v1/validation.md (SC-001, SC-002, SC-004).
- [ ] T013 Freeze exact source package and obtain independent ACCEPT/0, private attempt-02 audit (FR-010, SC-003).
- [x] T014 Write storage-v1/handoff.md with source and open production dependencies; own-branch commit after validation (status completed only after commit; exact receipt tracked privately) (FR-010, FR-011, SC-004).

## Dependencies and execution
T001→T002→T003→T004→tests/corpus→implementation→T012→T014→T013.
US1/US2/US3 independently testable using fresh small machines, share foundation.
One assigned worker, no delegation or parallel workers. No [P] tasks because the
same source/test files are shared. Implement all stories; no reduced MVP handoff.

T013 is an external acceptance gate. Its final status is recorded in the private
exact-source verification receipt, avoiding a source edit after final review.
The unchecked source marker does not claim acceptance; ACCEPT/0 remains mandatory.

## Constitution compliance
Constitution I–XII: see [plan.md Constitution Check](plan.md); no exception.
Tasks preserve owned scope, synthetic-only host evidence, exact independent review,
no secrets/weights and explicit production dependencies. T013 remains mandatory.
