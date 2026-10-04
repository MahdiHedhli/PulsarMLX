# Host validation and independent review evidence
2026-10-04, Darwin arm64, Python 3.14.7. No dependency installation.

## Current targeted host result
Command:
`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts/research/tests -p test_glm53_native_preparation_storage_v1.py -v`

`host-cycle-09.log`: 29 tests PASS, 0 failures/errors, 0.008s reported by unittest.
Six literal traces, 24 independent event-order permutations, 128 complete
reserve/read/admit/release-or-cancel/evict cycles, and three deliberately broken
adapter witnesses. Leak and double-release mutants fail audit reconciliation;
the retained-unused-reservation mutant passes internal audit and is caught by
independent literal ledger evidence. These are synthetic observations, not physical
memory or paging/performance measurements.

## Preserved host evidence
All raw artifacts are private in the attempt-02 audit located by handoff.md.
Host artifacts use `host-` prefixes; reviews use `review-` prefixes.

| Exact host artifact | Observed result |
|---|---|
| host-before-implementation.log | Missing fixture import error before implementation |
| host-cycle-01.log | 16 tests, 1 oracle owner/cancel precedence failure |
| host-cycle-02.log | 16 PASS after correcting oracle precedence |
| host-cycle-03.log | 21 tests, 1 cancelled/in-flight precedence failure |
| host-cycle-04.log | 21 PASS after correcting oracle precedence |
| host-cycle-05.log | 25 PASS after review-cycle-02 repairs |
| host-cycle-06.log | 26 PASS including protected pinned dispatch-error retention |
| host-cycle-07-regression.log | 28 tests, 2 reproduced protected unpublished-admission leaks |
| host-cycle-08.log | 28 PASS after publication-aware cleanup repair |
| host-cycle-09.log | 29 PASS including immediate unpublished refund evidence |

## Preserved independent review evidence
Each review uses the authorized tool-free command and saves `review-cycle-NN-raw.json`,
`review-cycle-NN-stderr.log`, `review-cycle-NN-receipt.json`, source/reference
manifests and capsule. Successful provider runs below report actual
`modelUsage.claude-opus-5-5`; provider error is never an acceptance verdict.

This table contains every terminal review before this source freeze, through
review-cycle-07. It is reconstructed from the actual private receipt JSON. Any
subsequent exact-package verdict is recorded in private progress/verification
receipts; those external receipts do not require changing this frozen source.

| Exact review receipt | Provider status and verdict | Repair disposition |
|---|---|---|
| review-cycle-01-receipt.json | Exit 1, is_error=true, empty modelUsage; provider error, no verdict | Authorized external retry; no login/security changes |
| review-cycle-02-receipt.json | Exit 0, provider success, actual claude-opus-5-5, REJECT/6 | F1–F6: protected dispatch cleanup, adversarial tests, corpus binding, quickstart, commit status, state/signature docs |
| review-cycle-03-receipt.json | Exit 0, provider success, actual claude-opus-5-5, REJECT/1 | R1: reproduce and fix protected unpublished admission leak; source-selection simplification documented |
| review-cycle-04-receipt.json | Exit 0, provider success, actual claude-opus-5-5, REJECT/2 | S1/S2: unpublished reservation refund policy, literal traces/mutant, exact reserve arguments |
| review-cycle-05-receipt.json | Exit 0, provider success, actual claude-opus-5-5, REJECT/3 | N1–N3: normative cancelled eviction exception, distinct evidence labels, private hash pointer |
| review-cycle-06-receipt.json | Exit 0, provider success, actual claude-opus-5-5, REJECT/2 | C1/C2: explicit Constitution I–XII in spec/tasks/checklist/commit and current direct-inspection procedure |
| review-cycle-07-receipt.json | Exit 0, provider success, actual claude-opus-5-5, REJECT/1 | V1: reconstruct complete pre-freeze review table from actual private receipts, including governance rejection |

Raw failures/rejections and each `review-cycle-NN-repair-disposition.json` remain
preserved. Final acceptance requires a fresh exact-current-package terminal
ACCEPT/0, provider success, exit 0, actual requested modelUsage, and independently
checked current source/capsule hashes. Final status and receipt are private to
avoid a source edit after review; no earlier verdict is substituted for acceptance.

## Requirement evidence and exclusions
FR-001/002: budget/category/overflow/multiple-reservation tests.
FR-003: packed fidelity/forgery/descriptor/post-copy rejection tests.
FR-004: transfer/source-close/foreign token/stale acknowledgement/generation tests.
FR-005: pin/release/eviction/cancelled cleanup/protected fault tests.
FR-006: cancellation before/during read/admission/dispatch and acknowledgement.
FR-007: scripted read, allocation, MemoryError, admission and dispatch faults.
FR-008: exact request/epoch/position envelope and no-state-advance receipts.
FR-009: six corpus traces, permutations/cycles and three mutation witnesses.
FR-010: exact-package manifest/review/verification receipt and own-branch commit.
FR-011: interface/proof/handoff production exclusions and dependencies.

`git diff --check` and exact owned-prefix stage checks passed. Direct artifact
inspection replaces the normal Speckit prerequisite invocation, which unexpectedly
persisted shared feature.json earlier. Exact original HEAD bytes were restored;
the scope incident and Git-index sandbox failure are retained privately. Final
scope verification checks every base-to-HEAD path and a clean worktree.
No Rust source changed: no Cargo/workspace/GPU/Metal/Apple lifecycle tests run.
Linux/CUDA execution unverified. real_reads=0; native_gpu_calls=0.
