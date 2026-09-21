# F017 Lifecycle V8 Causal Design — Opus Design Review, Cycle 01

Reviewed exact committed bytes at `dcf032a5fdf1e3da8b0d27fea3118bfab7c83686` (worktree clean, HEAD unmoved, `git status` empty before and after). No original checkpoint shard was opened, hashed, mmapped, or pread; no Event-04 authority minted; no real oracle executed; no P1 attempt 2 executed; no reviewed file modified. `qualify_f017_lifecycle_v8_design.py` was deliberately **not** run because it rewrites the banked qualification evidence.

## Verdict

`REJECT`

## Context

V7 was rejected at cycle 05 (terminal) with 3 `BLOCKING`, 5 `NON_BLOCKING_REQUIRED`, and 8 `DEFENSE_IN_DEPTH` findings. V8 rebuilds the lifecycle as a rank-ordered causal artifact DAG (111 nodes, 110 edges, 15 outcomes) with a generator/validator split, a symbolic constructor, and a recursive terminal-closure checker. Gemini cycle 01 rejected on mutation-census ambiguity; cycle 02 accepted at `9ac0019b`. This review independently reconstructs that work and attacks the frozen design.

## Reconstruction performed (all reproduced)

- **All 16 terminal V7 cycle-05 findings** reproduced from `f017-checkpoint-identity-v7-opus-design-cycle-05-normalized-result.json` and matched 1:1 (no missing, no extra) against `f017-corrected-oracle-v7-cycle05-findings-reproduction-v1.json`; `reviewed_head` agrees (`833d9610`).
- **Both Gemini V8 cycles** reproduced: cycle 01 `REJECT` on `MUTATION_CENSUS_STATIC_RUNTIME_ACCOUNTING_AMBIGUOUS`; cycle 02 `ACCEPT` at `9ac0019b`. The `126_STATIC_PLUS_2_RUNTIME_CLOSURE_ATTACKS` census is now explicit and the static suite asserts exactly 126.
- **Independent topological sort** of all 111 nodes (Kahn, not the committed DFS): single root `operator_approval`, fully sorted, zero self, future, inherited, conditional, or outcome-specific cycles. Per-outcome subgraphs are individually acyclic with no dangling dependency.
- **Symbolic construction of all 15 outcomes**: PASS, 407 real artifacts, maximum closure depth 51, recursive terminal closure PASS, cross-package splice and runtime closure attacks rejected.
- **Mechanical claims re-derived**: 111 artifacts, 110 edges, 15 outcomes, 25 safety invariants, 111/111 path-timing coverage with exact producer-transition agreement, 111 unique transition IDs, derived six-shard census `238,458,632,928` (independently summed; agrees with `docs/validation/glm52-checkpoint.json`), zero self-SHA payload keys, exact five-descriptor primary and secondary reports over ordinals 2–6, continuity reports bound before their durable starts, secondary report after `primary_terminal`, unstarted-consumer durable starts forbidden on every zero-delta outcome, release-before-terminal on success, numerical V3 authority SHA-isolated and unmodified, active live generation `NONE`, original checkpoint access `0`.
- `validate_f017_lifecycle_causal_design_v8.py` → PASS; `test_f017_lifecycle_causal_design_v8.py` → 3/3 OK.

---

## BLOCKING

### B1. `EVIDENCE_BANKING_FAILURE` requires two complete descriptor-release chains over the same five leases

`generate_f017_lifecycle_v8_design.py:163` appends a release chain to any outcome whose cut rank is `>= 26`, without checking whether the durable prefix already contains one. `EVIDENCE_BANKING_FAILURE` has `durable_prefix_rank = 45`, whose prefix already includes success ranks 43/44/45 (`descriptor_release_start` / `_report` / `_terminal`). The obligation set therefore requires **six** release artifacts:

```
descriptor_release_start,  descriptor_release_start__evidence_banking_failure
descriptor_release_report, descriptor_release_report__evidence_banking_failure
descriptor_release_terminal, descriptor_release_terminal__evidence_banking_failure
```

The symbolic constructor emits both, each claiming `attempted_closures = 5`, `successful_closures = 5`, `live_leases_after_release = 0` — ten successful closures of five leases. This contradicts `f017-corrected-oracle-descriptor-continuity-v8.json` (`release.duplicate_closures = 0`, `unknown_leases = 0`) and is unsatisfiable by any conforming implementation: after the rank-45 release, no lease is live, so a second chain reporting five successful closures must record either five duplicates or five unknown leases. Same class as V7 cycle-05 `BLOCKING` #1 (`IDENTITY_RECEIPT_LEASE_MANIFEST_CREATION_ORDER_UNSATISFIABLE`) — an obligation unsatisfiable on every trace. The full 128-mutation suite passes over it.

**Repair:** gate the failure-tail release chain on whether the durable prefix already closed the leases (release required *iff* leases are live at the cut), not on a bare rank threshold.

### B2. Identity failure over shards 2–6 is unrepresentable and terminates with unreleased graph-payload leases

