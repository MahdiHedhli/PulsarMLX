# Apple Silicon backend design

Status: implemented and reconciled for the initial bounded bring-up. This
design document is not evidence by itself; actual capabilities resolve through
the linked validation records and retain their stated exclusions.

This document defines a correctness-first route from the inherited
Linux/CUDA implementation to an additive Apple Silicon backend. The source
audit behind the design is
[UPSTREAM_ARCHITECTURE.md](UPSTREAM_ARCHITECTURE.md). GitHub Spec Kit owns the
feature requirements and implementation plan; this document supplies the
engineering constraints, implemented seams, and remaining boundaries.

## Design rules

1. Preserve the existing Linux/CUDA build, defaults, data formats, and runtime
   behavior. An Apple path must be additive until parity evidence supports a
   narrower shared implementation.
2. Make backend-neutral contracts express model semantics, not CUDA or MLX
   mechanisms. CUDA streams, raw device pointers, graph capture, Python
   objects, and Metal command details do not belong in common interfaces.
3. Keep capabilities explicit. A backend may offer optimized quantized
   operations, mapped storage, asynchronous execution, or graph compilation
   without forcing every backend to imitate them.
4. Build one executable vertical slice at a time and compare each slice with a
   scalar or inherited reference before expanding it.
5. Do not start custom Metal kernels until the correct MLX reference path and
   its reproducible correctness measurements exist.
6. Treat documentation, error behavior, memory accounting, and benchmark
   reproduction as part of each implementation slice.

## Target boundaries

```text
model metadata, tokenizer, routing rules, sampling, validation
                              |
                    backend-neutral semantics
                   /                         \
       existing Linux/CUDA path          Apple/MLX path
       kernels + CUDA storage             MLX tensor executor
       io_uring/O_DIRECT fetcher          bounded expert source
                   \                         /
              GGUF layout, virtual offsets, quant references
```

The common layer should retain GGUF parsing, split-shard virtual offsets,
tensor naming and byte layouts, tokenizer behavior, deterministic routing and
sampling rules, expert range calculations, and portable scalar quantization
references. The inherited CUDA engine remains the authority for its own
execution policy. The first Apple graph should be a small sibling path, not a
wholesale generic rewrite of the current engine.

### Backend identity and capabilities

A portable backend descriptor should report identity, selected device,
supported dtypes and quant formats, maximum practical tensor dimensions, and
optional facilities such as asynchronous execution or direct mapped access.
Selection must be explicit and diagnosable:

- the current Linux default continues to select the inherited CUDA path;
- the Apple path selects MLX only when its runtime and intended device are
  available; and
- an unsupported request returns a structured error rather than silently
  moving to a materially different execution mode.

Capability negotiation avoids lowest-common-denominator design. Common code
asks for semantic operations; a backend-specific extension may expose an
optimization only after the caller verifies that capability. Absence of an
optimization must not change numerical meaning.

### Tensor execution contract

The initial semantic operation set is intentionally coarse:

- create or upload a typed tensor with an explicit shape and layout;
- allocate initialized or uninitialized output under a documented rule;
- synchronize and read back a tensor for validation;
- embedding lookup, RMS normalization, dense matrix multiplication, and
  residual addition;
- attention primitives needed by the selected vertical slice;
- deterministic router scoring and top-k selection;
- grouped expert gate/up/activation/down computation; and
- final projection and logits transfer when the real-model slice reaches that
  boundary.

Each operation contract must define logical dimensions, physical byte order,
accepted dtypes, accumulation dtype, output dtype, broadcasting, quant block
requirements, behavior for partial blocks, synchronization, and errors. GGUF
uses fastest-varying-first dimensions while MLX arrays use conventional array
shapes, so orientation conversions must be explicit and fixture-tested at
every projection boundary.

Owned tensor handles must not expose backend allocation details. Backend
objects own their resources and cannot outlive the backend context. Readback
is an explicit synchronization point. Research selected one persistent Python
MLX worker as the first reference mechanism. It is implemented and exercised
through focused lifecycle tests, evaluated device/tensor fixtures, and bounded
evidence commands. Its process boundary uses a versioned framed protocol with
bounded messages, shape and dtype validation, controlled shutdown, and
structured errors; spawning a process per operation is outside the contract.

