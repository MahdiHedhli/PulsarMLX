# PulsarMLX F017 DPREFIX Numerical-Surface Closure Report

## Disposition

`GO FOR DPREFIX NUMERICAL-SURFACE CLOSURE ADVERSARIAL REVIEW`

The independently upheld `TIER_B_NUMERICAL_SURFACE_UNINSTANTIABLE` blocker is closed checkpoint-free. The frozen Tier-B contract remains byte-identical at `9d1a6cc20ce8325fe8395334416f5ebcf980b72f02c6a0b44dc3240e0810024a`. `DPREFIX-REAL-1` remains authorized, unconsumed, unexecuted, and without checkpoint access. The real-payload ledger remains 59.

The two prior `INFRASTRUCTURE` non-execution events remain immutable history. The continuation decision remains `SAME UNCONSUMED DPREFIX ATTEMPT MAY CONTINUE`: the attempt ID denotes real-budget consumption, while authorization revisions are append-only lineage events.

## Frozen paired-value surface

The contract-derived surface manifest is `docs/architecture/reviews/evidence/f017-dprefix-numerical-surface-manifest-v1.json` (SHA-256 `ecbc47bf1af97db99308a24e9303f2f6ef75d2f78d31d4853d8106afe0b271ec`). It maps every Tier-B field explicitly to candidate and oracle producers:

| Surface | Retention | Max abs | RMSE | Cosine |
|---|---|---:|---:|---:|
| embedding | B, exact input identity | 0 | 0 | 1 |
| layer 0 attention | B | 9.313225746154785e-8 | 5.986186099532666e-8 | 0.9999999999973668 |
| layer 0 output | B | 1.7881393432617188e-7 | 6.552901157436962e-8 | 0.9999999999999883 |
| layer 1 attention | B | 9.313225746154785e-9 | 3.769325273824005e-9 | 0.9999999999999538 |
| layer 1 output | B | 2.384185791015625e-7 | 7.038008911987778e-8 | 0.999999999999987 |
| layer 2 attention | B | 3.4458935260772705e-8 | 2.0372388817621303e-8 | 0.9999999999976434 |
| layer 2 output | A | 2.980232238769531e-7 | 8.784636688537564e-8 | 0.9999999999999795 |
| layer 3 entry | A, permanent 6,144-f32 retention | 2.980232238769531e-7 | 8.784636688537564e-8 | 0.9999999999999795 |

Class B values live until deterministic metric computation, canonical hashing, and diagnostics finish. Class A retains full canonical values. Hash-only retention is forbidden for every metric-bearing surface. The final layer-3 entry state remains an actual immutable 24,576-byte LE-f32 artifact.

## Candidate successor

The successor candidate adds observation only: it exports canonical values already produced after existing readbacks. It does not change arithmetic, reduction order, native dispatch grouping, or model semantics.

- predecessor executable: `69b8cda5e3a6e600d29c899cb75ac4cdcf98ef301f50d506240c3499c918ae4f`
- successor executable: `1a73dd4026592e21df05a82df806e52ebcb8dd0248aaffc0d8fd91c6f9e1387a`
- successor source-manifest identity: `1df94bc11a550dc589666fdbdac6fd3cd0c7bdc17ab76f2fd8a74f705dfed35d`
- candidate source-manifest artifact SHA-256: `031801d5d42c7e91823904f664670f4ea74ea727f746bdf64ada4ebef80c58f2`
- build-manifest artifact SHA-256: `0cf2db7205f0ca4e7f4f23111042a4884c2537221fe00baab7ca71342672e796`
- toolchain: Rust/Cargo 1.97.1, `aarch64-apple-darwin`
- native bindings: reviewed `libmlx` `6622caeb...` and `libmlxc` `a060915d...`

All ten predecessor/successor repeat-stage hashes and the retained final state are exact. Native dispatches remain 450, readbacks remain 450, fallback remains zero, and backend errors remain zero. Instrumentation adds eight host copies totaling 196,608 bytes and no native dispatch or readback.

## Oracle successor and metric engine

