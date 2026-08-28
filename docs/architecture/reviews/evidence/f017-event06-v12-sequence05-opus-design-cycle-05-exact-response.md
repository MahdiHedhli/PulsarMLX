Write is disabled in this session, so the arbitration report is delivered here rather than to a plan file. No repository state was modified; verification was read-only (byte reads, SHA-256 recomputation, census arithmetic). Neither script was executed.

# F017 Event 06 Sequence 5 — Opus Design Arbiter, Cycle 5
**Reviewed commit:** `e92c8162302edb609c8bef69921ab71887cca525` (30 files, 460 insertions, 0 deletions)

## Global verdict

**REJECT_F017_EVENT06_SEQUENCE05_DESIGN**

4 blocking, 7 required, 2 unresolved. Acceptance requires zero of each. No conditional acceptance offered.

## Claim verdicts

| Claim | Verdict | Grounds |
|---|---|---|
| CANONICAL_READINESS_DESIGN | **REJECT** | B1, R2 |
| MANIFEST_ACYCLICITY | **REJECT** | R2, A3 |
| PRODUCTION_INSTALLATION_DESIGN | **REJECT** | R3, R4 |
| POSTURE_SEPARATION | **REJECT** | B4, R1, R6 |
| FUTURE_GO_CAPABILITY_GATE | **ACCEPT** | — |
| DRY_INSTANTIABILITY_DESIGN | **REJECT** | B3, R2 |
| NO_ACCESS_DESIGN | **ACCEPT** | A1 advisory only |
| IMPLEMENTATION_QUALIFICATION_PLAN | **REJECT** | B1, B2, R5, R7 |

## Blocking findings

**B1 — Qualification v3 cross-bindings name keys that cannot exist in the closed readiness census.**
`qualification-role-requirements-v3.json` declares 8 cross-binding targets; 5 are absent from `readiness-consumer-interface-v6.json`, whose census is closed (`field_count: 84`, `required_fields` length 84, `unknown_keys_permitted: false`):

| Target | Declared by | Present in 84-field census |
|---|---|---|
| `review_head` | `challenge_result.reviewed_commit`, `opus_result.reviewed_commit` | **NO** |
| `challenge_reproduction_sha256` | `challenge_result.reproduction_report_sha256`, `opus_result.reproduction_report_sha256` | **NO** |
| `measured_implementation_head` | `full_native_evidence.implementation_head` | **NO** |
| `measured_implementation_tree` | `full_native_evidence.implementation_tree` | **NO** |
| `bridge_digest`, `implementation_head`, `implementation_tree`, `full_native_run` | 3 roles | yes |

Readiness carries `implementation_head`/`implementation_tree`, not the `measured_` names. This is cycle-4's R1 unchanged. `challenge-reproducibility-cycle04-v1.json` asserts R1 `observed: true` ("all qualification requirements name real present keys or explicit future schemas") — that assertion is false. Aggravating: `validate_..._v2.py:79-80` asserts `cross_bindings["reviewed_commit"] == "review_head"`, pinning the unsatisfiable name without ever resolving it.

**B2 — The challenge reproducibility report is a hardcoded constant, not a derivation.**
`generate_..._v5.py:211-217` emits all four `finding_checks` with literal `"observed": True, "expected": True, "result": "PASS"`. Nothing computes `observed`. `validate_..._v2.py:82-87` reads those literals back, requires `PASS`, and hardcodes the census `{"R1","R2","R3","U1"}`. Readiness v6's `challenge_reproducibility_policy` claims a bound report "mechanically covers every prior material arbiter finding"; the mechanism does not exist. R2 is not closed — the contract and report exist, the *validator* is circular.

**B3 — `prepared_manifest_bindings_validated: 21` overstates what is checked.**
`validate_..._v2.py:59-65` validates bindings for the 12 `current` roles only (path, SHA, predicates). Lines 66-74 iterate `future` roles but inspect the **rule text** (availability stage, field-list hygiene, schema prefix) — they never open, hash, or predicate-check the 9 future bindings. `design-mechanical-validation-v2.json` reports 21 validated; 12 were.

**B4 — Cross-posture substitution in the prepared manifest.**
8 of 9 `PROVISIONAL_NOT_FINAL` bindings carry a `schema` contradicting their role's own `required_schema`:

