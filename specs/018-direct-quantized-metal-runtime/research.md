# Research Decisions: Direct-Quantized Metal Runtime

## Target selection

**Decision**: Keep IQ2_XXS routed gate/up as the first target.

**Rationale**: The committed P2 model attributes 55.750817 seconds of warm
routed decode to 1,184 IQ2_XXS gate/up matrix touches, the largest measured
absolute quantized expert opportunity. No newer evidence invalidates it.

**Alternatives considered**: IQ3_XXS down is second at 43.125401 seconds;
Q2_K, IQ4_XS, Q3_K, and IQ2_S are each below 2.4 seconds. Starting a second
format before the first target qualifies would increase scope without resolving
the largest measured boundary.

## Ownership and registration

**Decision**: Reuse the same-repository Feature 017 stable page-aligned slab and
`newBufferWithBytesNoCopy` registration contract through selective clean
cherry-picks of `111ffb6d` and `f2b1b130`.

**Rationale**: Those commits already prove stable address, borrow-tied Metal
registration, registration identity, completion before return, and deterministic
teardown. Selective reuse avoids duplicating unsafe lifetime code and avoids
merging Feature 017's unrelated orchestration work.

**Alternatives considered**: Copying files would lose history; merging Feature
017 would couple independent work; allocating a new Metal-owned copy would not
exercise the target zero-copy ownership contract.

## Kernel shape

**Decision**: Begin with one logical output row per Metal thread and sequential
f32 accumulation across packed blocks.

**Rationale**: This geometry is the smallest inspectable true direct-quantized
operation. It uses packed weights directly, avoids a reduction-order design
choice before correctness evidence, and can be replaced behind the same ABI if
it is too slow.

**Alternatives considered**: SIMD-group reductions and threadgroup-tiled input
reuse may be faster but introduce reduction-order and synchronization changes.
Full f32 materialization followed by MLX is already the reference path and is
not direct quantized.

## Rust scalar oracle

**Decision**: Selectively reuse clean Feature 017 commit `a5fcf92f` for its
exact IQ2_XXS/IQ3_XXS f32 decoder and tests.

**Rationale**: The decoder is independently tested, stays on CPU, and gives the
Rust native Metal test a reviewed oracle without inventing a second packed
layout. It is reference infrastructure, not a second direct-kernel target.

**Alternatives considered**: Duplicating the decoder in `stream` would create
avoidable drift. The existing `cpu_dot` IQ2_XXS path quantizes activations to
Q8_K and therefore is not the f32-activation oracle required here.

## Lookup-table placement

**Decision**: Upload immutable IQ2_XXS grid magnitudes and sign masks once per
context as small read-only shared buffers.

**Rationale**: The tables describe the quantization format and total only a few
kilobytes. They do not materialize model weights and can be hash-checked against
the Python oracle tables.

**Alternatives considered**: Embedding large constants in shader source makes
review and generation error-prone; recomputing grids is unnecessary; full
decoded weights violate the feature boundary.

## Accumulation and numerical classification

**Decision**: Accumulate f32 in deterministic row order in validation mode and
classify with the frozen contract in `numerical-qualification-contract.md`.

**Rationale**: The product path is allowed to differ from scalar bit order, but
the difference must be bounded before timing. The four classes separate exact
identity, qualified same-greedy behavior, qualified divergence, and failure.

**Alternatives considered**: f16 accumulation risks avoidable drift; f64 is not
the intended Apple GPU compute contract; ad hoc tolerance changes after a
failure violate the project constitution.

## Compilation and timing

**Decision**: Compile the research shader once when creating the context,
record first-use compilation separately, retain the pipeline, and synchronize
every validation dispatch before reading output or ending the timer.

**Rationale**: Runtime compilation is transparent and sufficient for a bounded
research feature. It cleanly separates one-time setup from steady-state.

**Alternatives considered**: Precompiled metallib packaging is appropriate
after the ABI and kernel qualify. Unsynchronized timers are invalid.

## Fallback

**Decision**: Direct mode fails closed. Scalar/NumPy/MLX reference modes remain
explicit caller choices rather than hidden fallbacks.

**Rationale**: A successful direct result must prove that Metal executed the
requested boundary. Hidden fallback would corrupt correctness and timing claims.

## Deeper ladder and P1

**Decision**: Advance one rung at a time and admit at most one P1 only after a
material qualified complete-layer improvement.

**Rationale**: A matrix result cannot establish expert or token performance.
P2 and golden-eight are already unnecessary and explicitly out of scope.
