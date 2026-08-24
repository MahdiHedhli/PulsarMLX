# F017 Lifecycle V8 Causal Design — Opus Design Review, Cycle 04

## Context

The F017 corrected-oracle lifecycle design (V8) is a frozen, design-only causal artifact model:
95 artifacts, 94 dependency edges, 48 legal outcomes (`COMPLETE_SUCCESS` + 47 durable-prefix failure
variants), 25 safety invariants. It must be adversarially accepted before implementation begins.

Cycle 03 (`REJECT`, head `559fec05`) raised two `BLOCKING` findings:

- **B1** — every failure outcome retroactively rewrote its whole durable prefix, because `outcome` and
  `result` were envelope fields bound to the terminal outcome. Rank-1 `operator_approval` had different
  bytes in `COMPLETE_SUCCESS`, `…AFTER_RANK_022` and `…AFTER_RANK_047`, contradicting
  `path_timing.immutable_after_creation`, `EVIDENCE_APPEND_ONLY`, `attempts: 1 / retries: 0 / resume: false`
  and `dag.future_references_permitted: false`.
- **B2** — descriptor-continuity evidence was satisfiable with zero descriptors; `lease_ids` and
  `descriptor_identities` carried `TYPE: ARRAY` only, so `continuity.exact_comparison_to_lease_manifest`
  degenerated to `[] == []`, and the nine-field `descriptor_identity_fields` registry bound nothing.

Plus five `NON_BLOCKING_REQUIRED` (capsule closure counts anchored to nothing; ungated access-event ordering;
`critical_constants` an allowlist; free terminal `result`/`classification`; unbound digest restatements) and
nine `DEFENSE_IN_DEPTH`.

`d834a67d` ("preserve lifecycle v8 prefix immutability", on top of `af782a4d`) is the repair. This document
records cycle 04: an independent re-attack of every cycle-03 finding plus a fresh adversarial sweep, and the
work that remains.

**Review posture.** Exact committed bytes at `d834a67dde12df563f527e5fed38e85c1b43f62b`, detached read-only
worktree `/tmp/f017-v8-opus-c4.Eb9Nzs`. `git status --porcelain` empty before and after; HEAD unmoved; no
reviewed file modified; no `__pycache__` in the worktree. All execution ran against throwaway `git archive`
extractions (`/tmp/f017c4exec`, `/tmp/f017c4gen`) proven byte-identical to the worktree before use; all forged
packages were built in auto-cleaned `TemporaryDirectory`s. No original checkpoint shard opened, hashed, mmapped
or `pread`. No Event-04 authority minted, no real oracle executed, no P1 attempt 2 executed.
`qualify_f017_lifecycle_v8_design.py` was deliberately **not** run — it rewrites banked qualification evidence.

---

## Verdict

`ACCEPT_CHECKPOINT_IDENTITY_CAUSAL_DESIGN_V8_FOR_IMPLEMENTATION`

Zero `BLOCKING`, four `NON_BLOCKING_REQUIRED`, eleven `DEFENSE_IN_DEPTH`.

---

## Mechanical reproduction (all green on committed bytes)

| component | result |
| --- | --- |
| `validate_f017_lifecycle_causal_design_v8.py` | `PASS` — 95 artifacts, 94 edges, 48 outcomes, 25 invariants |
| `construct_f017_lifecycle_v8_symbolically.py` | `PASS` — 48/48 outcomes, 1223 real artifacts, max closure depth 48 |
| `test_f017_lifecycle_causal_design_v8.py` | **8/8 OK** (178 static design mutations + 13 runtime conformance attacks) |
| generator determinism | re-running `generate_f017_lifecycle_v8_design.py` into a fresh extraction reproduces all 12 committed contracts **byte-identically** |
| banked qualification | matches the run exactly (95 / 94 / 48 / 1223 / depth 48 / 25 / 238,458,632,928) |
| banked review evidence | all 10 `request_sha256` / `response_sha256` in the normalized results match their markdown byte-for-byte |

