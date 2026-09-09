# Finite default recurrent dispatch and outer-only evaluation

This research component exercises the pinned default recurrent dispatcher on
synthetic FP32 inputs. It reuses the accepted scalar recurrence and actual
ArraysCache, and adds the original custom Metal kernel factory, all four
initializers and the complete kernel caller. It is a component qualification,
not full KDA, a model run, a quantized artifact check or a performance result.

The selected source is `mlx_vlm/models/gated_delta.py` from
`Blaizzy/mlx-vlm@8d79dbcf82a7885ddfc56fb4a55440fa9c5dfb90`, and caller
statements289–303 from `PipeNetwork/glm53-flash-mlx@a61a7c7d2fbdf3d218a9909365a24bd794f3a247`.
The vendored texts, exact byte spans, complete AST nodes and both licenses are
retained. Repinning the capsule hash cannot admit changed original nodes.
No entire upstream module is imported. Extraction globals, function/API counter
wrappers and the synthetic caller context are explicitly research components.

Seven declared input cases include one unchanged small-Dk eager/lazy bridge,
a Dk32 sparse exact-rational anchor, Dk32/64 spread values with scalar/vector
and ordinary/safe gates, grouped heads, and one mixed-mask plus one all-false
case. Kernel cases have Dv4/8, B1–2,T1–4,Hk1–2,Hv1–4; the admission ceiling is
T7. Every input case, including the bridge and masks, counts toward the
eight-case maximum. Partitions, interleaving, next-step cache use and mutation
controls reuse declared inputs. No unsafe GPU shape/address mutation is used.

The original `use_kernel=True` default and selector remain unchanged. Each
child sets and records the actual MLX default device. CPU selects ops; Metal
selects the custom kernel for Dk32/64. The bridge selects ops on both. Actual
entry wrappers and submitted API calls identify the selected path. Factory
creation alone is not kernel execution. Original grid `(32,Dv,B*Hv)` and
threadgroup `(32,4,1)` are checked against bound source ASTs. Metadata guards
prove input/output sizes, head mapping bounds, lane coverage and launch tiling.
Scientific input values are validated before tensor construction; lazy source
gate/beta values are not host-read inside the recurrence.

The normal path has no per-step evaluation, tracing or host materialization.
It evaluates returned output/final state once per invocation and records
explicit before/after cache observation boundaries. Real ArraysCache holds
recurrent state in slot1 and executes the original advance(S), while slot0
retains identity and values. The caller remains synthetic vector-gate and
unmasked; projections, normalization and convolution integration are excluded.

Masked output contracts differ in the fixed source. Ops computes output before
restoring old state for a false mask. The custom kernel writes zero output and
retains old state. Both have independent path-specific expectations; masked
output parity is not claimed or manufactured. Unmasked output/state comparisons
use the shared binary64 scalar recurrence. The exact-rational anchor gives
state19/64 and output19/128 in the single active lane.

The fixed acceptance ceiling is atol2e-5 plus rtol3e-6 for output/state.
Pre-observation working FP32 propagation includes gate2e-6 and beta1e-6 absolute
allowances plus accumulation. Four times the largest propagated budgets fits
the ceiling. This is a coarse finite criterion, not a proven transcendental
bound or a few-ULP guarantee. The admitted MLX API documents the omitted
compile-options default as safe math; the effective compiler/driver setting is
NOT_OBSERVED. No compiler option is changed and tolerances are not fitted to
candidate outputs. Frozen-oracle recomputation is self-consistency; independence
rests on the separate scalar recurrence and exact-rational anchor.

Eight named controls cover decay, residual state, grouped mapping, a dropped
cache1 write, advance count, masked-output expectation, forced fallback and an
illicit inner evaluation barrier. The forced-fallback control is Metal-only:
CPU already chooses ops and makes no claim to detect that mutation. All
applicable controls require fresh normal/mutant/restored function/kernel
objects, identical declared inputs, the precise expected assertion and actual
entry/evaluation deltas. Semantic kernel mutations preserve valid memory bounds.
The wrong-mask control tests expectation discrimination, not a changed kernel.

Python source entries, factory calls, submitted kernel APIs and explicit
barriers are counted separately from process starts. Physical compiled traces,
GPU instruction counts, cache traffic and performance remain NOT_MEASURABLE.
Fresh source/run roots and processes verify reproduction within this finite
generation. Source-free confinement/custom-kernel capability receipts, original
failures and raw captures belong to the evidence, with scope unchanged when a
component is unavailable. The `dispatch` successor operation uses the existing
fenced doctor, capture, archive and failure-classification path; only explicit
operation/input/layout registration is added.
