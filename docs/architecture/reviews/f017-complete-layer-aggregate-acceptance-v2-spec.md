# F017 complete-layer aggregate acceptance v2

## Complete-layer surface

The protected production value is

`L = f32(f64(R) + (M + f64(S)))`,

where `R` is the canonical DPREFIX-EXACT-1 layer-3 entry residual, `M` is the
fixed-order binary64 routed aggregate, and `S` is the strict-f32 shared-expert
down output. The same strict-f32 FFN RMSNorm output feeds the routed and shared
experts. The shared branch is gate/up, strict-f32 SiLU multiplication, and down
projection; it has no extra output gate or scale. The implementation adds
`M + S`, adds `R` exactly once, and performs one final binary32 cast.

## R10 final-output acceptance domain

The immutable R10 v2 contract identifies the final-output limits as max
absolute `0.0625`, RMSE `0.03125`, and cosine minimum `0.999`. Its threshold
origin covers expert projections, nonlinear activation, weighted aggregation,
and the final residual before the production R10 output. V2 uses those values
without retuning or derivation. The routed-only v1 intermediate-surface theorem
and its cosine failure remain unchanged.

## Frozen uncertainty model

The proof concerns the already-frozen routing-weight ambiguity only. Its routed
perturbation interval is reused byte-for-byte. A future canonical shared output
must be exact-class, independently reproduced, persisted authority computed
from DPREFIX-EXACT-1; under this scoped proof it is a fixed point and
`delta_S=0`. A bounded shared artifact cannot claim that rule and must supply
componentwise intervals.

For each component, the theorem propagates the routed (and, if supplied,
shared) interval through the production-order binary64 additions and monotone
final binary32 cast. It subtracts the nominal final-f32 value with directed
outward rounding. If `B_k` is the resulting outward component radius, then
max absolute is `max(B_k)`, RMSE is `sqrt(sum(B_k^2)/6144)`, and
`epsilon=sqrt(sum(B_k^2))` bounds the perturbation L2 norm.

## Geometric cosine lemma

Let `a=L0`, `A=||a||2`, and let every admissible perturbation satisfy
`||delta||2 <= epsilon < A`. The ball of radius `epsilon` centered at `a`
subtends its maximum angle at the tangent point, where
`sin(theta)=epsilon/A`. Therefore

`cos(a,a+delta) >= sqrt(1-(epsilon/A)^2)`.

The implementation uses an outward lower bound on `A`, an outward upper bound
on `epsilon`, and downward rounding on the final square root. Zero/near-zero
nominal norm or `epsilon >= A_lower` fails closed. This formula is frozen before
the real shared output is observed; there is no production-value-selected
alternative.

The mathematical safety factor is the minimum of the downward-rounded ratios
`0.0625/B_inf`, `0.03125/B_rmse`, and
`(1-0.999)/(1-cosine_lower)`. Mathematical PASS requires all three bounds.
Engineering H=2 separately requires that minimum factor to be at least two.
