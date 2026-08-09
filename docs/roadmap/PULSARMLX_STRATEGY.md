# PulsarMLX Strategy

## Mission

Run oversized sparse models correctly and usefully on Apple Silicon through
quantization, SSD-backed model storage, unified-memory residency, MLX, and
direct Metal acceleration.

## Current verified boundary

This section names only committed evidence. The Qwen research baseline is
frozen at [`v0.2.0-qwen30b-e2e-research`](https://github.com/MahdiHedhli/PulsarMLX/releases/tag/v0.2.0-qwen30b-e2e-research): a real Qwen3-30B-A3B Q8_0 checkpoint was exercised through all 48 layers, full-vocabulary logits, matching greedy decode, and bounded generation. Its exact scopes and caveats remain in the [Qwen claims ledgers](../research/).

The GLM-5.2 research checkpoint is the six-shard Unsloth UD-IQ2_XXS artifact
bound by [`glm52-checkpoint.json`](../validation/glm52-checkpoint.json) and
[`glm52-revision-binding.json`](../validation/glm52-revision-binding.json):
238,458,632,928 bytes, immutable repository revision
`abc55e72527792c6e77069c99b4cb7de16fa9f23`, and set SHA-256
`d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`.
The C01–C11 research ladder is complete and frozen at
[`v0.3.0-glm52-e2e-research`](https://github.com/MahdiHedhli/PulsarMLX/releases/tag/v0.3.0-glm52-e2e-research), including the golden generated sequence
`[21615, 220, 16, 13, 16, 16, 15, 15]`.

Feature 016's vectorized reference path reproduced the complete frozen
sequence `[9703,21615,220,16,13,16,16,15,15]` on the MLX GPU. The deepest
committed optimization rung is the golden-eight record
[`f016-inference-golden8-iq3-0001.json`](../research/glm52/raw/f016-inference-golden8-iq3-0001.json)
at source commit `1a2ca76ee2df0f518bfc9ddbaafd31500a5e6a26`: nine complete
79-layer stacks, 1,824 decoded shared-cache hits, zero fallbacks or evictions,
and normal retained resource states. This is one bounded research correctness
and reuse run, not a tokens-per-second or production-runtime claim. Its
expert-cache quant metrics leave a material uninstrumented trunk residual, so
the first direct-quantized Metal target remains undecided pending trunk-side
fixture evidence.

## Architectural principles

1. Correctness before performance claims.
2. Python oracle, Rust runtime.
3. Compressed weights remain compressed as long as possible.
4. Storage, unified memory, and GPU form one managed hierarchy.
5. Model semantics must not change silently.
6. Every optimization must have a rollback path.
7. Measurements must separate I/O, decode, allocation, dispatch, and compute.
8. Product code must recover cleanly from interruption.
9. Donor code is qualified rather than blindly inherited.
10. No required Python process in the shipping runtime.

Python and NumPy remain the permanent architecture oracle, fixture generator,
boundary-inspection environment, reference decoder, differential-testing path,
and research evidence producer. That path may be slower, but it must remain
independently understandable.

## Runtime architecture

The shipping control and data plane is Rust. It owns checkpoint identity, the
GGUF catalog and multi-shard tensor store, positional reads, memory admission,
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

Owns the full GLM checkpoint, full-stack truth runs, P1/P2/golden generation,
memory admission, end-to-end performance, and final integration.

### M2 Max MacBook Pro

Owns extracted public-safe or local fixtures, quant decoder and Metal kernel
development, slab allocator and command-buffer experiments, memory-pressure
tests, unit/CI work, smaller Qwen regressions, CLI, and packaging.

Network-distributed inference between the Macs is outside the current roadmap.
External RAID testing follows a stable optimized M1 Ultra internal-SSD
baseline.

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

Reusable runtime mechanisms are the GGUF catalog, multi-shard store, storage
scheduling, caches and slab pools, telemetry, memory admission, MLX/Metal
backend contracts, CLI/server, and evidence infrastructure.

Architecture-specific plugins own the tensor map, router, expert activation,
residual graph, attention, KV/latent state, tokenizer/chat template, and output
head.

## Explicit non-goals and stop-doing list

- No wholesale rewrite from scratch.
- No production Python hot path.
- No naive global decoded-f32 LRU as the final architecture.
- No custom Metal before a measured format priority exists.
- No unqualified donor dependency.
- No distributed two-Mac inference now.
- No RAID benchmarking before the internal-SSD baseline.
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

## Proposed next feature

`017-rust-native-inference-runtime` is proposed after Feature 016 closes its
golden-eight optimization baseline. Likely scope: a Rust checkpoint/catalog
and whole-slab read boundary; exact f32 decode interface; low-copy MLX bridge;
model lifecycle, routing, MLA/DSA state, layer loop, logits, tokenizer,
generation, telemetry, cancellation, and recovery. No Spec Kit artifacts or
tasks should be generated until Feature 016's remaining gates establish the
correct starting point. Direct quantized Metal kernels may be a later separate
feature if profiling justifies that split.
