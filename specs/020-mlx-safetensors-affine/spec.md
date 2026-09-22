# Feature 020 — native Safetensors catalog and MLX affine representation

**Slice 1 only.** This document states the rules the two crates implement. It
is model-neutral throughout: no model's tensor names appear in it, because none
appear in the crates.

Governing design: the F020 Phase 0 design note v2 (2026-09-22). Numerical
contract: `contracts/numerics-v1.json`. Catalog rules in enforcement order:
`contracts/catalog-contract.md`. Current state and what is not claimed:
`docs/architecture/f020-native-safetensors-status.md`.

## 1. Scope

In scope for Slice 1:

* Safetensors header parsing and validation, without touching payload.
* Sharded `model.safetensors.index.json` handling.
* Deterministic tensor catalog construction with a stable digest.
* Bounded, checked offset and range arithmetic.
* Dtype and shape representation.
* The MLX affine packed-weight representation: `weight`/`scales`/`biases`
  association, bit width and group size, global and per-module override
  resolution, fail-closed handling of anything unsupported or ambiguous.
* The provenance needed to identify the source shard and byte range of one
  expert or one row.
* Synthetic fixtures and the native numerical and parser tests.

Explicitly out of scope for Slice 1: quantized matmul and gathered quantized
matmul, kernel selection, router and top-k, residency and streaming, any model
graph, any real-checkpoint payload claim, and any performance claim.

## 2. Dtypes

Every standard Safetensors dtype string parses and reports its element size:
`BOOL`, `U8`, `I8`, `F8_E5M2`, `F8_E4M3` (1 byte); `I16`, `U16`, `F16`, `BF16`
(2); `I32`, `U32`, `F32` (4); `F64`, `I64`, `U64` (8). Support at this layer
means exactly that — parse and size. What a consumer accepts is the consumer's
decision: `mlx-affine` admits `U32` packed weights and `F16`, `BF16` or `F32`
metadata and refuses the rest. An unknown dtype string is
`CatalogError::UnsupportedDtype`, carrying the tensor name and the string.

## 3. Header

The first eight bytes are a little-endian `u64` header length `n`. Required:
`n <= MAX_HEADER_BYTES` (100 MiB), `8 + n <= file_len`, and the JSON is an
object. `__metadata__`, if present, is a map of string to string. Every other
entry is a tensor and must carry `dtype`, `shape` and `data_offsets`.

* `shape` is an array of non-negative integers, each at most `u32::MAX`. The
  element count is their product, taken with `checked_mul` in `u64`; an
  overflow is `Overflow`. An empty shape is a scalar, i.e. a product of one.
* `data_offsets` is `[begin, end]` with `begin <= end <= data_len`, where
  `data_len = file_len - 8 - n`.
* `end - begin` must equal `elements * dtype.size_bytes()`, computed with
  `checked_mul`; otherwise `LengthMismatch`. A zero-element tensor is admitted
  only with `begin == end`.
* A name appearing twice in one header is `DuplicateTensor`. Duplicate JSON keys
  are detected rather than collapsed.
* Tensors must be pairwise non-overlapping. Gaps are legal and are recorded in
  `ShardHeader.gap_bytes`, which is the data section's length minus the bytes
  the tensors cover.

## 4. Index