### Expert storage contract

The portable storage boundary should operate on semantic keys and validated
byte ranges while retaining the existing absolute-offset model:

- an expert key identifies model shard space, layer, tensor role, and expert;
- a range carries an absolute offset and exact payload length;
- a batch request returns owned payloads matched to request keys;
- short, straddling, below-base, and beyond-end reads are errors;
- cancellation or failure cannot release buffers still used by outstanding
  I/O; and
- metrics distinguish requested bytes, mapped virtual bytes, resident pages,
  compressed payloads, decoded-cache bytes, and temporary tensor allocations.

The interface must not mention `io_uring`, `O_DIRECT`, file descriptors,
4096-byte allocations, CUDA pointers, or MLX arrays. The Linux fetcher remains
available behind its existing path. An Apple implementation may use bounded
positional reads or mapping, but mapped storage must not be described as
zero-copy into MLX until measurement proves that behavior.

Cache budgets are hard limits with deterministic eviction tie-breaking. A
unified-memory machine must not duplicate the inherited host-cache/device-cache
hierarchy mechanically: compressed residency, decoded tensors, working
buffers, and memory-pressure reserve need separate budgets.

### Quantized reference contract

Portable scalar code is the correctness oracle for the first supported
formats. A reference entry point must validate tensor type, row width, encoded
byte count, block divisibility or specified tail behavior, scales, and output
length before decoding. It must never silently discard a partial block.

The first bounded proof uses Q8_0 because the existing GGUF layout and portable
decode provide the narrowest strict reference path for the selected official
Qwen3-MoE GGUF candidate. The existing helpers still need exact byte-count,
block, error, row-decode, and matvec contracts before MLX use. Q4_0 and the
K-quant formats are deferred until a later compatible slice requires and proves
them. For each admitted format:

1. decode hand-constructed blocks with independently calculated expected
   values;
2. compare scalar matvec results with a dequantize-then-float reference;
3. execute the equivalent MLX expression; and
4. record absolute and relative tolerances by operation and dtype.

Performance numbers are invalid until the same fixtures pass these checks.

## Staged bring-up

Each stage produces a runnable command, durable output, and a focused commit.
A later stage cannot be used as evidence for an earlier stage that was never
run.

### Stage 0: preserve the baseline

Keep `cargo check --workspace --all-targets` and
`cargo test --workspace --no-fail-fast` green on macOS. Record the inherited
Linux/CUDA surface structurally and avoid unrelated formatting or Clippy
cleanup. No backend implementation begins until the pre-flight report has
been reviewed.

### Stage 1: MLX device smoke test

Implement the selected persistent Python-worker reference and test its pinned
installation, version handshake, lifecycle, message bounds, and failure
behavior. The smoke test must print the MLX version, selected device, backend
identity, input/output shapes and dtypes, and a deterministic result. Successful
import or CPU arithmetic alone is not proof of intended Apple GPU execution.

### Stage 2: tensor execution proof

Run deterministic elementwise, matrix multiplication, normalization, and
readback fixtures through the implemented tensor boundary. Compare all outputs
with independently calculated host references. This stage proves execution,
shape/orientation handling, synchronization, and error propagation without a
model loader.

### Stage 3: expert storage proof

Use a generated multi-shard fixture to validate absolute range calculation,
batch reads, exact-length enforcement, shard boundaries, deterministic cache
behavior, and memory metrics. Include forced short-read and cancellation/error
cases. Keep the existing Linux fetch implementation intact.

### Stage 4: quantized reference operations

Implement only the quantized decode and matvec operations needed by the first
model slice. Require block-level scalar fixtures, malformed-input tests, and
MLX-versus-reference comparisons before adding another format.

### Stage 5: synthetic routed MoE validation

Construct a tiny deterministic routed layer with a small token batch, explicit
router ties, a small expert count, top-k routing, and known gate/up/down
weights. Validate:

- stable expert ordering and explicit index tie-breaking;
- normalized route weights;
- deduplication and batch expert fetches;
- gate activation and down projection per selected expert;
- weighted accumulation and residual behavior; and
- peak allocations and hard storage/cache budgets.

The result must be labeled synthetic. It does not demonstrate compatibility
with a real checkpoint.

### Stage 6: bounded compatible real-model vertical slice

