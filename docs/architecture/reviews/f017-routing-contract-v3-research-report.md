# PulsarMLX F017 Routing-Contract v3 Research Report

## Outcome

`READY FOR ROUTING-CONTRACT V3 ADVERSARIAL REVIEW`

- Starting SHA: `b3b0ca39961fbe9d770b58fd23c6e06b21265f8d`
- Final implementation/evidence SHA: `d5097cef57613bc1e508e276ef8746cd04732712`
- Final documentation head: the commit containing this report; its exact SHA and final Apple CI run-to-SHA binding are supplied in the operator handoff to avoid a self-referential commit identity.
- Real checkpoint access: `0`
- Real-payload ledger: `57` (unchanged)
- Frozen ladder execution: `false`
- Q6_K: `blocked`
- M1-F: `blocked`
- P1: `blocked`

## Runtime semantic classification

`ORDER_IS_NUMERICALLY_OBSERVABLE_NOT_MODEL_SEMANTIC`

The source trace found that router selection produces expert IDs and weights in
matching selected slots. The expert pointer, activation, and weight use the
same slot, while a storage-only ID sort/dedup does not alter the pair mapping.
There is no rank-indexed scale, expert behavior, capacity rule, cache rule,
shared-expert rule, or residual rule.

Rank is nevertheless numerically observable: the current plain and grouped
MoE kernels serially reduce selected slots in rank order, so a joint pair
permutation can change binary32 rounding. That runtime policy is retained; v3
does not alter the model runtime merely to make qualification easier.

Source identities are banked in
`f017-routing-contract-v3-source-trace-v1.json` (SHA-256
`356ffad4e72d6950605a0c0afb7cef3b549000a7de15c8b61f8216370fad3832`):

| Source | SHA-256 |
|---|---|
| `crates/kernels/cuda/pulsar_kernels.cu` | `0289a24bfd5d4c1ff0cc6632426228f5a5911c18c5acb5110dd3254fe4f39c97` |
| `crates/engine/src/lib.rs` | `20f672f194b0076c2634c79248e00b2c8a3121a1920adfaa9dda01afbf45b406` |
| `crates/backend/src/routing.rs` | `8b3729c60db19586cb0e7fb1a5e00b0d3787a760945b29f50aff6e0805e296b5` |
| `crates/f017-runner/src/layer_qualification.rs` | `4b70a22816a1a14d990bee15a5e57e1ea1963b1c37a666b89b07fa6633b240e3` |
| `scripts/research/generate_f017_r10_oracle.py` | `da5ade945be6c9f0887d98c1d54ffa3d54ce6a6ce727773714f592b75ff6cd22` |
| `scripts/research/layer_stack_parity.py` | `92ea3abaffed9c5903a6298eea853145b3bc16cc63b7e0b457986d1f83b01f1c` |

## Permutation proof and equivalence taxonomy

For eight unique atomic records `P = {(id_k, weight_k)}`, every joint
permutation has the same exact mathematical contribution:

`sum_k weight_k * expert_id_k(x)`.

The proof does not permit independently permuting IDs or weights. Duplicate,
missing, extra, zero, signed-zero, or non-finite records fail closed.

The versioned taxonomy (SHA-256
`5e2962f724a0898ad1e11aec37173228aa6aadac6943a6937c70e9dca61024b4`)
separates:

- mathematical equivalence: invariant under joint pair permutation;
- reference-model semantic equivalence: invariant when association,
  normalization, and membership are preserved;
- binary32 equivalence: bounded, not necessarily bitwise;
- bitwise equivalence: not generally invariant and not required by the
  R7-R12/M1-D/M1-E numerical lineage.

M1-F therefore needs reference-model semantic equivalence plus the inherited
binary32 numerical gates, not rank-byte identity by itself.

## Atomic pair and serialization contract

The v3 semantic record is:

`RoutingPair { expert_id: u16, routing_weight: IEEE-754 binary64 }`.

