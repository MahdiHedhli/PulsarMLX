Write is disabled this session, so the arbitration report is delivered here.

# F017 Event 06 Sequence 5 — Opus Design Arbitration, Cycle 2

## Reviewed commit

`6040e02049f2ece4d3caafe9bbee93cce666fdb2` — "spec: repair Event 06 readiness installation design". 22 files, 448 insertions, zero deletions (append-only): 6 contracts, 15 evidence artifacts, 1 generator. Read-only review; no edits, no checkpoint/alias access, no numerical execution, no authority installation, no package start.

All 17 JSON artifacts in the commit are byte-identical to the `canonical_bytes` form of `f017_canonical_serialization_v10.py:11`. Zero canonical drift.

## Independently verified repairs

| Cycle-1 finding | Status | Mechanical evidence |
|---|---|---|
| B1 sentinels unpinned | RESOLVED | `exact_predicates` 27→33, now pins `declaration`, `gemini_verdict`, `opus_verdict`; `exact_predicates_exhaustive_for_acceptance: true` |
| B2 three posture vocabularies | RESOLVED | `posture_mapping` maps all 4 names onto (`authority_posture`, `authority_scope`, `live_authority`) — the real triple at `f017_checkpoint_identity_authority_v12.py:120,159`; replicated in matrix v2 |
| B3 matrix omissions / producer | RESOLVED | 14 rows; `synthetic_installed_validator` → SYNTHETIC_INSTALLED; `identity_runtime_producer` → PRODUCTION_INSTALLED + `requires_package_durable_start: true`, exactly `f017_checkpoint_identity_producer_v12.py:205-207` |
| B4 GO gate was a phrase | RESOLVED | new capability contract: 14 fields, sealing authority, expiry at prepare **and** commit, sameness = object identity + canonical digest equality, freshness/pairwise binding, scope 1 install, attempts 1 / retries 0 / resume false, no public constructor / copy / pickle, `sequence_5_factory_available: false` |
| B5 manifest shape | **PARTIAL** | schema, 7 required keys, `binding_count_equals_bindings_length`, 19 roles verified set-equal to the declaration's path roles minus `supersedes` — but see B1 below |
| B6 dry terminal unreachable | RESOLVED | `installation_preparer` (CANDIDATE→PREPARED_VALIDATION_ONLY) → `dry_package_gate` (`side_effects: 0`) → `PACKAGE_START_ELIGIBLE_DRY_STOP`, `production_commit_success_calls: 0` |
| R1 interposition re-label | RESOLVED | real primitives (`os.open`, `os.pread`, `mmap.mmap`, `Path.resolve/stat`) + real `validate_candidate_triple`, `build_identity_candidate_from_readiness` |
| R2 fail-closed unstated | RESOLVED | `spy_policy` carries all five fields incl. `fails_if_prohibited_capability_reached: true` |
| R3 failure matrix not total | **PARTIAL** | 16-entry `category_outcomes` + 6-entry `readiness_outcomes`, both total; derivation arithmetic wrong (R1 below) |
| R4 vacuous S4 discharge | RESOLVED | disposition contract lists the exact 8 IDs, verified identical to those in `…sequence04-opus-arbiter-cycle-02-response.md`; `unresolved_findings` added and pinned 0 |
| R5 supersedes vs layer 2 | RESOLVED | `historical_source_binding_policy` exempts `supersedes_*` |
| A1 P1 invariant | RESOLVED | `p1_attempt_2_authority_or_execution` pinned `"NONE"` |
| A2 ledger pre-states D3 | RESOLVED | ledger v2 supported 0 / challenged 3; graph v2 D1–D3 `REPAIR_REQUIRED` |
| A3, A4, U1, U2 | RESOLVED | posture outcome present; census carries predicates; exhaustiveness and posture map stated |
| U3 role content | **PARTIAL** | see R6 / U1 |

78-field partition verified: `field_count` 78 = `len(required_fields)` 78 = 78 unique typed names across 6 disjoint classes, set-equal to `required_fields`; all 33 predicate keys are required fields.

## Claim verdicts

| Claim | Verdict | Findings |
|---|---|---|
| CANONICAL_READINESS_DESIGN | REJECT | B1, R6, A1, U1 |
| MANIFEST_ACYCLICITY | REJECT | B1, A2 |
| PRODUCTION_INSTALLATION_DESIGN | REJECT | R4 |
| POSTURE_SEPARATION | REJECT | R4, A3 |
| FUTURE_GO_CAPABILITY_GATE | ACCEPT | — |
| DRY_INSTANTIABILITY_DESIGN | ACCEPT | — |
| NO_ACCESS_DESIGN | ACCEPT | A4 |
| IMPLEMENTATION_QUALIFICATION_PLAN | REJECT | R1, R2, R3, R5, U1, U2 |

