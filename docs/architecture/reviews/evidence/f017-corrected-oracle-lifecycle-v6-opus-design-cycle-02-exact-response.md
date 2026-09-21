The plan-file tools aren't available in this session, so here is the review in full.

# F017 lifecycle V6 semantic design — Opus cycle 02

**Reviewed head:** `409fc731cb14a411173560eaafa2d190f2a8db6d` (worktree clean, no files modified)
**Constraints honored:** no checkpoint shard opened, no Event-04 authority minted, no Event-04 state created, no oracle executed, no P1 attempt 2.

## Reproduction

`validate_f017_lifecycle_semantic_authority_v6.py` → `PASS`: 26 states, 29 transitions, 11 outcome classes, 29 artifact classes, 149 identities, 3892 required cells, 56 mutations rejected — byte-identical to `f017-corrected-oracle-lifecycle-v6-design-qualification-v2.json`. All 9 manifest SHAs match committed bytes.

## Cycle-01 repairs re-attacked — all three hold

- **B1** (same-transition artifacts bound each other's SHAs). Diff confirms `(visible | introduced) - {own_sha}` → `available - {own_sha}` with incremental `available.add(own_sha)` in both generator (`generate_f017_lifecycle_v6_authorities.py:106`) and validator (`validate_f017_lifecycle_semantic_authority_v6.py:598`), plus a new DFS check at `:887-909`. I recomputed the graph independently (Kahn sort over union of matrix edges): **29/29 ordered, acyclic**. Every required SHA binding names an artifact strictly earlier in the per-variant bank order; no artifact binds its own SHA; the cross-artifact graph is one-way (`f017-canonical-json-bytes-v6.json → model`, model references no v6 authority), so `model → {8 views} → manifest` is a realizable write order.
- **N1**. `complete_model` anchor added. I ran 9 coordinated model-mutation + full-regeneration attacks through the real generator: **9/9 rejected**.
- **N2**. Registry/matrix schema IDs exactly validated; artifact-schemas and the four derived documents are covered transitively. **13/13 forgery probes rejected.**
- Validator imports only stdlib (`argparse, copy, hashlib, json, dataclasses, itertools, pathlib, typing`). P1 stays `PROHIBITED`; `active_live_generation: "NONE"`; operator-go template inert.

## BLOCKING

**B1-C2 — pinned `authority_scope` is unsatisfiable and self-contradictory within one authority.**
The model pins `pinned_values.authority_scope = "F017_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT"` — which is the `/event_class` value from `scientific-access-v6.json`, a category error inherited from v4/v5. The same interface publishes `interface_scope: "PRODUCTION"`, new in v6 and **enforced**: `f017_corrected_oracle_authorization_v6.py:139` requires `interface_scope == document["authority_scope"]`; `f017_corrected_oracle_wrapper_support_v6.py:44` requires the literal `"PRODUCTION"`; the inert production template and both historical live authorizations carry `"PRODUCTION"`. No document satisfies both. I checked all 26 pinned values against the production template: 25 are satisfiable and enforced; `authority_scope` is the sole outlier. `_expected_interface` hardcodes `interface_scope` and copies `pinned_values` side by side without ever cross-checking them.

**B2-C2 — `TERMINAL::PRE_MINT_FAILURE` is unrealizable.**
Trace `["F00_PRE_MINT_FAILURE"]` from `DESIGN_ONLY`; required artifacts `["evidence_failure"]`; `candidate_authorization`, `installed_authorization` and `operator_approval` all forbidden. Yet the matrix requires `evidence_failure` to carry **122** bindings for that variant, all `source: AUTHORIZATION_DOCUMENT` / `EXACT_TYPED_EQUALITY_TO_FIRST_INTRODUCTION`, including `authorization_id` and `package_attempt_id`; and `artifact_path_descriptors.evidence_failure.leaf_identity = "package_attempt_id"`, so the file cannot even be named. `_expected_binding_surface` seeds `visible = base` unconditionally, so the 122 authorization identities are assumed available in every variant regardless of whether an authorization document may exist there.

**B3-C2 — the machine is not total over its own declared failure points.**
7 of 29 transitions declare a non-`EVIDENCE_BANKING_FAILURE` outcome with no terminalizing transition reachable from their source: `T02_PREFLIGHT`, `T03_RENDER_CANDIDATE`, `T04_PRIMARY_VALIDATE_CANDIDATE`, `T05_SECONDARY_VALIDATE_CANDIDATE` (all `PRE_MINT_FAILURE`), `T07_BANK_INSTALL_RECEIPT` (`INSTALLATION_FAILURE`), `T09_HANDSHAKE` (`HANDSHAKE_FAILURE`), `T11_START_PACKAGE` (`PACKAGE_PRE_START_FAILURE`). `evidence_failure` is bankable only from 4 states, and in each corresponding `FAILED::` variant it is a *forbidden* artifact — the design forbids the only durable-evidence artifact exactly where nothing can produce it. Its payload census (`failed_transition`, `durable_artifacts_before_failure`, `ledger_deltas_before_failure`) shows it was meant to be bankable from arbitrary states. With B2-C2, the whole `PRE_MINT_FAILURE` class has no realizable representation.

## NON_BLOCKING_REQUIRED

**N1-C2 — fabricated unstarted-consumer evidence at field level.** `package_receipt.payload` always carries `{primary,secondary}_{receipt,terminal}_sha256`; the binding is required only in started outcomes (`secondary_receipt_sha256`: 3 of 39 variants). No `must_be_null` obligation exists anywhere — `nullable_package_receipt_fields` only names them — and `_variant_obligation` checks fabrication at artifact granularity only. `{primary,secondary}_disposition` are unbound and untied to `package_consumer_disposition`.

**N2-C2 — canonical-JSON contract does not fix number formatting.** The contract fixes encoding, ordering, separators, escaping, BOM, duplicate/non-finite rejection and trailing newline, but not how finite non-integer numbers render. `comparison_receipt`'s payload is `compare()`'s output — `max_absolute_error`, `rmse`, `cosine_similarity` are floats — and its digest is bound into `comparison_terminal` and `package_receipt`. Under `SHA256_EXACT_CANONICAL_BYTES_OF_COMPLETE_ARTIFACT`, that digest is not reproducible in the Rust runtime this design targets. The only serialization probe is `{"z":[1,true,null],"a":"\u00e9"}` — no float.

**N3-C2 — nothing binds the executed control path to the design.** `execute_f017_corrected_oracle_event_v6.py` never creates `package_ledger_index`, `primary_ledger_index`, `secondary_ledger_index` (3 of 29 classes, members of `same_commit_banking`), and its payloads diverge from `artifact_payload_key_census` for at least `package_durable_start`, `package_ledger_entry`, both `*_durable_start`, both `*_receipt`, `comparison_receipt`, `package_receipt`; it writes 6 bindings where the matrix requires 100+. No test or qualifier compares produced artifacts to the artifact-schemas authority or the binding matrix.

**N4-C2 — fabricated qualification accounting, gated by CI.** `qualify_f017_lifecycle_v6.py` reports `failure_trace_count = variant_count * --failure-repeats` while executing zero failure traces (`qualify_outcomes()` ignores `failure_repeats`); `format_count: 11`, `packed_decoder_cases: 44` and the four process counts are constants/multipliers. `.github/workflows/macos.yml` asserts `failure_trace_count >= 195` — a gate on a product of a CLI flag. `execute_synthetic` also returns `historical_ledger_before/after = 175` as literals.

## DEFENSE_IN_DEPTH

- **D1-C2** bank order (the B1 repair's premise) is carried only by JSON list order plus a duplicated hardcoded `same_commit_banking`; not stated normatively.
- **D2-C2** `LIVE_ID.forbidden_markers` omits REHEARSAL; `rehearse_...event04_v6.py` mints `state:AUTHORIZED, live:true` docs with grammar-valid `F017-EVENT-04-REHEARSAL-*` IDs. `construct_candidate_from_inert` marker-checks `authorization_id` only.
- **D3-C2** unbound payload keys: `prior_entry_sha256`, `sequence`, `target`, `delta`, `actual_deltas`, `durable_artifacts_before_failure`, `ledger_deltas_before_failure`, `access_census_sha256`, `output_manifest_sha256`, `metrics`, `classification`, `{primary,secondary}_result_sha256`, `side_effects`.
- **D4-C2** measurement census omits both v6 test modules, `update_f017_lifecycle_v6_measurement_census.py`, `extract_..._target_sources_v6.py`, both `retire_..._v6.py`, `validate_f017_historical_corrected_oracle_authorities_v6.py`, and the v4/v5 generators/validators (`validate_f017_corrected_oracle_lifecycle_v4.py` is also outside the tombstone set).
- **D5-C2** `HISTORICAL_REAL_PAYLOAD_LEDGER.authority_path` is absent from this tree (branch `feat/017-real-checkpoint-runner`); 175/175/Δ0 rests on an unverifiable pinned SHA.
- **D6-C2** `satisfiability: "PASS"` and `lifecycle_binding_coverage: "COMPLETE"` are literals; `simulate_trace` never checks that an artifact's `parent_role` exists at creation (independently verified: 0 violations here; the 36-pair root relation matrix is complete and consistent).
- **D7-C2** `*_accounting_class` identities have no pinned value in v6 (v4 pinned them); nothing binds an authorization's accounting class to `ledger_targets`.

## Verdict

`REJECT`
