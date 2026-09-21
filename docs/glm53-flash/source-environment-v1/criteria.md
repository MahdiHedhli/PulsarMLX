# Prospective FP32 criteria and fixture limits

These criteria precede all selector/Conv1d boundary outputs. CPU and Metal
addition-only admission is separate. The predecessor's binary64 thresholds,
fixtures and records are unchanged. The new cases are deterministic rational
values identified by cases.json (seed label 20260908; no ambient RNG required).

Let u=2^-24 and gamma(n)=n*u/(1-n*u). The exercised depthwise kernel has four
taps (the wrapper cap is seven), dyadic inputs |x|<=2 and coefficients |w|<=1.
Dyadic conversion to FP32 is exact. Even the seven-tap ceiling has sum|x*w|<=14;
gamma(14)*14<1.2e-5 bounds ordinary rounded multiply/add accumulation. Raw
convolution uses atol=2e-5 and rtol=2e-6, with the relative term allowing benign
reassociation. Exact shape, channel isolation and saved input suffix are separate
checks; tolerance cannot accept a reversed tap or swapped axis.

SiLU has global derivative magnitude below 1.1. Propagating that raw error and
reserving 16u per sigmoid evaluation plus multiplication on |raw|<=14 gives a
conservative fixture budget below 4e-5. SiLU uses atol=4e-5, rtol=4e-6. The
16u transcendental allowance is a **prospective engineering error budget**, not
a proven library ULP guarantee; no such guarantee was found in the pinned
source. Failure cannot be repaired by claiming that assumption after results.
Empirical passes qualify only the exact fixtures, dtype, wheel and device.

Router fixtures have bounded logits, exact dyadic bias/scaling and at most
eight selected terms. Source sigmoid has the same prospective 16u allowance;
the positive selected-score sum is checked to exceed 0.1 in separated numeric
cases. Propagating score errors through positive normalization and scale<=2.5
reserves atol=4e-5, rtol=4e-6 for returned weights. The configured-only case uses
its artifact-declared scale; if it exceeds that bound its numeric case is left
unqualified until a prospective bound is banked, never silently shrunk.
Separated score margins must exceed 1e-4; ties are separately exact constructions.

For routed aggregation, the f64 fictional expert outputs remain an independent
control. Each output component permits
4e-5*sum(abs(expert_output)) + 64*u*max(1,sum(abs(weighted products))). This
propagates the declared router-weight absolute budget plus FP32 conversion and
short accumulation. The bound is a predeclared formula, not a fit to measured
errors. Shared/residual/full-layer execution is outside this new changed edge.

Seven distinct mutation controls are predeclared: source hash, missing mx global,
wrong module origin, dropped bias, wrong weight/ID pairing, reversed taps and
swapped axes. A detected mutation must fail the corresponding identity or
semantic check; actual survivors and evaluations are recorded. Normal → mutated
→ restored controls use the real source/operator entry. No upstream snapshot is
edited. Nonfinite inputs and finite-logit normalization underflow are additional
rejection probes, not fabricated arithmetic successes or extra mutant counts.

The grouped zero-mask diagnostic records source behavior and the possible
exclusion-intent discrepancy. It cannot count as proof that suppressed groups
are never selected. Exact tie cases retain raw returned order and test allowed
membership with paired weights; repeated order is an observation only.

The main convolution fixture is [2,7,3], kernel [3,4,1], state [2,3,3]; the
impulse fixture is [1,7,3]. An independently interleaved sequence and chunks
[2,1,4] expose suffix ownership. The predecessor bridge is [1,3,7] with seven
depthwise width-4 kernels. All stay below the phase dimensions/elements limits.
The configured selector exception allocates only <=512 scalar scores.
