Write is disabled this session, so the arbitration report is delivered here.

# F017 Event 06 Sequence 5 — Opus Design Arbitration, Cycle 3

## Reviewed commit

`11634077a9ce20e1f2e2600d034764a43da6fac3` — "spec: close Event 06 readiness design findings". 22 files, 345 insertions, **zero deletions** (append-only confirmed): 5 contracts, 16 evidence artifacts, 1 generator. Read-only; no edits, no checkpoint/alias access, no numerical execution, no authority installation, no package start. The cycle-3 agy result (`7c22f861…`, Gemini 3.1 Pro (High), ACCEPT, zero findings) is not banked in this commit and was not deferred to.

**Canonical baseline.** Applying `canonical_bytes` (`f017_canonical_serialization_v10.py:11`) to all 17 JSON artifacts: **16 canonical, 1 drift** (R1).

**84-field partition verified.** `field_count` 84 = `len(required_fields)` 84 = 84 unique names across 6 disjoint type classes, set-equal to `required_fields`; all 34 predicate keys are required fields; census v3's `required_fields`/`exact_predicates`/`exact_types` are byte-identical to consumer v4's.

## Cycle-2 finding closure

| Cycle-2 | Status | Mechanical evidence |
|---|---|---|
| B1 manifest binding deleted | **CLOSED** | v4 restores `authority_manifest_path`/`_sha256`; `schema` and `declaration_schema` both pinned to `…final-declaration/12.2.0`; census `authority_manifest_binding_present: true` |
| R1 derivation ≠ floor | **CLOSED** | 84+84+34+18+100 = 320 = `total` = `minimum_mutations`, exact |
| R2 provenance unbindable / instances violate | **PARTIAL** | contract v2 declares `instance_schema` and is bound via `qualification-role-requirements-v1.roles.challenge_provenance.contract`; instances still non-conforming |
| R3 `PASS` unreachable | **PARTIAL** | `independent_attestation_source_required: true` added; term undefined, no conforming instance |
| R4 state machine not superseded | **CLOSED** | v2 supersedes v1, adds `CANDIDATE`, `UNVALIDATED→CANDIDATE→PREPARED_VALIDATION_ONLY`, commit edge requires "same unexpired sealed future-GO capability" |
| R5 `unresolved_claims` two values | **CLOSED** | v4 `unresolved_claims_scope`/`unresolved_findings_scope`; ledger v3 `counter_scope`; graph v3 `current_cycle_*` + `historical_rejected_cycles: 2` |
| R6 roles lack content requirements | **PARTIAL** | 10 constrained, 11 unconstrained; two predecessor cross-bindings dropped |
| A1 `schema` outside predicates | **CLOSED** | `schema` now in `exact_predicates`; 33→34 |
| A2 manifest role/binding domain | **CLOSED** | `roles_type`, `bindings_type`, `role_count: 21`, `role_count_equals_roles_length`, `binding_count_equals_role_count`, `each_role_path_sha_must_equal_binding_entry` |
| A3 no row produces SYNTHETIC_INSTALLED | **CLOSED** | matrix v3 row 15 `install_noncanonical_candidate → SYNTHETIC_INSTALLED` |
| A4 prose consumer placeholders | **CLOSED** (residue in A4 below) | 14 named functions replace 3 prose strings |

## Claim verdicts

| Claim | Verdict | Findings |
|---|---|---|
| CANONICAL_READINESS_DESIGN | REJECT | R3, R4 |
| MANIFEST_ACYCLICITY | ACCEPT | — |
| PRODUCTION_INSTALLATION_DESIGN | ACCEPT | — |
| POSTURE_SEPARATION | ACCEPT | — |
| FUTURE_GO_CAPABILITY_GATE | ACCEPT | — |
| DRY_INSTANTIABILITY_DESIGN | ACCEPT | — |
| NO_ACCESS_DESIGN | ACCEPT | — |
| IMPLEMENTATION_QUALIFICATION_PLAN | REJECT | R1, R2, R3, R4, R5 |

