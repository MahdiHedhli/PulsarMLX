![PulsarMLX](docs/assets/pulsarmlx-poster.png)

# PulsarMLX

**Giant MoE inference on Apple Silicon.**

PulsarMLX is an experimental inference runtime for oversized Mixture-of-Experts models on Apple Silicon. It uses MLX for GPU execution, treats unified memory and fast internal NVMe as first-class resources, and validates results against an independent architecture-level CPU oracle with an evidence-first research workflow.

The current research/reference execution path uses Python, NumPy, and MLX. The
planned shipping runtime is Rust-native with no required Python process; direct
quantized Metal expert kernels are roadmap work, not a verified current
capability. See the [PulsarMLX strategy](docs/roadmap/PULSARMLX_STRATEGY.md).

It began as an Apple Silicon derivative of [Pulsar](https://github.com/giannisanni/pulsar). The Apple path has grown into a substantially independent runtime: MLX backend, portable storage, architecture-oracle methodology, research/evidence framework, and unified-memory-aware residency work—while still preserving Pulsar’s MIT license, Git history, and Linux/CUDA implementation.

> [!IMPORTANT]
> PulsarMLX is experimental research software. Verified capabilities are explicitly bounded by **committed** evidence. Correctness has been prioritized before performance optimization.

> **DON'T PANIC.** The giant model does not need to fit entirely in memory.

## Status at a glance (2026-09-20)

| Track | What runs today | Machine | Runtime | Observed speed | Fidelity evidence | Source |
| --- | --- | --- | --- | --- | --- | --- |
| **Qwen3-30B-A3B Q8_0** (frozen research baseline) | full 48-layer execution, greedy token, bounded generation | Apple Silicon (MLX GPU) | Python/NumPy reference + MLX worker | validation timings only (not advertised) | exact numerical boundaries vs the CPU architecture oracle, ≈10⁻⁷–10⁻⁸ at MoE boundaries | tag [`v0.2.0-qwen30b-e2e-research`](https://github.com/MahdiHedhli/PulsarMLX/releases/tag/v0.2.0-qwen30b-e2e-research) |
| **GLM-5.2 UD-IQ2_XXS** (research ladder + Rust-native runtime track) | committed research ladder C01–C11 (Python/NumPy reference path); **Rust-native one-token boundary established on the real checkpoint on 2026-09-20**: the native executor (Rust + MLX bridge) produced token 154820 for prompt 9703, equal to the corrected full-checkpoint oracle (Event 06), under a human-approved one-shot; multi-token generation, tokenizer/template and a CLI loop do not exist yet | Mac Studio M1 Ultra, internal SSD | Python/NumPy reference (research); Rust + MLX-bridge native P1 (one token, human-gated one-shots) | native one token: 1003.6 s = 704 s shard identity rehash (~238 GB) + 299 s forward pass — not a throughput claim | checkpoint-free native-vs-corrected-oracle differentials (11 formats bit-exact; 6/6 graph cases) + real-checkpoint attempt 2 (token and top-1 margin agree with the oracle) | [`docs/architecture/GLM52_CONTRACT.md`](docs/architecture/GLM52_CONTRACT.md), branch `feat/017-rust-native-inference-runtime` ([attempt-2 readiness + outcome](https://github.com/MahdiHedhli/PulsarMLX/blob/e38d002e54b5552966ccb7a586c2b0cc23b47e08/docs/architecture/reviews/f017-native-attempt-2-readiness-20260920.md)) |
| **GLM-5.3-Flash mixed-4/8, unpruned** (paged / persistent research candidate) | persistent OpenAI-style research server paging 288 experts × 42 layers through a wired slot store; corrected termination; 6.03 h soak segment at the 60 GB budget, and a **70 GB budget admitted on 2026-09-20** (117 slots/layer) after a paired ladder and an 80-request server soak | Mac Studio M1 Ultra 128 GB | Python/MLX (mlx 0.32.2, mlx-vlm 0.7.0 + pipenetwork `glm5_next`) | decode **2.6–3.3 tok/s** at the 60 GB budget (miss-bound); at the admitted 70 GB budget the same six paired CLI prompts give **3.06–4.20 tok/s** against **2.75–3.64** at 60 GB (+9–17 % per pair, mean +13.4 %, 18/18 token-identical); exact-repeat request latency 12–15 % lower, A-B-A 9–13 % lower than a fresh process (prefill) | 120/120 token-identical task pairs vs the fresh-process paged reference; 119/119 relative task retention; 0.9724 exact 95 % lower bound on group retention (scope-limited) | [`docs/glm53-flash/persistent-serving-results.md`](docs/glm53-flash/persistent-serving-results.md), commit `971db9c1` on `serve/glm53-flash-unpruned-persistent-20260919b` |
| **Pruned REAP variants** (GLM-5.3-Flash REAP50 etc.) | resident serving experiments on the pruned 144-expert build | Mac Studio M1 Ultra | Python/MLX | recorded in [`docs/glm53-flash/performance-notes.md`](docs/glm53-flash/performance-notes.md) | **not the fidelity target**; pruned-model numbers are never compared with unpruned results | same branch family |

None of these is a production runtime. The Python/MLX Flash candidate is **not** the Rust-native shipping architecture and does not complete it.

## The idea

A giant MoE may hold hundreds of billions of parameters while **activating only a fraction** on each token. That changes the memory problem: not every expert must stay resident for every step.

PulsarMLX explores a residency hierarchy:

```text
SSD  →  compressed expert residency  →  unified memory  →  MLX  →  token
```

Apple Silicon is interesting for that design because:

- CPU and GPU share **unified memory**
- **MLX** is built for Apple Silicon
- modern Macs have high memory bandwidth
- internal NVMe is fast
- MoE sparsity enables cache, prefetch, and streaming of experts

This is a **feasibility and resource-use** thesis—not a claim that Macs outrun discrete GPUs.

## Verified today

**Baseline (committed evidence):** [Qwen3-30B-A3B](https://huggingface.co/Qwen/Qwen3-30B-A3B-GGUF) **Q8_0** on **native Apple MLX GPU**, under the architecture contract *Q8_0 weight dequantization × f32 activation*. Research freeze tag: [`v0.2.0-qwen30b-e2e-research`](https://github.com/MahdiHedhli/PulsarMLX/releases/tag/v0.2.0-qwen30b-e2e-research).

Narrative report: **[PULSARMLX_APPLE_RUNTIME_REPORT.md](PULSARMLX_APPLE_RUNTIME_REPORT.md)** · raw evidence under [`docs/research/raw/`](docs/research/raw/).

### What was demonstrated

| Stage | Verified on Apple MLX |
| --- | --- |
| Device | Native GPU execution (admitted runs: no silent CPU fallback) |
| Checkpoint | Real Qwen3-30B-A3B Q8_0 identity (SHA-256 `4ad960d1…743c`) |
| Router | Real layer-0 router; deterministic top-8 IDs/order |
| Expert | Complete real expert MLP (gate / up / SiLU-SwiGLU / down) |
| Aggregation | Top-8 routed expert aggregation |
| MoE residual | Complete block `y = residual + MoE(RMSNorm(·))` |
| Attention | Real layer-0 attention residual (`ffn_inp`) |
| Layer | Complete transformer layer 0 (attention + MoE) |
| Depth | Progressive multi-layer ladder through **all 48 layers** |
| Head | Final `output_norm` + full-vocabulary logits |
| Decode | Matching greedy token (CPU = MLX) |
| Generation | Bounded autoregressive greedy generation |

### Exact numerical boundaries (MLX vs architecture CPU oracle)

| Boundary | max abs error | Source |
| --- | ---: | --- |
| Single expert (weighted MLP, expert 114) | **7.375932542519337×10⁻⁸** | [F003](docs/research/raw/003-expert-mlp/f003-expert-114-parity-0001.json) |
| Top-8 aggregation | **6.19571565163568×10⁻⁸** | [F004](docs/research/raw/004-top8-moe/f004-top8-aggregate-parity-0001.json) |
| MoE residual block | **≈6.20×10⁻⁸** | [F005](docs/research/raw/005-moe-block/f005-moe-block-parity-0001.json) |
| Layer-0 attention (MLX vs arch CPU) | **1.1298628832534519×10⁻⁷** | [F009](docs/research/raw/009-layer0-attention/) / [F010](docs/research/raw/010-011-layer-stack/) |
| Complete layer 0 | **1.1298628832534519×10⁻⁷** | [F010](docs/research/raw/010-011-layer-stack/f010-complete-layer0-0001.json) |
| 48-layer peak (layer 3) | **4.2811071364212694×10⁻⁴** | [F011 summary](docs/research/raw/010-011-layer-stack/f010-f011-layer-stack-summary.json) |
| Final layer (47) | **1.7724422104947735×10⁻⁴** | same |
| Full logits | **7.62939453125×10⁻⁶** | [F012](docs/research/raw/012-013-logits-greedy/f012-full-logits-0001.json) / [F013](docs/research/raw/012-013-logits-greedy/f013-greedy-token-0001.json) |
| Greedy token | **320** (CPU = MLX); top-5 `[320, 220, 4710, 374, 1115]` | [F013](docs/research/raw/012-013-logits-greedy/f013-greedy-token-0001.json) |
| Short generation | prompt `[0, 1]` → `[320, 16]`; full `[0, 1, 320, 16]` | [F014](docs/research/raw/014-short-prompt-gen/f014-short-prompt-gen-0001.json) |

Claims ledgers: [`docs/research/CLAIMS_LEDGER_*.md`](docs/research/) · reviewer index: [`docs/research/REVIEWER_INDEX.md`](docs/research/REVIEWER_INDEX.md).

**Not claimed for Qwen:** production tokens/sec, optimized MLX-only serving, KV-cached decode, or llama.cpp bit-identical output.

## Correctness before speed

PulsarMLX does not treat “text looks fine” as a correctness proof.

Validation uses:

- frozen model identities
- frozen inputs
- independent **CPU architecture oracles**
- intermediate graph-boundary checks
- deterministic repetition
- raw machine-readable evidence
- sanitization
- claims ledgers and reviewer indexes
- reproducible commands

```text
checkpoint
    ↓
frozen input
    ↓
CPU architecture oracle
    ↓
MLX execution
    ↓
numerical comparison
    ↓
evidence
    ↓
verified claim
```

### Architecture oracle, not fused-kernel mimicry

During Qwen validation, PulsarMLX and the independent architecture oracle agreed closely (≈10⁻⁷–10⁻⁸ at isolated MoE boundaries). llama.cpp’s fused Q8_0 path differed by about **3.43×10⁻³** max abs (cosine ≈0.99999) because that path **requantizes activations** for Q8_0×Q8_0 dots, while the PulsarMLX architecture contract is **f32 dequantized weights × f32 activations** ([F008](docs/research/raw/008-f006-root-cause/)).

Therefore:

- **Architecture-level numerical parity** is the contract
- **llama.cpp bit-identical output is not a goal**
- Implementation-specific fused numerical behavior is **documented**, not blindly reproduced

llama.cpp is not “wrong”; it implements a different quant contract. Feature 006 llama bit-parity remains a **preserved rejection**.

## How it works

```text
                 ┌───────────────────────┐
                 │      GGUF Model       │
                 │   hundreds of GB      │
                 └───────────┬───────────┘
                             │
                    positional / mapped I/O
                             │
                 ┌───────────▼───────────┐
                 │    Expert Storage     │
                 │  SSD • cache • map    │
                 └───────────┬───────────┘
                             │
                 ┌───────────▼───────────┐
                 │   PulsarMLX Runtime   │
                 │ routing • residency   │
                 │ prefetch • telemetry  │
                 └───────────┬───────────┘
                             │
                 ┌───────────▼───────────┐
                 │          MLX          │
                 │ Apple GPU execution   │
                 └───────────┬───────────┘
                             │
                 ┌───────────▼───────────┐
                 │    Apple Silicon      │
                 │    Unified Memory     │
                 └───────────────────────┘
```

The **CPU architecture oracle** is a validation path. It is not the intended optimized inference hot path.

## What is new in PulsarMLX

Relative to upstream Pulsar:

| Area | PulsarMLX work |
| --- | --- |
| **Apple MLX runtime** | GPU device path, MLX worker/backend, model ops, Apple device validation ([`crates/mlx-backend/`](crates/mlx-backend/), `python/`) |
| **Backend contracts** | Backend-neutral capability, tensor, routing, and evidence contracts ([`crates/backend/`](crates/backend/)) |
| **Portable storage** | Exact positional GGUF / expert access without Linux `io_uring` ([`crates/stream/`](crates/stream/) positional path) |
| **Architecture oracle** | Independent CPU reference execution for parity gates ([`scripts/research/`](scripts/research/)) |
| **Evidence framework** | Schemas, raw JSON, sanitization, claims ledgers, reviewer indexes, protocols ([`docs/research/`](docs/research/), [`docs/validation/`](docs/validation/)) |
| **Unified-memory runtime** | Expert-cache / budget / telemetry / fail-closed no-CPU-fallback scaffolding (Feature 016 research path) |

Unfinished or partial pieces (GLM generation, MLX-only serving, KV cache) are **not** marked complete.

## Built on Pulsar

PulsarMLX would not exist without **[Pulsar](https://github.com/giannisanni/pulsar)**, created by **Giannis Anni** and contributors.

Pulsar established much of the foundation that inspired this project: giant-MoE SSD expert streaming, the Linux/CUDA runtime, GGUF support, quantization work, multi-architecture model implementations, and substantial GLM / MLA / DSA architecture knowledge.

PulsarMLX **preserves**:

- Pulsar’s MIT license
- attribution and notices
- Git history
- the inherited Linux/CUDA implementation
- upstream architectural contributions

The Apple Silicon runtime, MLX execution backend, portable storage path, architecture-oracle methodology, research framework, and Apple unified-memory work are developed in **PulsarMLX by Mahdi Hedhli and contributors**.

See [NOTICE.md](NOTICE.md). Upstream authors do **not** endorse this repository.

## Lineage

```text
DwarfStar / ds4
       ↓
  NeutronStar
       ↓
     Pulsar
       ↓
   PulsarMLX
```

- [ds4 / DwarfStar lineage](https://github.com/antirez/ds4) explored giant-model inference (including early Mac work)
- [NeutronStar](https://github.com/giannisanni/neutronstar) evolved that line
- [Pulsar](https://github.com/giannisanni/pulsar) became an independent Rust/CUDA giant-MoE engine
- **PulsarMLX** carries the lineage onto Apple Silicon through MLX

CUDA kernel heritage from ds4/ggml remains MIT-notified in [LICENSE](LICENSE).

## Capability status

| Capability | Status |
| --- | --- |
| Apple MLX GPU execution | ✅ Verified |
| Portable positional GGUF access | ✅ Verified |
| Q8_0 reference / architecture execution | ✅ Verified |
| Real Qwen router (layer 0) | ✅ Verified |
| Real expert MLP | ✅ Verified |
| Top-8 MoE aggregation | ✅ Verified |
| Complete MoE residual block | ✅ Verified |
| Attention (layer 0) | ✅ Verified |
| Complete transformer layer | ✅ Verified |
| Full 48-layer Qwen execution | ✅ Verified |
| Full vocabulary logits | ✅ Verified |
| Deterministic greedy token | ✅ Verified |
| Bounded generation | ✅ Verified |
| Architecture CPU oracle | ✅ Verified |
| Evidence / claims / reviewer indexes | ✅ Verified |
| Optimized MLX-only generation | 🚧 |
| KV-cached decode | 🚧 |
| GLM-5.2 full stack (research ladder) | ✅ C01–C11 committed (Python/NumPy reference path) |
| GLM-5.2 Rust-native runtime (F017) | 🚧 In progress on feature branches; not merged, not claimed |
| GLM-5.3-Flash unpruned paged/persistent serving (research) | ✅ Measured candidate `971db9c1` (Python/MLX); see [results](docs/glm53-flash/persistent-serving-results.md) |
| OpenAI-compatible serving on Apple | 🚧 (Linux `pulsar-serve` exists upstream; macOS path not claimed) |
| Production readiness | ❌ Not claimed |
| Production tokens/sec | ❌ Not claimed |

## The next giant: GLM-5.2

Feature **016** (`016-glm52-full-execution`) targets **Unsloth GLM-5.2 UD-IQ2_XXS** multi-shard GGUF on **M1 Ultra internal SSD only**, under a frozen protocol.

**From frozen contract + checkpoint identity** ([`docs/architecture/GLM52_CONTRACT.md`](docs/architecture/GLM52_CONTRACT.md), [`docs/validation/glm52-checkpoint.json`](docs/validation/glm52-checkpoint.json)):

| Field | Value |
| --- | --- |
| Architecture | `glm-dsa` (MLA + DSA) |
| Layers | **79** |
| Experts | **256** routed, top-**8**, **1** shared |
| Embedding | **6144** |
| Quant | UD-IQ2_XXS, 6 shards |
| Checkpoint size | **238,458,632,928** bytes (~222 GiB) |
| Family scale (published) | ~744B total / ~40B active per token (family description; structure above is what we freeze) |

GLM is the model that **forces** SSD-backed expert residency rather than “fit the whole quant in RAM.”

### Deepest **committed** GLM boundary

| Boundary | Committed status |
| --- | --- |
| Disk admission + checkpoint identity | ✅ |
| Catalog (1809 tensors, 0 bad offsets) | ✅ C01 |
| Dense primitives | ✅ C02 |
| Real router (layer 3 probe) | ✅ C03 |
| Single expert + shared | ✅ C04 |
| MoE aggregate | ✅ C05 |
| MLA (layer 0) | ✅ C06 |
| DSA policy / short-ctx range-fill | ✅ C07 |
| Complete dense layer 0 | ✅ C08 |
| Single-token **79-layer** depth ladder (finite) | ✅ C09 |
| Full-vocab logits after 79 layers | ✅ C10 |
| Multi-token greedy generation | ✅ C11 frozen golden sequence; vectorized P1 prefix also committed |
| MLX-only performance | ❌ Not claimed |

Evidence: [`docs/research/glm52/`](docs/research/glm52/) · ledger: [`docs/research/glm52/CLAIMS_LEDGER.md`](docs/research/glm52/CLAIMS_LEDGER.md).

**Not claimed:** GLM product support, generation quality, tok/s, M2 Max, external RAID, or CUDA bit-parity.

### Rust-native runtime track (F017)

The shipping architecture for GLM-5.2 is a Rust-native runtime with no required Python hot path ([strategy](docs/roadmap/PULSARMLX_STRATEGY.md)). Its work lives on `feat/017-rust-native-inference-runtime`. State on 2026-09-20: the bounded one-token native executor (Rust + MLX bridge) **executed the real checkpoint and produced token 154820 for prompt 9703, equal to the corrected full-checkpoint oracle** (Event 06), under a human-approved one-shot (attempt 2; attempt 1 on 2026-08-22 had failed against an expected token later proven to come from a defective decoder family). Before the run, the native decoders were shown bit-identical to that oracle's independent decoders on all 11 checkpoint formats and the native graph matched it on the synthetic differential family. One token took 1003.6 s (704 s of shard identity rehash over ~238 GB plus a 299 s forward pass) — a correctness event, not a performance figure. Multi-token native generation, tokenizer/template handling and a CLI loop do not exist yet; every real-checkpoint run is human-gated; formal feature closeout requires a human approval that has not been granted. See the [attempt-2 readiness and outcome note](https://github.com/MahdiHedhli/PulsarMLX/blob/e38d002e54b5552966ccb7a586c2b0cc23b47e08/docs/architecture/reviews/f017-native-attempt-2-readiness-20260920.md). No native GLM-5.2 execution is committed on the default branch. The historical Python/NumPy research ladder above is banked evidence, not the native runtime.

## GLM-5.3-Flash: unpruned paged / persistent serving (research, 2026-09-20)

A separate research track ran the **unpruned** `GLM-5.3-Flash-MLX-mixed-4_8bit` (288 routed experts, top-8, 42 MoE layers, ~170 GB of experts) on a Mac Studio M1 Ultra 128 GB by paging experts through a 60 GB wired slot store, first as a CLI and then as a persistent OpenAI-style research server (Python/MLX; commit `971db9c1`). Headline results, all relative to a fresh-process run of the same paged path with the same corrected stop policy: token-identical outputs on 120/120 sealed tasks, 119/119 relative task retention (exact 95 % lower bound 0.9724 on group retention, scope-limited), exact-repeat request latency 12–15 % lower and A-B-A 9–13 % lower (a prefill effect; decode stays 2.6–3.3 tok/s because the budget holds ~35 % of the experts), and a 6.03 h single-process soak segment with 0 failed requests. The round also root-caused the `<|user|>`-after-answer termination fault (loader without eos ids) and fixed it. Full tables, definitions, the soak usability clarification and limitations: [`docs/glm53-flash/persistent-serving-results.md`](docs/glm53-flash/persistent-serving-results.md). Deployment authorization was not granted; nothing replaced a default service. A follow-on round on 2026-09-20 profiled decode (66 % cold expert reads), simulated the capacity curve and then raised the expert budget: **70e9 bytes (117 slots per layer) is now the recommended configuration**, with 18/18 token-identical paired runs, decode +9–17 % (mean +13.4 %), decode misses/token −16.4 %, peak MLX memory +10.107 GB and an 80-request server soak with 0 failed requests; 80e9 is not admitted on this host. Streaming the prefill outside the store was measured and is a negative result (identity failure from MLX's kernel selection, slower prefill, no reclaimable budget), as are speculative/union batching and request batching, which do not reduce expert I/O.

## Performance: not the point yet

Correctness has been established **before** optimization.

The full-Qwen research path often runs **CPU oracle and MLX**, and may replay more work than a production decoder. Those timings (e.g. dual 48-layer stack ≈962 s under F015) are **validation timings**, not advertised inference performance.

Optimization roadmap (intended order):

1. MLX-only execution
2. KV caching
3. Incremental decode
4. Expert residency + prefetch
5. Bounded SSD streaming
6. Cache-aware scheduling
7. Serving

No tokens/sec are published until a committed benchmark meets the evidence rules.

## Quick start

### Requirements

- Apple Silicon Mac (arm64)
- Recent macOS, Xcode CLT
- Rust toolchain (`cargo`)
- Python 3.12+ with MLX for worker-backed checks (see `python/` lockfiles)

### Clone

```sh
git clone https://github.com/MahdiHedhli/PulsarMLX.git
cd PulsarMLX
```

### Baseline

```sh
cargo check --workspace --all-targets
cargo test --workspace --no-fail-fast
```

### Fixture / device validation (no multi-hundred-GB download)

```sh
PYTHONPATH=python uv run python -m unittest discover \
  -s python/pulsar_mlx_worker/tests -v

cargo run -p mlx-backend --bin pulsar-mlx -- device-smoke \
  --backend apple-mlx --device gpu \
  --evidence "${TMPDIR:-/tmp}/pulsarmlx-device-smoke.json"

cargo run -p mlx-backend --bin pulsar-mlx -- validate-fixtures \
  --manifest fixtures/mlx/manifest.json \
  --evidence "${TMPDIR:-/tmp}/pulsarmlx-tensor-fixtures.json"

cargo run -p mlx-backend --bin pulsar-mlx -- validate-synthetic-moe \
  --fixture fixtures/mlx/routed-moe-v1.json \
  --evidence "${TMPDIR:-/tmp}/pulsarmlx-synthetic-moe.json"

cargo test -p stream --test positional_source
```

Real-checkpoint research runs need an external GGUF, identity checks, and the feature’s frozen protocol. Weights stay **out of Git**. See [docs/validation/README.md](docs/validation/README.md) and [specs/001-apple-silicon-mlx/quickstart.md](specs/001-apple-silicon-mlx/quickstart.md).

## Repository map

```text
crates/backend/          backend-neutral contracts
crates/mlx-backend/      Apple MLX runtime
crates/stream/           portable / expert storage
crates/quant/            quantization + CPU reference ops
crates/engine/           inherited Pulsar engine (CUDA/Linux path)
crates/serve/            inherited OpenAI-compatible serve (Linux)
python/                  MLX worker integration
scripts/research/        oracles, parity runners, GLM research tools
docs/research/           evidence, claims, reviewer indexes
docs/architecture/       architecture contracts (e.g. GLM-5.2)
docs/roadmap/            high-level product and runtime strategy
docs/validation/         Apple bring-up evidence index
docs/upstream/           inherited Pulsar docs (not Apple results)
specs/                   Spec Kit feature history
```

## Reproducibility

A public PulsarMLX claim should resolve to:

1. a **commit**
2. **raw evidence**
3. an **oracle / reference contract**
4. a **reproduction command**

Start here:

| Artifact | Path |
| --- | --- |
| Apple runtime report | [PULSARMLX_APPLE_RUNTIME_REPORT.md](PULSARMLX_APPLE_RUNTIME_REPORT.md) |
| Experiment protocol | [docs/research/EXPERIMENT_PROTOCOL.md](docs/research/EXPERIMENT_PROTOCOL.md) |
| Claims ledgers | [docs/research/CLAIMS_LEDGER*.md](docs/research/) |
| Reviewer index | [docs/research/REVIEWER_INDEX.md](docs/research/REVIEWER_INDEX.md) |
| Raw evidence | [docs/research/raw/](docs/research/raw/) |
| Validation index | [docs/validation/README.md](docs/validation/README.md) |
| GLM research | [docs/research/glm52/](docs/research/glm52/) |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) |

## Inherited upstream material

Detailed Pulsar Linux/CUDA model catalogs, CUDA benchmark tables, acquisition notes, and historical roadmap text live in:

**[docs/upstream/PULSAR_INHERITED.md](docs/upstream/PULSAR_INHERITED.md)**

Those are **historical/inherited Pulsar results**, not PulsarMLX Apple benchmarks.

## Roadmap

The single high-level source of truth is
**[docs/roadmap/PULSARMLX_STRATEGY.md](docs/roadmap/PULSARMLX_STRATEGY.md)**.

1. Finish Feature 016's measured mixed-quant, P1, and P2 optimization gates.
2. Begin the proposed Rust-native runtime only from that committed baseline.
3. Qualify direct quantized Metal work in measured format order.
4. Add the product CLI and serving surface only after the local runtime is stable.

## License & attribution

MIT licensed. See [LICENSE](LICENSE).

PulsarMLX is derived from **Pulsar** by **Giannis Anni and contributors** and preserves applicable upstream notices and history.

**Apple Silicon / MLX development:** Mahdi Hedhli and contributors.

See [NOTICE.md](NOTICE.md) for detailed attribution.
