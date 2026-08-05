# Pulsar upstream architecture and Apple Silicon seams

This document maps upstream Pulsar before Apple Silicon implementation work.
It describes revision `183a54b` on the upstream `main` branch. The checkout was
cloned from <https://github.com/giannisanni/pulsar> with its MIT license and Git
history intact.

The audit covered the root and crate manifests, engine and CLI entry points,
all platform gates, the CUDA wrapper and build script, GGUF access, expert
streaming and caches, quantization code, tokenizer integration, model-family
dispatch (including Qwen3-MoE), and the existing tests and benchmark scripts.

## Workspace and dependency graph

```text
pulsar-serve
  -> engine
       -> kernels (CUDA FFI on Linux; empty crate elsewhere)
       -> stream  (portable plans; io_uring fetcher on Linux)
       -> quant
       -> gguf
       -> tokenizer -> gguf
  -> tokenizer
  -> gguf

pulsar-cli (in engine)
  -> engine + tokenizer + gguf through the engine crate dependencies

pulsar-quant
  -> quant -> gguf

stream -> gguf
```

The workspace is declared in `Cargo.toml:1-4`. There are no backend feature
flags today. Platform selection is done with operating-system `cfg` gates.

| Crate | Upstream responsibility | Direct workspace dependencies | Apple Silicon assessment |
| --- | --- | --- | --- |
| `gguf` | Header, metadata, tensor table, split-shard virtual offsets | none | Portable and reusable |
| `stream` | Expert read planning and Linux `io_uring`/`O_DIRECT` fetches | `gguf` | Planning is portable; fetch implementation is not |
| `kernels` | Rust wrappers around the CUDA runtime and Pulsar CUDA kernels | none | Empty on non-Linux; requires a sibling Apple backend |
| `tokenizer` | GGUF GPT-2-style byte-level BPE and chat markers/templates | `gguf` | Portable and reusable without redesign |
| `quant` | Host conversion, quantization, dequantization, and CPU dot references | `gguf` | Scalar paths are portable; x86 SIMD is optional |
| `engine` | Model loading, CUDA tensor residency, caches, all forward graphs, generation | every library crate | Entire implementation is Linux-gated and tightly coupled to `kernels::DeviceBuf` |
| `serve` | CLI server, OpenAI-compatible API, web UI, MCP support | `engine`, `gguf`, `tokenizer` | Builds a non-Linux stub today; usable after engine dispatch exists |

External dependencies are deliberately small. `kernels` uses `cc` only as a
build dependency; `stream` adds `io-uring` and `libc` only for Linux; `serve`
adds Tokio, Serde, and `rmcp`. See each `crates/*/Cargo.toml`.

## Platform gates and current non-Linux behavior

The central engine module starts at `crates/engine/src/lib.rs:16` under
`#[cfg(target_os = "linux")]` and is only re-exported at
`crates/engine/src/lib.rs:8082`. Consequently the `engine` crate is effectively
empty on macOS: this is stronger than an individual-operation stub.

`pulsar-cli` has a separate non-Linux `main` that only prints
`pulsar-cli requires Linux + CUDA` (`crates/engine/src/bin/pulsar-cli.rs:13-20`).
The server follows the same pattern (`crates/serve/src/main.rs:13-20`). The
auxiliary engine binaries and examples are similarly gated.

The CUDA build script exits immediately unless the target OS is Linux
(`crates/kernels/build.rs:1-4`). The Rust CUDA wrapper is in a Linux-only
`real` module and re-exported only there (`crates/kernels/src/lib.rs:1-5`, end
of file). This makes workspace compilation possible on macOS, but exposes no
compute API there.

`stream` keeps `Read`, expert addressing, and plan serialization portable
(`crates/stream/src/lib.rs:7-77`). Both the aligned `io_uring` runner and the
reusable fetcher are Linux-only (`crates/stream/src/lib.rs:79-404`).

## Model loading flow

1. `pulsar-cli` parses command-line options, loads an optional draft model,
   calls `Model::load`, parses the header again for the tokenizer, and creates
   `State` (`crates/engine/src/bin/pulsar-cli.rs:138-243`).
2. `parse_header` recognizes GGUF split naming, opens every shard, parses each
   header, assigns virtual base offsets, and merges tensor tables into one
   virtual file (`crates/engine/src/lib.rs:2263-2301`). Header reads start at
   32 MiB and double only when parsing reports truncation.
