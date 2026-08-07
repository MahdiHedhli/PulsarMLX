![PulsarMLX](docs/assets/pulsarmlx-poster.png)

# PulsarMLX

**Giant MoE inference on Apple Silicon.**

PulsarMLX is an experimental Apple Silicon inference engine for oversized Mixture-of-Experts models. It combines MLX GPU execution, unified-memory-aware expert residency, SSD-backed tensor streaming, and an architecture-level correctness framework designed to make models larger than available memory practical on Macs.

It is **not** production-ready. Claims below are limited to committed evidence.

## Project identity

> PulsarMLX began as an Apple Silicon derivative of [Pulsar](https://github.com/giannisanni/pulsar), created by Giannis Anni and contributors. It preserves Pulsar's MIT license, Git history, original Linux/CUDA runtime, and important giant-MoE architecture work.
>
> The Apple Silicon runtime, MLX execution backend, portable storage path, architecture-oracle methodology, reproducible evidence framework, and ongoing unified-memory/SSD streaming work are developed independently in PulsarMLX by Mahdi Hedhli and contributors.

See [NOTICE.md](NOTICE.md) for complete attribution. PulsarMLX is an independent derivative; upstream authors do not endorse this repository.

## Lineage

`DwarfStar → NeutronStar → Pulsar → PulsarMLX`

PulsarMLX is the Apple Silicon branch of that engineering lineage. It still carries Pulsar's GGUF/streaming design heritage while hosting a substantially independent MLX runtime and validation framework.

## It runs a real model

**Verified baseline (committed evidence):** [Qwen3-30B-A3B](https://huggingface.co/Qwen/Qwen3-30B-A3B-GGUF) **Q8_0** on **Apple MLX GPU**, under the architecture contract *Q8_0 weight dequant × f32 activation*. Research freeze tag: `v0.2.0-qwen30b-e2e-research`.

On that checkpoint, the architecture path has been exercised end-to-end:

| Milestone | What was verified |
| --- | --- |
| Device / tensors | Real Apple MLX GPU execution (no silent CPU fallback in admitted runs) |
| Router | Real layer-0 router; deterministic top-8 expert IDs and order |
| Experts | Complete real expert MLP (gate / up / SiLU-SwiGLU / down) |
| Aggregation | Top-8 routed expert aggregation |
| MoE block | Complete MoE residual block `y = residual + MoE(RMSNorm(·))` |
| Attention | Real layer-0 attention residual (`ffn_inp`) |
| Layer | Complete transformer layer-0 (attention + MoE) |
| Full model | Complete **48-layer** stack |
| Logits | Full vocabulary logits after `output_norm` + `output.weight` |
| Parity | Architecture-level **CPU ↔ MLX** agreement |
| Decode | Matching greedy token (CPU = MLX) |
| Generation | Bounded short greedy generation |

**Strongest published numerical results** (MLX vs independent architecture CPU oracle; see evidence links):

| Boundary | Approx. max abs error | Evidence |
| --- | ---: | --- |
| Single expert (weighted MLP) | **~7.4×10⁻⁸** | [F003](docs/research/raw/003-expert-mlp/) |
| Top-8 aggregation | **~6.2×10⁻⁸** | [F004](docs/research/raw/004-top8-moe/) |
| Complete layer-0 | **~1.1×10⁻⁷** | [F010](docs/research/raw/010-011-layer-stack/) |
| Multi-layer peak (L3) | **~4.3×10⁻⁴** | [F011 summary](docs/research/raw/010-011-layer-stack/f010-f011-layer-stack-summary.json) |
| Final layer (L47) | **~1.8×10⁻⁴** | same |
| Full logits | **~7.6×10⁻⁶** | [F012](docs/research/raw/012-013-logits-greedy/) |
| Top-1 / top-5 | agree (CPU ↔ MLX) | [F012](docs/research/raw/012-013-logits-greedy/), [F013](docs/research/raw/012-013-logits-greedy/f013-greedy-token-0001.json) |
| Greedy token | **320** on both backends | [F013](docs/research/raw/012-013-logits-greedy/f013-greedy-token-0001.json) |
| Short generation | prompt `[0, 1]` → `[320, 16]`; full `[0, 1, 320, 16]` | [F014](docs/research/raw/014-short-prompt-gen/) |

Primary narrative report: **[PULSARMLX_APPLE_RUNTIME_REPORT.md](PULSARMLX_APPLE_RUNTIME_REPORT.md)**.  
Claims and raw evidence: [docs/research/](docs/research/) (ledgers `CLAIMS_LEDGER_*.md`, raw trees F002–F015).

**Not claimed:** production tokens/sec, serving quality, llama.cpp bit-parity, multi-host CI on the full GGUF, or GLM-5.2 full-model support.

## Architecture oracle, not implementation mimicry

PulsarMLX validates MLX execution against an **independent architecture-level CPU oracle**.

During Qwen validation, llama.cpp's fused Q8_0 path differed by approximately **3.4×10⁻³** (max abs) from that oracle because its Q8_0 × Q8_0 matmul **requantizes activations**, while the PulsarMLX architecture contract uses **Q8_0 weight dequantization × f32 activation**.

PulsarMLX and the independent CPU architecture oracle agree around the **10⁻⁷** scale at isolated MoE boundaries (and remain within frozen multi-layer tolerances through 48 layers).

Therefore:

- **Architecture-level numerical correctness** is the contract
- **llama.cpp bit-parity is not a project goal**
- Implementation-specific fused-kernel behavior is **documented**, not blindly reproduced

llama.cpp is not “wrong”; it implements a different (fused) quant contract. Feature 008 records the root cause: [docs/research/raw/008-f006-root-cause/](docs/research/raw/008-f006-root-cause/). Feature 006 llama bit-parity remains a **preserved rejection**.

## Why PulsarMLX?

Apple Silicon combines:

- GPU compute
- high-bandwidth unified memory
- fast internal NVMe
- MLX
- CPU and GPU access to the same memory architecture

Giant MoE models are unusually interesting on this platform because **only a fraction of total parameters are active per token**. PulsarMLX explores whether expert weights can be intelligently resident, cached, prefetched, or streamed from SSD while the active graph executes through MLX—without inventing throughput that has not been measured under a frozen protocol.

## Architecture

```text
                    ┌──────────────────────┐
                    │      Model / GGUF    │
                    └──────────┬───────────┘
                               │
                     positional / mapped I/O
                               │
                    ┌──────────▼───────────┐
                    │   Expert Storage     │
                    │ cache • stream • map │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   PulsarMLX Runtime  │
                    │ routing • residency  │
                    │ budgets • telemetry  │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │         MLX          │
                    │  Apple GPU execution │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   Apple Silicon GPU  │
                    │    Unified Memory    │
                    └──────────────────────┘
```

The research stack additionally keeps a pure CPU architecture oracle for parity gates. Expert addressing, admission, and telemetry scaffolding are developed for streaming budgets; fail-closed modes refuse silent CPU fallback and full-model materialization beyond declared limits (see Feature 016 research tools and [docs/research/glm52/EXPERIMENT_PROTOCOL.md](docs/research/glm52/EXPERIMENT_PROTOCOL.md)).

## GLM-5.2 (active research — not full support)

Feature **016** (`016-glm52-full-execution`) targets **Unsloth GLM-5.2 UD-IQ2_XXS** multi-shard GGUF on M1 Ultra internal SSD only, under a frozen experiment protocol.

**Committed so far (architecture path; see [docs/research/glm52/CLAIMS_LEDGER.md](docs/research/glm52/CLAIMS_LEDGER.md)):**

- Disk admission + checkpoint identity + complete multi-shard catalog (1809 tensors)
- Dense primitives, real router / single expert / MoE aggregate probes
- Layer-0 MLA + DSA short-context path + complete dense layer-0 residual
- Checkpoint-free CI suite (25 tests)

**Not claimed:** full 79-layer generation quality, production tok/s, M2 Max or external RAID, or “GLM support” as a product feature until C09–C11 and MLX-only performance close under the frozen protocol.

Contract sketch: [docs/architecture/GLM52_CONTRACT.md](docs/architecture/GLM52_CONTRACT.md).

## Evidence map

| Document | Role |
| --- | --- |
| [PULSARMLX_APPLE_RUNTIME_REPORT.md](PULSARMLX_APPLE_RUNTIME_REPORT.md) | Qwen F002–F015 narrative |
| [docs/research/](docs/research/) | Claims ledgers, raw JSON, figures, protocol |
| [docs/validation/](docs/validation/) | Device, fixture, and bounded model-slice evidence |
| [docs/apple-silicon/](docs/apple-silicon/) | Compatibility and known limitations |
| [NOTICE.md](NOTICE.md) / [LICENSE](LICENSE) | Attribution and MIT terms |

## Verify on Apple Silicon

Host probes (no install required):

```sh
sw_vers
uname -m
sysctl -n hw.memsize
df -h .
xcode-select -p
rustc -vV
cargo -V
```

Workspace baseline:

```sh
cargo check --workspace --all-targets
cargo test --workspace --no-fail-fast
```

Checkpoint-free GLM research suite (no multi-hundred-GB model required):

```sh
# from a Python env with the research path on PYTHONPATH
python -m pytest scripts/research/tests/test_glm52_checkpoint_free.py -q
```

Real-checkpoint research runs require an external GGUF (not in Git), identity checks, and the frozen protocol for the feature under test. Model files stay outside the repository.

Spec Kit features live under `specs/` (001–015 Qwen ladder; 016 GLM). Continue from the first incomplete task in the active feature; do not widen claim scope without new evidence.

## Inherited upstream (Linux + CUDA)

This repository **preserves** Pulsar's Linux/CUDA giant-MoE engine, GGUF tooling, tokenizer paths, and related history. Upstream model tables, CUDA tok/s figures, and multi-architecture bring-up notes remain **Pulsar / Linux+CUDA documentation**—they have **not** been re-measured as PulsarMLX Apple results.

For the original engine, models, and CUDA performance methodology, see [giannisanni/pulsar](https://github.com/giannisanni/pulsar).

## License

MIT. Copyright and third-party notices: [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).

Portions of retained CUDA kernels derive from `ds4` and `ggml` (MIT); their notices remain in affected source files.
