# F017 Routing-Contract v3 Adversarial Review Packet

## Requested verdict

Return exactly one:

- `GO FOR ROUTING-CONTRACT V3`
- `GO WITH REQUIRED FIXES`
- `NO-GO`

A GO permits consideration of a separately reviewed next phase. It does not authorize checkpoint access, Q6_K qualification, M1-F, or P1.

## Frozen review surface

| Object | Identity |
|---|---|
| Starting head | `b3b0ca39961fbe9d770b58fd23c6e06b21265f8d` |
| Formula freeze commit | `e603a84ae78cbc9d3b8b2943d7d0ddf91e31d983` |
| Contract freeze commit | `9d133286c727db33fe716055dc9d48d77e8453ce` |
| v3 candidate contract | `befbf30f85e12b779e7d5c778f337a5f7d6019a15805e04805a24e4903ea3969` |
| Final v2 contract | `36adbdcffeeb361638ec80258b912711b17a671276d68cf0129826e1ae042ac7` |
| Raw v2 recovery (immutable) | `f9422287cb98322d1412a6dd2397bb0f4a0d6538778aa587dddff7c5154acf2a` |
| Accepted M1-F0 route | `980b6a78ae04b816e1f9e563790f5a2d123723292dd0432a0218972d0f80593e` |
| Private antecedent manifest | `1007112a0642919321d0081e79bba12fe3809c456e79a22b9623d19689b78112` |
| Source trace | `356ffad4e72d6950605a0c0afb7cef3b549000a7de15c8b61f8216370fad3832` |
| Equivalence taxonomy | `5e2962f724a0898ad1e11aec37173228aa6aadac6943a6937c70e9dca61024b4` |
| Fixture-1 v3 retrospective | `dff0ed32f9a7c4c90954c4fe9778e48d855ba3bf0532cb7e055a49f723529d47` |
| v1/v2/v3 comparison | `ed00586d24b6e90d7cabda52f6be56532cc3d2f52e9b6163b0237d8840520b6a` |
| Representative target | `9c6f1c3fd4bd7e9245a771778e7461a8ac60238791bb51b8536582b79b7d7785` |
| Dense-prefix characterization | `8274850fe4702cb972b0ecbbc39e1378e942674b808a1287c128dc3a2efb5a28` |

All new work is checkpoint-free. The cumulative real-payload ledger remains 57.

## Central claim to attack

The mathematical/reference-model routing object is eight unique atomic `(expert_id, routing_weight)` records. A joint permutation preserves the exact weighted expert sum. Current rank order remains numerically observable because the production kernels reduce selected slots serially in rank order, but this is a runtime numerical policy rather than a rank-indexed model coefficient.

The v3 candidate therefore:

- requires exact membership;
- binds every routing weight to its expert ID;
- rejects duplicate, missing, extra, misassociated, zero, or non-finite records;
- serializes semantic evidence in expert-ID order without prescribing runtime reduction order;
- retains oracle/candidate rank order as diagnostics;
- separately bounds reduction-order effects and retains the complete-layer Tier-B gate;
- retains H=2 as engineering headroom, not mathematical necessity.

## Retrospective falsifier

Fixture 1 was evaluated only after the formula freeze. Its selected-set membership is mathematically stable with worst pair `177 -> 98`, `S=1.2497550469932908`, but fails H=2. Its v2 rank-order diagnostic remains unstable. The eight oracle weights instantiate ID-keyed prospective intervals; no candidate weight, expert output, complete layer, or M1-F execution was observed.

Disposition: `SEMANTICALLY_VALID_BUT_INSUFFICIENT_HEADROOM`.

## Adversarial questions

1. Is rank actually non-semantic along every production and reference path?
2. Are `(expert_id, routing_weight)` pairs atomic everywhere, including transport and storage resolution?
3. Can permutation-invariant qualification false-pass independently permuted or duplicated weights?
4. Is ID-sorted semantic serialization neutral with respect to runtime accumulation policy?
5. Is retaining the existing rank-order runtime reference-equivalent at the model-semantic level?
6. Is `2*gamma_7*sum(abs(term))+14*min_subnormal` a conservative difference bound for two eight-term serial binary32 reductions, including subnormals and cancellation?
7. Are local sigmoid and normalized selected-weight intervals rigorous and keyed by expert ID?
8. Did fixture 1 influence any coefficient, tolerance, headroom, serialization, or PASS rule?
9. Can the retrospective result be reproduced from retained antecedents with zero real access?
10. Are historical v1/v2 evidence and conclusions untouched?
11. Is the future representative-fixture target meaningful rather than outcome-conditioned?
12. Is the layer-3 dense-prefix fallback honestly characterized as embedding plus three real dense layers?
13. Does v3 relax only rank equality, while preserving membership, weight, accumulation, and full-layer numerical requirements?
14. Is any new checkpoint access genuinely needed before the next separately reviewed phase?

Also try the committed false-pass cases: same IDs/wrong weights, duplicate or missing pairs, rank serialization masking runtime order, individually valid weights with a failed layer sum, asynchronous completion changing reduction, non-finite weights, and undisclosed candidate accumulation policy.

## Phase boundary

Review only. Do not execute a checkpoint, frozen ladder, Q6_K gate, M1-F, P1/P2/golden-eight, or Feature 018.
