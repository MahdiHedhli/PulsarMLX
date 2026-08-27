# F017 Event 05 readiness interface — Opus final ratification cycle 01

Use `claude-opus-5`, high effort, a fresh detached read-only checkout, and committed bytes only. Begin with `git rev-parse HEAD` and bind the verdict to that exact head. Do not modify files, access checkpoint shards, mint or execute Event 05, or execute P1 attempt 2.

Ratify the exact final committed bytes:

- `docs/architecture/reviews/evidence/f017-corrected-oracle-event05-execution-readiness-final-declaration-v11-v2.json`
- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-runtime-authority-manifest-v1.json`
- `docs/architecture/reviews/evidence/f017-event05-final-readiness-declaration-instantiability-v1.json`
- `docs/architecture/reviews/evidence/f017-event05-final-readiness-validation-only-approval-v1.json`
- `scripts/research/f017_event05_readiness_authority_v1.py`
- `scripts/research/validate_f017_corrected_oracle_access_v11.py`
- `scripts/research/f017_event05_candidate_builder_v1.py`
- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-full-native-ci-v8.json`
- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-final-evidence-only-ci-v1.json`
- final Gemini and Opus implementation results transitively bound by the runtime manifest.

Verify the final declaration has exactly the canonical lower-case typed vocabulary, passes the measured authorizer through the shared validation-only candidate path, produces one deterministic candidate SHA across 20 repetitions, passes primary and secondary validation, creates no state or live authority, consumes no Event 05 ID, performs zero checkpoint access and numerical operations, and binds FULL_NATIVE run 33049485460 plus EVIDENCE_ONLY run 33053115610. Verify Event 05 and P1 attempt 2 remain absent and ledger 175 remains exact.

Return concise JSON with `model`, `reviewed_head`, `effort`, `declaration_sha256`, `instantiability_sha256`, `evidence_only_run`, `native_jobs_launched`, `checkpoint_access`, `event_05_authority_created`, `event_05_executed`, `p1_attempt_2_executed`, `findings`, and `verdict`. Verdict must be exactly `ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_05_EXECUTION_AUTHORIZATION_PREPARATION` or `REJECT`; no conditional acceptance.
