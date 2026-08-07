# ssd-llm qualification report (weekend sprint)

**Date**: 2026-08-07  
**Pinned SHA**: `d0afcf0f109a39b6aa04552cba123ccf58842333`  
**License**: MIT (Nicola Spieser)  
**Source**: https://github.com/quantumnic/ssd-llm  

## Executive decision

**Do not take a runtime dependency on ssd-llm.**

**Do** treat selected subsystems as **design references** (and optionally vendor **small, pure** utilities after rewrite + tests):

- memory-pressure tiering
- budgeted cache admission
- madvise WILLNEED/DONTNEED around positional maps
- prefetch/evict lifecycle around compute

**Do not** adopt as-is:

- Metal compute path as primary (PulsarMLX is MLX-first)
- softmax Mixtral MoE as GLM router
- full Ollama server surface
- unverified “70B tok/s” marketing without independent re-measure

## What was inspected

Source tree under `src/ssd/`, `src/model/`, `src/inference/`, `src/metal/`, `Cargo.toml`, `LICENSE`, `README.md`, `BENCHMARKS.md`.

Notable implementation facts:

1. **Binary-only crate** — no `lib` target; unit tests live in-module under `#[cfg(test)]`.
2. **Layer streaming** loads tensors via mmap loader, dequants to **f32 vectors**, optional layer LRU in `model/cache.rs`.
3. **Prefetch** is simple look-ahead of next N **layers** via `madvise(WILLNEED)`, not router-aware expert prefetch.
4. **Memory pressure** uses Mach `host_statistics64` with Normal/Warning/Critical/Urgent budget fractions — clean structure for adaptation.
5. **MoE** implements dense gate + softmax top-k (Mixtral-like), not GLM sigmoid + shared expert + scale 2.5.
6. **KV / paged attention / block swap** assume classical K/V heads; GLM MLA latent + DSA selection require a different state machine.

## Build / test results

| Command | Result |
| --- | --- |
| `cargo test --lib` | Fail: no library targets |
| `cargo test --bins` | **472 passed, 1 failed** (`metal::compute::tests::test_metal_shader_compilation`) |
| `cargo check` | **OK** (dev profile) |
| Independent PulsarMLX benchmarks of ssd-llm tok/s | **Not run** (out of scope; README numbers not re-validated) |

The single failure is Metal shader compilation on this host; SSD/cache/pressure unit tests pass. Reinforces: use ssd-llm for **policy ideas**, not as the compute backbone.

## Mapping to PulsarMLX GLM sprint

| PulsarMLX need | ssd-llm mapping | Action |
| --- | --- | --- |
| Remove oracle from hot path | n/a | Local design |
| MLA/DSA incremental state | classical KV only | Reimplement for GLM |
| Expert residency | layer cache closest | Adapt policy to **expert slabs** |
| Prefetch | layer look-ahead | Expert-id prefetch after correct decode |
| Memory headroom | memory_pressure.rs | Reimplement public-safe + tests |
| Storage | mmap + madvise | Benchmark vs existing positional pread |

## Risks

- README claims far exceed the depth of integration tests.
- Metal path would fork compute strategy away from MLX evidence chain.
- Copying large trees without tests would threaten reproducibility.

## Conclusion

ssd-llm is a useful **macOS SSD-offload idea library**, not a drop-in GLM/MLX runtime. Qualification: **pass for design borrow; fail for wholesale dependency**.
