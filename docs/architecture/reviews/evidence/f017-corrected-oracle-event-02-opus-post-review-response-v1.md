All verification complete. Note: worktree creation was blocked by filesystem permissions (the repo is read-only), so I reviewed committed bytes via `git show`/`git cat-file` from the existing detached HEAD — no working-tree writes, no checkpoint shard access, no oracle execution.

---

# F017 Corrected Oracle Event 02 — Opus Final Post-execution Review

**Reviewed head:** `f69b7e3680d6a35bf5b43a596ee788417c2f2bfc` (`docs(f017): bank corrected oracle event 02 failure`)
**Review request head:** `fc590841a99fddfe71416b361924b54ca5877a58` (adds only the two review-request `.md` files)

## 1. Hash and authority binding recomputation — PASS

Every SHA in the authority block recomputes exactly from committed bytes:

| Artifact | Recomputed | Match |
|---|---|---|
| contract (`…scientific-access-v2.json` @`4e53703`) | `ae39f31c…f519046` | ✓ |
| operator approval | `aa02ee1c…a246b64d` | ✓ |
| live authorization | `553a4f31…3d50a8e04` | ✓ |
| checkpoint identity | `9c5c4532…8137e473` | ✓ |
| receipt | `63cf8bf4…e2f482e7d` | ✓ |
| event ledger entry | `f4877338…95303a44e4` | ✓ |
| terminal | `11a8cde6…2ab3c69a` | ✓ |

Code-identity bindings all hold **at the executing HEAD `4e53703`**, not merely at `b92ba90`: primary `2041c033…`, secondary `8c4f9fde…`, coordinator `301d4ed4…`, memory observer `f020302…`, geometry `a9037a42…`, numerical contract `7c22507f…`, manifest `34b65d58…`, catalog `135500cc…`. `b92ba90` and `2fc212f` are both ancestors of `4e53703`, which is an ancestor of `origin/feat/017-rust-native-inference-runtime`.

The request's two head values are reconciled by the approval itself: `implementation_ci_head: 2fc212ff…` and `execution_code_head: b92ba90…` are recorded as distinct fields. The contract and live authorization bind `b92ba90`.

**New GO nonreuse — PASS.** `approval_id: F017-CORRECTED-ORACLE-EVENT-02-OPERATOR-GO`, `new_go: true`, `prior_go_reused: false`, `prior_go_disposition: EXPIRED_BEFORE_MINT_ON_LOAD_BEARING_PREFLIGHT_FAILURE`. The event-01 evidence independently corroborates: `authorization_minted: false`, `oracle_event_ledger_delta: 0`, `go_disposition` string-identical. No prior GO was carried forward.

## 2. One-shot consumption, owned claim, durable start, no replay — PASS

- **One-shot:** `attempts=1, retries=0, resume=false` enforced in four independent places — validator L45, primary L130, coordinator claim, terminal record.
- **Owned claim:** `owner_pid 97871` uniform across claim, durable-start, checkpoint-identity, all 30 events, receipt, and terminal.
- **Durable start:** `durable-start.json` banked (O_EXCL | O_NOFOLLOW, 0o400, fsync file + fsync dir + descriptor-relative exact readback) at `started_ns 1787456185016835000`, **before** the first shard open at `…017334000`. Satisfies contract `checkpoint_identity.verification_occurs_after_durable_owned_event_start: true`.
- **No replay authority:** two independent guards. Validator L74 `safe_absent_root(auth["state_root"])` and coordinator L134 `if root.exists(): raise SystemExit`. The state root is now populated, so this exact live authorization is structurally unusable again. Re-minting requires the operator env gate plus a fresh approval whose `contract_sha256` matches.

## 3. Thirty checkpoint identity events and six shard identities — PASS

Sequences `0..29` contiguous, timestamps monotonic, no `FAIL_*`/`REJECT` event, exact 6×5 kind pattern (`OPEN_ATTEMPT → OPEN_RESULT → HASH_ATTEMPT → HASH_RESULT → CLOSE`). All six `HASH_RESULT` digests and sizes equal `checkpoint-identity.json`, which equals the authorization's `shards`, which equals the contract's `shards`.

