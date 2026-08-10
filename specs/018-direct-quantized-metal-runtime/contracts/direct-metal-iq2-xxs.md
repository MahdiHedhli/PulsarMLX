# Direct Metal IQ2_XXS Contract

## Supported request

- Quantization: GGML IQ2_XXS (`type_id = 16`)
- Logical matrix: row-major `[rows, columns]`
- `rows > 0`, `columns > 0`, `columns % 256 == 0`
- Packed row bytes: `(columns / 256) * 66`
- Packed matrix bytes: `rows * packed_row_bytes`
- Activation: contiguous f32 vector of exactly `columns` elements
- Output: contiguous f32 vector of exactly `rows` elements

## Packed block layout

Each 66-byte block represents 256 weights:

1. Bytes `0..2`: little-endian IEEE f16 base scale.
2. Bytes `2..66`: eight 8-byte groups.
3. Each group begins with four grid indices and ends with one little-endian
   32-bit word encoding four sign-table indices and a 4-bit scale multiplier.
4. The immutable grid table contains 256 entries of eight u8 magnitudes.
5. The immutable sign table contains 128 u8 masks.

The kernel computes packed decode and dot accumulation directly. It MUST NOT
allocate or write a `[rows, columns]` f32 weight matrix.

## Ownership

- Packed bytes reside in a Rust-owned page-aligned stable slab.
- Metal registration uses a no-copy shared buffer view whose lifetime borrows
  the slab and context.
- Activation, lookup, and output buffers remain alive through command-buffer
  completion.
- Registration teardown occurs only after no command references the buffer.
- Slot generation prevents stale registration reuse after allocator reuse.

## Validation mode geometry

- One logical Metal thread owns one output row.
- The thread visits blocks, 32-weight groups, grids, and elements in increasing
  logical column order.
- Accumulation is f32.
- Tail columns are unsupported in v1 because admitted columns are divisible by
  256; unsupported tails fail before dispatch.

## Errors

Requests fail before dispatch for null or unaligned slab, zero dimensions,
arithmetic overflow, size mismatch, unsupported quantization, non-finite
activation, lookup hash mismatch, or device/pipeline unavailability.

A committed successful result requires command-buffer completion and zero
fallback. Reference fallback is an explicit separate mode, never internal to
this contract.
