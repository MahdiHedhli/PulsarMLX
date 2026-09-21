The plan file can't be created (Write is disabled this session), so the arbitration report is delivered here.

# F017 Event 06 Sequence 5 — Opus Design Arbitration

## Reviewed commit

`df4b7d28c210a2f09810a468a9bc9757d5b073ea` — "spec: freeze Event 06 readiness installation repair design". 12 files, 304 insertions: 2 contracts, 9 evidence artifacts, 1 generator. Read-only review; no edits, no checkpoint/alias/numerical-core/authority-installation/package-state access.

## Independent reconstruction of the Sequence 4 pre-mint failure

Recomputed from `…evidence/f017-corrected-oracle-event06-execution-readiness-final-declaration-v12-v3.json` against `…contracts/f017-corrected-oracle-event06-readiness-consumer-interface-v1.json`:

| Quantity | Recomputed | S5 artifact | Match |
|---|---|---|---|
| observed bytes | 3124 | 3124 | ✓ |
| canonical bytes | 2923 | 2923 | ✓ |
| canonical | False | False | ✓ |
| sha256 | `98586f23…149d` | ✓ | ✓ |
| artifact schema | `…final-declaration/12.1.0` | 12.1.0 | ✓ |
| consumer schema | 12.0.0 (hardcoded, `f017_event06_readiness_authority_v1.py:80`) | 12.0.0 | ✓ |
| missing required | 25 | 25 | ✓ |
| unexpected | 28 | 28 | ✓ |

Root causes: noncanonical bytes → `ArtifactDecodeError`; declaration/consumer version drift; 25/28 field divergence; and no live production installer — `install_noncanonical_candidate` was the only installer, and `validate_installed_triple` hard-rejects any receipt whose `live_authority` is not `False` (`validate_f017_corrected_oracle_access_v12.py:67`). The artifact's `prompt_expected_unexpected_fields: 30` vs measured 28 with `GIT_DERIVED_28_FIELDS_AUTHORITATIVE` is a correct, evidence-backed correction of the prompt. Credited.

## What passes

75 fields with `exact_types` partitioning the required-field set exactly (75 typed names, disjoint, set-equal); canonical serialization mandated and demonstrated (all 11 artifacts byte-identical to `canonical_bytes(...)` — zero drift); explicit historical supersession via `supersedes_path`/`supersedes_sha256` + `historical_declarations_permitted_as_current: false` + contract-level `declaration_schema`, replacing the predecessor's hardcoded sha frozenset; `install_noncanonical_candidate` retained as synthetic; prepare/validate/commit separated with `durable_commit_authorized_in_sequence_5: false` and `sequence_5_terminal_state: PREPARED_VALIDATION_ONLY` — **this graph cannot reach production install**; all eight attack classes enumerated.

## Claim verdicts

| Claim | Verdict | Findings |
|---|---|---|
| CANONICAL_READINESS_DESIGN | REJECT | B1, R4, R5, A1, A4 |
| MANIFEST_ACYCLICITY | REJECT | B5, R5 |
| PRODUCTION_INSTALLATION_DESIGN | REJECT | B2, B4, B6, R3, A3 |
| POSTURE_SEPARATION | REJECT | B2, B3 |
| FUTURE_GO_CAPABILITY_GATE | REJECT | B4 |
| DRY_INSTANTIABILITY_DESIGN | REJECT | B6, B2 |
| NO_ACCESS_DESIGN | REJECT | R1, R2 |
| IMPLEMENTATION_QUALIFICATION_PLAN | REJECT | R3, R4 |

## Findings

### BLOCKING

**B1 — Readiness acceptance sentinels unpinned.** `exact_predicates` (27 entries) omits `declaration`, `gemini_verdict`, `opus_verdict`; `exact_types` classes all three as `string` (non-empty only). v1 pinned `declaration` in-contract; the predecessor consumer pinned both verdicts in code (`f017_event06_readiness_authority_v1.py:85,87`). No Sequence 5 artifact carries any expected value, and the vocabulary demonstrably drifts (12.1.0 carries `ACCEPT_FOR_OPUS_WHOLE_DOMAIN_ARBITRATION` / `ACCEPT_F017_EVENT06_V12_TO_V11_BRIDGE_AND_READINESS`). A declaration bearing REJECT verdicts satisfies every stated constraint of the frozen successor.

