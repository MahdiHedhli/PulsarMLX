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
| 4 | the header bytes are JSON | `InvalidJson` |
| 5 | the JSON is an object | `NotAnObject` |
| 6 | `__metadata__`, if present, is a map of string to string, and appears once | `InvalidMetadata` |
| 7 | each entry has `dtype`, `shape` and a two-element `data_offsets`, all of the right JSON type | `InvalidTensorEntry` |
| 8 | the dtype string is a standard Safetensors dtype | `UnsupportedDtype` |
| 9 | each dimension is a non-negative integer at most `u32::MAX` | `InvalidShape` |
| 10 | `begin <= end <= data_len` | `InvalidRange` |
| 11 | the shape product, by `checked_mul` in `u64`, does not overflow; nor does product times element size | `Overflow` |
| 12 | `end - begin == elements * dtype.size_bytes()` | `LengthMismatch` |
| 13 | no name appears twice in one header | `DuplicateTensor` |
| 14 | no two tensors overlap | `OverlappingRanges` |

Gaps are legal and are recorded as `gap_bytes`, not refused.

### Per checkpoint

| # | Rule | Refusal |
|---|---|---|
| 15 | the root is a directory | `Io` |
| 16 | an index exists, or exactly one `*.safetensors` does, as `OpenMode` allows | `AmbiguousLayout` |
| 17 | the index is an object with a non-empty `weight_map` of string values, and `metadata.total_size`, if present, is a non-negative integer | `InvalidIndex` |
| 18 | every shard file name is a plain name inside the root | `InvalidShardPath` |
| 19 | every named shard exists | `MissingShard` |
| 20 | every shard's canonicalized path lies inside the canonicalized root | `PathEscape` |
| 21 | every `weight_map` entry appears in the header of the shard it names | `MissingTensorInShard` |
| 22 | every header tensor appears in `weight_map` | `UnindexedTensor` |
| 23 | no name appears in two shards | `DuplicateTensor` |
| 24 | the shard count fits a `ShardId(u16)` | `AmbiguousLayout` |

### Per read

| # | Rule | Refusal |
|---|---|---|
| 25 | `offset_within + len` does not overflow and does not exceed `byte_len` | `RangeOutOfBounds` |
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

```
name\tdtype\tshape\tshard_file\tdata_begin\tdata_end\n
```

per tensor in name order, with the shape as comma-separated decimals.
Two opens of the same bytes give the same digest, and the two mixed fixtures —
which differ only in whether the index declares `total_size` — give the same
digest as each other, because the catalog does not depend on that field.

## What this contract does not cover

Payload identity of a real checkpoint (Q0), dequantized values, quantized
matmul, kernel selection and residency. The first is separately authorized
later work; the second is `numerics-v1.json`; the rest are out of scope for
Slice 1.
