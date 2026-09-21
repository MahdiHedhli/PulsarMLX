# GLM53-Flash synthetic quantized bundle and store contract

Status: predeclared contract, source-derivation addendum frozen before candidate execution or generated fixture output. The exact earlier bytes are retained externally under SHA-256 `8275db4f80677c76633ed641fe4229739861e4376b4c65cdfa61c764f01d272d`; this addendum changes no equation, case, or acceptance threshold.

## Scope and evidence boundary

This contract covers a standard-library-only, synchronous research harness for fictional affine-quantized tensors. It does not read model weights or safetensors headers, run MLX or GPU code, or define a production loader. Physical I/O is `NOT_MEASURABLE`; native mapping and unmapping are `NOT_EXERCISED`.

The source identities used as design evidence are:

- MLX v0.32.0 commit `7a1d4f5c12ac82f4b4d0a6e71538d89ca0605247`, retained `mlx/backend/common/quantized.h` SHA-256 `e5bfbb9a3d2459b3dab6e50c90c1d7a22b55ac84e372e1dc22ef9429f872d4a7`, `python/mlx/nn/layers/quantized.py` SHA-256 `e6c34d65bfb9f1c6f35ade3b3c7c021693c60afa31eea922a78ddceca96b3f37`, and `mlx/backend/metal/kernels/quantized.h` SHA-256 `4da52bf4ee688165a65b84c52a5f4e82efcae7f69e8c74d9ee3e00bef463c99f` (Git blob `345dfc711ee89bcf7f110652b0e8513a0eb2ca68`). The kernel source was acquired as text through the authenticated contents API at that exact revision; its adjacent source-identity record has SHA-256 `2bb3f6556b6bff87bc38a39122c223f090a0d3e10419142496f3d4361e2b0fd2`.
- PulsarMLX R001 repack source commit `3ad39ec92ab77cf77263dfe2b6f26826caf0794a`, file `crates/repack/src/lib.rs`, used only as a design reference for ordered components, checked ranges, padding exclusion, and deterministic identities.

The corrected source lock is `pulsarmlx.glm53_flash.model_map_sources.v1`, whose corrected file SHA-256 is `f7708546c13ea90fc0a4abc0f3152f596f3d8818eae87bc75b3f05e8490f6f11`. These identities pin observed source evidence only. They do not identify the selected artifact's producer environment.

The retained common header defines the power-of-two packing factor, and `QuantizedLinear` exposes the packed last-axis relation `(packed_last * 32) // bits`. In the pinned Metal kernel, `affine_quantize` places each value with `val << (bits * (i % pack_factor))`; `affine_dequantize` recovers 4-bit fields with `(val >> (bits * i)) & 0x0f`, while its 8-bit case uses one byte per value. The kernel also computes `gindex = oindex / group_size` and `scale * d + bias`. These exact passages establish the low-coordinate/low-bit order and affine equation used below for power-of-two 4-bit and 8-bit cases. They remain source-level encoding evidence, not proof that the selected artifact was produced by this revision or that its uninspected bytes use this layout.

## Quantization equations and bit layout

Let a tensor have logical shape `D = (d0, ..., dR-2, N)`, where `R >= 1`. Let `b` be either 4 or 8, `P = 32 / b`, `G` be the group size, and `M = 2^b - 1`.

The admitted synthetic geometry must satisfy:

```
1 <= G <= 64
G mod P = 0
N mod G = 0
product(D) <= 65,536
```

The fixtures deliberately include group sizes 8 and 16 to exercise grouping independently at tiny sizes, plus group size 64 cases. The pinned Metal `affine_quantize` kernel has the stronger source constraint `group_size % 32 == 0`; therefore group-8/group-16 results are fictional format stress cases and do not establish support for those group sizes in MLX or a production loader.

The packed word shape is `(d0, ..., dR-2, N / P)`. Packed words are unsigned 32-bit integers serialized little-endian. The last axis is packed independently; values never cross an outer-row boundary. For logical last-axis coordinate `j`:

```
word_index(j) = floor(j / P)
shift(j)      = b * (j mod P)
q[j]          = (word[word_index(j)] >> shift(j)) & M
```

Thus the lowest logical last-axis coordinate occupies the least-significant bits. Packing is the inverse:

```
word[k] = OR over r in [0, P): (q[k*P + r] & M) << (b*r)
```

The affine metadata arrays have shape `(d0, ..., dR-2, N / G)` and are serialized as little-endian IEEE-754 binary64. For group coordinate `g = floor(j / G)`:

```
dequantize(q[j], scale[g], bias[g]) = q[j] * scale[g] + bias[g]
```

All quantized values must be integers in `[0, M]`. Every scale, bias, and decoded value must be finite. Synthetic positive fixtures use exactly representable binary fractions for scale and bias so bit-layout checks remain separate from floating-point tolerance.

## Bundle metadata and file contract