`weight_map` maps tensor name to shard file name; `metadata.total_size` is
optional. A shard file name must be a plain file name inside the root: a
non-empty run of ASCII letters, digits, `.`, `_` and `-`, not beginning with
`.` or `-`, neither `.` nor `..`, containing no `/`, `\` or NUL, and ending in
`.safetensors` with at least one character before the extension. Anything else
is `InvalidShardPath`, decided before the file system is touched.

## 5. Opening a checkpoint

The root must be a directory. If `model.safetensors.index.json` exists it is
used; otherwise exactly one `*.safetensors` file is admitted as a single shard;
otherwise `AmbiguousLayout`. `OpenMode` lets a caller require one of the two
layouts instead of accepting either.

For each referenced shard: it must exist under the root (`MissingShard`), and
its canonicalized path must still lie inside the canonicalized root
(`PathEscape`, which is what catches a symlink out of the tree). Its header is
then read and validated.

The index and the headers must agree **in both directions**:

* every `weight_map` entry must appear in the header of the shard it names —
  otherwise `MissingTensorInShard`, which is also what a cross-shard mismatch
  produces;
* every tensor in every shard's header must appear in `weight_map` — otherwise
  `UnindexedTensor`. There are no silent extras;
* the same name in two shards is `DuplicateTensor`.

## 6. The catalog

`TensorMeta { name, dtype, shape, elements, byte_len, shard, data_begin,
data_end }`, where `shard` is a `ShardId(u16)` index into the shard list sorted
by file name and `data_begin` is the absolute file offset `8 + n + begin`.

Determinism: shards are sorted by file name, tensors by name, and nothing
depends on directory order. `catalog_digest()` is the sha256 of one canonical
line per tensor, in name order:

```
name\tdtype\tshape\tshard_file\tdata_begin\tdata_end\n
```

with the shape written as comma-separated decimals and an empty shape as an
empty field. Two independent opens of the same checkpoint produce the same
digest.

## 7. Provenance and reads

`ShardProvenance { file_name, file_len, header_len, sha256 }`. The digest is
`None` until an explicit `Checkpoint::hash_shards()` call: a real shard is tens
of gigabytes, so hashing is never implicit.

Reads are `read_tensor_bytes` and `read_range(tensor, offset_within, len)`,
both through `pread` with checked bounds; `offset_within + len` must not exceed
`byte_len` (`RangeOutOfBounds`) and the destination length must match exactly.
There is no memory map in this slice. A mapped reader is a later addition
behind these same accessors, not a change to them.

`Checkpoint::from_headers` builds the same catalog from header bytes alone,
with no file system access, for a compatibility census over a checkpoint that
stays on another host. Reads in that mode are `NoBackingFile`.

## 8. The affine representation

`Bits` is 4 or 8. `GroupSize` is 32, 64 or 128. `Mode` is `affine`. Anything
else in a configuration is `UnsupportedQuantization`, including bits 2, 3, 5
and 6, group sizes 16 and 256, a non-`affine` mode, and non-integer or negative
values.

The restriction to 4 and 8 bits is not conservatism for its own sake: at those
widths `32 % bits == 0` and a code never straddles a 32-bit word, while MLX
uses a different bit-serial layout for the widths that do not divide 32.
Admitting a width whose layout the decoder does not implement would mis-decode
silently.

`QuantizationConfig::from_config_json` reads the `quantization` object. If
`quantization_config` is also present the two must be identical, otherwise
`InconsistentConfig`. The object's top-level `bits` and `group_size` are the
default and both are required. Every other key is a module path whose value
must be an object carrying its own `bits` and `group_size`; anything else is
`UnsupportedOverrideValue`. If there is no `quantization` object at all the
result is `NoQuantizationConfig`: the representation cannot resolve, and the
caller may still use the catalog unquantized.

**The upstream `False` override value is deliberately not admitted.** The
upstream Python loader writes `False` for "do not quantize this module".
Absence from the dict already means "no explicit override", and the presence of
`<module>.scales` already decides whether the default applies, so `False` is
redundant with a rule that is checked against the shards themselves. Admitting
it would create a second, weaker source of truth for the same question.

### 8.1 Association and classification

For a module path `p` the triple is `p.weight` (must be `U32`), `p.scales` and
`p.biases` (the same dtype, one of `F16`, `BF16`, `F32`, and identical shapes).

* **Quantized** when all three exist and the resolved spec is consistent.
* **Unquantized** when `p.weight` exists, is not `U32`, neither companion
  exists, and there is no explicit override.
* `IncompleteTriple` when one or two of the three are present, or `p.weight` is
  `U32` without both companions, or a weight with companions is not `U32`.
* `ScalesBiasesMismatch` when the companions differ in dtype or shape, or their
  dtype is not one of the three admitted.
* `OverrideWithoutScales` when a module with an explicit override has no
  `.scales`.
* `AmbiguousQuantization` when `.scales` exists and the checkpoint declares no
  quantization object. The shards say quantized and the configuration says
  nothing; guessing a width is the failure this crate exists to prevent.

### 8.2 Resolution and consistency

An explicit override wins. Otherwise the default spec applies **if and only
if** `p.scales` exists. Otherwise the module is unquantized.

The resolved spec is then checked against the stored shapes. With
`packed_cols = weight.shape[-1]` and `groups = scales.shape[-1]`:

* `in_features = groups * group_size`;
* `packed_cols * (32 / bits) == in_features`, exactly;
* all leading dimensions of weight, scales and biases are equal;
* `scales.shape[-1] == biases.shape[-1]`.

A failure is `InconsistentOverride`, reporting `implied_bits =
32 * packed_cols / in_features` when that division is exact and `None` when it
is not. This is MLX's own `validate_quantized_input` invariant, restated and
enforced.

### 8.3 Slicing

`AffineTriple::expert_slice(index_path)` returns the three `(shard, begin,
len)` ranges of one `[out_features, in_features]` plane — one expert of a
stacked `[E, out, in]` tensor, for instance — and `row_slice(index_path, row)`
does the same for one row. Both are pure checked arithmetic: nothing is read,
every multiplication is checked, and an index outside the leading dimensions is
`IndexOutOfBounds`.

This is the provenance a residency layer will need. Residency itself is out of
scope for this slice.

### 8.4 Decoding

Element `j` of a row occupies bits `[j*bits, j*bits + bits)` of that row's
contiguous little-endian `u32` stream. A group is `group_size` consecutive
elements along the last axis, and `w = scale * code + bias` with one
`(scale, bias)` pair per group. The scale may be negative: MLX's implemented
encoder uses a signed scale and the larger-magnitude group edge as the bias,
snapped so that zero quantizes exactly. A decoder must simply not assume a
positive scale, and this one does not.

`decode::dequantize_rows` computes in `f32`, as one multiplication followed by
one addition, never a fused multiply-add. `reference::dequantize_rows_*`
computes the same thing in binary64 from its own integer unpack. What their
agreement means is `contracts/numerics-v1.json`.

## 9. Acceptance

The nine acceptance criteria for Slice 1 are listed in
`contracts/numerics-v1.json` under `acceptance_criteria_slice_1`, and the
status document records the result of each.
