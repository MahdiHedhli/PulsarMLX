The plan file can't be written (the Write tool is disabled in this session), so the review record is delivered here in full.

# F017 Event 06 V12 Whole-Domain Arbiter — Cycle 3

## Preconditions

| Check | Result |
|---|---|
| HEAD | `686d74cbd10c23f0e3c2a4ebf69c0310e7e8bb20` ✅ |
| Tree | `6c076fc31d51ca8b9393d256a4ff9c3170f75862` ✅ |
| Worktree | clean ✅ |

Reviewed read-only against committed blobs (`git show`/`git cat-file`). No prohibited action taken. **Disclosure:** I did not create a fresh detached clone — plan mode forbids filesystem writes. For a committed-bytes-only review this is equivalent, but it is a deviation from the stated method.

## What verified clean

- **Event 05** terminal, non-retryable, closed: postmortem `TERMINAL_POST_PACKAGE_START_FAILURE_NO_RETRY`; graph state `E5: TERMINAL_FAILURE`, `E6/E7/E8/E13: INVALIDATED`, `FINAL_NO_GO_CLOSEOUT`, zero checkpoint access.
- **V10/V11 authorities byte-exact**: `d33fd067…`, `967c1d55…` reproduce; last touched at `11e4c7e9`/`53c114f7`.
- **N-1 genuinely repaired**: `f017_checkpoint_identity_producer_v12.py` at HEAD contains *zero* occurrences of `progress`/`callback`; `produce()` takes no such parameter and has no `**kwargs`, so injection is impossible. `run_identity_stage` no longer accepts or forwards it. Contract (`12.0.2`) requires `caller_callback_parameters: 0` and the validator raises on nonzero.
- **Measurement v5**: binds `ee1d5df6`/`5d361aa1` (tree independently confirmed). All **25** path digests reproduce exactly at both `ee1d5df6` and HEAD; all 6 historical bindings reproduce. **Zero mismatches.**
- **Qualification counts exact**: 90 terminals, 250 mutations rejected, 393 substantive failures, 12/12 modeled outcomes, 0 unexpected passes, 0 checkpoint access, `generic_fallback: false`.
- **Rehearsal v7**: all access counters 0, no state, no live authority, at `ee1d5df6`.
- **FULL_NATIVE `33120622266`**: `required_native_skips: 0`, `unexpected_skips: 0`.
- **CI history v3/v4**: 3 failed runs preserved, `33119484879`/`33119542626` bound, v4 appends `33121755141` and binds v3 by digest `3c4c5e08…` — reproduces exactly. Zero native jobs. No CI-history file was ever modified.
- **Rejection preserved**, six findings mapped in support ledger v11; drift zero; Event 06 unexecuted, ledger 175, P1 attempt 2 absent.

## Blocking findings (3)

**BLOCK-1 — Readiness declaration pinned to a superseded head, asserting a contradicted verdict.** The sole declaration binds `implementation_head 45647e1a`, not `ee1d5df6`, and asserts `ready_…_go: true` with `blocking_findings: 0`, `non_blocking_required_findings: 0`, `unresolved_claims: 0`, `opus_verdict: ACCEPT_…`. The committed ratification record says `REJECT`, 1/3/2. No successor declaration exists.

**BLOCK-2 — Latest authority manifest binds pre-repair bytes and is un-instantiable.** Manifest v6 (no v7 exists) binds the producer, capability module, and coordinator at `fbbf162f…`/`f9713801…`/`52dd8748…` — all stale vs HEAD. Its `identity_producer_progress_callback: "PROHIBITED"` is asserted over the exact bytes that *contained* the callback. Since `validate_event06_readiness_declaration` mechanically requires manifest head == declaration head and every declared SHA to appear in `manifest.bindings`, the readiness authority cannot be instantiated at the repaired head.

**BLOCK-3 — B-1's defect survives at the manifest layer.** Manifest v6 still names `evidence_only_run: 33118831286` while binding CI history **v2**, which ends at `33116756921`. Nothing binds v3/v4. Support ledger v11 itself reports `result: "REPAIR_IN_PROGRESS"`.

## Non-blocking-required (3)

- **NBR-1 (N-3 unrepaired):** synthetic v6 / failure v7 carry no committed generator or raw-qualifier binding.
- **NBR-2 (N-2 unrepaired):** bound canonical reviewer results predate both the declaration bytes and the repair.
- **NBR-3:** `f017_checkpoint_identity_capability_v12.py:32-35` inspects only `posonlyargs`/`args`/`kwonlyargs` for the literal names `callback`/`progress` — not `vararg`/`kwarg`. `**callback` or a renamed `on_progress`/`cb` passes. Exact-name mutations *are* rejected; the contract's broader `"caller_callback"` class is not enforced.

## Unresolved (1)

- **UNRES-1 (U-1 unrepaired):** `f017-event06-final-readiness-instantiability-v1.json` still omits `checkpoint_root` and `event_identity_plan_sha256`, so `candidate_sha256: 665180e2…` is unreproducible; the artifact is also pinned to `45647e1a`. *(U-2 is resolved.)*

## Claim verdicts

`C-SCOPE-001` ACCEPT · `C-SCOPE-002` ACCEPT · `C-INTERFACE-001` ACCEPT · `C-VALIDATE-001` ACCEPT · `C-VALIDATE-002` ACCEPT · `C-VALIDATE-003` ACCEPT · `C-RUNTIME-001` ACCEPT · `C-RUNTIME-002` ACCEPT · `C-FAIL-001` ACCEPT · `C-FAIL-002` ACCEPT · `C-FAIL-003` ACCEPT · `C-HIST-001` ACCEPT · `C-SYN-001` ACCEPT · `C-NOACCESS-001` ACCEPT · `C-CI-001` ACCEPT · **`C-GO-001` REJECT**

## Counts

Blocking: **3** · Non-blocking-required: **3** · Unresolved: **1**

## Global verdict

**REJECT**

The implementation layer at `ee1d5df6` is sound and the callback defect is genuinely repaired and measured. The authority layer is not: the newest manifest and the only readiness declaration both remain pinned to the superseded head `45647e1a`, bind pre-repair producer bytes, and assert an ACCEPT with zero findings that the preserved ratification record contradicts. The domain's own support ledger says `REPAIR_IN_PROGRESS`. The carry-forward exception does not apply — these gaps are the *absence* of enforcing bytes, not something mechanically enforced by them.

**Smallest truthful path forward:** bank manifest v7 at `ee1d5df6` binding the v5/v6/v7 successors and CI history v4; add raw-qualifier bindings to the qualification successors; widen `validate_capability` to `vararg`/`kwarg` and re-bank the contract; bank an expanded instantiability successor exposing `checkpoint_root` and `event_identity_plan_sha256`; obtain renewed canonical reviewer results at the repaired head; then bank a successor declaration and re-arbitrate.
