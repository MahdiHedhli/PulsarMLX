![PulsarMLX](docs/assets/pulsarmlx-poster.png)

# PulsarMLX

**Giant MoE inference on Apple Silicon.**

PulsarMLX is building an Apple Silicon runtime for Mixture-of-Experts models that do not fit in RAM. Its current targets are **GLM-5.3 and GLM-5.3 Flash**, with Flash leading the work toward practical local use. The selected [PipeNetwork mixed-precision Flash checkpoint](https://huggingface.co/pipenetwork/GLM-5.3-Flash-MLX-mixed-4_8bit) is reported at **181.9 GB**, larger than either the 128 GB Mac Studio or 64 GB MacBook Pro. The design keeps attention state and frequently used experts in unified memory while streaming other expert weights from SSD as routing requires them. Useful quality at usable speed remains the goal, not a claimed result.

Correctness comes before performance claims. The GLM-5.2 IQ2_XXS reference completed all **79 layers in two independent oracles**: both selected token **154820**, with identical ordered top-32 IDs and route structure, and maximum absolute error **2.45e-6** within the frozen numerical contract. This is [bounded reference evidence](https://github.com/MahdiHedhli/PulsarMLX/blob/c23e58ec87c7e73a23cf37ac64aa4dee6c45896f/docs/architecture/reviews/evidence/f017-event06-v12-sequence43-terminal-success-evidence-v1.json), not bit-identical floating-point output, a throughput benchmark, or validation of GLM-5.3 or Flash. See [model targets and evidence boundaries](docs/roadmap/MODEL_TARGETS.md).

The current research/reference execution path uses Python, NumPy, and MLX. The
planned shipping runtime is Rust-native with no required Python process; direct
quantized Metal expert kernels are roadmap work, not a verified current
capability. See the [PulsarMLX strategy](docs/roadmap/PULSARMLX_STRATEGY.md).

PulsarMLX approaches that through:

- **MLX** as the Apple Silicon execution layer
- **unified memory** shared by CPU and GPU
- **SSD-backed expert residency** rather than whole-checkpoint RAM residency
- **expert caching** with an explicitly admitted byte budget
- **prefetching** of experts the router is about to need
- **storage-aware execution** that treats I/O as a first-class scheduling term
- **correctness-first qualification**: every capability is bounded by committed evidence before it is claimed

It began as an Apple Silicon derivative of [Pulsar](https://github.com/giannisanni/pulsar). The Apple path has grown into a substantially independent runtime: MLX backend, portable storage, architecture-oracle methodology, research/evidence framework, and unified-memory-aware residency work—while still preserving Pulsar’s MIT license, Git history, and Linux/CUDA implementation.

> [!IMPORTANT]
> PulsarMLX is experimental research software. Verified capabilities are explicitly bounded by **committed** evidence. Correctness has been prioritized before performance optimization.

> **DON'T PANIC.** The giant model does not need to fit entirely in memory.

## Status at a glance (2026-09-20)

Every claim below is classified, and every number is traceable to the document cited beside it. The five columns are the only vocabulary this project uses for capability status.

| Track | ✅ Verified (independent evidence) | 📏 Measured (observed, not independently qualified) | 🧪 Experimental / research | 🗺️ Planned | ❌ Not implemented / not claimed |
| --- | --- | --- | --- | --- | --- |
| **Qwen3-30B-A3B Q8_0** — frozen Apple MLX baseline | full 48-layer execution, real router, expert MLP, top-8 aggregation, MoE residual, attention, full-vocab logits, greedy token 320, bounded generation, all against a CPU architecture oracle ([boundaries](#exact-numerical-boundaries-mlx-vs-architecture-cpu-oracle)) | validation timings only (never advertised) | — | — | production tok/s, optimized MLX-only serving, KV-cached decode, llama.cpp bit-identical output |
| **GLM-5.2 UD-IQ2_XXS** — Python/NumPy research ladder | C01–C11 committed boundaries ([ledger](docs/research/glm52/CLAIMS_LEDGER.md)) | — | — | — | MLX-only performance |
| **GLM-5.2 — F017 Rust-native runtime** | one token on the real 222 GiB checkpoint (token **154820**, attempt 2); decoder differential 0 ULP over 107,502 values per seed across 11 formats; graph differential 6/6; multi-position temporal graph 6/6 on synthetic fixtures; native text CLI on synthetic fixtures ([status](docs/architecture/f017-native-runtime-status.md)) | real-checkpoint Stage A positions 1–7; Stage B1 text generation (` 17 times table`); Stage B2 chat template end to end over 24 positions; Stage A/B timings | — | qualified multi-token generation against an independent oracle (execution of Stages A, B1 and B2 is already measured) | answer quality, tokens/sec, the sparse `glm-dsa` indexer, validated RoPE pairing, formal F017 closeout |
| **GLM-5.3-Flash mixed-4/8, unpruned** — Python/MLX paged research | 120/120 token-identical task pairs against the fresh-process paged reference, and 18/18 token-identical runs across the paired 60e9-vs-70e9 CLI budget ladder ([results](docs/glm53-flash/persistent-serving-results.md)) | decode 2.6–3.3 tok/s at 60e9 and 3.06–4.20 tok/s at the admitted 70e9 ceiling; 6.03 h soak segment at 60e9; 1.33 h / 80-request soak at 70e9 | persistent OpenAI-style research server, paged expert residency, expert-cache ceiling ladder | a 6 h soak segment at 70e9 (**has not run**) | production readiness; 80e9 on a 128 GB host; this is **not** the Rust-native runtime |
| **Pruned REAP variants** (REAP50 etc.) | — | resident serving experiments ([notes](docs/glm53-flash/performance-notes.md)) | — | — | **not the fidelity target**; never compared with unpruned results |
| **OpenAI-style synthetic serving crate** | — | — | on branch [`feat/openai-serving`](https://github.com/MahdiHedhli/PulsarMLX/tree/feat/openai-serving) only, **not on main**; its own gate `Serving synthetic qualification` is **red at head** (run [`35086336439`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/35086336439)) | merge once that gate is green | **not on main**; it serves **no model** even on its branch — a protocol and lifecycle harness, not inference |
| **Native MLX checkpoint ingestion** (the next target) | — | — | — | Safetensors ingestion + MLX affine quantization + expert residency, for `PipeNetwork GLM-5.3-MLX-mixed-4_8bit` and `…-Flash-…` ([below](#next-target-native-mlx-checkpoints)) | **not started** |

None of this is a production runtime. The Python/MLX Flash research path is **not** the Rust-native shipping architecture and does not complete it.

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

**Baseline (committed evidence):** [Qwen3-30B-A3B](https://huggingface.co/Qwen/Qwen3-30B-A3B-GGUF) **Q8_0** on **native Apple MLX GPU**, under the architecture contract *Q8_0 weight dequantization × f32 activation*. Research freeze tag: [`v0.2.0-qwen30b-e2e-research`](https://github.com/MahdiHedhli/PulsarMLX/tree/v0.2.0-qwen30b-e2e-research).

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

## Runtime design

The diagram describes the GGUF research path and intended residency architecture.
Optimized caching, prefetch, direct quantized Metal execution and serving are not
universally shipped capabilities. Flash additionally needs a model-specific
MLX/Safetensors adapter; the existing GGUF path is not a drop-in implementation.

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
| Optimized MLX-only generation | 🗺️ Planned |
| KV-cached decode | 🗺️ Planned |
| GLM-5.2 full stack (research ladder) | ✅ C01–C11 committed (Python/NumPy reference path) |
| GLM-5.2 Rust-native one token (real checkpoint) | ✅ Verified — token 154820, [F017 status](docs/architecture/f017-native-runtime-status.md) |
| GLM-5.2 Rust-native multi-position decode | ✅ Verified **on synthetic fixtures** against an independent reference. On the real checkpoint only **position 0** is verified — it reproduces the banked one-token receipt bit for bit; **positions 1–7 are 📏 measured, not qualified** |
| GLM-5.2 Rust-native text generation (real checkpoint, no Python inference) | 📏 Measured — `17 times 6 equals` → ` 17 times table`, four tokens from the real 222 GiB checkpoint with no Python in the inference path. Not independently qualified: no multi-token oracle exists for this checkpoint |
| GLM-5.2 Rust-native chat template (real checkpoint) | 📏 Measured — Stage B2 ran the checkpoint's own GLM template end to end over 24 positions with the full stop set. Executed, not independently qualified |
| GLM-5.2 native answer quality | ❌ Not claimed — four tokens from a 2-bit quantisation is not a task result |
| GLM-5.2 native tokens/sec | ❌ Not claimed |
| GLM-5.3-Flash unpruned paged/persistent serving (research) | 📏 Measured candidate `971db9c1` (Python/MLX); identity against the fresh-process paged reference is ✅ verified — see [results](docs/glm53-flash/persistent-serving-results.md) |
| GLM-5.3-Flash expert-cache budget | ✅ **70e9 is the admitted ceiling and the recommended server configuration** on the 128 GB host; the paged reference script's `--max-expert-cache-bytes` default remains 60e9. 80e9 is **not admitted** on a 128 GB host |
| OpenAI-style **synthetic** serving crate | ❌ **Not on main.** Branch-only on `feat/openai-serving`; its own gate is red at head (run `35086336439`). Protocol/lifecycle harness only — **serves no model** |
| OpenAI-compatible serving of a real model on Apple | 🗺️ Planned — Linux `pulsar-serve` exists upstream; the macOS path is **not implemented** and not claimed |
| Native Safetensors / MLX affine-quantized checkpoint ingestion | 🗺️ Planned, not started |
| Production readiness | ❌ Not claimed |
| Production tokens/sec | ❌ Not claimed |

## Large-model correctness reference: GLM-5.2

Feature **016** (`016-glm52-full-execution`) established the historical **Unsloth GLM-5.2 UD-IQ2_XXS** multi-shard GGUF research ladder on **M1 Ultra internal SSD only**, under its frozen protocol. That storage restriction belongs to this reference track, not the independent Flash bring-up on external NVMe.

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

### Historical Feature 016 committed boundaries

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

The later [F017 Sequence 43 reference](docs/roadmap/MODEL_TARGETS.md#glm-52-reference-evidence)
completed the corrected two-oracle comparison. Its six-shard identity census
recorded **238,458,632,928 bytes** (about **238.5 GB / 222.1 GiB**).
Exact numerical payload-read, mapping and fault counts were not separately
banked and remain unknown. [Prospective read-observation instrumentation](docs/research/f017/read-observation-publication-status.md)
does not backfill those historical counts.

### Feature 017: the Rust-native GLM-5.2 runtime

Feature 016 above is the research path: it executes GLM-5.2 through Python
tooling and an architecture oracle. Feature **017** is the native one — the
model runs from Rust, on MLX, with no Python process in the inference path.

**Current state — [`docs/architecture/f017-native-runtime-status.md`](docs/architecture/f017-native-runtime-status.md)**
(machine-readable: [`docs/glm52-native/native-runtime-summary.json`](docs/glm52-native/native-runtime-summary.json),
generated from the evidence records and checked in CI).

| Native boundary | Status |
| --- | --- |
| One token on the real 222 GiB checkpoint | ✅ token **154820** == the corrected oracle's expected token; 704.0 s identity rehash + 299.2 s for 79 layers and logits |
| Decoder differential vs the corrected oracle | ✅ 0 ULP over **107,502** values per seed, 11 formats |
| Full-graph differential vs the corrected oracle | ✅ 6/6 synthetic seeds |
| Multi-position attention, RoPE and retained state | ✅ 6/6 seeds vs an independent binary64 reference, logits max abs ≤ 1.5e-7 against a frozen 6.5e-3 threshold |
| Native text CLI (`f017-native-generate`) | ✅ tokenizer, GLM chat template, prefill, decode, stop semantics, streaming detokenisation |
| Multi-position decode on the **real checkpoint** | ✅ **position 0 only** — it reproduced the banked one-token receipt exactly, token **154820** and logits digest `db1456d8…`. The ladder ran eight positions with one retained state that grew to exactly 8 × 182,016 B; **positions 1–7 are 📏 measured, not qualified** (see the row below) |
| Text generation on the **real checkpoint** | 📏 Measured — `17 times 6 equals` → ` 17 times table`, four tokens, **no Python in the inference path**. Executed, not independently qualified |
| Chat template on the **real checkpoint** | 📏 Measured — Stage B2, 2026-09-21: `What is 17 times 6? Answer with the number only.` rendered to 21 tokens through the checkpoint's own GLM template with the full stop set installed, 24 positions, answer `**\n17 times `. It hit the four-token budget; **not** the arithmetic answer and no quality claim. Its record classifies later positions `MEASURED_NOT_QUALIFIED` |
| Positions after 0 on the real checkpoint | 📏 Measured, **not** qualified — no independent multi-token oracle exists for this checkpoint |
| Native tokens/sec | ❌ not claimed; the measured 0.0116 tok/s is this build's cold, uncached weight path, not a runtime capability |

```sh
cargo build -p f017-native --release --bin native_generate
./target/release/native_generate --model /path/to/checkpoint/root \
  --prompt "What is 17 times 6? Answer with the number only." --max-tokens 8
```

The answer goes to stdout and one diagnostics object to stderr.

**Unfinished, exactly as the status document lists it:**

| Not done | Status |
| --- | --- |
| Text generation on the real checkpoint | 📏 **Measured, not qualified.** Stage A (teacher-forced positions), Stage B1 (four generated tokens) and Stage B2 (the GLM chat template end to end) have all executed under the same approval. What is outstanding is qualification, not execution: no independent multi-token oracle exists for this checkpoint, so nothing past attempt 2's position 0 is qualified, and the formal Feature 017 closeout still awaits its human approval. |
| Performance baseline | **First real numbers, not a baseline.** No tokens-per-second figure is published **as a capability**; the measured cold-path rates in the [status document](docs/architecture/f017-native-runtime-status.md) are not decode rates. |
| Answer quality | **Not claimed, and B1 is not evidence of it.** Four tokens of raw-text continuation from a 2-bit quantisation is not a task result. |
| The checkpoint's RoPE pairing | **Declared, not validated.** B1 is consistent with `NeoxHalfSplit`, not proof of it; it is settled by the first approved multi-token run. |
| The sparse indexer | **Not implemented.** The runtime refuses sequences longer than `attention.indexer.top_k` rather than substituting dense attention beyond it. |
| Feature 017 formal closeout | **Pending the standing human approval.** Technical state and formal signoff are separate. |

There is also a known defect found by Stage B1: `--no-chat-template` currently
supplies an empty stop set, so a raw-text run terminates on `max-tokens` rather
than on the model's own terminal. Chat-template runs are unaffected.

## GLM-5.3-Flash: unpruned paged / persistent serving (research, 2026-09-20)

A separate research track ran the **unpruned** `GLM-5.3-Flash-MLX-mixed-4_8bit` (288 routed experts, top-8, 42 MoE layers, ~170 GB of experts) on a Mac Studio M1 Ultra 128 GB by paging experts through a 60 GB wired slot store, first as a CLI and then as a persistent OpenAI-style research server (Python/MLX; commit `971db9c1`). Headline results, all relative to a fresh-process run of the same paged path with the same corrected stop policy: token-identical outputs on 120/120 sealed tasks, 119/119 relative task retention (exact 95 % lower bound 0.9724 on group retention, scope-limited), exact-repeat request latency 12–15 % lower and A-B-A 9–13 % lower (a prefill effect; decode stays 2.6–3.3 tok/s because the budget holds ~35 % of the experts), and a 6.03 h single-process soak segment with 0 failed requests. The round also root-caused the `<|user|>`-after-answer termination fault (loader without eos ids) and fixed it. Full tables, definitions, the soak usability clarification and limitations: [`docs/glm53-flash/persistent-serving-results.md`](docs/glm53-flash/persistent-serving-results.md). Deployment authorization was not granted; nothing replaced a default service. A follow-on round on 2026-09-20 profiled decode (66 % cold expert reads), simulated the capacity curve and then raised the expert budget: **70e9 bytes (117 slots per layer) is now the recommended configuration**, with 18/18 token-identical paired runs, decode +9–17 % (mean +13.4 %) across 18/18 token-identical paired 60e9-vs-70e9 CLI runs, decode misses/token −16.4 %, peak MLX memory +10.107 GB and an 80-request server soak with 0 failed requests; 80e9 is not admitted on this host; 70e9 is the admitted ceiling and the recommended server configuration, while the paged reference script's default remains 60e9. A 6 h soak segment at the 70e9 budget **has not been completed**; the 70e9 exposure is 80 requests over 1.33 h against 335 requests over 6.03 h at 60e9.

**The decode I/O finding.** Decode is latency-bound on many small per-layer expert reads, not bandwidth-bound: at 60e9 about 66 % of instrumented decode time is spent in cold expert reads (266.7 ms/token, 3.0 ms per miss), and the reads are small and scattered rather than large and sequential. Read parallelism and coalescing therefore do not help much, and **capacity is the lever** — holding more experts resident is what removes the read, which is why the budget ladder (60e9 → admitted 70e9 ceiling) produced the gain and why 80e9 is **not admitted** on a 128 GB host.

**Negative results, retained on purpose.** Streaming the prefill outside the store is a negative result (identity failure from MLX's kernel selection between the plain and sorted `gather_qmm` kernels, slower prefill, no reclaimable budget); union/speculative batching and request batching are also negative, because they do not reduce expert I/O. The streaming-prefill code is merged here, default-off, and is **not** a candidate — it is kept so the measurement stays reproducible.

**This track is the Python/MLX research path** (`scripts/research/glm53_flash/`), **not the F017 Rust-native runtime.** It demonstrates the value of PulsarMLX's paged expert-residency architecture; it does not implement the shipping architecture, and no result here transfers to the native runtime as a claim.

## Next target: native MLX checkpoints

**Status: planned. Not implemented. Not started.**

The next major target is to consume MLX-native mixed-precision checkpoints directly:

- `PipeNetwork GLM-5.3-MLX-mixed-4_8bit`
- `PipeNetwork GLM-5.3-Flash-MLX-mixed-4_8bit`

The planned capability is the composition:

```text
Native Rust runtime
      +
Safetensors checkpoint ingestion
      +
MLX affine quantization
      +
PulsarMLX expert residency / streaming
      +
MLX execution
```

The goal is to consume these checkpoints **without converting them to GGUF** and **without requantizing their weights** — reading the published Safetensors shards and their MLX affine quantization parameters as they are.

Nothing in this section is implemented, measured or scheduled. It is stated here so the direction is legible, not to imply progress. The F017 Rust-native runtime described above operates on the GLM-5.2 GGUF checkpoint and does not read Safetensors today.

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

The `f017-native` crate links the pinned native MLX, so the two commands above
need it built and on `MLX_C_PREFIX` / `MLX_PREFIX` (see
[`scripts/ci/install_native_mlx.sh`](scripts/ci/install_native_mlx.sh)). Without
it, exclude that crate exactly as CI's baseline job does:

```sh
cargo check --workspace --exclude f017-native --all-targets
cargo test --workspace --exclude f017-native --no-fail-fast
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
**[docs/roadmap/PULSARMLX_STRATEGY.md](docs/roadmap/PULSARMLX_STRATEGY.md)**;
per-model boundaries live in [model targets](docs/roadmap/MODEL_TARGETS.md).

**This is a roadmap, not a claim of completion.** Items below the line that
separates done from planned have not been started. Nothing here is execution
authorization.

```text
Qwen Apple MLX baseline                        ✅ verified
        ↓
GLM-5.2 research execution                     ✅ committed ladder C01–C11
        ↓
F017 Rust-native GLM-5.2                       ✅ one token qualified; Stage A 1-7 and Stage B1 measured, not qualified
        ↓
GLM-5.3-Flash paged research                   📏 measured candidate (Python/MLX)
        ↓
Native Safetensors + MLX affine quantization   🗺️ planned, not started
        ↓
Native GLM-5.3 mixed 4/8                       🗺️ planned, not started
        ↓
Native GLM-5.3-Flash mixed 4/8                 🗺️ planned, not started
        ↓
Residency / caching / prefetch optimization    🗺️ planned
        ↓
KV / state optimization                        🗺️ planned
        ↓
Serving + broader hardware qualification       🗺️ planned
```

Studio F017 reference and instrumentation work and MacBook Flash bring-up are
independent tracks; neither implies a distributed inference system.

## License & attribution

Repository source is MIT licensed. See [LICENSE](LICENSE). Model weights and
external runtime components retain their own license terms; this repository's
license does not relicense them.

PulsarMLX is derived from **Pulsar** by **Giannis Anni and contributors** and preserves applicable upstream notices and history.

**Apple Silicon / MLX development:** Mahdi Hedhli and contributors.

See [NOTICE.md](NOTICE.md) for detailed attribution.
