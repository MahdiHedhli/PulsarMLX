All verification is complete. Worktree remained clean throughout.

## F017 Event 06 V12 Whole-Domain Arbiter — Cycle 4

### Preconditions

| Check | Result |
|---|---|
| HEAD | `cdae4b1bc814516be243f6004a50714100c4f54f` ✅ |
| Tree | `58cdeab997f595aa577a82b9fa9f82ad99601fe1` ✅ |
| Detached | ✅ |
| Worktree clean (before and after) | ✅ |

**Method disclosure:** I reviewed in the provided detached read-only checkout rather than minting a second clone; HEAD, tree, and cleanliness were verified before and after, and `git status --porcelain` stayed empty at every step. Per R15 items 5–16 I *executed* committed validators (capability policy, candidate builder, qualifier, rehearsal) — all reads plus process-local temp state only. No repo file was written, no checkpoint shard touched, no authority banked, no Event 06/05/P1 action taken.

---

### Cycle 3 findings — all seven verified

**BLOCK-1 — closed.** No committed artifact treats a pre-repair declaration as current authority. Manifest v7 sets `active_corrected_oracle_generation: NONE`, `result: PREPARED_PENDING_RENEWED_ARBITER`, and does **not** bind the declaration. The only four references to `…declaration-v12-v1` are instantiability v1 (superseded), instantiability v2 and approval v1 (both stamping it `HISTORICAL_PRE_REPAIR_…NOT_FINAL_GO_AUTHORITY`), and a historical request. Support ledger v12 records the next action as `SUCCESSOR_READINESS_DECLARATION_REQUIRED_AFTER_ACCEPTED_REVIEW`.

**BLOCK-2 — closed.** Manifest v7 declares `binding_count: 29`; there are exactly 29 keys, and **all 29 reproduce byte-exact** against committed blobs (zero mismatches). `implementation_head 96377a31…` / `implementation_tree 6fb7852b…` confirmed independently via `git rev-parse 96377a31^{tree}`. Producer, capability, authority, lifecycle, coordinator, authorizer, access validator, and readiness authority are all bound at current bytes.

**BLOCK-3 — closed.** Manifest v7 binds CI history v4; v4 binds v3 at `3c4c5e08…`, which reproduces exactly. v4 appends `33121755141` (head `bc9b7b18`), which is also manifest v7's `evidence_only_run` — the v6 inconsistency is gone. Three failed runs preserved, append-only intact. `EVIDENCE_ONLY` native jobs are zero *structurally*: in `.github/workflows/macos.yml` the evidence job is `ubuntu-latest` and every `macos-15` job is gated on `FULL_NATIVE`. See D1 for the one sub-assertion I could not verify.

**NBR-1 — closed.** Raw qualification v1 is committed. Synthetic v7 and failure v8 both bind `raw_qualification_sha256 9c8b09e9…` and `qualifier_sha256 f6d646ea…`; both reproduce exactly.

**NBR-2 — discharged on the Opus side by this cycle.** See D3 for the Gemini side.

**NBR-3 — closed, and independently exercised.** `produce` is exactly `(authority, *, package_attempt_id, package_durable_start, evidence_directory)`. I drove `validate_capability()` against a 14-case drift matrix: renamed `on_progress`, `*callbacks`, `**kwargs`, extra positional `cb`, literal `callback`, literal `progress`, `**callback`, `*progress`, pos-only `authority`, reordered kwonly, renamed `authority`, dropped `evidence_directory`, and **no `produce` at all** — every one raised `F017_V12_IDENTITY_CAPABILITY_DRIFT`. The `producer_signature_drift = 1` initializer makes it fail closed. Contract re-banked at `12.0.3` with `producer_signature_drift: 0`. Targeted suite is exactly **23** collected cases (statically enumerated); FULL_NATIVE `33122544355` ran it at the exact repaired head with `required_native_skips: 0`, `unexpected_skips: 0`.

**UNRES-1 — resolved.** Approval v1 exposes all seven required inputs. `sha256("F017-EVENT06-V12-FINAL-READINESS-VALIDATION-ONLY-PLAN")` = `cc735ec2…` ✅ and the declaration digest `eca5b5d3…` ✅ both reproduce. I rebuilt the candidate from approval v1's inputs alone in **20 fresh processes**: all 20 produced `94008a7d522d6216f05c92ffa7709c2941349db422680d2efe7e4f97812e6639`, matching exactly. Zero checkpoint access — `build_identity_candidate` never opens `checkpoint_root`.

---

### Independent verification

