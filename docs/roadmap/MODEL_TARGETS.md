# Model targets and evidence boundaries

PulsarMLX is building toward useful local inference on models larger than unified
memory. Flash leads practical-usability work; the GLM-5.2 reference and smaller
[Qwen regression baseline](../../README.md#verified-today) remain valuable evidence,
not substitutes for qualifying a new model.

| Model | Role | Current evidence boundary |
| --- | --- | --- |
| GLM-5.2 IQ2_XXS | Large-model correctness reference on the 128 GB Mac Studio | Sequence 43: two independent 79-layer oracles. Prospective instrumentation is separate; full performance and dogfood are not qualified. |
| GLM-5.3 | Full-scale model-family target | No exact PulsarMLX quantized artifact is ratified here. Numerical compatibility and performance remain to be qualified. |
| `pipenetwork/GLM-5.3-Flash-MLX-mixed-4_8bit` | Primary practical-usability target on the 64 GB M2 Max MacBook Pro with external NVMe; later 128 GB Studio evaluation | Model-specific source mapping and bounded synthetic component work. No PulsarMLX full-model correctness, sustained decoding or dogfood claim. |

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

Studio's F017 reference/instrumentation track and MacBook's Flash bring-up are
independent. They share verified components and lessons, not a distributed
inference session. External NVMe is the established Flash storage/workspace;
F017's internal-SSD and RAID sequencing rules are not global bans on that track.
This description grants no drive access or new experiment authority.

The runtime design keeps attention state and useful expert residency in unified
memory and streams other weights as needed. An optimized Flash streaming/cache
path is unfinished; existing research/scaffolding does not establish usable speed.

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