A bundle represents exactly one logical `(layer, expert)` key and exactly the roles `gate`, `up`, and `down`. Each role is one indivisible projection with packed, scales, and biases planes in one shard. The three roles may occupy different shards. Projection order is explicit and may vary, but it must list each role exactly once.

The manifest is an in-memory mapping with these exact top-level fields and no others:

```
schema             = "pulsarmlx.glm53-flash.synthetic-store.v1"
bundle             = {"layer": nonnegative integer, "expert": nonnegative integer}
alignment          = positive power-of-two integer, at most 4096
projection_order   = permutation of ["gate", "up", "down"]
projections        = list of exactly three projection descriptors
shards             = list of shard descriptors
semantic_sha256    = 64 lowercase hexadecimal characters
bundle_id          = 64 lowercase hexadecimal characters
```

Each shard descriptor has exactly `name` and `size`. Names are non-empty relative paths, contain no `.` or `..` component, and are unique. Absolute paths and symlinked roots, path components, or final shard files are rejected. A no-follow open failure with `ELOOP` or `ENOTDIR` for an intermediate or final symlink is exposed as `PathSafetyError`, and the escaped target is never opened or read. Resolution must remain beneath the admitted external fixture root. The actual regular-file size must equal the declared nonnegative size. Every shard must be referenced, and every projection shard must map to exactly one descriptor.

Each projection descriptor has exactly:

```
role       = one of gate/up/down
shape      = non-empty list of positive integers
encoding   = "mlx-affine-u32-low-bit-first-last-axis-v1"
precision  = {
  "mode": "affine",
  "bits": 4 or 8,
  "group_size": integer in [1, 64],
  "packed_dtype": "uint32-le",
  "scale_dtype": "float64-le",
  "bias_dtype": "float64-le"
}
shard      = admitted shard name
packed     = {"offset": nonnegative integer, "length": nonnegative integer}
scales     = {"offset": nonnegative integer, "length": nonnegative integer}
biases     = {"offset": nonnegative integer, "length": nonnegative integer}
```

No extra keys are accepted at any level. Numeric integer fields accept only JSON integers; booleans and floats, including integral-valued forms such as `4.0`, are rejected. In particular, `precision.bits` must be the integer `4` or `8` at manifest validation, synthetic production, and the public decode boundary. For each segment, `offset mod alignment = 0`, checked `end = offset + length` must not overflow the admitted unsigned 64-bit range, and `end <= shard.size`. All declared segments in a shard must be disjoint. Bytes outside segments are padding and must be zero.

For `outer = product(shape[:-1])`, `N = shape[-1]`, and `P = 32 / bits`, exact lengths are:

```
packed.length = outer * (N / P) * 4
scales.length = outer * (N / group_size) * 8
biases.length = outer * (N / group_size) * 8
```

Producer and consumer both enforce the geometry and length equations. Missing, duplicate, unknown, unmapped, or extra metadata is a bounded error; no defaults are supplied.

## Semantic hash and deterministic bundle identity

Canonical JSON is UTF-8 from `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)`.

The semantic hash is SHA-256 over the following byte stream:

```
ASCII "PULSARMLX-GLM53-FLASH-SYNTHETIC-SEMANTIC-V1"
one zero byte
for role in [gate, up, down]:
    uint16-le byte length of canonical semantic descriptor
    canonical semantic descriptor
    uint64-le packed byte length; exact packed bytes
    uint64-le scales byte length; exact scales bytes
    uint64-le biases byte length; exact biases bytes
```

The semantic descriptor contains exactly `role`, `shape`, `encoding`, and `precision`. It excludes shard names, offsets, shard sizes, alignment gaps, and all padding bytes. Re-layout of identical logical planes therefore preserves the semantic hash. The consumer recomputes this hash from actual exact reads and compares it with `semantic_sha256`.

The deterministic bundle identity is SHA-256 over:

```
ASCII "PULSARMLX-GLM53-FLASH-SYNTHETIC-BUNDLE-V1"
one zero byte
canonical JSON of all manifest fields except bundle_id
```

This identity intentionally commits to the logical key, precision and shapes, projection order, physical shard assignment, offsets, declared sizes, alignment, and semantic hash. Padding contents are not hashed; valid padding is constrained to zero. Identical manifest and unpadded bytes must reproduce the same identity.

## Synchronous store and telemetry contract

The demand store is synchronous and bounded. `acquire((layer, expert))` returns a consumer lease. On a cache miss, it validates metadata, reads each role in `projection_order` and each plane in `packed`, `scales`, `biases` order, verifies finite affine/dequantized values, semantic hash, and bundle identity, and only then publishes the cache entry. Unknown keys fail without a file read.

The fixture reader records telemetry at its actual read call site:

```
attempted_reads  += 1 before each positional read attempt
requested_bytes += requested length at the same point
returned_bytes  += bytes actually returned by the interface
completed_reads += 1 only when returned length equals requested length
short_reads     += 1 only when 0 <= returned length < requested length
failed_reads    += 1 when validation, path opening, range checking, or the injected interface raises before returning bytes
```

