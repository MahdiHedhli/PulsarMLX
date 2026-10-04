# Selected numerical v2 tasks

All paths relative to repository unless stated. Sequential: no parallel workers.
US1 host design/proof is the first deliverable; it does not complete real scope.

## Setup and foundations
- [x] T001 Preserve accepted boundaries; write selected-numerical-v2/spec.md and plan.md under specs/020-mlx-safetensors-affine (FR01..FR10).
- [x] T002 Specify concrete population and contract in specs/020-mlx-safetensors-affine/selected-numerical-v2/population-v2.md and contracts/selected-numerical-v2.json (FR01..FR07).
- [x] T003 Cross-artifact read-only analysis and requirements checklist in specs/020-mlx-safetensors-affine/selected-numerical-v2/analysis-v2.md (FR01..FR10).

## US1: prospective host package
- [x] T004 [US1] Implement deterministic input/fixture generator scripts/research/f020_selected_fixtures_v2.py with bounded streaming generation and private receipts (FR01,FR02).
- [x] T005 [US1] Independent analytic synthetic domain and mutation proof scripts/research/f020_selected_proof_v2.py; tests scripts/research/tests/test_f020_selected_v2.py (FR02,FR03).

## US2: original-byte implementation
- [x] T006 [US2] Strict bounded reader/adversarial tests crates/mlx-expert-mlp/src/selected_snapshot.rs and crates/mlx-expert-mlp/tests/selected_snapshot.rs (FR04).
- [x] T007 [US2] Independent row-streamed scripts/research/f020_selected_r1_v2.py and host tests, never dense real-weight arrays (FR03,FR05).
- [x] T008 [US2] Owned native adapter and scoped geometry in crates/mlx-expert-mlp/src/selected_execute.rs; keep old scope unchanged (FR04,FR06).
- [x] T009 [US2] Resource ledger, hard owned/allocation limits, measured overhead and supervisor/watchdog in scripts/research/f020_selected_qualify_v2.py (FR07).

## US3: review and qualification
- [x] T010 [US3] Source tests and complete exact-version freeze/review/capability verification in scripts/research/f020_selected_qualify_v2.py; private raw review and sanitized receipt (FR08).
- [x] T011 [US3] Full synthetic run and inherited 363+32 regressions with all mutation predicates in private audit; sanitized specs/020-mlx-safetensors-affine/selected-numerical-v2/qualification.json (FR09).
- [x] T012 [US3] One original snapshot R1 admission and at most one admitted real candidate; private stage/resource/refusal evidence (FR03..FR09,SC01,SC02).

## Publication
- [ ] T013 Sanitized evidence review and scoped validated commit/push; exact CI terminal results in specs/020-mlx-safetensors-affine/selected-numerical-v2/qualification.json (FR10).

Dependencies: T001->T002->T003->T004->T005->T006->T007->T008->T009->T010->T011->T012->T013.
Independent tests: US1 closed-form exact domain and mutations; US2 malformed
snapshot and authority controls; US3 full stage gates and all required IDs.
No parallel opportunities exercised: one authorized implementation owner.

## Current implementation evidence (not numerical qualification)

T004: original v2 input and two full-shape positive payloads generated privately;
refusal/mutation materialization remains open. T005: analytic positivity, bias
and gate/up asymmetry proved with explicit optimizer-safe checks; remaining
control ID completeness stays open. T006: Rust and independent Python custody
readers tested, including real payload corruption in all nine synthetic ranges.
T007: row-streamed dyadic R1 implemented and host-tested; final authority wrapper
and resource qualification still pending. T008: packed host adapter/preflight
and separate selected activation shim implemented; native runner now linked behind exact review/admission checks; compile PASS, selected numerical calls zero.
Preliminary host review ACCEPT/0 from actual claude-opus-5-5, source hashes
independently matched; subsequent source changes require final exact review.

T009: allocation ledger, measured native/RSS gates and owned watchdog implemented; measurements pending final reviewed qualification. T010: independent Rust/Python provider validators and host report controls pass; source/build freeze and final review remain open.

Final review 01 BLOCKED/2 preserved at 9d286b0c. T010 reopened: actual decoder/native nibble witness, fixed issued-real ledger, raw population/build bindings and re-review required. All numerical gates remain closed.

## Contract v3 framing continuation

See [framing-correction-v3.md](framing-correction-v3.md) and [contract v3](contracts/selected-numerical-v3.json). The real header refusal is retained; no packed real bytes or real numerical observations occurred. T004/T006/T010/T011/T012 reopen for the strict scope-field correction and41-case population. Numerical definitions and inputv2 are unchanged. No constitution conflict: original writer/artifacts and failed ledger preserved, no admission relaxation or claim from metadata.

V3 implementation: strict Rust/Python scope validation and actual original-writer
small synthetic schema regression complete. Full-shape generator now includes
scope and both new refusal IDs. Host32Python and17Rust/ownership tests pass;
new full41 numerical qualification remains pending exact-version review.

## Observed contract v3 result (source d9639737)

T004..T011 completed: input/positive payload identities retained, strict capture
compatibility repaired, exact release review04 ACCEPT/0, host32Python/17Rust,
full41 synthetic and363/32 inherited PASS, requiredCI37184777213 SUCCESS.
T012 bounded attempt completed with **PRE_ADMISSION_REFUSED**, not qualified
real execution. Original gate/up R1 completed from the selected snapshot; the
hidden prospective down nonzero-floor margin failed. No ideal down reference
or native real call followed. Resource gates passed. The consumed ledger and
private raw evidence remain preserved. See qualification.json for sanitized
bindings, exclusions and the independently checked refusal predicate.

The real-execution success criterion remains unmet. A new authorized objective
or separately scoped study is required to proceed beyond this fixed-input
refusal; no retries or post-observation input/budget repair are authorized here.
T013 publication is in progress; final review/push/CI receipts remain in the
private audit. Historical status paragraphs above describe their earlier gates.
