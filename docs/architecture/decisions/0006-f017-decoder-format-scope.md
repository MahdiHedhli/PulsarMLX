# ADR 0006: Select native decoder work from the authoritative inventory

- **Status**: Accepted for Feature 017 prioritization
- **Date**: 2026-08-10

## Decision

Feature 017 does not implement a decoder merely because a format appears in a
separate benchmark. Decoder work must be justified by the current GLM52
checkpoint inventory or by a versioned public-safe/local-only fixture that
binds the format to a runtime boundary.

The next uncovered format candidate is **Q5_K**. The authoritative trunk
inventory contains 162 Q5_K non-expert tensors and the existing research
evidence already qualifies real Q5_K matrix behavior against the Python
reference. Q4_K is a later output/embedding candidate with only two inventory
entries. Q6_K, IQ2_XXS, and IQ3_XXS are already banked in Rust and remain
covered by their existing exact tests and fixtures.

The following formats are deferred, not rejected:

| Format | Current F017 evidence | Decision |
| --- | --- | --- |
| Q2_K | No occurrence in the authoritative 1,353-tensor non-expert trunk inventory; no F017 manifest or fixture binds it to GLM52. | Defer until a GLM52 expert/local fixture is available. |
| Q3_K | Same inventory and fixture gap. | Defer until a GLM52 expert/local fixture is available. |
| IQ2_S | No F017 decoder fixture or authoritative inventory occurrence; current GLM52 expert evidence is IQ2_XXS. | Defer until a format-bound expert fixture is available. |
| IQ4_XS | No F017 decoder fixture or authoritative inventory occurrence. | Defer until a format-bound expert fixture is available. |

The inventory excludes 456 expert matrices, so absence from the trunk file is
not evidence that a format cannot occur in expert data. It is only a reason to
wait for a bound expert manifest rather than inventing production coverage.

## Consequences

- Q5_K is the next candidate for exact Rust implementation after the current
  Q8_0, Q6_K, IQ2_XXS, and IQ3_XXS boundaries.
- New decoder work must include synthetic blocks, malformed/truncated input,
  no-partial-write behavior, overflow-safe lengths, exact comparison where
  supported, and separate decode/allocation measurements.
- Feature 018 kernel evidence does not silently expand Feature 017 decoder
  scope.
- A new format can be promoted by adding a manifest with tensor identity,
  shard/range, checkpoint revision, quantization, dimensions, and content
  hash, followed by the normal exact qualification gate.