Independent cross-check without reopening anything: all six digests and sizes are byte-identical to `docs/validation/glm52-checkpoint.json` (recorded 2026-08-07 under feature 016), whose `total_bytes: 238458632928` equals my sum of the six event sizes exactly.

Per-shard throughput derived from event timestamps is internally coherent — 1.73, 1.80, 1.81, 1.80, 1.82 GB/s on the five large shards over 133.14 s wall. This is consistent with real streamed SHA-256 over 238.5 GB, not with synthesized timestamps.

## 4. Absence of mappings, tensor use, per-layer output, logits, top-32, selected token — PASS

Textual sweep of all 37 committed event artifacts returns zero occurrences of `logit`, `tensor`, `mmap`, `mapping`, `first_use`, `layer`, `top_n`, `selected_token`.

More decisively, the absence is attested by machine-generated coordinator output rather than by mere non-commit. The receipt computes `sha(primary) if primary.is_file() else None`; it records `primary_result_sha256: null`, `secondary_result_sha256: null`, `access_census_sha256: null`. The coordinator itself observed those files not to exist at terminal time.

**The committed directory is the complete state root.** The coordinator can write exactly nine `bank(root/…)` targets plus the events directory. Committed: 7 of 9 + 30 events = 37 files, matching the commit's 37 event paths. The two absent (`access-census.json`, `comparison.json`) are banked only inside the `try` block past the child subprocesses. Child-produced `primary-result.json`, `secondary-result.json`, `primary-access-events/`, `secondary-access-events/` are absent and independently attested null by the receipt.

## 5. Primary failure reconstructed from `AUTH_SCHEMA` — PASS

Direct from source at the executing head `4e53703`:

- `scripts/research/f017_corrected_oracle_primary.py:24` — `AUTH_SCHEMA = "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/1.0.0"`
- `scripts/research/f017_corrected_oracle_primary.py:128` — `if auth.get("schema") != AUTH_SCHEMA … raise ValueError("live scientific-access authorization required")`
- `scripts/research/validate_f017_corrected_oracle_access_v2.py:7` — `SCHEMA = "…/2.0.0"`; the mint path (L129) preserves that schema, and the banked live authorization carries `schema: "…/2.0.0"`.
- `scripts/research/f017_corrected_oracle_secondary.py:24` — identical `1.0.0` constant, so the secondary would have failed identically.

Uncaught `ValueError` → exit 1 → coordinator L142 `check=True` → `CalledProcessError`, matching the receipt's error string verbatim, including the interpreter path and all six argv entries. Root cause is exactly as classified: the v2 authorization generation was never propagated into the producers' `AUTH_SCHEMA` constants, and no validator checks producer schema acceptance.

## 6. Failure preceded numerical execution; secondary never invoked — PASS

In `main()` target mode the ordering is: read authorization → geometry hash check (passes, `a9037a42…`) → **`StreamingCatalogSource.__init__`** → `execute(...)`. The schema check is the *first* statement in `__init__`, ahead of the access-event `mkdir` (L149), ahead of any `os.open` on a shard (L207), and ahead of `execute()`. The output file is created with `O_EXCL` only after `execute()` returns.

Timing corroborates: the last shard `CLOSE` at `…318078703000` to receipt `completed_ns …318153471000` is **74.8 ms** — interpreter startup and a fail-closed schema read, far too short for any checkpoint load or forward pass.

Secondary: the coordinator iterates `(primary, secondary)` in one `for` loop with `check=True`; the first iteration raised, so the second never executed. `process_invoked: false`, `disposition: NOT_STARTED_AFTER_PRIMARY_FAILURE`. Consistent.

## 7. Coordinator caught the child failure; exact chaining; no retry/resume — PASS

`except Exception` at L150 caught it; `result_state` remained its initialized `ORACLE_EXECUTION_FAILURE`. Exactly one receipt, one ledger entry, one terminal were banked, in that order, with correct forward chaining:

