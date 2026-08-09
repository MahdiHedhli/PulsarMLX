# Rust Exact-Decode Boundary

**Status**: accepted Feature 016 design; implementation deferred to Feature 017

**Scope**: whole-slab positional read and exact f32 dequantization

**Non-scope**: Rust inference orchestration, direct quantized Metal, or a new performance claim

## Purpose

The first native boundary moves checkpoint reads and reference-compatible f32
dequantization into Rust without changing model semantics. It must produce the
same observable decoded f32 bits as the committed scalar Python decoder for an
admitted format, including signed zero. Python/NumPy remains an independent
oracle and fixture producer; the shipping path must not require Python.

This boundary is transitional. It supplies contiguous native f32 storage to the
existing MLX path while the longer-term direct-quantized Metal path keeps
compressed weights compressed through compute.

## Contract

### Request

A request is immutable after admission and contains:

- checkpoint set SHA-256 and immutable revision;
- shard identity from the validated catalog, never an unchecked path string;
- tensor name, quantization type, logical shape, file offset, compressed byte
  length, and decoded element count;
- an explicit decoder contract version;
- cancellation token and public-safe correlation identifier;
- destination policy: caller-provided aligned storage or Rust-owned storage.

The implementation resolves the catalog entry again and rejects any mismatch
before I/O. Arithmetic for offsets, lengths, shapes, block counts, and output
sizes is checked. Unsupported formats fail closed; there is no format guessing
or CPU/MLX fallback hidden behind the interface.

### Read

Rust opens admitted shard handles under the checkpoint store and performs a
bounded whole-slab positional read (`pread`-equivalent or `FileExt::read_at` in
a completion loop). Short reads, EOF, file replacement, or identity changes are
errors. The reader does not mutate the process file cursor and does not expose
private paths in telemetry.

The first implementation may copy compressed bytes into a Rust-owned aligned
buffer. A later page-aligned slot pool may remove that copy, but it cannot
change the decode contract. Alignment is recorded rather than assumed. The
minimum alignment is selected for the consumer API and tested on Apple arm64;
Metal page alignment is not claimed by this f32 boundary.

### Exact f32 decode

For a supported quantization, output must match the committed scalar Python
reference element-for-element under `f32::to_bits()`:

- all finite values have identical IEEE-754 binary32 bits;
- positive and negative zero are distinct and preserved;
- block, scale, grid, sign, and lane ordering are identical;
- conversion and multiplication points follow the frozen reference order;
- NaN or infinity in malformed source metadata is rejected rather than
  canonicalized;
- no fast-math, fused operation, alternate rounding mode, activation
  requantization, or Q8_K substitution is permitted in exact mode.

The x86 AVX2 IQ2_XXS `cpu_dot` path in `crates/quant` quantizes activations to
Q8_K and has different semantics. Its throughput and numerical behavior are
not evidence for this Apple f32-decode boundary.

The initial format set is deliberately small: only decoders with committed
Python exact-bit fixtures are admitted. Mixed-quant dispatch maps an explicit
GGUF quantization enum to a versioned decoder. A missing decoder returns
`UnsupportedQuantization`; it never routes to a numerically different kernel.

### Output ownership and lifetime

The primary result is an owned, contiguous, initialized f32 buffer plus its
shape, byte length, alignment, decoder version, and content SHA-256. Rust owns
allocation and deallocation. Any foreign consumer receives an opaque owner
handle and a read-only pointer/length view. The view remains valid until the
owner handle is released; releasing while a consumer evaluation is in flight
is prevented by reference-counted ownership or an explicit completion fence.

Caller-provided storage is optional and accepted only when its size, alignment,
mutability, and exclusive lifetime are proven by the boundary. Uninitialized
or partially decoded output is never returned. Cancellation or decode failure
zeroizes no model weights—it simply drops the uncommitted buffer—and returns no
success handle.

## Error model

The interface returns structured errors suitable for recovery and telemetry:

| Error | Meaning | Recovery |
| --- | --- | --- |
| `IdentityMismatch` | checkpoint, revision, shard, or catalog entry changed | invalidate store; require readmission |
| `InvalidRange` | offset/length/shape arithmetic is invalid | reject request; programming or corrupt-catalog fault |
| `ShortRead` | the exact compressed slab was not read | close/reopen shard; retry only under same identity |
| `MalformedBlock` | byte length or encoded block is invalid | reject tensor; preserve bounded diagnostic |
| `UnsupportedQuantization` | no exact decoder exists | retain Python/reference or supported fallback explicitly |
| `Cancelled` | cancellation observed at a safe boundary | discard partial output; no cache admission |
| `AllocationDenied` | admission or allocation would breach budget | release transient state; report recoverably |
| `ConsumerFailure` | MLX/native consumer rejected the result | release after fence; retain stage telemetry |

