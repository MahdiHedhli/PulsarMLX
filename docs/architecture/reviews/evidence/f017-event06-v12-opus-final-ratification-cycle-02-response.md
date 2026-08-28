Verification complete. The clone is unmodified and every assertion has been independently reproduced.

## F017 Event 06 V12 — Final Committed-Byte Ratification, Cycle 2

**Reviewed head** `767266773e9c1551fbe9fc322abd1dcabd1ba92e` · **tree** `e12e35e819cf7955210778a772b86fb8fc6733c4` · fresh detached read-only clone, clean before and after. No file modified, no original checkpoint root opened, no authority minted, no Event 05/06/P1 action taken.

### Final-byte surface — all confirmed

| Artifact | Claimed | Measured |
|---|---|---|
| declaration v12-v2 | `33bf3456…a17e3d` | ✅ match, **47** fields exactly |
| authority manifest v9 | `382c9bf6…5d9f0d2` | ✅ match, **31** bindings, all recompute |
| readiness validator | `d1ee8b80…50ba4bc8` | ✅ match |
| instantiability v3 | `57c44e0a…ea64dd4b` | ✅ match |
| approval v2 | `5b1f602b…12caa1b` | ✅ match |
| superseded v12-v1 | `eca5b5d3b56a…7e2cdf0d` | ✅ match, denylisted |

Implementation measurement v7 binds head `5b98e53e`/tree `e2759047`; `git rev-parse` confirms the tree; its 25 paths + 6 historical bindings recompute (31/31). All 10 declaration path/SHA pairs resolve exactly. The real validator **accepts v12-v2** and **rejects v12-v1** with `Event 06 readiness declaration superseded` — raised on the source digest at lines 94–96, strictly before `read_artifact`.

**CI runs, verified live via `gh`:** `33124907328` PASS at `5b98e53e` with both native jobs *succeeded* and zero required skips; `33127220575` PASS at `e6cd4e27` and `33127339764` PASS at `767266773` — both with `Apple MLX small-fixture validation` and `Apple Silicon workspace baseline` **skipped** (native jobs zero), evidence integrity PASS.

### Cycle-1 findings — all closed

- **B-1** — CI history v1→v6 is append-only (each version a superset; v4/v5/v6 chain by verified `prior_history_sha256`), 22 runs, covering the lineage through the cycle-5 request `33126144298`. Every successful branch run it omits is a *native* run accounted for in full-native CI v1–v6. The two newer final-byte runs are verified live above. ✅
- **N-1** — Callback capability is **structurally absent**, not merely asserted. I ran an 11-case mutation battery against the real `validate_capability()`: baseline ACCEPTED; `*args`, `**kwargs`, `callback=`, `progress=`, renamed positional, reordered kw-only, pos-only marker, a helper with a callback arg, `getattr` dispatch, and removing `produce` **all** rejected with `F017_V12_IDENTITY_CAPABILITY_DRIFT`. Local regression v8 records 24 PASS — I reran the suite: **24 passed**. ✅
- **N-2** — Cycle 5 reviewed head `99b8cb08`, accepted all 16 claims, ACCEPT verdict; response SHA `a053170a…` matches its normalized result. ✅
- **N-3** — Raw qualification v1 hashes to `9c8b09e9…dfe55ba7d`; synthetic v8 and failure v9 each bind *both* it and qualifier SHA `f6d646ea…` (verified). ✅
- **U-1** — Candidate reproduced **20/20** in fresh processes at `94008a7d522d…7812e6639`, unique. Approval v2 + instantiability v3 expose the nonexistent root, authorization ID, package ID, plan material (`cc735ec2…`, which I recomputed from the literal string), declaration path+SHA, builder SHA, validator SHA, head and tree. ✅
- **U-2** — Both evidence-only runs exact and successful. ✅

### Instrumented validation-only battery (measured, not asserted)

Running the real entrypoints end-to-end with `open`/`os.open` hooked: candidate triple **PASS** (primary, secondary, identity producer), installed-auth triple **PASS**, receipt binding **PASS**, capability **PASS**, package-start eligibility **PASS**. Measured side effects — checkpoint root opens **0**, shard opens **0**, identity hash reads **0**, numerical operations **0**, IDs consumed **0**, state created **false**, live authority **false**, repository writes **0**.

