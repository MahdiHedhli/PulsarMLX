# F017 Event 05 readiness-interface Gemini whole-domain CHALLENGE — cycle 02

Use `gemini-3.1-pro-high` at high effort in a fresh read-only session. Review exact committed bytes at the commit containing this request. Do not modify files, access checkpoint shards, mint or execute Event 05, or execute P1 attempt 2.

Cycle 01 was invalid only because it reported the packet parent as `reviewed_head`. Before reading the packet, execute `git rev-parse HEAD` in this detached worktree. Your `reviewed_head` value MUST be that exact 40-character result. Do not copy `packet_parent_head` from the manifest; it intentionally names an earlier commit.

Read every artifact in `docs/architecture/reviews/evidence/f017-event05-readiness-interface-whole-domain-review-manifest-v1.json`, independently recompute all 19 bindings, and inspect the complete implementations and imports.

Attack canonical schema/type exactness, alias rejection, complete safety predicates, authority resolution, stale bindings, one canonical validator, absence of authorizer-local readiness logic, shared candidate construction, live approval revalidation immediately before install, validation-only isolation, historical supersession, all 226 mutations, final-byte instantiability planning, FULL_NATIVE run 33036531209, numerical/result drift, checkpoint access, Event 05 authority absence, and P1 attempt-2 absence.

Create a challenge row for every material weakness. Each row must contain `challenge_id`, `claim_id`, `attack`, `mutation_or_trace`, `expected_behavior`, `observed_behavior`, `severity`, `affected_artifacts`, and `status`.

Return one JSON object and no Markdown fences or prose with exactly these keys: `reviewer_model`, `effort`, `reviewed_head`, `packet_read`, `recomputed_binding_count`, `sha_mismatches`, `challenges`, `blocking_count`, `non_blocking_required_count`, `defense_in_depth_count`, and `verdict`.

Set `reviewer_model` exactly to `gemini-3.1-pro-high`. Use verdict `NO_UNRESOLVED_MATERIAL_CHALLENGE` only if no blocking or non-blocking-required issue remains.