**Adversarial sweep: 175 probes across 9 batches; 32 uncaught, collapsing to 5 distinct defect classes**
(4 `NON_BLOCKING_REQUIRED` + 1 `DEFENSE_IN_DEPTH`). Every probe repaired dependency SHAs *and* every
`ARTIFACT_SHA256` / `ARTIFACT_SHA256_SEQUENCE` restatement in rank order except the field under test, so each
rule was isolated rather than shadowed by the digest chain.

---

## Cycle-03 findings: independently re-attacked

| # | status on `d834a67d` | evidence |
| --- | --- | --- |
| **B1** prefix relabelling | **CLOSED** | `outcome` is now `PENDING` on every non-terminal artifact and `result` is `PASS` on everything except `failure_terminal_capsule__*`; `package_attempt_id` no longer embeds the outcome; `payload_for` no longer interpolates it. Verified exhaustively: **1128/1128 prefix artifacts across all 47 failure outcomes are byte-identical to their `COMPLETE_SUCCESS` counterparts** (22/22 for `…AFTER_RANK_022`). Relabelling in either direction is rejected (B1–B8 probes), including a whole-prefix relabel. `schemas.outcome_field_semantics` / `result_field_semantics` are pinned and gated (`ENVELOPE_SEMANTICS`). |
| **B2** zero descriptors | **CLOSED** | `ARRAY_EXACT_LENGTH{5}` on `lease_ids`, `DESCRIPTOR_IDENTITY_ARRAY{length 5, ordinals [2..6]}` on `descriptor_identities` (nine-field census + `role == GRAPH_PAYLOAD`), plus a `descriptor_lease_manifest` semantic check binding `lease_count == len(lease_ids) == len(descriptor_identities)`, uniqueness, and positional `descriptor_identities[i].lease_id == lease_ids[i]`. Zero-array, short-array, `[{}]*5`, dropped field, extra field, wrong role, permuted ordinals, ordinal `1` (identity-only shard), duplicate and reversed lease ids — **all rejected, with the forgery propagated to both continuity reports and the release report** so the manifest rule itself fires. |
| N1 capsule closure counts | **mostly closed → residue in NON_BLOCKING 3** | `attempted_closures == expected_leases` is now enforced alongside `attempted == successful + duplicate + unknown`. `0/0/0/0` and `42/42/0/0` on a 5-lease capsule are rejected; a zero-lease capsule recording 7 closures is rejected (closes cycle-03 DiD 3); `sum < attempted`, negatives and `bool`-as-int are rejected. |
| N2 access-event ordering | **CLOSED** | `ACCESS_RECEIPT_CAUSAL_ORDER` in `validate_documents` requires `access_k.dependencies == [prior]`, `receipt_k.dependencies == [access_k]` and `rank(receipt_k) == rank(access_k) + 1` for k = 1…6. The cycle-03 drift is now caught by the **validator**, not only the suite (probes F1, F3). |
| N3 `critical_constants` allowlist | **mostly closed → residue in DEFENSE_IN_DEPTH 1** | Coverage is now 28 artifacts + the 12 identity artifacts + 47 capsules = 87 of 95. The cycle-03 exploit (pin `comparison_terminal.classification: NUMERICAL_MISMATCH`, `primary_terminal.result: FAIL`) is rejected (`CRITICAL_PAYLOAD_CONSTANTS`, `PAYLOAD_RULE_EXACT_SEMANTICS`). |
| N4 terminal `result`/`classification` | **mostly closed → residue in NON_BLOCKING 2** | `primary/secondary_receipt`, `primary/secondary_terminal`, `comparison_terminal` all pin `result: COMPLETE`; `descriptor_release_terminal` pins `PASS`; `layers_completed: 79` is pinned; `comparison_receipt.classification` is an `ENUM` over the numerical contract's exact five-outcome vocabulary; `comparison_terminal.classification` equals it. `FAIL`, `92`, `0`, `NUMERICAL_MISMATCH` and a desynced terminal are all rejected. |
| N5 digest-chain restatements | **CLOSED** | Ten new `ARTIFACT_SHA256` rules plus one `ARTIFACT_SHA256_SEQUENCE`. Each verified independently load-bearing with everything else repaired: empty/reversed/zeroed receipt-digest sequence, zeroed and mis-pointed `prior_event_digest`, zeroed `terminal_event_digest`, forged `installed_digest`/`candidate_digest`, and swapped install digests — **all rejected by the payload rule itself**, not by the dependency chain. A new default `SHA256` rule (any key containing `digest`) rejects non-hex and short values. |
| DiD 1 dead cycle detectors | **removed → see DEFENSE_IN_DEPTH 2** | Both DFS detectors deleted with an explanatory comment; acyclicity is genuinely constructive via strict rank decrease, enforced in both `validate_documents` and `validate_package`. |
| DiD 4 capsule-absent prefix | **CLOSED** | `interface.absent_capsule_after_process_exit = "UNBANKED_TERMINALIZATION_FAILURE_HUMAN_STOP_NO_RETRY"`, pinned and gated. |
| DiD 7 `cleanup_anomaly` dead vocabulary | **CLOSED** | removed from both boolean key sets. |
| DiD 2 path graph / DiD 5 release failure class / DiD 6 vacuous producer assertion / DiD 8 hardcoded census / DiD 9 phantom Gemini artifact | **carried** | see DEFENSE_IN_DEPTH 4, 6, 10, 7, 11. |