| Role | Bound schema | Required schema |
|---|---|---|
| canonical_readiness_qualification | `…design-mechanical-validation/1.0.0` | `…canonical-readiness-qualification/1.0.0` |
| full_corpus_validation | `…design-mechanical-validation/1.0.0` (same file) | `…full-corpus-validation/1.0.0` |
| installation_preparation_qualification | `…installation-state-machine/1.2.0` | `…installation-preparation-qualification/1.0.0` |
| failure_qualification | `…failure-matrix/1.3.0` | `…failure-qualification/1.0.0` |
| no_access_rehearsal | `…no-access-qualification-plan/1.3.0` | `…no-access-rehearsal/1.0.0` |
| full_native_evidence | `…event06-v12-full-native-ci/5.0.0` | `…sequence05-full-native-ci/1.0.0` |
| challenge_result | `…agy-design-result/1.2.0` | `…challenge-whole-domain-result/1.0.0` |
| opus_result | `…opus-design-result/1.2.0` | `…opus-whole-domain-result/1.0.0` |

Two are worse than a schema mismatch. `challenge_result` binds `agy-design-cycle-04-repair-normalized-result.json` — the artifact this same commit's `review-correction-index-v2.json` classifies `FALSE_ZERO_FINDING_ACCEPT` / `NONAUTHORITATIVE_MISSED_MATERIAL_FINDINGS`. `opus_result` binds a result whose `global_verdict` is `REJECT_F017_EVENT06_SEQUENCE05_DESIGN`, against an acceptance predicate demanding `ACCEPT_FOR_FRESH_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_06_GO`. Both `live-installation-interface-v5.json` and `installation-state-machine-v4.json` declare `cross_posture_substitution: "REJECT"`, which the prepared instance then performs.

## Required findings

**R1 — Prepared manifest binds superseded predecessors of artifacts this commit ships.** `failure_qualification` → `failure-matrix-v4.json` (ships v5, whose `supersedes` names v4); `installation_preparation_qualification` → `installation-state-machine-v3.json` (ships v4); `no_access_rehearsal` → `no-access-qualification-plan-v4.json` (ships v5); `canonical_readiness_qualification` and `full_corpus_validation` → `design-mechanical-validation-v1.json` (ships v2). The comment at `generate_..._v5.py:263` — "The prepared instance binds the just-generated successor bytes" — is false for these roles; `existing_bindings()` lines 160-168 point at predecessors.

**R2 — The prepared instance conforms to no shape contract, and violates the only one defined.** `readiness-authority-manifest-v4.json` defines `required_keys` = [schema, implementation_head, implementation_tree, binding_count, bindings, role_count, roles, result] and `roles_type` = "closed role-to-{path,sha256} mapping". The prepared instance omits `implementation_head`, `implementation_tree`, `result`, and its `roles` is a flat list. The contract constrains the prepared schema only by `prepared_instance_must_be_ineligible: true`. Separately, `instance_validation_algorithm` — including "resolve every path without symlink/traversal and verify SHA" and "reject self/final-declaration/future dependency" — is implemented nowhere, while the instance binds 9 roles whose `availability_stage` is `POST_IMPLEMENTATION_*`, i.e. future dependencies.

**R3 — `failure_outcome_edge_mapping` is a constant function.** All 16 outcomes map to the single value `ANY_NONTERMINAL_TO_TERMINAL_FAILURE` (`generate_..._v5.py:190`, one literal in a comprehension). `capability_expired`, `fsync`, `target`, and `partial` arise at structurally different edges. A constant map carries no information and does not show each outcome reachable from a specific transition; "failure transitions must be justified/mapped" is unmet.

**R4 — Mutation floor justification names a census that does not exist.** `component_justification.installation_and_race_floor` = "10 named transition/race families x 10 repetitions". The state machine has 9 transitions and no "race family" is enumerated anywhere in the repository. "3 independent structural variants" is likewise unnamed. The arithmetic is sound (34+18+100+84+84 = 320, with 34/84/84 matching `exact_predicates`/`required_fields`/`exact_types`), but both factorizations are asserted, not grounded.

**R5 — Cycle-4 advisories A1–A6 have no disposition anywhere.** The cycle-4 result records `finding_ids` = [R1,R2,R3,A1…A6], `advisory_findings: 6`. The challenge ledger, support ledger, and reproducibility report each cover only {R1,R2,R3,U1}. A1–A6 appear in no ledger, yet the report declares `unexpected_misses: 0` against a `source_arbiter_result_sha256` binding that very result.

**R6 — Bound review results use the counter vocabulary the validator forbids for their roles.** `validate_..._v2.py:77` rejects any `challenge_result`/`opus_result` rule containing `required_findings`. Both bound instances carry `required_findings` and lack `non_blocking_required_findings` (agy repair: `required_findings: 0`; opus cycle-04: `required_findings: 3`). Unchecked, per B3.