3. `Gguf::parse` validates magic/version/counts, parses metadata and tensor
   descriptors, and computes the aligned data-section offset without touching
   tensor payloads (`crates/gguf/src/lib.rs:264-326`). `merge_split` rewrites
   offsets into virtual-file space (`crates/gguf/src/lib.rs:328-350`).
4. `Shape::from_gguf` maps `general.architecture` into one of `Gqa`, `Mla`,
   `Dsv4`, `Qwen35`, or `K3` and resolves model metadata
   (`crates/engine/src/lib.rs:215-530`). Qwen3-MoE (`qwen3moe`) is dispatched
   to the generic GQA family at `crates/engine/src/lib.rs:234-236`; Qwen3.5/3.6
   (`qwen35moe`) uses the separate recurrent GDN family at lines 259-264.
5. `VFile` routes positional reads into the correct shard
   (`crates/engine/src/lib.rs:2480-2503`). Dense tensors are read into host
   vectors and uploaded immediately. Some f16 and K-quant dense tensors are
   requantized to Q8_0 during load, while selected K-quant weights remain in
   native form (`crates/engine/src/lib.rs:2505-2585`).
6. Routed expert tensors are not loaded wholesale. `ExpertTensor` records the
   absolute base, bytes per expert, row bytes, and quant code
   (`crates/engine/src/lib.rs:534-590`). Layer construction keeps these
   descriptors while loading router, normalization, attention, and shared
   expert weights resident (`crates/engine/src/lib.rs:3253-3350` and following).
7. `State::new`/`with_cache` allocates all CUDA activation, KV, router,
   staging, cache, and optional family-specific buffers, then opens the
   streaming store and prefetcher (`crates/engine/src/lib.rs:4163-4352`,
   `4867-5831`).

The GGUF reader tracks names requested through `tensor()` and can report
unconsumed tensors, preventing silent partial architecture loads
(`crates/gguf/src/lib.rs:363-394`). That check should remain backend-neutral.

## Decode flow

`forward_token` is a one-row wrapper around `forward_batch`; both enter
`forward_rows` (`crates/engine/src/lib.rs:5834-5869`). For the generic GQA/MLA
families, a decode step is:

1. Validate position and batch, upload token IDs, and run embedding lookup.
2. For each layer, normalize the residual stream, execute attention, apply the
   output projection and residual, normalize for FFN, execute dense or routed
   FFN, and update the residual (`crates/engine/src/lib.rs:5910-5970`,
   `6035-7300`).
3. Normalize the requested final row, run the native or Q8_0 language-model
   head, synchronize, and copy logits to the host (`crates/engine/src/lib.rs:5972-6033`).
4. Sampling remains host-side. Greedy decoding uses `argmax`; stochastic
   sampling uses a deterministic xorshift state plus temperature/top-p/min-p
   (`crates/engine/src/lib.rs:8003-8080`).

`generate_cancellable` prefills prompt chunks, then repeatedly samples and
forwards one token, with optional n-gram or MTP speculative paths
(`crates/engine/src/lib.rs:7729-8001`). The standalone CLI also supports a
simple explicit greedy loop (`crates/engine/src/bin/pulsar-cli.rs:404-491`).

`Dsv4`, `Qwen35`, and `K3` have recurrent state that must advance token by
token. `forward_rows` dispatches them to their own graphs instead of the
generic batched path (`crates/engine/src/lib.rs:5870-5889`).

## Prefill flow

The CLI divides a prompt into `State::max_batch()` chunks and calls
`forward_batch` for each (`crates/engine/src/bin/pulsar-cli.rs:404-421`). The
generic GQA and MLA graphs process a chunk as a matrix batch. Routed experts
are resolved from the union of selections across all rows, so each distinct
expert is fetched once per layer/chunk (`crates/engine/src/lib.rs:5847-5857`,
`6579-6589`). When a chunk is statistically expected to cover at least 75% of
the next layer, the prefetcher requests that whole layer; smaller chunks avoid
that cache-thrashing optimization (`crates/engine/src/lib.rs:6652-6701`).

The recurrent Dsv4, Qwen35, and K3 paths loop through tokens because their
compressor, convolution, or delta/KDA states are sequential. Their upstream
comments explicitly call these decode-only graphs even though prompt prefill
is supported by repeated single-token execution (`crates/engine/src/lib.rs:50-67`).

