# F017 Event 06 V12-to-V11 bridge — Gemini design challenge cycle 1

Act as the CHALLENGE reviewer using gemini-3.1-pro-high at high effort. Review committed source head `8bc069c7805bfcfdd771bd6f1d7887ae619bc3a2` on branch `feat/017-rust-native-inference-runtime`. Do not edit files and do not access checkpoint data.

Reconstruct the terminal parent failure from `f017-event06-v12-pre-mint-call-path-failure-v2.json`, then review these proposed design bytes:

- `specs/017-rust-native-inference-runtime/contracts/f017-event06-v12-to-v11-numerical-authority-bridge-v1.json`
- `specs/017-rust-native-inference-runtime/contracts/f017-event06-v12-to-v11-bridge-lifecycle-v1.json`
- `specs/017-rust-native-inference-runtime/contracts/f017-event06-v12-to-v11-bridge-capability-v1.json`
- `docs/architecture/reviews/evidence/f017-event06-v12-to-v11-bridge-design-v1.md`
- `docs/architecture/reviews/evidence/f017-event06-v12-to-v11-bridge-design-claim-ledger-v1.json`

Attack generation truth, provenance completeness, canonical digest construction, sealed-object feasibility, descriptor and lease bindings, role-view least authority, historical V11/V12 admission, exact consumer signatures, coordinator completeness, secondary ordering, one-shot behavior, lifecycle terminality, event-number capability branching, reconstruction, no-access qualification, and V4/V11 byte preservation.

Return a structured challenge report with one row per finding: ID, severity (`BLOCKING`, `REQUIRED`, `ADVISORY`), affected claim, evidence, attack or counterexample, required resolution, and status. End with exactly one design verdict: `ACCEPT_FOR_OPUS_DESIGN_ARBITRATION` or `REPAIR_REQUIRED`. Acceptance requires zero blocking and zero required findings.