Also confirmed rejected: terminal-capsule deletion, second-capsule insertion, stray-file insertion,
`final_declaration` planted into a failure package, a prefix artifact passed as `terminal_id`, prefix deletion,
emptied capsule dependencies, capsule rank forgery, weakened `atomic_terminalization`, repointed
`durable_prefix_id`, `package_delta: 0`, `mandatory_stop: False`, `event_04_executed: True`, actor drift
(single and global), root-authority repoint/forge/add/remove, `retries: 1`, failure-class boundary drift,
schema key-set drift, envelope key reordering, noncanonical bytes, duplicate JSON keys, forged
`artifact_id`/`artifact_kind`/`creation_rank`, per-artifact root-census drift, and zeroed dependency SHAs.

---

# NON_BLOCKING_REQUIRED

## N1. Descriptor identity tuples are shape-checked but value-free — five leases may name one file, and sizes may contradict the pinned shard census

`DESCRIPTOR_IDENTITY_ARRAY` enforces length, the `shard_ordinal` sequence `[2,3,4,5,6]`, the exact nine-key
census, and `role == "GRAPH_PAYLOAD"`. It constrains no other value. Reproduced on `COMPLETE_SUCCESS` with the
forgery propagated to both continuity reports and the release report (so the equality rules also pass) — all
`PASS`:

| forged success package | verifier |
| --- | --- |
| all five identities share `device: 7, inode: 7` | UNCAUGHT |
| all five identities `size: 1` (contradicting the pinned per-shard `expected_size`) | UNCAUGHT |
| `device`/`inode`/`size`/`mode` set to strings, `mtime_ns`/`ctime_ns` to `null` | UNCAUGHT |
| `lease_ids: ["", "a", "b", "c", "d"]` with matching `lease_id` fields | UNCAUGHT |

Five descriptors that are pairwise indistinguishable are evidence consistent with one descriptor passed five
times — the terminal V7 `SECONDARY_SUCCESS_CONTINUITY_ZERO_DESCRIPTOR_ALLOWED` degeneracy one step removed.
No named invariant becomes unfalsifiable (`GRAPH_LEASE_COUNT`, `PRIMARY/SECONDARY_DESCRIPTOR_COUNT` and
`exact_comparison_to_lease_manifest` are all genuinely discharged now), which is why this is not blocking.

**Repair:** extend `DESCRIPTOR_IDENTITY_ARRAY` to (a) require `int` for `device`, `inode`, `mode`, `size`,
`mtime_ns`, `ctime_ns` and non-empty `str` for `lease_id`; (b) require `(device, inode)` pairwise distinct
across the array; (c) bind `descriptor_identities[i].size` to `checkpoint_shard_receipt_{ordinal}.expected_size`
(the shard census is already pinned from `glm52-checkpoint.json`). Add each as a negative probe.

## N2. The comparison enum admits the two `ATTEMPT_2_BLOCKED` classifications on a `COMPLETE_SUCCESS` package

