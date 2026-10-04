# Tasks v1
All paths below are relative to this addendum unless stated otherwise.
Package P = scripts/research/glm53_flash/native_preparation_model_state_v1/.
Test T = scripts/research/tests/test_glm53_native_preparation_model_state_v1.py.

## Constitution-compliance check — 2026-10-04
PASS for this bounded preparation document under the existing [plan gates](plan.md#constitution-gates)
and [consistency analysis](analysis-v1.md). Authority: [Constitution Governance](../../../../.specify/memory/constitution.md#governance),
`.specify/memory/constitution.md` lines 166–168, requires an explicit check in
specifications, plans, tasks, reviews and commits. Correctness evidence remains
independent synthetic host tests; claims, ownership, attribution and exclusions
are unchanged. No constitution exception or production qualification is asserted.
The governance correction changes documentation only; the exact revised review
and next commit must each include their own check. Coordinator readiness and
integration approval remain separate gates (see [freeze history](evidence.md#governance-correction-freeze-cutoff)).

## Setup
- [x] T001 Read pinned source and create spec.md, checklist.md (FR-001,007).
- [x] T002 Create plan.md, research.md, data-model.md and quickstart.md (FR-007).
## Foundations
- [x] T003 Pin source-pins.json and analyze spec/plan/tasks (FR-001,008).
## US1 — interface and topology
- [x] T004 [US1] Write interface-v1.md and tensor-role-coverage-v1.md (FR-002,003,005,006).
- [x] T005 [US1] Add T topology and math edge tests and P fixtures.py/oracle.py (FR-002).
- [x] T006 [US1] Add P contract.py topology and semantic boundary harness (FR-002,006).
## US2 — state
- [x] T007 [US2] Add T partition/rollback/reset/interleave/mutation tests (FR-003,004).
- [x] T008 [US2] Add independent state oracle in P oracle.py and fixtures.py (FR-003,004).
- [x] T009 [US2] Add P state.py transactional bounded harness (FR-003,004,006).
## US3 — final gates
- [x] T010 [US3] Validate host tests and scope; update evidence.md (FR-007,008; SC-001,003).
- [x] T011 [US3] Freeze exact package and independent ACCEPT/0; private receipts (FR-008; SC-002).
- [x] T012 [US3] Own-branch commit and private handoff, coordinator integration dependency (FR-008; SC-003).

Dependencies: T001->T002->T003->T004->T005->T006->T007->T008->T009->T010->T011->T012.
No worker parallelism. US1 is first independently reviewable slice; final goal
requires all stories, not just that slice. Tests precede candidate implementation.

T011/T012 record the prior package's completion: attempt-02/acceptance-receipt.json
and commit 8e1e6d21d982d09cec2f0f606ee559177e0a8455. That acceptance is preserved;
it does not confer acceptance on this later documentation revision.

## Governance correction — coordinator finding model-state-governance-001
- [x] T013 Add explicit constitution-compliance checks to spec.md and tasks.md; record truthful freeze history in evidence.md. Implementation, fixtures, tests and pinned references remain unchanged.
- [ ] T014 Obtain exact revised-package ACCEPT/0 with an explicit Constitution Governance lines 166–168 compliance check; bind docs, unchanged functional hashes, prior acceptance and frozen integration contract in private attempt-03 receipts.
- [ ] T015 Create the narrow documentation commit with its compliance check/citation, verify committed hashes, and provide the attempt-03 handoff for coordinator re-verification before readiness; no integration.

Dependencies: T012->T013->T014->T015. At the documentation freeze cutoff, T013 is
complete and T014/T015 are prospective. Their terminal status belongs in exact
attempt-03 review/commit/handoff receipts, without editing reviewed source after
acceptance. No future verdict is required to exist before the freeze.
