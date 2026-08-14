# F017 Route-Stability v2 Recovery-Preparation Internal Review

## Scope

This review covers the final route-stability v2 contract and the checkpoint-free
antecedent-recovery package only. It does not authorize the future 12-payload
recovery, consume a route attempt, reclassify historical v1 evidence, qualify
Q6_K, or authorize M1-F.

## Findings

1. Bias bytes remain identical between oracle and candidate, so bias-operand
   perturbation is exactly zero. The final contract separately and explicitly
   accounts for rounding in each `fl(sigmoid(logit) + bias)` operation with a
   four-operation outward pair guard.
2. Exact top-8 canonical bytes are normative. The theorem requires all 1,984
   selected/unselected membership comparisons and all seven adjacent selected
   comparisons. Adjacent stability plus transitivity preserves the complete
   selected order; an exact tie fails the strict proof and is resolved only by
   the frozen lower-ID tie rule.
3. No unrelated v2 term changed. Mathematical stability remains the strict
   pairwise condition. `H = 2` remains an engineering classification reserving
   one additional complete modeled envelope; it is not mathematically required
   for swap prevention.
4. One hundred thousand randomized cases, all directed adversarial cases, and
   100-digit Decimal spot checks produced zero under-bounds. The maximum sampled
   actual-to-bound ratio was `0.9563522005807091`.
5. The interval-local sigmoid derivative implementation passes the requested
   zero-crossing, positive, negative, saturated, tiny-zero, and one-ULP endpoint
   cases with outward interval construction.
6. The primary structured implementation and separately transcribed scalar
   implementation share only binary64 primitives and input mappings. They share
   neither a contract parser nor generated expected-output constants, and agree
   exactly on the qualification surface.
7. The random-normal conclusion is labeled
   `SEMI_ANALYTIC_EFFECTIVE_CEILING`, explicitly not a support theorem. The
   eight-seed ladder remains paused and unexecuted.
8. The metadata-only expert-166 gate/up/down derivation matches the generic
   validator at exact offsets and lengths. No tensor payload was read and no
   route binding was created.
9. The retention manifest requires direct canonical f64 pre-sigmoid logits,
   public analytical values, all 1,984 membership bounds, all seven ordered
   bounds, and immutable private antecedents with public-safe hash/shape/dtype/
   serialization/provenance metadata.
10. The recovery allowlist is exactly the accepted 12 M1-F0 tensors. Every
    packed/decoded identity and every accepted input/stage/route hash is frozen.
11. Recovery semantics forbid new route discovery, route selection, historical
    reclassification, attempt consumption, expert access, and MLX candidate
    dispatch. A recomputed route is only an identity gate; mismatch fails closed.
12. The package leaves the ledger at 45 during preparation and permits one
    future successful recovery amendment of exactly 12 payloads to 57.
13. The config is bound to tooling commit
    `6b56dc88f89b92ebaeb525a35e48b3c2c1bc8fec` and tree
    `61eda4e19c57b0ddeea92a73468cbb5edff6019e`. Authorization is null and status
    is `NOT_AUTHORIZED_NOT_EXECUTED`.
14. Config-only preflight returns
    `READY_TO_EXECUTE_V2_ANTECEDENT_RECOVERY` with zero checkpoint reads, zero
    oracle creation, zero MLX contexts, zero expert access, and no consumption.
15. The synthetic full recovery exercises 12 synthetic payloads, eight private
    antecedents, 1,984 membership bounds, seven adjacent bounds, immutable
    before/after hashes, and separate mathematical/engineering classifications.
16. The result schema preserves `historical_v1_status_unchanged = true` and may
    only add retrospective v2 annotations.

## Verdict

`GO FOR V2 RECOVERY-PACKAGE ADVERSARIAL REVIEW`
