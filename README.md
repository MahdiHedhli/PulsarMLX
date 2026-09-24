![PulsarMLX](docs/assets/pulsarmlx-poster.png)

# PulsarMLX

**Giant MoE inference on Apple Silicon.**

PulsarMLX is an experimental runtime for running Mixture-of-Experts models that are larger than a Mac's unified memory.

The current practical target is **GLM-5.3 Flash**. The selected mixed-precision checkpoint is reported at **181.9 GB**, larger than either the **128 GB M1 Ultra Mac Studio** or the **64 GB M2 Max MacBook Pro** used in development. The project does not try to squeeze the whole model into memory. It treats fast NVMe storage, unified memory, and GPU execution as one managed hierarchy.

> **DON'T PANIC.** The giant model does not need to fit entirely in memory.

## The idea

A language model is a very large collection of learned numbers called **weights**. During inference, those weights are used to predict the next token, then the next, until a response is produced.

A dense model uses most of its weights for every token. A **Mixture-of-Experts (MoE)** model is different: it contains many expert blocks, but a learned router selects only a small subset for each token. GLM-5.3 Flash has **288 routed experts** and selects **8** at each MoE layer.

That changes the memory problem.

Instead of keeping every expert resident, PulsarMLX explores keeping shared state and useful experts in unified memory while fetching other compressed experts from SSD only when routing asks for them.

```text
        Giant MoE checkpoint
             ~181.9 GB
                 │
                 ▼
          ┌─────────────┐
          │  Fast NVMe  │
          │ most experts│
          └──────┬──────┘
                 │ selected / cached experts
                 ▼
     ┌───────────────────────────┐
     │ Apple unified memory      │
     │ hot experts               │
     │ attention / model state   │
     │ KV / recurrent state      │
     └────────────┬──────────────┘
                  │
                  ▼
             MLX / Metal
                  │
                  ▼
                token
```

The goal is not simply to make a giant checkpoint **fit**. The goal is to **move, expand, and recompute less data**.

## Why Apple Silicon is interesting

Apple Silicon gives this design a few useful properties:

- the CPU and GPU share **unified memory**
- **MLX** is designed for Apple Silicon
- modern Macs have high memory bandwidth
- internal and external NVMe can be fast enough to act as another storage tier
- MoE sparsity creates opportunities for caching, residency, and prefetch

This is a feasibility and systems-engineering thesis, not a claim that a Mac outperforms a multi-GPU server.

## Current research snapshot

| Track | What it proves | Status |
| --- | --- | --- |
| **Qwen3-30B-A3B Q8_0** | Apple MLX execution and architecture-oracle methodology | ✅ Verified and frozen |
| **GLM-5.2 research path** | Giant-model correctness across the full model | ✅ C01-C11 committed |
| **GLM-5.2 Rust-native runtime** | Native model semantics without Python in the inference path | ✅ One real-checkpoint token qualified; later positions measured |
| **GLM-5.3 Flash paged research** | Practical expert paging and persistent residency | 📏 Measured Python/MLX research path |
| **Native Safetensors + MLX affine** | Native checkpoint-format foundation for current targets | ✅ Slices 1 and 2B qualified on synthetic fixtures |
| **Native GLM-5.3 Flash runtime** | Intended shipping path | 🔨 In development / planned boundaries |

None of this is a production runtime. The Python/MLX Flash implementation is a research reference and performance vehicle. The intended shipping architecture is Rust-native.

## What has actually been demonstrated

### GLM-5.3 Flash on the 128 GB M1 Ultra

The unpruned mixed-4/8-bit Flash research path has demonstrated:

- **120/120 token-identical paired tasks** against a fresh-process paged reference
- decode around **2.6-3.3 tok/s** at a 60 GB expert-residency budget
- decode around **3.06-4.20 tok/s** at the admitted 70 GB ceiling
- **18/18 token-identical** paired 60 GB vs 70 GB budget runs
- a **6.03 hour** single-process soak at 60 GB with no failed requests
- repeat-request latency improvements when useful experts remain resident

These are bounded research measurements on one M1 Ultra host. They are not production throughput claims, 64 GB MacBook qualification, or evidence that the native Rust runtime already performs the same way.

See [GLM-5.3 Flash persistent-serving results](docs/glm53-flash/persistent-serving-results.md).

### GLM-5.2 as the correctness reference

GLM-5.2 is the project’s large-model correctness reference. Its quantized checkpoint is about **238.5 GB / 222.1 GiB**.

The research path established the full 79-layer model and frozen generation behavior. The native F017 runtime later qualified one token against the corrected oracle and has since executed multi-position and short-generation paths that remain explicitly classified as measured rather than independently qualified.