## Findings

### BLOCKING

**B1 — The repair deleted the declaration→manifest binding; the manifest layer is unreachable and the acyclicity claim's layer-3→layer-2 edge cannot exist.** `readiness-consumer-interface-v2.json` required `authority_manifest_path` and `authority_manifest_sha256`. v3 removes both (v2→v3 adds 5 fields, removes exactly those 2; `[f for f in v3.required_fields if "manifest" in f] == []`), while `unknown_keys_permitted: false` closes the 78-field set. In the same commit `readiness-authority-manifest-v1.json` asserts `final_declaration_binds_manifest: true`, and `authority-provenance-map-v2.json` asserts `layer_order: [dependencies, manifest, final declaration, terminal index]`, `self_references: 0`, `future_references: 0`, `REPAIRED_ACYCLIC_BY_CONSTRUCTION`. A closed schema with no manifest field cannot bind the manifest, so that edge is unsatisfiable and all 19 manifest roles become uncheckable for membership — `historical_source_binding_policy` waives membership only for `supersedes_*`, implying it is required for the other 19, with no field through which the manifest can be located. It also drops the `implementation_head`/`implementation_tree` cross-check the predecessor performs against the manifest (`f017_event06_readiness_authority_v1.py:110-118`) and the `binding_count == len(bindings)` invariant at `:119-121`, which the new manifest contract re-asserts but the declaration can no longer reach.

This is a regression, not an exemption: the generator's `manifest()` still filters `{role: 1 for role in ROLE_NAMES if role != "authority_manifest"}` (`generate_f017_event06_sequence05_design_v2.py:409`) although `ROLE_NAMES` no longer contains `authority_manifest`, and `PATH_FIELDS` derives from `ROLE_NAMES`, so both fields vanished silently. Across the whole commit `authority_manifest` appears only in that dead filter and in the quoted cycle-1 text.

### REQUIRED

**R1 — `minimum_mutations` is not derived by its own derivation.** `failure-matrix-v2.json`: `minimum_mutations: 320`, `derivation: {readiness_deletions: 78, readiness_types: 78, acceptance_predicates: 33, installation_and_race_floor: 100}`. 78+78+33+100 = **289**. The no-access plan repeats 320 and adds `readiness_reconstructions: 20` + `installation_reconstructions: 20` (329). No artifact reconciles 289, 320 or 329. Cycle-1 R3 asked for exactly this derivation.

**R2 — The transport provenance contract is unbindable, and both provenance instances violate it.** `f017-independent-review-transport-provenance-v1.json` declares only its own `schema` (`…-contract/1.0.0`) and no instance schema — unlike the manifest contract, which declares both `schema` and `manifest_schema`. Nothing binds `challenge_provenance_path` (a required declaration field and manifest role) to this contract, contrasting with `manifest_contract` and `future_go_capability_contract`, which are referenced. Both committed instances fail it anyway: the agy and opus cycle-01 provenance files each omit 4 of the 20 required fields — `started_at_utc`, `normalized_result_path`, `normalized_result_sha256`, `result`. Their `request_sha256`/`response_sha256` do verify.

**R3 — `independent_challenge_provenance: "PASS"` is unreachable under the commit's own policy.** The contract sets `provider_metadata_unavailable_policy: "UNRESOLVED"` and `self_report_alone_sufficient: false`. Both demonstrated transports self-report the metadata as absent: agy `"UNAVAILABLE_FROM_PRINT_TRANSPORT"` (`ANTIGRAVITY_CLI_PRINT`), opus `"NO_SESSION_PERSISTENCE"` (`CLAUDE_CODE_PRINT`). Both are therefore UNRESOLVED, yet `exact_predicates` pins `"PASS"` as an acceptance sentinel, and no conforming transport or non-self-report attestation source is specified anywhere. The cycle-1 agy response asserts "Unresolved provenance limitations: None" while its own provenance record states the metadata is unavailable — precisely the U-CHALLENGE-TRANSPORT-PROVENANCE failure mode.

