# Frozen arithmetic fixtures and criteria

Declared before candidate output. All values below are self-created rational
constants, with fixture identity seeds 20260908 (primary) and 20260909 (transfer).
The seeds identify cases; these fixtures do not use a platform RNG. The JSON
fixture and this document are MIT licensed under the repository license.

Use f64 `abs(a-r) <= 1e-12 + 1e-10*abs(r)` for every finite scalar; report max
absolute error and RMSE. IDs, index order, shapes and reset identity are exact.
Reject unsupported dimensions, nonfinite input and nonfinite intermediates.
No numerical threshold may change after results. No f32 candidate is included.

- Route: logits `[-1,0,0.5,1]`, correction `[2,0,0,0]`, top-k 2, scale 2.5.
  Compare no-correction and corrected IDs; selected weights must derive from
  original sigmoid scores. Direct selector tie scores `[0.5,0.5,0.25,0.125]`,
  zero correction, top-k 2, ascending expert ID for equal scores. This tie rule
  is a declared toy convention, not qualification of an unobserved device sort.
- KDA: one sequence, one head, T=3, Dk=2, Dv=3. q rows
  `[[1,0.5],[0.25,-0.5],[0.75,1]]`, k rows
  `[[0.5,1],[-0.25,0.75],[1,-0.5]]`, v rows
  `[[0.25,0.5,-0.75],[1,-0.5,0.25],[-0.25,0.75,0.5]]`.
  a rows `[[0,0.25],[-0.5,0.5],[0.75,-0.25]]`, b logits `[0,0.5,-0.5]`,
  A_log=0, dt_bias `[0.125,-0.25]`, lower bound -5. Nonzero Dk-by-Dv state
  `[[0.125,0.25,-0.125],[-0.25,0.5,0.125]]`. Compare whole prefix vs one
  token increments, reset to empty state and two interleaved distinct sequences.
  Transfer sequence negates q and v while retaining other inputs.
- Convolution: concatenate q,k,v to width 7, kernel length 4, coefficient at
  channel c/tap t = `((c+2*t)%5-2)/8`. Empty suffix is three zero rows; compare
  prefix and incremental output and exact trailing raw-input suffix. SiLU follows
  depthwise convolution. No projection fusion or mixed masking is exercised.
- mHC: four streams of width 3, stream[h][d]=`(3*h+d-5)/8`;
  fn[i][j]=`((3*i+5*j)%11-5)/32` (24 by 12),
  base[i]=`(i%7-3)/16`, scales `[0.5,0.75,1.25]`. Twenty Sinkhorn iterations,
  RMS epsilon 1e-5 and mHC epsilon 1e-6. Expansion branch `[0.25,-0.5,0.75]`.
  Require nonidentity combination matrix and nontrivial expanded residual.
- Clamps: gate and up values `[-11,-10,-9,9,10,11]`, Cartesian pairs, plus
  NaN and positive/negative infinity rejection. Also extreme finite dot inputs
  `[1e308,1e308]` times `[1e308,-1e308]` must reject overflow before clamp.
- Dense/shared/routed composition: width 3, intermediate width 2, four experts.
  Input `[0.5,-0.25,0.75]`, residual `[0.125,-0.5,0.25]`;
  gate[e][i][j]=`((e+2*i+j)%7-3)/4`,
  up[e][i][j]=`((2*e+i+3*j)%9-4)/4`,
  down[e][j][i]=`((e+3*j+2*i)%7-3)/4`.
  Shared projections use e=4 by the same generators; route inputs as above.
  Assert every projection/activation/weighted aggregation/shared/residual edge.
- Sparse: seven keys, width 2: key[t][d]=`((2*t+3*d)%7-3)/4`;
  gate[t][d]=`((t+d)%5-2)/4`; pool size 2, top-k 4, APE
  `[[0.125,-0.25],[-0.125,0.25]]`; two query heads
  `[[0.5,1],[-0.25,0.75]]`, head weights `[0.75,0.25]`.
  Evaluate causal query positions 3,4,6 with all tokens valid. Tail at position
  4 and 6 must be included; output width 5, unused positions -1. Short T=3
  bypass is independent. Transfer changes first-token validity to false, shifts
  pool origin, and tests invalid current query. Explicit selector ties are
  ascending pool ID. Full MLA projections/attention and optimized pool caching
  are excluded; this is index pooling/scoring/visibility/selection only.

Packing/storage fixtures are separately defined in store-contract.md. Their
group-64 axes are not bridged into width-3 arithmetic composition.
