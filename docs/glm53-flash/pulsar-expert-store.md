# PulsarExpertStore: LFU with decay and a persisted warm state (Flash AN, Graph 21)

`scripts/research/glm53_flash/dogfood/pulsar_expert_store.py` is a PulsarMLX-native
drop-in for mlx-vlm's `ExpertStore` (same repack format, same interface used
by `OffloadedSwitchGLU`/`patch_model`, same byte-budget semantics) with a
different residency policy: least-frequently-used with periodic
multiplicative decay (ties broken least-recently-touched), O(log n) eviction
through a heap with lazy invalidation, and a warm state (counters and the
resident set) persisted to `<offload>/pulsar-warm-state.json` and re-admitted
— and materialized — at construction, so a second request starts warm.

Qualified under the supervised successor harness (`successor.py
offload-pulsar`) on the graph-18 frozen store: values identical to the
graph-15 reference (the same admitted module), `stats()` equal to an explicit
stdlib LFU-with-decay model after every call of a seeded schedule chosen so
that LFU beats LRU on both cases (13 vs 9 and 16 vs 12 hits of 34) and every
control kills (decay disabled, tie-break inverted, warm state ignored); the
warm state round-trips to exactly the model's admitted set.

**A/B on the real model** (this MacBook Pro, 64 GB; unpruned mixed-4/8;
32 GB budget; the same 96-token greedy generation; single prompt):

| Store | Decode | Hit rate | Misses | Load |
|---|---|---|---|---|
| upstream LRU (cold) | 0.590 tok/s | 57.8% | 15,258 | 1.7 s |
| Pulsar v1 cold (O(n) eviction) | 0.593 | 59.1% | 14,804 | 2.0 s |
| Pulsar v1 warm (lazy warm set) | 0.546 | 62.3% | 13,625 | 2.0 s |
| **Pulsar v2 cold** | **0.616 (+4.4%)** | 59.1% | 14,804 | 1.9 s |
| **Pulsar v2 warm** | **0.620 (+5.1%)** | 62.3% | 13,626 | 20.9 s (materializes 32 GB) |

The honest reading: on one short prompt the policy buys a few percent; v1's
warm start *lost* throughput because its residents were only mmapped (hits
that still read from disk) and its Python `min()` eviction over ~2,000
residents cost more than the misses it saved — v2 fixes both. The policy has
little time to learn in 96 tokens; longer sessions and the persisted state
are where frequency should pay. Prefill is unchanged (upstream's bulk layer
loads). The bigger levers remain cross-layer prefetch and a prefill path that
does not read every expert file per chunk.

**A/B on the Mac Studio (M1 Ultra, 128 GB; offload dir on the internal SSD;
70 GB budget; same prompt and 96 tokens; 2026-09-17).** The warm start does
*not* pay here:

| Store | Decode (runs) | Hit rate | Decode misses | Warm load |
|---|---|---|---|---|
| upstream LRU | 3.00, 3.01, 3.08 tok/s | 77.8% | 4,325 | — |
| Pulsar v2 cold | 3.02, 2.98, 3.03, 3.05 | 77.8% | 4,342 | — |
| Pulsar v2 warm | 2.24, 2.14, 2.32, 2.35 | 85.1% | 3,678 | 17–20 s (70 GB) |

