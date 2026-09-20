# F017 native bounded-P1 — attempt 2 readiness (2026-09-20)

Status: **PREPARED_HUMAN_GATE_REQUIRED**. Nothing here executed on the real checkpoint; nothing is authorized.

## Where the native runtime stands
- Attempt 1 (2026-08-22, Mac Studio M1 Ultra, one human GO consumed): the native Rust + MLX one-token executor ran the real checkpoint in 123.5 s and produced token 17351 against the frozen expected token 21615 — a banked terminal failure; retry permanently prohibited. The root-cause ledger proved the *expected token* came from the defective F016 decoder family (Q6_K / IQ3_XXS lane permutations).
- Event 06 (2026-09-05, sequence 43, one human GO consumed): the corrected full-checkpoint oracle (independent binary64 CPU reference and an f32 accelerated cross-check) selected **154820** for the same prompt (9703, position 0, empty KV, greedy), margin 3.53, classification EXACT_EXPECTED_TOKEN_STABLE, accepted.
- This round (checkpoint-free, no GO needed):
  - the native production decoders (the secure loader's exact dispatch) are **bit-identical** to the corrected oracle's independent scalar decoders on synthetic blocks of all 11 formats in the checkpoint (`f017-native-decoder-differential-corrected-oracle-v1*.json`, MacBook and M1 Ultra);
  - the native full graph through the MLX bridge matches the corrected oracle's binary64 numerics on the 6-case synthetic family within the frozen thresholds, with identical expert selection (`f017-native-graph-vs-corrected-oracle-differential-v1*.json`);
  - the admission validator gained **generation 3** (schema 3.0.0): attempt id 2, expected token 154820, evidenced v4 receipt, mandatory corrected-oracle binding document; generation-2 rules are unchanged. (Generation 2 required the v2 receipt schema while `execute-evidenced-v4` requires v4, so no generation-2 contract could ever execute.)
  - contract v3 (`f017-native-bounded-p1-admission-contract-v3.json`) binds an executor **built on the M1 Ultra** with the pinned MLX 0.31.2 keg and Homebrew rustc 1.97.1 (`bin/f017-native-bounded-p1-v2`); `validate-contract`, `machine-preflight` and `plan-only` pass on the M1 Ultra with zero checkpoint reads; seven negative controls are rejected.
  - domain declaration v2, the final-review request packet, an inert human-approval template and a supporting adversarial review (ACCEPT, 0 blocking) are committed.

## What remains (in order)
1. Exact-head CI with native jobs on `feat/017-rust-native-inference-runtime`.
2. The operator-authorized final review (`claude-opus-5`, fresh session) with `ACCEPT_FOR_SINGLE_BOUNDED_M1_ULTRA_P1`, 0 blocking, 0 non-blocking-required — committed.
3. A human approval (`pulsarmlx.f017.native-bounded-p1-human-approval/1.0.0`, decision `AUTHORIZE_EXACTLY_ONE_BOUNDED_M1_ULTRA_P1`), `authorize`, then one `execute-evidenced-v4` on the M1 Ultra with ≥ 16 GiB available (pause the resident service first). Expected ≈ 2–3 minutes.

## What attempt 2 decides
Token 154820 → the native one-token boundary agrees with the corrected oracle on the real checkpoint (NATIVE_RUNTIME_TECHNICAL one-token level). Anything else → a banked failure with 79-layer fingerprints and full logits for diagnosis. Beyond P1, the native runtime still lacks multi-token generation, tokenizer/template handling and a CLI loop; those remain the frontier and every real-checkpoint run stays human-gated.

## Not claimed
Real-checkpoint agreement; a usable GLM-5.2 CLI; performance; any change to frozen tolerances or ledgers; Event 06 or attempt 1 replay.