**R7 — Chain of custody for the reproduced findings is self-declared nonauthoritative.** The reproducibility report roots in `opus-design-cycle-04-normalized-result.json`, which has no `exact_response_sha256` (cycles 01–03 all do), has no exact-response file, and whose provenance records `result: "HISTORICAL_REJECT_RESPONSE_BYTES_NOT_RETAINED_BY_NO_SESSION_PERSISTENCE_TRANSPORT"`, dispositioned `PRESERVED_NONAUTHORITATIVE_TRANSPORT_FAILURE`. The R1/R2/R3/U1 predicate wording is an unverifiable paraphrase. The artifact bound to `challenge_provenance` is also missing 4 of the 21 fields its role requires (`tool_version`, `requested_model`, `started_at_utc`, `completed_at_utc`); the opus cycle-04 provenance is missing 8.

## Advisory findings

**A1** — No-access primitive kinds are derived by substring heuristic (`generate_..._v5.py:192`: `CALLABLE` iff the name contains `(` or `.`). The resulting 5/5 split is defensible on inspection, but the 5 `NAMED_INSTRUMENTATION_BOUNDARY` entries name no enforceable symbol, so `required_counter: "ZERO"` has no stated mechanism.
**A2** — `design-graph-state-v5.json` reports `current_cycle_unresolved_claims: 1`; `design-claim-ledger-v5.json` reports `unresolved: 0`.
**A3** — `qualification_role_requirements` is a manifest dependency role bound to the contract defining that role, and the validator checks the file's `schema`/`role_scope` against the requirement the same file states — a self-edge neither excluded by `manifest_may_bind_itself: false` nor shown benign.

## Unresolved claims

- **U1 (carried forward)** — prepared 21-role manifest instantiability. Path/SHA resolution is genuinely achieved; closure is nonetheless asserted by a hardcoded report (B2) over bindings never validated (B3) and wrong-posture (B4).
- **U2 (new)** — disposition of A1–A6 is unknown; no artifact states resolved, conceded, or deferred.

## What this cycle did close

Stated for the record; none of it offsets the above.

- **R3 is genuinely closed.** Exactly 3 `FALSE_ZERO_FINDING_ACCEPT` rows (agy cycles 02, 03, 04-repair), all `NONAUTHORITATIVE_MISSED_MATERIAL_FINDINGS`, plus 3 preserved transport/receipt failures.
- **No historical erasure.** 460 insertions, 0 deletions; agy and opus cycles 01–04 responses, results, provenance, and requests all still present.
- **All 21 bindings resolve.** Every path exists and every `sha256` matches recomputed file bytes. `final_acceptance_eligible: false`, `live_authority: false`, `checkpoint_root_resolved: false`, `event_06_executed: false` — the final-ineligibility half of U1 is satisfied.
- **Role partition is exact.** 12 current + 9 future = 21, disjoint, equal to `manifest["required_roles"]` and `prepared["bindings"]`.
- **Raw provider envelope requirement present** and validator-checked (`raw_provider_envelope_required_for_current_acceptance: true`, `self_report_alone_sufficient: false`).
- **No dry-path production write.** Sequence-5 terminal is `PREPARED_VALIDATION_ONLY`; `durable_commit_authorized_in_sequence_5: false` is an exact-byte predicate on a current role; the only `write: true` transitions are the synthetic temporary root and the capability-gated production commit Sequence 5 cannot reach.
- **The Antigravity cycle-04 repair accept was not deferred to.** Its zero-finding accept is contradicted by B1–B4 and is already marked nonauthoritative by this commit.

## Minimum repair set for cycle 6

1. Add `review_head`, `challenge_reproduction_sha256`, `measured_implementation_head`, `measured_implementation_tree` to the readiness census (or retarget the cross-bindings), and assert in the validator that every cross-binding target resolves in `readiness["required_fields"]`.
2. Compute the reproducibility report: derive `finding_checks` from the bound arbiter result's `finding_ids` ∪ `unresolved_claim_ids`, compute each `observed` from repository state, derive the census.
3. Either validate the 9 future bindings or bind them to an explicit `UNBOUND_FUTURE` sentinel; stop counting them in `prepared_manifest_bindings_validated`.
4. Rebind stale roles to this commit's successors; remove design-cycle review results from `challenge_result`/`opus_result`.
5. Define a shape contract for the prepared schema and implement `instance_validation_algorithm`.
6. Map each of the 16 outcomes to a specific named transition; name the 10 transition/race families and 3 alias variants.
7. Add an A1–A6 disposition ledger.