Errors contain symbolic shard/tensor identities and bounded numeric context,
never usernames, home paths, model URLs, tokens, or raw weight bytes.

## Cancellation and crash recovery

Cancellation is checked before read, after read, between bounded decode chunks,
before publication of the result, and while waiting on a consumer fence.
Published buffers have a single owner record; cache admission is atomic only
after full decode and optional hash verification. A cancelled or crashed worker
cannot leave a partially valid cache entry.

Persistent state contains checkpoint/catalog identity and cache metadata, not
decoded f32 payloads. On restart, orphaned temporary allocations disappear with
the process and resident entries are reconstructed only from validated
compressed checkpoint data. If a future shared-memory bridge is used, it needs
generation-tagged handles and startup reclamation before admission.

## Telemetry

Every successful or failed request records monotonic stage timings separately:

- positional read and compressed bytes read;
- allocation and contiguous-buffer preparation;
- decode, decoded bytes, and format;
- optional exact-bit/hash validation;
- bridge handoff and consumer build/evaluation;
- MLX matvec where the consumer exposes it;
- cancellation wait and cleanup;
- current/peak resident memory and admission outcome.

Counters remain cumulative and reset only through an explicit new collector
generation. Evidence differencing must reject a generation change. Tensor and
checkpoint identities are symbolic and hash-bound; telemetry never contains
absolute local paths.

## Python differential gate

Before a Rust decoder is admitted, tests must compare it with the scalar Python
oracle without calling the implementation under test from the oracle:

1. randomized synthetic blocks, malformed/truncated/overlong inputs, and signed
   zero cases;
2. real rows from multiple shards and layers;
3. complete real matrices and decoded content hashes;
4. at least ten deterministic repeats for correctness-sensitive boundaries;
5. exact `uint32`/`to_bits` comparison with mismatch count and first mismatch;
6. matrix → MLX build/eval → matvec comparison against the existing reference;
7. bounded allocation, RSS, read, decode, and handoff measurements.

Fixtures commit manifests, shapes, offsets, quantization, and hashes, not model
weights unless redistribution is independently permitted. Any tolerance-based
consumer comparison is a separate numerical gate and cannot replace exact
decoded-bit equality.

## Bridge evaluation

| Option | Copies and lifetime | Product fit | Decision |
| --- | --- | --- | --- |
| Subprocess worker | serialization or shared-memory protocol; simple crash boundary | useful diagnostic and differential harness, poor ordinary-inference boundary | retain for research/debug, not primary shipping path |
| PyO3 extension | can expose Rust-owned buffers to NumPy with careful capsules; Python owns process orchestration | efficient research integration but violates no-required-Python product rule | optional oracle adapter only |
| C ABI | opaque owner handle plus pointer/length; explicit release/fence contract | stable narrow boundary for Rust, Objective-C++, and MLX adapters | preferred lowest-level ownership ABI |
| Official MLX C API bridge | potential direct construction from native buffers; exact ownership behavior must be qualified | best candidate for current dense MLX operations without Python | preferred consumer when supported APIs and lifetime tests pass |
| C++/Objective-C++ adapter over the C ABI | one Apple-specific compilation boundary; can own MLX/Metal completion fences | appropriate narrow platform component | acceptable Apple adapter; keep policy in Rust |

The implementation should first use Rust-owned contiguous memory and the
narrowest MLX C/native bridge that can prove lifetime and synchronization. It
must measure copies rather than describe a handoff as zero-copy by assumption.
PyO3 can accelerate differential testing but is not the product architecture.
A subprocess worker remains valuable for isolation and minimal reproductions.

## Feature 017 entry gate

Feature 017 may implement this design only after it freezes:

- supported format/version list and exact Python fixtures;
- Rust request/result/error ABI;
- allocator alignment and lifetime tests;
- checkpoint-store identity and positional-read behavior;
- cancellation and cache-publication state machine;
- bridge copy-count and synchronization experiment;
- rollback to the committed Python/MLX reference path.

Direct quantized Metal kernels are not part of this exact-f32 milestone. Their
first target remains undecided until trunk fixtures close the material warm
residual measured by Feature 016.