`CHECKPOINT_IDENTITY_FAILURE` is the only identity-failure outcome and its cut is pinned at rank 13 (`checkpoint_shard_receipt_1`, the `IDENTITY_ONLY` shard). Its `forbidden` set contains `checkpoint_access_event_2..6`, `checkpoint_shard_receipt_2..6`, and `descriptor_lease_manifest`, and it carries **zero** release artifacts.

But `f017-corrected-oracle-checkpoint-identity-v8.json` mandates `processing.durable_shard_receipt_before_next = true` and `graph_payload_disposition = "RETAIN_AS_PACKAGE_OWNED_DESCRIPTOR_LEASE"`. A failure while verifying shard *k* (3 ≤ *k* ≤ 6) therefore has a durable prefix containing receipts 2..*k*−1 with up to four live graph-payload leases. That prefix matches no outcome: `CHECKPOINT_IDENTITY_FAILURE` forbids those receipts, and `DESCRIPTOR_LEASE_ACTIVATION_FAILURE` (cut 28) requires all six receipts plus the identity terminal. Even a shard-2 failure is unrepresentable once `checkpoint_access_event_2` is banked.

Consequences: (a) the 15-outcome census claimed complete (`legal_outcome_count: 15`, `all_legal_outcomes_symbolically_constructed: PASS`) does not cover the dominant failure window — roughly 229 GB of the 238 GB is hashed inside it; (b) any such termination violates the design's own `NO_LIVE_LEASES_AT_TERMINAL` invariant and `live_leases_at_terminal: 0`, with no release obligation to satisfy. This is the unrepaired residue of V7 `POST_CLAIM_TERMINAL_RELEASE_SHAPE_BYPASS` and `LEASE_ARTIFACT_FAILURE_PROHIBITIONS_ABSENT`.

**Repair:** parameterise the identity-failure outcome by shard ordinal (or admit a prefix-ranged outcome family), and derive the release obligation from live-lease count at the cut.

---

## NON_BLOCKING_REQUIRED

### N1. `checkpoint_identity.processing` is entirely ungated; two safety invariants resolve only to a mirror of themselves

`generate_f017_lifecycle_v8_design.py:318` builds `safety_projection` as a literal copy of the same `expected_invariants` tuple list that produces the invariant registry. The validator then checks the registry against hardcoded constants *and* the projection against the same constants — two restatements of one literal. No invariant resolves into the surface it purports to constrain.

For 23 invariants the underlying surface happens to be independently pinned elsewhere, but `IDENTITY_HASH_EXACT_BYTES` and `IDENTITY_DESCRIPTOR_STABLE` are not. Reproduced against committed bytes: setting `processing.hash = "PREFIX_ONLY"`, `processing.pre_post_fstat_equal = false`, or replacing the whole `processing` block with `{}` all pass `validate_documents` and all 128 mutations. This is the load-bearing statement that identity hashing covers complete bytes through a NOFOLLOW root-relative descriptor with pre/post `fstat` equality. Direct recurrence of V7 `UNCONDITIONAL_SAFETY_INVARIANTS_UNGATED`, whose repair was recorded as "committed invariant registry with mutation per invariant".

### N2. Shard digests and filenames are unbound to the `checkpoint_metadata` root authority

`docs/validation/glm52-checkpoint.json` is SHA-bound in the manifest but never read by the validator. The six `sha256` values and filenames in the identity contract are checked only for uniqueness and count. Reproduced: forging `shards[2].sha256` to `0`*64 or renaming a shard to `ATTACKER.gguf` passes validation and every mutation. The V7 `BYTE_CENSUS_BARE_VALIDATOR_LITERAL` repair derived the *byte total* from the shard records but left the records themselves unbound — and the total is still additionally pinned by a hardcoded literal, so only size drift is caught.

### N3. The lifecycle semantic model's state machine is ungated and structurally incomplete

`validate_documents` checks only `model.outcomes`, `success_artifact_order`, `numerical_contract`, `safety_projection`, and a `"P1"` substring scan. Reproduced: replacing `transitions` with `[{"id": "RETRY", ...}]`, emptying `states`, or flipping every value in `unconditional_invariants` all pass. Additionally the model registers 62 transitions and 63 states, while the DAG defines 111 producer transitions — **63 producer transition IDs appear in path timing but in no lifecycle transition**, and all 14 failure paths collapse to a single atomic `FAIL_*` edge despite creating 3–6 durably banked artifacts each. `unconditional_invariants` and `safety_projection` are the same 25 facts declared twice with only one gated — the exact shape of V7 `INTERFACE_PATH_REOPEN_DECLARATION_UNGATED`.

### N4. Failure-path release reports cannot record duplicate or unknown closures