- **29/29** manifest v7 bindings and exact count ✅ · **25/25** measurement v6 paths and **6/6** historical bindings ✅
- **Qualification census reproduced from scratch.** I ran `qualify_f017_checkpoint_identity_authority_v12.py` fresh; its output is **byte-identical to banked raw v1** — zero differing keys. 90 terminals, 250 mutations rejected, 393 substantive failures, 12/12 outcomes, 0 unexpected passes, `generic_fallback: false`, all four checkpoint counters 0.
- **Rehearsal v8 reproduced.** Fresh run matches on every substantive field; the only deltas are banking metadata (see D3 note).
- Numerical V4 and V11 result-authority drift **0**; both artifacts byte-exact, last touched at historical commits `2e243077` / `53c114f7` ✅
- Event 05 terminal and non-retryable: `TERMINAL_POST_PACKAGE_START_FAILURE_NO_RETRY`, `event_05_retry: false`, `event_05_resume: false` ✅
- Event 06 unexecuted across **81** artifacts; no live authorization (36) or authority (12); no package start (7); `original_checkpoint_access: 0` across **334** files — the single nonzero is the historical Event 04 terminal result ✅
- P1 attempt 2 absent (198 files `false`); historical ledger **175** across **217** files ✅ (the `…ATTEMPT-2` directories are the inert native-tiny-full-model synthetic fixture, unrelated to P1)
- V10/V11 cannot mint Event 06: V10 accepts only `SYNTHETIC_QUALIFICATION`/`PRODUCTION_EVENT_04`, V11 requires `PRODUCTION_EVENT_05` ✅

### Claim verdicts

`C-SCOPE-001` ACCEPT · `C-SCOPE-002` ACCEPT · `C-INTERFACE-001` ACCEPT · `C-VALIDATE-001` ACCEPT · `C-VALIDATE-002` ACCEPT · `C-VALIDATE-003` ACCEPT · `C-RUNTIME-001` ACCEPT · `C-RUNTIME-002` ACCEPT · `C-FAIL-001` ACCEPT · `C-FAIL-002` ACCEPT · `C-FAIL-003` ACCEPT · `C-HIST-001` ACCEPT · `C-SYN-001` ACCEPT · `C-NOACCESS-001` ACCEPT · `C-CI-001` ACCEPT · `C-GO-001` ACCEPT

### Counts

Blocking: **0** · Non-blocking-required: **0** · Unresolved: **0**

### Disclosures (not findings — no committed byte is falsified by any of these)

**D1 — `33123861938` is not in committed bytes.** `git grep` finds no trace of it. Nothing committed asserts it either, so no artifact is untruthful; the run covering `cdae4b1b` is simply unbankable inside `cdae4b1b`. The next CI-history successor should append it. `C-CI-001` is scoped to exact-head FULL_NATIVE, which is fully satisfied by `33122544355` at `96377a31`/`6fb7852b`.

**D2 — the superseded declaration still passes the validator.** I executed `validate_execution_readiness` on `…declaration-v12-v1` at HEAD: it **validates**, returning `ready_go = True` at superseded head `45647e1a`. Supersession is asserted only in prose fields, not enforced by `f017_event06_readiness_authority_v1.py`, which checks the declaration against *its own* bound manifest rather than the current one. Blast radius is bounded — the candidate it builds derives every digest from current disk, so it binds the **repaired** producer, not the callback-bearing one, and no live authority exists — but R16/R19 should pin the validator to the current authority manifest before two declarations validate identically.

**D3 — Gemini coverage stops two repairs short.** The newest Gemini whole-domain result reviewed `bf27efa2`, predating both `ee1d5df6` (callback elimination) and `96377a31` (alias closure); R13's 4-cycle budget is exhausted (cycles 01–04 all banked). R16's Gemini binding will therefore carry pre-repair coverage — the graph routes that residue to R18 final ratification, which is exactly what caught the callback defect Gemini missed. Separately, rehearsal v8's `implementation_head`, `implementation_tree`, `producer_signature_drift`, `schema 12.0.7`, and `supersedes` are added at banking time, not emitted by the rehearsal script (which emits `12.0.0`); each is independently true, but they are asserted rather than measured by that artifact.

---

## Global verdict

**`ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_06_EXECUTION_AUTHORIZATION_PREPARATION`**

Every cycle 3 blocking finding is closed by enforcing bytes, not by assertion: the manifest now binds the repaired head with all 29 digests reproducing, the capability policy rejects the full alias/vararg/kwarg/rename/omission space and fails closed on a missing `produce`, the qualification chain binds its raw source and qualifier by exact SHA, and the instantiability artifact is now reproducible — I regenerated both the candidate SHA (20/20) and the entire qualification census (byte-identical) from committed bytes alone. Manifest v7 makes no go-claim: active generation `NONE`, result `PREPARED_PENDING_RENEWED_ARBITER`, cycle 3's REJECT preserved and bound. Event 06 is unexecuted, no live authority exists, checkpoint access is zero, Event 05 stays terminal, P1 attempt 2 is absent, and the ledger holds at 175.

**Next permitted action:** bank the canonical cycle-4 result successor from this response, then R16 — append-only declaration `v12-v2` with a manifest successor binding both reviewer results. Close D2 in that same step. Do not mint Event 06 authority.