`comparison_receipt.classification` is an `ENUM` over the numerical contract's exact five-member vocabulary,
and `comparison_terminal.classification` equals it. Nothing partitions that vocabulary by outcome. Reproduced
on `COMPLETE_SUCCESS`, both `PASS`:

| forged success package | verifier |
| --- | --- |
| `classification: "ORACLE_DISAGREEMENT"` on receipt and terminal | UNCAUGHT |
| `classification: "ORACLE_EXECUTION_FAILURE"` on receipt and terminal | UNCAUGHT |

The bound root authority `f017-corrected-full-checkpoint-oracle-numerical-contract-v3.json` maps both of these
under `future_p1_consequence` to `ATTEMPT_2_BLOCKED`. So a conforming `COMPLETE_SUCCESS` package can declare
the numerical verdict that blocks attempt 2 while `package_terminal.classification` is pinned
`COMPLETE_SUCCESS`, `comparison_terminal.result` is pinned `COMPLETE`, and `final_declaration` is banked.
(`TOP1_UNSTABLE_WITHIN_FROZEN_UNCERTAINTY` is legitimately success-compatible and is not part of this finding.)

**Repair:** restrict the `ENUM` on `COMPLETE_SUCCESS`-applicable nodes to the three members whose
`future_p1_consequence` is not `ATTEMPT_2_BLOCKED`, derived from the root authority rather than restated.

## N3. `unknown_leases` can absorb the entire lease census while `live_leases_after_release` stays a pinned `0`

The repair added `attempted_closures == expected_leases`, which kills the `0/0/0/0` and `42/42/0/0` forgeries.
It did not relate *which* counter absorbs the total to `live_leases_after_release`, which remains an
`EXACT_CONSTANT 0` — a self-assertion. Reproduced on `CHECKPOINT_IDENTITY_FAILURE__AFTER_RANK_022`
(`expected_leases: 5`), all `PASS`:

| forged capsule | verifier |
| --- | --- |
| `attempted 5, successful 0, duplicate 5, unknown 0` | UNCAUGHT |
| `attempted 5, successful 0, duplicate 0, unknown 5` | UNCAUGHT |
| `attempted 5, successful 3, duplicate 1, unknown 1` | UNCAUGHT |

`duplicate_closures` is benign (a duplicate close means already closed). `unknown_leases: 5` is not: it says
the releaser could not identify any of the five leases the package itself minted, and then asserts zero are
live. Cycle-03's proposed derivation (`live == expected - successful - duplicate`) would have caught this; the
implemented rule does not. Real leakage is still bounded by the declared terminator
(`NO_NEW_DURABLE_PREFIX_AND_PROCESS_EXIT_DESCRIPTOR_CLOSE`), which is why this is not blocking.

**Repair:** derive rather than pin — `live_leases_after_release == expected_leases - successful_closures -
duplicate_closures`, which with the pinned `0` forces `unknown_leases == 0` while leaving `duplicate_closures`
freely recordable. Keep the existing positive probe (`duplicate 1 / successful 0` must still pass) and add
`unknown 5` as a negative probe.

## N4. Every per-attempt identifier is unbound — all 15 remaining `TYPE`-only fields

The `TYPE`-only surface is down from 37 to 15, and all 15 are opaque identifiers. None is bound to anything.
Reproduced on `COMPLETE_SUCCESS` with full consistent rehashing, all `PASS`:

| forged success package | verifier |
| --- | --- |
| `candidate_authorization.payload.package_attempt_id != ` the envelope `package_attempt_id` | UNCAUGHT |
| `candidate_authorization.payload.authorization_id != ` the envelope `authorization_id` | UNCAUGHT |
| `installed_authorization.payload.authorization_id` drifted | UNCAUGHT |
| `primary_terminal.event_id != primary_durable_start.event_id` | UNCAUGHT |
| `primary_receipt.event_id` drifted | UNCAUGHT |
| all four `secondary_*` `event_id`s mutually distinct | UNCAUGHT |
| `package_ledger_entry.prior_entry_id` repointed | UNCAUGHT |
| `package_durable_start.package_ledger_entry_id` repointed | UNCAUGHT |
| `operator_approval_id: ""` | UNCAUGHT |
| `package_claim.owner_nonce: ""` | UNCAUGHT |