I also confirmed the tombstone is **not evadable**: every non-canonical re-serialization of v12-v1 is rejected as `noncanonical JSON artifact bytes`, and every canonical one lands on the denylisted digest. Exactly one byte string carries v12-v1's semantics, and it fails closed.

### The causal dual binding — sound

The typed validator hard-requires `opus.non_blocking_required_findings == 0`, so cycle 5 (NBR=1) is structurally ineligible for `opus_result_path`; cycle 4 (0/0/0) is bound there. This is sound, on four independently measured grounds:

1. **The delta cycle 4 missed is exactly one hardening, and cycle 5 reviewed it at byte-identical state.** `cdae4b1b → 5b98e53e` excluding evidence = exactly two files (the validator and its test). `5b98e53e → 99b8cb08` excluding evidence = **zero changes**.
2. **Nothing executable postdates cycle 5.** `99b8cb08 → HEAD` is 11 files, every one an addition under `evidence/` — zero `M`, zero `D`.
3. **Cycle 5's sole NBR was causally un-closeable pre-declaration.** It required a successor instantiability *bound to the v12-v2 declaration*, which cannot exist before that declaration does. No zero-finding review of the final bytes could have existed at minting time — the dual binding is the only causally available construction, which the cycle-5 request anticipated in terms.
4. **The cycle-5 ACCEPT is cryptographically inside the chain, not outside it:** declaration → `authority_manifest_sha256` → manifest v9 binding #12 (cycle-5 normalized) → `response_sha256` → cycle-5 response bytes. Each link recomputed. The exact response is bound transitively by digest rather than as a 32nd manifest path.

The cycle-5 non-blocking-required action is **fully closed** by instantiability v3, and I reproduced its every claim from committed bytes.

### Lifecycle invariants

Numerical V4 and V11 result-authority drift **0** (measurement v7: `numerical_drift: 0`, `result_authority_drift: 0`, with the V4 numerical contract and V11 result-authority contract among the 6 historical bindings that recompute). Event 05 is `TERMINAL_POST_PACKAGE_START_FAILURE` with `event_05_retry: false` and next action `STOP_EVENT_05_NO_RETRY…`. Event 06 unexecuted (98× false), no package start (11× false), no live authority (45×/14× false) — and unlike Event 05, Event 06 has **no** installed-authorization, live-candidate, operator-approval or installation-receipt artifact at all. Original-checkpoint access uniformly 0. P1 attempt 2 absent (only `attempt-01` exists; both attempt-2 flags uniformly false). Ledger **175** with no divergent value. Go template inert.

### Disclosures (no committed byte falsified)

- Runs `33127090360`, `33127220575`, `33127339764` postdate CI history v6 and are asserted nowhere in committed bytes — structurally unavoidable, since a run covering a commit cannot exist inside it. All three verified live as successful with zero native jobs. Cycle 5's D2 set this precedent and v6 duly appended `33126063555`.
- Manifest v9 still reads `post_commit_instantiability_pending: true` / `non_blocking_required_findings: 1`, and support ledger v14 records NBR-1 as pending. Both were banked one commit *before* instantiability v3; they are truthful point-in-time records, and closure is carried by instantiability v3 itself. Bookkeeping, not a defect.
- Measurement v7 carries schema label `…/6.0.0` on a v7 file; full-native CI v3 is a byte-duplicate of v2. Cosmetic; neither is on the bound final surface.

### Finding counts

**Blocking: 0 · Non-blocking-required: 0 · Unresolved: 0**

### Verdict

**`ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_06_EXECUTION_AUTHORIZATION_PREPARATION`**

Every assertion in the required surface reproduces from committed bytes alone. The one gap cycle 1 could legitimately raise — that the declaration's typed reviewer binding predates the final hardening — is closed not by argument but by measurement: the hardening delta is two files, cycle 5 reviewed it at a byte-identical execution state, nothing executable postdates cycle 5, and cycle 5's acceptance is committed transitively by the declaration through manifest v9. The single residual action was causally impossible to complete before the declaration existed, and instantiability v3 completes it. This authorizes **preparation** only; `exact_next_safe_action` remains `REQUEST_FRESH_HUMAN_EVENT06_GO`.
