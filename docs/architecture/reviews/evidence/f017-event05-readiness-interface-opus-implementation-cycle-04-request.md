# F017 Event 05 readiness interface — Opus implementation arbiter cycle 04

Use `claude-opus-5`, high effort, a fresh detached read-only checkout, and committed bytes only. Begin with `git rev-parse HEAD`; bind every claim verdict and the global verdict to that exact detached head. Do not modify files, access checkpoint shards, mint or execute Event 05, or execute P1 attempt 2.

This cycle reviews the complete repaired implementation after cycle 03 findings F-F and F-G. Independently verify:

- final-scope reviewer artifacts bind a real reviewed commit descending from the measured implementation head;
- `exact_response_path` is repository-relative and its exact bytes recompute to `exact_response_sha256`;
- final-scope Gemini and Opus predicates are exact and scope-specific;
- the generated 251-case campaign includes 20 final-scope reviewer-binding mutations and actually executes the final validation branch;
- uppercase/conflicting aliases, stale authority bindings, fake review commits, response-path/SHA substitutions, and candidate-path divergence fail closed;
- FULL_NATIVE run `33049485460` is successful at head `5357dbf580dff5332830818ebbbb9de042ab0968`, with zero required skips;
- numerical and result authority drift remain zero;
- validation has zero checkpoint access and creates no Event 05 live authority/state.

Primary evidence includes:

- `scripts/research/f017_event05_readiness_authority_v1.py`
- `scripts/research/validate_f017_corrected_oracle_access_v11.py`
- `scripts/research/f017_event05_candidate_builder_v1.py`
- `scripts/research/qualify_f017_event05_readiness_interface_v1.py`
- `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event05-readiness-consumer-interface-v3.json`
- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-qualification-v4.json`
- `docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v8.json`
- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-full-native-ci-v8.json`
- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-gemini-whole-domain-cycle-03-provenance-repair-confirmation-normalized-result.json`
- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-opus-implementation-cycle-03-normalized-result.json`

Issue one verdict (`ACCEPT`, `REJECT`, or `UNRESOLVED`) for each of: C-SCHEMA-001, C-SCHEMA-002, C-VALIDATOR-001, C-AUTHORIZER-001, C-INSTANT-001, C-INSTANT-002, C-BIND-001, C-SAFETY-001, C-LEGACY-001, C-CI-001, C-REVIEW-001, C-GO-001.

Return concise JSON containing `model`, `reviewed_head`, `effort`, `claim_verdicts`, `findings`, `accepted_claims`, `rejected_claims`, `unresolved_claims`, `blocking_findings`, `non_blocking_required_findings`, `original_checkpoint_access`, and `global_verdict`. The global verdict must be exactly `ACCEPT_F017_EVENT05_READINESS_INTERFACE_IMPLEMENTATION` or `REJECT`; no conditional acceptance.