The `cross-package artifact splice` check gates only the *envelope* pair, so the payload restatements of the
same two identifiers are free. The four-artifact consumer `event_id` chain
(`durable_start → ledger_entry → receipt → terminal`) is what ties a banked receipt to the durable start that
incremented the ledger; today it is four independent strings. Impact is bounded because the real binding is
structural (artifact presence, rank, dependency SHA), which is why this is not blocking.

**Repair:** `EQUAL_PAYLOAD_FIELD`-style envelope binding for `payload.authorization_id` /
`payload.package_attempt_id`; `EQUAL_ARTIFACT_PAYLOAD_FIELD` for the two `event_id` chains and for
`package_ledger_entry.prior_entry_id → package_durable_start.package_ledger_entry_id`; a `NONEMPTY_STRING`
rule kind for the remaining opaque ids. All four use machinery that already exists.

---

# DEFENSE_IN_DEPTH

1. **`critical_constants` is still an allowlist, not a census.** Eight artifacts escape it —
   `operator_approval`, `candidate_authorization`, `installed_authorization`, `installation_receipt`,
   `package_claim`, `package_durable_start`, `primary_durable_start`, `secondary_durable_start` — and constants
   may be freely *added* to them. Reproduced by coordinated `dag`+`schemas` drift: pinning
   `package_claim.owner_nonce`, `operator_approval.operator_approval_id`,
   `candidate_authorization.authorization_id` or `primary_durable_start.event_id` to a literal passes
   `validate_documents`. A frozen design mandating a constant exclusive-ownership nonce is a real (if
   unattractive) drift. The two digest-bearing members are protected by their `ARTIFACT_SHA256` overrides.
   Making the census total with `{}` as the expected value closes this in one line per artifact. *(cycle-03 N3,
   materially narrowed from 95 to 8)*

2. **Both cycle detectors were deleted rather than reordered, and `cycles: 0` is now a bare literal.**
   Acyclicity genuinely is constructive — strict rank decrease is enforced in `validate_documents`
   (`FUTURE_REFERENCE`) and per-edge in `validate_package` (`noncausal dependency rank`) — so the deletion is
   defensible. But `validate_package` still returns `"cycles": 0` computed from nothing,
   `construct_…` reports `"artifact_cycles": 0` as a literal that `validate()` then checks as evidence, and the
   banked qualification records `causal_artifact_dag: "ACYCLIC"` / `artifact_cycles: 0`. With `visiting`
   removed, a hypothetical cycle would surface as `RecursionError`, not a `ValueError`. Either derive the
   counter or drop the claim. *(carried three cycles; the underlying dead code is now gone)*

3. **`test_cross_package_splice_and_artifact_cycle_fail_closed` no longer tests an artifact cycle.** Its second
   half plants a self-dependency on `primary_descriptor_continuity_report`, which is caught by
   `dependency census mismatch`. The name should change or the test should exercise what the name claims.

4. **The "causal DAG" is now a pure path.** Out-degree histogram is `{0: 1, 1: 94}` — the three
   multi-dependency bindings were removed in this commit (they had been deduplicated to no-ops).
   `CONTINUITY_DURABLE_START_BINDING`, `IDENTITY_RECEIPT_DEPENDENCY` and `PRIMARY_CONTINUITY_SELF_REFERENCE` are
   therefore chain-adjacency restatements, and the cross-branch splicing machinery has no branch to attack.
   *(cycle-03 DiD 2, carried; the design is now honestly a chain rather than a chain pretending otherwise)*

5. **Two authoritative literals are restated rather than derived.** The five-member comparison `ENUM` is
   hardcoded in the generator and the validator, though `numerical_contract./outcomes` is a SHA-bound root
   authority; `layers_completed: 79` is hardcoded in both, though `TARGET_LAYERS_79` appears in the same
   contract's `uncertainty_derivation.factor_justification`. Both are corroborated by a pinned authority, so
   drift is detectable — but the design already has `resolve_pointer` for exactly this.

