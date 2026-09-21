# F017 Event 06 — V12 Whole-Domain Arbiter, Cycle 5 (Final Hardening)

**Reviewed head** `99b8cb08c31060caecb8cd532003f5699fd3c3b1` · **tree** `f8bbd50858eafb5e24e0b4e3697557af9257a568` · fresh detached read-only clone, clean before and after. No file modified, no original checkpoint root opened, no authority minted, no Event 05/06/P1 action taken.

## Verification of the twelve required items

**1. Validator SHA and fail-closure — CONFIRMED, with a corrected digest.** The committed blob of `f017_event06_readiness_authority_v1.py` hashes to `d1ee8b80…ba4bc8`, exactly as stated. The tombstone check sits at lines 94–96, strictly *before* `read_artifact` at line 97 — it fail-closes on the source digest prior to any parsing.

The request's superseded-declaration digest is wrong. The committed blob of `…declaration-v12-v1.json` hashes to `eca5b5d3b56a019b03654987eab512951afc08c52d805540c53e8ce77e2cdf0d` — which is precisely the constant in `SUPERSEDED_DECLARATION_SHA256S`. The request's `eca5b5d3ad1c669e…6f2cb840` shares only the 8-hex prefix and appears nowhere in the repository. **The code is correct; the request text is not.** No committed byte is falsified.

**2. No alias, fallback, or permissive path — CONFIRMED.** The diff adds only the frozenset, the fail-close, and reuse of the computed digest. I ran an independent 30-mutation battery against the typed contract (unknown key, key removal, key rename-to-alias, bool/int confusion, float-for-int, uppercase and non-hex digests, short git objects, absolute and traversal paths, every predicate flip, schema and verdict substitution, non-dict roots): **30/30 rejected**. The contract is closed (`unknown_keys_permitted: false`), with a 47-field census exactly equal to the type census.

**3. Regression v8 — REPRODUCED.** I reran the targeted suite: **24 passed, 0 unexpected**, including `test_superseded_event06_readiness_declaration_cannot_mint`. Matches v8 field-for-field.

**4. Exact-head FULL_NATIVE — CONFIRMED.** Run `33124907328` at `5b98e53e`/`e2759047`, `result: PASS`, `required_native_skips: 0`, `unexpected_skips: 0`, `original_checkpoint_access: 0`.

**5. Raw qualification output — BYTE-IDENTICAL.** I re-executed the qualifier from committed bytes; output hashes to `9c8b09e93da2…55ba7d`, identical to the banked artifact and equal as a decoded object.

**6. Synthetic v8 / failure v9 / rehearsal v9 — CONFIRMED.** All three bind `5b98e53e`/`e2759047`, all report zero original-checkpoint access, `event_06_executed: false`, `live_event_06_authority_created: false`.

**7. Manifest v8 — 29 bindings, all recomputed clean.** `binding_count` matches `len(bindings)`; every one of the 29 files exists and its SHA-256 reproduces. It binds measurement v7, FULL_NATIVE v6, CI history v5, the cycle-4 normalized result, the raw qualifier output, current runtime bytes, and contracts. Every bound evidence artifact is the latest of its family; the superseded declaration is **not** bound. Measurement v7's own 25 paths and 6 historical bindings also fully reproduce.

**8. Evidence-only run `33126063555` — NOT IN COMMITTED BYTES.** Neither the run ID nor the reviewed head `99b8cb08` appears anywhere in the repository. This is structural, not untruthful: `99b8cb08` is the commit that *banks* the evidence, so a run covering it cannot exist inside it. Critically, `99b8cb08` changes **only** the eight evidence JSONs — zero execution bytes differ from the FULL_NATIVE'd head `5b98e53e`. Cycle 4 faced the identical situation (disclosure D1) and its successor CI history v5 duly appended the missing run, validating the disposition. See disclosure below.

**9. Cycle-4 evidence immutable — CONFIRMED.** Response and normalized result each have exactly one commit in history (`2e80e67b`), never modified. 16 accepted, 0/0/0. Since cycle-4's reviewed head `cdae4b1b`, the **only** non-evidence changes are the validator and its test — every other change is an *addition* (no `M`, no `D`). Append-only holds.

**10. Producer surface — EXACT.** `produce(authority, *, package_attempt_id, package_durable_start, evidence_directory=None)`. No var-positional, no var-keyword, no callable parameter. Module contains no `getattr`/`setattr`/`eval`/`exec`/`importlib`/`subprocess`/`socket`. `validate_capability()` returns PASS with `producer_signature_drift: 0`, `caller_callback_parameters: 0`. No v12 runtime module has a `__main__` block — Event 06 cannot be triggered by execution.

**11. Candidate SHA — REPRODUCED 20/20 at the reviewed head**, `94008a7d522d…812e6639`, unique across all fresh processes. Rehearsal v9 reports candidate triple, installed triple and `package_start_eligible: true` with every side-effect counter zero. **However**, see the non-blocking finding: the *recorded procedure* in instantiability v2 no longer executes.

**12. Lifecycle — CONFIRMED.** Event 05 postmortem: `TERMINAL_POST_PACKAGE_START_FAILURE_NO_RETRY`, ledger 175→175. Across all committed bytes, uniformly: ledger `175` (278 occurrences, no other value), `event_05_retry: false`, `event_06_executed: false`, `event_06_package_started: false`, `live_event_06_authorization_created: false`, `p1_attempt_2_executed: false`. Zero original-checkpoint access in every accounting record. No P1-attempt-2 artifacts. Go template inert (`approval: false`, `operator_go: null`, `FRESH_HUMAN_GO_REQUIRED`).

