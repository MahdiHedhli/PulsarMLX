# Feature 018 Numerical Qualification Contract

**Version**: `f018-numerical-v1`

**Frozen**: 2026-08-09, before synthetic or real direct-kernel output was observed

## Reference hierarchy

1. The scalar Python IQ2_XXS decoder and scalar f32 matrix-vector operation are
   the architecture oracle.
2. The exact-bit qualified whole-matrix NumPy decoder plus synchronized MLX
   matvec is the optimized reference.
3. The direct packed Metal path is always the candidate under test and MUST NOT
   be called by either reference.

Checkpoint, tensor, packed bytes, activation, orientation, output length, and
reference hashes are frozen before a real candidate dispatch.

## Frozen matrix/projection envelope

- Elementwise gate: `abs(candidate - reference) <= 0.0005 + 0.0005 * abs(reference)`
- Cosine similarity: at least `0.999999`
- Candidate/reference norm ratio: `[0.9995, 1.0005]`
- All values finite
- Output length and ordering exact
- Reference-zero relative error is not reported as infinity; the elementwise
  absolute-plus-relative gate remains authoritative

## Frozen composed-boundary envelope

For complete expert, MoE, layer, residual, and logits boundaries:

- Elementwise gate: `abs(candidate - reference) <= 0.005 + 0.005 * abs(reference)`
- Cosine similarity: at least `0.999`
- Candidate/reference norm ratio: `[0.995, 1.005]`
- Routes, expert ordering, normalization rules, tensor identities, and shapes
  remain exact
- Greedy token identity is evaluated separately from the numerical envelope

These are the existing Feature 016 composed-boundary tolerances, retained
without widening.

## Determinism

- Synthetic validation: at least 100 identical executions.
- Real single-matrix correctness: at least 10 identical executions before the
  3-warmup/30-sample performance population.
- Deeper costly rungs: at least 10 identical executions when practical; any
  smaller population must be predeclared and cannot support a determinism claim.
- Exact output hashes, signed-zero counts, first mismatch, mismatch count,
  maximum absolute error, mean absolute error, RMSE, maximum meaningful relative
  error, cosine similarity, and norm ratio are retained.

## Classifications

### `golden_identical`

- Candidate f32 output bits equal the frozen reference bits at every admitted
  boundary.
- Signed-zero positions match.
- Routes, top-k order, greedy tokens, shapes, and identities are exact.
- Repeated output hashes are identical.

### `numerically_qualified_greedy_identical`

- At least one candidate output bit differs from the reference.
- All frozen numerical, finite, identity, route, resource, fallback, and
  determinism gates pass.
- Candidate greedy argmax equals the frozen greedy argmax at every evaluated
  position.

### `numerically_qualified_greedy_divergent`

- All frozen numerical, finite, identity, route, resource, fallback, and
  determinism gates pass.
- Candidate greedy argmax differs at one or more positions.
- Validation continues teacher-forced using the frozen reference token at every
  later position. The first divergence and all later position metrics remain in
  evidence.
- This class cannot admit a greedy-token, P1, P2, or golden continuation claim.

### `numerically_failed`

Any of the following is sufficient:

- tolerance, cosine, norm-ratio, finite-value, route, ordering, shape, identity,
  or deterministic-repeat gate fails;
- hidden CPU fallback or complete f32 weight materialization occurs;
- malformed input reaches dispatch instead of failing closed;
- ownership, command completion, or resource-safety gate fails.

## Teacher-forced continuation

After candidate argmax disagreement, the next input token remains the frozen
reference token. Candidate free-running output MUST NOT replace it. Validation
continues for every committed position and records both candidate argmax and
the teacher-forced token. This rule cannot be disabled to hide later behavior.

## Tolerance changes

This contract is immutable for Feature 018 v1. A future change requires a new
version, preserved failing pre-change evidence, technical justification before
rerun, and a complete rerun of every affected boundary. No in-place widening is
permitted.