## Findings

### BLOCKING — none

### REQUIRED

**R1 — Non-canonical banked artifact.** `f017-event06-v12-sequence05-agy-design-cycle-02-provenance-v1.json` diverges from canonical bytes at offset 258: `provenance_result` is appended after `verdict` instead of sorted between `exit_status` and `provider_reported_model`. The other 16 JSON files are byte-exact. `bank_exclusive` writes `canonical_bytes(value)`, so this file cannot have been produced by the sanctioned banking primitive, and consumer v4 sets `canonical_bytes_required: true`.

**R2 — No provenance instance conforms to transport contract v2, and `independent_attestation_source` is undefined.** Both cycle-02 instances omit 5 of the 21 required fields — `independent_attestation_source`, `started_at_utc`, `normalized_result_path`, `normalized_result_sha256`, `result` — and declare `…agy-design-provenance/1.1.0` / `…opus-design-provenance/1.1.0` rather than the contract's `instance_schema` `pulsarmlx.f017.independent-review-transport-provenance/1.0.0`, which nothing in the repository uses. The contract requires an `independent_attestation_source` but never enumerates acceptable sources or states how one is distinguished from self-report, while `self_report_alone_sufficient: false` and `provider_metadata_unavailable_policy: "UNRESOLVED"` hold. Both demonstrated transports self-report the metadata absent (`UNAVAILABLE_FROM_TEXT_PRINT_TRANSPORT`, `NO_SESSION_PERSISTENCE`), and the agy instance records `provenance_result: "UNRESOLVED"`. `independent_challenge_provenance: "PASS"` is pinned as an exhaustive acceptance sentinel with no demonstrated or specified satisfying instance. Request/response SHA-256 do verify on both instances.

**R3 — Qualification-role requirements constrain 10 of the manifest's 21 roles, with undefined closure scope.** Constrained: `canonical_readiness_qualification`, `installation_preparation_qualification`, `failure_qualification`, `no_access_rehearsal`, `full_corpus_validation`, `full_native_evidence`, `challenge_result`, `challenge_provenance`, `opus_result`, `sequence4_finding_disposition`. Unconstrained: `bridge_declaration`, `checkpoint_identity_authority`, `future_go_capability`, `implementation_measurement`, `live_installation_interface`, `numerical_contract`, `qualification_role_requirements`, `readiness_interface`, `result_authority`, `review_transport_provenance_contract`, `scientific_access_contract`. The contract asserts `unknown_roles_permitted: false` with no scope string, so it is undecidable whether an unlisted manifest role has no requirements or is prohibited — the manifest contract uses the identically-named key to close its role set at 21. Consumer v4 added `unresolved_claims_scope` and `unresolved_findings_scope` for exactly this ambiguity class; no equivalent was added here.

**R4 — Predecessor cross-bindings dropped with no successor rule, while completeness is asserted.** `f017_event06_readiness_authority_v1.py:128-129` binds `full_native_run` to the evidence's `run_id`; `:135-137` binds `gemini.verdict`/`opus.global_verdict` to the declaration's `gemini_verdict`/`opus_verdict`. Neither survives: `full_native_evidence` requires only `result: "PASS"` and `required_native_skips: 0`; `challenge_result` and `opus_result` require only three zeroed counters. `full_native_run` is a required `nonnegative_integer` carrying no predicate under `exact_predicates_exhaustive_for_acceptance: true`. A declaration may therefore pin `opus_verdict: "ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_06_EXECUTION_AUTHORIZATION_PREPARATION"` and `full_native_run: 0` against bound evidence that says otherwise, while `all_requirements_mechanically_validated: true` asserts the opposite.