## Qwen3-MoE and routed expert flow

There is no standalone Qwen3-MoE source file in this revision. The
`qwen3moe` architecture is a specialization of the shared GQA graph:

- GQA attention with per-head Q/K normalization.
- No leading dense layers and no shared expert in the ordinary Qwen3-MoE case.
- A bias-free softmax router. Missing router bias is materialized as zeros;
  selected top-k probabilities are normalized (`crates/engine/src/lib.rs:234-236`,
  `349-357`, `3313-3321`).
- Routed gate/up/down tensors use the same explicit expert descriptor and
  cache machinery as the other MoE families.

The generic routed layer proceeds as follows:

1. RMS-normalize the FFN input and multiply by the resident f32 router matrix.
2. Select deterministic top-k experts and weights in a CUDA kernel. Optional
   per-expert scaling is folded into route weights
   (`crates/engine/src/lib.rs:6457-6518`).
3. Start any shared-expert branch and activation quantization before the
   blocking expert resolve, overlapping compute with storage
   (`crates/engine/src/lib.rs:6553-6577`).
4. Synchronize for router readback, copy selected IDs to the host, count
   routing choices, and predict/request the next layer where enabled
   (`crates/engine/src/lib.rs:6579-6651`).
5. Deduplicate the selected experts, map every `(layer, tensor, expert)` to an
   absolute file range, and resolve gate/up/down slabs through resident tiers,
   the device hot-set cache, host LFU cache, or disk.
6. Build explicit `ExpertPtrs` for every `(token, selected slot)`, upload that
   compact pointer table, run pair+activation and down-projection kernels, add
   any shared branch, and update the residual. Kernels do not discover or
   fetch weights themselves.

The explicit pointer contract is the most reusable upstream design property:
storage policy is resolved before compute, and a missing pointer is explicit
rather than a hidden global fallback (`docs/DESIGN-expert-store.md:17-45`).

## Expert storage and cache flow

`stream::expert_reads` derives one range per expert from a three-dimensional
`*_exps.weight` tensor. GGUF dimension zero is the row width and dimension two
is the expert index; the absolute address is `data_offset + tensor.offset +
expert * expert_bytes` (`crates/stream/src/lib.rs:14-50`). It validates tensor
shape, modeled quantization layout, and end-of-file bounds.

The Linux fetcher opens shards with `O_DIRECT`, aligns requests to 4096-byte
brackets, submits at bounded `io_uring` queue depth, and returns an owned slab
whose payload is a window into the aligned allocation
(`crates/stream/src/lib.rs:250-404`). The extra 256 bytes are intentional CUDA
phantom-tail slack and are not part of the GGUF payload.

The engine's `StreamingStore` is a budgeted host cache keyed by absolute file
offset. Entries carry frequency and last-touch counters; misses are fetched in
one batch and admitted with LFU-style eviction (`crates/engine/src/lib.rs:1037-1057`,
`1643-1800`). A separate background fetcher owns its own ring and transfers
completed slabs over channels, avoiding shared cache locks
(`crates/engine/src/lib.rs:1284-1341`).

Above host storage, `DeviceSlabCache` maintains a stable CUDA hot set with
touch-count admission, and `ExpertTier` permanently places complete hot
gate/up/down triples on other GPUs (`crates/engine/src/lib.rs:1344-1421`). Warm
census sidecars contain repeated little-endian `(offset, len, count)` triples
(`crates/engine/src/lib.rs:1380-1392`). Their format must not be changed
silently.

For Apple Silicon, the same addressing and ownership model remains useful, but
the tier names change:

- resident compressed weights in unified memory;
- mapped GGUF ranges whose pages may or may not be resident;
- cold SSD-backed pages;
- an optional, separately budgeted decoded cache.

The CUDA device cache and host cache must not both be copied literally onto a
unified-memory machine.

## Quantization

GGUF tensor layout is centralized in `TensorType::block_layout` and
`row_bytes` (`crates/gguf/src/lib.rs:44-175`). Q4_0 is 32 values in 18 bytes;
Q2_K/Q3_K/Q4_K/Q5_K/Q6_K use 256-value superblocks. Tensor sizes use row width
rather than flattening blindly (`crates/gguf/src/lib.rs:225-245`).

