# Contract: Tensor Semantics and Q8_0 Reference v1

**Status**: Implemented and validated at the bounded v1 fixture and Q8_0 scope

**Initial quantization**: GGUF Q8_0

## Tensor descriptor

Every public tensor operation receives or resolves an immutable descriptor:

```text
logical_shape
storage_shape
layout
input_dtype
accumulation_dtype
output_dtype
element_count
encoded_byte_count (when encoded)
quantization (when quantized)
synchronization_rule
```

All products and byte calculations use checked arithmetic. Zero dimensions,
unsupported rank, mismatched element/byte count, unsupported dtype/layout, and
lossy integer conversion are rejected before creating an MLX array.

GGUF fastest-varying-first dimensions and conventional MLX array shapes are
not treated as interchangeable. Every projection contract states whether bytes
are interpreted directly, reshaped, or transposed. Nonsymmetric fixture values
must make an accidental transpose observable.

## Execution and synchronization

- The selected device is explicit.
- Creation or queueing is not completion.
- A validation result is observable only after `mx.eval` of the result graph and
  `mx.synchronize` for the selected GPU stream/device.
- Readback is bounded and is an explicit synchronization boundary.
- A backend error, non-finite result where disallowed, or missing evaluation
  evidence fails the operation; no CPU retry occurs.
- Backend-owned handles cannot outlive the backend context.

## Initial dense fixture operations

The reference suite covers, in dependency order:

1. elementwise arithmetic and bounded readback;
2. nonsymmetric matrix multiplication;
3. embedding gather with valid and invalid token IDs;
4. RMS normalization with a declared epsilon and accumulation dtype;
5. residual addition with exact shape rules;
6. router score normalization and deterministic top-k; and
7. the tensor operations required by the bounded routed-expert fixture.

Each fixture has an independently calculated host oracle. Test code must not
compute expected values through the MLX function under test.

## Q8_0 encoded layout

The existing GGUF type table defines Q8_0 as 32 logical elements in 34 bytes:

```text
bytes 0..2   little-endian IEEE-754 binary16 scale d
bytes 2..34  32 signed int8 quantized values q[0..32]
value[i] = f16_to_f32(d) * float(q[i])
```

The first strict portable entry points cover a complete row decode and a
row-by-float-vector dot/matvec reference. A row width must be divisible by 32;
the initial contract has no partial-block tail. Exact encoded bytes are:

```text
blocks = row_width / 32
encoded_bytes = blocks * 34
```

Both calculations are checked. The encoded input length and destination length
must equal their contracts exactly. Extra bytes are not ignored.

## Q8_0 validation

Before decoding or multiplying, reject:

- zero row width;
- row width not divisible by 32;
- checked-arithmetic overflow;
- encoded length other than exactly `row_width / 32 * 34`;
- output length other than the declared row/output dimensions;
- unsupported byte order or scale representation;
- non-finite scale unless a future compatibility record explicitly admits it;
  and
- input activation containing a disallowed non-finite value.

The implementation must not expose a panic for malformed public input.

## Required Q8_0 oracle cases

1. Hand-construct at least these independent blocks:
   - zero scale and all-zero quants;
   - positive exactly representable scale with negative, zero, and positive
     signed bytes;
   - negative scale, if accepted by the GGUF representation;
   - extrema `-128` and `127`; and
   - two distinct blocks to expose block-scale and indexing errors.
2. Check every decoded value against the hand calculation.
3. Compare scalar row dot/matvec with dequantize-then-float accumulation under a
   predeclared accumulation rule.
4. Execute the equivalent MLX expression and compare with the scalar oracle.
5. Exercise every malformed rule above and prove rejection before MLX
   execution.

Existing upstream round-trip and CUDA tests are useful inherited evidence but
do not replace this strict Apple boundary suite.

## Comparison policy

- Integer IDs, shapes, dtypes, byte counts, route order, and exact hand-decoded
  values representable in the chosen output type use exact comparison.
- Floating tensor operations use both absolute and relative tolerance fixed in
  each fixture before the Apple result is inspected.
- Report compared element count, maximum absolute error, maximum relative
  error, and the first bounded mismatch.
- NaN or infinity fails unless the fixture explicitly defines it as an expected
  value and comparison behavior.
- A checksum may supplement but cannot replace tolerance evidence.

Implemented fixtures use concrete per-operation tolerances chosen from
reference behavior and committed before Apple output. This contract does not
invent unmeasured universal tolerances.

## Router contract used by synthetic MoE

- Scores must be finite.
- `expert_count > 0`, `top_k > 0`, and `top_k <= expert_count`.
- Sort by score descending; exact ties resolve by ascending expert ID.
- Normalize selected weights with the declared function and accumulation dtype.
- Repeated expert IDs across different tokens are valid.
- Selected IDs and ordering compare exactly; normalized weights and final
  accumulation use declared numeric tolerances.

## Admission to a real-model slice

A tensor or quantized operation enters the real-model graph only when:

1. its descriptor and malformed-input tests pass;
2. scalar/reference fixtures pass;
3. the evaluated MLX comparison passes;
4. the model tensor role, orientation, dimensions, and exact encoded bytes match
   the compatibility record; and
5. the memory budget includes decoded and temporary allocations.

Failure leaves the operation/model status `blocked` or `unsupported`; it does
not trigger an alternate unvalidated interpretation.