`generate_f017_lifecycle_v8_design.py:166` gives `descriptor_release_report__*` the key census `["attempted_closures", "successful_closures", "live_leases_after_release", "lease_ids"]`, dropping `duplicate_closures` and `unknown_leases` that the success-path report carries. With `strict_key_census: true` and `unknown_fields: "REJECT"`, those two fields are unrecordable on all seven lease-bearing failure outcomes — precisely the paths where double-close and unknown-lease errors are most likely. The continuity authority still asserts both are `0`, with nothing able to observe them.

### N5. The committed transitive-closure validator enforces no authority conformance

`check_f017_transitive_artifact_closure_v8.py` is the design's only package-verification component (manifest key `transitive_closure_validator`), yet it never consults the DAG, the schema registry, or the outcome obligations. Reproduced against a constructed `COMPLETE_SUCCESS` package with consistent rehashing of all descendants — the following all pass:

| attack | result |
| --- | --- |
| forge `schema` on `checkpoint_identity_receipt` | UNCAUGHT |
| forge `outcome` on `package_terminal` to `PRE_MINT_FAILURE` | UNCAUGHT |
| add an unknown payload key to `descriptor_release_report` | UNCAUGHT (defeats `strict_key_census`) |
| drop the `numerical_contract` root-authority binding | UNCAUGHT (presence census never checked) |

Cross-package splice, dropped dependency edges, and rank inversion are correctly rejected. The strict key census and root-authority census are enforced only by the *producer* (`construct_outcome`), never by the verifier — the wrong side of the trust boundary for a design whose purpose is detecting forged evidence.

---

## DEFENSE_IN_DEPTH

1. `construct_outcome`'s forbidden-artifact assertion is vacuous: the loop only creates `required` artifacts, so `glob("*.json") & forbidden` can never be non-empty. The banked `unstarted_consumer_artifact_prohibitions: "PASS"` rests on the validator's partition check alone.
2. `accounting.package_start_rank` / `primary_start_rank` / `secondary_start_rank` are ungated restatements — forging them to `1` passes.
3. `outcomes[*].last_completed_artifact_id` and `failed_transition_id` are ungated; nothing binds `failure_evidence.durable_prefix_id` / `last_completed_transition_id` to the cut.
4. `node.actor` is ungated: reassigning `CHECKPOINT_IDENTITY_PRODUCER` artifacts to `PRIMARY_CONSUMER` passes, so producer separation is declared but unenforced.
5. `dag.edge_semantics` is a free string.
6. `continuity.success_reports[*].created_before` / `created_after` duplicate DAG bindings and are ungated (the real constraint is separately gated, so impact is limited to drift).
7. The 14 failure outcomes have no `final_declaration` analogue, so no failure package banks `event_04_executed` / `original_checkpoint_access` / `active_generation`.
8. Release-report `lease_ids` are never cross-checked against `descriptor_lease_manifest`, unlike the continuity reports (`construct_f017_lifecycle_v8_symbolically.py:110`).
9. `validate_package`'s cycle detector is unreachable: strict rank monotonicity on every edge makes a cycle impossible, so the "runtime artifact-cycle attack" counted in the `126 + 2 = 128` census is in fact rejected by the rank check, not the cycle check.
10. `test_120_design_mutations_fail_closed` asserts 126 mutations; the name is stale.
11. General form of B2: each outcome pins exactly one durable-prefix rank, so most intermediate prefixes (e.g. failure between `primary_durable_start` rank 30 and `primary_ledger_entry` rank 31) match no outcome.

---

## Required work before a V9 review cycle

1. Derive the failure-tail release chain from live-lease count at the durable prefix, not a rank threshold; eliminate the `EVIDENCE_BANKING_FAILURE` double release. *(B1)*
2. Cover identity failure across shard ordinals 2–6 with a release obligation derived from retained leases. *(B2)*
3. Resolve each safety invariant's `source_json_pointer` into the authority it constrains, not into a generated mirror; gate `checkpoint_identity.processing`. *(N1)*
4. Derive shard filenames, sizes, and digests from `docs/validation/glm52-checkpoint.json` and add mutation probes per field. *(N2)*
5. Gate `lifecycle_model.states` / `transitions` / `unconditional_invariants` against the DAG; register every producer transition or drop the duplicate declaration. *(N3)*
6. Restore `duplicate_closures` and `unknown_leases` to the failure-path release report census. *(N4)*
7. Make the closure validator check schema IDs, payload key census, declared outcome, DAG ranks/edges, and root-authority presence. *(N5)*
8. Close the eleven defense-in-depth items, at minimum 1, 4, and 9.

## Verification for a V9 design

Re-run, from a clean detached worktree, `python3 scripts/research/validate_f017_lifecycle_causal_design_v8.py` (expect PASS with the new census) and `python3 scripts/research/test_f017_lifecycle_causal_design_v8.py` (expect the enlarged mutation suite green), then confirm each repair with a targeted negative probe: forged shard digest, gutted `processing` block, replaced `transitions`, forged package `schema`/`outcome`/extra payload key, dropped root authority, and a constructed identity failure at shard 4 that must produce a release chain and a matching outcome. Re-bank the mechanical qualification only after all probes fail closed.
