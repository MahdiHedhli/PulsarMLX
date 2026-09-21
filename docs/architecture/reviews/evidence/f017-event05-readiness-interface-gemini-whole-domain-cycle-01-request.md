# F017 Event 05 readiness-interface Gemini whole-domain CHALLENGE — cycle 01

Use `gemini-3.1-pro-high` at high effort in a fresh read-only session. Review exact committed bytes at the commit containing this request. Do not modify files, access checkpoint shards, mint or execute Event 05, or execute P1 attempt 2.

Read every artifact in `docs/architecture/reviews/evidence/f017-event05-readiness-interface-whole-domain-review-manifest-v1.json` and independently recompute all 19 bindings. Inspect the complete implementations and their imports, not only the manifest summaries.

Attack the actual implementation across: canonical schema and exact types; alias rejection; complete safety predicates; transitive authority resolution; stale measurement, CI, and reviewer substitutions; one canonical validator; removal of authorizer-local uppercase logic; shared candidate construction; live approval admission and revalidation immediately before install; validation-only side effects; historical supersession; 226 mutation cases; deterministic final-byte construction plan; FULL_NATIVE run 33036531209; numerical/result byte drift; original checkpoint access; Event 05 authority absence; and P1 attempt-2 absence.

Create a challenge row for every material weakness. Each row must contain `challenge_id`, `claim_id`, `attack`, `mutation_or_trace`, `expected_behavior`, `observed_behavior`, `severity`, `affected_artifacts`, and `status`. Do not make the final arbiter decision.

Return one JSON object and no prose with exactly these keys: `reviewer_model`, `effort`, `reviewed_head`, `packet_read`, `recomputed_binding_count`, `sha_mismatches`, `challenges`, `blocking_count`, `non_blocking_required_count`, `defense_in_depth_count`, and `verdict`.

Use verdict `NO_UNRESOLVED_MATERIAL_CHALLENGE` only if every blocking and non-blocking-required challenge is absent or already closed by exact committed evidence.
