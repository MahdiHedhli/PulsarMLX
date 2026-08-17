# F017 Weighted-MoE Aggregate Perturbation Theorem v1

## Frozen scope

This contract answers only whether uncertainty in an already invariant,
ID-keyed top-8 routing-weight set can be proved harmless at the R10
`routed_aggregate` intermediate surface. It does not weaken the frozen
coefficient rule. The production coefficient result remains `0 / 8` and the
route disposition remains `ROUTE NOT PROVEN INVARIANT` until a separate loop
verifies the required expert-output inputs and then evaluates this theorem.

No real F017 expert-output or aggregate value was loaded while selecting the
theorem, reference rule, or budget.

## Bound downstream semantics

For coordinate `k`, the committed Rust candidate and independent Python oracle
both compute

`M[k] = fsum_i(q_i * f64(e_i[k]))`,

where `q_i` is binary64, `e_i[k]` is the routed expert's binary32 down output
promoted to binary64, and the eight products use a fixed
Python-`math.fsum`-equivalent reduction. The expert scale `2.5` is already in
`q_i`. The shared expert is added only after this surface to form
`combined_moe`; the residual is added after that and cast to binary32. There is
no intervening normalization.

The protected surface is therefore the 6,144-coordinate binary64
`routed_aggregate`, not `combined_moe` or the final residual output.

## Pre-existing acceptance budget

Production R10 Tier-B v2 explicitly states that its power-of-two intermediate
envelope covers weighted aggregation. The theorem consequently adopts the
unchanged intermediate limits directly:

- maximum absolute error `0.015625`;
- RMSE `0.0078125`;
- minimum cosine similarity `0.9999`.

The larger final-output envelope is rejected because shared-expert and residual
addition intervene. The `1e-5` routing coefficient limit remains a separate,
failed contract and is not mapped into a vector-output tolerance.

## Directed-outward theorem

Let `Q_i=[q_i^-,q_i^+]`, `E_i,k=[e_i,k^-,e_i,k^+]`, and let `q0_i`, `e0_i,k`
be contained nominal values. Weight-only evaluation sets `E_i,k` to the point
`e0_i,k`; joint evaluation supplies independently justified output intervals.

Two enclosures are computed for each coordinate.

The direct enclosure is

`D_k = sum_i(Q_i * E_i,k) - sum_i(q0_i * e0_i,k)`.

The centered identity uses a deterministic reference `c_k`, defined before any
real evaluation as the midpoint of the hull of the eight `E_i,k` intervals:

`delta M_k = sum_i((q_i-q0_i)(e_i,k-c_k))`

`            + sum_i(q0_i(e_i,k-e0_i,k))`

`            + c_k sum_i(q_i-q0_i)`.

The last term uses the already-derived common-denominator joint weight-sum
interval, never a sum of independently extremized `Q_i` endpoints. The final
coordinate enclosure is the intersection of the direct and centered
enclosures. Intersection is sound because each input enclosure independently
contains the same exact expression; an empty intersection fails closed.

Every lower endpoint is rounded toward negative infinity and every upper
endpoint toward positive infinity with binary64 `nextafter`. Full signed
interval multiplication handles mixed-sign and cancellation-heavy outputs.

From coordinate radii `B_k`, the theorem derives:

- `B_inf = max_k B_k`;
- `B_rmse = sqrt(sum_k B_k^2 / 6144)`;
- a directed-outward lower bound for `cosine(M0, M)` from the componentwise
  `M0 + delta M` box.

Cosine qualification fails closed if the nominal norm is zero or the aggregate
box admits a zero norm.

## Qualification and safety factor

Mathematical qualification requires all three R10 intermediate limits. The
three factors are the accepted max-absolute budget divided by `B_inf`, the
accepted RMSE budget divided by `B_rmse`, and the allowed cosine loss
`1-0.9999` divided by the proved cosine loss. Division rounds downward. The
aggregate factor is their minimum; zero perturbation has infinite factor.

Mathematical PASS requires factor at least `1`. Engineering H=2 requires the
same mathematical PASS and factor at least `2`; engineering headroom does not
redefine mathematical truth.

## Required future evidence

Already public (A): selected IDs, nominal and interval weights, their joint
sum enclosure, the R10 budgets, and the aggregation semantics.

Not currently available under the reviewed retained package surface (D): the
eight real, ID-keyed, canonical binary32 routed-expert down-output vectors.
Their presence must be resolved in a separate checkpoint-free-first loop. Once
verified, the nominal aggregate, component hulls, and norms are mechanically
derivable (C). Componentwise expert-output uncertainty intervals are optional
for a weight-only proof and separately required (D) for a joint proof.

No private binary path or bytes are part of this public freeze.
