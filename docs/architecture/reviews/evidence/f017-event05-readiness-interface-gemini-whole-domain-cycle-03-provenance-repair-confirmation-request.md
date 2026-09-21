# F017 Event 05 readiness interface — Gemini whole-domain cycle 03 provenance repair confirmation

This is a final repair confirmation within whole-domain cycle 03, not a fourth challenge cycle. Use `gemini-3.1-pro-high`, high effort, a fresh detached read-only checkout, and committed bytes only. Begin with `git rev-parse HEAD`; bind every finding and the global verdict to that exact detached head. Do not modify files, access checkpoint shards, mint or execute Event 05, or execute P1 attempt 2.

Review the two findings from Opus implementation cycle 03 and their transitive claims:

1. Final-scope reviewer evidence must bind `reviewed_head` to a real Git commit that descends from the measured implementation head and must recompute `exact_response_sha256` from an exact repository-relative `exact_response_path`.
2. The generated mutation campaign must execute the `FINAL_EVENT05_EXECUTION_READINESS` reviewer-validation branch and reject reviewer scope/finality/model/verdict/count/head/response-path/response-SHA substitutions.

Primary evidence:

- `scripts/research/f017_event05_readiness_authority_v1.py`
- `scripts/research/qualify_f017_event05_readiness_interface_v1.py`
- `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event05-readiness-consumer-interface-v3.json`
- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-qualification-v4.json`
- `docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v8.json`
- `specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v11-v8.json`
- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-full-native-ci-v8.json`
- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-opus-implementation-cycle-03-normalized-result.json`

Independently rerun safe synthetic tests and mutations as useful. Verify original-checkpoint access remains zero and no Event 05 authority/state exists.

Return one concise JSON object with: `reviewer_model`, `reviewed_head`, `claims` (all 12 readiness-interface claim IDs with `ACCEPT`, `REJECT`, or `UNRESOLVED`), `findings` (ID, severity `BLOCKING`, `NON_BLOCKING_REQUIRED`, or `DEFENSE_IN_DEPTH`, claim IDs, evidence, disposition), `blocking_findings`, `non_blocking_required_findings`, `unresolved_claims`, `original_checkpoint_access`, and `verdict`. Use verdict `NO_UNRESOLVED_MATERIAL_CHALLENGE` only if no blocking, non-blocking-required, or unresolved issue remains.
