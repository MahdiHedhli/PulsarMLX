# Tasks: Real Expert Execution

**Input**: Design documents from `/specs/003-real-expert-execution/`  
**Prerequisites**: Feature 002 complete on `main`

## Phase 1: Setup

- [X] T001 Create `fixtures/research/expert-v1/` skeleton and README bounds
- [X] T002 Wire feature id `003-real-expert-execution` into research package paths
- [X] T003 Add contracts checklist under `specs/003-real-expert-execution/checklists/`

## Phase 2: Foundational tests (fail first)

- [ ] T004 [P] Rust expert contract tests for admission and shape
- [X] T005 [P] Python expert oracle independence tests
- [ ] T006 [P] Research package path tests for `003-expert-mlp`

## Phase 3: US1 Expert admission

- [X] T007 Implement expert tensor range math for gate/up/down at index 114
- [ ] T008 Implement `inspect-expert` command
- [ ] T009 Fixture-only negative admission cases

## Phase 4: US2 CPU oracle

- [X] T010 Implement `scripts/research/expert_oracle.py` (SiLU SwiGLU, no MLX)
- [X] T011 Freeze external oracle using F002 input row + weight for expert 114
- [X] T012 Publish redistributable oracle freeze under fixtures/raw support

## Phase 5: US3 MLX parity

- [X] T013 Implement MLX full expert MLP + weighted output path
- [X] T014 Implement `validate-expert` command with comparison
- [ ] T015 Resource admission + NTFY pre-access
- [X] T016 Run real validate-expert; retain external candidate
- [X] T017 Sanitize, publish raw, regenerate artifacts, claim F003-C01
- [ ] T018 Clean-checkout reproduction

## Phase 6: Closeout

- [ ] T019 Update README/COMPATIBILITY/KNOWN_LIMITATIONS/SESSION_LOG
- [ ] T020 Workspace + research tests green; package verify
- [ ] T021 Push main; CI green; NTFY completion

## Dependencies

T001-T003 → T004-T006 → T007-T009 → T010-T012 → T013-T018 → T019-T021

## Notes

- Do not begin Feature 004 until T021 completes with verified claim.
- Expert 114 and F002 identities are frozen unless admission proves impossibility.
