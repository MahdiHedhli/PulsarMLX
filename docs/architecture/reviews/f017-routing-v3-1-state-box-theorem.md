# F017 routing-contract v3.1 state-box propagation theorem

## Scope and separation

This contract freezes the mathematics used by analytical consumer
`F017-DPREFIX-ROUTE-AMBIGUITY-PROPAGATION-ANALYTICAL-1`. It is defined and
tested entirely with symbolic derivation and synthetic fixtures. It neither
loads nor contains the real DPREFIX exact state, ambiguity radii, router rows,
FFN norm values, correction-bias values, or private antecedent bytes.

The later evaluation is a separate event. This freeze performs zero checkpoint
reads, zero shard opens, and leaves the real-payload ledger at 139.

## Bound GLM-5.2 routing semantics

For layer-3 entry state `x`, FFN RMSNorm computes

`y_j = gamma_j x_j / sqrt(mean_k(x_k^2) + epsilon)`

with the committed binary32 epsilon promoted exactly to binary64:
`epsilon = 9.999999747378752e-6`. The router matrix has shape `[256,6144]`;
row `i` maps the normalized state to expert logit `z_i`. The reviewed GLM
linear router has no logit bias. Its selection-only correction bias is applied
after sigmoid:

`p_i = sigmoid(z_i)`, `score_i = p_i + correction_bias_i`.

Top-8 selection orders by decreasing score with lower expert ID winning an
exact tie. The selected set is load-bearing. Internal rank order is diagnostic.
For an already proven fixed set `T`, the ID-keyed routed weight is

`q_i = 2.5 p_i / max(sum_(k in T) p_k, 2^-14)`.

The correction bias is excluded from weight normalization. The shared expert
is outside router selection. The semantic object remains an atomic
`(expert_id, routing_weight)` pair.

## State box and arithmetic domain

The theorem accepts arbitrary finite, shape-aligned `x0`, `dx`, and `gamma`
with `dx_j >= 0`, defining `x_j in [x0_j-dx_j,x0_j+dx_j]`. Model binary32
inputs are exactly promoted into the proof's binary64 arithmetic. Every lower
endpoint is rounded with `nextafter(value,-infinity)` and every upper endpoint
with `nextafter(value,+infinity)`.

Finite subnormals are retained. Signed zeros are numerical zero for interval
ordering. NaNs, infinities, missing guards, negative guards, invalid shapes,
and intermediate overflow fail closed.

## RMSNorm enclosure

For each coordinate, construct outward `L_j` and `U_j`. Its squared interval
is `[0,max(L_j^2,U_j^2)]` when the coordinate interval crosses zero; otherwise
the lower endpoint is the smaller endpoint square. All computed endpoints are
rounded outward.

Outward reduction and division give bounds on `mean(x^2)`. Its lower endpoint
is clamped to the algebraic fact zero. Adding epsilon and taking outward square
root yields `[r_lower,r_upper]`; `r_lower <= 0` fails closed.

Standard signed interval division encloses `x_j/rms(x)`, including positive,
negative, and zero-crossing numerators. Interval multiplication by `gamma_j`
handles every gamma sign. This separates coordinate/non-radial uncertainty in
the numerator from common radial uncertainty in the denominator without
assuming that they are independent. Ordinary interval dependency can widen
the result but cannot make it unsound.

## Router and score enclosure

For each expert independently, interval products of exact promoted row
weights and normalized-coordinate intervals are outwardly reduced. Explicit
per-row reduction, import/materialization, and bias-representation guards are
then added symmetrically. A single global router bound cannot replace available
row-specific guards.

Sigmoid is monotone, so outward sigmoid evaluations at each logit endpoint
enclose `p_i`. The correction-bias interval is added in implementation order.
For selected `i` and challenger `j`,

`D_ij = [down(score_i.lower-score_j.upper),
         up(score_i.upper-score_j.lower)]`.

Membership is proven only when `D_ij.lower > 0`. A real top-8 set therefore
requires all 8×248 = 1,984 strict selected/unselected inequalities. None are
evaluated by this freeze.

## Safety factors

Let nominal positive margin be `m_ij = down(score0_i-score0_j)` and the
conservative ambiguity allowance be
`a_ij = up(max(0,m_ij-D_ij.lower))`. The safety factor is `m_ij/a_ij` rounded
down, infinite when a positive margin has zero allowance, and zero for a
non-positive nominal margin.

Mathematical classification requires both strict membership and factor at
least 1. Engineering `H=2` additionally requires factor at least 2. `H=2` is
headroom policy, not mathematical truth. Evaluation reports minimum factor,
worst ID pair, counts below 1 and 2, and the median finite factor.

## Selected-weight enclosure

Weights are evaluated only after the selected set is independently invariant.
For each selected expert ID, monotonicity of `p_i/(p_i+sum_others)` yields:

- lower: `2.5*p_i.lower / max(2^-14,p_i.lower+sum(other.upper))`;
- upper: `2.5*p_i.upper / max(2^-14,p_i.upper+sum(other.lower))`.

Both endpoints and reductions are rounded outward. This dependency-aware
formula is keyed by expert ID, rejects duplicate IDs, and does not compare
weights by rank position. Selected-set invariance, mathematical weight
qualification, and engineering weight qualification are separate outcomes.

## Proof status

The implementation and adversarial/property suite demonstrate the theorem on
synthetic boxes only. Sampling checks implementation containment and does not
replace the interval derivation. The actual DPREFIX box, 256-expert scores,
1,984 inequalities, and real selected-weight intervals remain deliberately
unevaluated until the next separately authorized loop.
