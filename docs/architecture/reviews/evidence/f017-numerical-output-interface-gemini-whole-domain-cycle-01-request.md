# F017 V11 whole-domain CHALLENGE review — cycle 01

Use `gemini-3.1-pro-high` at high effort. Work read-only from exact committed
head `72cd12f0` on branch `feat/017-rust-native-inference-runtime`. Repository
evidence outranks this request.

Do not modify repository bytes, access original checkpoint shards, execute or
authorize Event 05, retry or resume Event 04, or execute P1 attempt 2.

Act only as the CHALLENGE reviewer. Attack every readiness-critical claim:

- `C-OUT-001`, `C-OUT-002`: one execution exposes hidden, normalized, logits.
- `C-FORM-001`, `C-FORM-002`: formulas and operation order are V2-equivalent.
- `C-LEGACY-001`, `C-LEGACY-002`: legacy APIs are exact.
- `C-BITS-001`, `C-BITS-002`: immutable payload bits match legacy hashes.
- `C-PURITY-001`: no file/checkpoint/lifecycle/reflection/callback capability.
- `C-ONEEXEC-001`: no recomputation or repeated source traversal.
- `C-INDEP-001`: primary and secondary remain independent.
- `C-QUAL-001`: numerical requalification is complete and truthful.
- `C-V11-001`: V11 banks all six payloads from one execution per role.
- `C-V11-002`: manifests, receipts, terminals, and package closure bind bytes.
- `C-CI-001`: exact-head FULL_NATIVE run `32981760971` is load-bearing.

Required attacks include formula-preserving V2-to-V3 changes, mutable aliases,
control-JSON leakage, hidden/normalization/projection recomputation, source-read
drift, primary/secondary common-mode coupling, exact binary geometry and
endianness, writer/readback integrity, bundle identity and closure, primary
terminal gating before secondary, Event 04 diagnostic nonpromotion, all 360
modeled fault cases, the production-shaped zero-access rehearsal, generated
authority drift checks, implementation measurement completeness, and CI
provenance. Independently verify Event 05 authority is absent, Event 05 was not
executed, original-checkpoint access is zero, Event 04 is terminal without
retry/resume, P1 attempt 2 is absent, and the historical ledger is 175.

Primary packet:

- `docs/architecture/reviews/evidence/f017-numerical-output-interface-claim-ledger-v8.json`
- `docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v1.json`
- `specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v11.json`
- `docs/architecture/reviews/evidence/f017-v11-full-geometry-qualification-v1.json`
- `docs/architecture/reviews/evidence/f017-v11-result-failure-qualification-v1.json`
- `docs/architecture/reviews/evidence/f017-event05-production-shaped-no-access-rehearsal-v11-v1.json`
- `docs/architecture/reviews/evidence/f017-v11-event05-full-native-ci-v1.json`
- `docs/architecture/reviews/evidence/f017-corrected-oracle-numerical-requalification-v4.json`
- `docs/architecture/reviews/evidence/f017-numerical-output-interface-opus-numerical-cycle-02-normalized-result.json`

Return one JSON object with `reviewed_head`, `reviewer_model`,
`attacked_claim_ids`, `challenges`, `original_checkpoint_access_observed`, and
`review_transport_status`. Each challenge row must contain `challenge_id`,
`claim_id`, `attack`, `mutation_or_trace`, `expected_behavior`,
`observed_behavior`, `severity` (`BLOCKING`, `NON_BLOCKING_REQUIRED`, or
`DEFENSE_IN_DEPTH`), `affected_artifacts`, and `status`. Return an empty
`challenges` array when no challenge is supported. Do not issue the final Opus
arbiter verdict.