See [F017 native runtime status](docs/architecture/f017-native-runtime-status.md) and [model targets and evidence boundaries](docs/roadmap/MODEL_TARGETS.md).

## What the profiling taught us

One of the most useful results in the project was a failed assumption.

A representative path performed **25,152 positional reads**. Reducing that to **4 whole-matrix reads** looked like it should transform performance.

It improved runtime by only about **0.4%**.

The SSD access pattern really was inefficient, but it was not the dominant cost. Profiling showed that the CPU was spending far more time **dequantizing compressed weights into floating-point matrices**.

Vectorizing those decoders produced much larger improvements.

| Measured boundary | Before | After |
| --- | ---: | ---: |
| Q5_K decode | 11.080 s | 0.548 s |
| Q8_0 decode | 3.056 s | 0.040 s |
| Q6_K decode | 6.182 s | 0.144 s |
| Representative MLA path | 55.137 s | 1.763 s |
| Representative complete layer after expert-format work | 44.266 s | 3.512 s |

The pattern is now fundamental to PulsarMLX:

**measure → change one thing → measure again**

Fix one bottleneck and the next one becomes visible.

## Why direct quantized execution matters

A conventional reference path can look like this:

```text
SSD
 ↓
compressed weights
 ↓
CPU decode / dequantize
 ↓
large f32 matrix
 ↓
MLX / Metal compute
```

On Apple Silicon, CPU and GPU share the same physical memory. That opens another possibility:

```text
SSD
 ↓
compressed weights in unified memory
 ↓
Metal-visible buffer over the same allocation
 ↓
direct quantized kernel
 ↓
output activation
```

The opportunity is not "zero-copy everything." Bytes still have to come off storage, memory still has to be managed, and GPU work still has to synchronize.

The important idea is narrower:

> **Do not construct a huge decoded representation when the GPU can consume the compressed representation directly.**

An early real GLM-5.2 IQ2_XXS experiment showed why system-level measurement matters:

| Boundary | Measured improvement |
| --- | ---: |
| Quantized matrix | **65.70×** |
| Complete expert | **1.76×** |
| Top-8 + shared MoE | **1.90×** |
| Complete layer | **1.44×** |

A 65× kernel does **not** mean the model became 65× faster. Once the rest of the computation is included, the improvement becomes smaller. PulsarMLX therefore reports the exact boundary behind each performance result instead of extrapolating microbenchmarks.

## The target runtime

The intended architecture separates research truth from the shipping implementation:

```text
Python / NumPy reference oracle
          │
          │ numerical qualification
          ▼
      Rust runtime
 routing • lifecycle • residency
 checkpoint access • telemetry
          │
          ▼
   Apple native execution
       MLX / Metal
          │
          ▼
 compressed expert weights
        from NVMe
```

The current native direction is:

```text
Native Rust runtime
      +
Safetensors checkpoint ingestion
      +
MLX affine quantization
      +
expert residency / streaming
      +
MLX / Metal execution
```

The goal is to consume the selected MLX mixed-precision checkpoints **without converting them to GGUF** and **without requantizing their weights**.

F020 Slice 1 has already merged the native Safetensors catalog/admission and MLX affine representation/decoder layers, qualified on synthetic fixtures. F020 Slice 2B provides native MLX affine primitives, including packed-weight quantized matmul, qualified on frozen synthetic fixtures on the recorded GitHub runner. Real checkpoint execution and production geometry remain unqualified. Residency integration and native Flash execution remain separate upcoming gates.

See [F020 native Safetensors status](docs/architecture/f020-native-safetensors-status.md).

## Correctness before speed

PulsarMLX does not treat "the output looks reasonable" as proof that the runtime is correct.

Validation uses:

- frozen checkpoint identities
- frozen inputs and numerical contracts
- independent architecture oracles
- intermediate graph-boundary comparisons
- deterministic repetition where appropriate
- retained raw evidence
- explicit distinctions between **verified**, **measured**, **experimental**, **planned**, and **not claimed**

The research process has intentionally rejected runs that looked numerically good when provenance or evidence was incomplete.

That discipline is part of the architecture, not paperwork around it.

## Roadmap

```text
Qwen Apple MLX baseline                    ✅ verified
        ↓
GLM-5.2 full-model research                ✅ verified reference
        ↓
GLM-5.2 Rust-native runtime                ✅ bounded native evidence
        ↓
GLM-5.3 Flash paged research               📏 measured
        ↓
Safetensors + MLX affine foundation        ✅ Slice 1
        ↓
Native packed-weight operations            ✅ Slice 2B (synthetic)
        ↓
Native GLM-5.3 Flash composition           🗺️ next
        ↓
Residency / cache / prefetch optimization  🗺️ planned
        ↓
KV / hybrid-state optimization             🗺️ planned
        ↓
Serving + broader hardware qualification   🗺️ planned
```