Canonical semantic evidence is exactly eight records sorted by expert ID,
each serialized as little-endian `u16` followed immediately by little-endian
binary64. The resulting 80 bytes are hashed with SHA-256. This ordering is an
evidence convention only; it does not choose the runtime reduction order.
Oracle and candidate rank-order byte streams are retained separately as
diagnostics.

## Per-expert routing-weight contract

The rule was frozen before retrospective evaluation. For every selected expert
ID, retained v2 antecedents derive an outward logit interval, a local sigmoid
probability interval, and a normalized selected-weight interval:

`weight_i = 2.5 * p_i / sum_selected(p)`.

The lower quotient uses `p_i_low` and all other highs; the upper uses
`p_i_high` and all other lows. A full binary32 ULP transport guard extends each
endpoint. A future mathematical PASS requires both:

1. the candidate ID-keyed weight lies in that propagated interval; and
2. absolute error is at most the inherited R10 `1e-5`.

H=2 additionally halves the oracle-centered propagated interval and caps
absolute error at `5e-6`. An implementation/contract mismatch found during
false-pass testing was repaired: the helper now enforces both conjuncts.

All eight oracle weights reproduce inside their ID-keyed intervals. This is
oracle self-consistency, not a claim that an unexecuted M1-F candidate passed.

## Accumulation policy and bound

The candidate contract retains the production rank-order serial binary32
reduction. Expert completion order must not implicitly change the declared
reduction order. Any different candidate order must be disclosed.

For already rounded atomic binary32 terms, the conservative per-element
difference between any two eight-term serial orders is:

`2 * gamma_7 * sum(abs(term_k)) + 14 * min_binary32_subnormal`,

where `gamma_7 = (7 * 2^-24) / (1 - 7 * 2^-24)`.

Qualification requires the observed difference to stay within this outward
bound, the bound itself to fit the R10 intermediate Tier-B `0.015625`, and the
complete-layer R10 contract to pass. Thus individually valid routing weights
cannot hide a failing layer sum.

The 100,000-case stress run covered cancellation, high dynamic range, signed
zero, subnormals, near-overflow finite values, and random permutations:

- under-bounds: `0`
- maximum actual/bound ratio: `0.2686807328000736`
- bitwise-equal cases: `64,601`

Directed permutation enumeration and 100-digit Decimal checks also passed.

## Frozen v3 contract

- Formula freeze commit: `e603a84ae78cbc9d3b8b2943d7d0ddf91e31d983`
- Final contract freeze commit: `9d133286c727db33fe716055dc9d48d77e8453ce`
- v3 candidate SHA-256: `befbf30f85e12b779e7d5c778f337a5f7d6019a15805e04805a24e4903ea3969`
- `post_observation_retuning = FORBIDDEN`
- Engineering headroom: `H=2`, retained as one additional modeled envelope
  for implementation/library drift, not as mathematical necessity.

Later implementation amendments only made public evidence tests CI-portable
and enforced the already-frozen inherited R10 cap. No coefficient, threshold,
serialization rule, classification rule, or fixture result changed.

## Fixture-1 retrospective

The zero-read artifact SHA-256 is
`dff0ed32f9a7c4c90954c4fe9778e48d855ba3bf0532cb7e055a49f723529d47`.

- exact selected membership: `{26, 78, 163, 166, 177, 186, 199, 233}`
- membership worst pair: `177 -> 98`
- membership mathematical factor: `1.2497550469932908`
- membership mathematical stability: `true`
- membership H=2: `false`
- eight ID-keyed oracle weight intervals: complete and self-consistent
- minimum prospective interval positivity factor: `92.3888548929209`
- candidate weight observation: `false`
- v2 rank diagnostic: unstable, worst adjacent pair `233 -> 177`,
  `S=0.22551544432236478`
- v3 semantic pre-admission status: `PRE_ADMISSION_MATHEMATICALLY_QUALIFIED`
- v3 engineering status: `NO_ENGINEERING_HEADROOM`
- M1-F candidate execution qualified: `false`