Select the legally accessible `qwen3moe` GGUF candidate with the lowest bounded
cost that satisfies the architecture, quantization, provenance, and memory
criteria and whose tensor types are already covered by reference tests. Record
its immutable
identity, source, license, hash, architecture metadata, tensor inventory, and
required disk/memory budget outside Git-tracked model data.

The delivered first slice is deliberately narrower than the original richer
target: it verifies immutable metadata and inventory, reads one exact
34,816-byte Q8_0 gate-projection prefix, executes 16 outputs through MLX, and
compares them with a frozen independent CPU result. It does not tokenize input,
execute checkpoint routing, resolve a routed-expert set, or complete a tensor,
expert, layer, or model. Those steps require separately specified milestones
rather than promotion from the prefix result.

### Stage 7: bounded correctness comparison

The delivered comparison covers the named 16-row intermediate against the
precommitted CPU oracle with the same weight bytes, activation, dtype, and
tolerance. The record includes hashes, versions, device identity, and errors.
Only that graph depth is verified; end-to-end inference still requires a
validated logits or token boundary.

### Stage 8: measured optimization (not run)

Establish reproducible latency, throughput, peak-memory, page-fault, and I/O
baselines. Optimize only a measured bottleneck while keeping the reference
path available. Custom Metal work requires a green MLX reference comparison,
a documented performance need, repeatable before/after measurements, and an
independent correctness test.

## Known exclusions from initial bring-up

- Replacing or broadly refactoring the inherited CUDA engine.
- Claiming Linux/CUDA runtime parity from a macOS-only check.
- Multi-GPU behavior, CUDA graph equivalence, or direct CUDA-pointer semantics.
- Qwen3.5/3.6 recurrent GDN models as an automatic consequence of Qwen3-MoE.
- MCP or production HTTP serving.
- Speculative decoding, long-context performance, and every upstream quant
  format.
- Committing model weights, converted checkpoints, tokens, or local benchmark
  output.
- Custom Metal kernels before a correct MLX reference implementation.

## Principal risks

| Risk | Required control |
| --- | --- |
| The persistent Python worker remains a bounded reference mechanism rather than a production runtime | Keep pinned installation, handshake, lifecycle, failure, and evaluated-device evidence as gates before expanding tensor or model claims. |
| CUDA objects permeate `Model`, `LayerW`, and `State` | Build an Apple vertical graph beside the current engine, then extract shared semantics incrementally. |
| GGUF/MLX orientation mismatch produces plausible values | Use nonsymmetric fixtures and compare every projection with a scalar reference. |
| Quantized tails or malformed payloads are silently truncated | Validate exact byte counts and block rules at every public boundary. |
| Mapping is mistaken for MLX zero-copy | Count mapping and MLX allocations separately until instrumentation proves aliasing. |
| Unified-memory pressure invalidates CUDA-era cache heuristics | Reserve headroom, use hard budgets, and report compressed, decoded, working, and resident-page measures separately. |
| Router ties change expert selection | Specify index tie-breaking and include exact-tie fixtures. |
| A broad abstraction changes Linux behavior | Keep Linux selection and implementations intact; require Linux/CUDA validation before shared refactors land. |
| No legal real-model fixture is available | Stop at labeled synthetic validation and record the missing fixture as a blocker. |

## Stop conditions

Stop the current milestone, preserve evidence, and do not expand scope when
any of these conditions occurs:

- the smoke test cannot identify the actual MLX device or silently falls back;
- a tensor, quantized operation, router, or MoE fixture exceeds its recorded
  numerical tolerance;
- shape, dtype, byte count, quant block, shard range, or model architecture is
  ambiguous;
- an exact storage read cannot be guaranteed, an I/O failure leaves ownership
  uncertain, or a memory budget is exceeded;
- progress requires modifying Linux/CUDA behavior without a suitable
  regression environment;
- the selected checkpoint's source, license, hash, format, or compatibility
  cannot be recorded;
- reproducible runs disagree and the source of nondeterminism is unknown; or
- an optimization proposal lacks a passing MLX reference result and measured
  bottleneck.

At a stop condition, the deliverable is the smallest reproducer, exact command
and output, affected contract, and a bounded next investigation—not a broader
unverified implementation.