The detailed source of truth is [PULSARMLX_STRATEGY.md](docs/roadmap/PULSARMLX_STRATEGY.md), with per-model boundaries in [MODEL_TARGETS.md](docs/roadmap/MODEL_TARGETS.md).

## Built on Pulsar

PulsarMLX began as an Apple Silicon derivative of [Pulsar](https://github.com/giannisanni/pulsar), created by Giannis Anni and contributors.

Pulsar established much of the foundation that inspired this work: giant-MoE SSD expert streaming, the Linux/CUDA runtime, GGUF support, quantization work, and substantial GLM / MLA / DSA architecture knowledge.

PulsarMLX preserves Pulsar's MIT license, notices, Git history, and inherited Linux/CUDA implementation. The Apple MLX backend, portable storage work, architecture-oracle methodology, evidence framework, unified-memory residency research, and native Apple runtime are developed in PulsarMLX.

See [NOTICE.md](NOTICE.md) for attribution.

## Quick start

### Requirements

- Apple Silicon Mac
- recent macOS and Xcode command-line tools
- Rust toolchain
- Python + MLX for research/reference checks

```sh
git clone https://github.com/MahdiHedhli/PulsarMLX.git
cd PulsarMLX

cargo check --workspace --all-targets
cargo test --workspace --no-fail-fast
```

The `f017-native` crate requires the pinned native MLX build. See [scripts/ci/install_native_mlx.sh](scripts/ci/install_native_mlx.sh). Smaller fixture/device validation can be run without downloading a multi-hundred-gigabyte checkpoint.

## Repository map

```text
crates/backend/          backend-neutral contracts
crates/mlx-backend/      Apple MLX runtime
crates/stream/           portable / expert storage
crates/quant/            quantization + CPU reference ops
python/                  MLX research/reference integration
scripts/research/        oracles, profilers, model research tools
docs/research/           evidence and claims ledgers
docs/architecture/       runtime contracts and status
docs/roadmap/            project strategy and model targets
docs/validation/         qualification and validation indexes
docs/upstream/           inherited Pulsar material
specs/                   feature specifications and contracts
```

## Evidence tracks

The README intentionally summarizes the project at human scale. Exact claim boundaries, machine-readable measurements, and reproduction details remain in the evidence tracks below.

| Evidence track | Start here | What it supports |
| --- | --- | --- |
| **Apple MLX baseline** | [Apple runtime report](PULSARMLX_APPLE_RUNTIME_REPORT.md) | Qwen Apple GPU execution, router/expert/layer parity, logits, and bounded generation |
| **GLM-5.2 optimization measurements** | [GLM-5.2 claims ledger](docs/research/glm52/CLAIMS_LEDGER.md) | Decoder, expert, MoE, layer, cache, profiling, and optimization measurements used in the performance story above |
| **GLM-5.2 native runtime** | [F017 current status](docs/architecture/f017-native-runtime-status.md) | What the Rust-native runtime has actually qualified, what is merely measured, and what remains unclaimed |
| **GLM-5.3 Flash paging / residency** | [Persistent-serving results](docs/glm53-flash/persistent-serving-results.md) | Decode ranges, expert-cache budget ladder, identity retention, latency, soak, and decode-I/O findings |
| **Native Safetensors / MLX affine** | [F020 current status](docs/architecture/f020-native-safetensors-status.md) | Native checkpoint catalog and affine-quantization foundation, plus its current qualification boundary |
| **Model-by-model boundaries** | [Model targets](docs/roadmap/MODEL_TARGETS.md) | Which findings transfer between Qwen, GLM-5.2, GLM-5.3, and Flash, and which explicitly do not |
| **Project strategy** | [PulsarMLX strategy](docs/roadmap/PULSARMLX_STRATEGY.md) | Current architecture, sequencing, product milestones, risks, and non-goals |
| **Raw/reproducible evidence** | [Research evidence index](docs/research/) | Claims ledgers, raw JSON, reviewer indexes, protocols, and reproduction material |

A public PulsarMLX claim should ultimately resolve to a **commit**, **raw evidence**, an **oracle/reference contract**, and a **reproduction path**.

## License

Repository source is MIT licensed. See [LICENSE](LICENSE). Model weights and external runtime components retain their own license terms; this repository does not relicense them.

**Apple Silicon / MLX development:** Mahdi Hedhli and contributors.
