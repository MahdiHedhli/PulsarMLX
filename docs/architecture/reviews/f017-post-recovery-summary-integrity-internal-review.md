# PulsarMLX F017 Post-Recovery Summary-Integrity Internal Review

## Scope

This checkpoint-free review covers only the completed v2 antecedent-recovery
summary-integrity remediation. It does not review or authorize checkpoint
access, route discovery, Q6_K qualification, M1-F execution, or P1.

Reviewed implementation commit: `36bff713e935ca466c3c32156ecaf164f180aa12`

## Findings

1. The executor now retains the complete 1,984 membership and 7 adjacent
   selected-order records before deriving any summary.
2. Membership and ordered summaries each use a full-surface scan. The true
   global extrema are `177 → 98` at `1.2497550469932908` for membership and
   `233 → 177` at `0.22551544432236478` for selected order.
3. `route_set_stable` is derived only from membership and is `true` for the
   banked recovery. `route_order_stable` is derived only from ordered pairs and
   is `false`. The overall mathematical result remains
   `NOT_MATHEMATICALLY_STABLE`.
4. Stored summaries are non-authoritative until exact canonical comparison
   with a freshly detail-derived summary succeeds. Missing, duplicate,
   noncanonical, stale-count, stale-factor, and summary-mutation inputs fail
   closed.
5. The six required independent summary mutations and eight additional
   surface/summary mutations all fail validation.
6. The historical raw recovery artifact remains byte-identical at
   `f9422287cb98322d1412a6dd2397bb0f4a0d6538778aa587dddff7c5154acf2a`.
   Authority is explicitly assigned to `derived_detail_summary`; historical
   raw evidence is not rewritten.
7. The related-path audit found the same first-failure/extrema defect in an
   active route-stability helper and corrected it. It found no historical
   false-PASS path. M1-D, M1-E, and M1-F0 PASS gates inspect complete repeat or
   qualification surfaces, and the affected v2 recovery was already an
   overall mathematical failure.
8. No v2 numerical term, threshold, pair record, ledger entry, or historical
   route identity changed.

## Validation reviewed

- Targeted summary/recovery/v2 suite: 41 tests passed.
- Full Python research/evidence suite: 524 tests passed.
- Rust workspace inventory: 442 tests discovered; every runnable test passed,
  with only previously declared environment-gated tests ignored.
- `cargo check --workspace --all-targets`: passed.
- `cargo test --workspace --no-fail-fast`: passed.
- `scripts/check.sh`: passed.
- Banked recovery summary validator and ledger validator: passed.
- Raw-evidence SHA-256 immutability and `git diff --check`: passed.

## Risk decision

There is no false-PASS path and no reason to reopen numerical or checkpoint
evidence. Active and future pairwise summary paths are fail-closed against
summary/detail disagreement. Final-head Apple-native CI remains the final
external gate.

## Verdict

`GO FOR CHECKPOINT-FREE POST-RECOVERY RESEARCH`
