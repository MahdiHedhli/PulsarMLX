# PulsarMLX Strategy

## Mission

Run oversized sparse models correctly and usefully on Apple Silicon through
quantization, SSD-backed model storage, unified-memory residency, MLX, and
direct Metal acceleration.

Current targets are **GLM-5.3 and GLM-5.3 Flash**, with Flash leading practical
local-usability work. GLM-5.2 remains the established large-model correctness
reference. The [model-target register](MODEL_TARGETS.md) separates their evidence,
formats and hardware roles; none inherits qualification solely from a family name.

## Current direction (2026-09-23)

**This section is the current pointer for strategy and sequencing.** It
supersedes older sequencing, format-status and hardware-priority descriptions
below. Historical evidence and model-specific restrictions remain unchanged.
The concrete planned experiments, dependencies, metrics and stop rules are in
[the optimization roadmap](OPTIMIZATION_ROADMAP.md).

The consolidated mainline carries distinct tracks:

| Track | What it is | Status |
| --- | --- | --- |
| Qwen3-30B-A3B Q8_0 | the frozen Apple MLX research baseline | Verified, frozen |
| GLM-5.2 | Python/NumPy research ladder and the F017 Rust-native runtime, separately qualified | Ladder C01-C11; one native token qualified on the real checkpoint; later real positions/text are measured, not independently qualified; formal closeout remains separate ([status](../architecture/f017-native-runtime-status.md)) |
| GLM-5.3-Flash | Python/MLX paged expert-residency research | Measured candidate `971db9c1`, not the native runtime ([results](../glm53-flash/persistent-serving-results.md)) |
| F020 Slice 1 | native model-neutral Safetensors catalog/admission and MLX affine representation/decoder | Merged; qualified on synthetic fixtures only ([status](../architecture/f020-native-safetensors-status.md)) |
| F020 Slice 2B | native packed-weight primitive implementation and synthetic qualification | Reviewed preparation at [`9bf6a810`](https://github.com/MahdiHedhli/PulsarMLX/blob/9bf6a810622b7ef1156b750dd0f3140f8c0ca211/specs/020-mlx-safetensors-affine/slice2b-plan.md); merged; native MLX affine primitives, including packed-weight quantized matmul, qualified on frozen synthetic fixtures on the recorded GitHub runner; real checkpoint execution and production geometry remain unqualified ([status](../architecture/f020-native-safetensors-status.md)) |
| F020 Slice 2C | synthetic stacked-affine expert-plane selection composed with native packed-weight quantized matmul | Merged; qualified on its frozen small-fixture population on the recorded GitHub runner; real checkpoint payloads, production geometry, full expert MLPs, model execution, streaming and performance remain outside that qualification ([status](../architecture/f020-native-safetensors-status.md)) |

The Python/MLX Flash path is a behavioral and compatibility reference, not a
shipping path or an independent correctness oracle for native MLX. R1 remains
an independent scalar/binary64 or exact mathematical reference; R2 records
upstream compatibility; R3 is the native candidate. The intended shipping
runtime remains Rust-native, with no required Python inference process.

The concrete native targets are
`pipenetwork/GLM-5.3-Flash-MLX-mixed-4_8bit` first and
`pipenetwork/GLM-5.3-MLX-mixed-4_8bit` as the full-scale second architecture.
Consume their Safetensors and affine-quantized bytes without conversion to
GGUF or requantization. Keep packed weights packed into quantized matmul;
metadata widening is not permission for complete f32 weight expansion.
Neither target is native-qualified by the catalog, census or synthetic tests.

Prioritize the owned **M1 Ultra Mac Studio, 128 GB**, for practical Flash
integration and later optimization. The **M2 Max MacBook Pro, 64 GB**, remains
a subsequent, separately admitted lower-memory target. Do not require a future
hardware purchase or infer a universal full-GLM memory floor from a discussion.
Existing host/storage authorization boundaries continue to apply.

Sequence (a roadmap, not a completion claim or execution authorization):

```text
Qwen baseline + GLM-5.2 reference/native evidence + Flash paged research
  -> F020 catalog/affine representation (Slice 1 merged, synthetic-only)
  -> independent native packed-weight primitive qualification (Slice 2B)
  -> authorized real weights and production shapes, Flash first
  -> projection / selected expert / block / fixed-prefix and state correctness
  -> token-time profiling and authentic routing traces
  -> hot/cold residency and capacity curves
  -> bounded double-buffered staging / prefetch and lossless repacking experiments
  -> streamed composition correctness before generation / serving acceptance
  -> KV/prefix/hybrid-state optimization and broader hardware qualification
```

Instrumentation precedes optimization selection. Storage experiments must
first avoid unnecessary reads, then reduce the cost of unavoidable reads.
Track logical/requested bytes separately from physical I/O, measure real
read/compute overlap, and keep negative results and rollback paths. See
[OPT-01 through OPT-08](OPTIMIZATION_ROADMAP.md#concrete-work-register).

**F020 Slice 2B remains bounded to its reviewed synthetic primitive contract.**
This roadmap does not authorize payload reads, production geometry, model
graphs, residency, streaming, serving or performance runs. F017 closeout stays
separate. The older GGUF/F018 migration stages below remain design references;
they do not override the active MLX-affine target sequence.

## Current verified boundary

This section names only committed evidence. The Qwen research baseline is
frozen at [`v0.2.0-qwen30b-e2e-research`](https://github.com/MahdiHedhli/PulsarMLX/tree/v0.2.0-qwen30b-e2e-research): a real Qwen3-30B-A3B Q8_0 checkpoint was exercised through all 48 layers, full-vocabulary logits, matching greedy decode, and bounded generation. Its exact scopes and caveats remain in the [Qwen claims ledgers](../research/).

The GLM-5.2 research checkpoint is the six-shard Unsloth UD-IQ2_XXS artifact
bound by [`glm52-checkpoint.json`](../validation/glm52-checkpoint.json) and
[`glm52-revision-binding.json`](../validation/glm52-revision-binding.json):
238,458,632,928 bytes, immutable repository revision
`abc55e72527792c6e77069c99b4cb7de16fa9f23`, and set SHA-256
`d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`.
F017's later [Sequence 43 evidence](https://github.com/MahdiHedhli/PulsarMLX/blob/c23e58ec87c7e73a23cf37ac64aa4dee6c45896f/docs/architecture/reviews/evidence/f017-event06-v12-sequence43-terminal-success-evidence-v1.json)
records 79 layers in each independent oracle, matching token 154820, identical
ordered top-32 IDs and route structure, and maximum absolute error
`2.4495741151042694e-06` within the frozen contract. This is a bounded reference
correctness result, not a throughput or product-readiness claim. Exact numerical
read/mapping/fault counts remain unknown; current instrumentation cannot backfill
them. See the [publication scope](../research/f017/read-observation-publication-status.md).

The following Feature 016 records are historical authorities, not new expected-token
predicates or active-run instructions. The C01–C11 research ladder is complete and frozen at
[`v0.3.0-glm52-e2e-research`](https://github.com/MahdiHedhli/PulsarMLX/tree/v0.3.0-glm52-e2e-research), including the golden generated sequence
`[21615, 220, 16, 13, 16, 16, 15, 15]`.

Feature 016's vectorized reference path reproduced the complete frozen
sequence `[9703,21615,220,16,13,16,16,15,15]` on the MLX GPU. The deepest
committed optimization rung is the golden-eight record
[`f016-inference-golden8-iq3-0001.json`](../research/glm52/raw/f016-inference-golden8-iq3-0001.json)
at source commit `1a2ca76ee2df0f518bfc9ddbaafd31500a5e6a26`: nine complete
79-layer stacks, 1,824 decoded shared-cache hits, zero fallbacks or evictions,
and normal retained resource states. This is one bounded research correctness
and reuse run, not a tokens-per-second or production-runtime claim. Its
derived [cold/warm profile](../research/glm52/raw/f016-golden8-derived-profile-0001.json)
found a 1675.492-second median warm uninstrumented residual (87.18% median of
stack wall), while expert-cache storage averaged only 3.872 seconds (0.20%
of mean stack wall). Prefetch is deferred, and the first direct-quantized Metal
target remains undecided pending trunk-side fixture evidence. The residual is
not itself a direct trunk or cleanup measurement.

## Architectural principles

1. Correctness before performance claims.
2. Independent mathematical reference, Rust runtime; upstream compatibility is separate.
3. Compressed weights remain compressed as long as possible.
4. Storage, unified memory, and GPU form one managed hierarchy.
5. Model semantics must not change silently.
6. Every optimization must have a rollback path.
7. Measurements must separate I/O, decode, allocation, dispatch, and compute.
8. Product code must recover cleanly from interruption.
9. Donor code is qualified rather than blindly inherited.
10. No required Python process in the shipping runtime.

Independent Python, NumPy and Rust reference implementations remain the
architecture-oracle, fixture-generation, boundary-inspection and differential
testing environment. The independent numerical path may be slower, but must
remain understandable and distinct from upstream MLX compatibility comparisons.

## Runtime architecture

The planned shipping control and data plane is Rust. It is intended to own checkpoint identity, the
GGUF/Safetensors catalogs and multi-shard tensor stores, positional reads, memory admission,
compressed expert residency, cache and prefetch policy, routing, MLA/DSA state,
tokenization, generation, telemetry, cancellation, recovery, CLI, and serving.
Architecture-specific plugins provide tensor maps and model semantics rather
than leaking them into the reusable store.

Existing dense operations transition through a narrow native MLX bridge. A
small Objective-C++ adapter and Metal shader sources are expected Apple
platform components; “Rust-native” does not mean every source file is Rust.
Direct Metal is reserved for qualified compressed expert kernels. Both
deterministic validation mode and aggressively parallel performance mode are
explicit configurations with different numerical gates.

The target production expert path is:

```text
compressed checkpoint bytes on SSD
    ↓
stable page-aligned compressed expert slots
    ↓
zero-copy Metal-visible unified-memory buffers
    ↓
quantized dequantization plus matvec inside the GPU kernel
    ↓
fused gate / up / SwiGLU / down
    ↓
routing-weight application and deterministic aggregation
```

Where a qualified native quantized kernel exists, the production path avoids
materializing complete f32 expert matrices. The current NumPy decode plus f32
MLX path remains the correctness reference, transitional accelerator, fallback
for unsupported formats, and shortest route to faster full-model experiments.

## Migration plan

The practical progression is model-specific semantic mapping and synthetic
composition; independent numerical qualification; measured memory, storage,
cache and decoding behavior; then usable CLI/serving and task-level quality.
The stages below describe implementation direction, not universally shipped
capabilities or permission to run new experiments.

### Stage A: accelerated research path

- Vectorize dominant Python decoders in measured golden-trace order.
- Reach faster P1 and P2 while retaining exact golden behavior.
- Preserve scalar decoders as independent references.

### Stage B: Rust exact-decode boundary

- Perform whole-slab reads and bit-exact f32 decode in Rust.
- Produce contiguous native buffers with a low-copy handoff to MLX.
- Compare decoded f32 bits exactly against the Python reference.
- Qualify CLI worker, PyO3, C ABI, and other narrow boundaries by copies,
  lifetime safety, recovery, and measured benefit.

### Stage C: Rust-native orchestration

Move model lifecycle, routing, attention state, layer execution, logits,
generation, and telemetry into Rust. Ordinary inference no longer enters
Python. Use an MLX C API or similarly narrow native bridge for qualified dense
operations rather than recreating working kernels prematurely.

### Stage D: direct quantized Metal expert path

Implement in measured order: IQ2_XXS GEMV, IQ3_XXS GEMV, then other formats
ranked by real golden-trace cost. Each format advances through one projection,
one complete expert, top-8 plus shared block, full layer, P1, P2, and golden
eight. Numerical gates must be frozen before performance collection.

### Stage E: overlap and residency

- Use stable compressed slots and partition resident from missing experts.
- Submit resident GPU work while bounded asynchronous reads fill misses.
- Add bounded prefetch and adapt to memory pressure.
- Test Metal residency sets only if measured binding overhead warrants them.
- Use the trace-driven experiments, double-buffer ownership rules and measured
  acceptance questions in [OPT-01 through OPT-05](OPTIMIZATION_ROADMAP.md#concrete-work-register).

### Stage F: product surface

- Installable CLI with a real tokenizer and chat template.
- Streaming output, cancellation, recovery, and reproducible safe defaults.
- OpenAI-compatible serving only after the local runtime is stable.

## Correctness gates

### Exact gates

Use exact decoded f32 bit patterns, deterministic tensor hashes, exact routes,
exact greedy tokens, and signed-zero preservation when the execution contract
should remain identical.

### Numerical gates

When accumulation ordering legitimately changes, freeze and report max
absolute error, RMSE, cosine similarity, norm ratio, top-k logit agreement,
greedy-token agreement, teacher-forced position agreement, and the exact
deterministic validation configuration. A parallel nondeterministic path is
never described as bit exact.

## Multi-host development plan

### M1 Ultra Mac Studio

The 128 GB Studio owns the F017 GLM-5.2 reference and prospective instrumentation
track and is the first practical Flash native-integration/optimization host.
Later GLM-5.3/Flash evaluation, memory admission and end-to-end integration
require their own qualified boundaries and authorization.

### M2 Max MacBook Pro

The 64 GB MacBook remains the lower-memory Flash target and a development host
for source mapping and bounded synthetic work, using its authorized external
NVMe workspace. Do not inherit the Studio's cache budget or claim full-model
correctness, sustained decoding or dogfood from another host. Shared work can
include verified fixtures, decoder/Metal experiments, smaller Qwen regressions,
CLI and packaging.

The tracks share verified components and lessons without blocking each other's
day-to-day progress. Network-distributed inference is outside the roadmap.
F017 internal-SSD/RAID sequencing restrictions do not prohibit Flash's separate
external-NVMe track. This documents the arrangement, not new drive-access authority.

## Product milestone definitions

### Research prototype

The full model executes and has committed correctness evidence.

### Usable research CLI

A user can run prompts locally without manual code editing, under bounded
memory with useful progress reporting.

### Alpha

- No required Python runtime.
- Repeatable installation and checkpoint validation.
- Supported-model manifest and safe memory defaults.
- Cancellation, recovery, documented performance, and deterministic validation.

### Developer preview

Stable CLI/API, multi-model architecture boundary, reproducible benchmarks,
packaging, support policy, and clear limitations.

### Production candidate

This label requires long-context correctness, failure recovery, security,
performance stability, and cross-machine validation. None is inferred from the
current research prototype.

## Generalization boundary

Reusable runtime mechanisms are the GGUF/Safetensors catalogs, multi-shard store, storage
scheduling, caches and slab pools, telemetry, memory admission, MLX/Metal
backend contracts, CLI/server, and evidence infrastructure.

Architecture-specific plugins own the tensor map, router, expert activation,
residual graph, attention, KV/latent state, tokenizer/chat template, and output
head.

The existing GGUF research paths do not supply Flash's MLX/Safetensors adapter.
Its hybrid architecture and mixed-precision artifact need explicit tensor/source
mapping and independent numerical qualification, not a renamed GLM-5.2 plugin.

## Explicit non-goals and stop-doing list

- No wholesale rewrite from scratch.
- No production Python hot path.
- No naive global decoded-f32 LRU as the final architecture.
- No custom Metal before a measured format priority exists.
- No unqualified donor dependency.
- No distributed two-Mac inference now.
- No F017 RAID benchmarking before that track's internal-SSD baseline; Flash's separate external-NVMe workspace is not covered by this restriction.
- No performance claims from microbenchmarks alone.
- No weakening the golden correctness contract merely for speed.

## Risks

- Mixed quantization complexity and model-specific architecture drift.
- Direct-Metal numerical drift and MLX/Metal bridge maintenance.
- f32 materialization pressure and Apple SoC thermal/power contention.
- Long experiments and interrupted-run recovery.
- Divergence between research and shipping implementations.
- Apache-2.0 donor-code obligations if Colibri code is ever adapted.

## Decision tree

| Observation | Action |
| --- | --- |
| Decoder acceleration does not improve full P1 | Re-profile end to end; retain it only as a bounded fallback and optimize the newly measured bottleneck. |
| P1 correctness fails | Stop, retain the failing record, bisect at the deepest exact boundary, and restore the scalar mode as rollback. |
| P1 improves but P2 reuse does not | Inspect cache identity/lifetime and repeated-token routes before increasing residency. |
| Cache hits improve but wall time does not | Measure lookup, allocation, pressure, and synchronization overhead; simplify or remove the cache if net benefit is absent. |
| Direct Metal differs numerically | Use the numerical gate, isolate the first divergent projection, and keep the MLX reference path active; never loosen tolerance silently. |
| Memory pressure becomes unsafe | Cancel cleanly, reduce residency/prefetch, and rerun admission before continuing. |
| One quantization dominates after reprofile | Qualify that decoder/kernel next; do not optimize by global tensor count. |
| Command dispatch becomes the bottleneck | Batch routed experts into fewer command buffers, then validate deterministic aggregation separately. |

## Donor qualification

[Pulsar](https://github.com/giannisanni/pulsar) is inherited lineage under MIT.
[ssd-llm](../upstream/SSD_LLM.md) and
[Colibri](../upstream/COLIBRI.md) are qualified design references, not assumed
dependencies or performance evidence. Any adaptation requires an explicit
license review, independently written tests, attribution, and measured benefit.

## Active research and intended native boundary

`017-rust-native-inference-runtime` includes ongoing numerical-reference and
instrumentation work. Its intended native scope remains a Rust checkpoint/catalog
and whole-slab read boundary; exact f32 decode interface; low-copy MLX bridge;
model lifecycle, routing, MLA/DSA state, layer loop, logits, tokenizer,
generation, telemetry, cancellation, and recovery. No Spec Kit artifacts or
tasks are generated here. The exact-decode entry contract is documented in
[`RUST_EXACT_DECODE_BOUNDARY.md`](../architecture/RUST_EXACT_DECODE_BOUNDARY.md).

The material uninstrumented warm residual justifies keeping the following
feature separate and profile-neutral: `018-direct-quantized-metal-runtime`.
Feature 017 should first provide the native ownership/orchestration boundary
and representative M2 Max trunk fixtures. Feature 018's first kernel is chosen
only after those fixture measurements are combined with Feature 016's
expert-cache-only per-quant evidence.