```
claim.json ─┐
durable-start.json ─┼─→ receipt.json (63cf8bf4…) ─┬─→ oracle-event-ledger-entry.json (f4877338…)
checkpoint-identity.json ─┘                        └─→ terminal.json (11a8cde6…) → both
```

`terminal.receipt_sha256` and `terminal.event_entry_sha256` both recompute exactly. `retry_permitted: false`, `resume_permitted: false`. `duration_ns` reconciles to the nanosecond (`133137392000`).

**56 of 56 adversarial cross-checks passed; zero failures.**

## 8. `oracle_event_delta: 2` truthfulness — TRUTHFUL, with one recorded ambiguity

The value is not free-floating. It is pinned in the frozen contract (`accounting.oracle_event_ledger_delta: 2`), hard-required by the authorizer (`validate` L50 raises unless exactly 2), and reproduced in the receipt and ledger entry.

The charging rule is recoverable from precedent, not from prose. Event 01 failed *before mint* and charged `oracle_event_ledger_delta: 0`. Event 02 minted and durably started, and charged 2. That establishes a **start-of-owned-event, whole-package** rule: opening the package spends both consumer slots, and since `attempts=1, retries=0, resume=false` and the state root is consumed, neither slot can ever be re-spent. Under that rule, 2 is truthful and errs conservatively — it over-charges relative to work performed and under-claims nothing. No scientific credit is asserted anywhere: `layers_completed: 0` and `result_artifact: null` for both consumers.