6. **Descriptor-release failures are still classified as evidence-banking failures.** `failure_class_for_rank`
   returns `EVIDENCE_BANKING_FAILURE` for ranks 43–47, which covers `descriptor_release_start` (43),
   `descriptor_release_report` (44) and `descriptor_release_terminal` (45). The three cuts where lease closure
   itself fails are indistinguishable from banking failures. *(cycle-03 DiD 5, carried)*

7. **`static_design_mutations_rejected: 178` and `runtime_closure_mutations_rejected: 16` remain hardcoded in
   `qualify_f017_lifecycle_v8_design.py`.** The suite asserts `len(mutations) == 178`, so static drift is
   caught. Nothing asserts 16; it reconciles only by reconstruction (13 conformance attacks + 2 splice probes +
   1 capsule-cleanup probe). *(cycle-03 DiD 8, carried)*

8. **The byte-identity test covers exactly one outcome pair.**
   `test_durable_prefix_bytes_do_not_depend_on_future_outcome` compares ranks ≤ 22 for
   `CHECKPOINT_IDENTITY_FAILURE__AFTER_RANK_022` against `COMPLETE_SUCCESS`. The property in fact holds for all
   47 failure outcomes (1128/1128 verified in this review); the suite should assert the general case, since B1
   was the cycle-03 blocker.

9. **Test 5's rank tuple `((13,0),(14,1),(16,2),(18,3),(20,4),(22,5))` is still a literal.** It is now backed
   by the validator's `ACCESS_RECEIPT_CAUSAL_ORDER`, so the drift it guards fails closed independently — the
   literal is redundant rather than load-bearing. *(cycle-03 N2 closed; the restatement remains)*

10. **`construct_outcome`'s `actual != required` assertion is still vacuous in the producer** — it constructs
    exactly `required` and then checks it. It is meaningful in `validate_package`, where both planted and
    deleted artifacts are rejected. *(cycle-03 DiD 6, carried)*

11. **The Gemini cycle-04 acceptance still cites an artifact that does not exist.** The banked response claims
    an implementation plan in `f017_lifecycle_v8_review.md`; no such file exists in the tree or in any commit
    reachable from HEAD. The normalized result records zero findings, so nothing material is lost.
    *(cycle-03 DiD 9, carried)*

---

## Remediation plan (before V9 re-qualification)

All seven items reuse rule kinds and helpers that already exist; no new machinery is required.

### Files to modify

- `scripts/research/generate_f017_lifecycle_v8_design.py` — rule assignment in `node()` / `build_nodes()`
- `scripts/research/validate_f017_lifecycle_causal_design_v8.py` — `expected_default_rule`, the `override`
  ladder in `validate_documents`, `critical_constants`
- `scripts/research/check_f017_transitive_artifact_closure_v8.py` — rule enforcement in `validate_package`
- `scripts/research/test_f017_lifecycle_causal_design_v8.py` — mutation and attack lists, census assertions
- `scripts/research/qualify_f017_lifecycle_v8_design.py` — mutation counts (last, once the suite is final)

The generator and the validator must be edited **in lockstep**: `validate_documents` re-derives every rule and
rejects any mismatch via `PAYLOAD_RULE_EXACT_SEMANTICS`, and `SCHEMA_EXACT_BINDING` requires
`schemas.artifacts[id]` to equal the DAG node field-for-field.

### Ordered steps

1. **N1 — descriptor identity values.** Extend the `DESCRIPTOR_IDENTITY_ARRAY` branch in
   `validate_package` (`check_…:78-81`) with per-field type checks, pairwise `(device, inode)` distinctness, and
   a `sizes` list in the rule bound to the six pinned `checkpoint_shard_receipt_*.expected_size` constants
   (already derived from `glm52-checkpoint.json` at `validate_…:355-365`). Mirror the rule literal in the
   generator (`generate_…:225-227`) and in the validator `override` ladder (`validate_…:317`).
2. **N2 — comparison enum partition.** Read the admissible set from the `numerical_contract` root authority via
   the existing `resolve_pointer`, filtering `future_p1_consequence != "ATTEMPT_2_BLOCKED"`. This also closes
   half of DEFENSE_IN_DEPTH 5.
