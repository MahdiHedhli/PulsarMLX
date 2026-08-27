# F017 Event 06 V12 whole-domain arbiter cycle 5

Use `claude-opus-5`, effort high, in a fresh detached read-only clone. Review exact committed bytes only. Verify HEAD `99b8cb08c31060caecb8cd532003f5699fd3c3b1`, tree `f8bbd50858eafb5e24e0b4e3697557af9257a568`, and a clean worktree before review. Do not modify files, access original checkpoint shards, mint Event 06 authority, execute Event 06, retry Event 05, or execute P1 attempt 2.

This is the final-hardening review after cycle 4 accepted all sixteen readiness-critical claims. The sole post-cycle-4 execution-byte change tombstones the superseded v12-v1 readiness declaration in the measured readiness validator. Determine whether the exact committed package may proceed to append-only final authority and readiness declaration banking. Do not require the final v12-v2 declaration to predate this acceptance: graph order creates it only after this arbiter accepts. Manifest v8 truthfully sets active generation `NONE`, result `PREPARED_PENDING_FINAL_HARDENING_ARBITER`, and `final_hardening_review_pending: true`.

Verify all of the following directly:

1. `scripts/research/f017_event06_readiness_authority_v1.py` SHA-256 is `d1ee8b80f7a6f9e778a7faffa8962a8795415db08b0c60308d01ee6650ba4bc8` and fail-closes the superseded v12-v1 declaration SHA `eca5b5d3ad1c669e246d70ee5a48ca2d2f687188002130b9a92ae1ea6f2cb840` before parsing.
2. The measured validator still accepts only the exact typed current contract; supersession adds no alias, fallback, or permissive path.
3. Targeted local regression v8 records 24 PASS, including superseded-declaration rejection, with no unexpected pass.
4. Exact-head FULL_NATIVE run `33124907328` at implementation head `5b98e53e6d9c4e2c2a8ae91bd71f55001517f5d0`, tree `e27590470ffb6ddf3885e8ae4e1a399e211aa27e`, passed with zero required native skips.
5. Raw qualification output remains byte-identical at SHA-256 `9c8b09e93da22ac5443683de0c696067e952fca187e0b61f9c4ef2adfe55ba7d`.
6. Synthetic qualification v8, failure qualification v9, and rehearsal v9 bind the exact final implementation and preserve zero original-checkpoint access.
7. Manifest v8 has exactly 29 bindings; recompute every bound file SHA. It binds measurement v7, FULL_NATIVE v6, CI history v5, cycle-4 accepted review, the raw qualifier output, current runtime bytes, and all current contracts.
8. Evidence-only run `33126063555` for this exact reviewed head passed evidence integrity with all native jobs skipped.
9. The cycle-4 accepted response and normalized result remain immutable evidence; this cycle independently covers the only later execution-byte hardening.
10. The producer signature remains exact, with no callback, reflection, variadic, I/O, authorization, or lifecycle capability in the pure producer surface.
11. Validation-only approval v1 and instantiability v2 still reproduce candidate SHA `94008a7d522d6216f05c92ffa7709c2941349db422680d2efe7e4f97812e6639` across 20 fresh processes with candidate triple, installed triple, and package-start eligibility PASS and every side-effect counter zero.
12. Event 05 is terminal and non-retryable; Event 06 is unexecuted, has no live authority or package start, and has zero original-checkpoint access; P1 attempt 2 is absent; historical ledger is 175.

Independently rerun or inspect the mechanically safe validators and mutations needed to support your verdict. Do not open the original checkpoint root or use real checkpoint payloads.

Decide every readiness-critical claim: `C-SCOPE-001`, `C-SCOPE-002`, `C-INTERFACE-001`, `C-VALIDATE-001`, `C-VALIDATE-002`, `C-VALIDATE-003`, `C-RUNTIME-001`, `C-RUNTIME-002`, `C-FAIL-001`, `C-FAIL-002`, `C-FAIL-003`, `C-HIST-001`, `C-SYN-001`, `C-NOACCESS-001`, `C-CI-001`, and `C-GO-001` using only `ACCEPT`, `REJECT`, or `UNRESOLVED`.

Return exact counts for blocking, non-blocking-required, and unresolved findings. The required global verdict is exactly one of:

- `ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_06_EXECUTION_AUTHORIZATION_PREPARATION`
- `REJECT`

No conditional acceptance.