A per-token probe (dt, hits, misses, evictions per generated token; private
`dogfood/studio-ab.json`) separates two effects. First, both stores call
`mx.clear_cache()` after every eviction; with the store full from token 0 the
warm run makes 5,403 such calls and each following miss re-allocates its
14.2 MB buffers from the OS instead of reusing freed ones — stubbing the call
gives 2.32 → 2.62 (warm) and 3.03 → 3.35 (cold). Second, the least-squares
cost per miss is 2.4–3.1 ms in the cold runs but 7.4–9.7 ms in the warm runs
(and 5.8–7.9 ms for every store at a 50 GB budget: LRU 1.50, cold 1.66, warm
1.50 tok/s). The cold runs fill the store during the first quarter of decode
and degrade quarter by quarter (0.27 → 0.39 s/token); the warm runs sit at
0.43–0.45 throughout. So the 15% fewer misses of the warm set are each ~3×
more expensive, and at 96 tokens the cold runs are still riding the page
cache left by prefill's bulk loads. The reading: on a host where the store
plus the resident weights plus other applications fill memory, the warm
state's extra residency competes with the page cache that serves its misses;
the policy's hit-rate gain is real (85% vs 78%) and does not convert to
throughput at this budget. Next: bound the cache clearing (clear only when
MLX's buffer cache exceeds a threshold — a store-level change with the
measured 10–13% upside for both policies), then re-measure warm vs cold at
budgets that leave page-cache headroom, on longer generations.

## Graph 22: bounded allocator-cache clearing

`PulsarExpertStore(..., cache_clear_threshold_bytes=2 << 30)`: after an
evicting `get()` the store calls `mx.clear_cache()` only when
`mx.get_cache_memory()` is at or above the threshold (0 reproduces upstream's
clear-per-eviction; `None` never clears). In between, MLX's allocator reuses
the freed fixed-size expert buffers for the next miss. `stats()` reports
`cache_clear_threshold_bytes` and `cache_clears`. The residency policy,
values and warm state are untouched.

Qualification (same `offload-pulsar` operation, fixture v2): the stdlib
model additionally counts evicting gets (`eviction_events`); every case runs
under threshold 0 (the store's `cache_clears` must equal `eviction_events`
— 19 and 16 on the two cases — and must equal the number of real
`mx.clear_cache()` invocations counted through a wrapper) and under a 1 GiB
bound the tiny fixtures never reach (`cache_clears` must be 0). Two
structural mutants, recorded in the matrix before any run: `clear-always`
(threshold ignored) and `never-clear`; both KILL on both cases with reason
`cache-clears-mismatch`, alongside graph 21's three policy mutants.
Supervised PASS on CPU and Metal. Two fixture-contact corrections are in the
record: the model first counted evicting *calls* (10) where the store clears
per evicting *get* (19), and "cache is empty after the call" is not a valid
check (later allocations in the same call refill it) — replaced by the
invocation count. `run_offload.py --cache-clear-threshold-gb` (default 2;
0 = upstream; negative = never) selects it for the A/B.

**A/B (same prompt, 96 tokens; `thr0` = upstream-equivalent clearing,
`thr2` = the 2 GiB default; interleaved, two repetitions on the Studio):**

| Host / budget | LRU | Pulsar cold thr0 | cold thr2 | warm thr0 | warm thr2 |
|---|---|---|---|---|---|
| Studio M1 Ultra, 70 GB | 2.96 / 3.15 | 3.06 / 3.15 | 3.46 / 3.16 | 2.35 / 1.28¹ | 2.65 / 2.67 |
| MacBook M2 Max, internal NVMe, 32 GB | 0.951 | 1.081 | 1.109 | 1.040 | **1.139** |

¹ outlier: 46 s warm load and 0.57 prompt tok/s (host memory pressure at
load time; the other apps on that machine were not closed).

Bounded clearing is worth +13% on the Studio's warm runs and +9.5% on the
MacBook's, and 0–13% on cold runs (inside the cold side's run-to-run noise).
`cache_clears` stayed 0 at the 2 GiB threshold in every run — MLX's cache
never reaches it at an evicting get on this model, so the default behaves as
never-clear with MLX's own cache limit in charge — and peak memory was
identical with and without clearing (83.4 GB / 45.4 GB). On the MacBook the
warm start is now a gain (1.139 vs 1.109 cold, +20% over LRU); on the Studio
at 70 GB it is still a loss, consistent with the page-cache reading above.
Moving the MacBook's offload directory from the external drive to the
internal NVMe alone took LRU from 0.590 to 0.951 tok/s.
