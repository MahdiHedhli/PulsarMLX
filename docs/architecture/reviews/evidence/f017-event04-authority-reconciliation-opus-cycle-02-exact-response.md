# F017 Event-04 Authority Reconciliation — Opus Cycle 02

Reviewed at evidence head `f4ed7c4e`; worktree byte-clean throughout (all mutations in `/tmp` scratch, now removed). No Event 04 minted or executed, no shard payload accessed, no P1 attempt 2.

## 1. Original parser/coordinator mismatch — reconstructed

The stale `…scientific-access-v6.json` (authored at `10ebfcb1`, schema `6.0.0`, 14 bindings, **no** `source_of_truth`) was a self-consistent snapshot at *its own* authoring head that decayed as the implementation advanced:

| binding | stale V6 declared | exact bytes @ `b6bf0af3` | lag |
|---|---|---|---|
| parser | `be4a52a0…` (= parser @ `10ebfcb1`) | `c5b230d6…` | 3 revisions |
| coordinator | `5c80525f…` (= coordinator @ `3f71bac6`) | `89a1881e…` | 1 revision |
| authorizer / primary / secondary | `ead56e34…` / `1ba89035…` / `36a5d2b4…` | identical | none |

Exactly 2 of 14 diverged. Those two literals are what M15/M16 replay.

## 2–4. Independent SHA computation and measurement V5

From `git show b6bf0af3:<path>`: parser `c5b230d6…` (blob `47e16afb`), coordinator `89a1881e…` (blob `823b5646`). Both equal the V3 contract, correction V2, manifest V3, and rehearsal V2.

All **68** V5 entries verified independently — SHA-256 of exact Git bytes, `ls-tree` blob identity, non-symlink, unique path, uniform `LOAD_BEARING_ACTIVE_OR_RETIREMENT_AUTHORITY`, zero worktree drift. **0 discrepancies.** V4 parent binding `7f2d823d…` is byte-exact and identical at measurement head, evidence head, and worktree (V4 = 64 entries). Tree `4ba0b4f1…` confirmed via `rev-parse`.

## 5–7. Cross-artifact equality

All **20** scientific bindings, all **33** manifest authorities, the 5 declaration↔contract bindings, and every inert/measurement/scientific/rehearsal cross-reference: **0 failures**. Original declaration V1 (`5b5eb941…`, head `12d2b916`, `EVENT_04_GO = YES`) and correction V1 (`a9dcc78f…`) are preserved byte-exact and superseded append-only.

## 8–11. Mutation testing — Git bytes control

Committed suite: **23/23 rejected**. My own independent battery added 24 more. The decisive ones:

- Stale parser/coordinator with the measurement entry, declaration, manifest **and** every outer SHA re-derived → rejected at `measurement entry SHA`.
- Same, plus the *genuine historical* `git_blob_sha` forged in → still rejected.
- Head+tree repointed to a real prior commit, fully coordinated → rejected.

No coordinated envelope substitutes for exact Git bytes.

## 12–16. Runtime rebind, fixture, rehearsal

Parser production defaults now name measurement **V5** and scientific-access **reconciliation V3**; it **accepts V5 and rejects both V4 and V3**. `required_entries` = 61 (semantic model) + 7 (reconciliation additions), disjoint, **= exactly the 68-entry set**. Parent-byte binding enforced against real V4 bytes.

Inert V3: `live: false`, `INERT_FIXTURE`, key census identical to the interface's 65 keys — and `construct_candidate_from_inert` requires *every* non-schema field be supplied, so no inert value can be promoted.

Rehearsal V2 reran **PASS** under a `sys.addaudithook` file-open audit: **478 open events, 0 `.gguf` opens, 0 opens anywhere under the checkpoint root** (the real 236 GB checkpoint *is* present on this host). The declared `checkpoint_shard_opens: 0` / `payload_reads: 0` / `numerical_operations: 0` / `state_created: false` are independently proven, not merely attested. All load-bearing fields match the banked V2.

## 17–19. CI census and the Gemini disagreement