## What the tombstone actually fixes

I confirmed the change is substantive, not cosmetic. Disabling the tombstone in memory, the stale v12-v1 declaration **validates and returns `ready_go = True` at superseded head `45647e1a`** — the validator checks a declaration against *its own* bound manifest, never the current one. The tombstone is the sole barrier. This is exactly cycle-4 disclosure D2, and support ledger v13 records its disposition truthfully as `SUPERSEDED_DECLARATION_SHA_REJECTION_IMPLEMENTED_BEFORE_FINAL_DECLARATION`.

The SHA denylist is adequate for the stated concern. The bounded decoder enforces canonical bytes (`sort_keys`, `(",",":")`, `ensure_ascii`, trailing newline, `raw != expected` → reject), so semantic content maps to exactly one accepted byte string — a re-serialized variant is rejected as non-canonical, which I verified directly. Once v12-v2 is banked, exactly one declaration will validate.

## Claim verdicts

`C-SCOPE-001` **ACCEPT** · `C-SCOPE-002` **ACCEPT** · `C-INTERFACE-001` **ACCEPT** · `C-VALIDATE-001` **ACCEPT** · `C-VALIDATE-002` **ACCEPT** · `C-VALIDATE-003` **ACCEPT** · `C-RUNTIME-001` **ACCEPT** · `C-RUNTIME-002` **ACCEPT** · `C-FAIL-001` **ACCEPT** · `C-FAIL-002` **ACCEPT** · `C-FAIL-003` **ACCEPT** · `C-HIST-001` **ACCEPT** · `C-SYN-001` **ACCEPT** · `C-NOACCESS-001` **ACCEPT** · `C-CI-001` **ACCEPT** · `C-GO-001` **ACCEPT**

## Finding counts

**Blocking: 0 · Non-blocking-required: 1 · Unresolved: 0**

**NBR-1 — the tombstone renders a bound artifact's recorded procedure non-executable.** Instantiability v2 and approval v1 both route through `…declaration-v12-v1` (`declaration_sha256: eca5b5d3b56a…`), which the tombstone now rejects. Re-running claim 11's recorded procedure at the reviewed head raises `Event 06 readiness declaration superseded`. Instantiability v2 also records the pre-repair head `96377a31` and the pre-tombstone validator digest `ba32132f…`. Nothing it asserts is false — I independently reproduced its candidate SHA 20/20 from current bytes, and it self-labels `PASS_FOR_INPUT_REPRODUCIBILITY_PENDING_SUCCESSOR_FINAL_DECLARATION`. **Required action:** bank a successor instantiability bound to the v12-v2 declaration at the current head when that declaration is minted. Not blocking: the certified candidate is provably invariant to this change.

## Disclosures (not findings — no committed byte is falsified)

- **D1 — the request's superseded digest is wrong.** `eca5b5d3ad1c…` vs. actual `eca5b5d3b56a…`. The committed code tombstones the correct artifact. Correct the request text, not the code.
- **D2 — evidence-only run `33126063555` is unverifiable from committed bytes,** and nothing committed asserts it. The reviewed head is evidence-only over the FULL_NATIVE'd head, so no execution byte is uncovered. The successor CI history should append it, as v5 did for `33123861938`.
- **D3 — the remedy is a SHA denylist, not the manifest-pinning D2 suggested.** It does not structurally prevent a *future* stale-but-self-consistent declaration from validating, since the validator still has no current-head anchor. `validate_execution_readiness`'s `expected=` parameter and append-only review are the compensating controls. Worth pinning at R19.
- **D4 — banking-time fields persist (cycle-4 D3 carried forward).** Rehearsal v9 adds `implementation_head`, `implementation_tree`, `producer_signature_drift`, `supersedes` and re-versions schema `12.0.0`→`12.0.8`; synthetic v8 re-versions `12.0.0`→`12.0.6`. I verified every added value is independently true and every substantive census value reproduces from the scripts.
- **D5 — manifest binds 6 contracts directly**; the other four current v12 contracts are covered transitively via measurement v7, all of whose 25 paths reproduce. Closure is complete, just layered.
- **Method note.** `scripts/research/statistics.py` shadows the stdlib under `PYTHONPATH=scripts/research`, breaking two unrelated environment tests. Pre-existing (commit `246e3da8`), unrelated to this change. All V12-adjacent suites: **238 passed**. Generator `--check`: PASS (`readiness_fields: 47`, `modeled_outcomes: 12`, `original_checkpoint_access: 0`).

## Global verdict

**`ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_06_EXECUTION_AUTHORIZATION_PREPARATION`**

The sole post-cycle-4 execution-byte change is a targeted, adequate remediation of the one gap cycle 4 disclosed, and it is enforced by bytes rather than asserted: the superseded declaration fails closed before parsing, the typed contract admits no permissive path under 30 independent mutations, the qualification chain reproduces byte-identically from committed bytes alone, and the candidate SHA reproduces 20/20. Manifest v8 truthfully claims no go — active generation `NONE`, `PREPARED_PENDING_FINAL_HARDENING_ARBITER`, `final_hardening_review_pending: true`. Event 06 is unexecuted with no live authority and no package start, checkpoint access is zero, Event 05 remains terminal and non-retryable, P1 attempt 2 is absent, and the ledger holds at 175.
