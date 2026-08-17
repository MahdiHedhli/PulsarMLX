# F017 selected-routing-weight acceptance contract v1

## Scope and freeze order

This contract qualifies an outward routing-contract v3.1 interval for each
selected expert ID. It was defined using symbolic and synthetic inputs only,
before applying it to any of the eight F017 production intervals. It neither
recomputes the production route nor changes the existing selected-set proof.

The prerequisite is an independently proven invariant set of eight distinct
expert IDs. The load-bearing object remains the atomic pair
`(expert_id, routing_weight)`; rank position is not a coefficient key.

## Model semantics

For the fixed selected set `T`, the committed GLM-5.2 rule is

`q_i = 2.5 * p_i / max(sum_{k in T}(p_k), 2^-14)`.

Here `p_i` is the pre-correction-bias sigmoid probability. Correction bias
selects the set but is excluded from weight normalization. No later
normalization changes `q_i`. The weights linearly scale their corresponding
expert outputs before the routed sum, shared-expert addition, and residual.

## Protected property and budget lineage

The interval must protect the inherited R10 coefficient-perturbation rule,
not merely contain one nominal value. Production R10 froze
`routing_weight_max_absolute_error = 1e-5` before its candidate execution.
Routing v3 subsequently froze the same mathematical cap and an H=2 cap of
`5e-6`.

For nominal exact-state weight `q0_i` and outward enclosure `[L_i,U_i]`, define

`rho_i = up(max(q0_i - L_i, U_i - q0_i))`.

An ID-keyed interval is mathematically qualified exactly when it is finite,
strictly positive, contains `q0_i`, and `rho_i <= 1e-5`. The selected-weight
surface is `WEIGHT_MATHEMATICALLY_QUALIFIED` only when all eight IDs pass and
the shared-denominator normalization check is valid.

Optional `WEIGHT_ENGINEERING_H2` additionally requires every
`rho_i <= 5e-6`. H=2 is headroom, not mathematical truth. Relative radius is
reported only as a diagnostic; this contract introduces no fitted relative
threshold or near-zero floor.

## Coupled denominator and conservation

Independent endpoint combinations for the eight `q_i` values generally
cannot occur together. Let the selected probability sum satisfy
`P in [P_low,P_high]`. The joint selected-weight sum is propagated from the
single shared quantity:

`Q(P) = 2.5 * P / max(P,2^-14)`.

When the floor is inactive throughout, the mathematical sum is exactly `2.5`.
When it is active, or when the box crosses the floor, the monotone piecewise
formula is propagated outward. The resulting joint interval must contain the
nominal selected-weight sum. The implementation must not sum eight
independently extremized weight intervals as a substitute for this dependency.

No additional joint-width threshold is introduced. No pre-existing bound on
the selected expert output norms maps such a threshold to R10 without loading
new expert data. A later M1-F candidate must therefore still pass the frozen
accumulation-order bound and complete-layer numerical contract. Weight
qualification cannot substitute for that downstream gate.

## Failure meaning

A mathematical failure means the state ambiguity permits at least one
ID-keyed coefficient to leave the pre-existing R10 coefficient budget, or the
enclosure is not a valid application of the shared-denominator theorem. It
does not invalidate selected-set invariance. An engineering-only failure means
the mathematical budget is met without the optional factor-of-two reserve.

Non-finite inputs, duplicate or missing expert IDs, invalid probability
domains, non-positive weight enclosures, absent selected-set proof, nominal
containment failure, derivation drift, and normalization inconsistency all fail
closed.

## Anti-fitting and isolation

The implementation and tests use only synthetic/adversarial fixtures. They do
not load or summarize the real F017 selected-weight intervals. Applying this
frozen rule to those already-banked intervals requires a separate loop.

This freeze performs zero checkpoint reads, opens zero shards, dispatches no
candidate or model, and leaves the real-payload ledger at 139.
