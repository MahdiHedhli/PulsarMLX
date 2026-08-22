# F017 native bounded-P1 numerical acceptance (D0 v1)

Status: frozen before retained representative qualification. No P1 and no
retained qualification result exists at this boundary.

## Surface

The native production surface is deliberately mixed: every quantized matvec
runs through pinned MLX 0.31.2 / MLX C 0.6.0 on the Apple M1 Ultra GPU; the
serial-f32 normalization, nonlinear, routing, aggregation, and residual
operations run in ordered Rust host code. Every captured MLX stage is
synchronized and read back before the next authority-bearing capture. A helper
may not silently open a GPU dispatch or substitute a CPU/reference matvec.

The canonical 34-stage vocabulary is byte-bound to the accepted historical
Apple serial-f32 stage manifest. D3.5 must emit those IDs and serialization or
an independently reviewed immutable mapping. It may not compare look-alike
names.

## Correctness hierarchy

The independent Python/NumPy fixture is the non-native correctness oracle for
projection, router, complete expert, top-8 plus shared, MLA/dense, complete
layer, and final norm/logits/top-k boundary families. Accepted historical R9,
expert Tier-B, and R10 contracts supply numerical-product contracts only at
their declared roles. Retained proof/reference artifacts are expected
authorities, never native output and never a threshold-selection corpus.

The routed f64 aggregate, f64 FFN, and proof/reference-derived S2 are
intentionally distinct from production serial-f32. Their distance metrics are
still recorded under the frozen intermediate/final product limits, but a close
vector cannot be relabeled byte-equivalent or production-identical.

## Frozen metrics

All comparisons first require exact shape, dtype, endianness, finite values,
and any structural predicate. Numeric stages then require the conjunction of
max absolute error, RMSE, cosine minimum, and a per-coordinate cap. Relative
error is disabled because near-zero coordinates make it unstable; it is not a
substitute for the required metrics. Signed zero is exact at byte boundaries
and whenever both numerically compared values are zero.

The representative intermediate contract is max-absolute 0.015625, RMSE
0.0078125, and cosine at least 0.9999. The final representative layer contract
is max-absolute 0.0625, RMSE 0.03125, and cosine at least 0.999. These are not
new fits: they are the unchanged accepted R10 product-level contracts frozen
before the target retained results. Routing additionally requires exact
membership, order, and lower-ID tie behavior before a 1e-5 routing-weight cap.
Quantized matvec boundaries that expose operands also require the unchanged
accepted operand-conditioned component bound.

No new empirical tolerance is derived in D0 v1. Any future empirical D0
revision must predeclare a synthetic or pinned public-safe fixture corpus,
repeat count, metrics, and derivation before observing results. Representative
retained bytes are forbidden from threshold selection.

## Epistemic repair rule

D3.5 may falsify this contract but may never tune it. If a failure proves a
tolerance derivation invalid, the triggering D3.5 output is quarantined from
threshold selection. Repair requires an append-only D0 revision, a fresh
synthetic/pinned-fixture corpus, a predeclared derivation, and another D0 Fable
review. Editing v1 or choosing a value from failed D3.5 output is prohibited.

## Determinism and portability

Correctness and determinism are separate. On the exact pinned M1 Ultra,
executable, MLX/Metal stack, and environment, ten same-process and ten fresh
process captures must be byte-identical stage by stage. Numeric tolerance may
not conceal a repeat failure; the earliest divergent stage is banked. This is
implementation-specific reproducibility, not a cross-device byte claim.
Cross-device portability remains unclaimed.

## Scope

A successful D3.5 qualifies only representative layer-3 S0-to-S2. It does not
qualify the approximately 93-layer full forward or the final token decision.
The remainder is admitted later only through F016 structural lineage plus
generalized, bound per-stage semantics and the separately human-authorized P1
receipt. Synthetic fixtures do not prove all real-checkpoint distribution
tails.