**R5 — The challenge role has no correctness or reproducibility requirement, and the commit banks a second demonstrably false zero-finding ACCEPT.** `f017-event06-v12-sequence05-agy-design-cycle-02-exact-response.md` reports zero blocking, required and advisory findings and "Unresolved provenance limitations: None" for `6040e020` — a commit where cycle-2 B1 is decidable by set-difference over `required_fields` and R1 by summing four integers, and whose own provenance file records `provenance_result: "UNRESOLVED"`. It also credits contract v1 with mandating external attestation, which only v2 does. `challenge_result` requires only `{blocking_findings: 0, required_findings: 0, unresolved_claims: 0}`, which this response satisfies numerically. `f017-event06-sequence4-finding-disposition-v1.json` lists `B-CYCLE02-CHALLENGE-FALSE-VERIFICATION` among the eight findings that must be `RESOLVED` under `resolved_requires_exact_support: true`; no artifact supplies an adjudication or reproducibility mechanism.

### ADVISORY

- **A1** — `alternate_encoding_alias_binding_floor: 18` is the only new derivation component and is exactly the residual needed to preserve the pre-existing floor (84+84+34+100 = 302; 320−302 = 18). It carries no independent justification, and both `total` and `minimum_mutations` are literals in `generate_f017_event06_sequence05_design_v3.py:190-191`, not computed sums.
- **A2** — State machine v2 lists `TERMINAL_FAILURE` but no transition reaches it; the 16 exact failure outcomes have no edge in the state model. Inherited from v1.
- **A3** — `phase_order` keeps `SEALED_INPUTS` and `CANDIDATE_VALIDATED`, which map to neither a posture nor a state, in the same file as the 4-key `posture_mapping`. Mitigated by `state_machine_contract` naming the authoritative document.
- **A4** — 6 of 14 `real_consumer_functions` do not exist in the tree (`validate_event06_readiness_declaration_v2`, `prepare_production_installation`, `validate_prepared_production_installation`, `validate_prepared_package_start_eligibility`, `derive_bridge_execution_plan`, `validate_result_authority`) — acceptable as Sequence-5 entrypoints, but `validate_primary`/`validate_secondary` exist only as import aliases (`qualify_f017_event05_readiness_interface_v1.py:20-21`) while `aliases_permitted: false`. 5 of 10 `interposed_primitives` remain prose.

## Unresolved claims

- **U1** — No independently attested challenge of `11634077` exists in the commit; both banked cycle-02 artifacts are scoped `reviewed_commit: 6040e02049f2…`. The cycle-3 agy result is not banked and cannot be verified from the commit; under R2 no specified transport can satisfy the design's own provenance policy.
- **U2** — `all_requirements_mechanically_validated: true` has no validator in the commit. The successor consumer `validate_event06_readiness_declaration_v2` does not exist; the generator's `--check` mode verifies artifact byte-drift only. Whether the 10 role requirements are enforceable as written is undetermined.

## Global verdict

**REJECT_F017_EVENT06_SEQUENCE05_DESIGN** — 0 blocking, 5 required, 4 advisory, 2 unresolved. Acceptance requires zero blocking, required and unresolved findings; no conditional acceptance is offered.

The repair is genuine and materially stronger than `6040e020`. Cycle-2's blocking regression is fully closed: the manifest binding is restored, the manifest contract fixes exact instance shape (`role_count: 21`, verified set-equal to the declaration's 23 path roles minus `authority_manifest` and `supersedes`), the mutation derivation sums exactly, the state machine supersedes v1 with `CANDIDATE` first-class, counter scopes are stated, matrix v3 produces SYNTHETIC_INSTALLED, and the authority graph is acyclic by construction — `layer_order` of 4, `self_references: 0`, `future_references: 0`, `manifest_may_bind_itself: false`, `manifest_may_bind_final_declaration: false`, `terminal_index_is_readiness_input: false`. MANIFEST_ACYCLICITY, PRODUCTION_INSTALLATION_DESIGN and POSTURE_SEPARATION move from REJECT to ACCEPT.

What remains is the provenance and qualification axis. The cycle-3 agy ACCEPT with zero findings is not reproducible against this commit: R1 is decidable by re-serializing one JSON file, R2 by set-differencing 21 contract field names against 16 instance keys, and R3 by set-differencing 21 manifest roles against 10 requirement keys.
