# Tasks

- [x] T01 Read rules/approved input and reconcile source inventory.
- [x] T02 Specify canonical interface and exact prospective test population; analyze constitution.
- [x] T03 Obtain exact preimplementation Opus5.5 ACCEPT/0.
- [x] T04 Import pinned packages without changes; author literal oracle and tests before adapter.
- [x] T05 Implement host phases/provenance/preflight/quiescent cancellation/outbox.
- [x] T06 Pass retained32 model runs/29 storage cases plus new normal/optimized tests and mutants; compile source offline.
- [ ] T07 Freeze exact final files/results/history and independently review/fix until ACCEPT/0.
- [ ] T08 Commit reviewed package, verify hashes and write bounded handoff. Coordinator readiness/integration remains external.

Sequential dependency T01→T02→T03→T04→T05→T06→T07→T08. No delegated or parallel workers in this track. Tests required by every R1–R8 precede implementation.

Constitution-compliance check: PASS for this bounded specification, under .specify/memory/constitution.md Governance lines166–168 and principles I, III, VIII, X, XI, XII. Only additive stdlib host synthetic code is planned; no production/native claim, weights, shared metadata or frozen-source modification. Tests, exact independent reviews, failures and commands remain explicit. No Rust changes; workspace/native checks are outside this slice.

Freeze cutoff and completion accounting: evidence.md states observed results and future review/commit boundaries. T07/T08 close via immutable audit receipts after this exact source freeze; never invent a future verdict to mark a reviewed input complete.
