# Feature 018 Numerical Qualification Contract

**Version**: `f018-numerical-v1`

**Frozen**: 2026-08-09, before synthetic or real direct-kernel output was observed

## Reference hierarchy

1. The **bit-exact oracle** is the scalar IQ2_XXS decode followed by f32
   multiplication and same-order sequential-column f32 accumulation. The Rust
   and Python/NumPy oracle implementations MUST visit logical columns in the
   same increasing order and compare outputs through exact `f32` bit patterns,
   including signed zero.
2. The exact-bit qualified whole-matrix NumPy decoder plus synchronized MLX
   tiled matmul is the optimized performance reference. MLX matmul is a
   **Tier-B numerical comparator**, not the bit-exact oracle, because its tiled
   reduction order is an implementation detail.
3. The direct packed Metal path is always the candidate under test and MUST NOT
   be called by either reference.

Checkpoint, tensor, packed bytes, activation, orientation, output length, and
reference hashes are frozen before a real candidate dispatch.

## Qualification implementations

- The current one-thread-per-row Metal kernel is the deterministic
  qualification scaffold. It decodes packed IQ2_XXS values and accumulates in
  increasing sequential-column order.
- Qualification/scaffold builds compile with fast math disabled and an
  explicitly recorded Metal language version. Compiler defaults are not part
  of the contract.
- If the strict sequential scaffold matches the same-order oracle exactly, it
  is `golden_identical` at that bounded output. If any bit differs, it is
  classified under the frozen Tier-B envelope; thresholds MUST NOT change in
  response to the observation.
- A future SIMD-group or threadgroup performance kernel may reorder reduction.
  It is a separate implementation and normally qualifies under Tier B, even
  when the deterministic scaffold remains bit exact. It MUST NOT replace or
  delete the scaffold.

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

- Candidate f32 output bits equal the same-order scalar/NumPy oracle bits at
  every admitted boundary.
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

## Validation dispatch semantics

- An intentional out-of-scope format or role is an **explicit reference
  dispatch** selected before candidate invocation. It is not a fallback.
- A selected direct operation that cannot execute is a **direct error**. In
  validation mode it fails the boundary immediately; reference recovery cannot
  turn that boundary into a pass.
- A production policy may permit an explicit, observable fallback, but that
  execution is ineligible for `golden_identical` and every qualified Feature
  018 validation claim.
