# Upstream donor: ssd-llm

**Status**: independently qualified for *design and selective adaptation*  
**Decision**: **do not depend on ssd-llm as a runtime**; **borrow design + optionally vendor small pure modules** under MIT with attribution.

## Pin

| Field | Value |
| --- | --- |
| Repository | https://github.com/quantumnic/ssd-llm |
| Upstream identity | README/Cargo point at `redbasecap-buiss/ssd-llm`; clone via quantumnic remotes to the same tree |
| Branch | default (`main` / depth-1 tip at qualification) |
| Commit SHA | `d0afcf0f109a39b6aa04552cba123ccf58842333` |
| Package version | 1.39.0 |
| License | **MIT** — Copyright (c) 2026 Nicola Spieser |
| Platforms | Primary: **macOS** (Metal + Mach memory APIs); builds as a single binary crate |

## Build / test

| Item | Observation |
| --- | --- |
| Build | `cargo check` / `cargo build --release` (Metal deps on macOS) |
| Lib tests | **None** — crate is `[[bin]]` only; `cargo test --lib` fails with “no library targets” |
| Unit tests | Embedded `#[cfg(test)]` modules inside `src/**` (chat, MoE, mmap pool, sliding window, quantized KV, etc.) — run via `cargo test --bins` |
| Benchmarks | Criterion bench `benches/inference_bench.rs`; `BENCHMARKS.md` claims M4 numbers vs llama.cpp |
| Scripts | `scripts/compare_benchmarks.sh` |

## Claimed features (README — not all verified as production-quality)

Layer streaming, LRU layer cache, mmap + madvise, Metal compute, GGUF, tokenizer, Ollama/OpenAI API, speculative decoding, paged attention, KV spill/quant, MoE, memory pressure, block swap, and a large surface of sampling/chat features.

**Qualification rule**: inspect implementation quality, not marketing feature list.

## Module map (relevant)

| Path | Role |
| --- | --- |
| `src/ssd/streamer.rs` | mmap load, dequant to f32, layer load, madvise prefetch/evict |
| `src/ssd/prefetch.rs` | look-ahead layer WILLNEED + DONTNEED behind |
| `src/ssd/mmap_pool.rs` | budgeted active-region registry |
| `src/ssd/memory_pressure.rs` | macOS `host_statistics64` pressure tiers |
| `src/ssd/block_swap.rs` | KV block swap file |
| `src/model/cache.rs` | layer LRU / pin |
| `src/inference/kv_cache.rs` | standard KV |
| `src/inference/moe.rs` | softmax top-k MoE (Mixtral-style; **not** GLM sigmoid+shared) |
| `src/metal/*` | Metal shaders + large `compute.rs` |

## Subsystem classification

| Subsystem | Class | Notes |
| --- | --- | --- |
| mmap + madvise WILLNEED/DONTNEED | **B** | Useful pattern; reimplement behind PulsarMLX store API |
| Layer LRU / pin budget | **B** | Map to **expert** (not layer) residency for GLM |
| Prefetch look-ahead | **B** | Conceptual; GLM needs expert-id / router-informed prefetch |
| Memory pressure monitor | **A/B** | Solid design for macOS; adapt public-safe telemetry |
| Block swap / paged KV | **C** | Useful ideas; GLM needs **MLA latent + DSA state**, not vanilla KV pages |
| Quantized KV spill | **C** | Design only unless profiling needs it |
| Metal matmul/dequant | **D/E** | Parallel stack to MLX; do **not** adopt as primary compute path |
| MoE router | **E** | Softmax Mixtral-style; conflicts with GLM contract |
| Full server / Ollama API | **E** | Out of weekend scope |
| Speculative decoding, vision, LoRA, grammar | **E** | Irrelevant to current sprint |
| README breadth (1.39 “everything”) | **D** | Feature surface >> tested integration depth; treat as aspirational |

## Dependency recommendation

1. **No Cargo dependency** on ssd-llm (binary-only, different architecture stack, Metal-first not MLX).
2. **Selective adaptation**: pressure monitor, budgeted cache policy, madvise hints — reimplemented in PulsarMLX with tests and attribution.
3. **Design borrow**: SSD as tiered memory, prefetch/evict, fail closed under pressure.

See `SSD_LLM_SYNC.md` and `docs/research/ssd-llm/QUALIFICATION_REPORT.md`.

## Attribution

Any adapted code must preserve MIT notice for Nicola Spieser / ssd-llm. Upstream authors do not endorse PulsarMLX.
