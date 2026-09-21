# F017 Event 05 readiness-interface Gemini design CHALLENGE — cycle 03

Use `gemini-3.1-pro-high` at high effort in a fresh read-only session. Review exact committed bytes at the commit containing this request. Do not modify files, access checkpoint shards, mint or execute Event 05, or execute P1 attempt 2.

Before deciding the verdict, read every file below from the detached worktree and independently recompute each SHA in `f017-event05-readiness-interface-authority-manifest-v2.json`:

- `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event05-readiness-consumer-interface-v1.json`
- `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event05-approval-interface-v1.json`
- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-design-authority-v1.json`
- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-mutation-plan-v1.json`
- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-review-protocol-v1.json`
- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-historical-tombstone-v1.json`
- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-authority-manifest-v2.json`
- `scripts/research/validate_f017_event05_readiness_interface_design_v1.py`
- `scripts/research/tests/test_f017_event05_readiness_interface_design_v1.py`

Attack every repaired Opus cycle-01 issue, especially:

1. design-review versus final-declaration reviewer scope and exact acceptance tokens;
2. transitive authority closure and stale-SHA rejection;
3. exact schema predicate and exhaustive field typing;
4. approval normalization, the declared candidate-difference allowlist, and installation-time live/expiry/readback enforcement;
5. the canonical declaration emitter and rejection of noncanonical bytes;
6. historical blob supersession without contradicting the future active-path repair;
7. receipt completeness and mutation coverage.

Your output must be one JSON object and no prose. It must contain exactly these keys: `reviewer_model`, `effort`, `reviewed_head`, `packet_read`, `recomputed_binding_count`, `sha_mismatches`, `challenges`, `blocking_count`, `non_blocking_required_count`, `defense_in_depth_count`, and `verdict`.

Requirements:

- `reviewed_head` must be the exact detached-worktree HEAD.
- `packet_read` must be `true` only after all listed files were read.
- `recomputed_binding_count` must be the independently observed manifest binding count.
- `sha_mismatches` must list every mismatch and must be empty for a valid packet.
- Each challenge must contain `challenge_id`, `claim_id`, `attack`, `mutation_or_trace`, `expected_behavior`, `observed_behavior`, `severity`, `affected_artifacts`, and `status`.
- Use `NO_MATERIAL_CHALLENGE` only if no blocking or non-blocking-required design issue remains.
