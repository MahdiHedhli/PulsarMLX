# Catalog contract — the refusal vocabulary, in enforcement order

Every rule below is checked before any payload byte is readable, and every
refusal is a distinct error variant so that a test can assert *which* defect it
found rather than that something went wrong. The negative fixture corpus under
`fixtures/safetensors/negative/` names the expected variant on the first line
of each case's `README`, and two tests read that line.

Nothing here knows any model. Module paths are opaque strings; there is no
regular expression over a tensor name in either crate.

## Order of enforcement

A defect that could match two rules is reported by the first rule below that
sees it. That order is part of the contract, because a fixture asserts one
variant.

### Per shard file

| # | Rule | Refusal |
|---|---|---|
| 1 | at least 8 bytes, and `file_len >= 8` | `MalformedHeader` |
| 2 | `n <= MAX_HEADER_BYTES` (100 MiB) | `HeaderTooLarge` |
| 3 | `8 + n <= file_len`, and that many bytes are actually supplied | `MalformedHeader` |
| 4 | the first byte after the prefix is `{` | `MalformedHeader` |
| 4b | the header bytes are JSON, and no object member repeats at any depth | `InvalidJson`, `DuplicateKey` |
| 5 | the JSON is an object | `NotAnObject` |
| 6 | `__metadata__`, if present, is a map of string to string, and appears once | `InvalidMetadata` |
| 7 | each entry has `dtype`, `shape` and a two-element `data_offsets`, all of the right JSON type | `InvalidTensorEntry` |
| 8 | the dtype string is a standard Safetensors dtype | `UnsupportedDtype` |
| 9 | each dimension is a non-negative integer at most `u32::MAX` | `InvalidShape` |
| 10 | `begin <= end <= data_len` | `InvalidRange` |
| 11 | the shape product, by `checked_mul` in `u64`, does not overflow; nor does product times element size | `Overflow` |
| 12 | `end - begin == elements * dtype.size_bytes()` | `LengthMismatch` |
| 13 | no name appears twice in one header (a repeated JSON member) | `DuplicateKey` |
| 14 | no two tensors overlap | `OverlappingRanges` |
| 14b | the tensors tile the data section, leaving no uncovered byte | `Gap` |

Gaps are **not** legal. Upstream Safetensors requires the data buffer to be
fully covered; Round 1 admitted gaps as an extension and Round 2 stopped,
because a reader that tolerates them cannot tell an intentional layout from a
truncated or mis-declared one, and all eighteen shards of the real checkpoint
this feature targets are gap-free. `gap_bytes` is therefore always zero: the
field is kept because reporting it is stating a checked fact, and because a
future extension would have to change the value rather than reinterpret it.
A zero-length tensor is still admitted, but only at a boundary between
tensors.

### Per checkpoint

| # | Rule | Refusal |
|---|---|---|
| 15 | the root is a directory | `Io` |
| 16 | an index exists, or exactly one `*.safetensors` does, as `OpenMode` allows | `AmbiguousLayout` |
| 17 | the index exists as a **regular file**, is within `MAX_INDEX_BYTES`, is an object with a non-empty `weight_map` of string values, and `metadata.total_size`, if present, is a non-negative integer | `InvalidIndex` |
| 18 | every shard file name is a plain name inside the root | `InvalidShardPath` |
| 19 | every named shard exists | `MissingShard` |
| 20 | every shard and the index are opened with `openat` relative to a held descriptor on the canonicalized root, with `O_NOFOLLOW`, and the opened descriptor's `(device, inode)` matches an `fstatat` of the same name | `PathEscape` |
| 21 | every `weight_map` entry appears in the header of the shard it names | `MissingTensorInShard` |
| 22 | every header tensor appears in `weight_map` | `UnindexedTensor` |
| 23 | no name appears in two shards | `DuplicateTensor` |
| 24 | the shard count fits a `ShardId(u16)` | `AmbiguousLayout` |

### Per read

| # | Rule | Refusal |
|---|---|---|
| 24b | the aggregate payload total does not overflow `u64` | `Overflow` |
| 25 | reads are addressed by **name**; an unknown name is refused and a caller-supplied `TensorMeta` is never consulted | `UnknownTensor` |
| 25b | `offset_within + len` does not overflow and does not exceed `byte_len` | `RangeOutOfBounds` |
| 26 | the destination length equals the requested length exactly | `DestinationLengthMismatch` |
| 27 | the catalog is backed by files | `NoBackingFile` |

## Shard path admission, in full

Admitted: a non-empty string of ASCII letters, digits, `.`, `_` and `-`, not
beginning with `.` or `-`, neither `.` nor `..`, ending in `.safetensors` with
at least one character before the extension.

This is a whitelist, so a spelling nobody anticipated is refused rather than
interpreted. It rejects `../x.safetensors`, `/abs/x.safetensors`,
`sub/x.safetensors`, `sub\x.safetensors`, an embedded NUL, `.hidden.safetensors`
and `-lead.safetensors`, and it is applied *before* the file system is touched.
Rule 20 is the second line of defence: a name that passes the whitelist but
resolves outside the root — a symlink — is still refused.

## What determinism means here

Shards are sorted by file name and tensors by name. Nothing in the catalog
depends on directory order, on file system timing or on the order the index
happens to list things in. `catalog_digest()` is the sha256 of

a record count as a little-endian `u64`, then per tensor, in name order, six
**length-framed** fields -- name, dtype, shape, shard file name, `data_begin`,
`data_end` -- each written as its byte length as a little-endian `u64`
followed by its bytes, with the shape as comma-separated decimals.

Framing rather than delimiters, because tensor names are opaque: a name
containing a tab or a newline made the earlier delimiter-joined form
structurally ambiguous, so two different catalogs could produce one digest.
Two opens of the same bytes give the same digest, and the two mixed fixtures —
which differ only in whether the index declares `total_size` — give the same
digest as each other, because the catalog does not depend on that field.

## What this contract does not cover

Payload identity of a real checkpoint (Q0), dequantized values, quantized
matmul, kernel selection and residency. The first is separately authorized
later work; the second is `numerics-v1.json`; the rest are out of scope for
Slice 1.

## Round 2 amendments

Recorded rather than folded in silently, so a reader can see what moved.

* **Strict coverage.** Gaps were admitted in Round 1 as a deliberate extension
  of the format. They are now refused (`Gap`). The Flash header census
  confirmed all eighteen real shards are gap-free before this was decided.
* **The initial byte.** A header beginning with whitespace before `{` parsed
  as JSON and was accepted; it is now `MalformedHeader`.
* **Length-framed digest.** Tensor names are opaque and may contain the
  delimiters the earlier serialization used.
* **Duplicate members at any depth.** `DuplicateKey` with a dotted path
  replaces the outermost-level-only check, and `DuplicateTensor` narrows to
  mean one thing.
* **Descriptor-bound admission.** Containment is decided about the object a
  descriptor holds, not about a pathname resolved separately.
* **The admitted dtype set.** Fifteen strings, listed. Upstream defines more,
  including sub-byte types; refusing them by name is the safe direction.
