The Write tool is disabled in this session, so I'll deliver the arbitration directly.

---

# REJECT

**`F017_EVENT06_SEQUENCE5_DESIGN_CYCLE8` — arbitration of `06013ba5` / tree `3064e800`**

## What I independently executed

| Command | Result |
|---|---|
| `generate_..._v8.py --check` (reviewed worktree, as-found) | exit 0 |
| `generate_..._v8.py --check` (clean clone of tree `3064e800`) | **exit 1 — `drift:` agy cycle-07 provenance** |
| `validate_..._v5.py` (clean clone) | exit 0, PASS, 13/13 predicates, 13/13 mutations, ast_guard 15 |
| `validate_..._v5.py --inject-a2-failure` | exit 1, FAIL, `A2` false, `C8-M04` unisolated |
| `py_compile` both scripts | OK |

The reviewed worktree is byte-unchanged; all execution ran in a throwaway clone. I reconstructed enforcement with counterexample probes rather than reading PASS labels.

## Antigravity findings: all four confirmed, two escalated

**AGY-1 → C8-OPUS-B1 (BLOCKING, escalated).** `generate_..._v8.py:63` sets `completed=datetime.fromtimestamp(envp.stat().st_mtime,...)`. Escalation: this is not merely drift. On the clean clone both tools' `completed_at_utc` collapsed to the *same* second — `12:09:38.006432Z` and `12:09:38.020293Z` — the checkout time, versus committed `11:49:12` / `12:02:57`. A field labelled `independent_attestation_source` is reporting filesystem state as provider timing, and `started_at_utc` is back-derived from it. The reviewed tree is not reproducible from its own generator. *Repair:* take both timestamps from the provider envelope; never `stat()`.

**AGY-2 → C8-OPUS-B2 (BLOCKING).** `:28-30` checks only `a["qualification_schema"]==q["schema"]`. Probes: rewriting `readiness()["schema"]` or `installation()["schema"]` to `pulsarmlx.f017.BOGUS/9.9.9` → caught by nothing. Only the authority-side field is protected (via the embedded SHA). *Repair:* add both artifact-vs-authority equalities.

**AGY-3 → C8-OPUS-B3 (BLOCKING, escalated).** `predicate_provenance:55-57` reads *cycle-06*. Probes on cycle-07: dropping `command` → undetected; flipping `result` from `REJECT_REVIEW_BANKED` to `ACCEPT_REVIEW_BANKED` → **undetected**. The record of both tools rejecting Cycle 7 is mechanically unprotected. *Repair:* iterate cycle-07 and pin `result`/`reviewed_commit`.

**AGY-4 → C8-OPUS-R1 (REQUIRED, downgraded).** Current bytes are clean — 9 distinct dispositions, 9 distinct SHAs — so this is an enforcement gap, not a live violation. But it is real: setting all nine rows to `"UNRESOLVED"` still passes with `unresolved: 0`. Disposition distinctness is largely redundant (derived from the `(cycle,id)` pairs already checked); the *semantic* and SHA distinctness are not.

## New blocking findings

**C8-OPUS-B4.** `design-graph-state-v7.json` asserts `cycle7_review_status: PENDING` / `PASS_PENDING_INDEPENDENT_REVIEW`; `claim-ledger-v7.json` asserts `mechanically_supported: 11, unresolved: 0`. Cycle 7 in fact returned REJECT from both tools (agy 2 blocking; opus 3 blocking / 7 required / 2 unresolved). No predicate reads either v7 file — mutating `status` to `"FABRICATED"` or `mechanically_supported` to `999` is caught by nothing. No v8 graph/claim state exists.

**C8-OPUS-B5.** `qualification()` asserts `all_requirements_mechanically_validated: True`, `validation_gap_count: 0`. Directly refuted by B2, B3 and R1.

## Additional required findings

- **R2** — `ast_guard` never references `PREDICATES`, so coverage is unproven; it rejects only literal `return True` (`return 1` escapes); generator v8 is unscanned; `derive_B2`/`derive_R6` are dead (v5 overrides both) yet inflate `count` to 15.
- **R3** — no predicate binds the validator to generator reproducibility. This is why the suite reports PASS on a tree its own generator rejects.
- **R4** — both banked cycle-8 reports attest parent tree `1cb43347`, not the reviewed tree.
- **R5** — `alias.derived_cases` and `failure_matrix.alias_family_derivation.total` (both 18) are decorative; mutating either to 999 is caught by nothing.

**Advisory:** A1 the as-found worktree carries the two rewritten provenance files — the B1 bug fired in place; A2 `len(keys)==len(c["required_fields"])` is a near-tautology detecting only duplicates; A3 the cycle-05 A1 advisory row SHA-attests `validate_..._v5.py` itself.

## Verified sound

324 **is** census-derived (86 + 86 + 34 + 18 + 100), cross-checked against the matrix and the qualification minimum; the 6×3 alias axes are set-disjoint; all 16 outcomes map to real transitions with matching `requires_write`; the bridge summary truthfully binds measurement v2 (identical digest `b7f473d7…`, head `7fbc6413`, tree `4ea92265`); the historical final declaration is absent from prepared bindings and listed forbidden; the injected FAIL path is genuinely reachable; the 13 mutations are each isolated.

## Claim verdicts

| Claim | Verdict |
|---|---|
| CANONICAL_READINESS_DESIGN | CHALLENGED (B2) |
| MANIFEST_ACYCLICITY | SUPPORTED |
| PRODUCTION_INSTALLATION_DESIGN | CHALLENGED (B2) |
| POSTURE_SEPARATION | SUPPORTED |
| FUTURE_GO_CAPABILITY_GATE | SUPPORTED |
| DRY_INSTANTIABILITY_DESIGN | CHALLENGED (B1, R3) |
| NO_ACCESS_DESIGN | SUPPORTED |
| IMPLEMENTATION_QUALIFICATION_PLAN | REFUTED (B5) |

## Counts

**Blocking 5 · Required 5 · Advisory 3 (3 claims challenged, 1 refuted) · Unresolved 2** — cycle-07 `U1`/`U2` were never re-adjudicated, and `claim-ledger-v7` asserts `unresolved: 0` without evidence.

Acceptance requires all counts zero. They are not. Cycle 8 is the terminal budget boundary, so I am not recommending progression to implementation: the head is not regenerable from its own generator, and three PASS-labelled enforcement claims are demonstrably false.

One caveat on my own method: the `--check` pass I first observed in the reviewed worktree was an artifact of that worktree's already-rewritten provenance files. The clean-clone run is the authoritative one, and it fails.
