# GLM-5.3-Flash native model/state preparation v1
Date: 2026-10-04. Status: preparation contract, never production runtime.
Base: bff720bd4ddc83fcf6c41ed4c58a938d8c2c33ef. Owned nested F020 addendum.

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

## User scenarios
US1 (P1): An integrator can inspect the complete text-model operation boundary,
45-layer dispatch and tensor-role coverage without opening a checkpoint.
Given pinned source/config, dispatch agrees with both explicit layer lists;
unknown or conflicting metadata is refused. Dense layers are exactly 0..2.
US2 (P1): An integrator can exercise request-owned KDA and sparse states.
Given nonzero unequal-axis synthetic inputs, prefill, arbitrary chunks and token
steps have equal outputs and final state; cancellation retains all prior state,
reset changes epoch, stale steps fail, and interleaved requests remain isolated.
US3 (P2): A reviewer can reproduce every bounded claim from a frozen package.
Given source hashes and host commands, tests and deliberate mutations pass and
an independent exact-package review ends ACCEPT with process exit 0.

## Requirements
FR-001: Pin source/config/capsule hashes; distinguish source metadata, tiny
arithmetic and unavailable checkpoint/production evidence.
FR-002: Validate 45-layer KDA/sparse and dense/routed-plus-shared dispatch;
validate corrected-score selection, original-score mixing, mHC orientation,
and embedding/stream mean/norm/untied-head boundary with independent math.
FR-003: Specify KDA recurrence plus raw convolution suffix ownership and sparse
latent/index-key/gate/pool/tail position ownership; no hidden ambient state.
FR-004: Test nonzero initial state, unequal axes, exact toy ties, all chunk
partitions, reset, continuity, rollback, interleaving, stale epochs and commits,
and meaningful semantic/state mutations for both attention kinds.
FR-005: Agree with frozen integration v1: explicit step identity and positions,
opaque bounded PackedTensorLease; storage policy remains the other lane's.
FR-006: List tokenizer/EOS, every uncovered production component and integration
dependency. Refuse unsupported geometry, nonfinite inputs and graph mismatches.
FR-007: Only owned source/docs/tests and private audit; stdlib, no MLX import,
checkpoint access, GPU, integration, push or feature metadata edits.
FR-008: Retain host/review failures and exact receipts; recover findings and
re-review the final package; coordinator checks before integration.

## Success criteria
SC-001: Targeted host suite proves FR-001..006 at declared tiny bounds with
binary64 atol 1e-12, rtol 1e-10 and exact integer/state identity checks.
SC-002: Source and review capsule hashes agree; actual reviewer modelUsage is
claude-opus-5-5 and terminal verdict ACCEPT/0; no provider error counts.
SC-003: real_reads=0, native_gpu_calls=0; handoff lists open dependencies.

## Entities and edge cases
Descriptor, LayerPlan, StepIdentity, Context, KDAState, SparseState, Proposal,
opaque PackedTensorLease. Empty work, booleans as integers, NaN, wrong layer,
position gaps/replays, exhausted context, changed epoch, cancellation after
partial computation, wrong recurrence transpose and stale sparse tail are
explicit tests. Tiny tie order is ascending ID; production tie behavior is open.
