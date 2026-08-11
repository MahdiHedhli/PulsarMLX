# Feature 017 canonical real-checkpoint runner gap analysis

Status: implementation input; no real-checkpoint runner exists at the reviewed
source boundary.

Reviewed source: `a4b08e192e7b7b11549fda7602cc34e153e565fe`

This review maps the existing Feature 017 foundation to the minimum work needed
for an independently executable GLM-5.2 P1. It does not promote the existing
checkpoint-free fixtures, Linux/CUDA engine, or Python research oracle into a
Rust-native inference claim.

## Executive gap

The branch contains backend-neutral runtime traits, deterministic positional
I/O, residency and lifecycle models, exact Rust decoder lanes, a narrow native
MLX ownership adapter, and independent checkpoint-free semantic fixtures. It
does not contain an executable which composes those pieces into a real
GLM-5.2 forward pass. `MlxContext` is used only by the adapter tests, and the
current native adapter can import one-dimensional f32 storage, add an array to
itself, evaluate, synchronize, and expose ownership counters. It cannot yet
perform the projections or elementwise graph required by GLM-5.2.

The Linux/CUDA `pulsar-cli` is not an acceptable shortcut. The Python/NumPy/MLX
implementation remains the independent semantic oracle and is not an
execution engine for this runner.

## A. Checkpoint layer

### Present

- `gguf::Gguf` parses versioned metadata and tensor tables without touching
  tensor payloads.
- `gguf::Gguf::merge_split` can represent a merged logical split once callers
  have parsed the shards and supplied their logical bases.
- `gguf::split_shard_names` and `split_shards` recognize conventional shard
  names.
- `stream::PositionalSource` supports bounded exact positional reads,
  multi-shard ranges, overflow rejection, short-read rejection, cancellation,
  whole-matrix reads, and request/byte telemetry.
- `backend::TensorCatalog`, `TensorStore`, `RuntimeTensor`, and `TensorRange`
  define portable lookup/read contracts.
- Feature 016 retains public-safe catalog, checkpoint binding, tensor ranges,
  dimensions, and quantization evidence for the admitted six-shard checkpoint.

### Missing

- A versioned runner checkpoint-manifest parser binding exactly six filenames,
  sizes, per-shard SHA-256 values, immutable revision, checkpoint-set hash,
  catalog identity, and symbolic public paths.
- A production composition that parses every shard, verifies its identity,
  computes safe logical bases, rejects duplicate or ambiguous tensor names,
  and implements both `TensorCatalog` and `TensorStore`.
- Explicit separation between identity-only header/catalog access and tensor
  payload execution.
- Atomic checkpoint identity evidence and public-path sanitization.
- A tiny multi-shard GGUF fixture that exercises tensors crossing logical
  shards through the actual runner binary.

Exact token IDs make tokenizer execution unnecessary for P1, but the evidence
must still identify the frozen tokenizer/chat-template contract and record that
the input was supplied as token IDs rather than retokenized.

## B. Architecture layer

### Present

- `backend::Glm52Plugin` is an architecture identifier only.
- Feature 017 independent fixtures cover isolated projection, router, expert,
  top-8 plus shared aggregation, MLA/dense, complete-layer, and final
  norm/logits/top-k semantics.
- Feature 016 freezes the Python oracle semantics and actual `glm-dsa` tensor
  catalog. Its research path identifies the residual order, RMS normalization,
  MLA projections, DSA indexer, sigmoid router plus bias, top-8 normalization,
  routed experts, separate shared expert, final norm, and output head.
- The inherited Linux engine contains a GLM/MLA shape description and useful
  tensor-loading precedent, but is compiled inside a Linux-only CUDA runtime
  and is not a portable F017 implementation.

### Missing

- A validated architecture contract requiring `glm-dsa`, 79 layers, 256
  routed experts, top-8 routing, one shared expert, and the exact admitted
  dimensions and metadata values.
- A complete, prevalidated tensor-name map for:
  `token_embd.weight`, per-layer attention and FFN norms, MLA q/kv/k/v/output
  projections, DSA/indexer tensors, dense layer-0/1/2 gate/up/down tensors,
  layer-3..78 router/bias/routed/shared expert tensors, `output_norm.weight`,
  and `output.weight`.
- Native embedding lookup, RMSNorm, MLA state transition, rotary behavior,
  DSA/indexer selection, sigmoid router, stable top-8 tie-breaking and
  normalization, SwiGLU expert execution, residual ordering, final norm,
  logits, and argmax composition.
- A runtime-level proof that the implementation reaches all 79 layers and 76
  MoE layers rather than replaying disconnected fixtures.

No tensor name may be guessed during execution. The map must be fully
constructed and validated before the first weight operation.

## C. Backend layer

### Present

- `stream::MlxContext` provides process-wide singleton acquisition, CPU/GPU
  selection, default or owned stream selection, managed f32 import, explicit
  evaluation/synchronization, one derived `add_self` operation, pointer
  inspection, and ownership/stream accounting.
- The Objective-C++ adapter owns native handles behind a narrow C ABI and has
  fail-closed validation, shape limits, exactly-once callbacks, and tested
  source-first/derived-later teardown.
- Stable Metal-visible slab registration is separately qualified; it is not
  treated as evidence that the MLX C import is copy-free.

### Missing MLX operation surface

