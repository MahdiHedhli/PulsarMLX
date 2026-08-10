# Feature 018 IQ3_XXS-Down Numerical Qualification Contract

**Version**: `f018-iq3-down-v1`

**Frozen**: 2026-08-10, before any IQ3_XXS Metal candidate was implemented or
observed

## Bound role and matrix

- Quantization: GGML `IQ3_XXS` (`type_id = 18`)
- Role: routed-expert down projection only
- Representative tensor: `blk.3.ffn_down_exps.weight`
- Expert: 15
- Logical row-major shape: `[6144, 2048]`
- Block: 256 weights in 98 bytes
- Packed row: `8 * 98 = 784` bytes
- Selected-expert matrix: `6144 * 784 = 4,816,896` bytes
- Activation: contiguous finite f32 SwiGLU output with exactly 2,048 elements
- Output: contiguous finite f32 vector with exactly 6,144 elements

The checkpoint set, tensor range, packed-byte SHA-256, activation SHA-256, and
same-order reference-output SHA-256 MUST be recorded before the first real
candidate dispatch.

## Reference hierarchy

1. The bit-exact oracle is the scalar IQ3_XXS decoder followed by f32
   multiplication and sequential-column f32 accumulation over columns
   `0..2048`. Signed-zero positions are part of exact identity.
2. The exact-bit NumPy whole-matrix decoder plus synchronized MLX matmul is the
   optimized performance reference and a Tier B numerical comparator. MLX
   tiled reduction is not the bit-exact oracle.
3. The Metal candidate consumes the 98-byte packed blocks directly and MUST
   NOT be invoked by either reference.

## Frozen IQ3 single-matrix envelope

The IQ3 matrix uses a distinct envelope rather than inheriting IQ2 gate/up
constants. Its admitted dot contains 2,048 sequential terms, one third of the
IQ2 gate/up column count, so the pre-observation bound is intentionally tighter:

- Elementwise: `abs(candidate - oracle) <= 0.00025 + 0.00025 * abs(oracle)`
- Cosine similarity: at least `0.9999995`
- Candidate/oracle norm ratio: `[0.99975, 1.00025]`
- All values finite; output length and order exact
- Reference-zero comparisons use the combined elementwise gate, not infinite
  relative error

The existing Feature 018 composed-boundary envelope remains unchanged:
absolute/relative `0.005`, cosine `0.999`, norm ratio `[0.995, 1.005]`, with
exact routes, tensor identities, ordering, and greedy-token checks.

## Determinism and classification

- Synthetic: at least 100 identical executions.
- Real matrix: at least 10 identical correctness executions, followed by 3
  warmups and 30 retained performance samples.
- Every output hash, f32-bit mismatch, signed-zero mismatch, first mismatch,
  tolerance mismatch, maximum and mean absolute error, RMSE, maximum meaningful
  relative error, cosine similarity, and norm ratio is retained.
- Classifications remain `golden_identical`,
  `numerically_qualified_greedy_identical`,
  `numerically_qualified_greedy_divergent`, and `numerically_failed`.

The deterministic one-thread-per-output-row IQ3 kernel is the qualification
scaffold. If a later parallel kernel changes reduction order, it is a distinct
Tier B candidate and does not replace the scaffold.

## Capability and failure semantics

- Direct IQ3 dispatch is admitted only for routed down tensors with exact
  IQ3_XXS layout and byte accounting.
- Unsupported roles or formats are intentional explicit reference dispatches
  selected before candidate invocation.
- A selected direct operation that fails is a direct error. Validation stops;
  it MUST NOT recover to the reference implementation and report success.
- Hidden CPU fallback, complete f32 weight materialization, nondeterminism,
  malformed input reaching dispatch, unsafe lifetime, or a frozen numerical
  gate failure classifies the attempt `numerically_failed`.

This contract is immutable. A changed threshold requires a new version,
preserved failing evidence, pre-rerun justification, and complete revalidation.