3. **N3 — derive `live_leases_after_release`.** In the capsule branch of `validate_package`
   (`check_…:106-118`), replace the pinned check with
   `live_leases_after_release == expected_leases - successful_closures - duplicate_closures`.
   Keep `test_cleanup_anomaly_is_recordable_in_atomic_terminal_capsule` green.
4. **N4 — identifier bindings.** Add `EQUAL_ENVELOPE_FIELD` for `payload.authorization_id` /
   `payload.package_attempt_id`; `EQUAL_ARTIFACT_PAYLOAD_FIELD` for both consumer `event_id` chains and for
   `package_ledger_entry.prior_entry_id`; a `NONEMPTY_STRING` kind for `operator_approval_id` and `owner_nonce`.
   Register every new kind in the `PAYLOAD_RULE_KIND` allowlist (`validate_…:303`).
5. **DiD 1 — total `critical_constants`.** Assert `node_map[aid]["payload_constants"] == expected[aid]` for all
   95 artifacts, `{}` where no constant is intended.
6. **DiD 2 / 3 / 7 / 8 / 9 / 10 — evidence hygiene.** Derive `cycles` / `artifact_cycles` or delete the claims
   and the banked `causal_artifact_dag: "ACYCLIC"`; rename the splice test; generalise the byte-identity test to
   all 47 outcomes; replace test 5's rank tuple with the `node_map` derivation; make the qualifier read the
   mutation counts from the suite instead of restating them.
7. **DiD 6 — add a `DESCRIPTOR_RELEASE_FAILURE` class** for ranks 43–45 in `failure_class_for_rank`, or record
   in the design why release failures are deliberately folded into evidence-banking failures.

Steps 1–4 are independent and can be done in any order; step 5 will start failing as soon as steps 1–4 add
constants, so do it after them. Step 7 renames three of the 47 outcomes, so it changes every capsule
`artifact_id` and the outcome census — do it last or defer it to V9.

---

## Verification

From a clean detached worktree (never in the review worktree; use a `git archive` extraction so no
`__pycache__` lands on tracked paths):

```
python3 scripts/research/generate_f017_lifecycle_v8_design.py      # then diff contracts: must be deterministic
python3 scripts/research/validate_f017_lifecycle_causal_design_v8.py   # expect PASS, 95/94/48/25
python3 scripts/research/construct_f017_lifecycle_v8_symbolically.py   # expect 48/48, 1223 artifacts, depth 48
python3 scripts/research/test_f017_lifecycle_causal_design_v8.py       # expect OK with the enlarged suite
```

Then confirm each repair with a negative probe that must fail closed, and one positive probe that must stay
open. Each probe builds a package with `construct_outcome`, mutates one field, repairs dependency SHAs **and**
every `ARTIFACT_SHA256`/`ARTIFACT_SHA256_SEQUENCE` restatement except the field under test, and calls
`validate_package`:

- five `descriptor_identities` sharing one `(device, inode)`; identity `size` contradicting
  `checkpoint_shard_receipt_k.expected_size`; identity integer fields as strings; empty `lease_id` — **reject**;
- `COMPLETE_SUCCESS` with `classification: "ORACLE_DISAGREEMENT"` and with `"ORACLE_EXECUTION_FAILURE"` —
  **reject**; with `"TOP1_UNSTABLE_WITHIN_FROZEN_UNCERTAINTY"` — **accept**;
- a 5-lease capsule with `unknown_leases: 5, successful_closures: 0` — **reject**; with
  `duplicate_closures: 1, successful_closures: 4` — **accept**;
- `candidate_authorization.payload.package_attempt_id` diverging from the envelope; `primary_terminal.event_id`
  diverging from `primary_durable_start.event_id`; `owner_nonce: ""` — **reject**;
- coordinated design drift pinning `package_claim.owner_nonce` to a literal — **reject by the validator**;
- byte-identity of the durable prefix for **all 47** failure outcomes against `COMPLETE_SUCCESS`, asserted in
  the suite rather than for one pair.

Re-bank the mechanical qualification (`qualify_f017_lifecycle_v8_design.py`, which rewrites banked evidence and
must not be run during review) only after every probe behaves as specified and the generator is still
byte-deterministic.