The NumPy oracle preserves exact canonical model output and remains independent: no MLX, Rust FFI, candidate helper, candidate output, or candidate expected value is used.

- predecessor package: `4f8344057c962c96f969aeb8dc60b833939dc64dd59ab5addec4b4c2249c486f`
- successor source-manifest identity: `a3900bb70a0255c1484d19b5f9988135f63ff9e8176276361be6c499cc73aea8`
- successor immutable package identity: `9b00ed225acc9b299c5bd789f1b082f6a2fd90b7893913bc9f353f99ee83c89b`
- environment: CPython 3.13.13, NumPy 2.4.5, no PRNG
- metric engine source SHA-256: `cd7ca4eee855b60b6695b8ac6671d59eae2f446231f437168df0985f984ad738`

The standalone metric engine consumes paired canonical LE-f32 bytes, rejects shape, dtype, serialization, and non-finite defects, and computes max absolute error, RMSE, cosine, non-finite counts, and signed-zero mismatches without trusting producer PASS flags. Directed exact, ULP, signed-zero, outlier, distributed-error, cosine, zero-norm, non-finite, and descriptor tests pass.

## Rehearsal, schema, and admission

The production-width rehearsal artifact is `docs/architecture/reviews/evidence/f017-dprefix-full-tier-b-synthetic-rehearsal-v1.json` (SHA-256 `b6fb821a364f05c607e069f914b67a3b4c09fe2cf405e1282b0c0701792ab69f`). It records `FULL_TIER_B_SURFACE_INSTANTIABLE_CHECKPOINT_FREE`, all eight populated surfaces, ten deterministic repeats, clean lifecycle, and operational retention.

The earlier final max-abs and RMSE reproduce exactly. Cosine changes by `7.771561172376096e-16` because the new deterministic scalar `math.fsum` accumulation differs from the old NumPy reduction; candidate and oracle canonical f32 bytes are unchanged.

Evidence schema v4 SHA-256 is `bbe43a845db568e0c43ec893e936fc56221a93b3156ad2e9b3ce2942c14844d4`. It requires each semantic surface exactly once and rejects missing/duplicate surfaces or missing paired metrics. Stage injections localize embedding, attention, layer-output, and final-state failures.

Paired-value overhead does not change the 27 GiB floor. The additional candidate surfaces, oracle surfaces, and metric workspace are each 196,608 bytes; the existing allocator allowance and 1.25 reserve absorb this overhead. The floor was not lowered.

## Successor authorization state

- config v4 artifact SHA-256: `042a1fac64813849ae1569fee05d60be6a86fba0f7ef874dbdaeb85c29252266`
- authorization binding v3 artifact SHA-256: `86fbf397b462f23fd6bb9d911afcc332b348bf60426d80790dec3b691ff6ee6c`
- attempt ledger v4 artifact SHA-256: `dd6ad01a2a38235dfd84a25269d0513c813ba7c87171ed3a898c7566ef63001e`
- canonical preflight: `READY_TO_EXECUTE_DENSE_PREFIX_REAL_CAPTURE`
- state: `AUTHORIZED_UNCONSUMED_NOT_EXECUTED_PENDING_INDEPENDENT_REVIEW`
- real checkpoint access: 0
- ledger: 59

The config preserves prompt `Hello`, token 9703, position 0, 40 payloads, 1,431,263,232 packed bytes, ledger plan 59 to 99, Q4/Q6 hard identity gates, ten repeats, frozen Tier-B, no retry, and no automatic M1-F0.

Final-head Apple CI run `31944939942` passed both `Apple Silicon workspace baseline` and `Apple MLX small-fixture validation` at exact preparation head `3f635806b11631cc9c54d0f34ce733501b712f03`, including the built successor-binary rehearsal and complete eight-surface Tier-B instantiation with no relevant skips. The append-only binding is recorded in `docs/architecture/reviews/evidence/f017-ci-run-head-binding-ledger-v1.json`.

## Exact next action

Independent adversarial review of the numerical-surface delta packet. Only `GO FOR ONE DENSE-PREFIX M1-F(-1) REAL CAPTURE` releases the still-unconsumed attempt for one real 40-read execution.