The `quant` crate provides portable f16/BF16 conversion, row decoding,
quantizers, and scalar reference dot products. `cpu_dot` has optional x86_64
SIMD implementations guarded by `target_arch`, with scalar alternatives
available on arm64. Existing public dequantizers include Q8_0 and Q4_K; the
tests contain independent dequant references for several other formats
(`crates/quant/src/cpu_dot.rs:207-260`, `724-790`, `793-1098`).

Q4_0 is modeled in GGUF and CUDA, but upstream does not expose a complete
portable Q4_0 row dequantizer/matvec in `quant` yet. That makes it a bounded,
high-value first Apple slice: add a strict reference decoder and compare its
matvec against known blocks before handing the dequantized values to MLX.

## CUDA-specific assumptions

- `kernels::DeviceBuf` is both the tensor handle and an ownership policy for
  CUDA allocations/pinned mappings. Engine structs store it directly.
- Device selection is mutable process/thread state (`set_device`/`get_device`).
- Dense, attention, routing, MoE, residual, sampling-transfer, copy-stream,
  event, and graph operations are all expressed as free functions in
  `kernels`, not behind a trait.
- Dense paths often assume Q8_0 weights and Q8_K activations; model loading may
  requantize to satisfy those kernel contracts.
- Routed execution depends on raw device pointers and CUDA-addressable staging
  arenas. Multi-GPU tiers depend on explicit cross-device copies.
- Router IDs are copied back to the CPU before storage resolution. This is a
  synchronization boundary and should remain visible in an initial MLX path.
- CUDA allocation headroom, PCIe bandwidth, pinned host memory, and separate
  VRAM budgets drive many upstream heuristics. Those numbers are not valid for
  unified memory.
- The kernel build uses `nvcc`, CUDA architecture fatbins, `cudart`, per-thread
  default streams, and Linux library paths (`crates/kernels/build.rs`).

## Linux-specific assumptions

- The complete engine and serving implementations are gated by Linux rather
  than a CUDA feature/backend capability.
- Expert misses require `io_uring`, `O_DIRECT`, Unix positional reads, and
  4096-byte aligned allocations.
- Default host-cache sizing reads `MemAvailable` from `/proc/meminfo`
  (`crates/engine/src/lib.rs:4352-4377`). Benchmark scripts read
  `/proc/loadavg` (`scripts/bench.sh:28-31`).
- CUDA discovery, `/usr/local/cuda/lib64`, `nvidia-smi`, and Linux shell scripts
  are assumed in production setup and benchmarks.
- The current stream API exposes Linux-only concrete `Fetcher` and `Slab`
  types to the engine, so simply adding a macOS module will not compile the
  current engine unchanged.

## Reusable components

The following should remain shared and behaviorally unchanged:

- GGUF parsing, split-shard virtual offsets, tensor naming and byte-layout
  interpretation;
- tokenizer, chat marker/template handling, and token byte decoding;
- shape metadata rules and architecture identification where they do not call
  backend APIs;
- expert absolute-range calculation and plan serialization;
- host scalar quantization/dequantization references;
- deterministic sampler and host correctness/reporting formats;
- warm census reader/writer format;
- CLI flags for logits dumping, teacher forcing, decode consistency, and
  deterministic seeds.

## Required abstraction seams

The smallest safe bring-up does not require making every CUDA call generic.
The initial seams should be coarse and additive:

1. **Backend selection and capabilities.** A portable `BackendKind` and
   capability report should select CUDA on the existing Linux path and MLX on
   Apple Silicon. Existing default Linux behavior must not change.
2. **Model-relevant compute interface.** An Apple backend should expose owned
   tensor handles plus coarse operations: upload/allocate/readback, embedding,
   RMS normalization, dense/quantized matmul, attention, router/top-k,
   grouped expert FFN, residual, and logits transfer. Do not encode CUDA
   streams, raw pointers, or graph capture in the common contract.
3. **Portable expert source.** Keep `stream::Read` and absolute offsets common,
   then add a bounded positional/mapped reader with owned payloads and metrics.
   CUDA `stream::fetch::Fetcher` remains intact.
4. **Apple-specific vertical graph.** Start with a small MLX backend module and
   synthetic Qwen3-MoE layer rather than refactoring the 8,000-line CUDA engine
   wholesale. Once operations execute, shared shape/loading logic can be
   extracted incrementally with parity tests.