**B2 — Three inconsistent posture vocabularies, none mapped to the implementation.** Install contract: `PREPARED_VALIDATION_ONLY, SYNTHETIC_INSTALLED, PRODUCTION_INSTALLED`. Consumer matrix: `PREPARED_VALIDATION_ONLY, CANDIDATE, PRODUCTION_INSTALLED`. State machine: has `SYNTHETIC_INSTALLED`, no `CANDIDATE`. Implementation: `ValidatedIdentityAuthority.posture ∈ {"CANDIDATE","INSTALLED"}` (`f017_checkpoint_identity_authority_v12.py:159`), with synthetic/production carried by a *different* field `authority_scope ∈ {"SYNTHETIC","PRODUCTION"}` and liveness by `receipt["live_authority"]`. No artifact maps the new names onto that triple, so "distinguishes all postures" and `cross_posture_substitution: REJECT` are unimplementable as specified — today synthetic and production installed authorities share `INSTALLED_SCHEMA` and posture `"INSTALLED"`.

**B3 — Matrix omits SYNTHETIC_INSTALLED and mis-assigns the runtime producer.** No row has posture SYNTHETIC_INSTALLED, yet the synthetic entrypoint is retained and consumed by `validate_installed_triple`/`validate_package_start` (`qualify_f017_checkpoint_identity_authority_v12.py:61,290-298`; `execute_f017_corrected_oracle_event_v12.py:12-14`); the matrix pins `installed_primary`/`installed_secondary`/`package_gate` to PRODUCTION_INSTALLED only, forbidding the retained synthetic path. Separately, `identity_producer` is assigned CANDIDATE only, but the checkpoint-touching producer requires INSTALLED (`f017_checkpoint_identity_producer_v12.py:26` → `F017_V12_IDENTITY_RUNTIME_AUTHORITY_DRIFT`); the boundary performing `open_directory_no_symlinks`, `os.open(dir_fd=…)`, `os.pread` (lines 218, 236, 61) has no row.

**B4 — The production commit gate is a phrase, not a contract.** "commit exclusively only with the same unexpired sealed future-GO capability" (`phases[3]`, state-machine `requires`) is the sole gate on durable commit, yet no artifact defines the capability type, sealing mechanism, minting authority, expiry rule, the meaning of "same", or any binding to a human GO artifact. The 75-field census contains no GO role, despite Sequence 4 failing with `fresh_go_disposition: EXPIRED_BEFORE_APPROVAL` and recording `human_go_sha256`. The inert GO template (`operator_go: null`, `FRESH_HUMAN_GO_REQUIRED`) is unreferenced. `forbidden_capabilities` gives negatives only, with no positive construction rule.

**B5 — Manifest shape unspecified while live manifests disagree.** The design freezes `authority_manifest_path`/`_sha256` and a 4-layer map but specifies no manifest schema. `…bridge-authority-manifest-v4.json` uses key `bindings` with no `binding_count`; `…sequence04-terminal-failure-authority-manifest-v9.json` uses key `artifacts` with neither. The predecessor consumer requires `bindings` and `binding_count == len(bindings)`. With no key name, no count invariant, and no role→layer assignment for the 19 roles, `self_references: 0` / `future_references: 0` / `ACYCLIC_BY_CONSTRUCTION` are assertions, not derivations.

**B6 — The dry terminal is unreachable under the design's own matrix.** `required_terminal: PACKAGE_START_ELIGIBLE_DRY_STOP` with `production_commit_success_calls: 0` and `durable_commit_authorized_in_sequence_5: false`. The only available write transition is UNVALIDATED→SYNTHETIC_INSTALLED, but `package_gate` requires PRODUCTION_INSTALLED — so the rehearsal cannot reach package-start eligibility without the cross-posture substitution the state machine marks REJECT. Compounded by `validate_installed_triple` rejecting any non-`False` `live_authority`, which no artifact plans to change.

### REQUIRED

**R1 — Interposition list is a re-label of the bridge-module capability vocabulary, not Event-06 consumer boundaries.** The ten items track `bridge_module_prohibited_capabilities` in `f017-event06-v12-to-v11-bridge-capability-v1.json`. None of the measured Event-06 access functions recorded in the Sequence 4 failure artifact (`_validate_producer`, `validate_candidate_triple`, `install_noncanonical_candidate`, `validate_installed_triple`, `bank_candidate`) or the actual primitives is named.

