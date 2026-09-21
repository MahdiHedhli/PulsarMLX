All probes complete. Review posture verified: worktree clean, HEAD unmoved, no `__pycache__`, all execution against throwaway `git archive` extractions proven byte-identical.

---

# F017 Lifecycle V8 Causal Design — Opus Design Review, Cycle 05

**Posture.** Exact committed bytes at `0084e7e007e0ab05474973c32b865a95a67e0c69`, detached read-only worktree `/private/tmp/f017-v8-opus-c5.HIrx4s`. `git status --porcelain` empty before and after; no reviewed file modified; no `__pycache__` on tracked paths. All execution ran in throwaway extractions (`/tmp/f017c5exec`, `/tmp/f017c5gen`) proven byte-identical to the worktree first; all forged packages built in auto-cleaned `TemporaryDirectory`s. No original checkpoint shard opened. No Event-04 authority minted, no oracle executed, no P1 attempt 2. `qualify_f017_lifecycle_v8_design.py` deliberately **not** run — it rewrites banked evidence.

## Verdict

`REJECT`

One `BLOCKING`, two `NON_BLOCKING_REQUIRED`, seven `DEFENSE_IN_DEPTH`.

## Mechanical reproduction — all green

| component | result |
| --- | --- |
| `validate_f017_lifecycle_causal_design_v8.py` | `PASS` — 95 artifacts, 94 edges, 48 outcomes, 25 invariants |
| `construct_f017_lifecycle_v8_symbolically.py` | `PASS` — **48/48** outcomes, 1223 artifacts, max closure depth 48, 0 cycles/self/future refs |
| `test_f017_lifecycle_causal_design_v8.py` | **10/10 OK** (179 static + 26 runtime = 205 rejected mutations) |
| generator determinism | re-run into a fresh extraction reproduces all committed contracts **byte-identically** |
| banked qualification | matches my run exactly (95/94/48/1223/48/25/179/26/205/238,458,632,928) |
| durable-prefix immutability | suite now asserts **all 1128 prefix artifacts across all 47 failure outcomes** — I independently recomputed 1128 |

**Adversarial sweep: 122 probes across 8 batches.** Every probe repaired dependency SHAs *and* every `ARTIFACT_SHA256`/`ARTIFACT_SHA256_SEQUENCE` restatement to a fixed point except the field under test, so each rule was isolated rather than shadowed by the digest chain.

## Cycle-04 findings: independently re-attacked

| # | status on `0084e7e0` | evidence |
| --- | --- | --- |
| **N1** descriptor identities value-free | **CLOSED** | All four exploits rejected with the forgery propagated to both continuity reports: shared `(device 7, inode 7)`; all `size: 1`; ints-as-strings/null times; `lease_id: ""`. Also rejected: bools-as-ints, float sizes, permuted sizes, duplicate lease ids, `[{}]×5`, reversed ordinals, wrong role. `sizes` is genuinely derived from the sha-bound `glm52-checkpoint.json` in generator, validator and constructor — drifting or dropping it fails `PAYLOAD_RULE_EXACT_SEMANTICS`. |
| **N2** blocked classifications on success | **CLOSED — but over-applied → BLOCKING 1** | `ORACLE_DISAGREEMENT` / `ORACLE_EXECUTION_FAILURE` on `COMPLETE_SUCCESS` now rejected, derived from `numerical_contract./future_p1_consequence` (sha-verified at line 241 *before* it is read at 283). Re-widening the ENUM in the design fails closed. |
| **N3** `unknown_leases` absorbs the census | **CLOSED — but over-tight → NON_BLOCKING 1** | 14-combination sweep: `5/0/0/5`, `5/3/1/1`, `0/0/0/0`, `42/42/0/0`, `10/5/5/0`, `4/4/0/0`, `6/5/1/0`, bool-as-int, negatives, forged `live_leases`, zero-lease-capsule-with-7-closures — **all rejected**. Positive probes `5/5/0/0`, `5/4/1/0`, `5/0/5/0`, `0/0/0/0` on a zero-lease capsule — all still pass. |
| **N4** 15 unbound identifiers | **CLOSED — residue in NON_BLOCKING 2** | Rule-kind census confirms **0 remaining `TYPE`-only rules** (was 15). All ten cycle-04 exploits rejected, each by the intended rule: `payload envelope equality mismatch` ×3, `payload artifact equality mismatch` ×5, `payload nonempty string mismatch` ×2. Also rejected: `operator_approval_id: 0`, `owner_nonce: null`, `owner_nonce: []`. |
| DiD 1 `critical_constants` allowlist | **CLOSED (by the override ladder, not the census) → DiD 3** | All 11 coordinated `dag`+`schemas` pins across the eight formerly-escaping artifacts are rejected; adding *or removing* a constant anywhere, including on census-exempt capsules, access events and shard receipts, fails closed. |
| DiD 7 hardcoded mutation counts | **half closed → DiD 5** | The qualifier now imports `STATIC_DESIGN_MUTATIONS` / `RUNTIME_CLOSURE_MUTATIONS` from the suite, so suite and evidence can no longer disagree. |
| DiD 8 one-pair byte identity | **CLOSED** | Generalised to all 47 outcomes × 1128 artifacts, keyed off `durable_prefix_rank`. |
| DiD 2 / 3 / 5 / 6 / 9 / 10 / 11 | **carried** | see DEFENSE_IN_DEPTH 1, 2, 4, 6, 7. |

