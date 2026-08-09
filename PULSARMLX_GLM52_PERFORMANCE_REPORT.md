# PulsarMLX GLM-5.2 performance report (in progress)

**Status**: living document for the weekend optimization sprint  
**Golden tag**: `v0.3.0-glm52-e2e-research`  
**Golden sequence**: `[9703, 21615, 220, 16, 13, 16, 16, 15, 15]`  
**Correctness rule**: optimized path must match golden before throughput claims

## Baseline research path (committed)

| Metric | Value | Evidence |
| --- | --- | --- |
| C11 wall (8 new tokens) | **48730.7 s** (~13.5 h) | `docs/research/glm52/raw/f016-c11-generation-0001.json` |
| Typical decode stack | ~**5335 s** | C11 log means |
| Logits (full vocab) | ~**79 s** | C11 log / C10 |

### Hotspot probe (layer 3, token 9703)

| Block | seconds |
| --- | ---: |
| moe_top8_plus_shared | ~50.8 |
| mla_layer3_pos0 | ~18.9 |
| shared_expert | ~10.0 |
| single_routed_expert | ~5.0 |
| router | ~0.06 |
| embed | ~0.01 |

Raw: `docs/research/glm52/raw/f016-hotspot-profile-0001.json`  
Narrative: `docs/research/glm52/HOTSPOT_REPORT.md`

**Primary cost**: expert dequant + SwiGLU matvec (×8 routed + 1 shared) per MoE layer × 76 MoE layers × tokens.

## MLX-only / cached path

| Milestone | Status |
| --- | --- |
| P1 first new token + expert cache | **golden prefix matched** — token `21615`; 15146.448 s |
| P2 two-token golden + useful reuse | ready after clean committed gate |
| Full 8-token golden match | blocked on P2 correctness + reuse |
| Expert prefetch | not started |
| Published tok/s | **not claimed** |

### Recovered P1 result

The original post-run JSON was recovered byte-for-byte after the reboot at
`docs/research/glm52/raw/f016-inference-p1-token1.json` (667 bytes, SHA-256
`b62c3062adc21498e1af19111202ac4a976aaa48106e7de7852f78280b8b2bfb`).
It records the exact sequence `[9703, 21615]`, matching the frozen first-token
golden prefix, with 15146.448245750013 seconds total wall time:

| Phase | Seconds |
| --- | ---: |
| Prompt-token stack | 6850.770356416004 |
| First-token logits | 92.97717149998061 |
| Generated-token stack | 8202.700665666023 |

The decoded expert cache recorded 0 hits, 4104 misses, 3934 evictions, and
8556380160 resident bytes. This proves the optimized path crossed its first
token-ID correctness gate, but it is not a performance success: the second
full stack pass also had no cache hit. The recovered legacy record does not
embed a schema identifier, checkpoint set hash, or execution commit. Its
checkpoint and source provenance therefore remain contextual rather than
self-contained, and no throughput or full-golden claim is promoted from P1.

### Cache-thrash diagnosis

The committed catalog and a committed 76-layer C09 routing trace drive the
checkpoint-free simulator at
`scripts/research/glm52_cache_simulator.py`. Its deterministic output is
`docs/research/glm52/raw/f016-cache-simulation-0001.json`. The trace is replayed
identically to isolate policy mechanics; P1 did not retain its own routed
expert IDs, so routed-expert overlap is not claimed.

| Quantity | Exact value |
| --- | ---: |
| Cache key | `tensor_name#expert_id` |
| Entries per full MoE stack | 2052 |
| Decoded bytes per tensor slab | 50331648 (48 MiB) |
| Decoded bytes per complete expert | 150994944 (144 MiB) |
| Decoded stack working set | 103280541696 (96.1875 GiB) |
| Compressed stack working set | 9070411776 (~8.4475 GiB) |
| Shared-expert decoded set | 11475615744 (10.6875 GiB) |
| Shared-expert compressed set | 2105769984 (~1.9612 GiB) |
| 8 GiB decoded capacity | 170 slabs (56 complete experts + 2 slabs) |

The legacy cache stores gate, up, and down as independent decoded Python-f32
row-list entries. It is created once per `generate` call and is not reset
between tokens. P1 performed exactly two 2052-access stacks; 4104 misses minus
3934 evictions equals the 170 resident entries, so the counters reconcile and
the second stack was not merely cold-start accounting. For an identical
sequential replay, each key's LRU stack distance is 2051 entries. Every tested
decoded-LRU budget from 8 through 48 GiB is smaller than the 96.1875 GiB set
and therefore produces zero warm decoded hits. This is classical cyclic LRU
thrash, not a router bottleneck or per-token cache reset.

The simulator separates storage and decode reuse:

| Policy | Budget | Warm storage hits | Warm decoded hits | Redequants |
| --- | ---: | ---: | ---: | ---: |
| decoded global LRU | 8–48 GiB | 0 | 0 | 2052 |
| compressed global LRU | 8 GiB | 0 | 0 | 2052 |
| compressed global LRU | 16–48 GiB | 2052 | 0 | 2052 |
| decoded shared-only | 8 GiB | 170 | 170 | 1882 |
| decoded shared-only | 16–48 GiB | 228 | 228 | 1824 |

The implemented P2 design is a protected decoded shared-expert tier:
shared experts execute at every MoE layer, so their reuse is guaranteed without
predicting routed experts. A logical 16 GiB budget contains all 228 shared
slabs and avoids their redequantization on the next token. The P2 runtime now
decodes into compact f32 storage, builds and synchronizes an MLX matrix, retains
only shared matrices, and releases each non-resident routed matrix after
synchronized use. It fails closed on MLX errors and records current/peak RSS
plus separate storage, decode, matrix-build, matvec, reuse, and transient-release
counters. These are model-free implementation facts; useful real-checkpoint
reuse remains unverified until P2. A compressed tier remains a later measured
storage experiment because its hits do not avoid dequantization.

## Configuration (defaults)

- Expert decoded cache budget: 8 GiB (legacy P1); 16 GiB (P2 protocol)
- Storage: existing multi-shard positional pread (no mmap change yet)
- Mode: inference (cached experts) vs research (uncached)
- P1 cache representation: decoded Python f32 rows, one cache entry per
  `tensor_name#expert_id`
- P2 policy: compact evaluated MLX/f32 shared-expert protection; 16 GiB logical
  cap, routed-matrix transient release, live memory admission, and RSS evidence

## Limitations

- Python research runtime, not a production server
- Residual scale on long research ladders is large; quality not claimed
- ssd-llm used for design only (no runtime dependency)
- P1 did not retain routing IDs, storage/dequant timing, bytes read, RSS, or a
  source/checkpoint identity inside the result; P2 uses a new self-contained
  evidence schema and is not merged with the legacy P1 record

## Commands

```sh
export PULSARMLX_GLM_GGUF=/path/to/final/GLM-5.2-UD-IQ2_XXS
.venv/bin/python scripts/research/glm52_profile_hotspots.py
.venv/bin/python scripts/research/glm52_inference.py --mode inference \
  --n-new 2 --cache-gib 16 --cache-policy decoded_shared_only \
  --out docs/research/glm52/raw/f016-inference-p2-token2.json
```