**R2 — The plan is never stated to be fail-closed.** The artifact has no fail-closed field. The predecessor bridge contract it borrows vocabulary from carries `qualification_spy_policy: {binds_real_consumer_signatures: true, bypasses_consumer_signatures: false, fails_if_prohibited_capability_reached: true, synthetic_temporary_roots_only: true, original_checkpoint_name_or_root_discovery: "PROHIBITED"}`. Sequence 5 states none of these, yet claim S5-DESIGN-NOACCESS asserts fail-closed interposition.

**R3 — The failure matrix is not a total map.** 14 categories vs 9 `exact_failure_outcomes` with `generic_fallback: false`, no category→outcome mapping, no per-category counts. The readiness-side categories have no failure-outcome vocabulary anywhere (the predecessor raises bare `ValueError`). `failure_prefix: "NO_LIVE_WRITE"` is never reconciled with the actual `F017_V12_PRODUCTION_INSTALL_` prefix. `minimum_mutations: 240` has no derivation from the census (75 missing + 75 wrong-type + 27 wrong-value = 177 on the readiness side alone).

**R4 — Sequence 4 findings can be discharged vacuously.** Sequence 4 closed with 4 blocking findings (B-CYCLE02-CHALLENGE-FALSE-VERIFICATION, B-CLAIM-LEDGER-CONTRADICTION, B-SUPPORT-LEDGER-COUNTERS, B-CYCLE01-ARBITRATION-UNAUDITABLE) and 4 unresolved findings, with an `exact_next_safe_action` requiring append-only repair plus an independently attested re-challenge before a new GO. Sequence 5 offers only an opaque `sequence4_finding_disposition_path`/`_sha256` role with no required content, IDs, or count. The census counter is `unresolved_claims` (claims), not `unresolved_findings` — a declaration can satisfy `unresolved_claims: 0` with all four Sequence 4 unresolved findings open. `challenge_provenance_path` carries no attestation requirement despite U-CHALLENGE-TRANSPORT-PROVENANCE.

**R5 — `supersedes_path` vs the layer-2 constraint is unresolved.** It is typed `repository_path` and follows the `<role>_path`/`<role>_sha256` convention the predecessor consumer uses to require manifest membership for every `_path` except `authority_manifest_path`. That forces the layer-2 manifest to bind a prior layer-3 final declaration, contradicting `may_bind_final_declaration: false`. No exemption is stated.

### ADVISORY

- **A1** — v1's `p1_attempt_2_executed: false` and 12.1.0's `p1_attempt_2_authority_or_execution: "NONE"` are both dropped; only `ready_to_prepare_p1_attempt_2_authorization: false` remains, losing an explicit non-execution invariant.
- **A2** — The claim ledger records all 3 claims SUPPORTED / `unresolved: 0` while graph state has `D3 independent design review = PENDING`, pre-stating the outcome D3 produces. Same class as Sequence 4's B-CLAIM-LEDGER-CONTRADICTION.
- **A3** — No posture-specific failure outcome exists despite a "posture" failure category and `cross_posture_substitution: REJECT`.
- **A4** — The field census omits `exact_predicates`; `result: FROZEN` freezes fields and types only, not values.

## Unresolved claims

- **U1** — Whether `exact_predicates` is intended as the exhaustive value-constraint set is undeterminable; the commit contains no successor consumer module and no exhaustiveness statement.
- **U2** — The intended mapping from the three new posture names to (`posture`, `authority_scope`, `live_authority`) is not determinable.
- **U3** — Required content of the `sequence4_finding_disposition`, `challenge_provenance`, `canonical_readiness_qualification`, `installation_preparation_qualification`, and `full_corpus_validation` roles is stated nowhere; whether they discharge the Sequence 4 findings is undecidable.

## Global verdict

**REJECT** — 6 blocking, 5 required, 3 unresolved. Acceptance requires zero of each; no conditional acceptance offered.

The agy ACCEPT with zero findings is not reproducible against this commit: B1, B3, B5 and B6 are each decidable by direct comparison of the committed artifacts against each other and against the in-tree consumer modules, and the drift/field-partition checks that do pass are the only mechanical properties the design currently supports.
