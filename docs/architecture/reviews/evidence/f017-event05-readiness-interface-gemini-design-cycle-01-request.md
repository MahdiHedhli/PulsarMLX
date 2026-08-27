# F017 Event 05 readiness-interface Gemini design CHALLENGE — cycle 01

Use `gemini-3.1-pro-high` at high effort in a fresh read-only session. Review exact committed bytes at the commit containing this request. Repository bytes outrank the request. Do not modify files, access checkpoint shards, mint Event 05 authority, execute Event 05, or execute P1 attempt 2.

Reconstruct the terminal E0 failure, including the earlier noncanonical-byte decode failure and the subsequent lower-case/upper-case field mismatch. Attack every readiness-critical design claim and create structured challenge rows. In particular attack:

- the 56-field canonical lower-case schema and exact types;
- unknown, duplicate, uppercase, conflicting, and normalized aliases;
- missing safety predicates;
- declaration/manifest, measurement, scientific-access, numerical, CI, and reviewer divergence;
- the proposed single readiness validator;
- duplicate authorizer-local logic;
- the shared candidate builder;
- validation-only installation and ID-consumption escape paths;
- final committed-byte instantiability;
- historical authorizer supersession.

Return JSON with keys `reviewer_model`, `effort`, `reviewed_head`, `challenges`, `blocking_count`, `non_blocking_required_count`, `defense_in_depth_count`, and `verdict`. Each challenge must include `challenge_id`, `claim_id`, `attack`, `expected_behavior`, `severity`, and `status`. The verdict is `NO_MATERIAL_CHALLENGE` only if there is no blocking or non-blocking-required design defect; otherwise return `CHALLENGE`.

Primary packet:

- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-mismatch-reproduction-v1.json`
- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-versioning-decision-v1.json`
- `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event05-readiness-consumer-interface-v1.json`
- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-design-authority-v1.json`
- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-mutation-plan-v1.json`
- `docs/architecture/reviews/evidence/f017-event05-readiness-interface-claim-ledger-v1.json`

