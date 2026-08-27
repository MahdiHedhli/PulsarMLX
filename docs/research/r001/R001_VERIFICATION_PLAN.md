# R001 Independent Verification Plan

The production repacker is Rust. Acceptance verification is a standalone
Python implementation that does not import the Rust mapping, bundle reader, or
generated schemas.

The verifier independently parses all GGUF headers, honors
`general.alignment`, maintains its own quantization geometry table, derives
tensor lengths from dimensions, recognizes anchored expert tensor names, and
reconstructs every `(layer, class, expert, role)` range.

For each selected bundle it requires:

1. Valid v1 header, footer, canonical metadata, reserved bytes, and exact file
   length.
2. Exact checkpoint, layer, expert, class, tensor, role, shape, type, block,
   source shard, offset, and length identity.
3. Independent chunked source-to-bundle byte equality.
4. Component, canonical payload, physical payload, object, footer, and stored
   hashes.
5. Zero padding and no trailing bytes.
6. Exact expected object-key coverage and uniqueness.

Semantic samples decode first, last, final-row, and deterministic interior
blocks for all observed quantization classes after exact byte equality. These
samples are mapping sanity, not decoder or model-output qualification.

Negative tests cover identity/component swaps, bad offsets and shards, header,
payload, padding and footer corruption, truncation, trailing data, unexpected
finals, interrupted partials, source changes, stale plans, path traversal,
links, and deterministic two-run regeneration.
