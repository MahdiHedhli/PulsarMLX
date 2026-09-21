# F017 Checkpoint Identity Lifecycle V7 — Opus Design Review, Cycle 03

Reviewed exact committed bytes at `17e3defd` in a detached read-only worktree. Both worktrees were clean. No original checkpoint shard was opened, hashed, mmapped, or pread; no Event-04 authority was minted; no real oracle or P1 attempt 2 executed. Mutation probes ran only against a deleted isolated scratch copy.

The reviewer independently reconstructed the V6 defect, re-derived the six-shard `238,458,632,928` byte census and 1,809 graph-tensor distribution, verified all 11 pinned authorities were canonical and hash-bound, confirmed numerical contract SHA `84ff9ba0…`, historical ledger 175, active live generation NONE, and original checkpoint access zero. Exhaustive graph enumeration found 33 states, 40 transitions, 19 maximal traces, exactly one failure outcome per non-success trace, and no isolated state.

No blocking findings were reported. Eleven non-blocking-required findings were returned before implementation entry:

1. Identity-failure obligations required success-only manifests without nullability.
2. Lease-release evidence enforcement excluded identity failure.
3. Required lists were not closed under artifact SHA back-references.
4. Post-claim/pre-package-start failure was absent.
5. Lease-activation failure was absent.
6. Pre-mint failure did not cover every pre-install boundary.
7. Lease owner/activation/release actor identity was inconsistent.
8. Path artifact names diverged from schema names and the access-journal terminal lacked a schema.
9. Seven material design regressions still passed validator mutation probes.
10. Design freeze posture was not validator-gated.
11. A failing post-primary continuity recheck had no dedicated evidence.

Defense-in-depth observations covered value censuses, lease-terminal closure counters, per-check continuity results, path timing coverage, exact six-shard loop guards, direct shard/journal obligations, stale draft marking, active status, and V6 revocation anchoring.

Required verdict returned:

`ACCEPT_CHECKPOINT_IDENTITY_LIFECYCLE_V7_FOR_IMPLEMENTATION`

The reviewer concluded that the security core remained sound and all findings were repairable evidence/enforcement defects that fail closed, but required their resolution before implementation entry.