Fixture-1 disposition:
`SEMANTICALLY_VALID_BUT_INSUFFICIENT_HEADROOM`.

It remains valuable adversarial stress evidence. It is not promoted as the
representative M1-F fixture.

## v1 / v2 / v3 comparison

The machine-readable comparison SHA-256 is
`ed00586d24b6e90d7cabda52f6be56532cc3d2f52e9b6163b0237d8840520b6a`.

- v1 asks whether the rank-8/rank-9 boundary clears the historical independent
  score bound and S>=4. Fixture 1 remains unsuitable under v1.
- v2 asks whether exact selected membership and rank-ordered top-8 bytes are
  pairwise stable. Fixture 1 is set-stable, order-unstable, and lacks H=2.
- v3 asks whether exact membership and every expert-associated weight survive,
  with runtime accumulation effects separately qualified. It is a future
  contract candidate, not a rewrite of v1/v2.

## Representative-fixture target and planning

The target artifact SHA-256 is
`9c6f1c3fd4bd7e9245a771778e7461a8ac60238791bb51b8536582b79b7d7785`.
A future representative fixture must provide exact membership stability, all
ID-keyed weights qualified, mathematical routing PASS, H=2, 10 deterministic
candidate repeats, a complete-layer numerical PASS, retained rank diagnostics,
and a disclosed/qualified accumulation policy. A separate stress fixture is
mandatory.

Four zero-read options were characterized. The review recommendation is a
representative-plus-stress split, retaining fixture 1 for stress. The choice
between a precommitted correlated synthetic state and a separately reviewed
real layer-3 entry-state capture remains unapproved and must be made before any
new route outcome is observed.

Layers 0-2 are confirmed as leading dense blocks. A real layer-3 entry-state
capture would honestly execute embedding plus three complete dense transformer
layers and needs its own gate: `F017 M1-FPREP REAL LAYER-3 ENTRY-STATE CAPTURE`.
Its payload inventory and quantization qualifications must be derived before
authorization. It cannot be disguised as fixture generation. Characterization
SHA-256: `8274850fe4702cb972b0ecbbc39e1378e942674b808a1287c128dc3a2efb5a28`.

## False-pass and validation results

The synthetic suite rejects misassociated weights, duplicate/missing experts,
one expert replacement, one out-of-bound weight, a weight inside the propagated
interval but outside R10, non-finites and signed zero, hidden rank dependence,
an unqualified alternate accumulation policy, and an individually valid route
whose layer sum exceeds Tier-B. Same atomic pairs with a different rank obtain
the semantic outcome required by the source proof while retaining a rank
diagnostic mismatch.

Validation completed:

- 34 focused v3 tests: passed, including a no-private-artifact CI simulation;
- 100,000 accumulation stress cases: zero under-bounds;
- 558 full Python research/evidence tests: passed;
- `cargo check --workspace --all-targets`: passed;
- `cargo test --workspace --no-fail-fast`: passed; only pre-existing,
  explicitly environment-gated native tests were ignored locally;
- release repository check script: passed;
- deterministic evidence/source regeneration: byte-identical;
- 323 JSON files passed duplicate-key parsing;
- privacy/path scan, raw-v2 hash immutability, Spec Kit prerequisite check,
  generated-artifact checks, and `git diff --check`: passed.

Internal review verdict:
`GO FOR ROUTING-CONTRACT V3 ADVERSARIAL REVIEW`.

Adversarial packet:
`docs/architecture/reviews/f017-routing-contract-v3-adversarial-packet.md`,
SHA-256 `6eb5f11249e7986b5404f4303d6aee22a8e16fe7bbf7225fc1389705c5907150`.

Final-head Apple-native CI is required on the commit containing this report.
The exact run-to-SHA binding is recorded in the operator handoff after it is
green; CI performs no checkpoint access.

## Exact next action

Independent adversarial review of the frozen v3 contract and packet. Do not
perform new real access, Q6_K qualification, M1-F, or P1.
