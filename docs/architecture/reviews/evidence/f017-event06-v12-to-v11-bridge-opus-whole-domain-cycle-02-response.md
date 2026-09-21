Write is disabled this session, so the arbitration record is delivered here.

# F017 Event 06 V12-to-V11 Bridge — Whole-Domain Opus Arbitration, Cycle 02

Reviewed committed bytes only at detached HEAD `02b8668c7be99a78b3dc3ee151f15b230437e0e5`, worktree clean, zero files edited.

**Safety attestation:** no checkpoint root resolved; no shard opened; no numerical inference; no authority or durable state created; no Event 06 identity consumed; Event 04/05/06 not retried or resumed; P1 attempt 2 not executed. All execution was bounded, in-memory, synthetic-fixture-only, `PYTHONDONTWRITEBYTECODE=1`. `PULSARMLX_MODEL_GGUF`/`PULSARMLX_GLM_GGUF` unset.

## Authority verified

| Item | Result |
|---|---|
| Impl head `7fbc6413` → tree `4ea92265` | matches |
| Evidence/Gemini head `83a463fd` | matches |
| Bridge digest `b7f473d7…c06cd` | **independently reproduced**, 42 fields |
| Source drift `7fbc6413`→HEAD | **zero** (non-docs diff empty) |
| Evidence `8f943e67`→HEAD | append-only: 6 adds, 0 mods, 0 dels |
| Manifest bindings | **15/15** byte-exact |
| Measured impl paths | **28/28** exact at both heads |

**Restored evidence bytes:** all 14 paths byte-identical across `8f943e67` ≡ `02ed1c53` ≡ HEAD. The sole delta is `index-restoration-v1.json` itself, which correctly did not exist at `8f943e67`. `8f943e67` is an ancestor of HEAD — no history rewrite. Treated as an index incident, not source drift, as instructed.

## Cycle-01 reconstruction — all four repairs proven

- **B-1** (no production adapter) — **REPAIRED.** `bind_identity_stage` adapts the real producer. Producer census is exactly congruent (12 report keys, 8 evidence keys); `access_census_sha256`←`access_journal_sha256`, `lease_owner`←installed `package_attempt_id`. The runtime seam yields the identical bridge digest.
- **R-1** (release on zero paths) — **REPAIRED.** 5 paths, each releasing exactly once.
- **R-2** (views not threaded) — **REPAIRED.** `close_bridge_package` now takes a sealed `ValidatedBridgeExecutionResult`; zero caller-supplied digest strings.
- **R-3** (lease_owner unbound) — **REPAIRED.** Even a self-consistent owner+lease_id co-substitution fails closed.

## Direct attacks — 46 executed, 46 fail-closed

14/14 provenance substitutions rejected; forged event-plan re-pointing rejected; 11 producer/report mismatches rejected; 4 owner substitutions rejected; 8 seal forgeries rejected; 2 execution-result forgeries rejected; 8 binding-chain attacks rejected; terminal and chain tampering rejected. Committed suite **12/12 pass**. All four qualifiers reproduce PASS with every banked number matching (42/25 fields, 20 fresh processes → 1 digest, 395 mutations, 14 substitutions, 4+1 release paths, all no-access counters zero).

## Claim verdicts

`C-BRIDGE-GEN-001` **ACCEPT** · `C-BRIDGE-PROV-001` **ACCEPT** · `C-BRIDGE-DIGEST-001` **ACCEPT** · `C-BRIDGE-LEGACY-001` **ACCEPT** · `C-BRIDGE-CALLPATH-001` **ACCEPT** · `C-BRIDGE-LIFE-001` **ACCEPT** · `C-BRIDGE-CAP-001` **ACCEPT** · `C-BRIDGE-DRIFT-001` **ACCEPT** · `C-BRIDGE-QUAL-001` **ACCEPT** · `C-BRIDGE-CI-001` **UNRESOLVED** · `C-BRIDGE-SAFETY-001` **ACCEPT**

## The finding (CI/evidence-head mismatch attack)

C-BRIDGE-CI-001 reads: *"Exact-head FULL_NATIVE **and final manifest-bound EVIDENCE_ONLY** CI pass…"*. The FULL_NATIVE half is fully bound (`33141124246`, 4 corroborating artifacts). The EVIDENCE_ONLY half has **no committed artifact at all** — runs `33142278211` and `33143982465` appear only as prose in the request document that is itself under review. No `…bridge-evidence-only-ci-*.json` exists and the authority manifest binds none, while the wider Event 06 domain does bank exactly these records (`f017-event06-v12-evidence-only-ci-history-v1…v7.json`). The gap is systematic: cycle-01's `33138365702` is likewise unbound, and both cycle-01 Opus and cycle-02 Gemini passed CI-001 without verifying it.

Not REJECT — the runs may well have passed; I cannot disprove them. UNRESOLVED is exact: the claim is unadjudicable from committed bytes.

**Blocking: 0. Required: 1. Unresolved: 1.** These are one root defect counted twice by register — the missing artifact is the required remediation item, and the claim it blocks is the unresolved adjudication.

## Non-blocking observations (explicitly not counted)

1. `release_view` sits outside the release guard in `execute_consumers`; a forced raise there leaks leases (measured: `release_calls=0`). Unreachable at committed bytes — its inputs are already sealed. Post-release failures still release exactly once (measured: `release_calls=1`).
2. `validate_package_terminal` shape-checks the three chain digests without re-verifying them; three tamper cases held open. Only ever called on coordinator-derived values, so unreachable.
3. Banked `failure-qualification-v2.json` declares schema `1.1.0`; the producer emits `1.0.0`. `qualification-v2.json` renames `numerical_and_result_drift` into two fields and omits two others. Every shared field value agrees exactly.

## Invalidation dispositions

Cycle-01 findings B-1, R-1, R-2, R-3: **all invalidated by the repair** — each independently re-attacked and disproven as still-live. Cycle-01's ACCEPT of C-BRIDGE-CI-001: **not sustained** on fresh review.

The bridge implementation is sound and the GO boundary is technically defensible on the merits, but the verdict condition is conjunctive and fails on evidence bindings alone.

Smallest unresolved claim: `C-BRIDGE-CI-001`.

`REJECT`