- shaped f32 array construction and safe multidimensional views;
- matrix-vector or matrix-matrix multiplication;
- elementwise add, multiply, sigmoid, and SiLU;
- reductions needed for RMSNorm and attention;
- softmax where retained on GPU;
- transpose/reshape/concatenate or narrowly composed equivalents required by
  MLA;
- bounded result extraction into Rust-owned storage;
- operation-level backend import/build, compute, and synchronization telemetry;
- explicit operation capability discovery and stable error codes.

Official MLX C operations behind the existing Objective-C++ boundary are the
preferred implementation. The bridge must remain narrow and typed rather than
exposing a generic `void *` MLX API.

### Deliberate CPU boundary

Rust CPU code may perform metadata/state transitions, stable top-8 selection
over 256 router values, routing normalization, and final argmax after an
explicit bounded transfer. These are candidate design choices, not implemented
capabilities. Each choice must be recorded as an explicit dispatch and must
not become a silent fallback. Large projections and expert matrix operations
belong on the production MLX path for the first P1.

## D. Runtime layer

### Present

- Backend-neutral configuration, cancellation, memory budget, tensor-store,
  layer, expert, logits, generation, telemetry, and validation contracts.
- Page-aligned stable slabs, positional I/O, inventory-derived residency
  classes, protected shared-expert policy, lifecycle generations, and
  cancellation/failure tests.
- Checkpoint-free `f017-soak` coverage of isolated semantic fixtures and
  lifecycle churn.

### Missing

- A runtime object owning exactly one `MlxContext`, checkpoint catalog/store,
  GLM tensor map, residency policy, attention/MLA/DSA state, cancellation,
  telemetry, evidence, and teardown.
- Position-zero and position-one latent/KV/indexer state transitions for the
  reviewed P1 contract.
- A fail-closed direct/native/reference dispatch policy for every operation.
- Admission collection and a fresh-process ownership-zero gate inside the
  process that will execute the model.
- Atomic progress after admission, checkpoint identity, adapter creation,
  bounded layer intervals, logits, token selection, and teardown.
- Complete post-run reconciliation of managed/derived arrays, callbacks,
  streams, context singleton, registrations, in-flight work, generations, and
  owner tokens.
- An interruption record which can never be rewritten into a passing result.

## E. Executable layer

### Present

- `f017-soak` is a checkpoint-free fixture exerciser.
- `pulsar-cli` is the inherited Linux/CUDA executable.
- The `pulsar-mlx` research worker is scoped to the earlier Qwen validation
  protocol and does not implement the GLM-5.2 F017 runtime.

### Missing

- A canonical `f017-glm52-runner` executable using the production adapter.
- Strict parsing for checkpoint manifest, exact tokens, new-token count,
  evidence output, validation mode, stream mode, memory floor, environment
  manifest, expected token, and mode flags.
- Mutually exclusive `--dry-run`, `--adapter-preflight-only`,
  `--checkpoint-identity-only`, and `--fixture-mode` paths sharing the same
  admission, evidence, and exit-class machinery.
- Versioned evidence schema, duplicate-key rejection, atomic JSON output,
  privacy normalization, and deterministic schema tests.
- Stable exit classes for success, admission/environment, checkpoint identity,
  lifecycle/ownership, numerical/behavioral, infrastructure/evidence, and
  cancellation.
- A literal reviewed P1 command. One cannot be documented until the real
  execution path and local-only boundary ladder pass.

## Required implementation ladder

| Gate | Current state | Required proof |
| --- | --- | --- |
| R0 process/CLI/evidence | Missing | Binary rejects unknown/inconsistent options and emits a versioned atomic result. |
| R1 environment/adapter | Adapter tests only | Same runner process records preflight, zero state, operation capability, and teardown. |
| R2 fake multi-shard manifest | Missing | Tiny deterministic split fixture and identity failure tests. |
| R3 GGUF catalog | Parser exists | Runner parses and validates the fake multi-shard catalog. |
| R4 tensor range/hash | Positional API exists | Exact range/read/hash through runner store. |
| R5 real-shaped projection fixture | CPU fixture exists | Production adapter projection with independent expected output. |
| R6 router | CPU fixture exists | Native projection plus stable Rust routing boundary. |
| R7 complete expert | CPU fixture exists | Native gate/up/down path and independent comparison. |
| R8 top-8 plus shared | CPU fixture exists | Real dispatch/accounting/residency composition. |
| R9 MLA/dense | CPU fixture exists | Native stateful attention boundary. |
| R10 complete layer | CPU fixture exists | One composed runtime layer. |
| R11 final output | CPU fixture exists | Final norm/logits/top-k and expected argmax. |
| R12 tiny end to end | Missing | Actual binary executes a synthetic multi-layer model through its real components. |
| R13 local-only real fixtures | Missing | Hash-bound embedding, early/middle/final layer and logits boundaries. |
| R14 M1 identity-only | Blocked on runner | Reviewed command verifies the admitted six-shard checkpoint without weight execution. |
| R15 one P1 | Not authorized | Fresh reviewed source, environment, resource, and model-time admission. |

## First implementation boundary

The first safe vertical slice is R0 through R4: strict CLI, versioned evidence
and failure classes, fake split-manifest/catalog storage, and exact bounded
tensor reads. R1 may then bind the existing adapter preflight into the same
executable. R5 is blocked until the typed MLX projection operation exists.

The branch is not P1-ready until R0 through R14 are independently reviewed.
Creating a binary name or printing a canonical-looking command does not close
that gate.