A short read raises a short-read error and is not also counted as failed. Missing files, injected disconnect/failure, incorrect ranges, and path-safety rejection at the reader call site are failed reads. Requested and returned bytes are logical interface counts only. The report always carries `physical_io = "NOT_MEASURABLE"` and `native_map_unmap = "NOT_EXERCISED"`; neither is represented by a numeric zero.

Eviction of an entry with an outstanding lease marks it pending and keeps its data readable. Releasing the last lease completes the eviction. A new acquisition during pending eviction receives a new lease on the same resident entry and postpones removal until the final release.

Preserved load state contains only exact, completed segment bytes keyed by bundle identity, role, and plane. A cancellation injected between read calls leaves completed segments in that state and publishes no cache entry. A fresh store instance may resume from the state after revalidating the manifest identity; it rereads only missing segments. State from another bundle identity, partial/short data, extra segment keys, or wrong segment lengths is rejected. Cancellation, disconnect, and restart are interface injections only; tests never disconnect or unmount a real filesystem.

## Predeclared fixtures and seeds

Fixture generation is deterministic and uses no model data. If a pseudorandom sequence is useful, it must use `random.Random` with the named integer seed; generation is otherwise closed-form.

- `layout_base_mixed`: seed `0x53A401`. Opaque fictional key `(2, 3)`, order `gate,up,down`, two shards, alignment 16. Gate is 4-bit with last axis 64, up is 8-bit with last axis 32, and down is 4-bit with last axis 16. Scale and bias values are chosen from `{0.125, 0.25, 0.5, 1.0}` and integer or half-integer biases. The layer/expert numbers identify the test record only; they do not assert that production layer 2 has an MoE expert.
- `layout_heldout_changed`: seed `0x53A402`. Key `(7, 1)`, order `down,gate,up`, three differently assigned shards and distinct outer/last-axis sizes. It uses a different 4/8 role assignment from the base case and at least one group size 64.
- `decode_literal`: no generator seed. Hard-coded little-endian words, scales, biases, and decoded outputs exercise the lowest, middle, and highest field in both 4-bit and 8-bit words. The expected decoder is implemented inside the test file and imports no candidate arithmetic helper.
- `store_faults`: seed `0x53A403`. A bounded injected reader schedule supplies one missing file, one short return, one raised failure, one bad range, one cancellation, and one simulated disconnect. No real disconnection occurs.

No fixture exceeds 256 KiB. All generated fixtures together stay below 64 MiB, task disk growth stays below 1 GiB, and each logical tensor stays at or below 65,536 elements. This store slice performs no arithmetic composition; any future bridge to composition must keep all toy composition dimensions at or below 32.

## Predeclared cases and acceptance criteria

The standard-library `unittest` suite will cover:

1. Exact 4-bit and 8-bit low-bit-first packing bytes and an independent scalar decode of `decode_literal`.
2. Base mixed-width bundle production, exact round-trip of every unpadded plane, zero padding, semantic-hash recomputation, deterministic identity replay, and candidate/independent decode agreement.
3. Held-out transfer with changed axis sizes, projection order, shard assignment, and precision allocation.
4. Semantic-hash invariance for identical logical planes under a changed valid physical layout, with a correspondingly changed physical bundle identity.
5. Rejection of nonfinite scales, biases, or decoded values.
6. Rejection of missing/duplicate/unknown roles, duplicate or unmapped shards, unknown shard references, extra keys at every metadata level, invalid precision/shape/length, overlapping or unaligned segments, arithmetic overflow, out-of-bounds ranges, wrong file sizes, nonzero padding, semantic-hash mismatch, and bundle-identity mismatch.
7. Rejection of absolute, traversal, root-symlink, component-symlink, and final-file-symlink paths without reading an escaped target.
8. Exact attempted/completed/short/failed/requested/returned telemetry for success, missing, short, raised failure, bad range, and injected disconnect cases.
9. A missing logical bundle demand miss with no read, eviction deferred under an outstanding lease, and removal after the final lease closes.
10. Injected cancellation with no cache publication, exact preserved completed state, fresh-store restart, no reread of preserved segments, successful completion, and rejection of contaminated state.
11. Exact sentinel reporting of physical I/O and native mapping status.

Integer fields, keys, role order, packed bytes, offsets, lengths, hashes, identities, state keys, telemetry counters, padding, and rejection classes require exact equality. Decoded f64 values use `abs_error <= 1e-12 + 1e-10 * abs(expected)` even though the positive fixtures are chosen to be exactly representable. Any nonfinite actual or expected value fails before tolerance comparison. No acceptance threshold may be loosened after output is observed; a necessary change requires a prospective successor contract and preservation of the failed result.

Passing these cases establishes only this declared synthetic encoding, its tiny fixture layouts, and the synchronous injected store behavior exercised here. It does not establish real-checkpoint layout, historical producer behavior, MLX kernel parity, physical I/O reduction, native map/unmap behavior, asynchronous demand loading, production cache safety, or GLM53-Flash inference correctness.
