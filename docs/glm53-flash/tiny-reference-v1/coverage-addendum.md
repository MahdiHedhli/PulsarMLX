# Prospective coverage additions after static review

These inputs and checks are declared before their first execution. Original
arithmetic JSON, equations, seeds and numerical tolerances remain unchanged.
They close test-coverage gaps found in static review; no past result is
relabelled as having exercised them.

- Route selection margin checks compare the kth selected score to the first
  excluded score, for both corrected and uncorrected fixtures; require >1e-3.
  Add finite saturated logits `[1000,-1000,0]`, zero bias, top-k 2, scale 2.5:
  IDs `(0,2)`, raw scores `(1,0,0.5)`. Sigmoid scores admit closed `[0,1]`;
  normalization rejects a zero selected-score sum explicitly.
- Sparse exact tie: keys `[[1],[1],[1],[1]]`, gates four `[0]` rows, APE two
  `[0]` rows, one query `[1]`, head weight `[1]`, all valid, query position 3,
  top-k 2, pool size 2, tail disabled. Identical complete pool scores must select
  token IDs `(0,1)`. This is the declared tiny tie rule.
- The source masks invalid pools with -1e30. This tiny implementation must reject
  a visible score <=-1e30, whose ordering against that sentinel is unsupported.
  Test the same sparse fixture with head weight `[-1e31]`. Do not silently replace
  the source's pool count or masking rule with a different algorithm.
- Compare the already-frozen altered KDA sequence between implementations as
  well as prefix/incremental within each one. Independently assert exposed decay
  equals `exp(-5*sigmoid(exp(0)*(a+dt_bias)))` and beta equals `sigmoid(b)`.
- Feed each mHC expansion from its own implementation's collapse result. Inject
  NaN, +Inf and -Inf into streams, fn, base, scale, branch, post and combination
  matrix in independent rejection cases. Also inject these into convolution
  inputs/kernels and sparse keys/gates/query/head weights. Reject before use.
- Isolate clamp boundaries: hold up=1 while gate varies at/above +10 or
  below -10; hold gate=1 while up varies at/above +10 or at/below -10.
- Reject a non-MlpWeights expert entry with a bounded ValueError.

All finite comparisons retain atol 1e-12 and rtol 1e-10; IDs/shapes are exact.

## Independent review repair additions

Declared before the next execution, following the first Fable 5.1 code review:

- Both sparse APIs reject an interior validity hole in the seven-token fixture
  with mask `[true,true,false,true,true,true,true]`, and reject an all-false
  seven-token mask. These are live-selection cases, outside the separately
  qualified short-context bypass. Existing contiguous-valid outputs stay fixed.
- Mini-contract mutations exercise a nonreciprocal test/API edge, an unknown
  output port, a KDA indexed tensor with the wrong layer, and an indexed layer-45
  name. Each must reject with the relevant JSON path. The layer-45 name fails
  the frozen name allowlist before downstream role validation.
- Synthetic precision bits must be integers: float and boolean descriptors
  reject at validation/decode boundaries. Symlink components must reject as
  `PathSafetyError` through the descriptor-relative no-follow reader.

These additions do not alter fixture bytes, seeds, dimensions, numerical
thresholds or any previous result. Renaming metadata ceilings clarifies their
meaning without changing their values or the executed dimensions.