**No structural regression.** 20 re-attacks from cycle-04's confirmed-rejected list all still fail closed: capsule deletion, stray file, planted `final_declaration`, prefix deletion, prefix relabelling in both directions, `event_04_executed: True`, `mandatory_stop: False`, forged `package_terminal.classification`, noncanonical bytes, duplicate JSON keys, zeroed root-authority sha, `layers_completed: 92`, `synthetic_only: False`, forged `creation_rank`.

---

# BLOCKING

## B1. The comparison ENUM is conditioned on the artifact, not the outcome — `ATTEMPT_2_BLOCKED` is now unrecordable in all 48 legal outcomes

Cycle-04 N2 asked to *"restrict the `ENUM` **on `COMPLETE_SUCCESS`-applicable nodes**"*. `comparison_receipt` is a single node applicable to **eight** outcomes, so restricting the node restricted all eight. The commit replaced the five-member vocabulary with a three-member one globally (`generate_…:105`, `validate_…:295`).

Exhaustive probe over every outcome whose durable prefix banks `comparison_receipt`:

| outcome | `classification: ORACLE_DISAGREEMENT` |
| --- | --- |
| `COMPLETE_SUCCESS` | rejected — correct, this is the repair |
| `COMPARISON_FAILURE__AFTER_RANK_041` | **rejected** |
| `COMPARISON_FAILURE__AFTER_RANK_042` | **rejected** |
| `EVIDENCE_BANKING_FAILURE__AFTER_RANK_043…047` (5) | **rejected** |

**8/8 unbankable.** `ORACLE_EXECUTION_FAILURE` behaves identically. `comparison_receipt` is the sole carrier of the numerical verdict: `comparison_terminal.classification` merely equals it, `package_terminal.classification` is the pinned constant `COMPLETE_SUCCESS`, and every capsule's `classification` is its own pinned outcome class (`COMPARISON_FAILURE`, …) — a failure label, not a numerical verdict. `grep` confirms **no V8 lifecycle contract mentions either name anywhere**.

This is a regression: at `d834a67d` the ENUM carried all five members, so `COMPARISON_FAILURE__AFTER_RANK_041` — whose `last_completed_artifact_id` *is* `comparison_receipt` — could record the disagreement it is named for.

**Failure scenario.** The comparator at rank 41 observes `STRUCTURE_OR_NUMERICS_EXCEED_FROZEN_CONTRACT`. There is no conforming artifact it may write. Its only legal move is to not write rank 41 at all, terminating as `SECONDARY_POST_START_FAILURE__AFTER_RANK_040` — an outcome that attributes the failure to the secondary consumer and records nothing about the numerical result. The bound root authority maps that verdict to `future_p1_consequence: ATTEMPT_2_BLOCKED`; the design can no longer produce durable evidence for it, so a downstream reader of the banked package never sees the gate. **The repair closed a false-success hole by deleting the blocking signal — the safety-adverse direction.**

The suite added `BLOCKED_DISAGREEMENT_ON_SUCCESS` and `BLOCKED_EXECUTION_FAILURE_ON_SUCCESS` as negative probes and `test_top1_uncertainty_is_success_compatible` as a positive one, all three on `COMPLETE_SUCCESS`. Nothing probes a failure outcome, which is why the over-restriction passed qualification.

**Repair.** Condition on the outcome, not the artifact. `validate_package` already receives `outcome` and already uses `outcome_applicability`; thread it into the ENUM check so the three-member set applies only when the package's terminal is `final_declaration`, and the full five-member set applies otherwise. Both halves must be derived from `numerical_contract./future_p1_consequence` (the machinery added in this commit), not restated. Then add the missing **positive** probe — `ORACLE_DISAGREEMENT` on `COMPARISON_FAILURE__AFTER_RANK_041` must be **accepted** — alongside the existing negatives; its absence is what let this through.

If instead the intent is that a numerical disagreement should have its own terminal outcome class, that adds capsules and changes the 48-outcome census, so it is a V9 change and must be recorded as such rather than left implicit.

---

