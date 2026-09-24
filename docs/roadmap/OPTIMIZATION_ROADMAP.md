# Optimization roadmap

**Updated 2026-09-23 (America/New_York). Planning, not execution authorization.**

This register captures the concrete optimization ideas from the latest project
feedback discussion: routing-trace-driven hot/cold residency, cache-capacity
curves, double-buffered Safetensors staging, deterministic expert-contiguous
repacking, and token-time decomposition before choosing an optimization. It
makes the broader [strategy](PULSARMLX_STRATEGY.md) actionable without expanding
F020 Slice 2B or converting suggestions into verified performance claims.

## Targets and the active boundary

The first practical native target is the unpruned
`pipenetwork/GLM-5.3-Flash-MLX-mixed-4_8bit` on the **owned M1 Ultra Mac Studio
with 128 GB unified memory**. The M2 Max MacBook Pro with 64 GB remains an
important subsequent, separately admitted lower-memory target.
`pipenetwork/GLM-5.3-MLX-mixed-4_8bit` remains the full-scale second architecture
target. Neither a larger Mac purchase nor a speculative memory-capacity floor
is a prerequisite for progress. Admission and useful performance must be
measured on each actual host and storage configuration.

The mainline baseline at `1a05cf4f` includes F020 Slice 1's model-neutral
Safetensors catalog/admission and MLX affine representation/decoder, qualified
on synthetic fixtures only ([status](../architecture/f020-native-safetensors-status.md)).
The [Slice 2 preparation at `9bf6a810`](https://github.com/MahdiHedhli/PulsarMLX/blob/9bf6a810622b7ef1156b750dd0f3140f8c0ca211/specs/020-mlx-safetensors-affine/slice2b-plan.md)
is a separately committed census and reviewed primitive contract, not proof of
implemented or qualified native model execution.

**The current Slice 2B implementation authorization is unchanged:** synthetic
qualification of packed-U32 and metadata import, metadata widening,
dequantization, and `transpose=true` f32 quantized matmul, with required native
CI. It does not authorize real-checkpoint payload reads, production-geometry
qualification, model graphs, residency, streaming, serving or benchmarks.
The frozen contract, fixture population and source pins are not amended here.

R1 remains the independent mathematical correctness reference. Pinned upstream
Python/MLX and the existing Flash research path provide compatibility and
behavioral comparisons, not an independent correctness oracle for native MLX.
R3 is the native candidate. Quantized-checkpoint fidelity and retained quality
against a higher-precision original model remain different evaluation questions.

## Dependency order

```text
F020 synthetic native packed-weight primitives (current bounded slice)
  -> separately authorized real-payload and production-shape qualification
  -> one projection, selected expert plane, expert, block and fixed-prefix graph
  -> retained-state and composition correctness
  -> instrumented native baseline and routing traces
  -> trace-driven residency, staging and layout experiments (one factor at a time)
  -> resident/streamed equivalence before streamed generation and serving
  -> longer contexts, broader workloads and separate 64 GB qualification
```

Flash leads the real-weight/native integration ladder; full GLM-5.3 follows
with independent architecture qualification. Instrumentation is designed with
the baseline, before optimizing it. Correctness of cache/state and streaming
composition is a prerequisite to accepting results, not a performance phase
that may be skipped. Future work needs its own bounded authorization.

## Concrete work register

Every row below is **planned native work**, not a new task inside Slice 2B.
Research precedents do not transfer their qualification to the native runtime.

| ID | Work item | Dependency and acceptance question |
| --- | --- | --- |
| OPT-01 | Token-time and bytes/token decomposition | After the relevant native boundary works, attribute routing, cache lookup, reads, packed decoding/materialization, array construction/copies, compute, synchronization/dispatch and attention/residual work. Which component actually limits the complete operation or token? |
| OPT-02 | Routing-trace-driven hot/cold residency and capacity curves | Use authentic traces from a qualified baseline. Measure expert reuse, reuse distance and per-layer demand; compare cache budgets and allocation policies. Does avoiding misses reduce requested bytes and end-to-end latency without unsafe memory pressure? |
| OPT-03 | Double-buffered Safetensors staging and bounded prefetch | After safe storage ownership and a synchronous baseline, overlap current compute with reads for the next known expert wave using fixed staging buffers. Does actual overlap hide unavoidable read latency, after accounting for added memory and synchronization? |
| OPT-04 | Deterministic expert-contiguous repacking | Start with direct bounded checkpoint access. Use traces and offset metadata to evaluate larger contiguous reads and less scatter. Does a lossless derived layout improve useful I/O and complete-token latency enough to justify its storage/build cost? |
| OPT-05 | Remove avoidable copies, decoding and allocation | Preserve packed U32 weights into quantized matmul; widen only required metadata. Reuse stable buffers and reduce array construction or transient f32 materialization where profiling justifies it. Is the benefit visible beyond an isolated primitive? |
| OPT-06 | Profile-selected native kernels, fusion and dispatch | Build on independently qualified primitives. Revisit the existing F018 direction only when the dominant format/operation is measured; candidates include fused expert projections/activation and fewer dispatches. Preserve model semantics and qualify changed numerical ordering separately. |
| OPT-07 | KV/prefix and hybrid-state optimization | After baseline retained-state correctness, measure state cost versus expert-cache demand. Qualify prefix reuse/invalidation and the full KV, sparse-attention, recurrent and convolution state as appropriate. Never assume KV alone describes Flash state. |
| OPT-08 | Persistent serving and hardware-specific tuning | After native generation and streaming equivalence, evaluate warm residency, request isolation, cancellation, bounded queues and soak behavior. Re-admit budgets on each host; research server results are comparisons, not native product claims. |

### OPT-01: measure the bottleneck before choosing the fix

Record both stage timings and end-to-end wall time. When work overlaps, label
inclusive/overlapped time and do not sum it as if every stage were serial.
Separate cold startup, identity verification, prefill, time to first token and
decode. Attribute counters to the measured request rather than mixing lifetime
server counters with per-request timings.

The primary storage measures are **expert bytes requested per token** and
**physical storage bytes per token where independently observable**. Keep
logical tensor bytes, issued/read bytes and physical device traffic separate;
mark physical traffic unknown when the instrumentation cannot measure it.
Include cache misses, read latency, copy/allocation cost, GPU execution and
synchronization, peak MLX/wired memory, compressor/swap behavior and tail latency.

Do not assume an I/O optimization is the priority because the checkpoint is
large. The [GLM-5.2 reference profile](PULSARMLX_STRATEGY.md#current-verified-boundary)
and [Flash decode research](../glm53-flash/persistent-serving-results.md) have
different execution paths and bottlenecks. Re-profile the native path rather
than transferring either conclusion unconditionally.

### OPT-02: avoid reading bytes before trying to move them faster

Capture expert IDs and order, token/layer position, hit/miss outcomes and the
bytes required by each projection. Traces are observations of actual routing,
not permission to change routing or prune experts. Sanitize public artifacts;
private prompts and user content do not belong in routing evidence.

Use trace replay to estimate per-layer hot/cold sets and cache-capacity curves,
then confirm promising policies in the actual runtime on held-out workloads.
Distinguish simulated hit-rate gains from measured latency gains. Compare a
simple fixed policy with any adaptive policy before accepting added complexity.
Keep resident non-expert weights, state, expert slots and staging allocations
inside one explicit unified-memory budget.

The existing [Flash research](../glm53-flash/persistent-serving-results.md)
admits a 70e9-byte expert-cache ceiling on its specified 128 GB configuration;
80e9 is not admitted there. Neither value is a native default, a spare-memory
allowance for double buffering, nor a budget transferable to the 64 GB host.

### OPT-03: double buffering is an experiment, not an automatic speedup

Use a deterministic shard/tensor/plane offset index, checked positional reads,
fixed bounded staging buffers and an explicit ownership lifecycle. Read the
next known expert wave while current work computes. Preserve exact expert
selection and ordered aggregation; predictions are optional later experiments,
never evidence that the next layer's route is already known.

Account for staging within the same unified memory used by CPU and GPU.
Fence GPU completion before buffer reuse, eviction or reload. Cover errors,
short reads, cancellation and cross-request isolation. Prove that overlapped
and synchronous execution agree at the contracted intermediate/state boundaries.
Prefill and decode need separate schedules and measurements.

Evaluate useful read sizes, bounded concurrency and coalescing from traces,
not by maximizing sequential disk throughput. Report achieved overlap,
read amplification, wasted prefetch bytes, stalls and complete-token latency.
A Python sketch is pseudocode until implemented and qualified. Neither mmap,
unified memory, asynchronous reads nor a two-buffer design proves zero-copy
GPU consumption or a particular speedup.

### OPT-04: repack placement, not model meaning

Preserve the source checkpoint and its quantized representation. A derived
store should make `(layer, expert, projection)` independently addressable,
retaining packed weights, scales, biases, logical shapes and original expert
identity. Expert-contiguous, page-aligned spans and larger contiguous reads
are candidate layouts, not reasons to requantize, prune or renumber routing.

Publish deterministic layout metadata and source-to-derived identity receipts
with explicit checkpoint revisions, source ranges, transformation version and
hash bindings. Verify byte equivalence under any recorded permutation and
numerical equivalence at the execution boundary. Support resumable offline
construction and reject partial/unverified derived stores.

Compare with direct checkpoint access before requiring a second checkpoint-sized
copy. Include build time, extra disk space, read amplification and cold/warm
performance. Preserve the accepted direct-access path as rollback.

## Controls, retained negatives and stop rules

The [unpruned Flash results](../glm53-flash/persistent-serving-results.md)
retain failed streaming-prefill, union/speculative batching and request-batching
experiments. The rejected streaming-prefill path also exposed a kernel-selection
identity failure. OPT-03 does not reactivate that path or make its results pass.
A different native staging design needs its own correctness comparison and
measured benefit; previous evidence remains unchanged.

Use the same checkpoint, quantization, token prefixes, stop policy, context and
host budget for paired comparisons. Keep MTP off for the retained Flash baseline;
no pruning, altered routing or reduced precision is authorized by this roadmap.
For native comparisons, preserve R1 correctness checks and separately label
upstream compatibility, checkpoint fidelity and higher-precision quality results.

Change one factor per comparison. Screen a bounded number of candidates and
promote only a reproducible end-to-end gain that meets prospectively frozen
correctness and resource criteria. Keep no-gain and failure records. If cache
hits, fewer reads or faster microbenchmarks do not improve the intended runtime
boundary, re-profile rather than expanding the mechanism.

Before accepting streamed generation or serving, cover cached versus recomputed
state, chunked versus unchunked prefill, resident versus streamed weights,
eviction/reload with GPU fencing, reset and cancellation isolation. Keep these
composition gates distinct from throughput benchmarking.

## Traceability

| Source | What this roadmap takes from it |
| --- | --- |
| Latest project feedback discussion, 2026-09-23 local date | Owned-hardware/Flash-first priority; routing traces, hot/cold residency, double buffering, deterministic repacking and full token-time profiling. Discussion examples and performance figures are hypotheses, not measurements. |
| [F020 current status](../architecture/f020-native-safetensors-status.md) | The qualified Slice 1 boundary and independent-reference roles. |
| [Reviewed Slice 2B plan, `9bf6a810`](https://github.com/MahdiHedhli/PulsarMLX/blob/9bf6a810622b7ef1156b750dd0f3140f8c0ca211/specs/020-mlx-safetensors-affine/slice2b-plan.md) | Packed-weight primitive scope, separate operation domains and exclusions; no new permission for optimization work. |
| [Flash persistent-serving results](../glm53-flash/persistent-serving-results.md) | Measured research precedents, cache-budget limits, reference-arm limitations and negative results. |
| [Strategy](PULSARMLX_STRATEGY.md) and [model targets](MODEL_TARGETS.md) | Existing native-runtime/F018 direction, hardware roles and independent model qualification. |

This document is a mutable planning register. It changes no frozen contract,
fixture, historical evidence, implementation or CI gate.
