# Model targets and evidence boundaries

PulsarMLX is building toward useful local inference on models larger than unified
memory. Flash leads practical-usability work; the GLM-5.2 reference and smaller
[Qwen regression baseline](../../README.md#verified-today) remain valuable evidence,
not substitutes for qualifying a new model.

| Model | Role | Current evidence boundary |
| --- | --- | --- |
| GLM-5.2 IQ2_XXS | Large-model correctness reference on the 128 GB Mac Studio | Historical research plus bounded native results; later measured positions/text are not independently qualified. See the [F017 current status](../architecture/f017-native-runtime-status.md). |
| `pipenetwork/GLM-5.3-Flash-MLX-mixed-4_8bit` | First practical native-integration/optimization target on the owned 128 GB M1 Ultra Studio; subsequent 64 GB M2 Max qualification | Measured Python/MLX paged/persistent research candidate, not a native model. Native tensor primitives and model integration retain separate qualification boundaries. |
| `pipenetwork/GLM-5.3-MLX-mixed-4_8bit` | Full-scale second architecture target | Exact mixed-4/8 target selected; native numerical compatibility, model execution and useful performance remain unqualified. No universal hardware floor is established here. |

## Current direction (2026-09-23)

This section is the current pointer for target selection. Historical evidence
below remains unchanged; it does not override the present Flash-first sequence.
The [optimization roadmap](OPTIMIZATION_ROADMAP.md) captures the latest project
feedback as explicit planned work, not implementation authority.

The intended capability is *native Rust runtime + Safetensors checkpoint
access + MLX affine quantization + PulsarMLX expert residency/streaming + MLX
execution*, consuming both targets **without converting to GGUF** and
**without requantizing weights**.

| Boundary | Status |
| --- | --- |
| F020 Slice 1 catalog/admission and affine representation/decoder | Merged; qualified on synthetic fixtures only ([status](../architecture/f020-native-safetensors-status.md)) |
| Slice 2 target metadata census and primitive contract | Committed preparation at [`9bf6a810`](https://github.com/MahdiHedhli/PulsarMLX/blob/9bf6a810622b7ef1156b750dd0f3140f8c0ca211/specs/020-mlx-safetensors-affine/slice2b-plan.md); metadata compatibility is not payload identity, numerical admission or native model qualification |
| Slice 2B native packed-weight operations | Merged. F020 Slice 2B provides native MLX affine primitives, including packed-weight quantized matmul, qualified on frozen synthetic fixtures on the recorded GitHub runner. Real checkpoint execution and production geometry remain unqualified. ([status](../architecture/f020-native-safetensors-status.md)) |
| Slice 2C synthetic expert-plane composition | Merged. F020 Slice 2C composes synthetic stacked-affine expert-plane selection with native packed-weight quantized matmul. It is qualified on its frozen small-fixture population on the recorded GitHub runner. Real checkpoint payloads, production geometry, full expert MLPs, model execution, streaming and performance remain outside that qualification. ([status](../architecture/f020-native-safetensors-status.md)) |
| Native Flash / full GLM-5.3 model execution | Planned; independently qualified per architecture, Flash first |
| Native residency, double buffering, prefetch and repacking | Planned after the relevant correctness/composition gates and an instrumented baseline; see OPT-01 through OPT-08 |

The active Slice 2B scope does not include real-checkpoint payload reads,
production-geometry qualification, model graphs, streaming or benchmarks.
A shape admitted by the primitive contract is not automatically qualified by
small fixtures. Individually selected expert planes and whole stacked tensors
are different execution boundaries.

Sequence (a roadmap, not a completion claim):

```text
Qwen baseline / GLM-5.2 reference and native evidence / Flash paged research
  -> F020 catalog and affine representation (Slice 1 synthetic qualification)
  -> native packed-weight primitive qualification (bounded Slice 2B)
  -> authorized Flash real-weight, expert, block, fixed-prefix and state gates
  -> separately qualified full GLM-5.3 architecture using shared infrastructure
  -> profiling and routing traces, then residency / layout / staging experiments
  -> streamed composition, generation and serving acceptance
  -> KV/prefix/hybrid-state tuning and separately admitted 64 GB qualification
```

The full-model track need not block bounded Flash profiling or optimization;
its implementation and evidence remain independent. Upcoming work needs its
own authorization and cannot silently enter the active primitive slice.

Current Flash research evidence is unchanged: the paged persistent-serving
candidate `971db9c1` is Python/MLX
([results](../glm53-flash/persistent-serving-results.md)), with a 60e9-byte
baseline expert-cache budget and **70e9 admitted as the ceiling** on its stated
128 GB host. A 6 h soak at 70e9 has not been completed. Those budgets are not
native defaults or 64 GB admission results. The Python/MLX path remains a
behavioral/compatibility reference, not the shipping runtime or R1 numerical
correctness oracle. Only the Rust-native Flash runtime is intended to ship.

## GLM-5.2 reference evidence

The [commit-pinned Sequence 43 record](https://github.com/MahdiHedhli/PulsarMLX/blob/c23e58ec87c7e73a23cf37ac64aa4dee6c45896f/docs/architecture/reviews/evidence/f017-event06-v12-sequence43-terminal-success-evidence-v1.json)
reports one execution per independent role, each completing 79 layers. Both
selected token **154820**, with identical ordered top-32 token IDs and route
structure. The token is a historical observation, not an expected-token predicate
for another execution.

| Metric | Observed | Frozen comparison bound |
| --- | ---: | ---: |
| Maximum absolute error | `2.4495741151042694e-06` | at most `0.0065169706285814755` |
| RMSE | `4.947803155886533e-07` | at most `0.003463567697419031` |
| Cosine similarity | `0.999999999999954` | at least `0.9999999985448085` |

Exact agreement refers to the selected token, top-32 ID order and route structure;
floating-point outputs agree within the numerical contract, not bit for bit.
The record reports six shard opens and complete identity hashes covering
**238,458,632,928 bytes**, about **238.5 GB / 222.1 GiB**. This is the measured
six-shard quantized set, not a model-family parameter count or another artifact.

Exact numerical payload-read, mapping and fault counts were not separately banked.
They remain **unknown, with no retroactive backfill**. Current process-level
telemetry does not measure per-shard physical I/O. The
[primary read-observation publication](../research/f017/read-observation-publication-status.md)
has its own narrower qualification boundary. None of these observations is a
throughput benchmark, a generation-quality result or qualification of GLM-5.3/Flash.

## Model-specific work

Model-card metadata was checked on **2026-09-09 UTC**; these are dated observations,
not a frozen model revision or a new local checkpoint measurement.

The [official GLM-5.3 card](https://huggingface.co/zai-org/GLM-5.3) describes a shared
base with GLM-5.2. That motivates investigating reuse, but does not establish
unchanged weights, quantization, implementation or numerical contracts.

The [selected Flash publisher card](https://huggingface.co/pipenetwork/GLM-5.3-Flash-MLX-mixed-4_8bit)
reports **181.9 GB** on disk and a hybrid architecture with mixed-precision weights.
That size exceeds both machines' RAM. Its upstream validation claims concern the
publisher's runtime, not PulsarMLX. Flash needs explicit MLX/Safetensors tensor
mapping and numerical qualification; it is not a smaller drop-in GLM-5.2/GGUF path.

## Hardware and progression toward local use

The owned 128 GB M1 Ultra Studio is the first practical native Flash integration
and optimization host. The 64 GB M2 Max MacBook remains a subsequent lower-memory
target and a development host for bounded fixtures and source mapping. Keep
F017's reference track independent. The hosts share verified components and
lessons, not a distributed inference session.

External NVMe is an established Flash workspace; F017's internal-SSD and RAID
sequencing rules are not global bans on that track. This description grants no
drive access or new experiment authority. Cache, state and staging memory need
fresh admission for each runtime, host, workload and storage configuration.

The runtime design keeps attention/hybrid state and useful expert residency in
unified memory and streams other weights as needed. The planned native
optimization work is explicit in [the optimization register](OPTIMIZATION_ROADMAP.md):
profile token costs, build routing-based hot/cold and capacity models, qualify
fixed-buffer read/compute overlap, and evaluate deterministic lossless layout
changes. Existing Python/MLX research does not establish native useful speed.

1. Establish model-specific semantics, tensor maps and synthetic composition.
2. Earn independent numerical qualification at the appropriate real boundary.
3. Measure memory pressure, storage traffic, cache behavior and sustained decoding.
4. Integrate usable CLI/serving and evaluate task-level quality.

These are roadmap stages, not execution instructions. Rust-native orchestration,
direct quantized Metal kernels, prefetch and serving retain their actual partial
or planned status in the [strategy](PULSARMLX_STRATEGY.md).

## Licenses and lineage

Repository source remains [MIT licensed](../../LICENSE), with inherited
[Pulsar attribution and notices](../../NOTICE.md) preserved. Model weights and
external runtime components retain their own terms. The GLM-5.3 card labels its
license `glm-5.3`; repository licensing does not relicense target weights.