# NON_BLOCKING_REQUIRED

## N1. `unknown_leases` is hard-pinned to zero by the checker while the frozen contract declares it a free counter

`check_…:118-121` raises unless `payload["unknown_leases"] == 0`. Every one of the 47 capsules declares `payload_rules["unknown_leases"] = {"kind": "NONNEGATIVE_INTEGER"}`, and `test_identity_prefix_release_is_exact_and_never_duplicated` **asserts that rule** for six capsules. The contract and the reference checker actively disagree about the field's domain.

| forged capsule | verifier |
| --- | --- |
| 1-lease capsule, `attempted 1, successful 0, duplicate 0, unknown 1` — an honest "one lease could not be identified" | **FALSE-REJECT** |

An implementer building from the contracts writes that capsule, is rejected at bank time, and falls into `UNBANKED_TERMINALIZATION_FAILURE_HUMAN_STOP_NO_RETRY` — losing the whole evidence package for the outcome. Bounded because a lease-closure anomaly is not a safety gate and leakage is still bounded by the declared terminator, which is why this is not blocking.

The clause is also unnecessary. With `live_leases_after_release` pinned `0` and the new derivation `live == expected − successful − duplicate`, `successful + duplicate == expected` already holds, so every expected lease is discharged; `unknown > 0` can then only mean "closures attempted beyond the census", which is a harmless honest record. **The fourth clause `(expected_leases == 0 and attempted_closures != 0)` is dead for the same reason** — I confirmed the zero-lease-capsule-with-7-closures forgery is rejected by the `live` derivation, not by that clause.

**Repair.** Drop `unknown_leases != 0` and the dead zero-lease clause; the derived `live` rule carries the census. If zero genuinely is intended, declare it `EXACT_CONSTANT 0` in `payload_constants` on all 47 capsules so `PAYLOAD_CONSTANT_RULE_BINDING`, `SCHEMA_EXACT_BINDING` and the constants census carry it, and change the suite assertion accordingly. Either way add an explicit probe stating the chosen semantics.

## N2. The two oracle executions may share one `event_id`; all opaque identifiers may be aliased to a single string

The repair made `(device, inode)` pairwise distinct so five leases cannot name one file. It left the identity that matters more un-distinguished. Reproduced on `COMPLETE_SUCCESS` with full consistent rehashing:

| forged success package | verifier |
| --- | --- |
| all eight `primary_*` **and** `secondary_*` chain artifacts carry `event_id: "SINGLE-EVENT"` | UNCAUGHT |
| `package_claim.owner_nonce == operator_approval.operator_approval_id` | UNCAUGHT |
| `package_ledger_entry_id == owner_nonce == both event chains == "X"` | UNCAUGHT |
| whole chain `event_id: " "` (whitespace passes the non-empty test) | UNCAUGHT |

Both chains carrying one `event_id` is evidence consistent with a single execution reported twice — precisely what the dual-oracle comparison exists to rule out, and the same degeneracy class cycle 04 flagged for descriptors ("five descriptors pairwise indistinguishable are evidence consistent with one descriptor passed five times"). `owner_nonce` is an *exclusive-ownership* nonce; aliasing it to the operator approval id defeats its purpose. Impact is bounded because the two chains remain structurally separated by artifact id, creation rank, actor and independent ledger deltas — the same reasoning cycle 04 used to keep its N1 non-blocking.

**Repair.** One rule kind plus one package-level check, both reusing existing machinery: a negated variant of `EQUAL_ARTIFACT_PAYLOAD_FIELD` binding `secondary_durable_start.event_id ≠ primary_durable_start.event_id`, and a pairwise-distinctness check over the eight opaque identifier values in `validate_package`. Tighten `NONEMPTY_STRING` to reject whitespace-only values while there. Add the first and third rows above as negative probes, and keep "whole *primary* chain aliased to one value" (which I confirmed passes, correctly) as the positive probe.

---

# DEFENSE_IN_DEPTH

1. **`cycles: 0` is still a bare literal.** `check_…:155` returns `"cycles": 0` computed from nothing; `construct_…:165` reports `"artifact_cycles": 0` as a literal that `validate()` then checks as evidence; the banked qualification records `causal_artifact_dag: "ACYCLIC"` / `artifact_cycles: 0`. Acyclicity genuinely is constructive via strict rank decrease, so derive the counter or drop the claim. *(carried four cycles)*

2. **`test_cross_package_splice_and_artifact_cycle_fail_closed` still does not test an artifact cycle.** Its second half plants a self-dependency caught by `dependency census mismatch`. *(carried)*

