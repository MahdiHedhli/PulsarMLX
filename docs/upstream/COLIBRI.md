# Upstream design reference: Colibri

**Status**: qualified as a selective design reference; not a dependency

## Pin

| Field | Value |
| --- | --- |
| Repository | https://github.com/JustVugg/colibri |
| Revision | [`8f512fc8c2f48ffa18cd624cd4a5bcaae4a4abfc`](https://github.com/JustVugg/colibri/commit/8f512fc8c2f48ffa18cd624cd4a5bcaae4a4abfc) |
| Revision subject | `chore: version 1.5.0` |
| License | Apache License 2.0 |
| Declared author | JustVugg (`pyproject.toml`) |

The revision and license were verified from a fresh local clone on 2026-08-09.
Colibri's authors and contributors do not endorse PulsarMLX.

## Files reviewed

- `LICENSE`
- `docs/metal.md`
- `docs/METAL-M5MAX-PERF-REPORT.md`
- `c/backend_metal.h`
- `c/backend_metal.mm`
- `c/tests/test_backend_metal.mm`
- `c/expert_store.h`
- relevant GLM/expert residency and dispatch call sites in `c/colibri.c`
- stable-slab and batched-expert call sites in `c/inkling.c`

## Qualification

| Idea | Classification | PulsarMLX interpretation |
| --- | --- | --- |
| Stable page-aligned compressed slab pools and stable slot reuse | Candidate for clean reimplementation | Fits the target compressed residency store; lifetime and memory-pressure behavior require PulsarMLX tests. |
| `newBufferWithBytesNoCopy` over unified-memory slabs | Candidate for clean reimplementation | Use behind a narrow Objective-C++ bridge after alignment, lifetime, cancellation, and device-loss qualification. |
| Resolve interior pointers within registered slabs | Candidate for clean reimplementation | Useful for tensor views without per-expert registration churn; must be race-safe and bounds-checked. |
| Direct quantized GEMV rather than f32 materialization | Design reference now; clean implementation candidate later | Implement only in measured quant-format order and validate against the Python/NumPy oracle. |
| One command buffer for routed gate/up/SwiGLU/down/scatter | Design reference now; clean implementation candidate later | Relevant after a single quantized projection and expert pass their gates. |
| Submit resident experts while reading misses | Candidate for clean reimplementation | Matches the intended resident/missing partition, with explicit lease and cancellation semantics. |
| Persistent residency bookkeeping | Experimental candidate | Evaluate only if profiling shows buffer-binding overhead; avoid register/unregister churn regardless. |
| Separate setup, dispatch, kernel, I/O, wait, and scatter timing | Candidate for clean reimplementation | Adopt the measurement principle, not Colibri's measured values. |
| Passive CPU waits on Apple SoCs | Candidate for independent measurement | Colibri reports shared power-budget contention; PulsarMLX must reproduce the effect on its own hardware and workload. |
| Deterministic validation versus parallel performance modes | Candidate for clean reimplementation | Exact and numerical contracts must be explicit; parallel floating reductions are not described as bit exact. |
| Hard-coded GLM dimensions, container formats, or CPU fallback policy | Not directly applicable | PulsarMLX needs architecture plugins, its own GGUF quant formats, and fail-closed validation behavior. |
| Colibri benchmark numbers | Not applicable as evidence | Different model formats, machine, runtime, cache state, and protocol prevent direct comparison. |

## Important differences

Colibri is a C/Objective-C++ runtime with its own containers, quant formats,
execution graph, fallbacks, and benchmark protocol. PulsarMLX currently uses a
Python/NumPy architecture oracle and f32 MLX reference path over GGUF, with
Feature 016 exact-golden gates. Colibri's in-kernel IQ3/E8 path is not an
IQ2_XXS implementation and cannot replace PulsarMLX's decoder by analogy.

No Colibri source code was copied or adapted during this review. The review
records design ideas only. Any future attributed adaptation must be separately
reviewed for Apache-2.0 notice and source obligations.
