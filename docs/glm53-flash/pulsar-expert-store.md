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
