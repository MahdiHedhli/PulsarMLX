# Direct Metal IQ3_XXS Down Contract

## Supported request

- GGML IQ3_XXS (`type_id = 18`), routed-expert down role only
- Row-major `[rows, columns]`; `rows > 0`, `columns > 0`
- `columns % 256 == 0`
- Packed row bytes: `(columns / 256) * 98`
- Exact packed matrix bytes: `rows * packed_row_bytes`
- Contiguous finite f32 activation of `columns` elements
- Contiguous finite f32 output of `rows` elements

## Packed block layout

Each 98-byte block encodes 256 weights:

1. Bytes `0..2`: little-endian IEEE f16 base scale.
2. Bytes `2..66`: 64 grid indices, eight per 32-weight group. Each index
   addresses four u8 magnitudes in the immutable 256-entry IQ3 grid.
3. Bytes `66..98`: eight little-endian u32 scale/sign words. Bits `28..32`
   encode the group scale nibble; four 7-bit sign indices encode parity-expanded
   eight-lane sign masks.
4. For each 32-weight group, four index pairs produce four plus four magnitudes
   under one sign mask. The candidate visits logical columns in increasing
   order and accumulates f32.

The direct path MUST NOT allocate or write a `[rows, columns]` f32 weight
matrix. Small immutable grid/sign metadata is allowed and hash-bound.

## Ownership and compiler semantics

The existing Feature 017/018 page-aligned slab, no-copy registration,
completion-handler retention, in-flight counter, generation protection, and
teardown invariants apply unchanged. The registration remains immutable until
all referencing command buffers complete.

Qualification uses explicit Metal compile options: fast math disabled,
safe/precise math, and language version 3.2. Compiler settings and the distinct
IQ3 pipeline identity are emitted in evidence.

## Rejection and telemetry

Null, unaligned, zero, overflowing, truncated, overlong, wrong-role,
wrong-quantization, non-finite, stale-generation, cross-context, or lookup-hash
inputs fail before dispatch. A successful validation call records zero CPU
fallback and zero complete-f32 materialized weight bytes.

Timing separates checkpoint read, no-copy registration, library compilation,
pipeline creation, dispatch preparation, kernel interval when available,
synchronization, first-use total, and every steady-state total sample.