FULL_NATIVE `32731485003` @ `6d0f6543`, `required_native_skips: 0`, both native jobs `success`; the three `skipped` jobs are mode-gated non-native jobs. All 4 EVIDENCE_ONLY runs show `native_mlx_jobs_launched: 0` — and this is *structurally entailed* by committed workflow bytes: all four heads touch only `docs/architecture/reviews/evidence/`, and the native jobs are gated `if: mode == 'FULL_NATIVE' || 'UNKNOWN_DEFAULT_FULL'`. Evidence-descendant rule holds: **no measured path changed** between `b6bf0af3` and the evidence head.

**Gemini cycle 02 was factually correct.** I extracted census V2 at `b3892e6d` — run `32732801169` is genuinely absent. The *request* asserted coverage that did not exist; Gemini rightly deferred to repository bytes. Census V3 repairs this append-only: both V2 runs preserved **byte-identically**, `32732801169` (`0` native jobs, PASS) and `32732899687` added, V2 preserved on disk and bound by SHA `02f671a2…`, Gemini's exact response preserved, and — the substantive fix — `coverage_cutoff_head: 47acee7d` now *discloses* the structural limit that a census can never cover its own commit's CI run. **I independently judge the material disagreement resolved.**

## 20–21. Safety

No Event-04 authorization or execution anywhere (`event_04_authorization_created` / `event_04_executed` false in every artifact). The operator-go artifact is `INERT_TEMPLATE_NOT_OPERATOR_APPROVAL` with `event_04_authorization_permitted: false`. The one `live: true` document is a retired **generation-2** Event-02 artifact, inert against the V6 control path. P1 attempt 2 exists only as `TEMPLATE_FAILS_CLOSED_ORACLE_NOT_EXECUTED` / `executable_authority: false` — no execution, durable-start, or authorization evidence.

## Cycle-01 disposition — all six verified closed

D1 rebound (proven by execution) · D2 Git-anchored (M19–M21) · D3 complete 20/20 (M22–M23) · D4 census V3 · D5 corrected append-only — I confirmed `655212eb…` occurs *only* inside Gemini's own quoted claim and the correction, never as a real binding · D6 validator defaults rebound.

## Findings

**BLOCKING: 0 · NON_BLOCKING_REQUIRED: 0 · DEFENSE_IN_DEPTH: 5**

**DD1 — Validator never reads the measurement parent-byte binding.** `parent_measurement_manifest_path/sha256` appear nowhere in `validate_documents`; I zeroed them and the validator returned PASS. *Mitigated:* the runtime parser pins the path to V4 and verifies its bytes, so the pre-mint path is covered. Commit `b6bf0af3` added the field; the independent validator never adopted it.

**DD2 — Validator does not pin the measurement entry census.** Only the 14 `MEASURED_BINDINGS` must be present; dropping an unbound entry passes. *Mitigated:* the runtime parser requires the census to equal exactly the 68-path set.

**DD3 — Declarative scalars are unchecked.** The manifest's `implementation_measurement_head`, `implementation_tree`, `active_generation`, `event_04_executed`, the contract's `safety.*` and `status`, and the declaration's `readiness_disposition` all accept arbitrary values. They are attestations, not gates — but the manifest head/tree are trivially cross-checkable against the measurement and currently are not.

**DD4 — Two stale defaults survive in active production modules** (same class as D6, which was scoped to the validator). `validate_f017_corrected_oracle_access_v6.py:23` still names the *original* inert V6; `rehearse_f017_corrected_oracle_event04_v6.py:22` still names the *stale* scientific-access V6. Neither is load-bearing — the first contributes only a key census I verified is identical to V3's, and the second is overridden by the reconciliation wrapper — but both are misleading literals in measured, active files.

**DD5 — 6 of 20 scientific bindings are worktree-anchored only in the validator** (`accounting`, `active_generation`, `capability_policy`, `interface`, `lifecycle_model`, `numerical_contract`). All six are in fact present in measurement V5 and match Git today — so extending `MEASURED_BINDINGS` from 14 to 20 would close D2's remainder at no cost.

None of these permits a false binding, a stale authority, or an unauthorized mint. Every one fails closed at the runtime parser.

---

## Verdict

`ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_AUTHORIZATION_PREPARATION`
