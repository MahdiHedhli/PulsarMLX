# F017 native bounded-P1 domain — cross-vendor evidence-consistency review C3

This is a non-security correctness and evidence-consistency review. Do not conduct a vulnerability assessment, penetration test, exploit search, or security audit. Review only whether committed claims are supported by committed code, contracts, tests, and CI evidence. Do not modify files or execute real model payloads.

Review branch `feat/017-rust-native-inference-runtime` at exact detached head `aeca5b08ae96f6bd97f507c81ae373e4b86f9e90`. Inspect exact-head CI run `32560783265`. Git and CI are authoritative.

The primary packet is `docs/architecture/reviews/evidence/f017-native-bounded-p1-domain-final-review-package-v1.json`; exact P1 contract SHA `44b9416ff2c4e14ae3005e8df931443f38adb4ab49d5c173dcdf103a222a7dda`; banked executable SHA `3894c4d12c93ac4c4f3584d2a9a41370c5074e7ef91402cfd8b16bf698c9c7ba`; execution-code head `22a76e4c248434a1827e81501607f93b0779352e`.

Check specification conformance and evidence consistency for these questions:

1. Does exact-head CI actually run the native `f017-native` tests and explicit D3.5 comparison-grant/numerical-grading validators and mutation tests under the intended pinned runtime?
2. Are Python MLX 0.32.0 and native C/Rust MLX 0.31.2 isolated so neither resolves the other's incompatible dylib?
3. Are D0 tolerances predeclared independently of D3.5, with D3.5 permitted to falsify but not select thresholds?
4. Do D1 counters have live producers and meaningful invariants, and does D2 bind historical ledger 175 without creating a competing master count?
5. Does the math-only mock keep lifecycle/accounting/receipt/terminalization real while making the original checkpoint unreachable?
6. Does RN1 require exclusive owned claim and receipt-derived terminal accounting?
7. Do retained grants, 89 read receipts, 34-stage vocabulary/serialization, and zero original-checkpoint reads support the representative-layer D3.5 result without claiming the remaining 79 layers were directly retained-qualified?
8. Is the exact P1 contract instantiable and limited to one future human-authorized token step with no retry, resume, continuation, or validation-created live authorization?

Report any unsupported claim or inconsistency with a stable ID and one of `BLOCKING`, `NON_BLOCKING_REQUIRED`, or `DEFENSE_IN_DEPTH`, plus exact evidence and required correction. Both first two severities prevent acceptance. State whether cycle-1 CI omissions are closed. End with exactly one verdict: `NO_MATERIAL_DISAGREEMENT` or `MATERIAL_DISAGREEMENT_ESCALATE`.

Also state exactly:

`REAL_M1_ULTRA_P1_EXECUTED_DURING_REVIEW: NO`

`ORIGINAL_CHECKPOINT_READS_DURING_REVIEW: 0`

`LIVE_P1_AUTHORIZATION_CREATED_DURING_REVIEW: NO`
