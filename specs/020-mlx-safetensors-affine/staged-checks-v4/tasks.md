# Sequential tasks (one numerical owner)

Setup/foundations:
- [x] T001 Record approved scope and unchanged identities in staged-checks-v4/spec.md and contract-v4.json (FR01,FR10).
- [x] T002 Freeze design and public A01..A12 in staged-checks-v4/plan.md and population.md (FR02..FR08).
- [x] T003 Cross-artifact/constitution analysis in staged-checks-v4/analysis.md and exact preimplementation review in own attempt audit (FR01..FR10).

US1 independent original certificate:
- [x] T004 [US1] Author literal independent oracle/control expectations in scripts/research/f020_staged_v4/literals.py and scripts/research/tests/test_f020_staged_v4.py (FR02,FR03,FR08).
- [x] T005 [US1] Implement bounded exact intervals, certificate and absolute down propagation in scripts/research/f020_staged_v4/numeric.py (FR02,FR03).
- [x] T006 [US1] Implement immutable original custody/reference construction in scripts/research/f020_staged_v4/source.py (FR01..FR03).

US2 live stages:
- [x] T007 [US2] Implement owner, linked receipts, replay/refusal/cleanup and resource barriers in scripts/research/f020_staged_v4/owner.py (FR04..FR07).
- [x] T008 [US2] Implement public-only CPU/mock backend in scripts/research/f020_staged_v4/mock.py and stage mutants in scripts/research/tests/test_f020_staged_v4.py (FR04..FR08).

US3 validation/freeze:
- [x] T009 [US3] Run A01..A12 plus two full-shape public positives, safe retained CPU tests and offline builds; record exact commands and unrun native population mapping in own attempt audit (FR08,FR09).
- [ ] T010 [US3] Obtain fresh exact final source/build/test Opus5.5 ACCEPT/0 and verify current/quoted hashes in own attempt audit (FR09).
- [ ] T011 Inspect staged inventory and make local-only reviewed commit; recheck committed/current/capsule hashes and preserve old contract in own attempt audit (FR01,FR09,FR10).
- [ ] T012 Complete own attempt REPORT.md and handoff.json with requirement evidence, limitations and future native gates (FR01..FR10).

Dependencies T001->T002->T003->T004->T005->T006->T007->T008->T009->T010->T011->T012.
No parallel worker tasks within this track. Other approved track owns different
worktree/audit; no dependency authorizes touching it. No reduced MVP completion:
all three stories and exact review/freeze required. Native observations remain
excluded; future qualification gates are not falsely checked as complete here.

T010–T012 are freeze-time outstanding receipt steps. Their final closure is
recorded in attempt02 handoff.json/task_closure and REPORT.md after review
and commit, preserving these exact reviewed document bytes.