The ambiguity I am promoting (below, DEFENSE_IN_DEPTH #2) is that this per-event-versus-per-consumer rule appears in no committed schema, and the receipt/ledger `delta` values are unconditional literals in the coordinator rather than derived quantities.

## 9. Historical ledger 175, zero unexpected/fallback access, no P1 attempt 2 — PASS

**Ledger at 175.** Verified four ways: authorization binds `historical_master_terminal: 175` and `historical_master_ledger_sha256: aa98f5cc…` at mint; receipt records `175 / 175 / 0`; CI's independent evidence validator reports `historical_master_terminal: 175` at the reviewed head; and — strongest — **no writer exists.** The coordinator's only writes are `bank(root/…)` into the fresh state root and `bank_event` into its events subdirectory; the primary and secondary contain zero references to any historical ledger. Delta 0 is structurally guaranteed, not merely asserted.

**Unexpected/fallback access zero.** Corroborated structurally: the primary aborted before `self.event_root.mkdir()`, so no access-event directory could exist, and none does.

**No P1 attempt 2.** No attempt-02 artifact exists anywhere in the tree. The only `ATTEMPT-2` paths are synthetic tiny-full-model inert qualification states and a template validator — neither touches the real checkpoint. `p1_authority: PROHIBITED` in the authorization; `p1_attempt_2: PROHIBITED` in the approval; CI reports `attempt_2_authorized: false`, `native_event_count: 1`.

## 10. Evidence-only CI `32616025531` — PASS, zero native jobs

`headSha` = `f69b7e3680d6a35bf5b43a596ee788417c2f2bfc` (exactly the reviewed head), `push`, `success`, and the only run at that commit.

| Job | Result |
|---|---|
| Classify committed change | success |
| Evidence integrity | success |
| Documentation integrity | skipped |
| **Apple Silicon workspace baseline** | **skipped** |
| **Apple MLX small-fixture validation** | **skipped** |
| Closed F017 branch guard | skipped |
| CI aggregate status | success |

Mode `EVIDENCE_ONLY`; all 38 changed paths classified `EVIDENCE_ONLY`. The aggregate gate actively *enforced* `test "$BASELINE_RESULT" = skipped` and `test "$NATIVE_RESULT" = skipped`. Validator output: `native_builds: 0`, `checkpoint_opens: 0`, `append_only: true`, `regular_non_symlink: true`, `duplicate_keys_rejected: true`, `credential_scan: PASS`, `json_file_count: 38`, `result: PASS`. Zero native jobs executed.

## 11. Completeness and immutability

**Complete.** Every artifact the coordinator could have produced on this path is committed; the two coordinator artifacts and four child artifacts that are absent are each independently attested absent by the receipt or excluded by the exception path. The chain is unbroken and the root cause is reconstructible from source constants alone.

**Immutable.** All four commits are pure adds (`git show --name-status` yields only `A`). No event-02 path has ever been modified or deleted in any branch's history. Each artifact was written O_EXCL | O_NOFOLLOW at mode 0o400 with fsync of file and directory plus a descriptor-relative exact readback comparison at write time. CI independently confirmed `append_only: true` at the exact reviewed head.

---

## Findings

**BLOCKING: none.**

**NON_BLOCKING_REQUIRED: none.**

**DEFENSE_IN_DEPTH (6) — none affects acceptance:**

1. **`claim.json` and `durable-start.json` are byte-identical** (`ffd696e3…`), because coordinator L137 banks the same dict twice. This is by design and the duplication provides storage redundancy, not content redundancy — the "durable start" artifact carries no information independent of the claim. Recording so a future reviewer does not read the matching SHAs as a banking error.

2. **Accounting fields are literals, not measurements.** `historical_master_before/after/delta` and `oracle_event_delta` in the receipt, and `delta`/`historical_master_terminal` in the ledger entry, are unconditional constants in the coordinator source; they would emit identical values on any outcome, including full success. The values are independently justified (contract freeze, validator L50 hard-require, structural absence of any ledger writer, CI corroboration), but the artifacts themselves carry no measurement authority. Related: the per-event-versus-per-consumer charging rule behind `delta: 2` is established only by precedent from event 01, not by any committed schema.

3. **`pre_mint_qualification.report_sha256: e2d3bf66…`** in the operator approval resolves to no committed file. Non-load-bearing: that report was explicitly `"authorizing": false`, and the mint path consumed the *banked* preflight `83e7042714c7dc708747f75ca418a92dbf50a66b7b568439a38fa638fd81333d`, which is committed and hash-bound into the live authorization. Every hash in the load-bearing chain approval → live authorization → event resolves.

4. **`accounting.unexpected_access_count: 0` and `fallback_attempt_count: 0`** in the failure summary have no producing artifact — those fields live only in `access-census.json`, which was never created. They are corroborated structurally (the primary aborted before the access-event `mkdir`; no such directory exists) but are author assertions in form.

5. **Completeness of the committed state root is inferred, not attested.** No committed manifest declares "this directory is the complete state root." I established it by enumerating the coordinator's nine possible `bank` targets against the 37 committed files. A banked directory census would make this checkable without source analysis.

6. **The frozen contract's self-description is now stale.** `status: "PREPARED_NOT_AUTHORIZED_NOT_EXECUTED"` and `authorization.live_created: false` remain in `f017-…-scientific-access-v2.json`. These are correct as pre-execution declarations and are correctly not re-stamped (re-stamping would break the `contract_sha256` binding), but a reader must not mistake the contract for a post-execution status record.

---

## TERMINAL VERDICT

**ACCEPT_CORRECTED_FULL_CHECKPOINT_ORACLE_EVIDENCE**

Scope of this acceptance, stated explicitly:

- This accepts **the committed failure evidence only** — that the event occurred as recorded, failed where and how it is recorded, produced no numerical output, and is completely and immutably banked.
- This is **not** corrected-oracle numerical acceptance. No logits, top-32, selected token, per-layer output, or comparison exists. Nothing numerical has been validated because nothing numerical was produced.
- This is **not** rerun permission. `repair_under_current_go: PROHIBITED` and `rerun_under_current_authorization: PROHIBITED` stand. The state root is consumed, the live authorization is structurally unusable, and the operator GO is spent. A rerun requires the `AUTH_SCHEMA` repair, FULL_NATIVE CI on the repaired head, fresh independent review, and a new operator GO.
