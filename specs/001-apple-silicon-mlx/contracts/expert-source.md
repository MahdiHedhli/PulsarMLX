# Contract: Portable Exact Expert Source

**Status**: Proposed for implementation

**Owner**: `crates/stream`

**Compatibility rule**: additive; inherited Linux fetch APIs remain intact

## Purpose

Provide backend-neutral, exact, owned byte payloads from one or more logical
GGUF shards without requiring `io_uring`, `O_DIRECT`, CUDA-addressable memory,
or MLX arrays. The source deals in byte ranges. Model-specific expert topology
stays in the model/expert directory and is associated by request order or a
separate semantic key.

## Proposed Rust surface

The existing public `stream::Read { offset: u64, len: u64 }` remains the range
type. The additive surface is equivalent to:

```rust
pub struct ShardPath {
    pub base: u64,
    pub path: PathBuf,
}

pub struct OwnedSlab {
    range: Read,
    bytes: Box<[u8]>,
}

impl OwnedSlab {
    pub fn range(&self) -> Read;
    pub fn payload(&self) -> &[u8];
}

pub trait ExpertSource: Send {
    fn fetch_exact(&mut self, read: Read) -> Result<OwnedSlab, SourceError>;
    fn fetch_batch(&mut self, reads: &[Read])
        -> Result<Vec<OwnedSlab>, SourceError>;
}

pub struct PositionalSource { /* opened handles and validated layout */ }

impl PositionalSource {
    pub fn open(path: &Path) -> Result<Self, SourceError>;
    pub fn open_split(shards: &[ShardPath]) -> Result<Self, SourceError>;
}
```

Exact names may change during implementation review, but the ownership, range,
ordering, validation, and error semantics in this document are normative.

## Construction invariants

1. Open every file once and retain the handles.
2. Snapshot lengths from those opened handles.
3. Require at least one shard and reject zero-length shards.
4. Require bases to be strictly increasing and all adjacent ranges contiguous.
5. Compute each half-open end with checked `base + file_length`.
6. Reject duplicates, descending bases, gaps, overlaps, and overflow.
7. A generic split layout may start at a nonzero base; GGUF model construction
   requires the first base to be zero.

Construction failure returns no usable source.

## Exact read semantics

- A request denotes `[offset, offset + len)` in the logical byte space.
- `len` must be nonzero and must convert to the allocation size without loss.
- Validate checked end, below-base, beyond-end, and single-shard containment
  before allocating or issuing I/O.
- A request ending exactly at a shard end is valid.
- A request starting exactly at the next shard base is valid.
- A request crossing a boundary by one or more bytes is `StraddlesShard`; the
  source does not concatenate shards.
- Positional I/O loops until all logical bytes are returned, retries
  `Interrupted`, and advances by the actual byte count.
- A zero read before completion is `ShortRead` with expected and accumulated
  counts. A partial payload is never returned as success.
- `OwnedSlab::payload().len()` equals the requested logical length exactly.
- `OwnedSlab` owns its data, is non-`Clone` by default, and remains valid after
  the source is dropped or the payload is moved to another thread.

## Batch semantics

- Output index `i` corresponds to input index `i`, including duplicate ranges.
- The operation is all-or-error: it returns no partially successful vector.
- Validation of the complete batch precedes payload I/O where practical.
- Implementation concurrency is not part of the semantic contract.
- Cancellation or error cannot free a buffer that an admitted I/O operation can
  still access.

## Structured errors

The public error must distinguish at least:

```text
EmptyShardSet
ZeroLengthShard { shard }
UnsortedShards { previous, shard }
ShardGap { previous_end, next_base }
ShardOverlap { previous_end, next_base }
LayoutOverflow { shard, base, len }
ZeroLengthRead { offset }
RangeOverflow { offset, len }
BelowBase { offset, first_base }
BeyondEnd { offset, len, virtual_end }
StraddlesShard { offset, len, shard_end }
LengthTooLarge { len }
DestinationLength { expected, actual }
ShortRead { shard, local_offset, expected, actual }
Io { operation, shard, local_offset, source }
```

Errors used in committed evidence sanitize private absolute paths while keeping
a stable shard index or fixture identity. The underlying `io::Error` remains
available to local callers.

## Optional mapping implementation

mmap is not required for the reference source. If later added, it satisfies the
same test suite and initially copies a validated range into `OwnedSlab`. Any
zero-copy variant requires an owned mapping lease that outlives every view,
page-aligned mapping arithmetic, validation against the snapshotted physical
extent, and a separately proved MLX ownership/aliasing contract.

Mapped virtual bytes and sampled resident pages are reported separately.
Residency is an instantaneous observation, not private process ownership or a
guarantee that pages remain resident.

## Linux preservation

Initial Apple work does not change:

- existing `#[cfg(target_os = "linux")]` boundaries;
- `stream::fetch::{Fetcher, Slab}` public methods;
- Linux `io-uring` and `libc` dependencies;
- `O_DIRECT`, aligned/pinned allocation, or completion callbacks;
- current engine call sites and default Linux/CUDA selection.

A future adapter may expose the existing Linux implementation through shared
semantics after Linux tests exist. A separate hardening change should verify
that an io_uring completion covers the complete logical payload; it need not
equal aligned tail bytes beyond the payload near EOF.

## Required contract tests

### Layout

- empty and zero-length shard sets;
- valid single and multiple shards;
- duplicate, descending, gapped, overlapping, and overflowing layouts.

### Range

- first and last bytes and exact shard-end reads;
- start exactly at the next shard;
- below-base and at/beyond-end requests;
- offset-plus-length and allocation-size overflow;
- one-byte straddle rejection; and
- proof that invalid requests issue no read or allocation through an injected
  test double.

### I/O and ownership

- deterministic bytes from two temporary shards;
- partial-read loop, `Interrupted` retry, and zero-before-complete behavior;
- file truncation after open produces `ShortRead`;
- batch order, duplicates, and all-or-error behavior; and
- payload validity after source drop and thread move.

### Optional mapping and Linux adapter

- identical contract suite for every source implementation;
- mapping owner lifetime and page rounding, without deterministic residency
  assertions;
- Linux byte parity and out-of-order completion mapping;
- payload-covered versus payload-short completion cases; and
- explicit skip reporting when a filesystem cannot support `O_DIRECT`.