3. **The new `UNDECLARED_PAYLOAD_CONSTANT` census is unreachable on the current design.** I probed all 11 payload keys of the eight artifacts outside `constants_checked`: the check fired **0/11** — every one is rejected earlier by the override ladder (`PAYLOAD_RULE_EXACT_SEMANTICS`). The suite's own new `COORDINATED_OPAQUE_ID_CONSTANT` mutation is caught by `PAYLOAD_CONSTANT_RULE_BINDING`, so nothing exercises it either. Cycle-04 DiD 1 is genuinely closed, but by the overrides, not the census — the census is future insurance that will only become load-bearing if an override is ever removed. Worth keeping; worth not crediting it in the evidence.

4. **`layers_completed: 79` is still a restated literal, and the generator still hardcodes the classification vocabulary.** The validator now derives the ENUM from the sha-bound numerical contract, but `generate_…:105` restates the three members and both restate `79`, though `TARGET_LAYERS_79` sits in the same contract's `uncertainty_derivation.factor_justification`. Half of cycle-04 DiD 5 closed. *(carried)*

5. **`RUNTIME_CLOSURE_MUTATIONS = 26` still reconciles only by reconstruction** (22 asserted attacks + 2 splice + 1 unknown-lease + 1 capsule-cleanup). `STATIC_DESIGN_MUTATIONS = 179` and `len(attacks) == 22` are asserted; the total 26 is not. Cycle-04 DiD 7 is half closed — the qualifier can no longer drift from the suite, but the number is still unverified. Likewise `cycle_05_findings_reproduced: "ALL_16"` in `qualify_…:25` is a hardcoded literal unchanged since the freeze commit `b56acbe4`; it refers to the *V7* cycle-05 reproduction and is never re-derived from `f017-corrected-oracle-v7-cycle05-findings-reproduction-v1.json`. In a V8 qualification file the name reads as a forward-dated self-assessment.

6. **Descriptor-release failures are still classified as evidence-banking failures.** `failure_class_for_rank` returns `EVIDENCE_BANKING_FAILURE` for ranks 43–47, covering the three cuts where lease closure itself fails. *(cycle-04 DiD 6, carried)*

7. **The nine-field descriptor census still has three semantically free fields, and the reference construction models an implausible filesystem.** `mode` and both timestamps are type-checked only: five identities may declare `mode: 0` or a directory `mode: 0o40755` (both UNCAUGHT) while carrying the pinned regular-file sizes, and negative `mtime_ns`/`ctime_ns` pass. Separately, `payload_for` now sets `device: ordinal`, so the reference package models the six checkpoint shards as living on five *different devices* — the cheapest way to satisfy `(device, inode)` distinctness, but not a state a single checkpoint directory can be in. The design rule itself is correct (POSIX file identity is the pair); only the exemplar is unrealistic. I confirmed the honest configuration — one shared `device`, distinct `inodes` — still passes.

8. **`primary_execution_evidence` and `secondary_execution_evidence` have byte-identical payloads.** Both are exactly `{"layers_completed": 79, "synthetic_only": true}`, both `EXACT_CONSTANT`, neither carrying `consumer_role`, an `event_id`, or any digest of the execution's output. Nothing binds `comparison_receipt.classification` to either. The lifecycle model delegates numerical content to the V3 contract, so this is arguably out of scope for a causal *artifact* model — but the design does pin `frozen_thresholds` and now derives the classification vocabulary from that contract, so it is half in scope already. Adding `consumer_role` to each and binding the classification to a digest of both would make the comparison evidence discharge rather than assert. Related to B1 and N2.

---

## Remediation order

1. **B1** — thread `outcome` into the ENUM check so the three-member restriction applies only to the success terminal; add the missing positive probe on `COMPARISON_FAILURE__AFTER_RANK_041`. *(blocking; must land before re-qualification)*
2. **N1** — drop `unknown_leases != 0` and the dead zero-lease clause, **or** declare `unknown_leases` an `EXACT_CONSTANT 0` and update the suite assertion.
3. **N2** — add distinctness for the two `event_id`s and pairwise distinctness across the opaque-identifier census; reject whitespace-only ids.
4. **DiD 1 / 2 / 4 / 5** — derive `cycles`, rename the splice test, resolve `layers_completed` and the generator's ENUM through `resolve_pointer`, assert the runtime total and re-derive the V7 reproduction count.
5. **DiD 6 / 7 / 8** — V9 candidates: a `DESCRIPTOR_RELEASE_FAILURE` class (renames three outcomes, so it churns the census), `mode`/timestamp semantics, and execution-evidence content.

Steps 2–4 are independent. Step 1 is the gate: **any required finding produces `REJECT` regardless of directional acceptance, and B1 is a safety-signal regression introduced by this commit.** The four cycle-04 `NON_BLOCKING_REQUIRED` findings are otherwise genuinely closed, and the mechanical suite, generator determinism and banked evidence are all sound.
