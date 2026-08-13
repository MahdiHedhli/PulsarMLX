# F017 M1-E IQ3_XXS Decoder Internal Implementation Review

**Verdict: GO FOR FRESH M1-E ATTEMPT 2**

## Review scope

The review covered decoder indexing, grid/sign lookup, block and row
boundaries, scale interpretation, endian conversion, row-major output order,
canonical f32 serialization, failure handling, versioning, and attempt-2
admission. It did not re-review M1-E candidate numerics and did not execute an
expert.

## Findings

- The 98-byte / 256-value IQ3_XXS block layout, 32-byte auxiliary area,
  f16 scale, high-nibble subscale, grid lookup, sign masks, and row packing
  match the pinned GGML reference.
- Rust writes grid 1 lanes to output positions 0–3 and grid 2 lanes to 4–7.
  It was correct and was not changed.
- Both Python implementations encoded the same wrong interleaving. The scalar
  two-loop correction and removal of the NumPy grid/lane transpose now make
  both paths exact.
- Decode routines reject malformed lengths and non-finite scales without
  partial output. The identity is row-major IEEE-754 f32 little-endian with no
  padding or NaN canonicalization.
- The one-block regression would fail under the old code and now matches the
  independent third decoder and Rust bit for bit.
- Full real-down output is identical across all three implementations at
  `f91987106198943c8a225b52dcf0099ba8f8b89d1ecad92c4a7c5c4964e20eae`.
- Config v2 rejects decoder v1, carries attempt-1 evidence, requires attempt
  number 2, and hash-binds the third decoder and regression fixture.
- The frozen scaffold and Tier-B contract are unchanged. Only corrected
  matrix-specific oracle output and bound artifacts differ.

No unresolved implementation defect remains in the reviewed delta.