**R4 — `installation-state-machine-v1.json` was not superseded and now contradicts the repaired model.** Every other v1 evidence artifact received a v2 with an explicit `supersedes`; the state machine did not. It remains the only committed artifact stating transitions and their write/no-write property, and its `states` are `{UNVALIDATED, PREPARED_VALIDATION_ONLY, SYNTHETIC_INSTALLED, PRODUCTION_INSTALLED, TERMINAL_FAILURE}` — no `CANDIDATE`, with a direct `UNVALIDATED → PREPARED_VALIDATION_ONLY` transition. The repaired `posture_mapping` and matrix v2 make `CANDIDATE` a first-class posture and the required input of `installation_preparer`; `phase_order` is a 4-phase list carrying no write semantics. Under `cross_posture_substitution: REJECT`, two live disagreeing enumerations of the state space is both a transition-semantics gap and a posture-separation defect.

**R5 — `unresolved_claims` carries two values in one commit and is a pinned acceptance sentinel.** `design-graph-state-v2.json`: `unresolved_claims: 3` (with `blocking_findings: 6`, `required_findings: 5` — the cycle-1 arbitration counters). `design-claim-ledger-v2.json`: `claim_count: 3`, `challenged: 3`, `unresolved: 0`. The declaration pins `unresolved_claims: 0`. No artifact defines the counter's scope, so the pin is satisfiable under the ledger reading while cycle-1 U1–U3 remain open — the vacuous-discharge class the disposition contract fixed only for Sequence 4. Its `row_counter_scope: "successor rows only"` and `cumulative_counters_separate: true` are Sequence-4-scoped; there is no equivalent for the Sequence-5 cycle-1 findings.

**R6 — Roles still lack content requirements.** Beyond the unbound contracts in R2, `canonical_readiness_qualification`, `installation_preparation_qualification`, `failure_qualification`, `no_access_rehearsal` and `full_corpus_validation` carry no required content anywhere, although the predecessor consumer enforced `result == "PASS"` and `event_06_executed is False` for three such roles (`f017_event06_readiness_authority_v1.py:133-137`) and v3 states no successor rule.

### ADVISORY

- **A1** — `exact_predicates_exhaustive_for_acceptance: true` omits `schema`, whose pin lives in the separate key `declaration_schema` (`…final-declaration/12.2.0`). Read literally, the exhaustiveness flag leaves `schema` constrained only to a non-empty string — the version drift that was root cause #2 of the Sequence-4 failure. Pin `schema` inside `exact_predicates`.
- **A2** — The same `{role: 1}` map serves as the manifest contract's `roles` (per-role count) and the provenance map's `role_layers` (layer index against a 4-element `layer_order`). A manifest *instance*'s `roles` value domain is never specified, and no rule states `binding_count == 19` or `bindings ⊇ role paths`.
- **A3** — No matrix row `produces` SYNTHETIC_INSTALLED although `install_noncanonical_candidate` is retained as `synthetic_entrypoint`; only `installation_preparer` carries a `produces` key.
- **A4** — `real_consumer_functions` includes three prose placeholders ("primary/secondary/result consumer signature") rather than function names, and omits the retained synthetic-path boundaries `install_noncanonical_candidate`, `validate_installed_triple`, `bank_candidate`, `_validate_producer` (`validate_f017_corrected_oracle_access_v12.py:19,36,56,76`). Primitive-level interposition is fail-closed regardless, so this is precision, not a hole.

## Unresolved claims

- **U1** — Whether the five qualification roles discharge anything is undecidable: no successor consumer module and no per-role content requirement exist in the commit (see R6).
- **U2** — Whether an independently attested challenge of *this* commit exists or could conform is undeterminable. The commit contains only cycle-1 agy/opus artifacts, both scoped `reviewed_commit: df4b7d28…`; no cycle-2 artifact is present, and R3 shows no specified transport can satisfy the design's own provenance policy.

## Global verdict

**REJECT** — 1 blocking, 6 required, 4 advisory, 2 unresolved. Acceptance requires zero blocking, required and unresolved findings; no conditional acceptance is offered.

The repair is substantial and most of cycle 1 genuinely discharges — posture mapping, producer gating, the GO capability contract, dry-path reachability, the fail-closed spy policy and the exact eight Sequence-4 finding IDs all verify mechanically. The blocking defect was introduced by the repair itself: fixing the `supersedes` membership finding removed the manifest binding from the declaration entirely, leaving CANONICAL_READINESS_DESIGN and MANIFEST_ACYCLICITY weaker than in `df4b7d28`.

The cycle-2 agy ACCEPT with zero findings is not reproducible against this commit: B1 is decidable by comparing `readiness-consumer-interface-v3.json` against `readiness-authority-manifest-v1.json` in the same commit, and R1 is decidable by adding four integers in `failure-matrix-v2.json`.