5. **Explicit process boundary if Python MLX is selected.** A worker must have
   a versioned framed protocol, shape/dtype validation, bounded request sizes,
   controlled lifetime, and structured errors. Shelling out once per operation
   is not an acceptable seam.

## Risks and unknowns

- **Integration route:** upstream Apple MLX may be consumed through native
  bindings or a Python worker. The first smoke proof must decide this based on
  build reliability and must confirm the selected MLX device, not infer GPU use
  from successful arithmetic.
- **Engine extraction size:** CUDA types are stored throughout `Model`,
  `LayerW`, and `State`. A global trait conversion would be broad and risky;
  a parallel Apple graph is safer until operation contracts are proven.
- **Tensor orientation:** GGUF dimensions are fastest-varying first, while MLX
  arrays use conventional row-major shapes. Every projection needs fixture
  evidence against a scalar reference to avoid plausible transposition errors.
- **Quantized tails:** GGUF `row_bytes` rounds up partial blocks, while several
  upstream paths assume widths divisible by 32 or 256. Odd-dimension behavior
  must be specified and tested rather than inherited accidentally.
- **Mapped-memory semantics:** it is unknown whether the chosen MLX bridge can
  alias mapped CPU storage. Until measured, documentation must assume an MLX
  allocation/copy.
- **Unified-memory accounting:** resident compressed bytes, mapped virtual
  bytes, resident pages, decoded arrays, and temporary MLX allocations are
  different quantities. Metrics and conservative budgets must keep them
  separate.
- **Memory pressure:** macOS has no `/proc/meminfo`; physical memory alone is
  insufficient. Defaults need a substantial headroom reserve and should react
  conservatively to pressure/available-memory evidence.
- **Router tie-breaking:** deterministic top-k ordering must match the trusted
  reference, including exact ties. A generic sort without an explicit index
  tie rule is insufficient.
- **Qwen naming drift:** current upstream supports both Qwen3-MoE and newer
  Qwen3.5/3.6 hybrids. The first real fixture should target `qwen3moe`; the GDN
  hybrid is a separate milestone, not an automatic consequence.
- **No model fixture is present:** real-model claims require a legally
  accessible, reasonably small GGUF or a checked-in metadata/weight fixture.
  Synthetic MoE evidence must be labeled synthetic.
- **Short reads are not rejected:** the Linux fetcher checks only negative
  completion results, not whether the returned byte count equals the submitted
  aligned length (`crates/stream/src/lib.rs:369-399`). A truncated read may
  therefore expose an incomplete payload. The portable path must require exact
  lengths and the Linux path should be hardened without changing successful
  behavior.
- **Error cleanup can outlive buffers:** `fetch_each` may return on one failed
  completion while other submitted reads still reference allocations owned by
  its local pending list (`crates/stream/src/lib.rs:354-399`). Any cleanup fix
  must drain or cancel outstanding operations before dropping buffers.
- **Alignment ownership is underspecified:** `Aligned::new` accepts an
  arbitrary alignment, while `Drop` reconstructs a 4096-aligned layout
  (`crates/stream/src/lib.rs:115-145`). The allocation must retain its actual
  layout.
- **Virtual-file routing lacks range proof:** current routing finds a shard by
  start offset but does not reject below-base, beyond-end, or straddling reads.
  Apple storage tests need explicit shard boundaries and exact-range errors.
- **Host budgets and determinism are soft:** cache admission compares payload
  lengths but accounts aligned slab capacity, and LFU victim selection depends
  on randomized `HashMap` iteration. The Apple resident/decoded budgets must be
  hard caps with deterministic tie-breaking.
- **Malformed quant input can be truncated silently:** several quant routines
  use `chunks_exact` and debug assertions, so release builds may ignore partial
  blocks. New public reference and MLX entry points must validate byte count,
  dimensions, and block divisibility before decoding.
- **CUDA regression testing:** this host cannot execute CUDA. Structural Linux
  checks can preserve cfg/dependency shape, but final CUDA runtime parity still
  requires supported hardware or upstream CI.

This map is the boundary for the bring-up: implementation will proceed in
small executable slices, preserving the Linux/CUDA modules and formats rather
than replacing them globally.
